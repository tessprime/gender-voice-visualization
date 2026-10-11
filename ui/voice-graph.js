

// Labels for each vowel (stress digits removed; see phoneClass() in
// util.js). Unstressed AH0 is the schwa, which sounds unlike stressed AH,
// so it gets its own group.
const VOWEL_LABELS = {
	AA: 'AA (father)', AE: 'AE (cat)',   AH: 'AH (but)',   SCHWA: 'ə (about)',
	AO: 'AO (thought)', AW: 'AW (cow)',  AY: 'AY (my)',    EH: 'EH (bed)',
	ER: 'ER (bird)',   EY: 'EY (say)',   IH: 'IH (sit)',   IY: 'IY (see)',
	OW: 'OW (go)',     OY: 'OY (boy)',   UH: 'UH (book)',  UW: 'UW (too)',
};

// Group a clip's vowel phones by vowel. Each group has the vowel's average
// position and the positions of every instance. Only phones with both a
// pitch and a resonance count, and outliers are skipped, as for the
// clip's own median. Each instance keeps its word and the word's span in
// the recording, which ends where the next word (or silence) starts, or at
// the end of the audio.
function vowelGroups(clip) {
	let groups = {};
	let phones = clip.phones || [];
	for (let [index, phone] of phones.entries()) {
		if (phoneClass(phone.phoneme) != 'vowel' || phone.outlier) continue;
		if (!phone.F || !phone.F[0] || phone.resonance == null) continue;
		let key = phone.phoneme == 'AH0' ? 'SCHWA' : phone.phoneme.replace(/\d/g, '');

		groups[key] = groups[key] || {key: key, label: VOWEL_LABELS[key], instances: []};
		groups[key].instances.push({
			pitch: pitchPercent(phone.F[0]),
			resonance: phone.resonance,
			hz: phone.F[0],
			start: phone.time,
			word: phone.word ? phone.word.word : '',
			wordStart: phone.word_time,
			wordEnd: wordEnd(phones, index),
		});
	}
	for (let group of Object.values(groups)) {
		let mean = values => values.reduce((a, b) => a + b, 0) / values.length;
		group.hz = mean(group.instances.map(i => i.hz));
		group.pitch = pitchPercent(group.hz);
		group.resonance = mean(group.instances.map(i => i.resonance));
	}
	return Object.values(groups);
}

// Playing parts of a clip, like a constellation's vowels, needs sample
// accuracy that seeking the player's <audio> element doesn't have, so they
// play through Web Audio from the clip's decoded audio (cached per clip).
let vowelAudioContext = null;
const decodedClipAudio = new WeakMap();
function decodeClipAudio(clip) {
	vowelAudioContext = vowelAudioContext || new AudioContext();
	if (!decodedClipAudio.has(clip)) {
		let decoding = fetch(clip.audio)
			.then(response => response.arrayBuffer())
			.then(data => vowelAudioContext.decodeAudioData(data));
		decoding.catch(() => decodedClipAudio.delete(clip));
		decodedClipAudio.set(clip, decoding);
	}
	return decodedClipAudio.get(clip);
}

// Vowel playback: each instance plays its whole word (an isolated vowel is
// often too short to hear), with a little audio either side, faded in and
// out to avoid clicks, and a pause between words.
const VOWEL_PADDING = .03;
const VOWEL_FADE = .015;
const VOWEL_GAP = .35;

// When the word of phones[index] ends: where the next phone of another
// word starts, or null for the end of the audio.
function wordEnd(phones, index) {
	let next = phones.slice(index + 1).find(phone => phone.word_index != phones[index].word_index);
	return next ? next.time : null;
}

class VoiceGraph {

