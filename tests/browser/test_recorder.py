"""Recording from the microphone (a fake one the browser provides)."""

import pytest


def record(page, seconds):
    previous = page.get_attribute('#recording-preview', 'src') or ''
    page.click('#start-recording')
    page.wait_for_function("!$('#stop-recording').disabled")
    page.wait_for_timeout(seconds * 1000)
    page.click('#stop-recording')
    page.wait_for_function("previous => ($('#recording-preview').src || '') != previous",
                           arg=previous)
    return page.get_attribute('#recording-preview', 'src')


def test_each_take_holds_only_its_own_audio(page, browser_name):
    if browser_name == 'webkit':
        pytest.skip("Playwright's WebKit has no fake microphone")
    page.click('button.new-clip')
    page.check('#record-voice')

    first = record(page, 2)
    second = record(page, 2)

    assert page.log.dialogs == []
    # A bug once appended every earlier take's audio again on each new take,
    # so the second take came out about twice as long as the first.
    assert 0.6 < len(second) / len(first) < 1.5


def test_shows_the_live_spectrogram_while_recording(page, browser_name):
    if browser_name == 'webkit':
        pytest.skip("Playwright's WebKit has no fake microphone")
    page.click('button.new-clip')
    page.check('#record-voice')
    page.click('#start-recording')
    page.wait_for_function("document.querySelector('#live-spectrogram').stream")
    page.wait_for_function("document.querySelector('#live-spectrogram')._history.write > 50")
    page.click('#stop-recording')
    page.wait_for_function("!document.querySelector('#live-spectrogram').stream")
    # The picture stays after stopping, and the scale menu changes it.
    page.select_option('#live-max-frequency', '500')
    labels = page.evaluate("Array.from(document.querySelector('#live-spectrogram').shadowRoot"
                           ".querySelectorAll('.axis span')).map(s => s.textContent)")
    assert labels[-1] == '500 Hz'
    # The recording view starts on a log axis from 75 Hz.
    assert page.evaluate("document.querySelector('#live-spectrogram').frequencyScale") == \
        {'min': 75, 'max': 500, 'log': True}
    assert page.evaluate("!!document.querySelector('#live-spectrogram')._history")
    assert page.log.errors == []
