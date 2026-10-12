# voice-spectrogram

Web components for looking at speech:

- `<voice-spectrogram>`: a recording's spectrogram with rows of aligned
  words and phones underneath, a playback cursor, click-to-seek, zoom and
  scroll.
- `<voice-live-spectrogram>`: a scrolling spectrogram of a live stream (the
  microphone while recording), with the pitch drawn over it.

They share the spectrogram code.

No framework and no dependencies: plain ES modules that define custom
elements, so they work in plain HTML, React/Next.js, Vue, Svelte and so on.
The elements hold no application state: the host sets properties and
listens for events.

Status: early. Written for the gender voice visualization app and meant to
be reusable elsewhere.

## License

MIT (see `LICENSE`). This folder is licensed separately from the rest of the
repository, which is AGPL-3.0: nothing here is taken from the app's code,
and the app only uses it. The magma and viridis colour maps are from
matplotlib, whose authors dedicated them to the public domain (CC0).

## Files

- `voice-spectrogram.js`: the `<voice-spectrogram>` element.
- `voice-live-spectrogram.js`: the `<voice-live-spectrogram>` element.
- `spectrogram.js`: computing and painting spectrograms (no DOM; usable in
  a worker).
- `pitch.js`: pitch estimation (YIN), for the live view.
- `demo.html`: a demo; serve the folder with any static server.

## `<voice-spectrogram>`

```html
<voice-spectrogram max-frequency="5000" colormap="magma"></voice-spectrogram>
<script type="module">
  import './voice-spectrogram.js';
  const view = document.querySelector('voice-spectrogram');
  view.audio = audioBuffer;            // or {samples: Float32Array, sampleRate}
  view.words = [{start: 0.25, end: 0.45, label: 'my'}, ...];
  view.phones = [{start: 0.25, end: 0.35, label: 'M', kind: 'sonorant'}, ...];
  view.currentTime = 1.2;              // cursor; null hides it
  view.addEventListener('seek', e => player.currentTime = e.detail.time);
</script>
```

### Properties

| Property | Type | |
|---|---|---|
| `audio` | `AudioBuffer` or `{samples, sampleRate}` | The recording. Stereo is mixed to mono. |
| `words`, `phones` | `[{start, end, label, kind?}]` | Aligned intervals, in seconds. An empty label draws a blank interval (silence). `kind` (e.g. `vowel`) is exposed as `data-kind` for styling. |
| `currentTime` | number or `null` | Draws the cursor and highlights the word and phone under it. |
| `duration` | number (read-only) | The recording's length. |
| `viewStart`, `viewEnd` | number (read-only) | The time range shown. Change it with `setView(start, end)` (`end` null keeps the length). |
| `pitchTrack` | `[{time, hz}]` | The pitch drawn over the spectrogram (`hz` null when unvoiced). Computed from the audio (YIN, as the live view) unless you set your own, e.g. from a more accurate analysis. |
| `showPitch` | boolean (read-only) | Whether the pitch is drawn (see `show-pitch`). |

### Attributes

| Attribute | Default | |
|---|---|---|
| `max-frequency` | `5000` | Top of the frequency axis, Hz. |
| `window-length` | automatic | Analysis window, s. By default it follows the scale: up to 2 kHz, 0.025 s ("narrowband", ~52 Hz resolution, separate harmonics); above, 0.005 s ("broadband", ~260 Hz, formants). Set it to fix the window. |
| `show-pitch` | automatic | `on` or `off`; by default the pitch is drawn at scales up to 2 kHz. |
| `dynamic-range` | `70` | dB below the loudest point that still shows. |
| `colormap` | `magma` | `magma` or `viridis` (dark pages), `gray` (light pages, like Praat). |
| `view-duration` | whole recording | Seconds shown at once; longer recordings scroll. |

### Zooming and scrolling

Drag the spectrogram, scroll horizontally (or shift+wheel), or click/drag
the overview strip under the rows to move through the recording; ctrl+wheel
(or a trackpad pinch) zooms around the pointer. Ctrl+wheel over the
frequency axis changes the frequency scale instead (fires `scalechange`).
Plain vertical scrolling is left to the page. The view follows `currentTime`, paging along so the cursor
stays in sight.

The defaults follow Praat's spectrogram (Gaussian window, +6 dB/octave
pre-emphasis). Each analysis is computed once, when first needed (the
narrowband one from audio decimated to ~16 kHz, up to 2 kHz; the broadband
one up to 5 kHz), so moving between scales afterwards only redraws.

### Events

`render`: a new spectrogram has been drawn. Computing waits until the
element is visible (it has a size) and runs once for several changes in a
row, so setting `audio` on a hidden element costs nothing until it's shown.

`viewchange`: the time range shown changed; `detail` is `{start, end}`.

`scalechange`: the user changed the frequency scale (ctrl+wheel over the
axis); `detail` is `{maxFrequency}`.

`seek`: the user clicked the spectrogram or an interval. `event.detail` is
`{time, segment}`, where `segment` is the clicked word or phone
(`{tier: 'word' | 'phone', start, end, label, ...}`) or `null`. The element
doesn't move its own cursor; set `currentTime` in response.

