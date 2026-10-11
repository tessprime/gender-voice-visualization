import re

# ARPABET phonemes by how air flows through the vocal tract. Vowels and
# sonorants are voiced with little obstruction, so they have real formants;
# obstruents block or constrict the air (silence, bursts, hiss), so formant
# measurements for them are mostly artifacts. Keep in sync with
# phoneClass() in ui/util.js.
VOWELS = {'AA', 'AE', 'AH', 'AO', 'AW', 'AY', 'EH', 'ER', 'EY', 'IH', 'IY',
          'OW', 'OY', 'UH', 'UW'}
SONORANTS = {'M', 'N', 'NG', 'L', 'R', 'W', 'Y'}
OBSTRUENTS = {'P', 'B', 'T', 'D', 'K', 'G', 'F', 'V', 'TH', 'DH', 'S', 'Z',
              'SH', 'ZH', 'HH', 'CH', 'JH'}

def phone_class(phoneme):
	"""'vowel', 'sonorant' or 'obstruent', or None for silence and unknown
	labels. Stress digits (AH0, AH1) are ignored."""
	base = re.sub(r'\d', '', phoneme or '')
	if base in VOWELS: return 'vowel'
	if base in SONORANTS: return 'sonorant'
	if base in OBSTRUENTS: return 'obstruent'
	return None

def parse(praat_output):
	word_lines = []
	phoneme_lines = []
	active_list = None

	for line in praat_output.split('\n'):
		if line == "Words:":
			active_list = word_lines
			continue
		if line == "Phonemes:":
			active_list = phoneme_lines
			continue

		active_list.append(line)	

	data = {}

	pronunciation_dict = {}
	with open('cmudict.txt', 'r', encoding='iso-8859-1') as f:
		for line in f.readlines():
			cols = line.split()
			pronunciation_dict[cols[0]] = cols[1:]

	data['words'] = []
	for line in word_lines:
		cols = line.split('\t')
		data['words'].append({
			'time' : float(cols[0]),
			'word' : cols[1],
			'expected' : (pronunciation_dict.get(cols[1].upper()) or [None]) + [None] * 10
		})

	data['phones'] = []
	word_index = -1
	phoneme_in_word_index = 0
	for line in phoneme_lines:	
		cols = line.split('\t')

		if len(cols) < 3: continue

		time = float(cols[0]) if re.match(r'^-?\d+(?:\.\d+)?$', cols[0]) else None
		while (
			type(time) == float and 
			word_index < len(data['words']) - 1 and
			time >= data['words'][word_index + 1]['time']
		):
			word_index += 1
			phoneme_in_word_index = 0
			
		data['phones'].append({
			'time': time,
			'phoneme': cols[1],
			'class': phone_class(cols[1]),
			'word_index': word_index,
			'word': data['words'][word_index],
			'word_time': data['words'][word_index]['time'],
			'expected': data['words'][word_index]['expected'][phoneme_in_word_index],
			'F': [None if '--' in f else float(f) for f in cols[2:]]
		})
		phoneme_in_word_index += 1

	return data
