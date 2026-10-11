"""Reference output from kalpy for testing voicealign, stage by stage.

    python dump_kalpy.py recording.wav OUT_DIR

Run inside the web app's Docker image (it has kalpy and the models). Writes,
for the recording with dither off (so the output is deterministic):

  mfcc.f32       raw MFCCs              (frames x 13)
  cmvn.f32       after CMVN             (frames x 13)
  features.f32   after splice + LDA     (frames x 40), what alignment uses

Each file is little-endian f32, row by row, preceded by two little-endian
u32s: rows and columns.
"""
import os
import struct
import sys
from pathlib import Path

import numpy
from kalpy.feat.cmvn import CmvnComputer
from kalpy.feat.mfcc import MfccComputer
from kalpy.utterance import Segment, Utterance
from montreal_forced_aligner.models import AcousticModel


def save(path, matrix):
	matrix = numpy.asarray(matrix, dtype='<f4')
	with open(path, 'wb') as f:
		f.write(struct.pack('<II', *matrix.shape))
		f.write(matrix.tobytes())
	print(f'{path}: {matrix.shape[0]} x {matrix.shape[1]}')


wav, out = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)
models = Path(os.environ.get('MFA_ROOT_DIR', os.path.expanduser('~/Documents/MFA'))) / 'pretrained_models'
model = AcousticModel(models / 'acoustic' / 'english.zip')

utterance = Utterance(Segment(wav), 'x')
utterance.generate_mfccs(MfccComputer(**dict(model.mfcc_options, dither=0)))
save(f'{out}/mfcc.f32', utterance.mfccs.numpy())
utterance.apply_cmvn(CmvnComputer().compute_cmvn_from_features([utterance.mfccs]))
save(f'{out}/cmvn.f32', utterance.mfccs.numpy())
# MFCCs are already computed, so this only splices and applies the LDA
# transform, exactly as KalpyAligner does before aligning.
save(f'{out}/features.f32', utterance.generate_features(model).numpy())
