"""Groups, tags and the Clips tab's folder tree (ui/tags.js, ui/clips.html)."""

from conftest import add_clip, wait_for_clip_or_alert
from test_storage import add_stored_clip, reload


def select(page, title):
    page.evaluate("t => globalState.set('previewClip', globalState.get('clips').find(c => c.title == t))", title)


def tag_in_details(page, title, tag):
    select(page, title)
    page.fill('#preview-tag-input', tag)
    page.press('#preview-tag-input', 'Enter')


def tags_of(page, title):
    return page.evaluate("t => globalState.get('clips').find(c => c.title == t).tags || []", title)


def shown_markers(page):
    """Titles of the clips whose markers the graph shows."""
    return page.evaluate("""globalState.get('clips')
        .filter(c => c.marker && !c.marker.classList.contains('filtered-out')).map(c => c.title)""")


def open_clips(page):
    page.click('.tab-set button.clips')


def test_tags_are_added_and_removed_in_the_details_tab(page):
    add_stored_clip(page, 'Mine')
    tag_in_details(page, 'Mine', 'week 1')
    tag_in_details(page, 'Mine', 'Morning, week 1, WEEK 1')
    assert tags_of(page, 'Mine') == ['week 1', 'Morning']
    assert page.locator('#preview-tags .tag-chip').all_text_contents() == ['week 1×', 'Morning×']

    page.click('#preview-tags .remove-tag[title*="week 1"]')
    assert tags_of(page, 'Mine') == ['Morning']
    assert page.log.errors == []


def folder(page, folder_id):
    return page.locator(f"li.folder[data-folder='{folder_id}']")


def folder_box(page, folder_id):
    return folder(page, folder_id).locator('> .row input[type=checkbox]')


def box_state(locator):
    return locator.evaluate("b => b.indeterminate ? 'some' : b.checked ? 'all' : 'none'")


def open_folder(page, folder_id):
    if folder(page, folder_id).get_attribute('aria-expanded') == 'false':
        folder(page, folder_id).locator('> .row .twisty').click()


def clip_box(page, folder_id, title):
    return folder(page, folder_id).locator(f"> ul > li.clip:has(.name:text-is('{title}')) input")


def test_the_clips_tab_is_a_folder_tree(page):
    add_stored_clip(page, 'Mine <i>1</i>')
    open_clips(page)
    # My recordings starts open, Examples closed.
    assert folder(page, 'mine').get_attribute('aria-expanded') == 'true'
    assert folder(page, 'examples').get_attribute('aria-expanded') == 'false'
    assert folder(page, 'mine').locator('li.clip .name').all_text_contents() == ['Mine <i>1</i>']
    assert folder(page, 'examples').locator('> .row .count').text_content() == '(7)'
    assert 'Add tags' in folder(page, 'tags').text_content()

    open_folder(page, 'examples')
    assert folder(page, 'examples').locator('li.clip .name').count() == 7
    # Clicking a clip selects it, staying on the Clips tab.
    page.click("li[data-folder=examples] li.clip .name >> text='Quinn'")
    assert page.evaluate("globalState.get('previewClip').title") == 'Quinn'
    assert page.locator('.current-tab > section.clips').is_visible()
    assert page.locator("li.clip.current .name").text_content() == 'Quinn'


def test_checkboxes_choose_what_the_graph_shows(page):
    add_stored_clip(page, 'One')
    add_stored_clip(page, 'Two')
    open_clips(page)
    everything = page.evaluate("globalState.get('clips').length")
    assert len(shown_markers(page)) == everything
    assert box_state(folder_box(page, 'mine')) == 'all'
    assert page.locator('#clip-tree-summary').text_content() == ''

    clip_box(page, 'mine', 'One').uncheck()
    assert 'One' not in shown_markers(page)
    assert box_state(folder_box(page, 'mine')) == 'some'
    assert 'Showing %d of %d' % (everything - 1, everything) in page.locator('#clip-tree-summary').text_content()

    # A half-ticked folder's box shows all of it; a ticked one hides all of it.
    folder_box(page, 'mine').click()
    assert box_state(folder_box(page, 'mine')) == 'all'
    folder_box(page, 'examples').click()
    assert sorted(shown_markers(page)) == ['One', 'Two']
    assert box_state(folder_box(page, 'examples')) == 'none'

    page.click('#show-all-clips')
    assert len(shown_markers(page)) == everything


