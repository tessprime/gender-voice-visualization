// Compare ui/scoring.js with the Python backend on reference cases from
// make_reference.py.
//
//   node tests/scoring/check_scoring.mjs CASES_DIR
//
// For each case: parse praat.tsv into words and phones, score with
// scoring.js, and compare every value with expected.json (numbers to a
// relative tolerance of 1e-9).
import { createRequire } from 'node:module';
import { readFileSync, readdirSync } from 'node:fs';

const require = createRequire(import.meta.url);
const { parsePronunciationDictionary, scoreMeasurements } = require('../../ui/scoring.js');

const casesDir = process.argv[2];
const dictionary = parsePronunciationDictionary(readFileSync(new URL('../../cmudict.txt', import.meta.url), 'latin1'));
const stats = JSON.parse(readFileSync(new URL('../../stats.json', import.meta.url), 'utf8'));

// The Praat script's output, as phones.parse reads it.
function readPraat(text) {
	const words = [], phones = [];
	let section = null;
	for (const line of text.split('\n')) {
		if (line === 'Words:') { section = 'words'; continue; }
		if (line === 'Phonemes:') { section = 'phones'; continue; }
		const cols = line.split('\t');
		if (section === 'words') {
			words.push({ time: Number(cols[0]), word: cols[1] });
		} else if (section === 'phones' && cols.length >= 3) {
			phones.push({ time: Number(cols[0]), phoneme: cols[1], F: cols.slice(2).map(f => f.includes('--') ? null : Number(f)) });
		}
	}
	return { words, phones };
}

// Differences between two JSON values, as "path: a vs b".
function compare(a, b, path, out) {
	if (typeof a === 'number' && typeof b === 'number') {
		if (Math.abs(a - b) > 1e-9 * Math.max(1, Math.abs(a), Math.abs(b))) out.push(`${path}: ${a} vs ${b}`);
	} else if (Array.isArray(a) && Array.isArray(b)) {
		if (a.length !== b.length) out.push(`${path}: length ${a.length} vs ${b.length}`);
		a.forEach((x, i) => i < b.length && compare(x, b[i], `${path}[${i}]`, out));
	} else if (a && b && typeof a === 'object' && typeof b === 'object') {
		for (const k of new Set([...Object.keys(a), ...Object.keys(b)])) {
			if (!(k in a) || !(k in b)) out.push(`${path}.${k}: ${k in a ? 'only in JS' : 'only in Python'}`);
			else compare(a[k], b[k], `${path}.${k}`, out);
		}
	} else if (a !== b) {
		out.push(`${path}: ${JSON.stringify(a)} vs ${JSON.stringify(b)}`);
	}
}

let identical = 0, total = 0;
for (const name of readdirSync(casesDir).sort()) {
	let praat, expected;
	try {
		praat = readFileSync(`${casesDir}/${name}/praat.tsv`, 'utf8');
		expected = JSON.parse(readFileSync(`${casesDir}/${name}/expected.json`, 'utf8'));
	} catch { continue; }
	const { words, phones } = readPraat(praat);
	// Round-trip through JSON, as the backend's output does (undefined -> absent).
	const ours = JSON.parse(JSON.stringify(scoreMeasurements(words, phones, dictionary, stats)));
	const differences = [];
	compare(ours, expected, name, differences);
	total += 1;
	if (differences.length === 0) identical += 1;
	console.log(`${name.padEnd(10)} ${differences.length === 0 ? 'identical' : `${differences.length} differences, e.g. ${differences.slice(0, 2).join('; ')}`}`);
}
console.log(`\n${identical}/${total} cases identical to the Python backend`);
