# Roadmap

Ideas for the project and the work each one needs. Items marked
**(verify)** are assumptions that haven't been checked yet.

## 1. Spectrogram with aligned phones and transcript

Mostly done: `<voice-spectrogram>` (`components/voice-spectrogram/`, MIT,
reusable) in the details panel, with words and phones rows, playback
cursor, click to play from a point, zoom and scroll. See docs/CURRENT.md.

- [ ] Overlay the measured pitch and F1-F3 (midpoints today; continuous
      tracks from voicemeasure would be better).
- [ ] Link to the voice graph: hovering a phone highlights its dot, and
      hovering a constellation instance highlights its span.
- [ ] Compute in a worker (~0.7 s on the main thread for a 30 s clip).
- [ ] Open question: should it show the audio as recorded or after noise
      reduction (if that comes back)?

## 2. Run MFA in the browser

Do the whole analysis on the user's device: audio never leaves it, there's
no server cost or queue, and it works offline. Combined with on-device
speech recognition (Chrome 139+, `SpeechRecognition.processLocally`),
users could speak freely without a fixed passage.

### What the server pipeline does today

1. ffmpeg: decode, silence detection, resample to 16 kHz mono.
2. sox: noise profile from the silences, then noise reduction.
3. MFA (`mfa align`): Python orchestration around compiled Kaldi (via the
   `kalpy` bindings: 22 `libkaldi-*.so` plus OpenFst). For one clip, about
   2.2 s of actual work: MFCC features, graph compilation, GMM alignment.
4. Praat (`textgrid-formants.praat`): pitch and F1-F3 at each phone's
   midpoint.
5. `phones.py` + `resonance.py`: z-scores against `stats.json`, resonance,
   clip statistics.

Every step needs a browser equivalent.

### Work

- [ ] **Feasibility spike.** Running MFA itself under Pyodide looks
      unlikely: it relies on multiprocessing, SQLite/SQLAlchemy and numba
      (via librosa) **(verify)**. The more promising route is to compile
      just the Kaldi pieces we use, plus OpenFst, to WebAssembly with
      Emscripten, and drive them from JS. Prior art: Kaldi-based speech
      recognition has been compiled to WASM before (e.g. vosk-browser)
      **(verify)**.
- [ ] **Minimal alignment pipeline.** Write down exactly which Kaldi calls
      `kalpy` makes for `align` (features, CMVN, training graph
      compilation, GMM alignment, CTM extraction). The long-lived
      server-side aligner (below) is a good place to build this, since it
      would call `kalpy` directly and serve as the reference
      implementation.
- [ ] **Model delivery.** The `english_us_arpa` acoustic model is a 92 MB
      zip and the dictionary is 7 MB. Measure what alignment actually needs
      from the model, compress it, download it once and cache it (Cache
      API/IndexedDB), and show download progress. The dictionary can be
      trimmed to the fixed passages' words, but freeform speech needs the
      full dictionary or G2P for unknown words.
- [ ] **Audio preprocessing.** `decodeAudioData` + `OfflineAudioContext`
      for decoding and resampling. Decide whether sox's noise reduction is
      needed; if so, reimplement spectral subtraction or drop it and
      measure the effect on alignment.
- [ ] **Pitch and formants.** Replace Praat: a pitch tracker
      (autocorrelation, as Praat's `To Pitch` uses) and Burg LPC formants.
      Validate against Praat's numbers on the example clips before
      switching, since `stats.json` was built from Praat's measurements.
- [ ] **Scoring.** Port `phones.py`/`resonance.py` to JS (small).
- [ ] **Performance.** Run alignment in a Web Worker; measure on low-end
      laptops and phones.
- [ ] **Licensing.** MFA is MIT and Kaldi/OpenFst are Apache 2.0. Check the
      pretrained model's license **(verify)**. Praat is GPL, so don't port
      its code unless the project is fine with GPL; reimplement the
      algorithms from their published descriptions instead.
- [ ] **Fallback.** Keep the server path for browsers or devices that can't
      run it.

## 3. Full audio pipeline in under a second

Goal: under 1 s from pressing **Add Clip** to the clip appearing on the
graph, for a ~25 s recording, measured end to end in the browser on the
production server. Today it's ~8 s (it was ~66 s before the dictionary and
queue-polling fixes).

