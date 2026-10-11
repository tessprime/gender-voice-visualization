const cyrb53 = function(str, seed = 0) {
	let h1 = 0xdeadbeef ^ seed, h2 = 0x41c6ce57 ^ seed;
	for (let i = 0, ch; i < str.length; i++) {
		ch = str.charCodeAt(i);
		h1 = Math.imul(h1 ^ ch, 2654435761);
		h2 = Math.imul(h2 ^ ch, 1597334677);
	}
	h1 = Math.imul(h1 ^ (h1>>>16), 2246822507) ^ Math.imul(h2 ^ (h2>>>13), 3266489909);
	h2 = Math.imul(h2 ^ (h2>>>16), 2246822507) ^ Math.imul(h1 ^ (h1>>>13), 3266489909);
	return 4294967296 * (2097151 & h2) + (h1>>>0);
};
const hash = cyrb53


function clamp(min, max, val) {
	if (val < min) return min;
	if (val > max) return max;
	return val;
}


function last(list) {
	return list[list.length - 1];
}


// 'vowel', 'sonorant' or 'obstruent' for an ARPABET phoneme, or null for
// silence and unknown labels. Keep in sync with phone_class() in
// acousticgender/library/phones.py, which explains the classes.
const PHONE_CLASSES = {
	vowel: ['AA', 'AE', 'AH', 'AO', 'AW', 'AY', 'EH', 'ER', 'EY', 'IH', 'IY',
	        'OW', 'OY', 'UH', 'UW'],
	sonorant: ['M', 'N', 'NG', 'L', 'R', 'W', 'Y'],
	obstruent: ['P', 'B', 'T', 'D', 'K', 'G', 'F', 'V', 'TH', 'DH', 'S', 'Z',
	            'SH', 'ZH', 'HH', 'CH', 'JH'],
};
function phoneClass(phoneme) {
	let base = (phoneme || '').replace(/\d/g, '');
	for (let [name, phonemes] of Object.entries(PHONE_CLASSES)) {
		if (phonemes.includes(base)) return name;
	}
	return null;
}


// A transcript word as the aligner spells it: lowercase, without
// punctuation, with a straight apostrophe.
function normalizeWord(word) {
	return word.toLowerCase().replace(/\u2019/g, "'")
		.replace(/[^\p{L}\p{N}']/gu, '').replace(/^'+|'+$/g, '');
}


// Split a transcript into pieces for display, each word matched to the
// aligned word(s) it was heard as: [{text, wordIndices}], where wordIndices
// are phones' word_index values (empty for spaces and punctuation). Words
// are matched in order by spelling; where they differ (the aligner's <unk>,
// or a compound it split), a run of transcript words between matches maps
// to the run of aligned words there.
function transcriptPieces(transcript, phones) {
	let pieces = [];
	let pattern = /[^\s\u2014\u2013-]+/g;  // spaces and dashes separate words
	let end = 0, match;
	while ((match = pattern.exec(transcript))) {
		if (match.index > end) pieces.push({text: transcript.slice(end, match.index), wordIndices: []});
		pieces.push({text: match[0], wordIndices: [], key: normalizeWord(match[0])});
		end = pattern.lastIndex;
	}
	if (end < transcript.length) pieces.push({text: transcript.slice(end), wordIndices: []});

	let tokens = pieces.filter(piece => piece.key);
	let words = [];
	for (let phone of phones) {
		if (!phone.word || !phone.word.word) continue;  // silence
		if (!words.length || last(words).index != phone.word_index) {
			words.push({index: phone.word_index, key: normalizeWord(phone.word.word)});
		}
	}

	// Longest common subsequence of the two spellings.
	let n = tokens.length, m = words.length;
	let common = Array.from({length: n + 1}, () => new Array(m + 1).fill(0));
	for (let i = n - 1; i >= 0; i--) {
		for (let j = m - 1; j >= 0; j--) {
			common[i][j] = tokens[i].key == words[j].key
				? common[i + 1][j + 1] + 1
				: Math.max(common[i + 1][j], common[i][j + 1]);
		}
	}
	let unmatchedTokens = [], unmatchedWords = [];
	let pair = () => {
		for (let token of unmatchedTokens) token.wordIndices.push(...unmatchedWords.map(word => word.index));
		unmatchedTokens = [];
		unmatchedWords = [];
	};
	let i = 0, j = 0;
	while (i < n || j < m) {
		if (i < n && j < m && tokens[i].key == words[j].key) {
			pair();
			tokens[i++].wordIndices.push(words[j++].index);
		} else if (j == m || (i < n && common[i + 1][j] >= common[i][j + 1])) {
			unmatchedTokens.push(tokens[i++]);
		} else {
			unmatchedWords.push(words[j++]);
		}
	}
	pair();
	return pieces;
}


// Set the word being heard (see 'spokenWord' in globals.js), if it changed.
function setSpokenWord(clip, wordIndex) {
	let spoken = globalState.get('spokenWord');
	if (clip == null || wordIndex == null) {
		if (spoken) globalState.set('spokenWord', null);
	} else if (!spoken || spoken.clip != clip || spoken.wordIndex != wordIndex) {
		globalState.set('spokenWord', {clip: clip, wordIndex: wordIndex});
	}
}


function pitchPercent(pitch) {
	return clamp(0, 1, (pitch - 50) / 250);
}
