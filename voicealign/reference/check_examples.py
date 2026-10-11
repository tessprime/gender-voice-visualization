"""Compare voicealign with kalpy on the web app's example clips.

Run from the repository root, with the app's Docker image built and
voicealign's examples built:

    cargo build --release --manifest-path voicealign/Cargo.toml --examples
    python3 voicealign/reference/check_examples.py MODEL_DIR OUT_DIR

MODEL_DIR is the extracted acoustic model (final.alimdl, tree, lda.mat,
phones.txt). For each clip in resources/*.json: decode its audio to a
16 kHz WAV, align it with kalpy (reference/dump_alignment.py, dither off)
and with voicealign (examples/compare_alignment.rs), and report how they
compare.
"""
import base64
import glob
import json
import os
import re
import subprocess
import sys

model_dir, out = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
os.makedirs(out, exist_ok=True)
clips = []
for path in sorted(glob.glob('resources/*.json')):
	data = json.load(open(path))
	if isinstance(data, dict) and data.get('audio') and data.get('transcript'):
		name = os.path.basename(path)[:-5]
		os.makedirs(f'{out}/{name}', exist_ok=True)
		with open(f'{out}/{name}/audio', 'wb') as f:
			f.write(base64.b64decode(data['audio'].split(',', 1)[1]))
		with open(f'{out}/{name}/transcript.txt', 'w') as f:
			f.write(data['transcript'])
		clips.append(name)

script = ' && '.join(
	f'ffmpeg -nostdin -loglevel error -y -i /out/{n}/audio -ac 1 -ar 16000 -acodec pcm_s16le /out/{n}/recording.wav'
	f' && python3 /app/voicealign/reference/dump_alignment.py /out/{n}/recording.wav /out/{n}/transcript.txt /out/{n} > /out/{n}/kalpy.log 2>&1'
	for n in clips)
subprocess.run(['docker', 'run', '--rm', '-v', f'{os.getcwd()}:/app:ro', '-v', f'{out}:/out', 'gvv-dev', 'bash', '-c', script], check=True)

totals = {'frames': 0, 'same_ids': 0, 'phones': 0, 'same_phones': 0, 'words': 0, 'same_words': 0}
print('%-10s %8s %18s %16s %14s %10s' % ('clip', 'frames', 'transition ids', 'phones', 'words', 'align ms'))
for n in clips:
	result = subprocess.run(['voicealign/target/release/examples/compare_alignment', f'{out}/{n}/recording.wav', model_dir, f'{out}/{n}'],
	                        capture_output=True, text=True)
	text = result.stdout + result.stderr
	ids = re.search(r'transition ids: (\d+)/(\d+)', text)
	phones = re.search(r'phones: ours (\d+), kalpy (\d+); identical \(label and times\) (\d+)', text)
	words = re.search(r'words: ours (\d+), kalpy (\d+); identical (\d+)', text)
	ms = re.search(r'alignment (\d+) ms', text)
	if not (ids and phones and words):
		print(f'{n:10} failed: {text.strip().splitlines()[-1] if text.strip() else "no output"}')
		continue
	same, frames = int(ids[1]), int(ids[2])
	totals['frames'] += frames; totals['same_ids'] += same
	totals['phones'] += int(phones[2]); totals['same_phones'] += int(phones[3])
	totals['words'] += int(words[2]); totals['same_words'] += int(words[3])
	print('%-10s %8d %18s %16s %14s %10s' % (n, frames, f'{same}/{frames}', f'{phones[3]}/{phones[2]}', f'{words[3]}/{words[2]}', ms[1] if ms else '?'))
t = totals
print(f'\nall clips: transition ids {t["same_ids"]}/{t["frames"]} identical; phones {t["same_phones"]}/{t["phones"]}; words {t["same_words"]}/{t["words"]}')
