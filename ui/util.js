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


// Play clip from time (seconds), switching the player to it if needed.
function playClipFrom(clip, time) {
	if (!clip) return;
	if (globalState.get('playingClip') != clip) globalState.set('playingClip', clip);
	globalState.set('playbackTime', time);
	globalState.set('playing', true);
}


// Set the word being heard (see 'spokenWord' in globals.js), if it changed.
// time, if given, is a moment in it to point at (e.g. the vowel playing);
// otherwise views follow the player's position.
function setSpokenWord(clip, wordIndex, time = null) {
	let spoken = globalState.get('spokenWord');
	if (clip == null || wordIndex == null) {
		if (spoken) globalState.set('spokenWord', null);
	} else if (!spoken || spoken.clip != clip || spoken.wordIndex != wordIndex || spoken.time != time) {
		globalState.set('spokenWord', {clip: clip, wordIndex: wordIndex, time: time});
	}
}


// A clip's decoded audio (an AudioBuffer), cached per clip. Used to play
// parts of a clip, like a constellation's vowels, which needs more accuracy
// than seeking the player's <audio> element, and to draw its spectrogram.
let clipAudioContext = null;
const decodedClipAudio = new WeakMap();
function decodeClipAudio(clip) {
	clipAudioContext = clipAudioContext || new AudioContext();
	if (!decodedClipAudio.has(clip)) {
		let decoding = fetch(clip.audio)
			.then(response => response.arrayBuffer())
			.then(data => clipAudioContext.decodeAudioData(data));
		decoding.catch(() => decodedClipAudio.delete(clip));
		decodedClipAudio.set(clip, decoding);
	}
	return decodedClipAudio.get(clip);
}


// Menus for a spectrogram's frequency axis (components/voice-spectrogram):
// Scale (linear or log), From and Up to, kept in step with its attributes
// (including ctrl+wheel over it, which changes "Up to"). Returns the element
// holding them; the menus' ids are idPrefix + '-frequency-scale',
// '-min-frequency' and '-max-frequency'. The choices are kept on the device
// per idPrefix (the 'spectrogramAxes' setting).
const spectrogramAxisResets = [];
function spectrogramControls(view, idPrefix) {
	const axes = ['frequency-scale', 'min-frequency', 'max-frequency'];
	const defaults = Object.fromEntries(axes.map(name => [name, view.getAttribute(name)]));
	const stored = (localSettings.get('spectrogramAxes', {}) || {})[idPrefix];
	if (stored) {
		for (const name of axes) if (stored[name] != null) view.setAttribute(name, stored[name]);
	}
	const remember = () => {
		const all = localSettings.get('spectrogramAxes', {}) || {};
		all[idPrefix] = Object.fromEntries(axes.map(name => [name, view.getAttribute(name)]));
		localSettings.set('spectrogramAxes', all);
	};

	let controls = document.createElement('div');
	controls.className = 'spectrogram-controls';
	let menu = (name, label, options) => {
		let select = document.createElement('select');
		select.id = `${idPrefix}-${name}`;
		for (let [value, text] of options) select.add(new Option(text, value));
		let wrapper = document.createElement('label');
		wrapper.append(`${label} `, select);
		controls.append(wrapper, ' ');
		return select;
	};
	let hz = values => values.map(value => [String(value), `${value} Hz`]);
	let scale = menu('frequency-scale', 'Scale', [['linear', 'Linear'], ['log', 'Log']]);
	let from = menu('min-frequency', 'From', hz([0, 50, 75, 100, 150, 200]));
	let upTo = menu('max-frequency', 'Up to', hz([500, 1000, 2000, 5000]));

	// Select value, adding it to the menu if it isn't there (e.g. from ctrl+wheel).
	let show = (select, value) => {
		value = String(value);
		if (!Array.from(select.options).some(option => option.value == value)) {
			select.add(new Option(`${value} Hz`, value));
		}
		select.value = value;
	};
	let log = view.getAttribute('frequency-scale') == 'log';
	scale.value = log ? 'log' : 'linear';
	show(from, view.getAttribute('min-frequency') || (log ? 75 : 0));
	show(upTo, view.getAttribute('max-frequency') || 5000);

	scale.addEventListener('change', () => {
		view.setAttribute('frequency-scale', scale.value);
		// A log axis can't start at 0.
		if (scale.value == 'log' && Number(from.value) <= 0) {
			from.value = '75';
			view.setAttribute('min-frequency', '75');
		}
	});
	from.addEventListener('change', () => view.setAttribute('min-frequency', from.value));
	upTo.addEventListener('change', () => view.setAttribute('max-frequency', upTo.value));
	view.addEventListener('scalechange', event => show(upTo, event.detail.maxFrequency));
	for (const select of [scale, from, upTo]) select.addEventListener('change', remember);
	view.addEventListener('scalechange', remember);

	// Back to how the page set it up (when the stored setting is reset).
	spectrogramAxisResets.push(() => {
		for (const name of axes) {
			if (defaults[name] == null) view.removeAttribute(name); else view.setAttribute(name, defaults[name]);
		}
		const log = view.getAttribute('frequency-scale') == 'log';
		scale.value = log ? 'log' : 'linear';
		show(from, view.getAttribute('min-frequency') || (log ? 75 : 0));
		show(upTo, view.getAttribute('max-frequency') || 5000);
	});
	return controls;
}


// A clip's aligned words and phones as intervals ({start, end, label},
// plus kind for phones), as <voice-spectrogram> takes them, and each
// measured phone's resonance as levels (vowels at full strength; other
// phones and outliers faded, since their formants are less meaningful).
// Each interval ends where the next begins; the last at the end of the
// audio. Silences get an empty label.
const SILENCE_LABELS = ['', 'sil', 'sp', '<eps>'];
function alignedIntervals(clip, duration) {
	let phones = (clip.phones || []).map((phone, index, all) => ({
		start: phone.time,
		end: index + 1 < all.length ? all[index + 1].time : duration,
		label: SILENCE_LABELS.includes(phone.phoneme) ? '' : phone.phoneme,
		kind: phoneClass(phone.phoneme),
		wordIndex: phone.word_index,
	}));
	let words = [];
	for (let [index, phone] of phones.entries()) {
		let previous = last(words);
		if (previous && previous.wordIndex == phone.wordIndex) {
			previous.end = phone.end;
		} else {
			let word = clip.phones[index].word;
			words.push({start: phone.start, end: phone.end, label: word ? word.word : '', wordIndex: phone.wordIndex});
		}
	}
	let levels = [];
	for (let [index, phone] of phones.entries()) {
		let measured = clip.phones[index];
		if (measured.resonance == null || !phone.label) continue;
		levels.push({
			start: phone.start, end: phone.end, value: measured.resonance,
			faded: phone.kind != 'vowel' || !!measured.outlier,
		});
	}
	return {words, phones, levels};
}


function pitchPercent(pitch) {
	return clamp(0, 1, (pitch - 50) / 250);
}
