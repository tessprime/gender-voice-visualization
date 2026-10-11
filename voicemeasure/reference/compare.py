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


if __name__ == '__main__':
	compare_formants(sys.argv[1] + '-formant.tsv', sys.argv[2] + '-formant.tsv')
