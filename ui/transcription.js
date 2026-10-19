// Transcribing a recording with a speech-to-text server the user chooses
// (a "transcription endpoint"), to fill in the transcript.
//
// Endpoints are set up in the settings tab and stored on the device
// ('transcriptionEndpoints'); the Add a Clip dialog picks one
// ('transcriptionEndpoint', its id). Each has:
//
//   {id, name, url, schema, model, apiKey}
//
// url is the transcription URL itself (for the OpenAI schema, ending in
// /v1/audio/transcriptions); schema says how to talk to it, one of
// TRANSCRIPTION_SCHEMAS; model and apiKey are optional.
//
// Only an explicit press of "Transcribe" sends the recording, and only to
// the endpoint shown next to the button.

const TRANSCRIPTION_SCHEMAS = {
	openai: {
		label: 'OpenAI',
		description: 'OpenAI\'s audio transcription API, also offered by Speaches, '
			+ 'faster-whisper-server, LocalAI, Groq and others. '
			+ 'URL like https://host/v1/audio/transcriptions.',
		placeholder: 'https://example.com/v1/audio/transcriptions',

		headers(endpoint) {
			return endpoint.apiKey ? { Authorization: `Bearer ${endpoint.apiKey}` } : {};
		},

		// The models the server offers ([] if it doesn't say), from the
		// /v1/models next to the transcription URL.
		async models(endpoint) {
			const url = endpoint.url.replace(/\/audio\/transcriptions\/?$/, '/models');
			if (url == endpoint.url) return [];
			const response = await transcriptionFetch(endpoint, url, { headers: this.headers(endpoint) });
			const body = await response.json();
			const models = Array.isArray(body.data) ? body.data : [];
			// Speech recognition models first, when the server says which.
			const isSpeech = model => model.task == 'automatic-speech-recognition' || /whisper|transcri/i.test(model.id);
			return models.filter(isSpeech).concat(models.filter(model => !isSpeech(model))).map(model => model.id);
		},

		// {text, words}: words are [{text, probability}] when the server
		// says how sure it is of each (Speaches and faster-whisper-server do;
		// OpenAI itself doesn't), else null.
		async transcribe(endpoint, audio) {
			let model = endpoint.model;
			if (!model) {
				// OpenAI requires a model; take the server's first speech
				// model, else OpenAI's own name for Whisper.
				model = (await this.models(endpoint).catch(() => []))[0] || 'whisper-1';
			}
			const request = format => {
				const form = new FormData();
				form.append('file', audio, audioFileName(audio));
				form.append('model', model);
				form.append('response_format', format);
				if (format == 'verbose_json') form.append('timestamp_granularities[]', 'word');
				return transcriptionFetch(endpoint, endpoint.url,
					{ method: 'POST', body: form, headers: this.headers(endpoint) });
			};
			let response;
			try {
				response = await request('verbose_json');
			} catch (error) {
				// Some models (OpenAI's gpt-4o-transcribe) only do plain json.
				if (!(error instanceof TranscriptionError && error.status == 400)) throw error;
				response = await request('json');
			}
			const body = await response.json().catch(() => {
				throw new Error("the server's reply wasn't JSON");
			});
			if (typeof body.text != 'string') throw new Error("the server's reply has no text");
			return { text: body.text.trim(), words: transcriptionWords(body.words) };
		},
	},
};

class TranscriptionError extends Error {
	constructor(message, status = null) {
		super(message);
		this.status = status;
	}
}

// A verbose_json word list as [{text, probability}] (text keeps its
// leading space), or null without probabilities for every word.
function transcriptionWords(words) {
	if (!Array.isArray(words) || !words.length) return null;
	if (!words.every(w => w && typeof w.word == 'string' && typeof w.probability == 'number')) return null;
	return words.map(w => ({ text: w.word, probability: w.probability }));
}

// How much to trust a word: 'unsure' below 0.5, 'check' below 0.8. On
// shardblade's test clips, the misheard words scored 0.47 to 0.75 and the
// right ones mostly above 0.9.
function wordConfidence(probability) {
	return probability < 0.5 ? 'unsure' : probability < 0.8 ? 'check' : 'sure';
}

