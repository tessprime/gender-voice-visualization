// SPDX-License-Identifier: MIT
// (See LICENSE in this folder; the rest of the repository is AGPL-3.0.)

// <voice-live-spectrogram>: a scrolling spectrogram of a live audio stream
// (e.g. the microphone while recording), with the pitch drawn over it.
//
// Framework-free custom element; see README.md for the API. Set `stream`
// to a MediaStream to start, and to null to stop (the picture stays).

import {SpectrumAnalyzer, colormap, paintColumns, COMPUTED_MAX_FREQUENCY, zoomedScale,
	renderFrequencyAxis, Decimator, ANALYSIS_RATE, drawPitch} from './spectrogram.js';
import {PitchTracker} from './pitch.js';

const Base = typeof HTMLElement == 'undefined' ? class {} : HTMLElement;

const DEFAULTS = {
	maxFrequency: 1000,   // Hz shown; columns are computed up to COMPUTED_MAX_FREQUENCY
	windowLength: .025,   // s; longer than <voice-spectrogram>'s so harmonics separate
	dynamicRange: 60,     // dB
	duration: 5,          // s visible
	minPitch: 75,
	maxPitch: 600,
	colormap: 'magma',
};
const TIME_STEP = .01;        // s between columns

// Collects the input's samples off the audio thread, in batches.
const TAP_WORKLET = `
class VoiceLiveTap extends AudioWorkletProcessor {
	constructor() { super(); this.batch = new Float32Array(1024); this.length = 0; }
	process(inputs) {
		const input = inputs[0] && inputs[0][0];
		if (input) {
			for (let i = 0; i < input.length; i++) {
				this.batch[this.length++] = input[i];
				if (this.length == this.batch.length) {
					this.port.postMessage(this.batch);
					this.batch = new Float32Array(1024);
					this.length = 0;
				}
			}
		}
		return true;
	}
}
registerProcessor('voice-live-tap', VoiceLiveTap);
`;

const TEMPLATE = `
<style>
	:host {
		display: block;
		position: relative;
		color: var(--vs-text, currentColor);
		background: var(--vs-background, transparent);
		user-select: none;
		-webkit-user-select: none;
	}
	:host([hidden]) { display: none; }
	.plot {
		position: relative;
		height: var(--vs-height, 200px);
		margin-left: var(--vs-axis-width, 3.2em);
		background: var(--vs-plot-background, black);
	}
	canvas {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
		display: block;
	}
	.axis {
		position: absolute;
		top: 0;
		bottom: 0;
		right: 100%;
		width: var(--vs-axis-width, 3.2em);
		font-size: .75em;
		opacity: .8;
	}
	.axis span {
		position: absolute;
		right: .4em;
		transform: translateY(-50%);
		white-space: nowrap;
	}
	.axis span:first-child { transform: translateY(-100%); }
	.axis span.top { transform: none; }
	.readout {
		position: absolute;
		top: .3em;
		right: .4em;
		padding: 0 .3em;
		border-radius: 3px;
		background: rgba(0, 0, 0, .6);
		color: var(--vs-pitch, #4dd0ff);
		font-variant-numeric: tabular-nums;
		font-weight: bold;
	}
</style>
<div class="plot" part="plot">
	<canvas part="canvas"></canvas>
	<div class="axis" part="axis"></div>
	<div class="readout" part="readout">– Hz</div>
</div>
`;

export class VoiceLiveSpectrogram extends Base {
	static get observedAttributes() {
		return ['max-frequency', 'window-length', 'dynamic-range', 'colormap', 'duration', 'min-pitch', 'max-pitch'];
	}

	constructor() {
		super();
		this.attachShadow({mode: 'open'});
		this.shadowRoot.innerHTML = TEMPLATE;
		this._plot = this.shadowRoot.querySelector('.plot');
		this._canvas = this.shadowRoot.querySelector('canvas');
		this._axis = this.shadowRoot.querySelector('.axis');
		this._readout = this.shadowRoot.querySelector('.readout');

		this._stream = null;
		this._session = null;   // the audio graph and analysis while running
		this._history = null;   // what's drawn: a ring of columns and pitches
		this._pitch = null;
		this._frame = null;

		// Ctrl+wheel (or pinch) over the view changes the frequency scale.
		this.addEventListener('wheel', event => {
			if (!event.ctrlKey) return;
			event.preventDefault();
			let value = zoomedScale(this.maxFrequency, event.deltaY);
			if (value != this.maxFrequency) {
				this.setAttribute('max-frequency', value);
				this.dispatchEvent(new CustomEvent('scalechange', {detail: {maxFrequency: value}}));
			}
		}, {passive: false});

		if (Object.prototype.hasOwnProperty.call(this, 'stream')) {
			let stream = this.stream;
			delete this.stream;
			this.stream = stream;
		}
	}

