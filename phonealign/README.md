# phonealign

Fast forced alignment of a single short recording to its transcript: a
replacement for running the Montreal Forced Aligner (`mfa align`) once per
request. See "Full audio pipeline in under a second" in
[`docs/ROADMAP.md`](../docs/ROADMAP.md).

This lives in this repository for now but is meant to become its own
package, so keep it independent of the web app: it must not import from
`acousticgender` or read the app's `settings.json`.

## Why

`mfa align` is built for large corpora. For one clip, nearly all of its
~6 s is overhead (imports, a SQLite corpus database, job splitting,
quality analysis, per-stage queue polling); the actual alignment is a few
hundred milliseconds. phonealign keeps the model loaded and calls Kaldi
directly through `kalpy`, the bindings MFA itself uses.

## Intended API

```python
from phonealign import Aligner

aligner = Aligner(acoustic_model='english_us_arpa.zip', dictionary='english.dict')
result = aligner.align(samples, sample_rate=16000, transcript='When the sunlight ...')
result.words   # [(start, end, 'when'), ...]
result.phones  # [(start, end, 'HH'), (start, end, 'W'), ...]
```

The `Aligner` is created once (loading the model) and reused for every
request. Output should match `mfa align` with the same models, which is the
reference for testing.

## Status

Not implemented yet. First steps:

1. List the `kalpy` calls `mfa align` makes for one utterance (features,
   CMVN, training graph compilation, GMM alignment, word/phone extraction).
2. Reproduce one clip's TextGrid exactly with those calls.
3. Time each call.

## License

Not decided yet. The repository is AGPL-3.0, which covers this directory
while it lives here. A different license for the standalone package (e.g.
MIT, matching MFA and kalpy) would need the copyright holders' agreement.

## Dependencies

`kalpy` (Kaldi bindings), currently installed through conda alongside MFA
in the Docker image. Pin it in `pyproject.toml` once the exact
requirements are known.
