# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

output "app_name" {
  description = "Name of the deployed application"
  value       = juju_application.login_ui_frontend.name
}

output "provides" {
  description = "Map of provides endpoint names"
  value = {
    metrics_endpoint  = "metrics-endpoint"
    grafana_dashboard = "grafana-dashboard"
  }
}

output "requires" {
  description = "Map of requires endpoint names"
  value = {
    logging      = "logging"
    tracing      = "tracing"
    public_route = "public-route"
  }
}
