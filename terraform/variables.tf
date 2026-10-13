# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

variable "app_name" {
  description = "Application name"
  type        = string
  default     = "identity-platform-login-ui-frontend"
}

variable "model_name" {
  description = "Juju model name"
  type        = string
}

variable "channel" {
  description = "Charm channel"
  type        = string
  default     = "latest/edge"
}

variable "base" {
  description = "Base operating system version"
  type        = string
  default     = "ubuntu@22.04"
}

variable "config" {
  description = "Application configuration options"
  type        = map(string)
  default     = {}
}

variable "resources" {
  description = "Application resources"
  type        = map(string)
  default     = {}
}

variable "units" {
  description = "Number of units to deploy"
  type        = number
  default     = 1
}
