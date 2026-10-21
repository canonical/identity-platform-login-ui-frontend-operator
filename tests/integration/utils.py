# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

import base64
import json
import platform
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator

import boto3
import jubilant
import lightkube
import requests
import yaml
from botocore.config import Config
from integration.constants import (
    APP_NAME,
    EXPECTED_SECURITY_HEADERS,
    MINIO_ACCESS_KEY,
    MINIO_BUCKET,
    MINIO_SECRET_KEY,
    SAMPLE_BUNDLE_FILES,
)
from lightkube.generic_resource import create_namespaced_resource
from lightkube.models.meta_v1 import ObjectMeta
from lightkube.resources.apps_v1 import Deployment
from tenacity import retry, stop_after_attempt, wait_exponential

StatusPredicate = Callable[[jubilant.Status], bool]


def is_istio_control_plane_deployed() -> bool:
    """Return True if an Istio control plane (istiod) is already running in the cluster."""
    client = lightkube.Client()
    return any(True for _ in client.list(Deployment, namespace="*", labels={"app": "istiod"}))


def generate_self_signed_cert(common_name: str) -> tuple[str, str]:
    """Generate a base64-encoded self-signed TLS certificate and private key for MinIO."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cert_path = Path(tmpdir) / "public.crt"
        key_path = Path(tmpdir) / "private.key"
        subprocess.run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-keyout",
                str(key_path),
                "-out",
                str(cert_path),
                "-days",
                "1",
                "-subj",
                f"/CN={common_name}",
                "-addext",
                f"subjectAltName=DNS:{common_name}",
            ],
            check=True,
            capture_output=True,
        )
        cert_b64 = base64.b64encode(cert_path.read_bytes()).decode("utf-8")
        key_b64 = base64.b64encode(key_path.read_bytes()).decode("utf-8")
        return cert_b64, key_b64


def trust_ca_in_unit(
    juju: jubilant.Juju,
    unit_name: str,
    cert_b64: str,
    container: str | None = None,
) -> None:
    """Install a base64-encoded CA certificate into a unit's system trust store."""
    cmd = (
        f"echo '{cert_b64}' | base64 -d > /usr/local/share/ca-certificates/minio.crt "
        "&& update-ca-certificates"
    )
    if container:
        juju.ssh(unit_name, f'sh -c "{cmd}"', container=container)
    else:
        juju.exec(cmd, unit=unit_name)


def trust_ca_in_istio_gateway(
    model_name: str,
    cert_b64: str,
    s3_host: str,
    s3_port: int,
) -> None:
    """Configure the Istio Gateway in the test namespace to trust MinIO's self-signed CA."""
    envoy_filter_cls = create_namespaced_resource(
        group="networking.istio.io",
        version="v1alpha3",
        kind="EnvoyFilter",
        plural="envoyfilters",
    )
    cert_pem = base64.b64decode(cert_b64).decode("utf-8")
    ef = envoy_filter_cls(
        metadata=ObjectMeta(name="test-minio-ca-trust", namespace=model_name),
        spec={
            "configPatches": [
                {
                    "applyTo": "CLUSTER",
                    "match": {
                        "context": "GATEWAY",
                        "cluster": {
                            "service": f"{APP_NAME}-s3-external.{model_name}.svc.cluster.local",
                            "portNumber": s3_port,
                        },
                    },
                    "patch": {
                        "operation": "MERGE",
                        "value": {
                            "transport_socket": {
                                "name": "envoy.transport_sockets.tls",
                                "typed_config": {
                                    "@type": (
                                        "type.googleapis.com/"
                                        "envoy.extensions.transport_sockets.tls.v3.UpstreamTlsContext"
                                    ),
                                    "sni": s3_host,
                                    "common_tls_context": {
                                        "validation_context": {
                                            "trusted_ca": {
                                                "inline_string": cert_pem,
                                            }
                                        }
                                    },
                                },
                            }
                        },
                    },
                }
            ]
        },
    )
    client = lightkube.Client(field_manager="integration-test")
    client.apply(ef, field_manager="integration-test", force=True)


def assert_security_headers(response: requests.Response) -> None:
    """Assert that a response contains all required security and cache-control headers."""
    for header_name, expected_value in EXPECTED_SECURITY_HEADERS.items():
        assert response.headers.get(header_name) == expected_value


def juju_model_factory(model_name: str) -> jubilant.Juju:
    juju = jubilant.Juju()
    try:
        juju.add_model(model_name, config={"logging-config": "<root>=INFO"})
    except jubilant.CLIError as e:
        if "already exists" not in e.stderr:
            raise

    juju.model = model_name

    arch_map = {
        "aarch64": "arm64",
        "arm64": "arm64",
        "x86_64": "amd64",
        "amd64": "amd64",
    }
    host_arch = arch_map.get(platform.machine().lower(), "amd64")
    juju.cli("set-model-constraints", f"arch={host_arch}")

    return juju


