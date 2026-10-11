#!/usr/bin/env bash
# Download the acoustic model and pronunciation dictionary the in-browser
# analysis uses into models/ (git-ignored), from the Montreal Forced
# Aligner's model releases: English (US) ARPA acoustic model and dictionary
# v3.0.0, both CC BY 4.0 (credited on the app's help page). These are the
# same files as in the gvv-dev Docker image. Skips the download if they're
# already there; delete models/ to fetch them again.
set -euo pipefail
cd "$(dirname "$0")/.."

files=(final.alimdl tree lda.mat phones.txt english.dict)
if (cd models 2>/dev/null && ls "${files[@]}" >/dev/null 2>&1); then
    echo "models/ is complete; not downloading"
    exit 0
fi

releases=https://github.com/MontrealCorpusTools/mfa-models/releases/download
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

curl -fsSL -o "$tmp/model.zip" "$releases/acoustic-english_us_arpa-v3.0.0/english_us_arpa.zip"
mkdir -p models
curl -fsSL -o models/english.dict "$releases/dictionary-english_us_arpa-v3.0.0/english_us_arpa.dict"
python3 - "$tmp/model.zip" models <<'EOF'
import sys, zipfile
archive, out = sys.argv[1:]
with zipfile.ZipFile(archive) as z:
    for name in z.namelist():
        if name.rsplit('/', 1)[-1] in ('final.alimdl', 'tree', 'lda.mat', 'phones.txt'):
            with open(f"{out}/{name.rsplit('/', 1)[-1]}", 'wb') as f:
                f.write(z.read(name))
EOF
ls -la models
