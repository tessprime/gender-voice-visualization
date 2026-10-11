// Scoring a measured recording: a port of acousticgender/library/phones.py
// (parse) and resonance.py (compute_resonance), producing the same data the
// backend returns, so the analysis can run in the browser.
//
// Input: the aligned words and phones (silence as label ''), with each
// phone's F0-F3 at its midpoint (null where undefined), in time order:
//   words:  [{time, word}]
//   phones: [{time, phoneme, F: [f0, f1, f2, f3]}]
// plus the pronunciation dictionary (cmudict.txt's text) and stats.json.
//
// Mirrors the Python closely, including its truthiness tests (0 counts as
// missing) and its use of the sample standard deviation.

const SCORING_WEIGHTS = [0.7321428571428571, 0.26785714285714285, 0.0];

// Phone classes, as phones.py's phone_class().
const SCORING_PHONE_CLASSES = {
	vowel: ['AA', 'AE', 'AH', 'AO', 'AW', 'AY', 'EH', 'ER', 'EY', 'IH', 'IY', 'OW', 'OY', 'UH', 'UW'],
	sonorant: ['M', 'N', 'NG', 'L', 'R', 'W', 'Y'],
	obstruent: ['P', 'B', 'T', 'D', 'K', 'G', 'F', 'V', 'TH', 'DH', 'S', 'Z', 'SH', 'ZH', 'HH', 'CH', 'JH'],
};

function scoringPhoneClass(phoneme) {
	const base = (phoneme || '').replace(/\d/g, '');
	for (const [name, list] of Object.entries(SCORING_PHONE_CLASSES)) {
		if (list.includes(base)) return name;
	}
	return null;
}

// cmudict.txt's text -> {WORD: [phones]}; later lines win, as in Python.
function parsePronunciationDictionary(text) {
	const dictionary = {};
	for (const line of text.split('\n')) {
		const cols = line.split(/\s+/).filter(c => c);
		if (cols.length) dictionary[cols[0]] = cols.slice(1);
	}
	return dictionary;
}

// phones.parse(), from words and phones instead of Praat's text output.
function parseMeasurements(words, phones, pronunciationDictionary) {
	const data = { words: [], phones: [] };
	for (const w of words) {
		data.words.push({
			time: w.time,
			word: w.word,
			expected: (pronunciationDictionary[w.word.toUpperCase()] || [null]).concat(Array(10).fill(null)),
		});
	}
	let wordIndex = -1, phonemeInWordIndex = 0;
	for (const p of phones) {
		while (wordIndex < data.words.length - 1 && p.time >= data.words[wordIndex + 1].time) {
			wordIndex += 1;
			phonemeInWordIndex = 0;
		}
		// Python's negative indexing: index -1 is the last word.
		const word = data.words[wordIndex < 0 ? data.words.length + wordIndex : wordIndex];
		data.phones.push({
			time: p.time,
			phoneme: p.phoneme,
			class: scoringPhoneClass(p.phoneme),
			word_index: wordIndex,
			word: word,
			word_time: word.time,
			expected: phonemeInWordIndex < word.expected.length ? word.expected[phonemeInWordIndex] : undefined,
			F: p.F.slice(),
		});
		phonemeInWordIndex += 1;
	}
	return data;
}

function scoringMean(values) {
	return values.reduce((a, b) => a + b, 0) / values.length;
}

// Python's statistics.stdev: the sample standard deviation.
function scoringStdev(values) {
	const m = scoringMean(values);
	return Math.sqrt(values.reduce((a, v) => a + (v - m) * (v - m), 0) / (values.length - 1));
}

function scoringMedian(values) {
	const sorted = values.slice().sort((a, b) => a - b);
	const middle = Math.floor(sorted.length / 2);
	return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
}

// resonance.compute_resonance().
function computeResonance(data, stats, weights = SCORING_WEIGHTS) {
	data.mean = { F: [] };
	data.stdev = { F: [] };
	// Remove outliers: values more than 2 standard deviations from the mean.
	for (let i = 0; i < 4; i++) {
		const values = data.phones.map(p => p.F[i]).filter(v => v !== null && v !== undefined);
		const mean = scoringMean(values), stdev = scoringStdev(values);
		data.mean.F.push(mean);
		data.stdev.F.push(stdev);
		for (const p of data.phones) {
			if (!p.F[i]) continue;
			if (Math.abs(p.F[i] - mean) / stdev > 2) {
				p.outlier = true;
				p.F[i] = null;
			}
		}
	}
	for (const p of data.phones) {
		if (!(p.phoneme && p.expected && stats[p.phoneme] && stats[p.expected])) continue;
		p.F_stdevs = [0, 1, 2, 3].map(i =>
			p.F.length <= i || p.F[i] === null ? null : (p.F[i] - stats[p.expected][i].mean) / stats[p.expected][i].stdev);
	}
	for (const p of data.phones) {
		const z = p.F_stdevs;
		if (z && z[1] && z[2] && z[3]) {
			p.resonance = Math.max(0, Math.min(1, (weights[0] * z[1] + weights[1] * z[2] + weights[2] * z[3]) / 3 + 0.5));
		}
	}
	const pitch = data.phones.filter(p => p.F && p.F[0] && !p.outlier).map(p => p.F[0]);
	const resonance = data.phones.filter(p => p.resonance && !p.outlier).map(p => p.resonance);
	data.meanPitch = scoringMean(pitch);
	data.meanResonance = scoringMean(resonance);
	data.medianPitch = scoringMedian(pitch);
	data.medianResonance = scoringMedian(resonance);
	data.stdevPitch = scoringStdev(pitch);
	data.stdevResonance = scoringStdev(resonance);
	return data;
}

// The whole step: what backend.cgi returns, given the measurements.
function scoreMeasurements(words, phones, pronunciationDictionary, stats) {
	return computeResonance(parseMeasurements(words, phones, pronunciationDictionary), stats);
}

if (typeof module !== 'undefined') {
	module.exports = { parsePronunciationDictionary, parseMeasurements, computeResonance, scoreMeasurements, scoringPhoneClass };
}
