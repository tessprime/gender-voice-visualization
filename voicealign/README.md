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
- **Model loading** (`model.rs`, `tree.rs`): the transition model, the
  diagonal GMMs and the decision tree, read from Kaldi's binary files.
  Identical to kalpy's view of them; GMM log-likelihoods within float32
  rounding.
- **Graph compilation** (`lexicon.rs`, `graph.rs`): the alignment graph
  for a transcript, built directly. kalpy's alignment of the test clip is a
  path through it with the same score (to 5e-7).
- **Alignment** (`align.rs`): Viterbi with beam pruning, as Kaldi's
  gmm-align-compiled. On the test recording, the output (every frame's
  transition id, phone and word times) is identical to kalpy's.

`examples/compare_alignment.rs` runs the whole pipeline from a WAV file and
compares with `reference/dump_alignment.py`'s output. On the web app's 21
example clips, 99.88% of frames are identical to kalpy's
(`reference/check_examples.py`); the rest differ through beam pruning.

## Usage

```rust
let aligner = voicealign::Aligner::new(&final_alimdl, &tree, &lda_mat, &phones_txt, &dictionary)?;
let alignment = aligner.align(&samples, 16000, "When the sunlight strikes...")?; // f32 samples, -1..1
for word in &alignment.words {
    println!("{:.2}-{:.2} {}", word.start, word.end, word.label);
}
```

`cargo run --release --example align_api -- MODEL_DIR dictionary.dict recording.wav transcript.txt`

## WebAssembly

```sh
cargo build --release --target wasm32-unknown-unknown   # ~480 KB, ~190 KB gzipped
node reference/check_wasm.mjs target/wasm32-unknown-unknown/release/voicealign.wasm MODEL_DIR dictionary.dict recording.wav transcript.txt
```

`src/wasm.rs` documents the interface (`va_new`, `va_align` returning JSON).
Loading the model and full dictionary takes ~2.4 s; aligning a 26 s
recording ~300 ms.

## Comparing with kalpy

```sh
# In the web app's Docker image (it has kalpy and the models):
python3 reference/dump_kalpy.py recording.wav out/
# Here (lda.mat from the extracted acoustic model):
cargo run --release --example compare_features -- recording.wav lda.mat out/

# Model and tree (MODEL_DIR: the extracted acoustic model):
python3 reference/dump_model.py MODEL_DIR out/features.f32 out/   # in the image
cargo run --release --example compare_model -- MODEL_DIR out/
```

## License

Not decided yet. Code ported from Kaldi must keep Kaldi's Apache-2.0 notice.
