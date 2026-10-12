# Current work

What we're working on right now, kept up to date as work happens. The
longer-term plan is in [ROADMAP.md](ROADMAP.md).

## Goal: run the whole analysis in the browser

voicealign (alignment) and voicemeasure (pitch, formants) run in
WebAssembly. Still needed to replace the server:

- [x] 1. Audio input (`ui/analysis.js`): decoded to 16 kHz mono in the
      page (`decodeAudioData` at 16 kHz, channels averaged). Recorder bug
      fixed: listeners are added once, so later takes no longer upload
      duplicated audio.
- [x] 2. Model files: `tools/setup_browser_analysis.sh` builds both WASM
      modules into `ui/wasm/` and extracts the model and dictionary from
      the Docker image into `models/` (both git-ignored); `serve.py`
      serves them plus `cmudict.txt` and `stats.json`. Loaded once per page
      by the worker, with a progress message. *Still open:* the pretrained
      model's license (it's redistributed to every visitor); HTTP caching
      across visits; shrinking ~60 MB of downloads.
- [x] **3. Scoring in JavaScript** (`ui/scoring.js`): a port of
      `phones.parse` and `resonance.compute_resonance`, from aligned words
      and phones with F0-F3 to the JSON the backend returns. Checked with
      `tests/scoring/`: `make_reference.py` runs recordings through the
      server pipeline and saves Praat's measurements and the backend's
      JSON; `check_scoring.mjs` scores the same measurements in JS and
      compares every value. **22/22 cases identical** (21 example clips +
      the test clip; relative tolerance 1e-9). The check fails all 22 when
      a weight is changed from 0.268 to 0.27 or the outlier threshold from
      2 to 2.5, so it isn't vacuous.
- [x] 4. Wiring: `ui/analysis-worker.js` (Web Worker) loads voicealign,
      voicemeasure, the model and data files once, then per clip: align,
      fill silences to rebuild the TextGrid tiers, measure F0-F3 at every
      phone's midpoint, score with `scoring.js`. `new-clip.html` analyses in
      the browser and falls back to `backend.cgi` if that fails (e.g.
      models not set up). In Chromium: first clip 3.4 s (loading), then
      **~0.4-0.6 s per clip**, with no server requests.
- [x] 5. End-to-end check: 21 example clips + test clip through the page's
      in-browser analysis vs the server's results (median pitch and
      resonance per clip):

      | | median resonance | median pitch |
      |---|---|---|
      | browser (raw audio) vs server | 1.1 pts (max 7.4) | 0.58 Hz (max 11.1) |
      | browser on the server's noise-reduced audio vs server | 0.14 pts (max 2.1) | 0.20 Hz (max 5.5) |
      | server vs itself (sox noise reduction is random) | 0.35 pts (max 1.4) | 0.00 Hz (max 4.2) |

      So the browser pipeline reproduces the server as closely as the
      server reproduces itself; the gap is the dropped noise reduction.
      **Open decision:** `stats.json` was built from noise-reduced audio.
      Options: reimplement noise reduction in the browser; use it only for
      measuring (not aligning, where it caused failures); or keep it off
      and accept the shift.

## Licenses of the reusable parts

- [x] `voicemeasure`: MIT (`LICENSE`, `license = "MIT"`, SPDX headers).
      Implemented from Praat's documentation, so no GPL code.
- [x] `voicealign`: "MIT AND Apache-2.0". MIT for our code; the five files
      ported from Kaldi's C++ (`features.rs`, `model.rs`, `tree.rs`,
      `align.rs`, `kaldi_io.rs`) stay Apache-2.0, as Kaldi's license
      requires, with headers saying so. `NOTICE` lists them and credits
      Kaldi, kalpy and MFA (MIT; `graph.rs` and `lexicon.rs` follow their
      behaviour). Checked: kalpy and MFA are MIT (their package metadata
      in the Docker image).
- [x] `components/voice-spectrogram`: MIT.
- [ ] `phonealign` (Python): still undecided.

