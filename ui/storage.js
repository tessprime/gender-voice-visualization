// What the app keeps on this device, between visits. Nothing is sent
// anywhere; the "Stored on this device" panel in the settings tab
// (settings.html) shows all of it and deletes it.
//
//   localSettings  small preferences, in localStorage
//   clipStore      the user's own clips (audio and analysis), in IndexedDB,
//                  since a few recordings outgrow localStorage's ~5 MB
//
// Both can be unavailable (private windows, blocked site data, storage
// cleared by the browser): reads then return defaults and writes do
// nothing, so the app works as it did before anything was stored.

const STORAGE_PREFIX = 'gvv:';

// Every setting the app stores, with what the storage panel calls it.
const STORED_SETTINGS = {
	saveClips: 'Save new clips on this device',
	hiddenClips: 'Clips hidden from the graph',
	openFolders: 'Open folders in the Clips tab',
	transcriptionEndpoints: 'Transcription endpoints',
	transcriptionEndpoint: 'Transcription endpoint last used',
	exampleTags: 'Tags on examples',
	theme: 'Theme',
	customTheme: 'Custom theme',
	spectrogramAxes: 'Spectrogram axes',
};

const localSettings = {
	get(key, fallback = null) {
		try {
			const value = localStorage.getItem(STORAGE_PREFIX + key);
			return value === null ? fallback : JSON.parse(value);
		} catch (error) {
			return fallback;
		}
	},
	set(key, value) {
		try {
			localStorage.setItem(STORAGE_PREFIX + key, JSON.stringify(value));
			window.dispatchEvent(new Event('storedsettingschange'));
			return true;
		} catch (error) {
			return false;
		}
	},
	remove(key) {
		try {
			localStorage.removeItem(STORAGE_PREFIX + key);
			window.dispatchEvent(new Event('storedsettingschange'));
		} catch (error) {}
	},
	// The keys stored now, ours only (other apps on the same origin, e.g. a
	// shared github.io domain, have their own).
	keys() {
		try {
			return Object.keys(localStorage)
				.filter(key => key.startsWith(STORAGE_PREFIX))
				.map(key => key.slice(STORAGE_PREFIX.length));
		} catch (error) {
			return [];
		}
	},
	clear() {
		for (const key of this.keys()) this.remove(key);
	},
};

const clipStore = {
	// Each stored clip's key in the database, by clip object. Kept out of
	// the clip itself so exported files don't carry it.
	keys: new WeakMap(),
	_db: null,

	open() {
		if (!this._db) {
			this._db = new Promise((resolve, reject) => {
				const request = indexedDB.open('gvv', 1);
				request.onupgradeneeded = () => {
					request.result.createObjectStore('clips', { keyPath: 'key', autoIncrement: true });
				};
				request.onsuccess = () => resolve(request.result);
				request.onerror = () => reject(request.error);
				request.onblocked = () => reject(new Error('the database is open in another tab'));
			});
			this._db.catch(error => console.warn("Clips can't be stored on this device:", error));
		}
		return this._db;
	},

	async _run(mode, action) {
		const db = await this.open();
		return new Promise((resolve, reject) => {
			const transaction = db.transaction('clips', mode);
			const result = action(transaction.objectStore('clips'));
			transaction.oncomplete = () => resolve(result.result);
			transaction.onerror = () => reject(transaction.error);
			transaction.onabort = () => reject(transaction.error || new Error('storing the clip was aborted'));
		});
	},

	// Saved records: [{key, savedAt, clip}], oldest first. [] if storage
	// isn't available.
	async records() {
		try {
			return await this._run('readonly', store => store.getAll());
		} catch (error) {
			return [];
		}
	},

	// The saved clips, as clip objects for globalState's 'clips'.
	async load() {
		const clips = [];
		for (const record of await this.records()) {
			this.keys.set(record.clip, record.key);
			clips.push(record.clip);
		}
		return clips;
	},

	isSaved(clip) {
		return this.keys.has(clip);
	},

	// Save a clip, or update its saved copy. Resolves to true if it was
	// stored.
	async save(clip) {
		const { marker, ...data } = clip;  // the marker is a page element
		const record = { version: 1, savedAt: Date.now(), clip: data };
		if (this.keys.has(clip)) record.key = this.keys.get(clip);
		try {
			const key = await this._run('readwrite', store => store.put(record));
			this.keys.set(clip, key);
			window.dispatchEvent(new Event('storedclipschange'));
			return true;
		} catch (error) {
			console.warn("Couldn't store the clip on this device:", error);
			return false;
		}
	},

	// Save a clip if the user wants new clips kept (the default).
	saveIfWanted(clip) {
		return localSettings.get('saveClips', true) ? this.save(clip) : Promise.resolve(false);
	},

	async remove(clip) {
		if (!this.keys.has(clip)) return;
		await this.removeKey(this.keys.get(clip));
		this.keys.delete(clip);
	},

	async removeKey(key) {
		try {
			await this._run('readwrite', store => store.delete(key));
		} catch (error) {
			console.warn("Couldn't delete the stored clip:", error);
		}
		window.dispatchEvent(new Event('storedclipschange'));
	},

	async clear() {
		try {
			await this._run('readwrite', store => store.clear());
		} catch (error) {
			console.warn("Couldn't delete the stored clips:", error);
		}
		this.keys = new WeakMap();
		window.dispatchEvent(new Event('storedclipschange'));
	},
};

// About how many bytes a stored clip takes: its audio (a base64 data URL)
// plus its analysis.
function storedClipBytes(clip) {
	const audio = clip.audio ? Math.round((clip.audio.length - clip.audio.indexOf(',') - 1) * 3 / 4) : 0;
	let analysis = 0;
	try { analysis = JSON.stringify(clip.phones || []).length; } catch (error) {}
	return audio + analysis;
}

function formatBytes(bytes) {
	if (bytes < 1000) return `${bytes} B`;
	if (bytes < 1e6) return `${Math.round(bytes / 1e3)} kB`;
	if (bytes < 1e9) return `${(bytes / 1e6).toFixed(1)} MB`;
	return `${(bytes / 1e9).toFixed(1)} GB`;
}
