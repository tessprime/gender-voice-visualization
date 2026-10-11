#!/usr/bin/env bash
# Set up the files the browser needs to analyse recordings itself:
#   ui/wasm/voicealign.wasm, ui/wasm/voicemeasure.wasm  (built from the crates)
#   models/final.alimdl, tree, lda.mat, phones.txt       (the acoustic model)
#   models/english.dict                                   (pronunciations)
# Both directories are generated, so git ignores them. Needs Rust with the
# wasm32-unknown-unknown target; the models are downloaded (fetch_models.sh).
set -euo pipefail
cd "$(dirname "$0")/.."

for crate in voicealign voicemeasure; do
    cargo build --release --quiet --target wasm32-unknown-unknown --manifest-path "$crate/Cargo.toml"
done
mkdir -p ui/wasm
cp voicealign/target/wasm32-unknown-unknown/release/voicealign.wasm ui/wasm/
cp voicemeasure/target/wasm32-unknown-unknown/release/voicemeasure.wasm ui/wasm/
ls -la ui/wasm

tools/fetch_models.sh
