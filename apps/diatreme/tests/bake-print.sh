#!/usr/bin/env bash
set -euo pipefail

export REGISTRY="ghcr.io"
export IMAGE_NAME="example/my-app"
export VERSION="v0.0.0-test"
export PLATFORMS="linux/amd64"

docker buildx bake -f examples/config/docker-bake.hcl default --print >/dev/null
docker buildx bake -f examples/config/docker-bake.hcl api --print >/dev/null
docker buildx bake -f examples/config/docker-bake.hcl worker --print >/dev/null

echo "Docker Bake examples render successfully."