// fetch, with errors a person can act on.
async function transcriptionFetch(endpoint, url, options) {
	let response;
	try {
		response = await fetch(url, options);
	} catch (error) {
		let reason = "check the address, that the server is running, and that it allows requests from this site (CORS)";
		if (blockedAsMixedContent(url)) reason = "this page is https, and browsers block requests from it to http addresses";
		throw new TranscriptionError(`Couldn't reach ${endpointHost(endpoint)}: ${reason}.`);
	}
	if (!response.ok) {
		let detail = '';
		try {
			const text = await response.text();
			try {
				const body = JSON.parse(text);
				detail = (body.error && (body.error.message || body.error)) || body.detail || body.message || text;
			} catch (error) {
				detail = text;
			}
		} catch (error) {}
		if (typeof detail != 'string') detail = JSON.stringify(detail);
		detail = detail.trim().slice(0, 300);
		const hint = response.status == 401 || response.status == 403 ? ' (check the API key)' : '';
		throw new TranscriptionError(`${endpointHost(endpoint)} answered ${response.status}${hint}${detail ? ': ' + detail : ''}`,
			response.status);
	}
	return response;
}

function blockedAsMixedContent(url) {
	try {
		const target = new URL(url, location.href);
		const local = ['localhost', '127.0.0.1', '[::1]'].includes(target.hostname);
		return location.protocol == 'https:' && target.protocol == 'http:' && !local;
	} catch (error) {
		return false;
	}
}

function endpointHost(endpoint) {
	try { return new URL(endpoint.url).host; } catch (error) { return endpoint.url; }
}

// A file name with an extension matching the audio's type: servers (and
// OpenAI) pick the decoder from it.
function audioFileName(audio) {
	if (audio.name) return audio.name;
	const type = (audio.type || '').split(';')[0];
	const extensions = {
		'audio/webm': 'webm', 'video/webm': 'webm', 'audio/ogg': 'ogg', 'audio/mp4': 'm4a',
		'audio/mpeg': 'mp3', 'audio/wav': 'wav', 'audio/x-wav': 'wav', 'audio/flac': 'flac',
	};
	return `recording.${extensions[type] || 'webm'}`;
}

function transcribeWith(endpoint, audio) {
	const schema = TRANSCRIPTION_SCHEMAS[endpoint.schema];
	if (!schema) return Promise.reject(new TranscriptionError(`Unknown API type "${endpoint.schema}".`));
	return schema.transcribe(endpoint, audio);
}

// The endpoints, kept in globalState so the dialog and the editor follow
// each other.
globalState.init('transcriptionEndpoints', (() => {
	const stored = localSettings.get('transcriptionEndpoints', []);
	return Array.isArray(stored) ? stored.filter(endpoint => endpoint && endpoint.url) : [];
})());

function setTranscriptionEndpoints(endpoints) {
	globalState.set('transcriptionEndpoints', endpoints);
	if (endpoints.length) localSettings.set('transcriptionEndpoints', endpoints);
	else localSettings.remove('transcriptionEndpoints');
}

function saveTranscriptionEndpoint(endpoint) {
	const endpoints = globalState.get('transcriptionEndpoints');
	if (!endpoint.id) endpoint = { ...endpoint, id: Date.now().toString(36) + Math.random().toString(36).slice(2, 6) };
	const index = endpoints.findIndex(e => e.id == endpoint.id);
	setTranscriptionEndpoints(index < 0 ? endpoints.concat([endpoint])
		: endpoints.map(e => e.id == endpoint.id ? endpoint : e));
	return endpoint;
}

function deleteTranscriptionEndpoint(id) {
	setTranscriptionEndpoints(globalState.get('transcriptionEndpoints').filter(e => e.id != id));
	if (localSettings.get('transcriptionEndpoint') == id) localSettings.remove('transcriptionEndpoint');
}

// The endpoint the dialog uses: the one picked last, else the first.
function chosenTranscriptionEndpoint() {
	const endpoints = globalState.get('transcriptionEndpoints');
	const id = localSettings.get('transcriptionEndpoint');
	return endpoints.find(e => e.id == id) || endpoints[0] || null;
}
