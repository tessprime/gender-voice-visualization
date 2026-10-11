import os
import random
import sys

from . import phones, preprocessing, resonance
from .preprocessing import ProcessingError
from .settings import settings

# Formant weights for resonance, fitted by corpusanalysis.py.
WEIGHTS = [0.7321428571428571, 0.26785714285714285, 0.0]

def load_aligner():
	"""Load phonealign's Aligner with the MFA english models (a few seconds).
	Raises if phonealign or the models aren't available."""
	repository = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
	sys.path.insert(0, os.path.join(repository, 'phonealign', 'src'))
	from phonealign import Aligner

	models = os.path.join(os.environ.get('MFA_ROOT_DIR', os.path.expanduser('~/Documents/MFA')), 'pretrained_models')
	# Loading unpacks the model under $MFA_ROOT_DIR. Callers may run as root
	# while `mfa align` (backend.cgi) runs as nobody, so keep anything created
	# there writable by everyone, as the Dockerfile does.
	old_umask = os.umask(0)
	try:
		return Aligner(os.path.join(models, 'acoustic', 'english.zip'),
		               os.path.join(models, 'dictionary', 'english.dict'))
	finally:
		os.umask(old_umask)

def analyze(uploaded_file, transcript, aligner=None):
	"""Process one uploaded recording. Returns (id, data), where data is
	what the frontend expects from backend.cgi.

	See preprocessing.process() for `aligner`.
	"""
	id = str(random.randint(0, 2**32))
	tmp_dir = settings['recordings'] + id

	praat_output = preprocessing.process(uploaded_file, transcript, tmp_dir, aligner)
	if praat_output is None:
		raise ProcessingError(
			"The recording couldn't be matched to the transcript. Check that "
			"the transcript matches what was said and that the recording isn't cut off.")

	data = phones.parse(praat_output)
	resonance.compute_resonance(data, WEIGHTS)
	return id, data
