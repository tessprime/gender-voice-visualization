"""Compare voicemeasure with Praat on the web app's example clips
(resources/*.json), at the clips' phone midpoints, as the app measures.

Run from the repository root, with the app's Docker image built (it has
Praat and ffmpeg) and voicemeasure's examples built:

    cargo build --release --manifest-path voicemeasure/Cargo.toml --examples
    python3 voicemeasure/reference/check_examples.py OUT_DIR

For each clip: decode its audio to a 16 kHz mono WAV, analyse that same file
with Praat (dump_tracks.praat) and with voicemeasure (measure_at), and
compare F0-F3 at each phone's midpoint. Then run the app's resonance.py on
both sets of measurements and compare what the app shows: per-vowel
resonance, and each clip's median pitch and resonance.
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
from acousticgender.library import resonance
from acousticgender.library.phones import phone_class

WEIGHTS = [0.7321428571428571, 0.26785714285714285, 0.0]

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


def read(path):
	return list(csv.DictReader(open(path), delimiter='\t'))


def number(text):
	return None if text.startswith('--') else float(text)


def praat_value_at(rows, times, t, column):
	"""Praat's Get value at time ... Hertz Linear: linear between the two
	frames around t, or the nearer frame's value if one is undefined."""
	i = bisect.bisect_right(times, t) - 1
	if i < 0 or i + 1 >= len(times):
		return None
	a, b = number(rows[i][column]), number(rows[i + 1][column])
	w = (t - times[i]) / (times[i + 1] - times[i])
	if a is not None and b is not None:
		return a + w * (b - a)
	return a if w < 0.5 else b


def measurements(clip, name):
	"""{'praat': [...], 'ours': [...]}: [F0, F1, F2, F3] per phone (except
	the last, which has no end time)."""
	phones = clip['phones']
	middles = [(a['time'] + b['time']) / 2 for a, b in zip(phones, phones[1:])]
	formant, pitch = read(f'{out}/{name}-praat-formant.tsv'), read(f'{out}/{name}-praat-pitch.tsv')
	formant_times = [float(r['time(s)']) for r in formant]
	pitch_times = [float(r['time(s)']) for r in pitch]
	praat = [[praat_value_at(pitch, pitch_times, t, 'F0(Hz)')]
	         + [praat_value_at(formant, formant_times, t, f'F{k}(Hz)') for k in (1, 2, 3)]
	         for t in middles]
	with open(f'{out}/{name}-times.txt', 'w') as f:
		f.write('\n'.join(repr(t) for t in middles))
	result = subprocess.run(['voicemeasure/target/release/examples/measure_at',
	                         f'{out}/{name}.wav', f'{out}/{name}-times.txt'],
	                        check=True, capture_output=True, text=True).stdout
	ours = [[number(v) for v in line.split('\t')[1:]] for line in result.strip().split('\n')]
	return {'praat': praat, 'ours': ours}


def app_view(clip, values):
	"""Run the app's resonance.py on one set of measurements."""
	data = {'phones': [{'phoneme': p['phoneme'], 'expected': p.get('expected'), 'F': list(v)}
	                   for p, v in zip(clip['phones'], values)]}
	resonance.compute_resonance(data, WEIGHTS)
	return data


raw = {k: [] for k in range(4)}
voicing = [0, 0]  # vowel midpoints where F0 voicing agrees, total
clip_pitch, clip_resonance, vowel_resonance = [], [], []
print('%-10s %-22s %-24s %s' % ('clip', 'median pitch P / V', 'median resonance P / V', 'vowel F0 |diff| median'))
for name, clip in clips.items():
	m = measurements(clip, name)
	vowel_f0 = []
	for phone, p, o in zip(clip['phones'], m['praat'], m['ours']):
		if phone_class(phone['phoneme']) != 'vowel':
			continue
		voicing[0] += (p[0] is None) == (o[0] is None)
		voicing[1] += 1
		for k in range(4):
			if p[k] is not None and o[k] is not None:
				raw[k].append(abs(p[k] - o[k]))
		if p[0] is not None and o[0] is not None:
			vowel_f0.append(abs(p[0] - o[0]))
	praat, ours = app_view(clip, m['praat']), app_view(clip, m['ours'])
	clip_pitch.append(abs(praat['medianPitch'] - ours['medianPitch']))
	clip_resonance.append(abs(praat['medianResonance'] - ours['medianResonance']) * 100)
	vowel_resonance += [abs(a['resonance'] - b['resonance']) * 100
	                    for a, b in zip(praat['phones'], ours['phones'])
	                    if phone_class(a['phoneme']) == 'vowel'
	                    and a.get('resonance') is not None and b.get('resonance') is not None]
	print('%-10s %6.1f / %6.1f Hz      %5.1f%% / %5.1f%%          %.3f Hz' % (
		name, praat['medianPitch'], ours['medianPitch'],
		praat['medianResonance'] * 100, ours['medianResonance'] * 100,
		statistics.median(vowel_f0) if vowel_f0 else float('nan')))

print()
print(f'vowel midpoints: voicing agrees at {voicing[0]}/{voicing[1]} ({100 * voicing[0] / voicing[1]:.1f}%)')
for k, label in enumerate(['F0', 'F1', 'F2', 'F3']):
	d = raw[k]
	print(f'  {label}: {len(d)} vowels, |difference| median {statistics.median(d):.3f} Hz, '
	      f'within 1 Hz {100 * sum(x < 1 for x in d) / len(d):.1f}%, within 10 Hz {100 * sum(x < 10 for x in d) / len(d):.1f}%, '
	      f'max {max(d):.1f} Hz')
print(f'clip median pitch: |difference| median {statistics.median(clip_pitch):.3f} Hz, max {max(clip_pitch):.3f} Hz')
print(f'clip median resonance: |difference| median {statistics.median(clip_resonance):.2f}, max {max(clip_resonance):.2f} percentage points')
print(f'per-vowel resonance: {len(vowel_resonance)} vowels, |difference| median {statistics.median(vowel_resonance):.3f} pts, '
      f'>1 pt: {sum(x > 1 for x in vowel_resonance)}, >5 pts: {sum(x > 5 for x in vowel_resonance)}, max {max(vowel_resonance):.1f} pts')
