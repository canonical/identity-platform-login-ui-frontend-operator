# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

resource "juju_application" "login_ui_frontend" {
  name  = var.app_name
  model = var.model_name

  charm {
    name    = "identity-platform-login-ui-frontend-operator"
    channel = var.channel
    base    = var.base
  }

  config    = var.config
  resources = var.resources
  units     = var.units
}
