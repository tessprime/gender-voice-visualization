"""Reference alignment from kalpy for testing voicealign end to end.

    python dump_alignment.py recording.wav transcript.txt OUT_DIR

Run inside the web app's Docker image. Aligns as phonealign does (trimmed
dictionary, SimpleTokenizer, KalpyAligner defaults) but with dither off,
so it uses exactly the features dump_kalpy.py writes. Writes:

  dictionary.dict  the dictionary lines used
  words.txt        the normalized transcript, one word per line
  alignment.txt    one transition id per frame
  result.txt       "likelihood <value>", then word and phone intervals
                   ("word <start> <end> <label>", "phone ...")
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, '/app/phonealign/src')
from kalpy.aligner import KalpyAligner
from kalpy.feat.cmvn import CmvnComputer
from kalpy.feat.mfcc import MfccComputer
from kalpy.utterance import Segment, Utterance
from montreal_forced_aligner.models import AcousticModel
from montreal_forced_aligner.online.alignment import tokenize_utterance_text
from phonealign.aligner import Aligner, _tokenizer

wav, transcript_path, out = sys.argv[1:4]
os.makedirs(out, exist_ok=True)
models = Path(os.environ.get('MFA_ROOT_DIR', os.path.expanduser('~/Documents/MFA'))) / 'pretrained_models'
transcript = open(transcript_path).read()

# Reuse phonealign's dictionary trimming and lexicon setup.
aligner = Aligner(models / 'acoustic' / 'english.zip', models / 'dictionary' / 'english.dict')
dictionary = Path(out) / 'dictionary.dict'
dictionary.write_text(aligner._dictionary_for(transcript))
lexicon = aligner._lexicon(dictionary)
text = tokenize_utterance_text(transcript, lexicon, _tokenizer(lexicon), None)
Path(out, 'words.txt').write_text('\n'.join(text.split()) + '\n')

model = aligner._model
utterance = Utterance(Segment(wav), text)
utterance.generate_mfccs(MfccComputer(**dict(model.mfcc_options, dither=0)))
utterance.apply_cmvn(CmvnComputer().compute_cmvn_from_features([utterance.mfccs]))

kalpy_aligner = KalpyAligner(model, lexicon)
alignment = kalpy_aligner._align_utterance(utterance)
Path(out, 'alignment.txt').write_text('\n'.join(map(str, alignment.alignment)) + '\n')
ctm = kalpy_aligner.align_utterance(utterance)
with open(Path(out, 'result.txt'), 'w') as f:
	f.write(f'likelihood {alignment.likelihood!r}\n')
	for word in ctm.word_intervals:
		f.write(f'word {word.begin:.3f} {word.end:.3f} {word.label}\n')
		for phone in word.phones:
			f.write(f'phone {phone.begin:.3f} {phone.end:.3f} {phone.label}\n')
print(f'{len(alignment.alignment)} frames, {len(text.split())} words, likelihood {alignment.likelihood}')
