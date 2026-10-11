"""Run phonealign.Aligner on a clip: time several requests, write a TextGrid,
and check that a transcript that doesn't match the audio raises
AlignmentError.

    python check_aligner.py CLIP_DIR OUT.TextGrid [RUNS]

Run inside the Docker image, as `nobody`.
"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

t0 = time.perf_counter()
import soundfile
from phonealign import Aligner, AlignmentError

clip_dir, out_path = Path(sys.argv[1]), Path(sys.argv[2])
runs = int(sys.argv[3]) if len(sys.argv) > 3 else 5
models = Path(os.environ.get('MFA_ROOT_DIR', os.path.expanduser('~/Documents/MFA'))) / 'pretrained_models'

aligner = Aligner(models / 'acoustic' / 'english.zip', models / 'dictionary' / 'english.dict')
print(f'startup (imports + model + dictionary): {(time.perf_counter() - t0) * 1000:.0f} ms')

samples, rate = soundfile.read(clip_dir / 'corpus' / 'recording.wav', dtype='float32')
transcript = (clip_dir / 'corpus' / 'recording.txt').read_text()

results = []
for run in range(runs):
	start = time.perf_counter()
	alignment = aligner.align(samples, rate, transcript)
	results.append(alignment)
	print(f'request {run}: {(time.perf_counter() - start) * 1000:.0f} ms, '
		f'{len(alignment.words)} words, {len(alignment.phones)} phones')

print('identical across requests:', all(
	(r.words, r.phones) == (results[0].words, results[0].phones) for r in results))
print('first words:', [(w.start, w.end, w.label) for w in results[0].words[:3]])
print('first phones:', [(p.start, p.end, p.label) for p in results[0].phones[:4]])
results[0].write_textgrid(out_path)

try:
	aligner.align(samples[:rate], rate, transcript)  # 1 s of audio, whole passage
	print('mismatched transcript: aligned anyway (unexpected)')
except AlignmentError as e:
	print('mismatched transcript: AlignmentError raised as expected')
