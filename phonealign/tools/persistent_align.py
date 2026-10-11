"""Experiment: a long-lived aligner. Compile the full dictionary and create
the aligner once, then align the clip several times, timing setup and each
request separately. Uses seeded dither (see docs/CURRENT.md).

    python persistent_align.py CLIP_DIR OUT_DIR [RUNS]

Run inside the Docker image, as `nobody`.
"""
import os
import sys
import time
from pathlib import Path


def timed(timings, label, function, *args, **kwargs):
	start = time.perf_counter()
	result = function(*args, **kwargs)
	timings.append((label, time.perf_counter() - start))
	return result


setup = []
t0 = time.perf_counter()
import numpy
import soundfile
from kalpy.aligner import KalpyAligner
from kalpy.feat.cmvn import CmvnComputer
from kalpy.feat.mfcc import MfccComputer
from kalpy.fstext.lexicon import HierarchicalCtm, LexiconCompiler
from kalpy.utterance import Segment
from kalpy.utterance import Utterance as KalpyUtterance
from montreal_forced_aligner.data import (
	BRACKETED_WORD, CUTOFF_WORD, LAUGHTER_WORD, OOV_WORD)
from montreal_forced_aligner.dictionary.mixins import (
	DEFAULT_BRACKETS, DEFAULT_CLITIC_MARKERS, DEFAULT_COMPOUND_MARKERS,
	DEFAULT_PUNCTUATION, DEFAULT_WORD_BREAK_MARKERS)
from montreal_forced_aligner.models import AcousticModel
from montreal_forced_aligner.online.alignment import tokenize_utterance_text
from montreal_forced_aligner.tokenization.simple import SimpleTokenizer
setup.append(('imports', time.perf_counter() - t0))

clip_dir, out_dir = Path(sys.argv[1]), Path(sys.argv[2])
runs = int(sys.argv[3]) if len(sys.argv) > 3 else 5
out_dir.mkdir(parents=True, exist_ok=True)
models = Path(os.environ.get('MFA_ROOT_DIR', os.path.expanduser('~/Documents/MFA'))) / 'pretrained_models'

# --- One-time setup ---
model = timed(setup, 'load acoustic model', AcousticModel, models / 'acoustic' / 'english.zip')
p = model.parameters
lexicon = LexiconCompiler(
	disambiguation=False,
	silence_probability=p['silence_probability'],
	initial_silence_probability=p['initial_silence_probability'],
	final_silence_correction=p['final_silence_correction'],
	final_non_silence_correction=p['final_non_silence_correction'],
	silence_phone=p['optional_silence_phone'],
	oov_phone=p['oov_phone'],
	position_dependent_phones=p['position_dependent_phones'],
	phones=p['non_silence_phones'],
	ignore_case=True,
)
timed(setup, 'load full dictionary', lexicon.load_pronunciations, models / 'dictionary' / 'english.dict')
timed(setup, 'compile lexicon FSTs', lexicon.create_fsts)
tokenizer = timed(setup, 'create tokenizer', SimpleTokenizer,
	word_table=lexicon.word_table,
	word_break_markers=DEFAULT_WORD_BREAK_MARKERS,
	punctuation=DEFAULT_PUNCTUATION,
	clitic_markers=DEFAULT_CLITIC_MARKERS,
	compound_markers=DEFAULT_COMPOUND_MARKERS,
	brackets=DEFAULT_BRACKETS,
	laughter_word=LAUGHTER_WORD,
	oov_word=OOV_WORD,
	bracketed_word=BRACKETED_WORD,
	cutoff_word=CUTOFF_WORD,
	ignore_case=True,
)
aligner = timed(setup, 'create aligner', KalpyAligner, model, lexicon)
mfcc_computer = MfccComputer(**dict(model.mfcc_options, dither=0))

print('one-time setup:')
for label, seconds in setup:
	print(f'  {seconds * 1000:8.1f} ms  {label}')


# --- Per request ---
def align(wav, transcript, seed=0):
	steps = []
	text = timed(steps, 'tokenize', tokenize_utterance_text, transcript, lexicon, tokenizer, None)
	segment = Segment(wav)
	timed(steps, 'load audio', lambda: segment.wave)
	# Seeded dither: Kaldi's dither 1 is Gaussian noise, sd 1 in 16-bit units.
	noise = numpy.random.default_rng(seed).normal(0, 1, segment.wave.shape)
	segment._wave = segment.wave + noise / 32768
	utterance = KalpyUtterance(segment, text)
	timed(steps, 'MFCCs', utterance.generate_mfccs, mfcc_computer)
	cmvn = timed(steps, 'CMVN', CmvnComputer().compute_cmvn_from_features, [utterance.mfccs])
	utterance.apply_cmvn(cmvn)
	ctm = timed(steps, 'align', aligner.align_utterance, utterance)
	return ctm, steps


wav = clip_dir / 'corpus' / 'recording.wav'
transcript = (clip_dir / 'corpus' / 'recording.txt').read_text()
duration = soundfile.info(str(wav)).duration
for run in range(runs):
	ctm, steps = align(wav, transcript)
	path = out_dir / f'persistent-run{run}.TextGrid'
	HierarchicalCtm(ctm.word_intervals).export_textgrid(
		path, file_duration=duration, output_format='long_textgrid')
	print(f'request {run}: {sum(s for _, s in steps) * 1000:.0f} ms  '
		+ '  '.join(f'{label} {s * 1000:.0f}' for label, s in steps))
