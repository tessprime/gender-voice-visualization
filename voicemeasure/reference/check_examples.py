"""Compare voicemeasure with Praat on the web app's example clips
(resources/*.json), at the clips' phone midpoints, as the app measures.

Run from the repository root, with the app's Docker image built (it has
Praat and ffmpeg) and voicemeasure's example built:

    cargo build --release --manifest-path voicemeasure/Cargo.toml --example dump_tracks
    python3 voicemeasure/reference/check_examples.py OUT_DIR

For each clip: decode its audio to a 16 kHz mono WAV, analyse that same file
with Praat and with voicemeasure, and compare F1-F3 at each phone's
midpoint. Also reports the difference from the values stored in the clip,
which came from the 2021 pipeline (older Praat, noise-reduced audio), as
context for how much that pipeline drifts anyway.
"""
import base64
import bisect
import csv
import glob
import json
import os
import statistics
import subprocess
import sys

sys.path.insert(0, '.')
from acousticgender.library.phones import phone_class

out = os.path.abspath(sys.argv[1])
os.makedirs(out, exist_ok=True)
clips = {}
for path in sorted(glob.glob('resources/*.json')):
	data = json.load(open(path))
	if isinstance(data, dict) and data.get('audio') and data.get('phones'):
		name = os.path.basename(path)[:-5]
		clips[name] = data
		with open(f'{out}/{name}.audio', 'wb') as f:
			f.write(base64.b64decode(data['audio'].split(',', 1)[1]))

# Decode to WAV and run Praat, in the app's image. Praat 6.4.06 sometimes
# fails to create its output file here ("this is a folder, not a file") and
# succeeds when rerun, so retry a few times.
script = ' && '.join(
	f'ffmpeg -nostdin -loglevel error -y -i /out/{n}.audio -ac 1 -ar 16000 -acodec pcm_s16le /out/{n}.wav'
	f' && for attempt in 1 2 3; do'
	f'   praat --run /app/voicemeasure/reference/dump_tracks.praat /out/{n}.wav /out/{n}-praat >/dev/null 2>&1 && break;'
	f'   echo "Praat failed on {n} (attempt $attempt)" >&2; [ $attempt = 3 ] && exit 1;'
	f' done'
	for n in clips)
subprocess.run(['docker', 'run', '--rm', '-v', f'{os.getcwd()}:/app', '-v', f'{out}:/out',
                'gvv-dev', 'bash', '-c', script], check=True)
for n in clips:
	subprocess.run(['voicemeasure/target/release/examples/dump_tracks',
	                f'{out}/{n}.wav', f'{out}/{n}-ours'], check=True)


def read(path):
	return list(csv.DictReader(open(path), delimiter='\t'))


def value_at(frames, times, t, k):
	"""Like Praat's Get value at time ... Hertz Linear."""
	i = bisect.bisect_right(times, t) - 1
	if i < 0 or i + 1 >= len(times):
		return None
	a, b = frames[i][f'F{k}(Hz)'], frames[i + 1][f'F{k}(Hz)']
	if '--' in a or '--' in b:
		return None
	w = (t - times[i]) / (times[i + 1] - times[i])
	return float(a) * (1 - w) + float(b) * w


totals = {k: [] for k in (1, 2, 3)}
stored_totals = {k: [] for k in (1, 2, 3)}
print('%-10s %6s  %-26s %-26s %-26s  %s' % ('clip', 'vowels', 'F1 median/max (Hz)', 'F2 median/max', 'F3 median/max', 'F1-F3 vs stored 2021 values (median)'))
for n, data in clips.items():
	praat, ours = read(f'{out}/{n}-praat-formant.tsv'), read(f'{out}/{n}-ours-formant.tsv')
	assert len(praat) == len(ours), n
	praat_times = [float(r['time(s)']) for r in praat]
	ours_times = [float(r['time(s)']) for r in ours]
	phones = data['phones']
	row, stored_row, vowels = [], [], 0
	for k in (1, 2, 3):
		differences, stored_differences = [], []
		for this, following in zip(phones, phones[1:]):
			if phone_class(this['phoneme']) != 'vowel' or this['time'] is None or following['time'] is None:
				continue
			middle = (this['time'] + following['time']) / 2
			p, o = value_at(praat, praat_times, middle, k), value_at(ours, ours_times, middle, k)
			if p is not None and o is not None:
				differences.append(abs(p - o))
			stored = this['F'][k] if this.get('F') and len(this['F']) > k else None
			if stored is not None and o is not None:
				stored_differences.append(abs(stored - o))
		vowels = max(vowels, len(differences))
		totals[k] += differences
		stored_totals[k] += stored_differences
		row.append('%6.2f / %7.1f' % (statistics.median(differences), max(differences)) if differences else '-')
		stored_row.append('%5.0f' % statistics.median(stored_differences) if stored_differences else '-')
	print('%-10s %6d  %-26s %-26s %-26s  %s' % (n, vowels, *row, ' '.join(stored_row)))

print()
for k in (1, 2, 3):
	d = totals[k]
	print(f'all clips F{k}: {len(d)} vowels, median {statistics.median(d):.2f} Hz, '
	      f'within 1 Hz {100 * sum(x < 1 for x in d) / len(d):.1f}%, within 10 Hz {100 * sum(x < 10 for x in d) / len(d):.1f}%, '
	      f'max {max(d):.1f} Hz | vs stored 2021 values: median {statistics.median(stored_totals[k]):.0f} Hz')
