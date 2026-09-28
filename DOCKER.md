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

Then open <http://localhost:8000/>.

The first build downloads a few GB of conda packages and takes a while. Later
runs reuse the cached image. You only need to rebuild after changing the
`Dockerfile`.

## Notes

- Processing a recording takes about a minute, most of it in MFA.
- Uploads are processed in `/rec` inside the container, which is mounted from
  `./rec` in your checkout. With `"dev": true` in `settings.json`, every clip's
  directory is kept, successful or not. It holds the original upload (`orig`),
  the cleaned audio, `align.log` (aligner console output), `mfa_logs/` (MFA's
  per-step logs, e.g. `alignment/log/align.1.log`) and `output/` (the
  TextGrid, if alignment succeeded). To rerun alignment by hand:
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
