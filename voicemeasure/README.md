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

- **Formants** (`to_formant_burg`): done. On the test recording, at vowel
  midpoints, F1-F3 are within a median of 0.05-0.18 Hz of Praat 6.4.06
  (largest 4.5-10 Hz).
- **Pitch** (`To Pitch`, autocorrelation): not yet.
- **Values at a time** (`Get value at time ... Hertz Linear`): not yet.

## Comparing with Praat

```sh
# Praat's frames (in the app's Docker image, which has Praat):
praat --run reference/dump_tracks.praat recording.wav out/praat
# voicemeasure's frames:
cargo run --release --example dump_tracks -- recording.wav out/ours
python3 reference/compare.py out/praat out/ours
```

## License

Not decided yet; it contains no GPL code, so it's free to choose.