def get_unit_data(model: jubilant.Juju, unit_name: str) -> dict:
    """Get the data for a given unit."""
    stdout = model.cli("show-unit", unit_name)
    cmd_output = yaml.safe_load(stdout)
    return cmd_output[unit_name]


def get_integration_data(
    juju: jubilant.Juju, app_name: str, integration_name: str, unit_num: int = 0
) -> dict | None:
    """Get the integration data for a given integration."""
    data = get_unit_data(juju, f"{app_name}/{unit_num}")
    return next(
        (
            integration
            for integration in data.get("relation-info", [])
            if integration["endpoint"] == integration_name
        ),
        None,
    )


def get_app_integration_data(
    model: jubilant.Juju,
    app_name: str,
    integration_name: str,
    unit_num: int = 0,
) -> dict | None:
    """Get the application data for a given integration."""
    data = get_integration_data(model, app_name, integration_name, unit_num)
    return data["application-data"] if data else None


def get_unit_address(juju: jubilant.Juju, app_name: str, unit_num: int = 0) -> str:
    """Get the address of a given unit."""
    data = get_unit_data(juju, f"{app_name}/{unit_num}")
    return data["address"]


def upload_sample_bundle(endpoint_url: str) -> None:
    """Create a public S3 bucket in MinIO and upload the sample static bundle."""
    s3_client = boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        verify=False,
        config=Config(
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        ),
    )
    existing_buckets = {bucket["Name"] for bucket in s3_client.list_buckets().get("Buckets", [])}
    if MINIO_BUCKET not in existing_buckets:
        s3_client.create_bucket(Bucket=MINIO_BUCKET)

    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"AWS": ["*"]},
                "Action": ["s3:GetObject"],
                "Resource": [f"arn:aws:s3:::{MINIO_BUCKET}/*"],
            }
        ],
    }
    s3_client.put_bucket_policy(Bucket=MINIO_BUCKET, Policy=json.dumps(policy))

    for key, body in SAMPLE_BUNDLE_FILES.items():
        content_type = "text/html" if key.endswith(".html") else "application/javascript"
        s3_client.put_object(
            Bucket=MINIO_BUCKET,
            Key=key,
            Body=body.encode("utf-8"),
            ContentType=content_type,
        )


@contextmanager
def remove_integration(
    juju: jubilant.Juju, /, remote_app_name: str, integration_name: str
) -> Iterator[None]:
    """Temporarily remove an integration from the application."""
    if ":" in remote_app_name:
        remote_endpoint = remote_app_name
    elif integration_name == "istio-ingress":
        remote_endpoint = f"{remote_app_name}:istio-ingress-route"
    elif integration_name == "traefik-ingress":
        remote_endpoint = f"{remote_app_name}:traefik-route"
    else:
        remote_endpoint = remote_app_name

    @retry(
        wait=wait_exponential(multiplier=2, min=1, max=30),
        stop=stop_after_attempt(10),
        reraise=True,
    )
    def _reintegrate() -> None:
        juju.integrate(f"{APP_NAME}:{integration_name}", remote_endpoint)

    juju.remove_relation(f"{APP_NAME}:{integration_name}", remote_endpoint)
    try:
        yield
    finally:
        _reintegrate()


def all_active(*apps: str) -> StatusPredicate:
    return lambda status: (
        jubilant.all_active(status, *apps) and jubilant.all_agents_idle(status, *apps)
    )


def all_blocked(*apps: str) -> StatusPredicate:
    return lambda status: (
        jubilant.all_blocked(status, *apps) and jubilant.all_agents_idle(status, *apps)
    )


def all_idle(*apps: str) -> StatusPredicate:
    return lambda status: jubilant.all_agents_idle(status, *apps)


def any_error(*apps: str) -> StatusPredicate:
    return lambda status: jubilant.any_error(status, *apps)


def is_active(app: str) -> StatusPredicate:
    return lambda status: status.apps[app].is_active and jubilant.all_agents_idle(status, app)


def is_blocked(app: str) -> StatusPredicate:
    return lambda status: status.apps[app].is_blocked and jubilant.all_agents_idle(status, app)


def unit_number(app: str, expected_num: int) -> StatusPredicate:
    return lambda status: len(status.apps[app].units) == expected_num


def and_(*predicates: StatusPredicate) -> StatusPredicate:
    return lambda status: all(predicate(status) for predicate in predicates)


def or_(*predicates: StatusPredicate) -> StatusPredicate:
    return lambda status: any(predicate(status) for predicate in predicates)