	connectedCallback() {
		if (!this._resizeObserver && typeof ResizeObserver != 'undefined') {
			this._resizeObserver = new ResizeObserver(() => this._draw());
			this._resizeObserver.observe(this._plot);
		}
		this._renderAxis();
		this._draw();
	}

	disconnectedCallback() {
		this.stream = null;
		if (this._resizeObserver) this._resizeObserver.disconnect();
		this._resizeObserver = null;
	}

	attributeChangedCallback(name) {
		if (['max-frequency', 'dynamic-range', 'colormap'].includes(name)) {
			// Display only; dynamic range and colours apply to new columns.
			this._renderAxis();
			this._draw();
		} else if (this._session) {
			// Analysis settings: start over with them.
			let stream = this._stream;
			this.stream = null;
			this.clear();
			this.stream = stream;
		}
	}

	// The MediaStream to analyse, or null to stop. Starting needs an audio
	// context, which browsers only allow after a user gesture (such as the
	// click that started recording).
	get stream() { return this._stream; }
	set stream(stream) {
		if (stream == this._stream) return;
		this._stop();
		this._stream = stream || null;
		if (this._stream) this._start(this._stream);
	}

	// The latest pitch in Hz, or null when unvoiced or stopped.
	get pitch() { return this._pitch; }

	get maxFrequency() { return this._number('max-frequency', DEFAULTS.maxFrequency); }

	// Forget what's been drawn.
	clear() {
		this._history = null;
		this._pitch = null;
		this._readout.textContent = '– Hz';
		this._draw();
	}

	_number(name, fallback) {
		let value = parseFloat(this.getAttribute(name));
		return isNaN(value) ? fallback : value;
	}

	async _start(stream) {
		let session = {stream};
		this._session = session;
		try {
			let context = new AudioContext();
			session.context = context;
			if (context.state == 'suspended') await context.resume();
			let factor = Math.max(1, Math.round(context.sampleRate / ANALYSIS_RATE));
			let rate = context.sampleRate / factor;
			session.decimator = new Decimator(context.sampleRate, factor);
			session.analyzer = new SpectrumAnalyzer(rate, {
				windowLength: this._number('window-length', DEFAULTS.windowLength),
				maxFrequency: COMPUTED_MAX_FREQUENCY,
			});
			session.tracker = new PitchTracker(rate, {
				minPitch: this._number('min-pitch', DEFAULTS.minPitch),
				maxPitch: this._number('max-pitch', DEFAULTS.maxPitch),
			});
			session.rate = rate;
			session.hop = Math.round(TIME_STEP * rate);
			session.reach = Math.max(Math.ceil(session.analyzer.window.length / 2), session.tracker.reach);
			session.buffer = new Float32Array(0);   // recent samples
			session.bufferStart = 0;                // absolute index of buffer[0]
			session.next = session.reach;           // absolute centre of the next column
			session.column = new Float32Array(session.analyzer.bins);
			this._ensureHistory(session.analyzer);

			let source = context.createMediaStreamSource(stream);
			let tap;
			try {
				let url = URL.createObjectURL(new Blob([TAP_WORKLET], {type: 'text/javascript'}));
				await context.audioWorklet.addModule(url);
				URL.revokeObjectURL(url);
				tap = new AudioWorkletNode(context, 'voice-live-tap');
				tap.port.onmessage = event => this._session == session && this._push(session, event.data);
			} catch (error) {
				// No AudioWorklet (or blob: URLs are blocked): the older API.
				tap = context.createScriptProcessor(2048, 1, 1);
				tap.onaudioprocess = event => this._session == session &&
					this._push(session, event.inputBuffer.getChannelData(0).slice());
			}
			if (this._session != session) return;  // stopped meanwhile
			let mute = context.createGain();
			mute.gain.value = 0;
			source.connect(tap).connect(mute).connect(context.destination);
			session.nodes = [source, tap, mute];
			let tick = () => {
				if (this._session != session) return;
				this._draw();
				this._frame = requestAnimationFrame(tick);
			};
			tick();
		} catch (error) {
			console.error('voice-live-spectrogram could not start:', error);
			if (this._session == session) this._stop();
			this.dispatchEvent(new CustomEvent('error', {detail: error}));
		}
	}

	_stop() {
		let session = this._session;
		this._session = null;
		cancelAnimationFrame(this._frame);
		if (!session) return;
		for (let node of session.nodes || []) node.disconnect();
		if (session.context) session.context.close();
		this._pitch = null;
		this._draw();
	}

