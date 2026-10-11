import random

from . import phones, preprocessing, resonance
from .settings import settings

# Formant weights for resonance, fitted by corpusanalysis.py.
WEIGHTS = [0.7321428571428571, 0.26785714285714285, 0.0]

def analyze(uploaded_file, transcript, aligner=None):
	"""Process one uploaded recording. Returns (id, data), where data is
	what the frontend expects from backend.cgi.

	See preprocessing.process() for `aligner`.
	"""
	id = str(random.randint(0, 2**32))
	tmp_dir = settings['recordings'] + id

	praat_output = preprocessing.process(uploaded_file, transcript, tmp_dir, aligner)

	data = phones.parse(praat_output)
	resonance.compute_resonance(data, WEIGHTS)
	return id, data
