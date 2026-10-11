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

## Usage

```python
from phonealign import Aligner, AlignmentError

# Once: loads the acoustic model and reads the dictionary (~4 s with imports).
aligner = Aligner(acoustic_model='english_us_arpa.zip', dictionary='english.dict')

# Per recording: mono float samples in -1..1, at any sample rate (resampled
# to 16 kHz). ~300 ms for a 26 s clip.
try:
	alignment = aligner.align(samples, sample_rate=16000, transcript='When the sunlight ...')
except AlignmentError:
	...  # transcript doesn't match the audio, recording too short, etc.

alignment.words   # [Interval(start=1.33, end=1.53, label='when'), ...]
alignment.phones  # [Interval(start=1.33, end=1.37, label='HH'), ...]
alignment.write_textgrid('out.TextGrid')  # same format as `mfa align`
```

Times are in seconds, at the aligner's 10 ms resolution. Silence isn't
listed: it's the time not covered by any interval.

Results match `mfa align` within MFA's own run-to-run variation (MFA's
feature extraction is random; see `docs/CURRENT.md`), and are identical for
identical input.

## Status

Working, not yet used by the backend. `tools/` has the experiments and
checks behind it:

- `check_aligner.py`: runs `Aligner` on a clip and times it.
- `compare_textgrids.py`: compares two TextGrids' intervals.
- `kalpy_align.py`, `persistent_align.py`: the timing and accuracy
  experiments that shaped the design.

They need the Docker image (for kalpy and the models).

## License

Not decided yet. The repository is AGPL-3.0, which covers this directory
while it lives here. A different license for the standalone package (e.g.
MIT, matching MFA and kalpy) would need the copyright holders' agreement.

## Dependencies

`kalpy` (Kaldi bindings) and, for now, `montreal_forced_aligner` (for
loading acoustic models and its tokenizer), both installed through conda
in the Docker image. Pin them in `pyproject.toml` once the exact
requirements are known. Dropping the MFA dependency would cut ~2 s of
imports from startup.
