// Grouping clips and choosing which ones the graph shows.
//
// Every clip is in one group (examples or the user's recordings) and has
// any number of tags (clip.tags, strings the user picks, e.g. "week 3").
// The Clips tab (clips.html) shows them as folders: one per group, and one
// per tag. globalState's 'hiddenClips' is the set of clip ids the graph
// leaves out; everything else is shown.
//
// Tags are saved with the clip (storage.js); examples aren't stored, so
// their tags are kept in the 'exampleTags' setting, by clip id.

const CLIP_GROUPS = [
	{ id: 'mine', label: 'My recordings' },
	{ id: 'examples', label: 'Examples' },
];

function clipGroup(clip) {
	return clip.example ? 'examples' : 'mine';
}

function clipTags(clip) {
	return Array.isArray(clip.tags) ? clip.tags : [];
}

function tagKey(tag) {
	return tag.toLowerCase();
}

// A tag as typed, tidied; '' if there's nothing left.
function normalizeTag(text) {
	return String(text).replace(/\s+/g, ' ').trim().slice(0, 40);
}

// "week 3, morning" → ['week 3', 'morning']
function parseTags(text) {
	return uniqueTags(text.split(',').map(normalizeTag).filter(Boolean));
}

function uniqueTags(tags) {
	const seen = new Set();
	return tags.filter(tag => !seen.has(tagKey(tag)) && seen.add(tagKey(tag)));
}

function hasTag(clip, tag) {
	return clipTags(clip).some(t => tagKey(t) == tagKey(tag));
}

// Every tag in use, sorted, one spelling per tag (the first seen).
function allTags(clips) {
	return uniqueTags(clips.flatMap(clipTags)).sort((a, b) => a.localeCompare(b, undefined, { sensitivity: 'base' }));
}

function setClipTags(clip, tags) {
	clip.tags = uniqueTags(tags.map(normalizeTag).filter(Boolean));
	if (clip.example) {
		const stored = localSettings.get('exampleTags', {});
		if (clip.tags.length) stored[clip.id] = clip.tags; else delete stored[clip.id];
		if (Object.keys(stored).length) localSettings.set('exampleTags', stored);
		else localSettings.remove('exampleTags');
	} else if (clipStore.isSaved(clip)) {
		clipStore.save(clip);
	}
	globalState.mutate('clips', () => {});
}

function addClipTag(clip, tag) {
	setClipTags(clip, clipTags(clip).concat([tag]));
}

function removeClipTag(clip, tag) {
	setClipTags(clip, clipTags(clip).filter(t => tagKey(t) != tagKey(tag)));
}

// An example's tags from earlier visits.
function applyStoredExampleTags(clip) {
	const tags = localSettings.get('exampleTags', {})[clip.id];
	if (Array.isArray(tags)) clip.tags = tags;
}

function clipId(clip) {
	return clip.id != null ? String(clip.id) : clip.title;
}

globalState.init('hiddenClips', (() => {
	const stored = localSettings.get('hiddenClips', []);
	return new Set(Array.isArray(stored) ? stored : []);
})());

function clipShown(clip, hidden = globalState.get('hiddenClips')) {
	return !hidden.has(clipId(clip));
}

// Show or hide clips on the graph.
function setClipsShown(clips, shown) {
	const hidden = new Set(globalState.get('hiddenClips'));
	for (const clip of clips) {
		if (shown) hidden.delete(clipId(clip)); else hidden.add(clipId(clip));
	}
	globalState.set('hiddenClips', hidden);
	if (hidden.size) localSettings.set('hiddenClips', [...hidden]);
	else localSettings.remove('hiddenClips');
}

// A folder's checkbox: 'all', 'some' or 'none' of its clips shown.
function shownState(clips, hidden = globalState.get('hiddenClips')) {
	const shown = clips.filter(clip => clipShown(clip, hidden)).length;
	return shown == 0 ? 'none' : shown == clips.length ? 'all' : 'some';
}
