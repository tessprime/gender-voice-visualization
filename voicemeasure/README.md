# voicemeasure

Pitch and formant analysis that produces the same numbers as Praat's
`To Pitch` and `To Formant (burg)`, in Rust so it can run in the browser
(WebAssembly). It replaces the Praat step of the app's pipeline
(`textgrid-formants.praat`): the app's reference data (`stats.json`) was
built from Praat's measurements, so a replacement has to match them.

The algorithms are implemented from Praat's published documentation (its
manual, and Boersma 1993 for pitch), not from Praat's source code, which is
GPL. Real Praat is the reference for testing.

Meant to become its own crate; keep it independent of the web app.

## Status

Compared with Praat 6.4.06 on the web app's 21 example clips, at their
1475 vowel midpoints (`reference/check_examples.py`):

- **Formants** (`to_formant_burg`): F1-F3 differ by a median 0.11 / 0.24 /
  0.36 Hz. A few percent of frames contain very broad, numerically fragile
  formants that one side places differently, renumbering those above.
- **Pitch** (`to_pitch`): F0 differs by a median 0.018 Hz (99.6% within
  1 Hz); voicing agrees at 98.7% of vowels. voicemeasure calls a few more
  frames voiced at the edges of voiced stretches than Praat does.
- **Values at a time** (`measure_at`, `pitch_at`, `formant_at`): as
  `Get value at time ... Hertz Linear`.

Undocumented details were settled by comparison with Praat; see
`docs/CURRENT.md` in the web app's repository.

## WebAssembly

```sh
cargo build --release --target wasm32-unknown-unknown
# -> target/wasm32-unknown-unknown/release/voicemeasure.wasm (~320 KB, ~120 KB gzipped)
node reference/check_wasm.mjs target/wasm32-unknown-unknown/release/voicemeasure.wasm recording.wav times.txt
```

The module exports `vm_alloc`, `vm_measure` and `vm_free` (see `src/wasm.rs`);
`reference/check_wasm.mjs` shows how to call them. On a 26 s recording,
measuring takes ~270 ms in Chromium; Firefox is currently much slower
(~7.5 s in Playwright's Firefox build), cause not yet known.

`cargo run --release --example bench -- recording.wav` times each stage.

## Comparing with Praat

```sh
# Praat's frames (in the app's Docker image, which has Praat):
praat --run reference/dump_tracks.praat recording.wav out/praat
# voicemeasure's frames:
cargo run --release --example dump_tracks -- recording.wav out/ours
python3 reference/compare.py out/praat out/ours

# The example clips, end to end (from the web app's repository root):
cargo build --release --manifest-path voicemeasure/Cargo.toml --examples
python3 voicemeasure/reference/check_examples.py out/examples
```

## License

MIT (see `LICENSE`). It contains no Praat (GPL) code: the algorithms are
implemented from Praat's published documentation. It's licensed separately
from the web app it was written for (AGPL-3.0).
