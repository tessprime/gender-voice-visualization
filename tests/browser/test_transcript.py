"""The details panel's transcript highlights the word being heard."""

CLIP = 'Morgan'


def highlighted(page):
    return page.evaluate("Array.from(document.querySelectorAll('#preview-transcript .current'))"
                         ".map(e => e.textContent)")


def test_words_are_matched_to_the_alignment(page):
    pieces = page.evaluate("""() => {
        const phones = [
            {word_index: 0, word: {word: ''}},
            {word_index: 1, word: {word: 'kings'}},
            {word_index: 2, word: {word: '<unk>'}},   // heard as one unknown word
            {word_index: 3, word: {word: 'lose'}},
            {word_index: 4, word: {word: "don't"}},
        ];
        return transcriptPieces('Kings\u2014nor lose, \u201cdon\u2019t', phones)
            .filter(p => p.wordIndices.length).map(p => [p.text, p.wordIndices]);
    }""")
    assert pieces == [['Kings', [1]], ['nor', [2]], ['lose,', [3]], ['\u201cdon\u2019t', [4]]]


def test_transcript_is_text_not_html(page):
    page.evaluate("""() => {
        const clip = globalState.get('clips').find(c => c.title == 'Bob');
        clip.transcript = '<img src=x onerror="window.injected = true"> hello';
        globalState.set('previewClip', clip);
    }""")
    assert page.locator('#preview-transcript img').count() == 0
    assert '<img' in page.text_content('#preview-transcript')


def test_player_highlights_the_word_at_the_playback_position(page):
    page.evaluate("""title => {
        const clip = globalState.get('clips').find(c => c.title == title);
        globalState.set('playingClip', clip);
        globalState.set('previewClip', clip);
        globalState.set('playbackTime', clip.phones.find(p => p.word.word == 'advisor').time + .01);
    }""", CLIP)
    assert highlighted(page) == ['advisor']


def test_vowel_playback_highlights_each_word(page):
    page.wait_for_function("title => globalState.get('clips').some(c => c.title == title && c.marker)", arg=CLIP)
    page.evaluate_handle("title => globalState.get('clips').find(c => c.title == title).marker",
                        CLIP).as_element().hover()
    page.locator('.constellation .vowel-dot', has_text='AE (cat)').click()
    page.wait_for_selector('#preview-transcript .current')
    label = page.text_content('.constellation .vowel-instance.current .vowel-label')
    assert [word.strip(',."').lower() for word in highlighted(page)] == [label]

    page.wait_for_selector('.constellation .vowel-dot.playing', state='detached', timeout=30_000)
    assert highlighted(page) == []


def test_clicking_a_word_plays_from_it(page):
    # Another clip is in the player; clicking a word switches to this one.
    start = page.evaluate("""title => {
        const clips = globalState.get('clips');
        globalState.set('playingClip', clips.find(c => c.title == 'Bob'));
        const clip = clips.find(c => c.title == title);
        globalState.set('previewClip', clip);
        return clip.phones.find(p => p.word.word == 'advisor').time;
    }""", CLIP)
    page.locator('#preview-transcript .transcript-word', has_text='advisor').click()
    assert page.evaluate("globalState.get('playingClip').title") == CLIP
    assert page.evaluate("globalState.get('playing')")
    page.wait_for_function("t => !$('audio.clip').paused && $('audio.clip').currentTime > t", arg=start)
    assert page.evaluate("$('audio.clip').currentTime") < start + 1.5
    assert 'advisor' in highlighted(page)
    assert page.log.errors == []


def test_clicking_the_first_word_goes_back_to_the_start(page):
    page.evaluate("""title => {
        const clip = globalState.get('clips').find(c => c.title == title);
        globalState.set('previewClip', clip);
        // As if it had no leading silence.
        clip.phones.find(p => p.word && p.word.word).time = 0;
        showTranscript(clip);
        globalState.set('playingClip', clip);
    }""", CLIP)
    page.wait_for_function("$('audio.clip').readyState >= 1")
    page.evaluate("globalState.set('playbackTime', 3)")
    page.wait_for_function("Math.abs($('audio.clip').currentTime - 3) < .1")
    page.locator('#preview-transcript .transcript-word').first.click()
    page.wait_for_function("!$('audio.clip').paused")
    assert page.evaluate("$('audio.clip').currentTime") < 1


def test_selecting_text_doesnt_seek(page):
    page.evaluate("""title => {
        const clip = globalState.get('clips').find(c => c.title == title);
        globalState.set('previewClip', clip);
        globalState.set('playingClip', clip);
    }""", CLIP)
    # Once the page has settled: the player has switched to its WAV
    # (test_player.py) and the spectrogram is drawn, which moves the
    # transcript.
    page.wait_for_function("$('audio.clip').src.startsWith('blob:') && $('#preview-spectrogram').audio")
    page.wait_for_timeout(200)
    words = page.locator('#preview-transcript .transcript-word')
    first, second = words.nth(0).bounding_box(), words.nth(2).bounding_box()
    page.mouse.move(first['x'] + 2, first['y'] + first['height'] / 2)
    page.mouse.down()
    page.mouse.move(second['x'] + second['width'] - 2, second['y'] + second['height'] / 2, steps=5)
    page.mouse.up()
    assert page.evaluate("window.getSelection().toString()") != ''
    assert not page.evaluate("globalState.get('playing')")