## Goal: reusable spectrogram components (ROADMAP items 1 and 5)

Framework-free web components in `components/voice-spectrogram/`, meant
to be reused in another app (Next.js). See its README.

1. [x] Shared core (`spectrogram.js`: FFT, Praat-style Gaussian-window
       spectrogram, colour maps, painting) and `<voice-spectrogram>` for a
       recording. Checked on synthetic vowels (formant bands where they
       were synthesised) and Fern's recording (0.2 s for 8 s at 44.1 kHz).
2. [x] Words and phones rows, cursor with the current word and phone
       highlighted, `seek` events from clicks. Safe to import during
       server-side rendering; properties set before the element is defined
       still apply. 7 tests in `tests/browser/test_voice_spectrogram.py`.
3. [x] In the app's details panel, 6 s at a time: follows the player and
       a constellation's vowel playback (cursor on the vowel); clicking
       plays from there. Computes only while the details tab is visible
       and 200 ms after the selected clip settles (hovering changes it
       often). `decodeClipAudio()` moved to util.js, shared with vowel
       playback; `alignedIntervals()` converts a clip's phones. 4 tests in
       `tests/browser/test_details_spectrogram.py`.
   [x] Zoom and scroll, pulled forward from step 5 (a 30 s clip in the
       ~520 px panel was unreadable): `view-duration`, drag or shift+wheel
       to scroll, ctrl+wheel/pinch to zoom, an overview strip, paging to
       follow the cursor. 4 more component tests.
4. [x] `<voice-live-spectrogram>` in the "Record your voice" option:
       scrolling spectrogram of the microphone, 0-1000 Hz by default with
       a "Show up to" menu (500-5000 Hz) and ctrl+wheel; 25 ms window so
       harmonics separate; pitch by YIN (`pitch.js`) drawn as dots and a
       number. Columns are computed to 5 kHz so rescaling is instant.
       Checked: a gliding test voice is tracked within 2% (median); a
       300 Hz tone draws at 300 Hz; Fern's recording as a fake microphone
       gives a median 150 Hz (her stored Praat median: 152 Hz). 5
       component tests, 1 app test.
5. [ ] Pitch and formant overlays, computing in a worker, pinch-zoom on
       touch screens.
- [x] License: MIT, in the component's own `LICENSE` (the rest of the
      repository stays AGPL-3.0). It can stay in this repository; moving it
      to its own would make installing it from git easier (npm can't
      install a subfolder of a git repository).

## Goal: hear a vowel's variation from the constellation

- [x] Clicking a constellation vowel dot plays the word of each instance
      in order, highlighting and labelling the one playing (`playVowel()`
      in `ui/voice-graph.js`; ROADMAP item 6). First version played only
      the vowel; switched to whole words, since vowels are often too short
      to hear. Checked in headless Chromium on Morgan's AE: "actually",
      "fabric", "answer", "hadn't", in time order.
