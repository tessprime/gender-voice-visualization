# Docker development environment

The Docker image contains the whole backend toolchain: Montreal Forced Aligner
(with the `english_us_arpa` models), praat, ffmpeg, sox, and the Python
dependencies. It does **not** contain the site's source. Your checkout is
bind-mounted at `/app`, so edits to `ui/`, `acousticgender/`, `backend.cgi`,
etc. take effect on the next request with no rebuild.

## Run

```sh
docker compose up --build
# or, without the compose plugin:
./docker-dev.sh
```

Then open <http://localhost:8000/>. The port is published on loopback only,
so other machines can't reach it, and `serve.py` only serves the page,
`ui/` and `resources/` (plus uploads to `backend.cgi`). Everything else,
including the recordings in `rec/`, `.git/` and `settings.json`, returns 404.
To reach the server from another device, change `127.0.0.1:8000:8000` in
`docker-compose.yml` (or `docker-dev.sh`), knowing it has no authentication.

The first build downloads a few GB of conda packages and takes a while. Later
runs reuse the cached image. You only need to rebuild after changing the
`Dockerfile`.

## Notes

- `serve.py` loads [phonealign](phonealign/README.md) at startup (a few
  seconds) and processes uploads itself, in ~2-2.5 s for a 25 s recording.
  Each upload logs its timing (`clip <id> processed in ...`). If phonealign
  fails to load, the log says so and uploads fall back to `backend.cgi`,
  which runs `mfa align` per request (~8-10 s).
- Uploads are processed in `/rec` inside the container, which is mounted from
  `./rec` in your checkout. Each clip's directory is deleted as soon as it's
  processed, successful or not, since it holds the user's recording. To keep
  them for debugging, add `"keep_recordings": true` to `settings.json`; then
  clean up `./rec` yourself, as nothing else will. A kept directory holds
  the original upload (`orig`),
  the cleaned audio, `align.log` (the aligner's output or error) and
  `output/` (the TextGrid, if alignment succeeded). Clips processed by
  `backend.cgi` also have `mfa_logs/` (MFA's per-step logs, e.g.
  `alignment/log/align.1.log`) and an `align.sh` to rerun alignment by hand:
  `docker compose exec web bash -c 'cd /rec/<id> && ./align.sh'`.
- `./rec` must be world-writable because the CGI runs as `nobody`.
  `docker-dev.sh` handles this. With compose, run
  `mkdir -p rec && chmod a+rwx rec` once.
- Request logging (`logs` in `settings.json`) is off in the container because
  the log directory doesn't exist. Logging also needs the non-public
  `countries.mmdb` GeoIP file.
- After editing anything under `ui/` or `resources/`, regenerate `index.html`
  with `docker compose exec web ./build.cgi` (or
  `docker run --rm -v "$PWD":/app gvv-dev ./build.cgi`).