def test_tag_folders(page):
    add_stored_clip(page, 'Week 1')
    add_stored_clip(page, 'Week 2')
    tag_in_details(page, 'Week 1', 'week 1')
    tag_in_details(page, 'Week 2', 'week 2')
    tag_in_details(page, 'Week 2', 'morning')
    tag_in_details(page, 'Quinn', 'morning')
    open_clips(page)
    tags = folder(page, 'tags')
    assert tags.locator('> ul > li.folder > .row .name').all_text_contents() == ['morning', 'week 1', 'week 2']
    assert tags.locator('> .row .count').text_content() == '(3)'

    # Unticking a tag folder hides its clips, wherever else they are.
    folder_box(page, 'tag:morning').uncheck()
    assert 'Week 2' not in shown_markers(page) and 'Quinn' not in shown_markers(page)
    assert 'Week 1' in shown_markers(page)
    assert box_state(folder_box(page, 'tag:week 2')) == 'none'
    assert box_state(folder_box(page, 'mine')) == 'some'
    assert box_state(folder_box(page, 'tags')) == 'some'
    # A clip's tags are listed next to it.
    open_folder(page, 'tag:week 2')
    assert folder(page, 'tag:week 2').locator('li.clip .clip-tags').text_content() == 'week 2, morning'


def test_what_is_shown_and_open_is_kept(page):
    add_stored_clip(page, 'Kept')
    add_stored_clip(page, 'Hidden')
    tag_in_details(page, 'Kept', 'week 3')
    tag_in_details(page, 'Quinn', 'target')
    open_clips(page)
    clip_box(page, 'mine', 'Hidden').uncheck()
    open_folder(page, 'examples')
    page.wait_for_function("clipStore.records().then(rs => rs.some(r => r.clip.tags && r.clip.tags[0] == 'week 3'))")

    reload(page)
    page.wait_for_function("['Kept', 'Hidden', 'Quinn'].every(t => globalState.get('clips').some(c => c.title == t))")
    assert tags_of(page, 'Kept') == ['week 3']
    assert tags_of(page, 'Quinn') == ['target']
    assert 'Hidden' not in shown_markers(page)
    assert 'Kept' in shown_markers(page)
    open_clips(page)
    assert folder(page, 'examples').get_attribute('aria-expanded') == 'true'


def test_tags_given_when_adding_a_clip(page, example):
    page.evaluate("""() => {
        const clip = globalState.get('clips').find(c => c.title == 'Quinn');
        setClipTags(clip, ['Week 4']);
    }""")
    add_clip(page, 'Tagged', example['audio_path'], example['transcript'], tags='week 4, evening')
    assert wait_for_clip_or_alert(page, 'Tagged') is not None
    # The existing spelling isn't forced on it, but it matches the same tag.
    assert tags_of(page, 'Tagged') == ['week 4', 'evening']
    open_clips(page)
    tag_names = folder(page, 'tags').locator('> ul > li.folder > .row .name').all_text_contents()
    assert tag_names == ['evening', 'Week 4']
    page.wait_for_function("clipStore.records().then(rs => rs.length == 1 && rs[0].clip.tags.length == 2)")


def test_clicking_a_dot_stays_on_the_current_tab(page):
    open_clips(page)
    page.evaluate("globalState.get('clips').find(c => c.title == 'Quinn').marker.click()")
    assert page.evaluate("globalState.get('previewClip').title") == 'Quinn'
    assert page.locator('.current-tab > section.clips').is_visible()
