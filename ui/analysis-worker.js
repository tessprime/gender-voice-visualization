// Web Worker that analyses a recording entirely in the browser: the same
// steps as the server (backend.cgi), with WebAssembly modules in place of
// MFA and Praat:
//
//   voicealign    align the transcript to the audio (words, phones)
//   voicemeasure  F0 and F1-F3 at each phone's midpoint
//   scoring.js    expected phonemes, z-scores, resonance, statistics
//
// Messages in:  {id, samples (Float32Array, 16 kHz mono, -1..1), transcript}
// Messages out: {id, progress: text} while loading, then {id, result} with
//               what backend.cgi returns, or {id, error}.
//
// Loading (~60 MB of model data, a few seconds) happens once, on the first
// request.
importScripts('scoring.js');

let loading = null;

async function bytes(url) {
	const response = await fetch(url);
	if (!response.ok) throw new Error(`couldn't load ${url} (${response.status})`);
	return new Uint8Array(await response.arrayBuffer());
}

async function instantiate(url) {
	return (await WebAssembly.instantiate(await bytes(url), {})).instance.exports;
}

// Copy bytes into a module's memory; returns [pointer, length].
function copyIn(module, alloc, data) {
	const pointer = alloc(data.byteLength);
	new Uint8Array(module.memory.buffer, pointer, data.byteLength).set(new Uint8Array(data.buffer, data.byteOffset, data.byteLength));
	return [pointer, data.byteLength];
}

async function load(progress) {
	progress('Loading voice models (first time only)…');
	const [align, measure, model, tree, lda, phones, dictionary, cmudict, stats] = await Promise.all([
		instantiate('wasm/voicealign.wasm'),
		instantiate('wasm/voicemeasure.wasm'),
		bytes('../models/final.alimdl'),
		bytes('../models/tree'),
		bytes('../models/lda.mat'),
		bytes('../models/phones.txt'),
		bytes('../models/english.dict'),
		bytes('../cmudict.txt'),
		bytes('../stats.json'),
	]);
	progress('Preparing voice models…');
	const buffers = [model, tree, lda, phones, dictionary].map(b => copyIn(align, align.va_alloc, b));
	const aligner = align.va_new(...buffers.flat());
	buffers.forEach(([p, n]) => align.va_free(p, n));
	if (!aligner) throw new Error('the alignment model failed to load');
	return {
		align, measure, aligner,
		pronunciations: parsePronunciationDictionary(new TextDecoder('iso-8859-1').decode(cmudict)),
		stats: JSON.parse(new TextDecoder().decode(stats)),
	};
}

// Intervals covering 0..duration, with gaps filled by silence (''), as the
// TextGrid tiers the server's Praat script reads.
function fillTier(intervals, duration) {
	const tier = [];
	let time = 0;
	for (const [start, end, label] of intervals) {
		if (start > time + 1e-9) tier.push([time, start, '']);
		tier.push([start, end, label]);
		time = end;
	}
	if (time < duration - 1e-9) tier.push([time, duration, '']);
	return tier;
}

function analyze(m, samples, transcript) {
	// Align.
	const text = new TextEncoder().encode(transcript);
	const s = m.align.va_alloc(samples.byteLength);
	new Float32Array(m.align.memory.buffer, s, samples.length).set(samples);
	const [t, tn] = copyIn(m.align, m.align.va_alloc, text);
	const r = m.align.va_align(m.aligner, s, samples.length, t, tn);
	const length = new DataView(m.align.memory.buffer).getUint32(r, true);
	const alignment = JSON.parse(new TextDecoder().decode(new Uint8Array(m.align.memory.buffer, r + 4, length)));
	m.align.va_free(r, 4 + length); m.align.va_free(s, samples.byteLength); m.align.va_free(t, tn);
	if (alignment.error) throw new Error(alignment.error);

	const duration = samples.length / 16000;
	const words = fillTier(alignment.words, duration);
	const phones = fillTier(alignment.phones, duration);

	// Measure at each phone's midpoint.
	const times = Float64Array.from(phones, ([start, end]) => start + (end - start) / 2);
	const sp = m.measure.vm_alloc(samples.length), tp = m.measure.vm_alloc(times.length), out = m.measure.vm_alloc(4 * times.length);
	new Float64Array(m.measure.memory.buffer, sp, samples.length).set(samples);
	new Float64Array(m.measure.memory.buffer, tp, times.length).set(times);
	m.measure.vm_measure(sp, samples.length, 16000, tp, times.length, out);
	const values = Array.from(new Float64Array(m.measure.memory.buffer, out, 4 * times.length), v => Number.isNaN(v) ? null : v);
	m.measure.vm_free(sp, samples.length); m.measure.vm_free(tp, times.length); m.measure.vm_free(out, 4 * times.length);

	return scoreMeasurements(
		words.map(([start, , label]) => ({ time: start, word: label })),
		phones.map(([start, , label], i) => ({ time: start, phoneme: label, F: values.slice(4 * i, 4 * i + 4) })),
		m.pronunciations, m.stats);
}

self.onmessage = async ({ data }) => {
	const { id, samples, transcript } = data;
	try {
		const progress = text => self.postMessage({ id, progress: text });
		loading = loading || load(progress);
		const models = await loading;
		self.postMessage({ id, progress: 'Analysing…' });
		self.postMessage({ id, result: analyze(models, samples, transcript) });
	} catch (error) {
		if (loading && String(error).includes('load')) loading = null; // allow a retry
		self.postMessage({ id, error: String(error && error.message || error) });
	}
};
