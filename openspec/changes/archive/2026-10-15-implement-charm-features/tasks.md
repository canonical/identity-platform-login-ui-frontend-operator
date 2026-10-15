# Tasks

## 1. Metadata and Configuration Cleanup

- [x] 1.1 Update `charmcraft.yaml` to remove workload container, Pebble definitions, and local workload relations, and define required config options (`ui-bundle-url`, `istio-route-hostnames`, `istio-egress-proxy`, `istio-gateway-workload-labels`, `istio-resources-namespace`) and relations (`traefik-ingress`, `istio-ingress`). Verify with `charmcraft expand-extensions`.
- [x] 1.2 Refactor `src/constants.py` and `src/exceptions.py` to remove Pebble constants and add S3/Ingress/security-header constants and exceptions. Verify via unit tests in `tests/unit/test_constants.py`.

## 2. Configuration & URL Parsing Core Modules

- [x] 2.1 Create `src/config.py` to perform typed parsing and validation of charm config options in `charmcraft.yaml`. Verify with unit tests in `tests/unit/test_config.py`.
- [x] 2.2 Create `src/bundle.py` to split `ui-bundle-url` into origin, hostname, port, and base path components. Verify with unit tests in `tests/unit/test_bundle.py`.
- [x] 2.3 Create `BundleHealthCheck` in `src/services.py` to perform HEAD health checks against S3 origin `/index.html` honouring `JUJU_CHARM_HTTPS_PROXY`. Verify with unit tests in `tests/unit/test_services.py`.

## 3. Traefik Ingress Integration

- [x] 3.1 Create `TraefikRouteData` in `src/integrations.py` and `templates/traefik-route.json.j2` to construct dynamic configuration for redirect, root, page-slash-redirect, page, and asset routers, custom 404 error middleware, and security response headers. Verify with unit tests in `tests/unit/test_integrations.py`.
- [x] 3.2 Update `src/charm.py` to integrate `TraefikRouteRequirer` and reconcile Traefik dynamic configuration. Verify with unit tests in `tests/unit/test_charm.py`.

## 4. Istio Ingress & Lightkube Egress Integration

- [x] 4.1 Create `IstioIngressRouteData` in `src/integrations.py` and `IstioMeshService` in `src/services.py` to build `IstioIngressRouteConfig` and manage K8s CRDs (`ServiceEntry`, `DestinationRule`, `EnvoyFilter`) using `lightkube`. Verify with unit tests in `tests/unit/test_integrations.py` and `tests/unit/test_services.py`.
- [x] 4.2 Update `src/charm.py` to integrate `IstioIngressRouteRequirer` and reconcile Istio route and egress resources via `lightkube`, including cleanup on relation broken or charm removal. Verify with unit tests in `tests/unit/test_charm.py`.

## 5. Central Reconciliation & Status Evaluation

- [x] 5.1 Implement `_holistic_handler()` in `src/charm.py` to coordinate config validation, ingress reconciliation, health checks, and status evaluation (`ActiveStatus`, `WaitingStatus`, `BlockedStatus`). Verify with comprehensive Scenario unit tests in `tests/unit/test_charm.py`.

## 6. Verification Suite

- [x] 6.1 Run full unit test suite via `tox -e unit` and verify 100% test pass rate and coverage requirements.
- [x] 6.2 Execute integration tests via `tox -e integration` using `jubilant` / `pytest` against HTTPS-configured MinIO and Traefik/Istio ingress providers.

## 7. Documentation & Rollout

- [x] 7.1 Update `README.md` and charm documentation to detail configuration options, relation requirements, and `juju deploy --trust` deployment instructions.

## Implementation Notes

- Refactored into a 3-layer charm structure (`src/charm.py`, `src/integrations.py`, `src/services.py`, `src/config.py`, `src/bundle.py`, `src/utils.py`, and `templates/traefik-route.json.j2`).
- Rewrote unit test suite using `ops.testing.Context` and `ops.testing.State` (`Scenario`).
- Configured `.github/workflows/ci.yaml` to reuse `canonical/identity-team/.github/workflows/charm-pull-request.yaml`.
