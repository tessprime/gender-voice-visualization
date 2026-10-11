"""Recordings are analysed in the browser, without uploading them."""

import statistics

from conftest import add_clip, wait_for_clip_or_alert


def test_upload_is_analysed_in_the_browser(page, example):
    add_clip(page, 'Test clip', example['audio_path'], example['transcript'])
    clip = wait_for_clip_or_alert(page, 'Test clip')

    assert page.log.dialogs == []
    assert clip is not None
    assert page.log.non_get == [], 'the recording was uploaded'
    assert page.log.errors == []

    # The stored example was analysed by the server, with noise reduction the
    # browser doesn't do, so expect close, not identical, results.
    # Words with several pronunciations ("dog": AA1 or AO1) can go either way.
    silence = {'', 'sil', 'sp'}
    phonemes = [p['phoneme'] for p in clip['phones'] if p['phoneme'] not in silence]
    expected = [p['phoneme'] for p in example['phones'] if p['phoneme'] not in silence]
    assert len(phonemes) == len(expected)
    assert sum(a != b for a, b in zip(phonemes, expected)) <= 3

    offsets = [abs(a['time'] - b['time']) for a, b in zip(clip['phones'], example['phones'])]
    assert statistics.median(offsets) <= 0.03
    assert max(offsets) <= 0.15

    assert abs(clip['medianPitch'] / example['medianPitch'] - 1) < 0.05
    assert abs(clip['medianResonance'] - example['medianResonance']) < 0.06

    # Some vowels go unmeasured (no pitch found); about as many as on the server.
    def measured_vowels(phones):
        return sum(1 for p in phones if any(c.isdigit() for c in p['phoneme'])
                   and p['F'][0] and p.get('resonance') is not None)
    assert measured_vowels(clip['phones']) >= measured_vowels(example['phones']) - 3


def test_mismatched_transcript_fails_with_a_reason(page, example):
    transcript = 'When the sunlight strikes raindrops in the air, they act as a prism. ' * 8
    add_clip(page, 'Bad clip', example['audio_path'], transcript)
    clip = wait_for_clip_or_alert(page, 'Bad clip')

    assert clip is None
    assert len(page.log.dialogs) == 1
    assert "couldn't be matched to the transcript" in page.log.dialogs[0]
    assert page.log.non_get == []
