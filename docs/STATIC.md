# Static build

The app can run entirely in the browser: recordings are aligned
(voicealign), measured (voicemeasure) and scored (`ui/scoring.js`) in the
page, so a host only needs to serve files. No Python, Docker or per-upload
processing on the server.

## Build

```sh
tools/setup_browser_analysis.sh   # once, and after changing voicealign/voicemeasure:
                                  # builds the WASM modules and downloads the model
                                  # (needs Rust's wasm32 target)
tools/build_static.py             # writes dist/ (or: tools/build_static.py OUT_DIR)
```

`dist/` (~133 MB, 54 files) holds the page (scripts and styles inlined), the
analysis worker, the WASM modules, the acoustic model and dictionaries
(~60 MB) and the example clips (~68 MB). It's git-ignored.

To try it locally: `python3 -m http.server 8000 --directory dist`, then open
<http://localhost:8000/>.

## Hosting

Upload `dist/` to any static web server or host. What matters:

- **HTTPS.** Browsers only allow recording from the microphone on HTTPS
  (or `localhost`). Uploading audio files works either way.
- **Compression and caching.** The model (`models/final.alimdl`, 50 MB) and
  dictionary download once per visit; serving them compressed and with long
  cache lifetimes makes later visits fast. The largest file is 50 MB, under
  common per-file limits (e.g. GitHub's 100 MB).
- **Licenses.** `dist/` redistributes MFA's acoustic model and dictionary
  (CC BY 4.0) and the CMU Pronouncing Dictionary (BSD-style); the help
  page's credits attribute them. The app itself is AGPL-3.0: if you host a
  modified version, link its source code.

## GitHub Pages

`.github/workflows/pages.yml` builds `dist/` and publishes it to GitHub
Pages on every push to `master` (or by hand from the Actions tab). The
model and dictionary are downloaded from MFA's releases during the build
(`tools/fetch_models.sh`) and cached between runs; they're part of the
published site, never of the repository.

One-time setup: in the repository's Settings → Pages, set Source to
"GitHub Actions". A project site is served at
`https://<user>.github.io/<repository>/`, so the repository's name is the
path. The page loads everything by relative URL, so it works under a
subpath.

## Differences from the server-backed app

- No fallback: if the in-browser analysis can't run (no WebAssembly or Web
  Workers, or the model fails to load), adding a clip fails with a message.
  The server-backed page (`serve.py`) falls back to `backend.cgi`.
- No noise reduction (the server runs sox's). On the example clips this
  shifts a clip's median resonance by a median 1.1 percentage points
  (up to 7.4); see docs/CURRENT.md.
- No server-side request logging.
