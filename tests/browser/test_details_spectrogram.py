"""The details panel's spectrogram (components/voice-spectrogram in the app)."""

import pytest

CLIP = 'Morgan'


def spectrogram(page, expression):
    return page.evaluate(f"(() => {{ const view = document.querySelector('#preview-spectrogram'); return {expression}; }})()")


@pytest.fixture
def details(page):
    page.wait_for_function("title => globalState.get('clips').some(c => c.title == title && c.marker)", arg=CLIP)
    page.evaluate_handle("title => globalState.get('clips').find(c => c.title == title).marker",
                        CLIP).as_element().click()
    page.wait_for_function("document.querySelector('#preview-spectrogram').duration > 0")
    return page


def test_shows_the_selected_clip(details):
    duration, words, view = spectrogram(details, '[view.duration, view.words.length, [view.viewStart, view.viewEnd]]')
    assert duration == pytest.approx(30, abs=2)
    assert words > 80
    assert view == [0, 6]
    assert details.log.errors == []


def test_clicking_a_word_plays_from_it(details):
    details.locator('#preview-spectrogram').locator('.words .segment', has_text='advisor').click()
    start = spectrogram(details, "view.words.find(w => w.label == 'advisor').start")
    assert details.evaluate("globalState.get('playing')") is True
    assert details.evaluate("globalState.get('playbackTime')") >= start - 0.01
    details.evaluate("globalState.set('playing', false)")


def test_follows_the_player(details):
    details.evaluate("globalState.set('playbackTime', 13.6)")
    view_start, view_end, current = spectrogram(
        details, "[view.viewStart, view.viewEnd, view.currentTime]")
    assert current == pytest.approx(13.6)
    assert view_start < 13.6 < view_end


def test_points_at_the_vowel_a_constellation_plays(details):
    details.evaluate_handle("title => globalState.get('clips').find(c => c.title == title).marker",
                           CLIP).as_element().hover()
    details.locator('.constellation .vowel-dot', has_text='AE (cat)').click()
    details.wait_for_function("document.querySelector('.vowel-instance.current')")
    current = spectrogram(details, "Array.from(view.shadowRoot.querySelectorAll('.segment.current')).map(s => s.textContent)")
    assert current[1] == 'AE1'


def test_scale_menu_changes_the_frequency_axis(details):
    details.select_option('#preview-max-frequency', '1000')
    top = spectrogram(details, "Array.from(view.shadowRoot.querySelectorAll('.axis span')).pop().textContent")
    assert top == '1 kHz'


def test_log_scale_menu(details):
    details.select_option('#preview-frequency-scale', 'log')
    details.select_option('#preview-max-frequency', '1000')
    scale = spectrogram(details, 'view.frequencyScale')
    assert scale == {'min': 75, 'max': 1000, 'log': True}
    assert details.input_value('#preview-min-frequency') == '75'
    details.select_option('#preview-min-frequency', '100')
    assert spectrogram(details, 'view.frequencyScale.min') == 100
