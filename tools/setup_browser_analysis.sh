#!/usr/bin/env bash
# Set up the files the browser needs to analyse recordings itself:
#   ui/wasm/voicealign.wasm, ui/wasm/voicemeasure.wasm  (built from the crates)
#   models/final.alimdl, tree, lda.mat, phones.txt       (the acoustic model)
#   models/english.dict                                   (pronunciations)
# Both directories are generated, so git ignores them. The model files come
# from the app's Docker image (gvv-dev), which has them installed.
set -euo pipefail
cd "$(dirname "$0")/.."

for crate in voicealign voicemeasure; do
    cargo build --release --quiet --target wasm32-unknown-unknown --manifest-path "$crate/Cargo.toml"
done
mkdir -p ui/wasm models
cp voicealign/target/wasm32-unknown-unknown/release/voicealign.wasm ui/wasm/
cp voicemeasure/target/wasm32-unknown-unknown/release/voicemeasure.wasm ui/wasm/

docker run --rm -v "$PWD/models":/out gvv-dev bash -c '
    set -e
    cd /tmp
    python3 -c "import zipfile; zipfile.ZipFile(\"/opt/mfa/pretrained_models/acoustic/english.zip\").extractall(\"model\")"
    cp model/*/final.alimdl model/*/tree model/*/lda.mat model/*/phones.txt /out/
    cp /opt/mfa/pretrained_models/dictionary/english.dict /out/'

ls -la ui/wasm models
