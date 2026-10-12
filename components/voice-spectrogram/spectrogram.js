// SPDX-License-Identifier: MIT
// (See LICENSE in this folder; the rest of the repository is AGPL-3.0.)

// Spectrogram computation and painting, shared by <voice-spectrogram> (a
// whole recording) and the live view. Nothing here touches the DOM except
// renderFrequencyAxis(), so it also works in a worker and loads safely
// during server-side rendering.
//
// The defaults follow Praat's spectrogram: a Gaussian window of effective
// length 5 ms (a "broadband" spectrogram, which shows formants as dark
// bands rather than resolving individual harmonics), up to 5 kHz, 70 dB of
// dynamic range and +6 dB/octave pre-emphasis.

export const DEFAULTS = Object.freeze({
	windowLength: 0.005,  // s, effective; the window spans twice this
	timeStep: 0.002,      // s between columns (raised for long recordings)
	maxFrequency: 5000,   // Hz
	dynamicRange: 70,     // dB below the loudest point that still shows
	preEmphasis: 6,       // dB per octave above 50 Hz
	maxColumns: 8000,     // longer recordings get a larger time step
});

// In-place radix-2 FFT of (re, im), whose length must be a power of two.
// Tables are cached per size.
const fftTables = new Map();
function fftTablesFor(n) {
	if (!fftTables.has(n)) {
		let bits = Math.log2(n);
		let reverse = new Uint32Array(n);
		for (let i = 0; i < n; i++) {
			let r = 0;
			for (let b = 0; b < bits; b++) r |= ((i >> b) & 1) << (bits - 1 - b);
			reverse[i] = r;
		}
		let cos = new Float64Array(n / 2), sin = new Float64Array(n / 2);
		for (let i = 0; i < n / 2; i++) {
			cos[i] = Math.cos(-2 * Math.PI * i / n);
			sin[i] = Math.sin(-2 * Math.PI * i / n);
		}
		fftTables.set(n, {reverse, cos, sin});
	}
	return fftTables.get(n);
}

export function fft(re, im) {
	let n = re.length;
	let {reverse, cos, sin} = fftTablesFor(n);
	for (let i = 0; i < n; i++) {
		let j = reverse[i];
		if (j > i) {
			[re[i], re[j]] = [re[j], re[i]];
			[im[i], im[j]] = [im[j], im[i]];
		}
	}
	for (let size = 2; size <= n; size *= 2) {
		let half = size / 2, step = n / size;
		for (let start = 0; start < n; start += size) {
			for (let k = 0; k < half; k++) {
				let a = start + k, b = a + half;
				let wr = cos[k * step], wi = sin[k * step];
				let tr = re[b] * wr - im[b] * wi;
				let ti = re[b] * wi + im[b] * wr;
				re[b] = re[a] - tr; im[b] = im[a] - ti;
				re[a] += tr;        im[a] += ti;
			}
		}
	}
}

// Computes one spectrogram column at a time: the power spectrum, in dB,
// of the window centred on a sample, from 0 Hz to maxFrequency.
export class SpectrumAnalyzer {
	constructor(sampleRate, options = {}) {
		let o = {...DEFAULTS, ...options};
		this.sampleRate = sampleRate;
		this.maxFrequency = Math.min(o.maxFrequency, sampleRate / 2);

		// Praat's Gaussian window: physical length twice the effective one.
		let length = Math.max(4, Math.round(2 * o.windowLength * sampleRate));
		this.window = new Float32Array(length);
		let edge = Math.exp(-12);
		for (let i = 0; i < length; i++) {
			let x = (i + .5) / length - .5;
			this.window[i] = (Math.exp(-48 * x * x) - edge) / (1 - edge);
		}
		// Zero-padded to twice the next power of two, for a smoother
		// frequency axis.
		this.fftSize = 2 ** (Math.ceil(Math.log2(length)) + 1);
		this.binHz = sampleRate / this.fftSize;
		this.bins = Math.floor(this.maxFrequency / this.binHz) + 1;

		this.emphasis = new Float32Array(this.bins);
		for (let k = 0; k < this.bins; k++) {
			let f = k * this.binHz;
			this.emphasis[k] = f > 50 ? o.preEmphasis * Math.log2(f / 50) : 0;
		}
		this.re = new Float64Array(this.fftSize);
		this.im = new Float64Array(this.fftSize);
	}