	// The ring of columns drawn: one pixel column per 10 ms, as many as the
	// visible duration holds. Kept across stop/start, so a recording's
	// picture stays until clear().
	_ensureHistory(analyzer) {
		let columns = Math.round(this._number('duration', DEFAULTS.duration) / TIME_STEP);
		let h = this._history;
		if (h && h.columns == columns && h.bins == analyzer.bins && h.binHz == analyzer.binHz) return;
		let image = document.createElement('canvas');
		image.width = columns;
		image.height = analyzer.bins;
		this._history = {
			image, columns, bins: analyzer.bins, binHz: analyzer.binHz,
			context: image.getContext('2d'),
			pixels: new ImageData(1, analyzer.bins),
			pitch: new Float32Array(columns).fill(NaN),
			write: 0,            // the next column to fill
			maxDb: -Infinity,    // loudest recently, for the colour scale
		};
	}

	_push(session, chunk) {
		let samples = session.decimator.process(chunk);
		let buffer = new Float32Array(session.buffer.length + samples.length);
		buffer.set(session.buffer);
		buffer.set(samples, session.buffer.length);
		session.buffer = buffer;
		let end = session.bufferStart + buffer.length;
		while (session.next + session.reach <= end) {
			let center = session.next - session.bufferStart;
			session.analyzer.column(session.buffer, center, session.column);
			let pitch = session.tracker.estimate(session.buffer, center);
			this._addColumn(session.column, pitch, session.next / session.rate);
			session.next += session.hop;
		}
		// Keep only what the next column needs.
		let keep = session.next - session.reach - session.bufferStart;
		if (keep > 0) {
			session.buffer = session.buffer.slice(keep);
			session.bufferStart += keep;
		}
	}

	_addColumn(column, pitch, time) {
		let h = this._history;
		let loudest = -Infinity;
		for (let v of column) if (v > loudest) loudest = v;
		// The colour scale follows the loudest recent column, decaying slowly
		// (about 20 dB in 4 s) so quiet stretches don't all turn bright.
		h.maxDb = Math.max(loudest, h.maxDb - .05);
		let range = this._number('dynamic-range', DEFAULTS.dynamicRange);
		let table = colormap(this.getAttribute('colormap') || DEFAULTS.colormap);
		paintColumns(h.pixels.data, 1, column, h.bins, 0, 1, h.maxDb, range, table);
		h.context.putImageData(h.pixels, h.write, 0);
		h.pitch[h.write] = pitch == null ? NaN : pitch;
		h.write = (h.write + 1) % h.columns;

		this._pitch = pitch;
		this.dispatchEvent(new CustomEvent('pitch', {detail: {time, hz: pitch}}));
	}

	_draw() {
		let canvas = this._canvas;
		let ratio = (typeof devicePixelRatio == 'number' && devicePixelRatio) || 1;
		let width = Math.round(this._plot.clientWidth * ratio);
		let height = Math.round(this._plot.clientHeight * ratio);
		if (!width || !height) return;
		if (canvas.width != width || canvas.height != height) {
			canvas.width = width;
			canvas.height = height;
		}
		let context = canvas.getContext('2d');
		context.clearRect(0, 0, width, height);
		let h = this._history;
		this._readout.textContent = this._pitch ? `${Math.round(this._pitch)} Hz` : '– Hz';
		if (!h) return;

		// Oldest on the left: the ring from write onwards, then up to write.
		let maxFrequency = this.maxFrequency;
		let shownBins = Math.min(h.bins, maxFrequency / h.binHz);
		let sourceY = h.bins - shownBins;
		let columnWidth = width / h.columns;
		context.imageSmoothingEnabled = true;
		let older = h.columns - h.write;
		context.drawImage(h.image, h.write, sourceY, older, shownBins, 0, 0, older * columnWidth, height);
		if (h.write) {
			context.drawImage(h.image, 0, sourceY, h.write, shownBins, older * columnWidth, 0, h.write * columnWidth, height);
		}

		// The pitch, as dots on the same frequency axis.
		let colour = getComputedStyle(this).getPropertyValue('--vs-pitch').trim() || '#4dd0ff';
		let points = [];
		for (let i = 0; i < h.columns; i++) points.push([(i + .5) * columnWidth, h.pitch[(h.write + i) % h.columns]]);
		drawPitch(context, points, maxFrequency, height, ratio, colour);
	}

	_renderAxis() {
		renderFrequencyAxis(this._axis, this.maxFrequency);
	}
}

if (typeof customElements != 'undefined' && !customElements.get('voice-live-spectrogram')) {
	customElements.define('voice-live-spectrogram', VoiceLiveSpectrogram);
}
