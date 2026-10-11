# Roadmap

Ideas for the project and the work each one needs. Items marked
**(verify)** are assumptions that haven't been checked yet.

## 1. Spectrogram with aligned phones and transcript

Show a spectrogram of the clip in the browser, with MFA's phone and word
boundaries drawn over it and the transcript underneath, so people can
quickly find and replay any part of a recording.

### What we have

- MFA's TextGrid has start and end times for every word and phone,
  silences included, at 10 ms resolution.
- The browser already has each clip's audio as a data URL (`clip.audio`).
  This includes the example clips in `resources/*.json`. Their audio is
  Ogg, despite being labelled `audio/wav`.
- Each phone has F0-F3 measured at its midpoint, plus its class
  (vowel/sonorant/obstruent; see `phone_class()` in
  `acousticgender/library/phones.py`).

### Backend

- [ ] Output phone and word **end** times. `textgrid-formants.praat` reads
      them but only prints start times, and `phones.parse()` only keeps
      starts. The frontend currently infers the end from the next phone's
      start, which won't work for the last one.
- [ ] Optionally output pitch and formant **tracks** (e.g. every 10 ms)
      rather than one midpoint sample per phone, to draw continuous
      contours over the spectrogram. This makes responses bigger; consider
      a coarser step or a separate request.
- [ ] Stored clips (examples and users' saved clips) don't have end times.
      Either derive them on load (start of the next phone; last phone ends
      at the audio's end) or regenerate the examples (the source audio is
      embedded in the JSON, so it's possible).

### Frontend

- [ ] Decode the clip audio with `AudioContext.decodeAudioData`.
- [ ] Compute the spectrogram (short-time FFT, ~25 ms window, ~10 ms hop to
      match MFA's frames), via an FFT in JS or `OfflineAudioContext` +
      `AnalyserNode`. Cache the result per clip.
- [ ] Render to a canvas: time on x, frequency on y (0-5 kHz covers
      F1-F3), with a perceptual color map that works in light and dark
      themes.
- [ ] Overlay phone boundaries and labels, colored by class.
- [ ] Transcript row underneath: words placed at their aligned times.
- [ ] Overlay the measured F1-F3 and pitch points (midpoints today,
      contours if the backend provides tracks).
- [ ] Sync with playback: a cursor at `playbackTime`, and click a phone
      or word to seek there.
- [ ] Link to the voice graph: hovering a phone highlights its dot, and
      hovering a constellation instance highlights its span.
- [ ] Horizontal zoom and scroll for long clips; layout for narrow screens.

### Open questions

- Where does it go in the layout: under the player, in the details tab, or
  in its own panel?
- Should it show the processed audio MFA aligned (16 kHz, noise-reduced)
  or the original recording? The times match either way, but they look
  different.

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
- [ ] Constellation on touch screens (no hover).
