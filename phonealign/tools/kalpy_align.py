"""Experiment: align one clip by calling kalpy directly, as `mfa align_one`
does, timing each step.

Loads the model and lexicon once, then aligns the clip several times with
MFCC dither on (each run draws different noise, which measures MFA's own
run-to-run variation) and with dither off. Writes a TextGrid per run.

    python kalpy_align.py CLIP_DIR DICTIONARY OUT_DIR [RUNS]

CLIP_DIR is a backend clip directory (it uses corpus/recording.wav and
corpus/recording.txt). Run inside the Docker image, as `nobody`.
"""
import os
import sys
import time
from pathlib import Path

timings = []


def timed(label, function, *args, **kwargs):
	start = time.perf_counter()
	result = function(*args, **kwargs)
	timings.append((label, time.perf_counter() - start))
	return result


t0 = time.perf_counter()
import soundfile
from kalpy.aligner import KalpyAligner
from kalpy.feat.cmvn import CmvnComputer
from kalpy.feat.mfcc import MfccComputer
from kalpy.fstext.lexicon import HierarchicalCtm, LexiconCompiler
from kalpy.utterance import Segment
from kalpy.utterance import Utterance as KalpyUtterance
from montreal_forced_aligner.models import AcousticModel
from montreal_forced_aligner.online.alignment import tokenize_utterance_text
from montreal_forced_aligner.tokenization.simple import SimpleTokenizer
timings.append(('imports', time.perf_counter() - t0))

clip_dir, dictionary_path, out_dir = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
runs = int(sys.argv[4]) if len(sys.argv) > 4 else 3
wav = clip_dir / 'corpus' / 'recording.wav'
transcript = (clip_dir / 'corpus' / 'recording.txt').read_text()
out_dir.mkdir(parents=True, exist_ok=True)
mfa_root = os.environ.get('MFA_ROOT_DIR', os.path.expanduser('~/Documents/MFA'))

# One-time setup: what a long-lived aligner would do at startup.
model = timed('load acoustic model', AcousticModel,
	Path(mfa_root) / 'pretrained_models' / 'acoustic' / 'english.zip')
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
aligner_options = {}  # align_one passes beam etc. only when configured


def make_tokenizer():
	# english_us_arpa's language is Language.unknown, so align_one uses
	# SimpleTokenizer with MFA's default markers rather than spacy.
	from montreal_forced_aligner.data import (
		BRACKETED_WORD, CUTOFF_WORD, LAUGHTER_WORD, OOV_WORD)
	from montreal_forced_aligner.dictionary.mixins import (
		DEFAULT_BRACKETS, DEFAULT_CLITIC_MARKERS, DEFAULT_COMPOUND_MARKERS,
		DEFAULT_PUNCTUATION, DEFAULT_WORD_BREAK_MARKERS)
	return SimpleTokenizer(
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


def align(dither, seed=None):
	"""Align the clip once; return its intervals and per-step timings.

	With `seed`, add the dither noise ourselves from that seed (and turn
	Kaldi's own off), which is deterministic. Kaldi's `dither: d` adds
	Gaussian noise with standard deviation d, in 16-bit sample units.
	"""
	del timings[:]
	# Per request, since the dictionary is built from the transcript.
	timed('load pronunciations', lexicon.load_pronunciations, dictionary_path)
	timed('compile lexicon FSTs', lexicon.create_fsts)
	# The tokenizer uses the lexicon's word table, so it's rebuilt with it.
	tokenizer = timed('create tokenizer', make_tokenizer)
	text = timed('tokenize transcript', tokenize_utterance_text,
		transcript, lexicon, tokenizer, None)
	options = dict(model.mfcc_options, dither=dither)
	segment = Segment(wav)
	if seed is not None:
		import numpy
		noise = numpy.random.default_rng(seed).normal(0, dither, segment.wave.shape)
		segment._wave = segment.wave + noise / 32768
		options['dither'] = 0
	utterance = KalpyUtterance(segment, text)
	timed('MFCCs', utterance.generate_mfccs, MfccComputer(**options))
	cmvn = timed('CMVN', CmvnComputer().compute_cmvn_from_features, [utterance.mfccs])
	timed('apply CMVN', utterance.apply_cmvn, cmvn)
	aligner = timed('create aligner', KalpyAligner, model, lexicon, **aligner_options)
	ctm = timed('align', aligner.align_utterance, utterance)
	return ctm, list(timings)


setup = list(timings)
print('one-time setup:')
for label, seconds in setup:
	print(f'  {seconds * 1000:8.1f} ms  {label}')

duration = soundfile.info(str(wav)).duration
configurations = [(f'dither{d}-run{r}', d, None) for d in (1, 0) for r in range(runs)]
configurations += [(f'seeded-seed{s}-run{r}', 1, s) for s in range(3) for r in range(2)]
for name, dither, seed in configurations:
		run = int(name[-1])
		ctm, steps = align(dither, seed)
		path = out_dir / f'{name}.TextGrid'
		HierarchicalCtm(ctm.word_intervals).export_textgrid(
			path, file_duration=duration, output_format='long_textgrid')
		total = sum(seconds for _, seconds in steps)
		print(f'{name}: {total * 1000:.0f} ms  ->  {path.name}')
		if run == 0:
			for label, seconds in steps:
				print(f'  {seconds * 1000:8.1f} ms  {label}')