### Styling

CSS custom properties on the element (or any ancestor):
`--vs-height` (spectrogram height, default 200px), `--vs-tier-height`,
`--vs-axis-width`, `--vs-background`, `--vs-text`, `--vs-border`,
`--vs-hover`, `--vs-cursor`, `--vs-current` and `--vs-current-text`
(highlighted interval), `--vs-vowel`, `--vs-pitch`, `--vs-overview` and
`--vs-overview-height`. Parts for `::part()`: `plot`, `canvas`, `axis`,
`cursor`, `words`, `phones`, `overview`.

## `<voice-live-spectrogram>`

```html
<voice-live-spectrogram max-frequency="1000"></voice-live-spectrogram>
<script type="module">
  import './voice-live-spectrogram.js';
  const live = document.querySelector('voice-live-spectrogram');
  startButton.onclick = async () => {
    live.clear();
    live.stream = await navigator.mediaDevices.getUserMedia({audio: true});
  };
  stopButton.onclick = () => live.stream = null;   // the picture stays
  live.addEventListener('pitch', e => console.log(e.detail.hz));
</script>
```

Set `stream` from a user gesture (e.g. the click that starts recording):
browsers only start audio processing after one. The element only listens;
it doesn't play the stream or stop its tracks.

The audio is decimated to about 16 kHz and analysed every 10 ms: a
spectrogram column (computed up to 5 kHz, so changing `max-frequency`
rescales instantly without losing what's drawn) and a pitch estimate (YIN,
drawn as dots on the same frequency axis, and shown as a number). The pitch
is for display; it can differ from Praat's, especially at voicing
boundaries.

| Property / method | |
|---|---|
| `stream` | A `MediaStream` to analyse, or `null` to stop. |
| `pitch` | The latest pitch in Hz, or `null` (unvoiced or stopped). |
| `maxFrequency` | The top of the scale (read-only; set the attribute). |
| `clear()` | Forget what's been drawn. |

| Attribute | Default | |
|---|---|---|
| `max-frequency` | `1000` | Top of the frequency axis, Hz (100–5000). |
| `window-length` | `0.025` | Analysis window, s. Longer than `<voice-spectrogram>`'s, so the harmonics separate. |
| `dynamic-range` | `60` | dB below the loudest recent sound that still shows. |
| `duration` | `5` | Seconds visible. |
| `min-pitch`, `max-pitch` | `75`, `600` | Pitch search range, Hz. |
| `colormap` | `magma` | As for `<voice-spectrogram>`. |

Events: `pitch` (every 10 ms; `detail` is `{time, hz}`, `hz` null when
unvoiced), `scalechange` (the user changed the scale with ctrl+wheel or a
pinch; `detail` is `{maxFrequency}`), `error` (couldn't start; `detail` is
the error). CSS: as for `<voice-spectrogram>`, plus `--vs-pitch` (the dots
and the number) and `--vs-plot-background`; parts `plot`, `canvas`, `axis`,
`readout`.

## Using it from Next.js

The modules can be imported during server-side rendering (nothing runs
there); the element is defined when the module loads in the browser. Use it
from a client component, and set properties through a ref: that works in
React 18 and 19, and doesn't depend on the element being defined before
React first renders it.

```jsx
'use client';
import {useEffect, useRef} from 'react';

export default function Spectrogram({audio, words, phones, currentTime, onSeek}) {
  const ref = useRef(null);
  useEffect(() => { import('voice-spectrogram'); }, []);
  useEffect(() => {
    const view = ref.current;
    Object.assign(view, {audio, words, phones, currentTime});
  }, [audio, words, phones, currentTime]);
  useEffect(() => {
    const view = ref.current;
    const listener = event => onSeek?.(event.detail);
    view.addEventListener('seek', listener);
    return () => view.removeEventListener('seek', listener);
  }, [onSeek]);
  return <voice-spectrogram ref={ref} colormap="magma" />;
}
```

With TypeScript, declare the tag once:

```ts
declare module 'react' {
  namespace JSX {
    interface IntrinsicElements {
      'voice-spectrogram': React.DetailedHTMLProps<React.HTMLAttributes<HTMLElement>, HTMLElement> & {
        colormap?: string; 'max-frequency'?: number; 'window-length'?: number; 'dynamic-range'?: number;
      };
    }
  }
}
```

To install it into another project before it's published, point a
dependency at this folder or a git URL, e.g.
`"voice-spectrogram": "file:../gender-voice-visualization/components/voice-spectrogram"`.

## Limits and plans

- The spectrogram is computed on the main thread: ~0.2 s for 8 s of 44.1 kHz
  audio. Long recordings use a coarser time step (at most 8000 columns).
  Moving it into a worker is planned.
- No pinch-zoom on touch screens yet (dragging scrolls).
- The YIN pitch sometimes jumps an octave up (locking onto the second
  harmonic) for a few frames. Supplying `pitchTrack` from a Praat-style
  analysis avoids it.
- Planned: formant overlays.