	// Writes the column centred on samples[center] into out (bins values).
	column(samples, center, out) {
		let {window, re, im} = this;
		let first = center - Math.floor(window.length / 2);
		re.fill(0);
		im.fill(0);
		for (let i = 0; i < window.length; i++) {
			let s = first + i;
			if (s >= 0 && s < samples.length) re[i] = samples[s] * window[i];
		}
		fft(re, im);
		for (let k = 0; k < this.bins; k++) {
			let power = re[k] * re[k] + im[k] * im[k];
			out[k] = 10 * Math.log10(power + 1e-20) + this.emphasis[k];
		}
		return out;
	}
}

// The spectrogram of a whole recording (mono samples).
// Returns {data, columns, bins, timeStep, binHz, maxFrequency, duration,
// maxDb}, with data holding columns × bins dB values, column by column;
// column i is centred at (i + .5) * timeStep.
export function computeSpectrogram(samples, sampleRate, options = {}) {
	let o = {...DEFAULTS, ...options};
	let duration = samples.length / sampleRate;
	let timeStep = Math.max(o.timeStep, duration / o.maxColumns);
	let columns = Math.max(1, Math.floor(duration / timeStep));
	let analyzer = new SpectrumAnalyzer(sampleRate, o);
	let data = new Float32Array(columns * analyzer.bins);
	let maxDb = -Infinity;
	for (let i = 0; i < columns; i++) {
		let column = data.subarray(i * analyzer.bins, (i + 1) * analyzer.bins);
		analyzer.column(samples, Math.round((i + .5) * timeStep * sampleRate), column);
		for (let v of column) if (v > maxDb) maxDb = v;
	}
	return {
		data, columns, bins: analyzer.bins, timeStep, duration, maxDb,
		binHz: analyzer.binHz, maxFrequency: analyzer.maxFrequency,
	};
}

// Colour maps as 256 RGB entries, interpolated from a few stops; value 0 is
// silence and 1 the loudest. "magma" suits dark pages, "gray" (Praat's
// black on white) light ones.
const COLORMAP_STOPS = {
	magma: ['#000004', '#1c1044', '#4f127b', '#812581', '#b5367a', '#e55964', '#fb8761', '#fec287', '#fcfdbf'],
	viridis: ['#440154', '#472c7a', '#3b518b', '#2c718e', '#21908d', '#27ad81', '#5cc863', '#aadc32', '#fde725'],
	gray: ['#ffffff', '#000000'],
};
const colormapCache = new Map();
export function colormap(name) {
	if (!colormapCache.has(name)) {
		let stops = (COLORMAP_STOPS[name] || COLORMAP_STOPS.magma).map(hex =>
			[1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16)));
		let table = new Uint8ClampedArray(256 * 3);
		for (let i = 0; i < 256; i++) {
			let position = i / 255 * (stops.length - 1);
			let low = Math.min(Math.floor(position), stops.length - 2);
			let t = position - low;
			for (let c = 0; c < 3; c++) {
				table[i * 3 + c] = stops[low][c] + (stops[low + 1][c] - stops[low][c]) * t;
			}
		}
		colormapCache.set(name, table);
	}
	return colormapCache.get(name);
}

// Paints spectrogram columns into RGBA pixels: one pixel per column and per
// bin, highest frequency at the top. pixels is width × bins × 4 bytes;
// columns go to x = firstX onwards.
export function paintColumns(pixels, width, columnsData, bins, firstX, count, maxDb, dynamicRange, table) {
	for (let i = 0; i < count; i++) {
		let x = firstX + i;
		for (let k = 0; k < bins; k++) {
			let value = (columnsData[i * bins + k] - (maxDb - dynamicRange)) / dynamicRange;
			let index = Math.round(Math.min(1, Math.max(0, value)) * 255) * 3;
			let p = ((bins - 1 - k) * width + x) * 4;
			pixels[p] = table[index];
			pixels[p + 1] = table[index + 1];
			pixels[p + 2] = table[index + 2];
			pixels[p + 3] = 255;
		}
	}
}

// Audio for analyses that only need low frequencies (pitch, narrowband
// spectrograms) is decimated to about this rate, which makes them cheaper.
export const ANALYSIS_RATE = 16000;

// Low-pass (two biquads) and keep every factor-th sample.
export class Decimator {
	constructor(rate, factor) {
		this.factor = factor;
		this.phase = 0;
		let w = 2 * Math.PI * .45 * rate / factor / rate, alpha = Math.sin(w) / (2 * Math.SQRT1_2);
		let a0 = 1 + alpha;
		this.b = [(1 - Math.cos(w)) / 2 / a0, (1 - Math.cos(w)) / a0, (1 - Math.cos(w)) / 2 / a0];
		this.a = [-2 * Math.cos(w) / a0, (1 - alpha) / a0];
		this.state = [[0, 0, 0, 0], [0, 0, 0, 0]];  // x1, x2, y1, y2 per stage
	}

