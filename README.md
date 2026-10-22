# Login UI Frontend Operator Charm

A pure Kubernetes Juju charm operator that proxies and routes incoming traffic to an S3-hosted Next.js static application bundle for the Canonical Identity Platform.

## Overview

The **Login UI Frontend Operator** manages dynamic ingress routing and egress rules for a Next.js static UI bundle stored on an S3-compatible object store (such as AWS S3 or MinIO). The charm operates as a pure operator (no local Pebble container) and routes requests through either Traefik or Istio ingress providers.

## Key Features

- **S3 Bundle Proxying**: Routes incoming requests to a dynamic S3 origin specified by `ui-bundle-url`.
- **Dynamic Path Rewriting**: Automatically maps UI page routes (e.g. `/ui/login` -> `/login.html`, `/ui/consent` -> `/consent.html`) and asset paths.
- **Traefik Ingress Support**: Integrates with `traefik-k8s` via the `traefik-ingress` relation (`traefik_route` interface v0).
- **Istio Ingress & Egress Support**: Integrates with Istio via `istio-ingress` (`istio_ingress_route` interface) and dynamically manages Kubernetes CRDs (`ServiceEntry`, `DestinationRule`, and `EnvoyFilter`) using `lightkube`.
- **Automated Health Checking**: Performs HEAD health checks against `/index.html` on the S3 bundle origin, respecting `JUJU_CHARM_HTTPS_PROXY`.

## Configuration Options

| Option | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `ui-bundle-url` | string | *(Required)* | Full HTTPS URL to the S3 bucket directory containing static UI assets (e.g. `https://s3.example.com/my-bucket/dist`). |
| `istio-route-hostnames` | string | `""` | Comma-separated list of hostnames for Istio HTTPRoute matching. |
| `istio-resources-namespace` | string | `""` | Namespace override for Istio gateway and EnvoyFilter CRD deployment. |

## Relations

### `traefik-ingress` (`traefik_route`)
Requirer relation to `traefik-k8s` providing dynamic Traefik configuration for path routing, redirects, and error handling.

```bash
juju relate login-ui-frontend:traefik-ingress traefik-k8s:traefik-route
```

### `istio-ingress` (`istio_ingress_route`)
Requirer relation to Istio ingress gateway for HTTPRoute rules.

```bash
juju relate login-ui-frontend:istio-ingress istio-ingressgateway:ingress
```

## Deployment Instructions

> [!IMPORTANT]
> The charm manages Kubernetes custom resources (`ServiceEntry`, `DestinationRule`, `EnvoyFilter`) via `lightkube`. It **must** be deployed with `--trust` to grant cluster-level API permissions.

```bash
juju deploy ./identity-platform-login-ui-fe-operator_ubuntu-22.04-amd64.charm \
  --trust \
  --config ui-bundle-url="https://s3.example.com/bucket/dist"
```

## Testing

Run unit tests locally:

```bash
PYTHONPATH=src:lib .venv/bin/pytest tests/unit/
```
