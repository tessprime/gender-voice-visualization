"""Hovering a clip fans it out into its vowels."""

CLIP = 'Morgan'


def open_constellation(page):
    page.wait_for_function("title => globalState.get('clips').some(c => c.title == title && c.marker)",
                           arg=CLIP)
    marker = page.evaluate_handle("title => globalState.get('clips').find(c => c.title == title).marker",
                                  CLIP)
    marker.as_element().hover()
    page.wait_for_selector('.constellation .vowel-dot')


def test_hovering_a_clip_shows_its_vowels(page):
    open_constellation(page)
    expected = page.evaluate("title => vowelGroups(globalState.get('clips').find(c => c.title == title)).length",
                             CLIP)
    assert page.locator('.constellation .vowel-dot').count() == expected > 0


def test_hovering_a_vowel_shows_each_instance(page):
    open_constellation(page)
    dot = page.locator('.constellation .vowel-dot').first
    dot.hover()
    page.wait_for_selector('.constellation .vowel-instance.shown')
    assert page.locator('.constellation .vowel-instance.shown').count() >= 1


def test_closes_after_the_pointer_leaves(page):
    open_constellation(page)
    page.mouse.move(5, 5)
    page.wait_for_selector('.constellation', state='detached', timeout=3000)


def test_clicking_a_vowel_plays_each_instances_word_in_order(page):
    # Record what Web Audio is asked to play.
    page.evaluate("""() => {
        window.playedSegments = [];
        const start = AudioBufferSourceNode.prototype.start;
        AudioBufferSourceNode.prototype.start = function(when, offset, duration) {
            window.playedSegments.push(offset);
            return start.apply(this, arguments);
        };
    }""")
    open_constellation(page)
    dot = page.locator('.constellation .vowel-dot').first
    expected = page.evaluate("""([title, label]) => {
        const clip = globalState.get('clips').find(c => c.title == title);
        return vowelGroups(clip).find(g => g.label == label).instances.map(i => i.wordStart).sort((a, b) => a - b);
    }""", [CLIP, dot.text_content()])

    dot.click()
    page.wait_for_selector('.constellation .vowel-dot.playing')
    page.wait_for_selector('.constellation .vowel-instance.current .vowel-label:not(:empty)')
    page.wait_for_selector('.constellation .vowel-dot.playing', state='detached', timeout=30_000)

    played = page.evaluate('window.playedSegments')
    assert len(played) == len(expected)
    # Each word starts a little early, for context.
    assert all(0 <= start - offset <= 0.05 for offset, start in zip(played, expected))
    assert page.log.errors == []


def test_clicking_a_playing_vowel_stops_it(page):
    open_constellation(page)
    dot = page.locator('.constellation .vowel-dot').first
    dot.click()
    page.wait_for_selector('.constellation .vowel-dot.playing')
    dot.click()
    assert page.locator('.constellation .vowel-dot.playing').count() == 0
    assert page.locator('.constellation .vowel-instance.current').count() == 0
