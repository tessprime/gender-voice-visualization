# voicealign

Forced alignment of a recording to its transcript with Kaldi GMM-HMM
acoustic models (as trained by the Montreal Forced Aligner), in Rust, so it
can run in the browser (WebAssembly). A port of what
[phonealign](../phonealign/README.md) does through kalpy/Kaldi; Kaldi is
Apache-2.0, and the relevant parts are ported from its source.

Meant to become its own crate; keep it independent of the web app.

## Status

Work in progress; see `docs/CURRENT.md` in the web app's repository.

- **Features** (`features.rs`): MFCC, CMVN, splice ±3, LDA, as kalpy
  computes them for `english_us_arpa`. Within float32 rounding of kalpy's.
- Model loading, graph compilation, alignment: not yet.

## Comparing with kalpy

```sh
# In the web app's Docker image (it has kalpy and the models):
python3 reference/dump_kalpy.py recording.wav out/
# Here (lda.mat from the extracted acoustic model):
cargo run --release --example compare_features -- recording.wav lda.mat out/
```

## License

Not decided yet. Code ported from Kaldi must keep Kaldi's Apache-2.0 notice.
