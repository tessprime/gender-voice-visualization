"""Reference output from kalpy for testing voicealign's model loading.

    python dump_model.py MODEL_DIR FEATURES OUT_DIR

MODEL_DIR is an extracted acoustic model (final.alimdl, tree); FEATURES is
features.f32 from dump_kalpy.py. Run inside the web app's Docker image.
Writes:

  transitions.tsv  per transition id: pdf, phone, transition state,
                   self-loop?, final?, log probability; plus a summary line
  loglikes.tsv     frame, pdf, log-likelihood, for a fixed sample of pairs
  pdf_info.tsv     per pdf: the (phone, pdf class) pairs the tree maps to it
"""
import random
import struct
import sys

import numpy
from kalpy.gmm.utils import read_gmm_model, read_tree

model_dir, features_path, out = sys.argv[1:4]
transitions, gmms = read_gmm_model(f'{model_dir}/final.alimdl')
tree = read_tree(f'{model_dir}/tree')

with open(f'{out}/transitions.tsv', 'w') as f:
	f.write(f'# transition_ids {transitions.NumTransitionIds()} transition_states {transitions.NumTransitionStates()} '
	        f'pdfs {transitions.NumPdfs()} phones {transitions.NumPhones()} dim {gmms.Dim()} gaussians {gmms.NumGauss()}\n')
	for tid in range(1, transitions.NumTransitionIds() + 1):
		f.write('\t'.join(map(str, [
			tid, transitions.TransitionIdToPdf(tid), transitions.TransitionIdToPhone(tid),
			transitions.TransitionIdToTransitionState(tid), int(transitions.IsSelfLoop(tid)),
			int(transitions.IsFinal(tid)), repr(transitions.GetTransitionLogProb(tid))])) + '\n')

with open(features_path, 'rb') as f:
	rows, cols = struct.unpack('<II', f.read(8))
	features = numpy.frombuffer(f.read(), dtype='<f4').reshape(rows, cols)
from _kalpy.matrix import FloatVector
rng = random.Random(1)
with open(f'{out}/loglikes.tsv', 'w') as f:
	for _ in range(2000):
		frame, pdf = rng.randrange(rows), rng.randrange(gmms.NumPdfs())
		vector = FloatVector(cols)
		vector.numpy()[:] = features[frame]
		f.write(f'{frame}\t{pdf}\t{gmms.LogLikelihood(pdf, vector)!r}\n')

phones = list(transitions.GetPhones())
# Pdf classes per phone, from the topology (its number of emitting states).
topology = transitions.GetTopo()
num_pdf_classes = [0] * (max(phones) + 1)
for p in phones:
	num_pdf_classes[p] = topology.NumPdfClasses(p)
info = tree.GetPdfInfo(phones, num_pdf_classes)
with open(f'{out}/pdf_info.tsv', 'w') as f:
	for pdf, pairs in enumerate(info):
		f.write(f'{pdf}\t' + ' '.join(f'{p},{c}' for p, c in sorted(pairs)) + '\n')
print('wrote transitions.tsv, loglikes.tsv, pdf_info.tsv')