	process(input) {
		if (this.factor == 1) return input;
		let out = new Float32Array(Math.ceil((input.length + this.phase) / this.factor));
		let count = 0;
		for (let x of input) {
			for (let s of this.state) {
				let y = this.b[0] * x + this.b[1] * s[0] + this.b[2] * s[1] - this.a[0] * s[2] - this.a[1] * s[3];
				s[1] = s[0]; s[0] = x; s[3] = s[2]; s[2] = y;
				x = y;
			}
			if (this.factor == 1 || this.phase == 0) out[count++] = x;
			this.phase = (this.phase + 1) % this.factor;
		}
		return out.subarray(0, count);
	}
}

// Whole samples decimated to about ANALYSIS_RATE: {samples, sampleRate}.
export function decimate(samples, sampleRate) {
	let factor = Math.max(1, Math.round(sampleRate / ANALYSIS_RATE));
	return {samples: new Decimator(sampleRate, factor).process(samples), sampleRate: sampleRate / factor};
}

// A pitch track ([{time, hz}], hz null when unvoiced) at a fixed step.
export function computePitchTrack(samples, sampleRate, tracker, timeStep = .01) {
	let track = [];
	for (let t = timeStep / 2; t < samples.length / sampleRate; t += timeStep) {
		track.push({time: t, hz: tracker.estimate(samples, Math.round(t * sampleRate))});
	}
	return track;
}

// Draw pitch values as dots on a frequency axis from 0 to maxFrequency.
// points is a list of [x, hz] (canvas pixels, Hz); unvoiced and
// off-scale values are skipped.
export function drawPitch(context, points, maxFrequency, height, ratio, colour) {
	context.fillStyle = colour;
	context.strokeStyle = 'rgba(0, 0, 0, .7)';
	context.lineWidth = ratio;
	let radius = 2 * ratio;
	for (let [x, hz] of points) {
		if (!(hz > 0) || hz > maxFrequency) continue;
		context.beginPath();
		context.arc(x, (1 - hz / maxFrequency) * height, radius, 0, 2 * Math.PI);
		context.fill();
		context.stroke();
	}
}

// The frequency scale. Views compute columns up to at least
// COMPUTED_MAX_FREQUENCY and show up to their max-frequency, so changing the
// scale within that range only redraws.
export const COMPUTED_MAX_FREQUENCY = 5000;
export const SCALE_LIMITS = Object.freeze([100, 5000]);

// The scale after a ctrl+wheel (or pinch) step of deltaY pixels: zoomed
// exponentially, kept within SCALE_LIMITS, in steps of 50 Hz.
export function zoomedScale(maxFrequency, deltaY) {
	let scaled = maxFrequency * Math.exp(deltaY * .01);
	return Math.round(Math.min(SCALE_LIMITS[1], Math.max(SCALE_LIMITS[0], scaled)) / 50) * 50;
}

// Labels for a frequency axis from 0 to maxFrequency: about 3-6 round
// values, as [{frequency, label}].
export function frequencyTicks(maxFrequency) {
	let step = [50, 100, 200, 250, 500, 1000, 2000].find(s => maxFrequency / s <= 6) || 5000;
	let ticks = [];
	for (let f = 0; f <= maxFrequency + 1e-9; f += step) {
		ticks.push({frequency: f, label: f >= 1000 ? `${f / 1000} kHz` : `${f} Hz`});
	}
	return ticks;
}

// Fill an axis element with frequency labels, for the elements. (The only
// function here that uses the DOM, and only when called.)
export function renderFrequencyAxis(axis, maxFrequency) {
	axis.textContent = '';
	for (let {frequency, label} of frequencyTicks(maxFrequency)) {
		let span = document.createElement('span');
		span.textContent = label;
		span.style.top = `${(1 - frequency / maxFrequency) * 100}%`;
		if (frequency > maxFrequency - 1e-9 && frequency > 0) span.classList.add('top');
		axis.appendChild(span);
	}
}

// Mono samples from an AudioBuffer (channels averaged), or from
// {samples, sampleRate}.
export function monoSamples(audio) {
	if (audio.samples) return {samples: audio.samples, sampleRate: audio.sampleRate};
	let samples = new Float32Array(audio.length);
	for (let c = 0; c < audio.numberOfChannels; c++) {
		let channel = audio.getChannelData(c);
		for (let i = 0; i < samples.length; i++) samples[i] += channel[i] / audio.numberOfChannels;
	}
	return {samples, sampleRate: audio.sampleRate};
}
