# Reference output from Praat for testing voicemeasure: the formant and pitch
# analyses textgrid-formants.praat uses, with every analysis frame written
# out, so voicemeasure can be compared frame by frame.
#
#   praat --run dump_tracks.praat recording.wav out/recording
#
# writes out/recording-formant.tsv and out/recording-pitch.tsv.

form Dump tracks
	sentence soundfile
	sentence outprefix
endform

Read from file: soundfile$
sound = selected("Sound")

# Same settings as textgrid-formants.praat.
To Formant (burg): 0, 5, 5000, 0.025, 50
formant = selected("Formant")
# Frame number, time (6 decimals), no intensity, number of formants,
# frequencies (3 decimals), bandwidths.
Down to Table: "yes", "yes", 6, "no", 3, "yes", 3, "yes"
Save as tab-separated file: outprefix$ + "-formant.tsv"
Remove

selectObject: sound
To Pitch: 0, 75, 600
pitch = selected("Pitch")
numberOfFrames = Get number of frames
path$ = outprefix$ + "-pitch.tsv"
writeFileLine: path$, "frame", tab$, "time(s)", tab$, "F0(Hz)"
for frame from 1 to numberOfFrames
	time = Get time from frame number: frame
	f0 = Get value in frame: frame, "Hertz"
	appendFileLine: path$, frame, tab$, fixed$(time, 6), tab$, fixed$(f0, 3)
endfor