	constructor(element) {

		this.element = element;

		element.style.position = 'relative';
		element.style.boxSizing = 'border-box'
		let size = element.clientWidth;

		this.pitchUpperBoundHz = 300;
		this.pitchLowerBoundHz = 50;
		this.pitchRange = this.pitchUpperBoundHz - this.pitchLowerBoundHz;

		for (let child of [
			div({'class': 'x axis-labels'}, 
				['0%', '← Resonance →', '100%'].map((s, i) => span(
					s, {style: 'min-width: 3em; text-align: center;', 'class': i == 1 ? 'title' : ''}
				))
			),
			div({'class': 'x-opposite axis-labels'}, [
				this.xValueLabel = span('25%', {'class': 'current-value'})
			]),

			div({'class': 'y axis-labels'},
				[this.pitchUpperBoundHz + 'Hz', '← Pitch →', 
				 this.pitchLowerBoundHz + 'Hz'
				].map((s, i) => span(
					s, {style: 'min-height: 3em; text-align: center;', 'class': i == 1 ? 'title' : ''})
				)
			),
			div({'class': 'y-opposite axis-labels'}, [
				this.yValueLabel = span('25%', {'class': 'current-value'})
			]),
			
			div({'class': 'overlay'}, [
				this.xHairline = span(' ', {'class': 'x hairline hidden'}),
				this.yHairline = span(' ', {'class': 'y hairline hidden'}),
			], ' '),
			
			div('𝄞', {'class': 'treble clef'}),
			div('𝄢', {'class': 'bass clef'}),
			div({'class': 'instrument flute'}, String(brightIcon)),
			div({ 'class': 'instrument tuba'}, String(darkIcon)),

			this.canvas = create('canvas', {
				height: size, 
				width: size, 
			})
		]) {
			element.appendChild(child);
		}


		// displays a plane which blends colors
		// from cool to warm, leftward, on the x-axis
		// and from light to dark, downard, on the y-axis.
		let ctx = this.canvas.getContext('2d');
		let rgba = ctx.getImageData(0, 0, this.canvas.width, this.canvas.height);
		let pink = {r: 255, g: 40,  b: 0};
		let blue = {r: 0,   g: 100, b: 255};
		for (let i = 0; i < rgba.data.length; i += 4) {
			let rise = ((i/4) / rgba.height) / rgba.height;
			let run  = ((i/4) % rgba.width) / rgba.width;
			let pinkBlue = this.lighten(
				this.blend(blue, pink, (2/3)*run + (1/3)*(1 - rise)),
				1 - (1.5 * rise)**(.5)
			)
			rgba.data[i]   = pinkBlue.r;
			rgba.data[i+1] = pinkBlue.g;
			rgba.data[i+2] = pinkBlue.b;
			rgba.data[i+3] = 255;
		}
		ctx.putImageData(rgba, 0, 0);

		window.addEventListener('resize', evt => {
			for (let marker of $$('.marker')) {
				this.update(marker);
			}
			this.closeConstellation();
		});
		// The player and vowel playback shouldn't play over each other.
		globalState.render(['playing'], current => {
			if (current.playing) this.stopVowel();
		});
		globalState.render(['clips'], current => {
			let orphanedMarkers = Array.from($$('.marker'));
			for (let clip of current.clips) {
				if (!clip.marker) {
					clip.marker = this.addMarker(pitchPercent(clip.medianPitch) || .5, clip.medianResonance || .5, null, null);
					clip.marker.setAttribute('data-id', clip.id);
					clip.marker.style.background = clip.color;

					clip.marker.addEventListener('click', evt => {
						if (globalState.get('playingClip') == clip) {
							globalState.set('playing', !globalState.get('playing'));
						} else {
							$('.tab-set button.details').click();
							globalState.set('playbackTime', 0);
							globalState.set('playing', false);
							globalState.set('playingClip', clip);
							globalState.set('previewClip', clip);
						}
					});
					clip.marker.addEventListener('mouseenter', evt => {
						globalState.set('previewClip', clip);
						for (let marker of $$('.marker')) this.update(marker);
						this.openConstellation(clip);
					});
					clip.marker.addEventListener('mouseleave', evt => {
						this.scheduleConstellationClose();
					});
					this.update(clip.marker);
				} else {
					let index = orphanedMarkers.indexOf(clip.marker);
					orphanedMarkers.splice(index, 1);
				}
			}
			for (let marker of orphanedMarkers) {
				marker.parentNode.removeChild(marker);
			}

		})


		globalState.render(['previewClip'], current => {
			for (let marker of $$('.marker')) {
				marker.classList.remove('preview');
				this.update(marker);
			}
			if (current.previewClip && current.previewClip.marker) {
				current.previewClip.marker.classList.add('preview');
			}
			let hairlines = $$('voice-graph-2d > .overlay > .hairline');
			for (let hairline of hairlines) {
				if (current.previewClip) {
					hairline.classList.remove('hidden');
				} else {
					hairline.classList.add('hidden');
				}
			}
		})

		globalState.render(['playingClip'], current => {
			for (let marker of $$('.marker')) {
				marker.querySelector('.infobox').innerHTML = '';
				marker.classList.remove('playing');
			};
			if (current.playingClip && current.playingClip.marker) {
				current.playingClip.marker.classList.add('playing');
			}
		})

		globalState.render(['playbackTime'], current  => {

			let timeIndex = Math.floor(current.playbackTime * 100);
			let playingClip = globalState.get('playingClip');
			if (!playingClip || 
				!playingClip.indexedPhones || 
				timeIndex >= playingClip.indexedPhones.length ||
				!playingClip.marker
			) return;
			
			let currentPhone = playingClip.indexedPhones[timeIndex];

			playingClip.marker.querySelector('.infobox').innerHTML = 
				currentPhone.word.word == '' ? '' 
					: (currentPhone.word.word.replace(/^\w/, (c) => c.toUpperCase()) + ' - ') 
				+ currentPhone.phoneme;
			
			if (current.playbackTime == 0 || Math.abs(current.playbackTime - last(playingClip.phones).time) < 1 ) {
				playingClip.marker.setAttribute('data-pitch', pitchPercent(playingClip.medianPitch) || .5);
				playingClip.marker.setAttribute('data-resonance', playingClip.medianResonance || .5);
			} else {
				let isVowel = phoneClass(currentPhone.phoneme) == 'vowel';

				if (isVowel && currentPhone.hasOwnProperty('F_stdevs') && 
					currentPhone.F_stdevs[0] &&  currentPhone.F_stdevs[1] && 
					currentPhone.F_stdevs[2] &&  currentPhone.F_stdevs[3]
				) {
					if (currentPhone != null && currentPhone.F[0]  &&isVowel) {
						playingClip.marker.setAttribute('data-pitch', pitchPercent(currentPhone.F[0]));
					}
					// Use the backend's per-phone resonance so playback is on the
					// same scale as the clip's median and the details panel.
					if (currentPhone.resonance != null && isVowel) {
						playingClip.marker.setAttribute('data-resonance', currentPhone.resonance);
					}
				}
			}

			this.update(playingClip.marker);
		});
	}