### Where the time goes now (26 s clip, dev machine)

| Step | Time | Mostly |
|---|---|---|
| MFA process startup and shutdown | ~3.8 s | Python imports (2.0 s), database setup (~0.9 s), shutdown (~0.6 s), `conda activate` (0.3 s) |
| MFA stages | ~2.2 s | MFCCs 0.6 s, corpus split 0.4 s, alignment 0.3-0.4 s, quality analysis 0.2-0.3 s, the rest ≤0.2 s each |
| CGI, upload, response | ~0.7 s | a fresh Python process and imports per request |
| ffmpeg + sox | ~0.5 s | five separate subprocesses |
| Praat | ~0.5 s | one subprocess |
| parse + resonance | 0.1 s | |

Almost all of it is per-request process startup and pipeline overhead, not
computation. The actual alignment is a few hundred milliseconds.

### Work

- [ ] **Persistent server instead of CGI.** A long-running app (e.g. a small
      WSGI/ASGI server) that keeps everything imported and loaded. Removes
      the ~0.7 s per-request Python startup. Python 3.15 also removes the
      `cgi` module, so this is needed eventually anyway.
- [ ] **Long-lived aligner calling `kalpy` directly** (in
      [`phonealign/`](../phonealign/README.md)). Load the acoustic
      model once and skip MFA's per-run work that a single clip doesn't
      need: the corpus database, corpus split, quality analysis and
      TextGrid export. Removes the ~3.8 s of startup and shutdown, the
      `sitecustomize.py` queue-polling workaround, and most of the stage
      overhead. Expect roughly feature extraction + graph compilation +
      alignment, likely well under 0.5 s **(verify)**. This is also the
      reference implementation for running MFA in the browser (item 2).
- [ ] **Profile the real work.** 0.6 s for MFCCs on 26 s of audio seems slow
      for Kaldi; it probably includes MFA overhead **(verify)**. Time each
      `kalpy` call on its own.
- [ ] **Audio preprocessing in process.** Replace the ffmpeg/sox
      subprocesses with in-process decoding and resampling (e.g. PyAV or
      soundfile) and a numpy implementation of silence detection and noise
      reduction, or measure whether noise reduction is needed at all.
- [ ] **Praat in process.** Use parselmouth (Praat as a Python library):
      the same algorithms, so `stats.json` stays valid, without spawning a
      process. Note that parselmouth is GPL, like Praat.
- [ ] **Smaller uploads.** Downmix to mono and resample to 16 kHz in the
      browser before uploading. MFA only uses 16 kHz anyway.
- [ ] **Concurrency.** A persistent process needs a worker pool or queue,
      with per-request working state. That also fixes the shared MFA
      working directory problem below.
- [ ] **Start before the user finishes.** Optionally upload in chunks while
      recording and align completed sentences early, so only the last
      sentence remains when they press Stop.
- [ ] **Per-stage budget and timing.** Log each stage's duration per request
      (ties in with the logging cleanup below), and add a timing check to
      catch regressions.

## 4. Opt-in bug reports with the recording

Recordings are deleted as soon as they're processed, including ones that
fail, for privacy. That leaves no way to debug a failure a user hits. Let
the user choose to send the failed recording as a bug report.

- [ ] When processing fails, offer "Send this recording to help fix it",
      with wording that says exactly what's sent (the audio and the
      transcript) and how long it's kept. Never send without that click.
- [ ] The browser already has the audio (`clip.audio`), so the report can
      re-upload it to a separate endpoint; the server doesn't need to hold
      on to anything in the meantime.
- [ ] Store reports apart from normal processing, with the error, the
      server's log line and the app version, and a retention limit (e.g.
      delete after 30 days, or once the bug is fixed).
- [ ] Decide who can access reports, and say so in the consent text.

## 5. Live spectrogram and pitch while recording

Show a scrolling spectrogram and a live pitch trace while the user records,
so they can see their voice as they speak instead of only after the clip
is analysed.

### What we have

- The recorder already has a `MediaStream` from `getUserMedia` (in
  `ui/new-clip.html`).
- voicemeasure has Praat's pitch algorithm (`To Pitch`, 75-600 Hz) in
  WASM; `vm_measure` measures a whole recording at given times, not a
  stream.
