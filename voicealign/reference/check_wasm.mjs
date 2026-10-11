// Run the WebAssembly build on a WAV file and transcript, and time it.
//
//   node reference/check_wasm.mjs voicealign.wasm MODEL_DIR dictionary.dict recording.wav transcript.txt
//
// MODEL_DIR holds final.alimdl, tree, lda.mat and phones.txt. Prints the
// result as JSON on stdout and timings on stderr.
import { readFileSync } from 'node:fs';

const [wasmPath, modelDir, dictionaryPath, wavPath, transcriptPath] = process.argv.slice(2);

function readWav(buffer) {
	const view = new DataView(buffer.buffer, buffer.byteOffset, buffer.byteLength);
	let offset = 12;
	while (offset < buffer.length) {
		const id = buffer.toString('ascii', offset, offset + 4), size = view.getUint32(offset + 4, true);
		if (id === 'data') {
			const samples = new Float32Array(size / 2);
			for (let i = 0; i < samples.length; i++) samples[i] = view.getInt16(offset + 8 + 2 * i, true) / 32768;
			return samples;
		}
		offset += 8 + size + (size % 2);
	}
	throw new Error('no data chunk');
}

let t = performance.now();
const { instance } = await WebAssembly.instantiate(readFileSync(wasmPath), {});
const { memory, va_alloc, va_free, va_new, va_align } = instance.exports;
const compileMs = performance.now() - t;

function copy(bytes) {
	const pointer = va_alloc(bytes.length);
	new Uint8Array(memory.buffer, pointer, bytes.length).set(bytes);
	return [pointer, bytes.length];
}

const files = ['final.alimdl', 'tree', 'lda.mat', 'phones.txt'].map(f => readFileSync(`${modelDir}/${f}`));
files.push(readFileSync(dictionaryPath));
t = performance.now();
const buffers = files.map(copy);
const aligner = va_new(...buffers.flat());
const loadMs = performance.now() - t;
buffers.forEach(([p, n]) => va_free(p, n));
if (!aligner) throw new Error('failed to load the aligner');

const samples = readWav(readFileSync(wavPath));
const transcript = new TextEncoder().encode(readFileSync(transcriptPath, 'utf8'));
const runs = [];
let json;
for (let i = 0; i < 3; i++) {
	t = performance.now();
	const s = va_alloc(samples.byteLength);
	new Float32Array(memory.buffer, s, samples.length).set(samples);
	const [tp, tn] = copy(transcript);
	const result = va_align(aligner, s, samples.length, tp, tn);
	const length = new DataView(memory.buffer).getUint32(result, true);
	json = new TextDecoder().decode(new Uint8Array(memory.buffer, result + 4, length));
	va_free(result, 4 + length); va_free(s, samples.byteLength); va_free(tp, tn);
	runs.push(performance.now() - t);
}
console.log(json);
console.error(`compile ${compileMs.toFixed(0)} ms; load model + dictionary ${loadMs.toFixed(0)} ms; ` +
	`align ${(samples.length / 16000).toFixed(1)} s of audio (ms): ${runs.map(r => r.toFixed(0)).join(', ')}; ` +
	`memory ${(memory.buffer.byteLength / 1048576).toFixed(0)} MB`);