- [x] Browser tests for it in `tests/browser/test_constellation.py`.
- [x] The transcript in the details panel highlights the word being heard,
      from the player and from vowel playback (`tests/browser/
      test_transcript.py`). Transcript words are matched to aligned words
      by spelling (longest common subsequence); on all 21 examples every
      transcript word matched, and `<unk>` maps to the words it replaced
      (Aiden's "Kings—nor") or to none (noises in Jenn, Steve).
- [x] The transcript is now inserted as text, not HTML (it was
      `innerHTML`, so an imported clip's transcript could inject markup).
      The title and other details fields still use `innerHTML`.
- [ ] Not yet listened to in a real browser.

## Goal: browser tests

- [x] `tests/browser/` (pytest + Playwright): serves `dist/` like GitHub
      Pages (or `GVV_URL`), engines from `GVV_BROWSERS`. Covers page load
      and examples, in-browser analysis of the Fern example against its
      stored analysis, a mismatched transcript's error, the recorder's
      takes, and the constellation. 11 pass in Chromium (~30 s).
- [ ] Not in CI; Firefox/WebKit not tried; recorder-bug test not yet
      shown to fail on the old code.
- Surprise: the browser picked a different pronunciation for one word
  ("dog", AA1 vs the stored AO1), and the stored Fern example has 6 of 28
  vowels unmeasured, so the comparisons allow small differences.

## Goal: a static-only build

- [x] `tools/build_static.py` writes `dist/` (54 files, ~133 MB): the page
      in production mode with no server fallback (`serverAnalysisAvailable
      = false`, a template flag; `build.cgi` sets it true), plus the worker,
      WASM, models, dictionaries and example clips. See docs/STATIC.md.
- [x] Tested served by plain `python3 -m http.server`: page and 7 example
      clips load; a recording is analysed (3.1 s first clip, including model
      loading); a bad clip shows the reason; no non-GET requests, no failed
      responses, no page errors.
- [x] Error alerts now include the analysis's reason (e.g. "the recording
      couldn't be matched to the transcript").
- [x] Removed a stray `<link href="style.css">` from the embedded "bright"
      icon (Inkscape leftover), which caused a 404 on every page load.
- [x] GitHub Pages deploy: `.github/workflows/pages.yml` builds and
      publishes `dist/` on push to `master`. The model and dictionary now
      come from MFA's GitHub releases (`tools/fetch_models.sh`), byte-for-byte
      the same files as in the Docker image, so setup no longer needs Docker.
- [x] Live at `tessprime.github.io/gender-voice-visualization/`, deployed
      from the fork's `master` (local `tessmaster`). Surprise: the first
      deploy failed with a 404 because Pages was still on "Deploy from a
      branch", which also served the committed server-backed `index.html`
      (falling back to `backend.cgi` → 405, models 404). Fixed by setting
      Source to "GitHub Actions" and re-running.
- [ ] Rename the fork to `gvv` (site moves to `tessprime.github.io/gvv/`).
- [ ] Decide noise reduction (see above), then consider retiring the
      server path (`serve.py` analysis, `backend.cgi`, the 3.5 GB image).

## Goal: voicealign, phonealign's forced alignment in Rust

Port what `phonealign` does through kalpy/Kaldi to a Rust crate,
`voicealign/`, compilable to WebAssembly, so alignment can run in the
browser. Kaldi is Apache-2.0, so its source can be ported directly. Each
stage is validated against kalpy on the test clip.

What kalpy actually runs for this model (`english_us_arpa`), which differs
from the model's metadata (`uses_deltas: true`): kalpy switches to splicing
+ LDA whenever the model has an `lda.mat`, and aligns with `final.alimdl`
(the speaker-independent model; a different file from `final.mdl`)
whenever there's no speaker transform. So:

  MFCC (13) → CMVN (mean only) → splice ±3 frames (91) → LDA (40 × 91)
  → GMM-HMM alignment with `final.alimdl`

Phones are not position-dependent (72 phones). Model files are in Kaldi's
binary format.

- [x] **1. Features**: MFCC, CMVN, splice, LDA (`src/features.rs`, ported
      from Kaldi), and a reader for Kaldi's binary format
      (`src/kaldi_io.rs`). `reference/dump_kalpy.py` dumps kalpy's
      features at each stage (dither off); `examples/compare_features.rs`
      compares. Test clip, 2638 frames (same count as kalpy):

      | stage | median \|difference\| | max | values up to |
      |---|---|---|---|
      | MFCC | 1.6e-5 | 0.019 | 116 |
      | CMVN | 1.6e-5 | 0.019 | 107 |
      | splice + LDA (alignment input) | 1.5e-6 | 0.0027 | 11 |

      At float32 rounding level (Kaldi computes in float, we in double);
      the largest are probably near-silent frames, where the log of a tiny
      energy amplifies rounding. Step 5 will show whether they matter.
- [x] **2. Model loading**: transition model and diagonal GMMs
      (`src/model.rs`, from `final.alimdl`), decision tree (`src/tree.rs`,
      from `tree`). `reference/dump_model.py` dumps kalpy's view;
      `examples/compare_model.rs` compares:
      - counts identical: 12165 transition ids, 6092 transition states,
        5912 pdfs, 40 dims, 150000 Gaussians; tree width 3, central 1.
      - all 12165 transition ids: same pdf, phone, transition state,
        self-loop and final flags; log-probabilities exactly equal.
      - GMM log-likelihoods on kalpy's features (2000 random frame/pdf
        pairs): median |difference| 5e-6, max 3e-5 (values around -70).
      - tree: over all 1.12M triphone contexts, every one of the 5912 pdfs
        is reached by exactly the (phone, pdf class) pairs kalpy's
        `GetPdfInfo` lists.

      Loading takes 231 ms natively. Format details learned: Kaldi writes
      unsigned integers with a negative size byte (-4); the tree's event
      map follows a `ToPdf` token.
- [x] **3. Graph compilation** (`src/lexicon.rs`, `src/graph.rs`). Built
      directly rather than by FST composition: phone graph (words in
      order, pronunciation alternatives, optional silence, kalpy's lexicon
      costs) → triphone units (each phone with every possible left/right
      neighbour) → HMM-state nodes with transition ids. 72 words: 852
      units, 2870 nodes, 8883 arcs, built in 3.5 ms. Determinization and
      weight pushing, which Kaldi applies, don't change path costs here.

      Checked with `examples/check_graph.rs` against kalpy's alignment of
      the test clip (`reference/dump_alignment.py`, dither off): kalpy's
      transition-id sequence is a path through the graph, and that path's
      score is **-166465.73 vs kalpy's -166465.64** (difference 5e-7
      relative; float32 acoustic scores).

      Two Kaldi conventions found on the way:
      - **Reordered labels**: kalpy labels a stay in an HMM state with the
        forward transition first, then the self-loops (Kaldi's default
        `reorder`). Same frame-to-state assignment; `from_reordered` /
        `to_reordered` in model.rs convert.
      - **Scaled transitions** (`GetScaledTransitionLogProb`): with
        transition scale 1.0 and self-loop scale 0.1, a forward transition
        costs 0.1·log(1 - p_self) + 1.0·log(p / (1 - p_self)). Charging
        log p at scale 1.0 overcounted by ~495 (score off by ~4950).

      Notes from researching kalpy's compiler: what kalpy does (`kalpy/fstext/lexicon.py` `create_fsts` /
      `add_pronunciation`, `kalpy/decoder/training_graphs.py`):
      - **Lexicon L** (tropical weights, costs = -log p): states 0 start,
        1 "no silence before", 2 "silence before". Start→1 `<eps>`
        (-log(1 - 0.18)); start→2 `sil` (-log 0.18). Per pronunciation
        p1..pn of word w: 1→… `p1:w` (pron cost + non-silence-before
        cost), 2→… `p1:w` (pron cost + silence-before cost), then p2..pn
        with `<eps>` output; from the last state, the silence
        disambiguation symbol → 1 (non-silence-following cost) or `sil` →
        2 (silence-following cost). Finals: state 2 -log(0.99), state 1
        -log(0.01). Costs: pron = |log p| with p floored at 0.01;
        dictionary columns are p, silence-after p, silence-before
        correction, non-silence-before correction (correction cost =
        -log c; missing silence-after p falls back to 0.18).
        `disambiguation=False`, so no per-word disambiguation symbols.
      - **Compiler**: kalpy's Python wraps Kaldi's C++
        `TrainingGraphCompiler` (`CompileGraphsFromText`), defaults
        transition_scale 0.0 and self_loop_scale 0.0 here (check what
        `KalpyAligner` passes). Kaldi's steps: compose L with the linear
        word acceptor, compose with the context FST (triphones, width 3,
        central 1), compose with H (HMMs from tree + transition model),
        determinize in the log semiring, add self-loops.
      - `KalpyAligner` compiles graphs with transition and self-loop
        scales 0, so graphs hold only lexicon costs; the aligner
        (`gmm_align_compiled`) adds transition costs (scale 1.0, self-loops
        0.1) and scales acoustics by 0.1. Kaldi reports
        likelihood = -(graph cost + 0.1 · acoustic cost) / 0.1.