- Item 1 plans a spectrogram for finished clips; the rendering (color map,
  frequency axis, themes) should be shared.

### Work

- [ ] Tap the microphone stream with an `AudioWorklet` (or `AnalyserNode`
      for the spectrogram alone) without disturbing `MediaRecorder`.
- [ ] Scrolling spectrogram on a canvas: ~25 ms window, ~10 ms hop,
      0-5 kHz, drawn as columns arrive.
- [ ] Live pitch: either a streaming entry point in voicemeasure (pitch
      for a short buffer, e.g. the last ~100 ms) or a lightweight tracker
      (autocorrelation/YIN) for the live view. If it isn't Praat's
      algorithm, label it as approximate, since the clip's final numbers
      come from voicemeasure. Measure how far the two differ.
- [ ] Draw the pitch trace over the spectrogram and/or as a moving marker
      on the voice graph's pitch axis.
- [ ] Optionally live resonance: formants need longer windows and are noisy
      outside vowels, and scoring needs the phone (from alignment), so a
      live estimate would be rough. Decide whether it's worth showing.
- [ ] Performance: keep it under one frame per update on phones; run
      analysis off the main thread.

## 6. Play back a constellation's vowels

Clicking a vowel dot in a clip's constellation plays every instance of that
vowel from the recording, so people can hear how much it varies.

- [x] `vowelGroups()` keeps each instance's word and the word's span (to
      where the next word or silence starts; the last to the end of the
      audio).
- [x] Click a vowel dot: the word of each instance plays in the order they
      were spoken (a lone vowel is often too short to hear), with 30 ms
      either side, 15 ms fades and 350 ms between words, through Web Audio
      (decoded once per clip). The instance playing is highlighted and
      labelled with its word. Click again to stop; starting the player
      stops it too.
- [x] The constellation stays open while a vowel plays.
- [x] The details panel's transcript highlights the word being heard,
      during vowel playback and normal playback (`spokenWord` state;
      `transcriptPieces()` in `ui/util.js` matches transcript words to
      aligned ones, including the aligner's `<unk>`).
- [ ] Click a single instance to play just that one (instances ignore the
      pointer today).
- [ ] Maybe an option to hear just the vowel instead of the word.
- [ ] Move the clip's marker to the instance playing, as normal playback
      does, or show its word.
- [ ] Touch screens: there's no hover to open the constellation (see Other
      open items).

## 7. Automatic transcription

Fill in the transcript from the recording with the browser's speech
recognition (Web Speech API, `SpeechRecognition`), so users can speak
freely instead of reading a fixed passage, then check and correct the text
before analysis.

### What we have

- The transcript is a textarea in `ui/new-clip.html`, filled from the
  chosen passage or typed for "custom"; it's passed to `analyzeInBrowser`.
- voicealign aligns any transcript. Words missing from the dictionary
  become `<unk>` (spoken noise, `spn`), so they get no vowels and aren't
  measured.

### Work

- [x] **User-configured transcription endpoints** (`ui/transcription.js`):
      OpenAI-style servers (e.g. Speaches with Whisper) set up in the
      settings tab and used from the Add a Clip dialog. The rest of this
      item is about the browser's own recognition.
- [ ] **Privacy first.** In Chrome, recognition normally sends the audio to
      Google's servers; Chrome 139+ can run it on the device
      (`processLocally`, after the language pack downloads)
      **(verify)**. Safari's goes to Apple **(verify)**. Firefox has no
      `SpeechRecognition` **(verify)**. Always prefer on-device.
- [ ] **Consent for server recognition.** If on-device isn't possible, the
      first press of "Auto-transcribe" asks first: the recording is sent to
      the browser maker's speech service (name it: Google or Apple), which
      this app doesn't control, and everything else stays on the device.
      Choices: "Send it", "Not now", and a "Remember my choice" checkbox.
      - Store the choice (`transcriptionConsent`: unset / allowed / denied)
        in `localStorage`, wrapped in try/catch so a blocked storage just
        means asking again.
      - A control in the settings tab shows the current choice and lets the
        user change or reset it.
      - With "denied" remembered, the button stays visible but explains why
        it's off and links to the setting, rather than vanishing.
      - Option 2 (recognising during recording) needs this consent before
        the recording starts, not after.
      - Store it with `localSettings` (`ui/storage.js`) and add it to
        `STORED_SETTINGS`, so the "Stored on this device" panel lists it
        and can reset it.
