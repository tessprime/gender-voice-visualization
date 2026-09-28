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
- Uploads are processed in `/rec` inside the container. Failed runs leave
  their working directory there for debugging:
  `docker compose exec web ls /rec`.
- Request logging (`logs` in `settings.json`) is off in the container because
  the log directory doesn't exist. Logging also needs the non-public
  `countries.mmdb` GeoIP file.
- After editing anything under `ui/` or `resources/`, regenerate `index.html`
  with `docker compose exec web ./build.cgi` (or
  `docker run --rm -v "$PWD":/app gvv-dev ./build.cgi`).