	// The CSS transform that places a dot at the given pitch and resonance
	// (both 0-1) within the overlay, as update() does for markers.
	position(pitch, resonance) {
		let overlay = this.element.querySelector('.overlay');
		return `translate(${Math.round(overlay.clientWidth * resonance)}px, `
			+ `${Math.round(overlay.clientHeight * (1 - pitch))}px)`;
	}

	// Fan a clip's marker out into one dot per vowel, at that vowel's
	// average position. Hovering a vowel dot fans it out into each instance.
	openConstellation(clip) {
		clearTimeout(this.constellationCloseTimer);
		if (this.constellation && this.constellation.clip == clip) return;
		this.closeConstellation();

		let groups = vowelGroups(clip);
		if (!groups.length) return;

		let overlay = this.element.querySelector('.overlay');
		let origin = this.position(
			parseFloat(clip.marker.getAttribute('data-pitch')),
			parseFloat(clip.marker.getAttribute('data-resonance'))
		);
		let container = div({'class': 'constellation'});
		container.style.setProperty('--clip-color', clip.color || 'black');
		container.addEventListener('mouseenter', () => clearTimeout(this.constellationCloseTimer));
		container.addEventListener('mouseleave', () => this.scheduleConstellationClose());

		// Every dot starts at the clip marker and moves to its target once
		// it's in the DOM, so the constellation visibly expands.
		let dots = [];
		for (let group of groups) {
			let groupPosition = this.position(group.pitch, group.resonance);

			let instances = group.instances.map(instance => {
				// The word shows while it plays. (Text, not HTML: span() would
				// parse it.)
				let label = span('', {'class': 'vowel-label'});
				label.textContent = instance.word;
				let dot = div({'class': 'vowel-instance'}, [label]);
				dot.style.transform = groupPosition;
				container.appendChild(dot);
				return {element: dot, target: this.position(instance.pitch, instance.resonance)};
			});

			let vowelDot = div({
				'class': 'vowel-dot',
				'title': `${group.label}: average of ${group.instances.length}, `
					+ `${Math.round(group.hz)}Hz, ${Math.round(group.resonance * 100)}% resonance. `
					+ 'Click to hear each one.',
			}, [span(group.label, {'class': 'vowel-label'})]);
			vowelDot.style.transform = origin;
			let showInstances = shown => {
				for (let instance of instances) {
					instance.element.style.transform = shown ? instance.target : groupPosition;
					instance.element.classList.toggle('shown', shown);
				}
			};
			let isPlaying = () => this.vowelPlayback && this.vowelPlayback.dot == vowelDot;
			vowelDot.addEventListener('mouseenter', () => showInstances(true));
			// While its instances play, they stay out even without the pointer.
			vowelDot.addEventListener('mouseleave', () => isPlaying() || showInstances(false));
			vowelDot.addEventListener('click', () => {
				if (isPlaying()) {
					this.stopVowel();
					return;
				}
				showInstances(true);
				this.playVowel(clip, group.instances, instances.map(i => i.element), vowelDot,
					() => vowelDot.matches(':hover') || showInstances(false));
			});
			container.appendChild(vowelDot);
			dots.push({element: vowelDot, target: groupPosition});
		}

		overlay.appendChild(container);
		overlay.classList.add('constellation-open');
		clip.marker.classList.add('constellation-origin');
		container.offsetWidth;  // Apply the starting positions before animating.
		for (let dot of dots) dot.element.style.transform = dot.target;

		this.constellation = {clip: clip, element: container, dots: dots, origin: origin};
	}

