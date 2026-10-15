# Spec Delta

## Purpose

The `frontend-ingress` capability defines the operational contract for publishing a compiled Next.js static frontend application bundle hosted in S3-compatible object storage under the `/ui/` public HTTP path using Traefik or Istio ingress layers.

## ADDED Requirements

### Requirement: S3 Bundle URL Parsing and Configuration Validation

The charm SHALL validate and parse the `ui-bundle-url` configuration option to extract the upstream origin scheme/host, hostname, port, and base path.

#### Scenario: Valid HTTPS S3 URL configured
- **WHEN** `ui-bundle-url` is set to a valid HTTPS URL such as `https://s3.example.com/dist` or `https://s3.example.com:8443/swift/v1/AUTH_123/bucket`
- **THEN** the charm SHALL split the URL into origin (`https://s3.example.com` or `https://s3.example.com:8443`), hostname (`s3.example.com`), port (`443` or `8443`), and base path (`/dist` or `/swift/v1/AUTH_123/bucket`).

#### Scenario: Missing or Invalid S3 URL
- **WHEN** `ui-bundle-url` is empty, malformed, contains credentials, query parameters, fragments, or uses a non-HTTPS scheme
- **THEN** the charm SHALL set unit status to `BlockedStatus` with an explicit error message stating that `ui-bundle-url` must be a valid HTTPS URL.

### Requirement: Traefik Ingress Route Reconciliation

The charm SHALL configure Traefik dynamic routing via the `traefik-ingress` relation (`traefik_route`) to forward `/ui/` traffic to the S3 bucket upstream.

#### Scenario: Traefik relation joined with valid configuration
- **WHEN** the `traefik-ingress` relation is established and `ui-bundle-url` is valid
- **THEN** the charm SHALL submit dynamic configuration containing five routers:
  1. Redirect router (priority 400): Exact `/ui` redirects permanently (HTTP 301) to `/ui/`.
  2. Page-slash-redirect router (priority 350): Trailing-slash page paths `/ui/<page>/` redirect permanently (HTTP 301) to `/ui/<page>`.
  3. Root router (priority 300): Exact `/ui/` rewrites path to `<base_path>/index.html`.
  4. Page router (priority 200): Extension-less page paths under `/ui/<page>` rewrite path to `<base_path>/<page>.html`.
  5. Asset router (priority 100): PathPrefix `/ui/` rewrites path prefix to `<base_path>/`.
- **AND** configured routers SHALL use `passHostHeader: false`, custom 404 error middleware (`<base_path>/404.html`), and security response headers (`Permissions-Policy`, `Cache-Control`, `Content-Security-Policy`, `X-Frame-Options`, `X-Content-Type-Options`).

### Requirement: Istio Ingress Route & K8s Egress Resource Reconciliation

The charm SHALL submit HTTPRoute configuration via the `istio-ingress` relation (`istio_ingress_route`) and create external Kubernetes egress and route rewrite resources (`ServiceEntry`, `DestinationRule`, and `EnvoyFilter`) using `lightkube`.

#### Scenario: Istio relation joined in Direct Egress mode (PS6)
- **WHEN** `istio-ingress` relation exists, `ui-bundle-url` is valid, and `istio-egress-proxy` is empty
- **THEN** the charm SHALL submit `IstioIngressRouteConfig` declaring five `HTTPRoute` entries (`ui-redirect`, `ui-root`, `ui-page-slash-redirect`, `ui-page`, and `ui-assets`, scoped to `istio-route-hostnames` when configured) targeting `<app>-s3-external`: Exact `/ui` redirect (HTTP 301 to `/ui/`), Exact `/ui/` root rewrite to `<base_path>/index.html`, RegularExpression `^/ui/([^/.]+)/$` trailing-slash route, RegularExpression `^/ui/([^/.]+)$` page route, and PathPrefix `/ui` asset rewrite to `<base_path>`.
- **AND** the charm SHALL create a Kubernetes `ServiceEntry` (`<app>-s3-external.<namespace>.svc.cluster.local`, protocol `HTTPS` on `bundle.port` with `dnsName: bundle.hostname`), a `DestinationRule` (TLS SIMPLE with SNI `bundle.hostname` on `bundle.port`), and an `EnvoyFilter` (`<app>-ui-rewrite`) configuring regex redirect (`ui-page-slash-redirect` to `/ui/\1`), regex path rewrite (`ui-page` to `<base_path>/\1.html`), `:authority` header override to `bundle.hostname`, and security response headers (`Permissions-Policy`, `Cache-Control`, `Content-Security-Policy`, `X-Frame-Options`, `X-Content-Type-Options`) on `ui-root`, `ui-assets`, and `ui-page` routes using `lightkube`.

#### Scenario: Istio relation joined in Proxy Tunnel mode (PS7)
- **WHEN** `istio-ingress` relation exists and `istio-egress-proxy` is set to `proxy.example.com:3128`
- **THEN** the charm SHALL additionally verify `istio-gateway-workload-labels` is configured.
- **AND** the charm SHALL create an internal `ServiceEntry` (`<app>-s3-external.<namespace>.svc.cluster.local`) and `DestinationRule` (with SNI set to the S3 hostname) targeting port `15999`, the `<app>-ui-rewrite` `EnvoyFilter`, and a `<app>-proxy-tunnel` `EnvoyFilter` configuring a loopback TCP tunnelling `LISTENER` on `127.0.0.1:15999` and a `CLUSTER` pointing to the upstream proxy.

#### Scenario: Missing Juju Trust for Istio Kubernetes resources
- **WHEN** Istio relation exists but the charm lacks Kubernetes API permissions (`juju deploy --trust` was omitted)
- **THEN** the charm SHALL set unit status to `BlockedStatus` stating that Juju trust is required to manage Istio egress resources.

### Requirement: Health Checking and Unit Status Evaluation

The charm SHALL perform HTTP HEAD health checks on `/index.html` against the S3 origin and reflect operational readiness in unit status.

#### Scenario: Successful health check and active ingress
- **WHEN** required configuration is valid, an Ingress relation exists, and HEAD request to `/index.html` returns HTTP 200..399
- **THEN** the charm SHALL set unit status to `ActiveStatus`.

#### Scenario: S3 Bucket or Bundle Unreachable
- **WHEN** HEAD check to `/index.html` returns HTTP >= 400 or TLS/DNS resolution fails
- **THEN** the charm SHALL set unit status to `BlockedStatus` with an actionable diagnostic message detailing the reachability failure.

#### Scenario: Missing Ingress Relation
- **WHEN** no `traefik-ingress` or `istio-ingress` relation exists
- **THEN** the charm SHALL set unit status to `WaitingStatus` waiting for an Ingress relation.
