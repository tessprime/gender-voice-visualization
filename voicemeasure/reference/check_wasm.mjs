// Run the WebAssembly build on a WAV file at given times, and time it.
//
//   node reference/check_wasm.mjs target/wasm32-unknown-unknown/release/voicemeasure.wasm recording.wav times.txt
//
// Prints `time f0 f1 f2 f3` per line like examples/measure_at.rs, so the two
// outputs can be compared directly.
import { readFileSync } from 'node:fs';

const [wasmPath, wavPath, timesPath] = process.argv.slice(2);

function readWav(buffer) {
	// 16-bit PCM mono only, which is what the app produces.
	const view = new DataView(buffer.buffer, buffer.byteOffset, buffer.byteLength);
	let offset = 12, rate = 0, channels = 0, bits = 0;
	while (offset < buffer.length) {
		const id = buffer.toString('ascii', offset, offset + 4);
		const size = view.getUint32(offset + 4, true);
		if (id === 'fmt ') {
			channels = view.getUint16(offset + 10, true);
			rate = view.getUint32(offset + 12, true);
			bits = view.getUint16(offset + 22, true);
		} else if (id === 'data') {
			if (channels !== 1 || bits !== 16) throw new Error('expected 16-bit mono');
			const samples = new Float64Array(size / 2);
			for (let i = 0; i < samples.length; i++) samples[i] = view.getInt16(offset + 8 + 2 * i, true) / 32768;
			return { rate, samples };
		}
		offset += 8 + size + (size % 2);
	}
	throw new Error('no data chunk');
}

const compileStart = performance.now();
const { instance } = await WebAssembly.instantiate(readFileSync(wasmPath), {});
const compileMs = performance.now() - compileStart;
const { memory, vm_alloc, vm_free, vm_measure } = instance.exports;

const { rate, samples } = readWav(readFileSync(wavPath));
const times = readFileSync(timesPath, 'utf8').trim().split('\n').map(Number);

function measure() {
	const s = vm_alloc(samples.length), t = vm_alloc(times.length), out = vm_alloc(4 * times.length);
	// Views are made after allocating: allocation can grow (and replace) the memory buffer.
	new Float64Array(memory.buffer, s, samples.length).set(samples);
	new Float64Array(memory.buffer, t, times.length).set(times);
	vm_measure(s, samples.length, rate, t, times.length, out);
	const result = Float64Array.from(new Float64Array(memory.buffer, out, 4 * times.length));
	vm_free(s, samples.length); vm_free(t, times.length); vm_free(out, 4 * times.length);
	return result;
}

const runs = [];
let result;
for (let i = 0; i < 5; i++) {
	const start = performance.now();
	result = measure();
	runs.push(performance.now() - start);
}
const show = v => Number.isNaN(v) ? '--undefined--' : v.toFixed(3);
for (let i = 0; i < times.length; i++) {
	console.log([times[i], ...Array.from(result.slice(4 * i, 4 * i + 4), show)].join('\t'));
}
console.error(`audio ${(samples.length / rate).toFixed(1)} s at ${rate} Hz; compile+instantiate ${compileMs.toFixed(0)} ms; ` +
	`measure runs (ms): ${runs.map(r => r.toFixed(0)).join(', ')}`);