	// Close after a delay, so the pointer can cross the gap between the
	// clip marker and the constellation's dots.
	// It stays open while a vowel plays and closes once it's done.
	scheduleConstellationClose() {
		clearTimeout(this.constellationCloseTimer);
		this.constellationCloseTimer = setTimeout(() => {
			if (this.vowelPlayback) {
				this.scheduleConstellationClose();
			} else {
				this.closeConstellation();
			}
		}, 800);
	}

	// Play the word of each of a vowel's instances, in the order they were
	// spoken, highlighting the one that's playing. onStop runs when it finishes or
	// is stopped.
	playVowel(clip, instances, elements, dot, onStop) {
		this.stopVowel();
		globalState.set('playing', false);
		let playback = {dot: dot, sources: [], timers: [], elements: elements, onStop: onStop};
		this.vowelPlayback = playback;
		dot.classList.add('playing');

		decodeClipAudio(clip).then(buffer => {
			if (this.vowelPlayback != playback) return;
			let context = vowelAudioContext;
			context.resume();
			let order = instances.map((instance, index) => index)
				.sort((a, b) => instances[a].start - instances[b].start);
			let when = context.currentTime + .05;
			for (let index of order) {
				let instance = instances[index];
				let start = Math.max(0, instance.wordStart - VOWEL_PADDING);
				let end = Math.min(buffer.duration, (instance.wordEnd == null ? buffer.duration : instance.wordEnd) + VOWEL_PADDING);
				let duration = Math.max(end - start, 2 * VOWEL_FADE);

				let gain = context.createGain();
				gain.gain.setValueAtTime(0, when);
				gain.gain.linearRampToValueAtTime(1, when + VOWEL_FADE);
				gain.gain.setValueAtTime(1, when + duration - VOWEL_FADE);
				gain.gain.linearRampToValueAtTime(0, when + duration);
				gain.connect(context.destination);
				let source = context.createBufferSource();
				source.buffer = buffer;
				source.connect(gain);
				source.start(when, start, duration);
				playback.sources.push(source);

				let delay = (when - context.currentTime) * 1000;
				playback.timers.push(setTimeout(() => {
					for (let element of elements) element.classList.remove('current');
					elements[index].classList.add('current');
				}, delay));
				when += duration + VOWEL_GAP;
			}
			playback.timers.push(setTimeout(() => this.stopVowel(),
				(when - VOWEL_GAP - context.currentTime) * 1000));
		}).catch(error => {
			console.error('Could not play the vowel:', error);
			if (this.vowelPlayback == playback) this.stopVowel();
		});
	}

	stopVowel() {
		let playback = this.vowelPlayback;
		if (!playback) return;
		this.vowelPlayback = null;
		for (let source of playback.sources) source.stop();
		for (let timer of playback.timers) clearTimeout(timer);
		for (let element of playback.elements) element.classList.remove('current');
		playback.dot.classList.remove('playing');
		playback.onStop();
	}

