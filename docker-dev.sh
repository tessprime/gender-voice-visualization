#!/usr/bin/env bash
# Build (if needed) and run the dev container with the repo bind-mounted at /app.
# Equivalent to `docker compose up --build` for machines without the compose plugin.
set -euo pipefail
cd "$(dirname "$0")"

# Clips are processed in ./rec (mounted at /rec). The CGI runs as `nobody`, so
# the directory must be world-writable.
mkdir -p rec
chmod a+rwx rec

docker build --network=host -t gvv-dev .
exec docker run --rm -it -p 8000:8000 -v "$PWD":/app -v "$PWD/rec":/rec gvv-dev "$@"
