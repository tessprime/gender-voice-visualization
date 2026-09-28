#!/usr/bin/env bash
# Build (if needed) and run the dev container with the repo bind-mounted at /app.
# Equivalent to `docker compose up --build` for machines without the compose plugin.
set -euo pipefail
cd "$(dirname "$0")"

docker build --network=host -t gvv-dev .
exec docker run --rm -it -p 8000:8000 -v "$PWD":/app gvv-dev "$@"
