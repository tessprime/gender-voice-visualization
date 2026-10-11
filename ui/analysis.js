// Analysing a recording in the browser (see analysis-worker.js), off the
// main thread so the page stays responsive.
//
//   analyzeInBrowser(blob, transcript, onProgress) -> Promise of what
//   backend.cgi returns.

let analysisWorker = null;
let analysisRequests = 0;

// Decode a recording or audio file to 16 kHz mono samples (-1..1), as the
// analysis expects; channels are averaged.
async function decodeTo16kMono(blob) {
	const context = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
	try {
		const audio = await context.decodeAudioData(await blob.arrayBuffer());
		const mono = new Float32Array(audio.length);
		for (let c = 0; c < audio.numberOfChannels; c++) {
			const channel = audio.getChannelData(c);
			for (let i = 0; i < mono.length; i++) mono[i] += channel[i] / audio.numberOfChannels;
		}
		return mono;
	} finally {
		context.close();
	}
}

async function analyzeInBrowser(blob, transcript, onProgress = () => {}) {
	if (typeof Worker === 'undefined' || typeof WebAssembly === 'undefined') {
		throw new Error("this browser can't run the analysis");
	}
	const samples = await decodeTo16kMono(blob);
	if (!analysisWorker) analysisWorker = new Worker('./ui/analysis-worker.js');
	const id = ++analysisRequests;
	return new Promise((resolve, reject) => {
		const listener = ({ data }) => {
			if (data.id !== id) return;
			if (data.progress) return onProgress(data.progress);
			analysisWorker.removeEventListener('message', listener);
			if (data.error) reject(new Error(data.error)); else resolve(data.result);
		};
		analysisWorker.addEventListener('message', listener);
		analysisWorker.postMessage({ id, samples, transcript }, [samples.buffer]);
	});
}
