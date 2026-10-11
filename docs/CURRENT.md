# Current work

What we're working on right now, kept up to date as work happens. The
longer-term plan is in [ROADMAP.md](ROADMAP.md).

## Goal: voicemeasure, Praat's pitch and formant analysis in Rust

The fork is moving all processing into the browser. Praat (pitch and
formants at each phone's midpoint, `textgrid-formants.praat`) must be
replaced by code that runs there and produces the same numbers, since
`stats.json` was built from Praat's measurements. `voicemeasure/` is a Rust
crate (compilable to WASM) reimplementing the two analyses the app uses,
from Praat's published documentation, not its GPL source. Praat 6.4.06 in
the Docker image is the reference.

- [x] **1. Reference harness.** `voicemeasure/reference/dump_tracks.praat`
      dumps every formant and pitch frame from Praat; `examples/dump_tracks.rs`
      writes voicemeasure's in the same format; `reference/compare.py`
      compares them. Praat's frame layout follows its documented rule
      (centred frames): formants every 6.25 ms with a 50 ms window, pitch
      every 10 ms with a 40 ms window. `frames.rs` reproduces both exactly.
- [x] **2. Formants:** `To Formant (burg): 0, 5, 5000, 0.025, 50`.
      Resample to 10 kHz (FFT low-pass, then windowed sinc), pre-emphasis
      from 50 Hz, Gaussian-like window (2 × 25 ms), Burg LPC of order 10,
      polynomial roots → frequencies and bandwidths, drop those below 50 Hz
      or above 4950 Hz. On the test clip (26 s, 4213 frames):
      - frame times identical; same number of formants in 96.8% of frames;
        median |difference| F1 0.11, F2 0.22, F3 0.38 Hz.
      - **at vowel midpoints** (what the app uses; 97 vowels): median
        |difference| F1 0.05, F2 0.09, F3 0.18 Hz; largest 4.5, 8.4,
        10.1 Hz.
      - larger differences are in near-silent frames (median −85 dB) with
        very broad bandwidths (median 630 Hz), i.e. not real formants.

      Which samples Praat's window covers isn't documented; of the
      placements tried, `centre - N/2 + 1 ..= centre + N/2` matched best
      (median F1 difference 0.11 Hz, vs 0.29-0.83 Hz for the others).

      **On the 21 example clips** (`voicemeasure/reference/check_examples.py`;
      each clip's audio decoded to one 16 kHz WAV that both tools analyse,
      compared at its stored phone midpoints, 1475 vowels):

      | | median | within 1 Hz | within 10 Hz | worst |
      |---|---|---|---|---|
      | F1 | 0.11 Hz | 93.2% | 99.1% | 382 Hz |
      | F2 | 0.24 Hz | 83.3% | 98.2% | 879 Hz |
      | F3 | 0.36 Hz | 75.0% | 96.4% | 1199 Hz |

      For scale, today's Praat pipeline differs from the values stored in
      the clips in 2021 by a median 3 / 6 / 9 Hz.

      The large differences come from **very broad "formants"** (bandwidths
      of 1000-7700 Hz): numerically fragile poles that tiny differences move
      by hundreds of Hz, or make appear on one side only, which renumbers
      every formant above them. 46 of the 698 frames around vowel midpoints
      (6.6%) disagree by more than 20 Hz or in formant count.

      **Effect on what the app shows** (running `resonance.py` on Praat's
      vs voicemeasure's formants, everything else identical): clip median
      resonance differs by a median 0.12 percentage points, at most 2.2
      (`chuck`, 31.4% vs 33.6%). Per vowel (1288): median 0.018 points; 11
      vowels differ by more than 1 point, 3 by more than 5, and 1 (in
      `wina`) by 100 points (a renumbered vowel whose resonance is clamped
      to the opposite end).
- [ ] **3. Pitch:** *Next.* `To Pitch: 0, 75, 600` (autocorrelation method,
      Boersma 1993): candidates per frame, then a Viterbi path with
      Praat's default costs.
- [ ] **4. Measurements at phone midpoints**, linear interpolation as
      `Get value at time ... Hertz Linear`; compare with Praat on the test
      clip and the example clips, then on per-clip resonance and pitch.

## Goal: harden `serve.py` for a small real deployment

A friend may host the app from the Docker image. `serve.py` began as a dev
server, so make it safe and robust enough for that before packaging it.

- [x] **Concurrency.** `ThreadingHTTPServer`, with uploads serialized by a
      lock (the aligner and MFA's working directory aren't safe to share).
      Page loads during an upload: 2-12 ms (were ~2 s). Three simultaneous
      uploads all succeed, processed in turn (2.0, 3.7, 5.4 s).
- [x] **Non-root user.** The image runs as its `ubuntu` user (uid 1000).
      The `mfa align` fallback still works (it used to drop to `nobody`).
- [x] **Error responses without internals.** 422 with a user-facing message
      when the recording can't be read as audio or matched to the
      transcript; 400 for malformed requests; 500 "Processing failed" for
      bugs. Each carries a random reference that's also in the server log,
      next to the full error.
- [x] **Request limits.** Uploads over 25 MB get 413, no Content-Length 411.
      Connections idle for 60 s mid-request are dropped; a stalled request
      doesn't block others.
- [x] **Remove debug output.** No more environment dump at startup or
      per-request filename prints.
- [x] **`X-Content-Type-Options: nosniff`** on every response.

Not yet: the frontend still shows its generic alert for every failure;
showing the server's message is part of the roadmap's JSON-errors item.

Later: check uploads are audio before ffmpeg parses them; the pre-existing
`innerHTML` use of clip titles and transcripts in the frontend (a crafted
clip file can run script); a self-contained image to give to the host
(the current one bind-mounts the source); HTTPS in front of it, which
in-browser recording requires.

## Done: phonealign, a fast replacement for `mfa align`

Align one recording to its transcript in well under a second by keeping
the model loaded and calling Kaldi (via `kalpy`) directly, producing the
same result as `mfa align`. See [phonealign/README.md](../phonealign/README.md)
and item 3 of the roadmap.

Test clip: `rec/3306064823` (26 s, the rainbow passage). Its TextGrid from
`mfa align` (`output/recording.TextGrid`) is the reference output.

## Steps

- [x] **1. Find the `kalpy` calls `mfa align` makes for one utterance.**
      MFA already has a single-file path, `mfa align_one`
      (`montreal_forced_aligner/command_line/align_one.py`), with no corpus
      database, job splitting or queues. Its sequence:
      1. `LexiconCompiler(...)` + `load_pronunciations()` +
         `create_fsts()`: pronunciation FSTs from the dictionary, with
         silence settings from the acoustic model's parameters.
      2. A tokenizer (`generate_language_tokenizer(language)`) and
         `tokenize_utterance_text()` to normalize the transcript.
      3. `kalpy.utterance.Utterance(Segment(wav), text)` +
         `.generate_mfccs(acoustic_model.mfcc_computer)`.
      4. `CmvnComputer().compute_cmvn_from_features()` + `utt.apply_cmvn()`.
      5. `KalpyAligner(acoustic_model, lexicon_compiler, beam=...,
         ...).align_utterance(utt)` → word and phone intervals.
      6. `HierarchicalCtm.export_textgrid()`.

      `mfa align` does a single pass too: it disables speaker adaptation
      (fMLLR) before aligning, even though the model supports it.
- [x] **2. Reproduce the test clip's TextGrid with those calls**, outside
      MFA, and compare it to the reference.
      `phonealign/tools/kalpy_align.py` makes the same calls as
      `align_one`, keeping the model loaded across runs. Its first run
      reproduces the `mfa align_one` CLI's TextGrid exactly (267/267 phones,
      92/92 words). `phonealign/tools/compare_textgrids.py` compares two
      TextGrids' intervals, ignoring formatting.

      Since exact reproduction of `mfa align` is impossible (see notes),
      results are judged against MFA's own run-to-run variation, measured on
      the test clip (~265 phones):

      | | Pronunciation differences | Boundaries moved | Moved >10 ms |
      |---|---|---|---|
      | `mfa align_one` vs `mfa align` (reference) | 1 | 7 | 0 |
      | Kaldi dither runs vs each other (**MFA's variation**) | 0 | 10-14 | 2-3 |
      | Kaldi dither runs vs reference | 1 | 7-19 | 0-3 |
      | dither off vs reference | 6 | 39 | 16 |
      | **seeded dither** vs reference | 1 | 18-20 | 3-5 |
      | seeded dither, different seeds vs each other | 0 | 13 | 5 |
      | seeded dither, same seed twice | 0 | 0 | 0 |

      **Decision: seeded dither.** Add the dither noise ourselves (Gaussian,
      standard deviation 1 in 16-bit units, from a fixed seed) and turn
      Kaldi's off. It's deterministic and within MFA's own variation;
      turning dither off entirely is not.
- [x] **3. Time each call** to see how close the core work gets to the
      under-a-second target. First with `kalpy_align.py`, which builds a
      per-transcript dictionary and aligner on every request (as the backend
      does today). Per request, warm, on the test clip (26 s of audio):

      | Step | Time |
      |---|---|
      | load pronunciations, compile lexicon, tokenize | ~5 ms |
      | MFCCs | ~13 ms (452 ms on the first call: warm-up) |
      | CMVN | <1 ms |
      | **create aligner** (`KalpyAligner(...)`) | **~200-320 ms** |
      | **align** | **~105-140 ms** |
      | total | **~300 ms** |

      One-time startup: imports ~1.8 s, loading the acoustic model ~0.56 s.

      "Create aligner" reads the model files from disk and builds a training
      graph compiler for the lexicon, so the per-transcript dictionary forces
      it on every request. `phonealign/tools/persistent_align.py` instead
      compiles the **full** dictionary and creates the aligner **once**:

      | | Time |
      |---|---|
      | **Startup** (one-time) | **~22 s**: imports 2.0 s, model 0.6 s, load full dictionary 2.0 s, **compile lexicon FSTs 14.8 s**, create aligner 2.8 s |
      | First request | 1.3 s (warm-up: librosa's first audio load 0.7 s) |
      | **Later requests** | **140-185 ms**: align 120-160 ms, MFCCs ~15 ms, the rest ~1 ms |
      | Peak memory | **~970 MB** |

      Output is identical to the per-transcript-dictionary version (267/267
      phones, 92/92 words) and identical across requests.

      **So the alignment itself fits well within the 1 s budget.** Open
      choices for step 4:
      - Full dictionary (~150 ms/request, ~22 s startup, ~1 GB) vs
        per-transcript dictionary (~300 ms/request, little memory).
        Middle ground to try: create the `GmmAligner` once and only the
        graph compiler per request.
      - Save the compiled lexicon FSTs to disk (as `align_one` does with
        `L.fst`) to cut the 14.8 s compile from later startups.
      - Run one dummy alignment at startup to absorb the warm-up.
- [x] **4. Wrap it in the `Aligner` API described in the README.**
      **Decision (2026-10-10): per-transcript dictionary** (~300 ms/request,
      small memory) for now, rather than the full dictionary (~150
      ms/request, ~22 s startup, ~1 GB). The acoustic model is loaded once;
      the lexicon and aligner are built per request.

      `phonealign/src/phonealign/aligner.py`: `Aligner(acoustic_model,
      dictionary)` and `.align(samples, sample_rate, transcript)` returning
      word and phone `Interval`s (silence excluded), with seeded dither.
      Checked with `phonealign/tools/check_aligner.py` on the test clip:
      - output identical to the seeded-dither experiment (267/267 phones,
        92/92 words in the TextGrid) and across repeated requests
      - startup ~4.1 s (imports, model, reading the dictionary); first
        request ~0.4-0.6 s, then **~310-330 ms**
      - a transcript that doesn't fit the audio raises `AlignmentError`
- [x] **5. Use it in the backend in place of `align.sh`.** CGI can't keep
      the `Aligner` loaded (each request is a fresh process), so `serve.py`
      now loads it at startup and processes uploads to `backend.cgi`
      itself. If phonealign fails to load, uploads still go through
      `backend.cgi` and `mfa align`.
      - `acousticgender/library/analysis.py`: `analyze()`, the shared
        request logic, used by both `backend.cgi` and `serve.py`.
      - `preprocessing.process()` takes an optional `aligner`; alignment is
        split into `align_with_phonealign()` and `align_with_mfa()`.
      - `backend.cgi` is unchanged in behavior; production doesn't use
        `serve.py`, so it keeps running `mfa align` for now.

      Results on the test clip, server-side (in `serve.py`'s log):

      | | Before (`mfa align` per request) | Now |
      |---|---|---|
      | 26 s recording | ~7.7 s | **~2.0-2.6 s** |
      | Browser, Add Clip to clip shown | ~8 s | **~4 s** |
      | 1.2 s clip that fails alignment | ~6.3 s | **~0.5 s** |

      Where the ~2 s goes now (profiled): Praat ~0.6-0.7 s, ffmpeg (4
      runs) ~0.45 s, phonealign ~0.3 s, sox ~0.18 s, `phones.parse`
      0.13-0.26 s (re-reads `cmudict.txt` every request), upload parsing
      ~20 ms. The analysis time varied between 1.6 and 2.5 s across
      batches; I haven't found why.

## Next

- The remaining time is in the rest of the pipeline, not alignment (see
  roadmap item 3): run Praat in process (parselmouth), replace the ffmpeg
  and sox subprocesses, and load `cmudict.txt` once.
- Production still runs `backend.cgi`; using phonealign there needs a
  persistent server in production too.
- Optional: keep the model-only parts of the aligner loaded to cut
  phonealign from ~300 to ~150 ms.

## Notes and surprises

- **2026-10-10: Exact reproduction of `mfa align` isn't possible, because
  feature extraction is random.** The acoustic model sets MFCC
  `dither: 1`: Kaldi adds small random noise to the audio before
  computing features, and its random generator isn't reseeded per call.
  Computing the same clip's features twice in one process gives different
  results; with `dither: 0` they're identical. `mfa align` only looks
  deterministic because each run is a fresh process.

  Consequences:
  - `mfa align_one` vs `mfa align` on the test clip: same words and phones
    except one pronunciation variant ("and" as `AH0` vs `AE1`), boundaries
    shifted by one 10 ms frame in three places, and an extra zero-length
    silence at the end (an export quirk). Dither is the likely cause.
  - The goal "same result as `mfa align`" needs to become "within `mfa
    align`'s own run-to-run variation", measured by aligning the same clip
    with different dither draws.
  - A long-lived aligner would give different results for the same
    recording on every request unless dither is disabled (or the generator
    reseeded per request). Plan: use `dither: 0` and check the result stays
    within that variation.
- **2026-10-10: Turning dither off made alignment noticeably worse**
  (6 pronunciation differences and 16 boundaries moved by >10 ms, vs 0 and
  2-3 for MFA's own variation). Likely the model, trained on dithered
  features, sees out-of-range log energies in quiet stretches. Seeded
  dither avoids it.
- **2026-10-10: `english_us_arpa`'s language is `Language.unknown`**, so
  `align_one` normalizes text with MFA's `SimpleTokenizer`, not spacy
  (which isn't installed). phonealign must use the same tokenizer.
- **2026-10-10: Most of MFA's "real work" was warm-up.** MFCCs took
  ~450 ms on the first call but ~13 ms after, so the 0.6 s MFCC stage in
  `mfa align` was mostly one-off cost, not computation.
- **2026-10-11: Uploads to `serve.py` were silently truncated.**
  `CGIHTTPRequestHandler` makes the request stream unbuffered (to pass it
  to CGI processes), so one `read(n)` can return less than `n` bytes. A
  425 KB upload arrived as 122 KB and alignment failed. `serve.py` now
  reads in a loop. The same unbuffered stream is probably why
  `cgi.FieldStorage` took ~750 ms to parse an upload (now ~20 ms with the
  `email` parser).
- **2026-10-11: Loading the aligner as root broke the `mfa align`
  fallback.** `serve.py` runs as root and loading the model unpacks it
  under `/opt/mfa`; `mfa align` runs as `nobody` (the CGI user) and
  couldn't write there. `serve.py` now loads with a umask of 0, keeping
  that directory world-writable as the Dockerfile intends.
- **2026-10-11: kalpy's TextGrid export labels silence `<eps>`**, where
  `mfa align` writes `""`. The frontend detects silence by the empty label,
  so phonealign writes its own TextGrids in `mfa align`'s format.
- **2026-10-11: Praat 6.4.06 intermittently fails to create output
  files** ("Cannot create file ... this is a folder, not a file"), ~9% of
  runs (18 of 200), and succeeds when rerun. `check_examples.py` retries up
  to three times. Not the bind mount: it fails as often with all files
  inside the container. `strace` shows no failing syscall: failed and
  successful runs make the same `newfstatat(path) = ENOENT` check, and
  failed runs then report the error without ever calling `openat`.
  Likely a Praat bug that reads the stat result even when stat failed.
  Pre-creating the formant output file cut failures to 4 of 200; untested
  whether pre-creating the pitch file too removes the rest. The app's own
  Praat script writes no files, so it isn't affected. See the roadmap's
  open items for follow-up.
- **Lexicon caching in `align_one`** keys the compiled FSTs by the
  dictionary file's name (`extracted_models/dictionary/<stem>`), reusing
  them unless `--clean`. Our per-request dictionaries are all named
  `dictionary.dict`, so phonealign must not reuse that cache as is.
