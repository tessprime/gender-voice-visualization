"""Forced alignment of single recordings, keeping the acoustic model loaded.

Makes the same kalpy calls as `mfa align_one`, with two differences:

- The pronunciation dictionary is trimmed to the transcript's words for each
  request. Compiling only those is far faster than the full dictionary.
- The MFCC dither noise is added from a fixed seed instead of by Kaldi,
  whose random generator isn't reseeded between calls. Results are then
  identical for identical input. Turning dither off instead makes alignment
  worse, presumably because the model was trained on dithered features.

See docs/CURRENT.md for the measurements behind both.
"""
import dataclasses
import re
import tempfile
import typing
from pathlib import Path

import numpy

SAMPLE_RATE = 16000  # Hz; what the acoustic models expect.
SILENCE_LABELS = {'', '<eps>', 'sil', 'sp', 'spn'}


class AlignmentError(Exception):
	"""The transcript couldn't be aligned to the audio, e.g. because they
	don't match or the recording is too short."""


@dataclasses.dataclass(frozen=True)
class Interval:
	start: float  # seconds
	end: float
	label: str


@dataclasses.dataclass
class Alignment:
	"""Aligned words and phones, in time order. Silence isn't included: it's
	the time not covered by any interval."""
	words: typing.List[Interval]
	phones: typing.List[Interval]
	duration: float  # seconds

	def write_textgrid(self, path):
		"""Write a long-format TextGrid like `mfa align`'s: a "words" tier
		then a "phones" tier, each covering the whole recording, with
		silence as empty intervals."""
		def tier(name, intervals):
			filled, time = [], 0.0
			for interval in intervals:
				if interval.start > time:
					filled.append(Interval(time, interval.start, ''))
				filled.append(interval)
				time = interval.end
			if time < self.duration:
				filled.append(Interval(time, self.duration, ''))
			lines = [
				'        class = "IntervalTier" ',
				f'        name = "{name}" ',
				'        xmin = 0.0 ',
				f'        xmax = {self.duration} ',
				f'        intervals: size = {len(filled)} ',
			]
			for number, interval in enumerate(filled, 1):
				lines += [
					f'        intervals [{number}]:',
					f'            xmin = {interval.start} ',
					f'            xmax = {interval.end} ',
					f'            text = "{interval.label}" ',
				]
			return lines

		lines = [
			'File type = "ooTextFile"',
			'Object class = "TextGrid"',
			'',
			'xmin = 0.0 ',
			f'xmax = {self.duration} ',
			'tiers? <exists> ',
			'size = 2 ',
			'item []:',
			'    item [1]:',
			*tier('words', self.words),
			'    item [2]:',
			*tier('phones', self.phones),
		]
		Path(path).write_text('\n'.join(lines) + '\n', encoding='utf-8')


