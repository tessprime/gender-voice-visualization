"""Compare two TextGrids' word and phone intervals, ignoring formatting.

Silence may be written as "" or "<eps>", and numbers as 0 or 0.0, depending
on the tool; both are treated as equal.

    python compare_textgrids.py reference.TextGrid other.TextGrid
"""
import re
import sys

SILENCE = {'', '<eps>', 'sil', 'sp'}


def read_intervals(path):
	"""{tier name: [(start, end, label), ...]} for a long-format TextGrid."""
	tiers = {}
	current = None
	start = end = None
	for line in open(path, encoding='utf-8'):
		line = line.strip()
		if m := re.match(r'name = "(.*)"', line):
			current = tiers.setdefault(m.group(1), [])
		elif m := re.match(r'xmin = (\S+)', line):
			start = float(m.group(1))
		elif m := re.match(r'xmax = (\S+)', line):
			end = float(m.group(1))
		elif (m := re.match(r'text = "(.*)"', line)) and current is not None:
			label = m.group(1)
			current.append((round(start, 3), round(end, 3), '' if label in SILENCE else label))
	return tiers


def compare(reference_path, other_path):
	"""Print the differences and return how many intervals differ."""
	reference, other = read_intervals(reference_path), read_intervals(other_path)
	differences = 0
	for tier in sorted(set(reference) | set(other)):
		a, b = reference.get(tier, []), other.get(tier, [])
		mismatched = [(x, y) for x, y in zip(a, b) if x != y]
		differences += len(mismatched) + abs(len(a) - len(b))
		print(f'{tier}: {len(a)} vs {len(b)} intervals, {len(mismatched)} differ')
		for x, y in mismatched[:5]:
			print(f'    {x}  vs  {y}')
	return differences


if __name__ == '__main__':
	sys.exit(1 if compare(sys.argv[1], sys.argv[2]) else 0)