- [ ] **"Auto-transcribe" button after recording.** Once a recording
      exists (recorded or uploaded), a button next to the transcript fills
      it in from the audio; the user then reviews it. The catch: the API
      listens to a live microphone, not a recorded blob. Ways to get there,
      best first:
      1. Pass the recording as a track: play it into a
         `MediaStreamAudioDestinationNode` and give that track to
         `recognition.start(track)` (newer Chrome **(verify)** which
         version, and whether it runs faster than real time). Works for
         uploads too.
      2. Recognise silently during recording, on the same stream as
         `MediaRecorder`, and keep the result; the button then fills it in
         instantly. Only for live recordings; costs the privacy prompt even
         if the user never presses the button, so start it only if they've
         opted in.
      Hide the button when neither works.
- [ ] **Feature detection**, decided once per page load:
      - Recognition at all: `window.SpeechRecognition ||
        window.webkitSpeechRecognition`.
      - On-device: `SpeechRecognition.available({langs: ['en-US'],
        processLocally: true})` → available / downloadable / unavailable,
        and `SpeechRecognition.install(...)` for "downloadable"
        **(verify)** the exact API.
      - Track input (option 1) can't be detected from a property, and an
        older browser silently ignores the extra argument to `start()` and
        listens to the **microphone** instead. So don't just try it: gate
        it on a related newer feature, or run a short probe with a silent
        track and check that recognition ended without a microphone
        prompt **(verify)** a reliable test.
      - Pick option 1, then option 2, then hide the button; put the result
        in one `transcriptionSupport` value the UI reads, and test each
        branch (including "unsupported") in the browser test setup.
- [ ] **Review step.** Show the recognised text for editing before
      analysis; recognition errors become alignment errors. Started:
      words the server is unsure of are marked under the transcript.
- [ ] **Normalise the text** for the dictionary: numbers ("25" → "twenty
      five"), symbols and punctuation. Highlight words that aren't in the
      dictionary so the user can fix or respell them.
- [ ] **Unknown words.** Freeform speech hits names and slang the
      dictionary lacks. Options: let the user respell, or add
      grapheme-to-phoneme conversion (MFA has G2P models; another WASM
      port) **(verify)** size and license.
- [ ] Ties in with item 2's note on freeform speech, and with item 5 (both
      tap the live microphone stream).

## Other open items

From earlier work, roughly by priority:

- [ ] Concurrent requests share MFA's working directory
      (`$MFA_ROOT_DIR/corpus`), so two at once can break each other. Give
      each request its own MFA temporary directory.
- [ ] Recorder bug: each new recording on a page adds another
      `dataavailable`/`stop` listener, so the second take uploads doubled
      audio and gets wrong results. Register the listeners once.
- [ ] Show expected processing time (~10 s) while a clip is processing.
- [ ] Return errors as JSON (`{"error": ..., "id": ...}`) instead of
      `cgitb` HTML, show the reason in the UI, and use Python `logging`
      with the clip ID instead of ad-hoc prints.
- [ ] Reject obviously bad clips early (too short, transcript words missing
      from the dictionary) before running MFA.
- [ ] Compute clip resonance/pitch statistics from vowels only. Obstruents'
      formant values are mostly artifacts, and including them compresses
      differences between voices. Discuss with the original author first.
- [ ] `console.assert` in `ui/new-clip.html` checks that `phones` is
      *empty*; it's inverted.
- [ ] Report MFA's 1 s queue polling upstream (the long-lived aligner is
      in item 3).
- [ ] Praat 6.4.06 intermittently fails to create files ("this is a
      folder, not a file") with no failing syscall; diagnosis in
      `docs/CURRENT.md`. Before reporting it upstream: confirm whether
      pre-creating every output file avoids it, and check whether a current
      Praat release still has it. Low priority, since we're replacing Praat.
- [ ] Constellation on touch screens (no hover).
- [x] The help page said clips are "sent to our server for processing"
      and not stored; updated for in-browser analysis and saved clips.