- [x] **4. Alignment** (`src/align.rs`): Viterbi token passing with beam
      pruning as Kaldi's FasterDecoder (beam 10, retry 40); arc cost =
      lexicon + scaled transition + 0.1 × acoustic. Outputs Kaldi
      (reordered) transition ids, the likelihood, and phone and word
      segments (end times clipped to the recording's length, as kalpy).
      `examples/compare_alignment.rs`, end to end from the WAV, on the test
      clip vs kalpy (dither off): **2638/2638 transition ids identical, all
      269 phones and 72 words identical**; likelihood -166465.70 vs
      -166465.64. Time: features 17 ms, graph 3 ms, alignment 84 ms
      (native).

      **Bug found by this comparison:** the graph didn't make a triphone
      unit lead only into units of the phone it assumed as its right
      context, so the search could pick context variants freely and found
      "better" paths kalpy's graph doesn't allow (likelihood -166287.6;
      98.4% of frames with the same phone). kalpy's own path scored
      identically in both graphs, which is why step 3's check missed it.
      Rerunning kalpy with beams up to 200 (-166464.69) ruled out pruning
      before the cause was found.
- [x] **5. More recordings, an API, WebAssembly.**
      - **21 example clips** (`reference/check_examples.py`, dither off):
        42463/42515 frames' transition ids identical to kalpy's (99.88%);
        18 clips entirely identical. `luna` (ours slightly worse) and
        `david` (both retried with beam 40; ours better) differ through
        beam pruning: Kaldi pushes the lexicon costs to other places in
        its graph, so intermediate scores, and so pruning, differ.
        Reported differently: OOV words keep their text (kalpy: `<unk>`),
        and like kalpy, the last segment ends at the end of the recording.
      - **Transcript normalization** (`lexicon::normalize`), dictionary-
        aware like MFA's SimpleTokenizer: hyphenated words not in the
        dictionary are split; clitics split off (`x's` → `x` `'s`);
        `’` counts as an apostrophe. Identical to kalpy on all 21
        transcripts.
      - **API** (`Aligner`, src/aligner.rs): load from the model files'
        bytes and a dictionary; `align(samples, 16000, transcript)` →
        word and phone intervals. Dither (sd 1, fixed seed, own PRNG) is
        on by default, as phonealign. With dither off it reproduces kalpy
        exactly (72/72 words on the test clip); with dither on, 53/72 words
        identical, the rest mostly 10-120 ms apart, plus one ambiguous "a"
        placed after a pause instead of before.
      - GMM parameters stored as f32 (as in the file): half the memory,
        identical results.
      - **WebAssembly** (src/wasm.rs; `va_alloc`, `va_new`, `va_align`
        returning JSON, `va_free`): 479 KB (189 KB gzipped).
        `reference/check_wasm.mjs` in Node: load model + full 208k-word
        dictionary 2.4 s, align the 26 s test clip in 275-450 ms (617 ms
        first run), 230 MB memory. Natively: load 0.5 s, align ~100 ms.

      Possible next steps: faster/lighter loading (parse straight to f32;
      a compact dictionary or only the words needed), and the browser glue
      that combines voicealign and voicemeasure.

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
- [x] **3. Pitch:** `To Pitch: 0, 75, 600` (autocorrelation, Boersma
      1993): per 40 ms frame, subtract the mean, Hanning window,
      autocorrelation divided by the window's; candidates at its peaks
      (parabolic interpolation) plus an unvoiced candidate; Viterbi path
      with Praat's default costs. On the test clip (2634 frames): voicing
      agrees in 99.1% of frames; where both are voiced, F0 differs by a
      median 0.015 Hz (99.4% within 1 Hz), no octave errors.

      Undocumented detail found by experiment: the **local peak** (frame
      loudness, for the unvoiced candidate's strength) is measured **after
      windowing**; measuring the raw frame gave 96.0% voicing agreement.

      **Open: a small voicing bias.** The remaining disagreements are all
      frames voiced only in voicemeasure (24 on the test clip; 79 of 7065
      frames on the test clip + `all` + `wina`), at the edges of voiced
      stretches. They're loud but weakly periodic: unvoiced strength 0.450
      (its minimum), best voiced candidate ~0.50 (margin ~+0.05). Praat
      must find ~0.05-0.1 lower periodicity there. Tried without effect:
      sinc instead of parabolic peak interpolation, the paper's low-pass
      from 95% of Nyquist, two other Hanning window definitions. Scaling the
      local peak trades extra voiced frames for missing ones, so loudness
      isn't the cause. Next ideas: how the autocorrelation is normalized or
      zero-padded, and whether peak heights use r_x or r_a.
- [x] **4. Measurements at phone midpoints.** `measure.rs`: `measure_at()`
      returns F0 and F1-F3 at given times, replacing
      textgrid-formants.praat. Between frames, values are linear; if one
      frame has no value, the nearer frame's value is used (undocumented;
      reproduces Praat's F0 at 266/266 test-clip phone midpoints, vs 261 and
      256 for the other rules tried).

      **On the 21 example clips** (`reference/check_examples.py`, 1475
      vowels): F0 median |difference| 0.018 Hz (99.6% within 1 Hz), voicing
      agrees at 98.7% of vowel midpoints; F1-F3 as above. What the app
      shows: clip median pitch differs by a median 0.28 Hz (max 5.0 Hz,
      `all` 141.7 vs 136.6, `wina` 209.3 vs 213.9; the median includes
      consonants, so the voicing-edge bias moves it); clip median resonance
      by a median 0.18 points (max 1.6).

- [x] **5. WebAssembly build.** `src/wasm.rs` exports a minimal C-style
      interface (`vm_alloc`, `vm_measure`, `vm_free`; no bindings
      generator). `cargo build --release --target wasm32-unknown-unknown`
      gives a 318 KB module (117 KB gzipped) that instantiates in 7-17 ms.
      `reference/check_wasm.mjs` runs it in Node. Its output is
      byte-identical to the native build's on the test clip.

      Speed, measuring at the test clip's 266 phone midpoints (26 s of
      audio), warm runs: native ~225 ms, Node ~305 ms, Chromium 136
      ~290 ms (first run ~500 ms). Firefox 137 *as bundled with
      Playwright* took ~7.5 s, but a regular **Firefox 157 on Windows**
      matched Chromium within ~10% (`reference/wasm_test.html`, which
      times each stage, on a synthetic signal or a chosen audio file decoded
      at 16 kHz). So the slowness was Playwright's Firefox build.

      The synthetic signal exposed a slow path: formant root finding
      (Durand-Kerner) never met its 1e-14 stopping threshold when roots were
      clustered, so most frames ran the full 500 iterations (median 9 on
      real speech); formants took 1460 ms instead of ~190. Now Aberth's
      method, stopping at 1e-12 (Newton polishing follows), max 100
      iterations: ~200 ms on both signals, with identical results on the
      test clip and unchanged numbers on all 21 example clips.

      Speed-ups on the way (results unchanged: identical at all 266
      midpoints): resampling, 97% of the time at first (2.0 of 2.1 s), went
      to 140 ms with polyphase interpolation (16 -> 10 kHz repeats every 5
      outputs, so the sinc weights are computed once per phase).

      **Bug found and fixed along the way:** a faster sine trick lost
      precision when an output sample landed within ~1e-10 of an input
      sample (every fifth sample, at 16 -> 10 kHz), giving sinc values like
      0.9998 instead of 1 and shifting formants by up to 4 Hz. Fixed by
      computing the sine from the distance's fractional part; a unit test
      now covers positions next to whole samples.

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
