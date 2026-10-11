
//let playingData;

// List of values indexed by 1/100 of milliseconds.
// Faster to retreieve because array access is O(1).
//let timedPlayingData = [];  

let globalState = new StateManager();

globalState.init('clips', []);
globalState.init('playingClip', null);
globalState.init('playbackTime', 0);
globalState.init('previewClip', null);
globalState.init('playing', false);
globalState.init('transcript', null);
// The word being heard, from the player or a constellation's vowel playback:
// {clip, wordIndex} (a phone's word_index), or null. See setSpokenWord().
globalState.init('spokenWord', null);


/*
globalState.init('windowSize', {
	height: window.innerHeight,
	width: window.innerWidth
})

window.addEventListener('resize', evt => {
	globalState.set('windowSize', {
		height: window.innerHeight,
		width: window.innerWidth
	})
});
*/