class Aligner:
	"""Create once (this loads the acoustic model, ~2-3 s with imports), then
	call `align()` for each recording.

	`acoustic_model` is an MFA acoustic model zip (e.g. english_us_arpa.zip)
	and `dictionary` an MFA pronunciation dictionary file for it.
	"""

	def __init__(self, acoustic_model, dictionary, dither_seed=0):
		# Imported here so importing phonealign itself stays cheap.
		from kalpy.feat.mfcc import MfccComputer
		from montreal_forced_aligner.models import AcousticModel

		self._model = AcousticModel(Path(acoustic_model))
		self._dither = self._model.mfcc_options.get('dither', 0)
		self._dither_seed = dither_seed
		self._mfcc_computer = MfccComputer(**dict(self._model.mfcc_options, dither=0))
		self._pronunciations, self._clitics = _read_dictionary(Path(dictionary))

	def align(self, samples, sample_rate, transcript):
		"""Align `transcript` to mono audio `samples` (floats in -1..1).

		Returns an `Alignment`; raises `AlignmentError` if alignment fails.
		"""
		from kalpy.aligner import KalpyAligner
		from kalpy.exceptions import AlignerError
		from kalpy.feat.cmvn import CmvnComputer
		from kalpy.utterance import Segment
		from kalpy.utterance import Utterance
		from montreal_forced_aligner.online.alignment import tokenize_utterance_text

		samples = numpy.asarray(samples, dtype=numpy.float32)
		if samples.ndim != 1:
			raise ValueError('samples must be mono (a 1-D array)')
		if sample_rate != SAMPLE_RATE:
			import librosa
			samples = librosa.resample(samples, orig_sr=sample_rate, target_sr=SAMPLE_RATE)
		duration = len(samples) / SAMPLE_RATE

		with tempfile.TemporaryDirectory() as directory:
			dictionary = Path(directory) / 'dictionary.dict'
			dictionary.write_text(self._dictionary_for(transcript))
			lexicon = self._lexicon(dictionary)
		text = tokenize_utterance_text(transcript, lexicon, _tokenizer(lexicon), None)

		# kalpy reads audio from a file; hand it the samples directly, with the
		# seeded dither applied. Kaldi's dither d is Gaussian noise with
		# standard deviation d, in 16-bit sample units.
		segment = Segment('', begin=0.0, end=duration)
		noise = numpy.random.default_rng(self._dither_seed).normal(0, self._dither, samples.shape)
		segment._wave = samples + noise / 32768

		utterance = Utterance(segment, text)
		utterance.generate_mfccs(self._mfcc_computer)
		utterance.apply_cmvn(CmvnComputer().compute_cmvn_from_features([utterance.mfccs]))
		try:
			ctm = KalpyAligner(self._model, lexicon).align_utterance(utterance)
		except AlignerError as e:
			raise AlignmentError(str(e)) from e

		# kalpy's times are float32 (1.33 comes back as 1.3300000429...).
		# Alignment works in 10 ms frames, so milliseconds lose nothing.
		def interval(ctm_interval):
			return Interval(
				round(ctm_interval.begin, 3), round(ctm_interval.end, 3), ctm_interval.label)

		words, phones = [], []
		for word in ctm.word_intervals:
			if word.label not in SILENCE_LABELS:
				words.append(interval(word))
			phones.extend(
				interval(phone) for phone in word.phones if phone.label not in SILENCE_LABELS)
		return Alignment(words, phones, duration)

	def _dictionary_for(self, transcript):
		"""The dictionary lines needed for `transcript`'s words."""
		# MFA splits words on hyphens and clitic apostrophes, so include the
		# parts as well as the whole word, plus the clitic entries ('s, 'll, ...).
		words = set()
		for token in re.findall(r"[\w'-]+", transcript.lower()):
			words.add(token)
			words.update(part for part in re.split(r"['-]", token) if part)
		lines = list(self._clitics)
		for word in sorted(words):
			lines.extend(self._pronunciations.get(word, []))
		return ''.join(lines)

	def _lexicon(self, dictionary_path):
		from kalpy.fstext.lexicon import LexiconCompiler
		p = self._model.parameters
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
		lexicon.load_pronunciations(dictionary_path)
		lexicon.create_fsts()
		return lexicon


def _read_dictionary(path):
	"""({word: [dictionary lines]}, [clitic lines]) for an MFA dictionary."""
	pronunciations = {}
	clitics = []
	with open(path, encoding='utf-8') as f:
		for line in f:
			word = line.split('\t', 1)[0].lower()
			if word.startswith("'"):
				clitics.append(line)
			else:
				pronunciations.setdefault(word, []).append(line)
	return pronunciations, clitics


def _tokenizer(lexicon):
	"""The tokenizer `mfa align_one` uses for models without a language set
	(english_us_arpa's language is unknown), with MFA's default markers."""
	from montreal_forced_aligner.data import (
		BRACKETED_WORD, CUTOFF_WORD, LAUGHTER_WORD, OOV_WORD)
	from montreal_forced_aligner.dictionary.mixins import (
		DEFAULT_BRACKETS, DEFAULT_CLITIC_MARKERS, DEFAULT_COMPOUND_MARKERS,
		DEFAULT_PUNCTUATION, DEFAULT_WORD_BREAK_MARKERS)
	from montreal_forced_aligner.tokenization.simple import SimpleTokenizer
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