	closeConstellation() {
		clearTimeout(this.constellationCloseTimer);
		this.stopVowel();
		if (!this.constellation) return;
		let {clip, element, dots, origin} = this.constellation;
		this.constellation = null;

		this.element.querySelector('.overlay').classList.remove('constellation-open');
		if (clip.marker) clip.marker.classList.remove('constellation-origin');

		// Collapse back into the clip marker, then remove.
		element.classList.add('closing');
		for (let dot of dots) dot.element.style.transform = origin;
		setTimeout(() => element.remove(), 250);
	}

	getClipById(id) {
		for (let marker of $$('.marker')) {
			if (marker.getAttribute('data-id') == id) {
				return marker;
			}
		}
	}

	addMarker(pitch, resonance, label, ratings) {
		let newMarker;
		this.element.querySelector('.overlay').appendChild(
			 newMarker = button(label || ' ', {
				'class': 'marker', 
				'data-pitch': pitch,
				'data-resonance': resonance,
			}, [
				div({'class' : 'infobox'}, ratings == null ? [] : [
					 div({'class':'ratings-bar'}, [
							'strongly-disagree', 'disagree',
							'agree', 'strongly-agree'
						].map((e, i) => span(
							ratings[i] > .14 ? this.percent(ratings[i]) : ' ', 
							{'class': e, style: `width: ${this.percent(ratings[i])}`}
						))
					)
				])
			])
		)
		let vg = this;
		let showDetails = evt => {
			vg.update(newMarker);
		}
		newMarker.addEventListener('mouseover', showDetails);
		newMarker.addEventListener('click', showDetails);
		
		this.update(newMarker);
		
		return newMarker;
	}

	// Set visual positioning of markers and labels
	// to match the values in `data-pitch` and `data-resonance`.
	update(marker) {
		let overlay = $('.overlay');

		let pitch     = parseFloat(marker.getAttribute('data-pitch'));
		let resonance = parseFloat(marker.getAttribute('data-resonance'));

		let translateX = `${Math.round(overlay.clientWidth * resonance)}px`;
		let translateY = `${Math.round(overlay.clientHeight * (1-pitch))}px`;
		let markerTranslateY = `${-Math.round(overlay.clientHeight * pitch)}px`;
		let hairTranslateY = `${Math.round(overlay.clientHeight * (1 - pitch))}px`;
		marker.style.transform = `translate(${translateX}, ${translateY})`;


		// Update the hairlines and labels
		this.xHairline.style.border = '1px solid red';
		
		let previewClip = globalState.get('previewClip');

		if (previewClip && previewClip.marker && marker == previewClip.marker) {
			this.xValueLabel.style.transform = `translate(${translateX}, 0px)`;
			this.yValueLabel.style.transform = `translate(0px, ${markerTranslateY})`; 

			// Doesn't move unless there's a delay
			let hairx = this.xHairline;
			let hairy = this.yHairline;
			setTimeout(() => {
				$('.x.hairline').style.transform = `translate(${translateX}, 0px)`;
				$('.y.hairline').style.transform = `translate(0px, ${hairTranslateY})`;
			}, 1);

			this.xValueLabel.innerHTML = `${Math.round(resonance * 100)}%`;
			this.yValueLabel.innerHTML = `${Math.round(
				this.pitchLowerBoundHz + pitch * this.pitchRange
			)}Hz`;

			this.yHairline.style.opacity = '1';
			this.yValueLabel.style.opacity = '1';
			this.xHairline.style.opacity = '1';
			this.xValueLabel.style.opacity = '1';
		}
	}

	/*
	preview(recordings) {
		for (recording of recordings) {
			let el = document.createElement('div');
			let vg = this;
			el.addEventListener('click', evt => {
				vg.play(recording);
				vg.preview(recordings);
			})
		}
	}
	*/

	/* Color manipulation */
	lighten(color, proportion) {
		return proportion >= 0 
		? { r: color.r + (255 - color.r) * proportion,
			g: color.g + (255 - color.g) * proportion,
			b: color.b + (255 - color.b) * proportion, }
		: { r: color.r - color.r * -proportion,
			g: color.g - color.g * -proportion,
			b: color.b - color.b * -proportion, }
	}
	blend(color1, color2, amount) {
		return {
			r: color1.r * (1 - amount) + color2.r * amount,
			g: color1.g * (1 - amount) + color2.g * amount,
			b: color1.b * (1 - amount) + color2.b * amount,
		}
	}

	percent(x) {
		return Math.floor(x * 100) + '%';
	}
}

for (let graph of document.querySelectorAll('voice-graph-2d')) {
	graph.voiceGraph = new VoiceGraph(graph);
}

