"""Compare voicemeasure's frame-by-frame output with Praat's.

    python compare.py praat-prefix voicemeasure-prefix

Reads <prefix>-formant.tsv from each (see dump_tracks.praat and
examples/dump_tracks.rs) and reports how closely they agree.
"""
import csv
import statistics
import sys


def read(path):
	with open(path) as f:
		return list(csv.DictReader(f, delimiter='\t'))


def value(row, column):
	v = row[column]
	return None if v == '--undefined--' else float(v)


def percentile(values, p):
	values = sorted(values)
	return values[min(len(values) - 1, int(p / 100 * len(values)))]


def compare_formants(praat_path, ours_path):
	praat, ours = read(praat_path), read(ours_path)
	print(f'formant frames: Praat {len(praat)}, voicemeasure {len(ours)}')
	if len(praat) != len(ours):
		return
	time_error = max(abs(float(a['time(s)']) - float(b['time(s)'])) for a, b in zip(praat, ours))
	same_count = sum(a['nformants'] == b['nformants'] for a, b in zip(praat, ours))
	print(f'  frame times differ by at most {time_error * 1e6:.1f} us')
	print(f'  same number of formants in {same_count}/{len(praat)} frames ({100 * same_count / len(praat):.1f}%)')
	for k in (1, 2, 3):
		column = f'F{k}(Hz)'
		differences = [abs(value(a, column) - value(b, column)) for a, b in zip(praat, ours)
		               if value(a, column) is not None and value(b, column) is not None]
		print(f'  F{k}: |difference| median {statistics.median(differences):.2f} Hz, '
		      f'95th percentile {percentile(differences, 95):.2f} Hz, '
		      f'max {max(differences):.1f} Hz over {len(differences)} frames; '
		      f'within 1 Hz in {100 * sum(d < 1 for d in differences) / len(differences):.1f}%')


def compare_pitch(praat_path, ours_path):
	praat, ours = read(praat_path), read(ours_path)
	print(f'pitch frames: Praat {len(praat)}, voicemeasure {len(ours)}')
	if len(praat) != len(ours):
		return
	pairs = [(value(a, 'F0(Hz)'), value(b, 'F0(Hz)')) for a, b in zip(praat, ours)]
	both = [(p, o) for p, o in pairs if p is not None and o is not None]
	only_praat = sum(p is not None and o is None for p, o in pairs)
	only_ours = sum(p is None and o is not None for p, o in pairs)
	print(f'  voicing agrees in {len(pairs) - only_praat - only_ours}/{len(pairs)} frames '
	      f'({100 * (len(pairs) - only_praat - only_ours) / len(pairs):.1f}%); '
	      f'voiced only in Praat: {only_praat}, only in voicemeasure: {only_ours}')
	if both:
		differences = [abs(p - o) for p, o in both]
		octave = sum(abs(p / o - 2) < 0.1 or abs(o / p - 2) < 0.1 for p, o in both)
		print(f'  F0 where both voiced ({len(both)} frames): |difference| median {statistics.median(differences):.3f} Hz, '
		      f'95th percentile {percentile(differences, 95):.2f} Hz, max {max(differences):.1f} Hz; '
		      f'within 1 Hz {100 * sum(d < 1 for d in differences) / len(differences):.1f}%; octave errors {octave}')


if __name__ == '__main__':
	compare_formants(sys.argv[1] + '-formant.tsv', sys.argv[2] + '-formant.tsv')
	compare_pitch(sys.argv[1] + '-pitch.tsv', sys.argv[2] + '-pitch.tsv')
