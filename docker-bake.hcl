# docker-bake.hcl for Diatreme image CI and release promotion.
#
# Diatreme injects:
#   VERSION    pr-<N> during PR CI, release tag during release
#   REGISTRY   container registry, default ghcr.io
#   IMAGE_NAME <owner>/dunmir-agent from the workflow image_name input
#   PLATFORMS  comma-separated platform list

variable "VERSION" {
  default = "latest"
}

variable "REGISTRY" {
  default = "ghcr.io"
}

variable "IMAGE_NAME" {
  default = "magmamoose/dunmir-agent"
}

variable "PLATFORMS" {
  default = "linux/amd64,linux/arm64"
}

target "dunmir-agent" {
  context = "apps/dunmir/agent"
  dockerfile = "Dockerfile"
  platforms = split(",", PLATFORMS)
  tags = ["${REGISTRY}/${IMAGE_NAME}:${VERSION}"]
}

group "default" {
  targets = ["dunmir-agent"]
}
