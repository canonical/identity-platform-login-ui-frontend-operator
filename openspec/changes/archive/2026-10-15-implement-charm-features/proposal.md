# Proposal

## Why

The `identity-platform-login-ui-frontend-operator` previously contained boilerplate workload container logic (Pebble) that did not align with the product architecture. The frontend application is a pre-compiled Next.js static bundle hosted in an S3-compatible object store. This charm must operate as a pure Kubernetes-native operator ("no workload") that configures Ingress providers (Traefik or Istio) to fetch assets directly from the S3 bucket and serve them under the `/ui/` public path.

## What Changes

- **BREAKING**: Remove the Pebble workload container orchestration, local application port bindings, and workload-specific observability relations from `charmcraft.yaml` and `src/charm.py`.
- Introduce configuration options for the S3 bundle URL (`ui-bundle-url`) and Istio gateway/proxy settings (`istio-route-hostnames`, `istio-egress-proxy`, `istio-gateway-workload-labels`, `istio-resources-namespace`).
- Add support for Traefik ingress configuration via the `traefik_route` interface (`traefik-ingress` relation), rendering dynamic configuration via `templates/traefik-route.json.j2` for redirects (`/ui` and `/ui/<page>/`), root (`/ui/`), extension-less HTML pages, static assets, custom 404 handling, and security response headers.
- Add support for Istio ingress configuration via the `istio_ingress_route` interface (`istio-ingress` relation) exposing all static application pages and Kubernetes API resources (`ServiceEntry`, `DestinationRule`, and `EnvoyFilter` via `lightkube`).
- Implement automated health checking (HEAD requests to `/index.html`) and status reporting (`BlockedStatus`, `WaitingStatus`, `ActiveStatus`).

## Capabilities

### New Capabilities
- `frontend-ingress`: Manages public Ingress routing (Traefik and Istio) to static Next.js frontend bundles stored in S3-compatible object storage.

### Modified Capabilities
*(None)*

## Non-goals

- Running a local workload container or proxy inside the charm pod.
- Managing readiness relations with `identity-platform-login-ui-operator`.
- Uploading, versioning, or modifying files inside the S3 bucket.
- Custom private Certificate Authority (CA) configuration.
- Routing non-UI API endpoints (such as `/self-service` or `/api/`).

## Success Metrics

- 100% of `/ui/` HTTP traffic correctly routed through Traefik and Istio ingress layers to external S3 buckets.
- Zero workload containers running in the charm pod.
- Comprehensive status reporting reflecting missing configuration, missing relation, or S3 unreachable errors.

## Workload Data Provenance

| Configuration Option | Source / Provenance | Purpose | Target Component |
| :--- | :--- | :--- | :--- |
| `ui-bundle-url` | Juju User Configuration | S3 URL identifying bucket & folder path | Traefik / Istio Route rules |
| `istio-egress-proxy` | Juju User Configuration | Host:port HTTP proxy endpoint for PS7 egress | Istio EnvoyFilter tunnel |
