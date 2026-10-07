# Identity Platform Login UI Frontend Operator

A Kubernetes-native [Charmed Operator](https://juju.is/) that deploys and manages the Identity Platform Login UI Frontend application within Canonical's Identity Platform stack.

## Description

The `identity-platform-login-ui-frontend-operator` encapsulates the operational knowledge required to deploy, configure, scale, and manage the Login UI Frontend component on Kubernetes.

The Login UI Frontend provides the web user interface for user authentication, login flows, and user account interaction within Canonical's Identity Platform solution.

## Usage

### Deploying the Charm

Deploy the charm using Juju 3.x:

```bash
juju deploy identity-platform-login-ui-frontend-operator --channel=latest/edge
```

### Integrations

The charm integrates with other components in Canonical's Identity Platform stack via standard Juju relations:

- **Ingress**: Exposes the frontend service through `ingress` (e.g., NGINX Ingress Integrator or Istio).
- **Observability**: Integrates with Canonical Observability Stack (COS) for metrics, logging, and tracing.

## Development

### Prerequisites

- Python 3.12+
- Juju 3.x
- `charmcraft`

### Testing

Run unit tests:

```bash
tox run -e unit
```

Run lint checks:

```bash
tox run -e lint
```

## Spec-Driven Development (OpenSpec)

This repository adopts [OpenSpec](https://github.com/Fission-AI/openspec) for specification-driven development.
Active specifications are maintained in `openspec/specs/`. When proposing new features or architectural changes:

1. Propose a change using `/opsx-propose "Feature description"`.
2. Implement and verify the tasks outlined in `openspec/changes/<change-name>/tasks.md`.
3. Archive completed changes using `/archive-spec` on the pull request.

## Licence

The Charmed Identity Platform Login UI Frontend Operator is free software, distributed under the Apache Software License, version 2.0. See [LICENSE](LICENSE) for details.
