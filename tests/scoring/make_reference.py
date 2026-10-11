"""Reference cases for ui/scoring.js: run recordings through the server's
pipeline and save Praat's measurements (the port's input) and the JSON the
backend returns (the expected output).

    python3 tests/scoring/make_reference.py OUT_DIR CLIP_DIR...

Run inside the web app's Docker image from the repository root (/app).
Each CLIP_DIR holds recording.wav and transcript.txt; writes
OUT_DIR/<name>/praat.tsv and OUT_DIR/<name>/expected.json.
"""
import json
import os
import random
import sys

sys.path.insert(0, '.')
from acousticgender.library import phones, preprocessing, resonance
from acousticgender.library.analysis import WEIGHTS, load_aligner

out, clips = sys.argv[1], sys.argv[2:]
aligner = load_aligner()
for clip in clips:
	name = os.path.basename(clip.rstrip('/'))
	os.makedirs(f'{out}/{name}', exist_ok=True)
	audio = open(f'{clip}/recording.wav', 'rb').read()
	transcript = open(f'{clip}/transcript.txt').read()
	tmp = f'/tmp/scoring-{random.randint(0, 2**32)}'
	praat_output = preprocessing.process(audio, transcript, tmp, aligner)
	if praat_output is None:
		print(f'{name}: alignment failed, skipped')
		continue
	with open(f'{out}/{name}/praat.tsv', 'w') as f:
		f.write(praat_output)
	data = phones.parse(praat_output)
	resonance.compute_resonance(data, WEIGHTS)
	with open(f'{out}/{name}/expected.json', 'w') as f:
		json.dump(data, f)
	print(f'{name}: {len(data["phones"])} phones')
