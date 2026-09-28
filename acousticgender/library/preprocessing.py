import subprocess, os, glob, shutil, sys
import magic

from . import settings as settings_module

settings = settings_module.settings

def process(uploaded_file, transcript, tmp_dir):
	################## Noise Removal ##################

	os.mkdir(tmp_dir)
	filetype = magic.from_buffer(uploaded_file)

	input_file    = tmp_dir + '/orig'
	format_file   = tmp_dir + '/format.wav'
	silence_file  = tmp_dir + '/silence.wav'
	clean_file    = tmp_dir + '/clean.wav'
	noise_profile = tmp_dir + '/noise.prof'

	with open(input_file, "wb") as f: 
		f.write(uploaded_file)

	assert(os.path.exists(input_file))

	try:
		subprocess.check_output(['ffmpeg', '-i', input_file, format_file])

		ffmpeg_silence = subprocess.check_output([
				'ffmpeg', '-i', input_file, 
				'-af', 'silencedetect=n=-30dB:d=0.5', 
				'-f', 'null', '-'
		], stderr=subprocess.STDOUT).decode('utf-8').split('\n')

		silence_ranges = list(zip(
				[line.split(" ")[4] for line in ffmpeg_silence 
						if 'silence_start' in line],
				[line.split(" ")[4] for line in ffmpeg_silence
						if 'silence_end' in line]
		))

		subprocess.check_output(['ffmpeg', '-i', input_file, 
				'-af', "aselect='" + '+'.join(
						['between(t,' + r[0] + ',' + r[1]+')' for r in silence_ranges]
				) + "', asetpts=N/SR/TB", 
				silence_file
		])

		assert(os.path.exists(silence_file))

		subprocess.check_output([
				'sox', silence_file, '-n', 'noiseprof', noise_profile
		])
		subprocess.check_output(['chmod', '777', noise_profile])
		subprocess.check_output([
				'sox', format_file, clean_file, 
				'noisered', noise_profile, '0.2'
		])

		assert(os.path.exists(clean_file))
	except e:
		clean_file = input_file

	################## Forced Alignment ##################
	corpus_dir = tmp_dir + '/corpus'
	output_dir = tmp_dir + '/output'
	os.mkdir(corpus_dir)
	os.mkdir(output_dir)

	subprocess.check_output([
		'ffmpeg' , 
		'-i'     , clean_file,
		'-acodec', 'pcm_s16le',
		'-ac'    , '1',
		'-ar'    , '16000',
		corpus_dir + '/recording.wav'
	])

	subprocess.run(['chmod', '777', '-R', tmp_dir])

	with open(corpus_dir + '/recording.txt', 'w') as f:
		f.write(transcript)

	with open(tmp_dir + '/align.sh', 'w') as f:
		f.write("""#!/usr/bin/env bash
		source /opt/conda/etc/profile.d/conda.sh
		conda activate aligner
		mfa align ./corpus/ english english ./output/ --clean
		""")

	assert(os.path.exists(tmp_dir + '/align.sh'))

	subprocess.check_output(['chmod', '777', tmp_dir + '/align.sh'])
	cwd = os.getcwd()
	os.chdir(tmp_dir)

	try:
		# shell out so we can `source`
		align_output = subprocess.check_output(['./align.sh'], stderr=subprocess.STDOUT) 
	except subprocess.CalledProcessError as e:
		align_output = e.output
		# stdout is the HTTP response; diagnostics go to stderr (the server log).
		print(e, file=sys.stderr)
		print(str(e.output, 'utf-8'), file=sys.stderr)
	except Exception as e:
		align_output = str(e).encode('utf-8')
		print("Error running align.sh:", e, file=sys.stderr)
	
	os.chdir(cwd)

	# Keep the aligner's console output and MFA's own logs next to the clip.
	# MFA's working directory is shared by every run and wiped on the next one.
	with open(tmp_dir + '/align.log', 'wb') as f:
		f.write(align_output)
	mfa_root = os.environ.get('MFA_ROOT_DIR', os.path.expanduser('~/Documents/MFA'))
	for log in glob.glob(mfa_root + '/corpus/**/log/*.log', recursive=True):
		dest = tmp_dir + '/mfa_logs/' + os.path.relpath(log, mfa_root + '/corpus')
		os.makedirs(os.path.dirname(dest), exist_ok=True)
		shutil.copy(log, dest)


	################## Phonetic Processing ##################
	for recording, grid in zip(
		glob.glob(corpus_dir + '/*.wav'), 
		glob.glob(output_dir + '/*.TextGrid')
	):
		praat_output = subprocess.check_output([
			'./textgrid-formants.praat', recording, grid
		]).decode('utf-8')

		with open(grid.replace('.TextGrid', '.tsv'), 'w') as f:
			f.write(praat_output)

		if not settings['dev']:
			shutil.rmtree(tmp_dir)
		return praat_output
