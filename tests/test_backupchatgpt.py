"""Backup contracts; scraper semantics remain tested in tools/aiscrapers."""
import asyncio
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import backupchatgpt as b


def messages():
    return [{"id": str(uuid4()), "role": role, "content": role, "parts": [{"type": "text", "text": role}]} for role in ("user", "assistant")]


def test_revision_idempotence_and_partial_rejection(tmp_path):
    rows = b.records(messages(), "chat")
    path = tmp_path / "chat.jsonl"
    assert b.save(path, rows, "markdown")
    stamp = path.stat().st_mtime_ns
    assert not b.save(path, rows, "markdown")
    assert path.stat().st_mtime_ns == stamp
    changed = [dict(row) for row in rows]
    changed[1]["content"] = "edited"
    changed = b.records(changed, "chat")
    assert b.save(path, changed, "edited markdown")
    revision = next((tmp_path / ".revisions" / "chat").glob("*.jsonl"))
    assert b.read_rows(revision, "chat") == rows
    with pytest.raises(ValueError, match="missing previously"):
        b.validate(changed[:1], changed)
    assert b.read_rows(path, "chat") == changed


def test_ids_hashes_and_corruption(tmp_path):
    rows = b.records(messages(), "chat")
    b.validate(rows, [])
    for broken in ([], [rows[0], rows[0]], [dict(rows[0], id="user-1")]):
        with pytest.raises(ValueError):
            b.validate(broken, [])
    path = tmp_path / "chat.jsonl"
    path.write_text(json.dumps(dict(rows[0], content="corrupt")) + "\n")
    with pytest.raises(ValueError, match="hash"):
        b.read_rows(path, "chat")


@pytest.mark.parametrize('roles', [
    ('user', 'user', 'assistant'),  # An interrupted response.
    ('user', 'assistant', 'user'),  # A request not to respond.
    ('assistant', 'assistant'),  # Scheduled messages.
    ('user',),
])
def test_valid_role_sequences_survive_save_and_reload(tmp_path, roles):
    cid = str(uuid4())
    rows = b.records([dict(id=str(uuid4()), role=role, content=role) for role in roles], cid)
    path = tmp_path / b.filename('chat', cid)
    b.validate(rows, [])
    b.save(path, rows, 'markdown')
    assert b.read_rows(path, cid) == rows
    replacement = b.records([dict(id=str(uuid4()), role='assistant', content='new')], cid)
    with pytest.raises(b.IncompleteChat, match='missing previously'):
        b.validate(replacement, rows)


def test_interrupted_activity_has_explicit_local_identity_and_prompt(tmp_path):
    cid = str(uuid4())
    prompt = dict(id=str(uuid4()), role='user', content='Question')
    activity = dict(id=f"local-activity:{prompt['id']}:0", idSource='local-activity', role='assistant', content='Interrupted progress')
    rows = b.records([prompt, activity], cid)
    path = tmp_path / b.filename('chat', cid)
    b.validate(rows, [])
    b.save(path, rows, 'markdown')
    assert b.read_rows(path, cid) == rows
    assert b.unchanged_anchor([activity], rows) is None
    for broken in ([activity], [prompt, dict(activity, idSource='')], [prompt, dict(activity, role='user')]):
        with pytest.raises(b.IncompleteChat):
            b.validate(broken, [])
    with pytest.raises(b.IncompleteChat, match='local activity changed'):
        b.validate(b.records([prompt, dict(activity, content='different')], cid), rows)
    with pytest.raises(b.IncompleteChat, match='local activity changed'):
        b.validate(b.records([prompt, dict(activity, content='different')], cid), rows[:1], rows)
    with pytest.raises(b.IncompleteChat, match='local activity missing'):
        b.validate(b.records([prompt], cid), rows[:1], rows)


def test_selection_rotates_oldest_and_retries_incomplete():
    ids = [str(uuid4()) for _ in range(4)]
    catalog = {ids[i]: {"title": str(i), "checked": checked} for i, checked in enumerate(["", "2026-10-18", "2026-10-01", "2026-10-19"])}
    selected = b.select(catalog, [], "", False, 3, "2026-10-19")
    assert [key for key, _ in selected] == [ids[0], ids[2], ids[1]]
    assert b.select(catalog, [ids[3]], "", False, 1, "2026-10-19")[0][0] == ids[3]


def test_source_is_read_each_injection(tmp_path, monkeypatch):
    monkeypatch.setattr(b, "SCRAPERS", tmp_path)
    for name in b.SOURCES:
        (tmp_path / name).write_text("window.sourceVersion=1;")
    class Page:
        async def evaluate(self, source):
            self.source = source
    page = Page()
    asyncio.run(b.inject(page))
    assert "sourceVersion=1" in page.source
    (tmp_path / b.SOURCES[-1]).write_text("window.sourceVersion=2;")
    asyncio.run(b.inject(page))
    assert "sourceVersion=2" in page.source


def test_interrupted_markdown_repair(tmp_path):
    rows = b.records(messages(), "chat")
    path = tmp_path / "chat.jsonl"
    b.save(path, rows, "markdown")
    path.with_suffix(".md").unlink()
    assert b.save(path, rows, "markdown")
    assert path.with_suffix(".md").read_text() == "markdown"


def test_title_rename_keeps_ids_and_prior_markdown(tmp_path):
    cid = str(uuid4())
    rows = b.records(messages(), cid)
    path = tmp_path / b.filename('Old/title', cid)
    b.save(path, rows, 'old markdown')
    assert b.save(path, rows, 'new markdown', 'New: title')
    new = tmp_path / b.filename('New: title', cid)
    assert not path.exists()
    assert b.read_rows(new, cid) == rows
    assert new.with_suffix('.md').read_text() == 'new markdown'
    assert next((tmp_path / '.revisions' / cid).glob('*.md')).read_text() == 'old markdown'
    assert len(b.filename('🙂' * 200, cid).encode()) < 255


def test_interruption_commits_only_finished_chats_and_resume(tmp_path, monkeypatch):
    from contextlib import asynccontextmanager
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    out = tmp_path / "output"
    cids = sorted([str(uuid4()), str(uuid4())])
    cache = tmp_path / ".cache/sanand-scripts/backupchatgpt" / b.digest(str(out.resolve()))[:16]
    cache.mkdir(parents=True)
    catalog = {cid: dict(title=cid, url=f'https://chatgpt.com/c/{cid}') for cid in cids}
    (cache / 'catalog.json').write_text(b.encoded(catalog))
    (cache / 'discovery.json').write_text(b.encoded(dict(attempted=b.time.time(), attempted_day=b.dt.datetime.now(b.dt.UTC).date().isoformat())))
    data = messages()
    class Page:
        cid = None
        async def evaluate(self, source, arg=None):
            if 'orderValid' in source:
                return dict(messages=data, metadata=dict(title=self.cid, date='2026-10-19', source=f'https://chatgpt.com/c/{self.cid}'), orderValid=True)
            if 'messagesToMarkdown' in source:
                return 'markdown'
    page = Page()
    @asynccontextmanager
    async def owned(url):
        yield page
    opened = []
    async def navigate(p, url, conversation=False):
        p.cid = b.identity(url)
        opened.append(p.cid)
        if len(opened) == 2:
            raise KeyboardInterrupt()
    async def sweep(*args, **kwargs):
        return dict(boundary=True)
    monkeypatch.setattr(b, 'owned_page', owned)
    monkeypatch.setattr(b, 'navigate', navigate)
    monkeypatch.setattr(b, 'sweep', sweep)
    monkeypatch.setattr(b, 'discovery_due', lambda *args: False)
    with pytest.raises(KeyboardInterrupt):
        asyncio.run(b.run('http://localhost', out, [], '', False, 2, False, 'jsonl', 10))
    state = json.loads((cache / 'catalog.json').read_text())
    assert state[cids[0]]['checked']
    assert not state[cids[0]]['pending']
    assert state[cids[1]]['pending'] and not state[cids[1]].get('checked')
    assert state[cids[1]]['error'] == 'KeyboardInterrupt'
    latest = json.loads((cache.parent / 'latest.json').read_text())
    assert latest['conversationId'] == cids[1]
    assert latest['position'] == 2 and latest['selected'] == 2 and latest['completed'] == 1
    assert latest['stage'] == 'opening'
    events = [json.loads(line) for path in cache.parent.glob('*-runs.jsonl') for line in path.read_text().splitlines()]
    assert any(e['event']=='conversation_start' and e['position']==2 for e in events)
    attempted = state[cids[1]]['attempted']
    monkeypatch.setattr(b.time, 'time', lambda: attempted + 901)
    asyncio.run(b.run('http://localhost', out, [], '', False, 2, False, 'jsonl', 10))
    assert opened == [cids[0], cids[1], cids[1]]
    assert not json.loads((cache / 'catalog.json').read_text())[cids[1]]['pending']
    path = out / b.filename(cids[1], cids[1])
    before = path.read_bytes()
    async def failed_sweep(page, sidebar, direction, steps, checkpoint, **kwargs):
        checkpoint(data)
        raise ValueError('history gap')
    monkeypatch.setattr(b, 'sweep', failed_sweep)
    with pytest.raises(ValueError, match='history gap'):
        asyncio.run(b.run('http://localhost', out, [cids[1]], '', False, 1, False, 'jsonl', 10))
    assert path.read_bytes() == before
    partial = next((out / '.incomplete' / cids[1]).glob('*.jsonl'))
    assert len(b.read_rows(partial, cids[1])) == 2
    assert json.loads(partial.with_suffix('.json').read_text())['status'] == 'incomplete'
    assert json.loads(partial.with_suffix('.json').read_text())['stage'] == 'scroll-down'
    # Explicit full rescans bypass the bottom-first incremental path.
    with pytest.raises(ValueError, match='history gap'):
        asyncio.run(b.run('http://localhost', out, [cids[1]], '', True, 1, True, 'jsonl', 10))
    assert json.loads((cache.parent/'latest.json').read_text())['stage']=='scroll-up'
    # A daily rerun during cooldown must make no browser connection at all.
    @asynccontextmanager
    async def no_browser(url):
        raise AssertionError('Redundant CDP connection')
        yield
    monkeypatch.setattr(b, 'owned_page', no_browser)
    asyncio.run(b.run('http://localhost', out, [], '', False, 2, False, 'jsonl', 10))


def test_project_urls_and_filename_identity():
    cid = str(uuid4())
    assert b.identity(f'https://chatgpt.com/g/project/c/{cid}?messageId=last') == cid
    assert b.file_id(Path(b.filename('Renamed [title]/new', cid))) == cid
    with pytest.raises(ValueError):
        b.identity(f'https://evil.example/c/{cid}')


def test_markdown_only_changes_keep_distinct_revisions(tmp_path):
    rows = b.records(messages(), 'chat')
    path = tmp_path / 'chat.jsonl'
    b.save(path, rows, 'one')
    b.save(path, rows, 'two')
    b.save(path, rows, 'three')
    assert {p.read_text() for p in (tmp_path / '.revisions/chat').glob('*.md')} == {'one', 'two'}


def test_failed_same_day_scan_stays_due_after_cooldown():
    cid = str(uuid4())
    catalog = {cid: dict(title='pending', checked='2026-10-19', pending=True, attempted=b.time.time())}
    assert not b.select(catalog, [], '', False, 1, '2026-10-19')
    catalog[cid]['attempted'] -= 901
    assert b.select(catalog, [], '', False, 1, '2026-10-19')[0][0] == cid


@pytest.mark.parametrize('boundary', [True, False])
def test_scroll_plateau_is_success_only_at_boundary(monkeypatch, boundary):
    async def no_sleep(*args):
        pass
    monkeypatch.setattr(b.asyncio, 'sleep', no_sleep)
    data = messages()
    class Page:
        async def evaluate(self, source, arg):
            if 'captured:' in source:
                return dict(captured=data, visible=[m['id'] for m in data], busy=False)
            return dict(top=0 if boundary else 40, height=200, viewport=100, before=0)
    if boundary:
        assert asyncio.run(b.sweep(Page(), False, -1, 5))['boundary']
    else:
        with pytest.raises(b.IncompleteChat, match='plateau'):
            asyncio.run(b.sweep(Page(), False, -1, 5))


def test_gap_retains_capture_for_incomplete_candidate(monkeypatch):
    data = messages()
    data[-1]['id'] = 'assistant-1'
    captured = []
    class Page:
        async def evaluate(self, source, arg):
            return dict(captured=data, visible=[m['id'] for m in data], busy=False)
    with pytest.raises(ValueError, match='Unstable'):
        asyncio.run(b.sweep(Page(), False, -1, 5, captured.extend))
    assert captured == data


def test_canonical_metadata_preserves_project_url_and_full_title(tmp_path):
    cid = str(uuid4())
    metadata = dict(title='Project / unsanitized title', date='2026-10-19', source=f'https://chatgpt.com/g/project-slug/c/{cid}')
    rows = b.records(messages(), cid, metadata)
    path = tmp_path / b.filename(metadata['title'], cid)
    b.save(path, rows, 'markdown')
    assert b.read_rows(path, cid)[0]['conversation'] == metadata
    assert b.records(rows, cid) == rows


def test_auth_failure_does_not_retry_navigation(monkeypatch):
    async def no_sleep(*args):
        pass
    monkeypatch.setattr(b.asyncio, 'sleep', no_sleep)
    class Page:
        navigations = 0
        async def command(self, method, **params):
            self.navigations += 1
            return {}
        async def evaluate(self, source):
            return dict(login=True, url='https://chatgpt.com/auth/login')
    page = Page()
    with pytest.raises(RuntimeError, match='authentication unavailable'):
        asyncio.run(b.navigate(page, 'https://chatgpt.com/'))
    assert page.navigations == 1


def test_describe_without_browser():
    from typer.testing import CliRunner
    result = CliRunner().invoke(b.app, ['--describe'])
    assert result.exit_code == 0
    schema = json.loads(result.stdout)
    assert schema['sources'] == [str(b.SCRAPERS / name) for name in b.SOURCES]
    assert next(p for p in schema['parameters'] if p['name']=='limit')['default'] == 20
    params = {p['name']: p for p in schema['parameters']}
    assert params['conversation']['type'] == 'text'
    assert params['conversation']['multiple'] is True
    assert params['limit']['type'] == 'integer'
    assert params['dry_run']['type'] == 'boolean'
    assert params['out_dir']['type'] == 'path'


def exported(cid, title='Export title', content='export body'):
    return f'# {title}\n\n- Link: https://chatgpt.com/c/{cid}\n\n## User\n\n{content}\n'


def test_shared_markdown_preserves_export_and_accepts_later_overwrite(tmp_path):
    cid = str(uuid4())
    shared = tmp_path / 'shared'
    shared.mkdir()
    canonical = tmp_path / 'data' / f'{cid}.md'
    canonical.parent.mkdir()
    canonical.write_text(f'---\nsource: "https://chatgpt.com/c/{cid}"\n---\n\nscraper markdown')
    target = shared / 'A title.md'
    original = exported(cid, 'A: title').replace('\n', '\r\n').encode()
    target.write_bytes(original)
    state = b.publish_markdown(canonical, cid, 'A: title', shared, b.markdown_index(shared), {})
    assert target.read_text() == canonical.read_text()
    assert original in [p.read_bytes() for p in (canonical.parent / '.revisions' / cid).glob('shared-*.md')]
    target.write_text(exported(cid, 'A: title', 'later export'))
    newer_export = target.read_bytes()
    state = b.publish_markdown(canonical, cid, 'A: title', shared, b.markdown_index(shared), state)
    assert not state['changed'] and target.read_bytes() == newer_export


def test_shared_duplicate_title_matches_by_id_and_renames_without_loss(tmp_path):
    cid, other = str(uuid4()), str(uuid4())
    shared = tmp_path / 'shared'
    shared.mkdir()
    canonical = tmp_path / f'{cid}.md'
    canonical.write_text(f'---\nsource: "https://chatgpt.com/c/{cid}"\n---\n\nnew')
    first, second = shared / 'Dup.md', shared / 'Dup (1).md'
    first.write_text(exported(other, 'Dup'))
    second.write_text(exported(cid, 'Dup'))
    untouched = first.read_bytes()
    state = b.publish_markdown(canonical, cid, 'Dup', shared, b.markdown_index(shared), {})
    assert state['file'] == second.name
    assert first.read_bytes() == untouched
    canonical.write_text(f'---\nsource: "https://chatgpt.com/c/{cid}"\n---\n\nrenamed')
    state = b.publish_markdown(canonical, cid, 'Renamed?', shared, b.markdown_index(shared), state)
    assert state['file'] == 'Renamed.md' and not second.exists()
    assert first.read_bytes() == untouched
    assert list((tmp_path / '.revisions' / cid).glob('shared-*.md'))


def test_shared_unknown_occupant_is_never_overwritten(tmp_path):
    cid = str(uuid4())
    shared = tmp_path / 'shared'
    shared.mkdir()
    (shared / 'Notes.md').write_text('my handwritten notes')
    canonical = tmp_path / f'{cid}.md'
    canonical.write_text(f'---\nsource: "https://chatgpt.com/c/{cid}"\n---\n')
    result = b.publish_markdown(canonical, cid, 'Notes', shared, b.markdown_index(shared), {})
    assert result['file'] == 'Notes (1).md'
    assert (shared / 'Notes.md').read_text() == 'my handwritten notes'


def test_real_converter_filenames_and_reexport(tmp_path):
    import shutil
    import subprocess
    converter = Path.home() / 'code/chatgpt-to-markdown/chatgpt-to-markdown.js'
    if not converter.exists() or not shutil.which('node'):
        pytest.skip('Sibling converter and Node required for integration test')
    shared, data = tmp_path / 'shared', tmp_path / 'data'
    shared.mkdir()
    data.mkdir()
    titles = ['A: title/with—punct', 'Dup', 'Dup', '日本語', 'Café ñ']
    conversations = [dict(title=title, conversation_id=str(uuid4()), create_time=i+1, update_time=10, mapping={}) for i,title in enumerate(titles)]
    source = 'import fs from "node:fs"; const {default:convert}=await import(process.argv[1]); await convert(JSON.parse(fs.readFileSync(0,"utf8")),process.argv[2]);'
    def convert():
        subprocess.run(['node', '--input-type=module', '-e', source, converter.as_uri(), str(shared)], input=json.dumps(conversations), text=True, check=True, capture_output=True)
    convert()
    original = {p.name: p.read_bytes() for p in shared.glob('*.md')}
    index = b.markdown_index(shared)
    expected = {cid: p.name for p,cid in index.items()}
    states = {}
    for c in conversations:
        cid = c['conversation_id']
        canonical = data / f'{cid}.md'
        canonical.write_text(f'---\nsource: "https://chatgpt.com/c/{cid}"\n---\n\nlive content')
        states[cid] = b.publish_markdown(canonical, cid, c['title'], shared, index, {})
        assert states[cid]['file'] == expected[cid]
        assert original[expected[cid]] in [p.read_bytes() for p in (data / '.revisions' / cid).glob('shared-*.md')]
    assert set(original) == {p.name for p in shared.glob('*.md')}
    convert()
    before = {p.name: p.read_bytes() for p in shared.glob('*.md')}
    index = b.markdown_index(shared)
    for c in conversations:
        cid = c['conversation_id']
        assert not b.publish_markdown(data / f'{cid}.md', cid, c['title'], shared, index, states[cid])['changed']
    assert before == {p.name: p.read_bytes() for p in shared.glob('*.md')}


def test_offline_publication_and_export_overwrite_do_not_trigger_cdp(tmp_path, monkeypatch):
    from contextlib import asynccontextmanager
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    cid = str(uuid4())
    out, shared = tmp_path / 'data', tmp_path / 'shared'
    metadata = dict(title='Example: title', date='2026-10-19', source=f'https://chatgpt.com/c/{cid}')
    rows = b.records(messages(), cid, metadata)
    canonical = out / b.filename(metadata['title'], cid)
    b.save(canonical, rows, f'---\nsource: "{metadata["source"]}"\n---\n\nlive')
    today = b.dt.datetime.now(b.dt.UTC).date().isoformat()
    cache = tmp_path / '.cache/sanand-scripts/backupchatgpt' / b.digest(str(out.resolve()))[:16]
    cache.mkdir(parents=True)
    catalog = {cid: dict(title=metadata['title'], url=metadata['source'], checked=today)}
    (cache / 'catalog.json').write_text(b.encoded(catalog))
    (cache / 'discovery.json').write_text(b.encoded(dict(attempted=b.time.time(), attempted_day=today)))
    @asynccontextmanager
    async def no_browser(url):
        raise AssertionError('Publishing Markdown must not open ChatGPT')
        yield
    monkeypatch.setattr(b, 'owned_page', no_browser)
    asyncio.run(b.run('http://localhost', out, [], '', False, 1, True, 'jsonl', 10, shared))
    assert not shared.exists()
    assert json.loads((cache / 'catalog.json').read_text()) == catalog
    asyncio.run(b.run('http://localhost', out, [], '', False, 1, False, 'jsonl', 10, shared))
    target = shared / 'Example title.md'
    assert target.read_bytes() == canonical.with_suffix('.md').read_bytes()
    # Simulate moving between host/container aliases with a different path hash.
    alternate = cache.with_name('1234567890abcdef')
    cache.rename(alternate)
    cache = alternate
    (out / '.backupchatgpt-state').write_text(cache.name + '\n')
    target.write_text(exported(cid, content='older reexport'))
    before = target.read_bytes()
    asyncio.run(b.run('http://localhost', out, [], '', False, 1, False, 'jsonl', 10, shared))
    assert target.read_bytes() == before
    assert json.loads((cache / 'catalog.json').read_text())[cid]['checked'] == today


def test_labeled_summary_counts_and_units():
    rows = messages()
    stats = b.message_stats(rows)
    summary = dict(conversationId='chat', position=2, total=10, duration_ms=150000, markdown_bytes=230000, changed=False, shared_status='unchanged', **stats)
    line = b.result_line(summary)
    assert 'ID=chat' in line and '(2/10)' in line
    assert 'messages=2' in line and 'prompts=1' in line
    assert 'elapsed=00:02:30' in line and 'markdown=230KB' in line
    assert 'canonical=unchanged' in line and 'shared=unchanged' in line
    assert 'False' not in line


def test_navigation_logs_state_and_failure_without_message_text(monkeypatch):
    async def no_sleep(*args):
        pass
    monkeypatch.setattr(b.asyncio, 'sleep', no_sleep)
    events = []
    class Trace:
        def event(self, name, data):
            events.append((name, data))
    class Page:
        backup_trace = Trace()
        backup_context = dict(conversationId=str(uuid4()), position=7, total=20, stage='opening')
        async def command(self, method, **params):
            return {}
        async def evaluate(self, source):
            return dict(login=False, url='https://chatgpt.com/', history=True, assistant=False, error=False, users=1, assistants=0, readyState='complete', challenge=False)
    page = Page()
    with pytest.raises(b.ChatLoadTimeout, match='timeout'):
        asyncio.run(b.navigate(page, f'https://chatgpt.com/c/{page.backup_context["conversationId"]}', True))
    assert events[0][0] == 'navigation_start'
    assert any(name=='navigation_state' and data['users']==1 and data['assistants']==0 and data['position']==7 for name,data in events)
    assert events[-1][0] == 'navigation_failed'
    assert not any('content' in data or 'text' in data for _,data in events)


def test_scroll_events_capture_geometry_without_content(monkeypatch, capsys):
    async def no_sleep(*args):
        pass
    monkeypatch.setattr(b.asyncio, 'sleep', no_sleep)
    data = messages()
    data[0]['content'] = 'PRIVATE MESSAGE SENTINEL'
    events = []
    class Trace:
        def event(self, name, value):
            events.append((name, value))
    class Page:
        backup_trace = Trace()
        backup_context = dict(conversationId='chat', position=1, total=1, stage='scroll-up')
        async def evaluate(self, source, arg):
            if 'captured:' in source:
                return dict(captured=data, visible=[m['id'] for m in data], busy=False)
            return dict(top=0, height=200, viewport=100, before=0)
    result = asyncio.run(b.sweep(Page(), False, -1, 5))
    checkpoints = [row for name,row in events if name=='scroll_checkpoint']
    assert checkpoints[-1]['boundary'] and checkpoints[-1]['geometry']['viewport']==100
    assert checkpoints[-1]['captured']==2 and checkpoints[-1]['position']==1
    assert result['duration_ms']>=0
    assert events[-1][0]=='scroll_finish'
    assert 'PRIVATE MESSAGE SENTINEL' not in json.dumps(events)
    output=capsys.readouterr().err
    assert 'direction=up step=000/005 captured=002 elapsed=00:00:' in output
    assert 'history ID=' not in output


def test_incremental_anchor_and_edited_tail_keep_old_snapshot(tmp_path):
    original = messages() + messages() + messages()
    observed = [dict(m) for m in original[2:4]] + messages()
    assert b.unchanged_anchor(observed, original) == original[2]['id']
    assert b.unchanged_anchor([dict(observed[0], id=str(uuid4()))], original) is None
    merged = b.merge_tail(original, observed, original[2]['id'])
    assert merged == original[:2] + observed
    # The unchanged later output must not hide an earlier observed edit.
    edited = [dict(m) for m in observed]
    edited[0]['content'] = 'edited earlier prompt'
    assert b.unchanged_anchor(edited, original) is None
    rich_changed = [dict(m) for m in observed]
    rich_changed[0]['parts'] = [{'type':'text','text':'changed rich part'}]
    assert b.unchanged_anchor(rich_changed, original) is None
    path = tmp_path / 'chat.jsonl'
    b.save(path, b.records(original, 'chat'), 'before')
    b.validate(merged, original[:2])
    b.save(path, b.records(merged, 'chat'), 'after')
    assert any(b.read_rows(p, 'chat')==b.records(original, 'chat') for p in (tmp_path/'.revisions/chat').glob('*.jsonl'))


def test_full_scan_reuses_prefix_only_when_saved_suffix_is_complete():
    previous = [dict(id=str(uuid4()), role='assistant', content=str(i)) for i in range(5)]
    previous[1]['role'] = 'user'
    captured = [dict(m) for m in previous[1:]] + [dict(id=str(uuid4()), role='assistant', content='new')]
    captured[2]['content'] = 'updated rendering'
    assert b.full_scan_prefix(previous, captured) == 1
    assert b.full_scan_prefix(previous, captured[:2] + captured[3:]) == 0
    assert b.full_scan_prefix(previous, [dict(captured[0], content='changed'), *captured[1:]]) == 0
    assert b.full_scan_prefix(previous, [captured[0], captured[2], captured[1], *captured[3:]]) == 0
def test_fixed_width_duration_and_priority_for_bumped_old_chats():
    assert b.duration(30) == '00:00:30'
    assert b.duration(150) == '00:02:30'
    old, other = str(uuid4()), str(uuid4())
    catalog = {old:dict(title='old edited chat', rank=1, checked='2026-10-19', changed=True), other:dict(title='other',rank=20,checked='',changed=True)}
    assert b.select(catalog, [], '', False, 1, '2026-10-19')[0][0] == old


def test_anchor_stops_before_top_only_after_stable_capture(monkeypatch):
    async def no_sleep(*args):
        pass
    monkeypatch.setattr(b.asyncio, 'sleep', no_sleep)
    previous = messages() + messages()
    captured = previous[2:]
    class Page:
        moves = 0
        async def evaluate(self, source, arg):
            if 'captured:' in source:
                return dict(captured=captured, visible=[m['id'] for m in captured], busy=False)
            self.moves += bool(arg['direction'])
            return dict(top=800, height=2000, viewport=100, before=800)
    page = Page()
    result = asyncio.run(b.sweep(page, False, -1, 10, anchor_previous=previous))
    assert result['anchor_id']==previous[2]['id'] and not result['boundary']
    assert result['steps']>=4 and page.moves==0


@pytest.mark.parametrize('fail', [False, True, 'keep', 'running'])
def test_owned_tab_closes_on_success_and_stays_open_on_failure(monkeypatch, fail):
    from contextlib import asynccontextmanager
    import io
    commands = []
    def fetch(url, **kwargs):
        value = dict(Browser='Edg/155', webSocketDebuggerUrl='ws://browser') if url.endswith('/json/version') else [dict(id='owned',webSocketDebuggerUrl='ws://page')]
        return io.BytesIO(json.dumps(value).encode())
    @asynccontextmanager
    async def connect(*args, **kwargs):
        from types import SimpleNamespace
        socket = SimpleNamespace(open=True)
        try:
            yield socket
        finally:
            socket.open=False
    class Page:
        def __init__(self, socket, url, version):
            self.socket=socket
            self.url = url
        async def evaluate(self, source):
            assert self.socket.open, 'Safety check must precede CDP disconnection'
            return fail == 'running'
        async def command(self, method, **kwargs):
            commands.append((method,kwargs))
            return dict(targetId='owned') if method=='Target.createTarget' else dict(success=True)
    class Trace:
        counters = {}
        def event(self, name, value):
            pass
    monkeypatch.setattr(b, 'urlopen', fetch)
    monkeypatch.setattr(b.websockets, 'connect', connect)
    monkeypatch.setattr(b, 'CDPPage', Page)
    trace = Trace()
    async def run():
        async with b.owned_page('http://localhost:9222') as page:
            page.backup_trace=trace
            page.url='https://chatgpt.com/c/example'
            page.backup_keep_open = fail == 'keep'
            if fail is True:
                raise ValueError('inspect me')
    if fail is True:
        with pytest.raises(ValueError, match='inspect me'):
            asyncio.run(run())
        assert trace.counters['inspection_target_id']=='owned'
    else:
        asyncio.run(run())
    assert sum(name=='Target.closeTarget' for name,_ in commands)==(0 if fail else 1)
    if fail:
        assert trace.counters['inspection_tabs'][-1]['target_id']=='owned'


def test_sidebar_refresh_is_bounded_and_catches_same_day_updates(monkeypatch):
    monkeypatch.setattr(b.time,'time',lambda:1000)
    assert not b.discovery_due(dict(attempted=999))
    assert b.discovery_due(dict(attempted=99))
    assert b.discovery_due(dict(attempted=999),True)


def test_bumped_successful_chat_is_not_blocked_by_failure_cooldown():
    cid=str(uuid4())
    catalog={cid:dict(title='edited',rank=1,checked='2026-10-19',changed=True,pending=False,attempted=b.time.time())}
    assert b.select(catalog,[],'',False,1,'2026-10-19')[0][0]==cid


def test_incremental_run_saves_edits_and_archives_replaced_suffix(tmp_path, monkeypatch, capsys):
    from contextlib import asynccontextmanager
    monkeypatch.setattr(Path,'home',lambda:tmp_path)
    cid=str(uuid4())
    metadata=dict(title='Edited chat',date='2026-10-19',source=f'https://chatgpt.com/c/{cid}')
    original=messages()+messages()+messages()
    observed=[dict(m) for m in original[2:4]]+messages()
    observed[1]['content']='Edited answer'
    out=tmp_path/'data'
    path=out/b.filename(metadata['title'],cid)
    before=b.records(original,cid,metadata)
    b.save(path,before,'original markdown')
    class Page:
        async def evaluate(self, source, arg=None):
            if 'orderValid' in source:
                return dict(messages=observed,metadata=metadata,orderValid=True)
            if 'messagesToMarkdown' in source:
                return 'edited markdown'
    @asynccontextmanager
    async def owned(url):
        yield Page()
    async def navigate(*args):
        pass
    async def sweep(page, sidebar, direction, steps, checkpoint, anchor_previous=None):
        checkpoint(observed)
        return dict(count=len(observed),boundary=direction>0,**({'anchor_id':observed[0]['id']} if direction<0 else {}))
    async def no_sleep(*args):
        pass
    monkeypatch.setattr(b,'owned_page',owned)
    monkeypatch.setattr(b,'navigate',navigate)
    monkeypatch.setattr(b,'sweep',sweep)
    monkeypatch.setattr(b.asyncio,'sleep',no_sleep)
    asyncio.run(b.run('http://localhost',out,[cid],'',False,1,False,'jsonl',10))
    saved=b.read_rows(path,cid)
    assert [r['id'] for r in saved]==[m['id'] for m in original[:2]+observed]
    assert saved[3]['content']=='Edited answer'
    assert path.with_suffix('.md').read_text()=='edited markdown'
    assert any(b.read_rows(p,cid)==before for p in (out/'.revisions'/cid).glob('*.jsonl'))
    summaries=[json.loads(line) for line in capsys.readouterr().out.splitlines()]
    result=next(r for r in summaries if r.get('conversationId')==cid)
    assert result['reused_messages']==2 and result['captured_messages']==4
    assert result['coverage']=='matched-prefix+rendered-tail'
    snapshot=path.read_bytes()
    async def empty_tail(page, sidebar, direction, steps, checkpoint, **kwargs):
        checkpoint([])
        return dict(count=0,boundary=True)
    monkeypatch.setattr(b,'sweep',empty_tail)
    assert asyncio.run(b.run('http://localhost',out,[cid],'',False,1,False,'jsonl',10)) == 1
    assert path.read_bytes()==snapshot


def test_full_scan_retains_missing_prefix_and_archives_prior_snapshot(tmp_path, monkeypatch, capsys):
    from contextlib import asynccontextmanager
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    cid = str(uuid4())
    metadata = dict(title='Scheduled chat', date='2026-10-19', source=f'https://chatgpt.com/c/{cid}')
    original = messages() + messages() + messages()
    observed = [dict(m) for m in original[2:]] + messages()
    observed[1]['content'] = 'reformatted answer'
    out = tmp_path / 'data'
    path = out / b.filename(metadata['title'], cid)
    before = b.records(original, cid, metadata)
    b.save(path, before, 'original markdown')
    class Page:
        async def evaluate(self, source, arg=None):
            if 'orderValid' in source:
                return dict(messages=observed, metadata=metadata, orderValid=True)
            if 'messagesToMarkdown' in source:
                return 'updated markdown'
    @asynccontextmanager
    async def owned(url):
        yield Page()
    async def navigate(*args): pass
    async def sweep(page, sidebar, direction, steps, checkpoint, anchor_previous=None):
        checkpoint(observed)
        return dict(count=len(observed), boundary=True)
    monkeypatch.setattr(b, 'owned_page', owned)
    monkeypatch.setattr(b, 'navigate', navigate)
    monkeypatch.setattr(b, 'sweep', sweep)
    assert not asyncio.run(b.run('http://localhost', out, [cid], '', True, 1, False, 'jsonl', 10))
    saved = b.read_rows(path, cid)
    assert [r['id'] for r in saved] == [m['id'] for m in original[:2] + observed]
    assert any(b.read_rows(p, cid) == before for p in (out / '.revisions' / cid).glob('*.jsonl'))
    result = next(json.loads(line) for line in capsys.readouterr().out.splitlines() if '"conversationId"' in line)
    assert (result['reused_messages'], result['captured_messages']) == (2, 6)


def test_selection_counts_distinguish_limit_cooldown_and_finished(monkeypatch):
    monkeypatch.setattr(b.time, 'time', lambda: 2000)
    catalog = {str(uuid4()):dict(title='chat') for _ in range(25)}
    ids = list(catalog)
    catalog[ids[0]].update(checked='2026-10-19')
    catalog[ids[1]].update(pending=True, attempted=1999)
    counts = b.selection_counts(catalog, [], '', False, 20, '2026-10-19')
    assert counts == dict(known=25, selected=20, due=24, deferred_limit=3, cooldown=1, not_due=1, filtered=0)
    assert b.selection_counts(catalog,[ids[0]],'',False,20,'2026-10-19')['due']==1


@pytest.mark.parametrize('kind', ['extraction', 'running', 'validation', 'authentication', 'rate-limit', 'cdp', 'write', 'unexpected'])
def test_batch_continues_only_chat_local_failures(tmp_path, monkeypatch, capsys, kind):
    from contextlib import asynccontextmanager
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    ids = sorted([str(uuid4()), str(uuid4())])
    out = tmp_path/'output'
    cache = tmp_path/'.cache/sanand-scripts/backupchatgpt'/b.digest(str(out.resolve()))[:16]
    cache.mkdir(parents=True)
    (cache/'catalog.json').write_text(b.encoded({cid:dict(title=cid,url=f'https://chatgpt.com/c/{cid}') for cid in ids}))
    (cache/'discovery.json').write_text(b.encoded(dict(attempted=b.time.time())))
    data = messages()
    opened, lifecycles = [], []
    class Page:
        cid = None
        async def evaluate(self, source, arg=None):
            if 'orderValid' in source:
                return dict(messages=data, metadata=dict(title=self.cid,date='2026-10-19',source=f'https://chatgpt.com/c/{self.cid}'),orderValid=not(kind=='validation' and self.cid==ids[0]))
            if 'messagesToMarkdown' in source:
                return 'markdown'
            return False
    @asynccontextmanager
    async def owned(url):
        page = Page()
        lifecycles.append(('opened',page))
        try:
            yield page
        except BaseException:
            lifecycles.append(('retained',page))
            raise
        else:
            lifecycles.append(('retained' if getattr(page,'backup_keep_open',False) else 'closed',page))
    async def navigate(page,url,conversation=False):
        page.cid=b.identity(url)
        opened.append(page.cid)
        if page.cid!=ids[0]:
            return
        if kind=='running':
            raise b.IncompleteChat('Generation still running')
        if kind in {'authentication','rate-limit'}:
            raise RuntimeError(kind)
        if kind=='cdp':
            raise OSError('CDP disconnected')
        if kind=='unexpected':
            raise KeyError('coding error')
    async def sweep(page,sidebar,direction,steps,checkpoint,**kwargs):
        checkpoint(data)
        if page.cid==ids[0] and kind=='extraction':
            raise b.IncompleteChat('Unstable message IDs')
        return dict(boundary=True,count=len(data))
    monkeypatch.setattr(b,'owned_page',owned)
    monkeypatch.setattr(b,'navigate',navigate)
    monkeypatch.setattr(b,'sweep',sweep)
    if kind=='write':
        def broken_write(*args):
            raise OSError('disk full')
        monkeypatch.setattr(b,'save',broken_write)
    local = kind in {'extraction','running','validation'}
    if local:
        assert asyncio.run(b.run('http://localhost',out,ids,'',False,2,False,'jsonl',10))==1
    else:
        with pytest.raises((RuntimeError,OSError,KeyError)):
            asyncio.run(b.run('http://localhost',out,ids,'',False,2,False,'jsonl',10))
    state=json.loads((cache/'catalog.json').read_text())
    assert state[ids[0]]['pending'] and not state[ids[0]].get('checked')
    assert not (out/b.filename(ids[0],ids[0])).exists()
    assert opened == (ids if local else ids[:1])
    assert [event for event,_ in lifecycles] == (['opened','retained','opened','closed'] if local else ['opened','retained'])
    latest=json.loads((cache.parent/'latest.json').read_text())
    assert latest['completed']==(1 if local else 0)
    assert latest['unattempted']==(0 if local else 1)
    if local:
        assert not state[ids[1]]['pending'] and state[ids[1]]['checked']
        assert latest['failed']==1 and latest['pending_count']==1
        assert latest['due_remaining']==1 and latest['failures'][0]['conversationId']==ids[0]
        assert len(b.read_rows(out/b.filename(ids[1],ids[1]),ids[1]))==2
        result=json.loads(capsys.readouterr().out.splitlines()[-1])
        assert result['status']=='incomplete' and result['completed']==1
        # Both the successful check and failed attempt suppress immediate requests.
        async def forbidden(*args):
            raise AssertionError('redundant navigation')
        monkeypatch.setattr(b,'navigate',forbidden)
        asyncio.run(b.run('http://localhost',out,[],'',False,2,False,'jsonl',10))


def test_active_generation_defers_before_scrolling_or_checkpoint(monkeypatch):
    class Page:
        async def evaluate(self,source,arg=None):
            assert 'captured:' in source  # No scroll/geometry evaluation allowed.
            return dict(captured=messages(),visible=[],busy=True)
    def checkpoint(*args):
        raise AssertionError('Never publish a running capture')
    with pytest.raises(b.IncompleteChat,match='Generation still running'):
        asyncio.run(b.sweep(Page(),False,-1,10,checkpoint))


@pytest.mark.parametrize('status,exception', [
    (dict(busy=True),b.IncompleteChat),
    (dict(rate_limited=True),RuntimeError),
    (dict(error=True),b.IncompleteChat),
    (dict(load_error=True),b.ChatLoadFailure),
    (dict(challenge=True),RuntimeError),
])
def test_navigation_classifies_running_rate_limit_and_missing(monkeypatch,status,exception):
    async def no_sleep(*args):
        pass
    monkeypatch.setattr(b.asyncio,'sleep',no_sleep)
    class Page:
        commands=[]
        async def command(self,method,**params):
            self.commands.append(method)
            return {}
        async def evaluate(self,source):
            return dict(dict(url='https://chatgpt.com/c/'+str(uuid4()),login=False,error=False,assistant=True),**status)
    page=Page()
    with pytest.raises(exception):
        asyncio.run(b.navigate(page,'https://chatgpt.com/c/'+str(uuid4()),True))
    assert page.commands==['Page.navigate']


def test_cli_nonzero_after_partial_batch_has_no_spurious_error(tmp_path,monkeypatch):
    from typer.testing import CliRunner
    monkeypatch.setattr(Path,'home',lambda:tmp_path)
    async def partial_run(*args):
        return 1
    monkeypatch.setattr(b,'run',partial_run)
    result=CliRunner().invoke(b.app,['--out-dir',str(tmp_path/'data'),'--markdown-dir',str(tmp_path/'md'),'--dry-run'])
    assert result.exit_code==1
    assert 'backupchatgpt: 1' not in result.output


def test_rate_limit_during_scroll_is_fatal():
    class Page:
        async def evaluate(self,*args):
            return dict(captured=[],visible=[],busy=False,blocked=True)
    with pytest.raises(RuntimeError,match='rate limit'):
        asyncio.run(b.sweep(Page(),False,-1,10))


def test_navigation_uses_scraper_counts_for_image_only_readiness(monkeypatch):
    cid=str(uuid4())
    sources=[]
    async def no_sleep(*args): pass
    async def inject(page): sources.append('injected')
    monkeypatch.setattr(b.asyncio,'sleep',no_sleep)
    monkeypatch.setattr(b,'inject',inject)
    class Page:
        async def command(self,*args,**kwargs): return {}
        async def evaluate(self,source):
            sources.append(source)
            if 'const messages=chatgptscraper.extractMessages' in source:
                return dict(users=1,assistants=1)
            return dict(url=f'https://chatgpt.com/c/{cid}',readyState='complete',login=False,error=False,assistant=False,history=True,users=1,assistants=0)
    asyncio.run(b.navigate(Page(),f'https://chatgpt.com/c/{cid}',True))
    assert sources.count('injected')==1


@pytest.mark.parametrize('users', [0, 1])
def test_prompt_only_navigation_waits_for_hydration(monkeypatch, users):
    cid=str(uuid4())
    async def no_sleep(*args): pass
    async def inject(*args): pass
    monkeypatch.setattr(b.asyncio,'sleep',no_sleep)
    monkeypatch.setattr(b,'inject',inject)
    class Page:
        navigations=0
        polls=0
        async def command(self,*args,**kwargs):
            self.navigations+=1
            return {}
        async def evaluate(self,source):
            if 'const messages=chatgptscraper.extractMessages' in source:
                self.polls += 1
                return dict(users=users,assistants=0)
            return dict(url=f'https://chatgpt.com/c/{cid}',readyState='complete',login=False,error=False,assistant=False,history=True,users=1,assistants=0)
    page=Page()
    if users:
        asyncio.run(b.navigate(page,f'https://chatgpt.com/c/{cid}',True))
    else:
        with pytest.raises(b.ChatLoadTimeout, match='users=0 assistants=0'):
            asyncio.run(b.navigate(page,f'https://chatgpt.com/c/{cid}',True))
    assert page.navigations==1 and page.polls==60


@pytest.mark.parametrize('sequence,stops', [
    (['timeout','ok','timeout','ok'],False),
    (['timeout','validation','timeout','ok'],False),
    (['timeout','running','timeout','ok'],False),
    (['timeout','timeout','ok'],True),
    (['timeout','load-error','ok'],True),
    (['load-error','load-error','ok'],True),
    (['load-error','ok','timeout','ok'],False),
])
def test_consecutive_load_timeout_breaker(tmp_path,monkeypatch,capsys,sequence,stops):
    from contextlib import asynccontextmanager
    monkeypatch.setattr(Path,'home',lambda:tmp_path)
    ids=sorted(str(uuid4()) for _ in sequence)
    behavior=dict(zip(ids,sequence))
    out=tmp_path/'data'
    cache=tmp_path/'.cache/sanand-scripts/backupchatgpt'/b.digest(str(out.resolve()))[:16]
    cache.mkdir(parents=True)
    (cache/'catalog.json').write_text(b.encoded({cid:dict(title=cid,url=f'https://chatgpt.com/c/{cid}') for cid in ids}))
    data=messages()
    opened=[]
    class Page:
        cid=None
        async def evaluate(self,source,arg=None):
            if 'orderValid' in source:
                return dict(messages=data,metadata=dict(title=self.cid,date='2026-10-19',source=f'https://chatgpt.com/c/{self.cid}'),orderValid=behavior[self.cid]!='validation')
            if 'messagesToMarkdown' in source: return 'markdown'
            return False
    @asynccontextmanager
    async def owned(url): yield Page()
    async def navigate(page,url,*args):
        page.cid=b.identity(url)
        opened.append(page.cid)
        if behavior[page.cid]=='load-error': raise b.ChatLoadFailure('Could not load this ChatGPT conversation')
        if behavior[page.cid]=='timeout': raise b.ChatLoadTimeout('No assistant content after 60s')
        if behavior[page.cid]=='running': raise b.IncompleteChat('Generation still running')
    async def sweep(page,sidebar,direction,steps,checkpoint,**kwargs):
        checkpoint(data)
        return dict(count=2,boundary=True)
    monkeypatch.setattr(b,'owned_page',owned)
    monkeypatch.setattr(b,'navigate',navigate)
    monkeypatch.setattr(b,'sweep',sweep)
    if stops:
        with pytest.raises(RuntimeError,match='2 consecutive'):
            asyncio.run(b.run('http://localhost',out,ids,'',False,len(ids),False,'jsonl',10))
        assert opened==ids[:2]
    else:
        assert asyncio.run(b.run('http://localhost',out,ids,'',False,len(ids),False,'jsonl',10))==sum(x!='ok' for x in sequence)
        assert opened==ids
    state=json.loads((cache/'catalog.json').read_text())
    assert state[ids[0]]['pending'] and not state[ids[0]].get('checked')
    latest=json.loads((cache.parent/'latest.json').read_text())
    assert latest['completed']==(0 if stops else sequence.count('ok'))
    assert latest['unattempted']==(len(ids)-2 if stops else 0)
    if stops:
        assert latest['consecutive_load_failures']==2
        assert len(latest['failures'])==2
    else:
        assert not state[ids[-1]]['pending'] and state[ids[-1]]['checked']


def test_collapsed_prompt_is_incomplete_not_accepted():
    class Page:
        async def evaluate(self,*args):
            return dict(captured=messages(),visible=[],busy=False,expanded_prompts=1,collapsed_prompts=1)
    with pytest.raises(b.IncompleteChat,match='remains collapsed'):
        asyncio.run(b.sweep(Page(),False,-1,10))


def test_existing_prefix_requires_prompt_expansion_baseline(tmp_path,monkeypatch):
    from contextlib import asynccontextmanager
    monkeypatch.setattr(Path,'home',lambda:tmp_path)
    cid=str(uuid4()); data=messages(); out=tmp_path/'data'
    metadata=dict(title=cid,date='2026-10-19',source=f'https://chatgpt.com/c/{cid}')
    b.save(out/b.filename(cid,cid),b.records(data,cid,metadata),'markdown')
    directions=[]
    class Page:
        async def evaluate(self,source,arg=None):
            if 'orderValid' in source:
                # A collapsed remount after sweeping must not replace the confirmed snapshot.
                current = data if '__backupState.messages' in source else [dict(data[0],content='truncated'),data[1]]
                return dict(messages=current,metadata=metadata,orderValid=True)
            if 'messagesToMarkdown' in source:return 'markdown'
            return False
    @asynccontextmanager
    async def owned(url):yield Page()
    async def navigate(*args):pass
    async def sweep(page,sidebar,direction,steps,checkpoint,**kwargs):
        directions.append(direction);checkpoint(data)
        return dict(count=2,boundary=True)
    async def no_sleep(*args):pass
    monkeypatch.setattr(b,'owned_page',owned)
    monkeypatch.setattr(b,'navigate',navigate)
    monkeypatch.setattr(b,'sweep',sweep)
    monkeypatch.setattr(b.asyncio,'sleep',no_sleep)
    asyncio.run(b.run('http://localhost',out,[cid],'',False,1,False,'jsonl',10))
    assert directions==[-1,1] # Unverified old prefix is audited before reuse.
    directions.clear()
    asyncio.run(b.run('http://localhost',out,[cid],'',False,1,False,'jsonl',10))
    assert directions==[1,-1]
    assert b.read_rows(out/b.filename(cid,cid),cid)[0]['content']==data[0]['content']


def test_discovery_failure_is_reported_and_explicit_run_ignores_old_error(tmp_path, monkeypatch, capsys):
    from contextlib import asynccontextmanager
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    class Page:
        async def evaluate(self, *args):
            return False
    @asynccontextmanager
    async def owned(url):
        yield Page()
    async def navigate(*args):
        pass
    async def sweep(*args):
        raise b.IncompleteChat('Scroll budget exhausted after 5 steps; scan incomplete')
    monkeypatch.setattr(b, 'owned_page', owned)
    monkeypatch.setattr(b, 'navigate', navigate)
    monkeypatch.setattr(b, 'sweep', sweep)
    out = tmp_path / 'output'
    assert asyncio.run(b.run('http://localhost', out, [], '', False, 1, False, 'jsonl', 5))
    result = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert result['status'] == 'incomplete' and 'Scroll budget' in result['discovery_error']
    # Cached failed discovery must also signal failure when there is no work to select.
    assert asyncio.run(b.run('http://localhost', out, [], '', False, 1, False, 'jsonl', 5))
    result = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert result['status'] == 'incomplete'
    # Explicit URLs intentionally bypass discovery, so a stale error is irrelevant.
    cid = str(uuid4())
    assert not asyncio.run(b.run('http://localhost', out, [cid], 'no-match', False, 1, False, 'jsonl', 5))
    result = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert result['status'] == 'partial' and result['discovery_error'] is None


def test_raw_publication_preserves_exports_and_is_idempotent(tmp_path, capsys, monkeypatch):
    raw, output = tmp_path / "raw", tmp_path / "md"
    raw.mkdir()
    output.mkdir()
    released, current, partial, placeholder, working, image_working, missing, legacy, stale, corrupt, unknown = (
        str(uuid4()) for _ in range(11)
    )

    def capture(cid, coverage="branch"):
        mid = str(uuid4())
        snapshot = dict(conversation_id=cid, title="Same title", update_time=30,
                        current_node=mid, page_info=dict(has_previous_page=False, has_next_page=False),
                        messages=[dict(id=mid, author=dict(role="user"),
                                       content=dict(content_type="text", parts=["Recovered prompt"]))])
        if cid == placeholder:
            snapshot["messages"][-1].update(author=dict(role="tool"), channel="final",
                                            content=dict(content_type="multimodal_text", parts=[]))
        if cid in {working, image_working}:
            snapshot["title"] = "Working\tchat\n"
            snapshot["messages"][-1]["status"] = "in_progress"
            if cid == image_working:
                snapshot["messages"][-1]["metadata"] = {"image_gen_estimated_duration_ms": 1000}
        payload = b.encoded(snapshot)
        (raw / f"{cid}.json").write_text(payload)
        (raw / f"{cid}.backup.json").write_text(b.encoded(dict(
            coverage=coverage, hash=b.hashlib.sha256(payload.encode()).hexdigest(), updateTime=30)))

    for cid in (released, current, placeholder, stale, corrupt, unknown):
        capture(cid)
    for cid in (partial, working, image_working):
        capture(cid, "partial")
    (raw / "catalog.json").write_text(b.encoded({
        missing: {"updateTime": 40, "title": "Catalog\tchat\n"},
        legacy: 40,
        stale: {"updateTime": 31.25, "title": "Renamed in ChatGPT"},
        current: {"updateTime": 29, "title": "Older catalog title"},
    }))
    (raw / f"{corrupt}.json").write_text("{}")
    original = f'---\ntitle: "Old name"\ndate: 1970-01-01T00:00:20Z\nsource: "https://chatgpt.com/c/{released}"\n---\n\nOld bytes\n'
    newer = f'---\ntitle: "Same title"\ndate: 1970-01-01T00:00:30Z\nsource: "https://chatgpt.com/c/{current}"\n---\n\nOfficial export\n'
    (output / "Old name.md").write_text(original)
    (output / "Same title.md").write_text(newer)
    (output / "Undated.md").write_text(f'---\nsource: "https://chatgpt.com/c/{unknown}"\n---\n\nKeep this.\n')

    cache = tmp_path / "cache.json"

    def statuses(dry_run, *, verbose=True):
        assert b.raw_backup(raw, output, dry_run, "jsonl", verbose=verbose, cache_path=cache) == 1
        out, err = capsys.readouterr()
        rows = {row["conversationId"]: row for row in map(json.loads, out.splitlines())}
        assert sorted(err.splitlines()) == [
            f"error[chatcli-backup]: {corrupt} Snapshot identity or sidecar hash mismatch",
            f"warning[chatcli-backup]: {unknown} Check the update date in Undated.md before replacing the Markdown.",
        ]
        if verbose:
            assert (rows[missing]["label"], rows[missing]["title"]) == ("missing", "Catalog chat")
            assert (rows[stale]["label"], rows[stale]["title"]) == ("stale", "Renamed in ChatGPT")
        return {cid: row["status"] for cid, row in rows.items()}

    attention = {unknown: "unknown-markdown-version", corrupt: "error"}
    assert statuses(True) == (attention | {released: "would-update", current: "up-to-date", partial: "deferred",
                                           placeholder: "deferred", working: "deferred", image_working: "deferred",
                                           missing: "missing", legacy: "missing", stale: "stale-capture"})
    assert b.raw_backup(raw, output, True, "text", verbose=True) == 1
    rows = {cid: (label, updated, title) for label, cid, updated, title in (
        line.split("\t") for line in capsys.readouterr().out.splitlines()
    )}
    assert {len(label) for label, _, _ in rows.values()} == {len("🟢 would-update")}
    rows = {cid: (label.rstrip(), updated, title) for cid, (label, updated, title) in rows.items()}
    updated = "1970-01-01T00:00:30Z"
    assert rows == {
        released: ("🟢 would-update", updated, "Same title"), current: ("🟢 done", updated, "Same title"),
        partial: ("🟡 part", updated, "Same title"), placeholder: ("🟡 img", updated, "Same title"),
        working: ("🟡 wip", updated, "Working chat"), image_working: ("🟡 img", updated, "Working chat"),
        missing: ("🟡 missing", "1970-01-01T00:00:40Z", "Catalog chat"),
        legacy: ("🟡 missing", "1970-01-01T00:00:40Z", "—"),
        stale: ("🟡 stale", "1970-01-01T00:00:31.250000Z", "Renamed in ChatGPT"),
        corrupt: ("🔴 check", "—", "—"), unknown: ("🔴 check", updated, "Same title"),
    }
    assert statuses(True, verbose=False) == attention | {released: "would-update"}
    assert sorted(p.name for p in output.iterdir()) == ["Old name.md", "Same title.md", "Undated.md"]
    assert statuses(False, verbose=False) == attention
    assert (output / "Same title.md").read_text() == newer
    rendered = output / "Same title (1).md"
    assert b.markdown_owner(rendered) == released
    assert "Recovered prompt" in rendered.read_text()
    assert next((output / ".revisions" / released).glob("*.md")).read_text() == original
    stamp = rendered.stat().st_mtime_ns
    assert statuses(False)[released] == "up-to-date"
    assert b.raw_backup(raw, output, False, "text", verbose=True) == 1
    labels = {line.split("\t", 1)[0] for line in capsys.readouterr().out.splitlines()}
    assert {"🟢 done   ", "🟡 missing"} <= labels
    assert {len(label) for label in labels} == {len("🟡 missing")}
    assert rendered.stat().st_mtime_ns == stamp

    checked = []
    read_snapshot = b.raw_snapshot

    def track_snapshot(path):
        checked.append(path.stem)
        return read_snapshot(path)

    monkeypatch.setattr(b, "raw_snapshot", track_snapshot)
    assert statuses(True)[released] == "up-to-date"
    assert checked == [corrupt]  # Integrity errors still get retried.
    unchanged = raw / f"{current}.json"
    original_stat = unchanged.stat()
    original_bytes = unchanged.read_bytes()
    unchanged.write_bytes(original_bytes.replace(b"Recovered prompt", b"Corrupted prompt"))
    os.utime(unchanged, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
    assert unchanged.stat().st_size == original_stat.st_size
    assert b.raw_backup(raw, output, True, "jsonl", verbose=True, cache_path=cache) == 2
    rows = {row["conversationId"]: row for row in map(json.loads, capsys.readouterr().out.splitlines())}
    assert rows[current]["status"] == "error"
    unchanged.write_bytes(original_bytes)
    assert statuses(False)[current] == "up-to-date"
    rendered.unlink()
    checked.clear()
    assert statuses(True)[released] == "would-create"
    assert sorted(checked) == sorted([released, corrupt])
    assert not rendered.exists()


def test_raw_backup_replays_linked_streams_and_preserves_conflicts(tmp_path, capsys):
    raw, output = tmp_path / "raw", tmp_path / "md"
    raw.mkdir()
    cid, prompt_id, reply_id, follow_id, answer_id = (str(uuid4()) for _ in range(5))

    def stream(parent, user_id, assistant_id, start, *, terminal=True):
        path = "/backend-api/f/conversation"
        capture = str(uuid4())
        directory = raw / "events" / f"1-{capture}"
        directory.mkdir(parents=True)
        prompt = dict(id=user_id, author=dict(role="user"), status="finished_successfully",
                      create_time=start, content=dict(content_type="text", parts=[f"Prompt {start}"]))
        if parent != "client-created-root":
            prompt["metadata"] = dict(parent_id=parent)
        request = dict(action="next", parent_message_id=parent, messages=[prompt])
        if parent != "client-created-root":
            request["conversation_id"] = cid
        reply = dict(id=assistant_id, author=dict(role="assistant"), channel="final", recipient="all",
                     status="in_progress", create_time=start + 1, content=dict(content_type="text", parts=[""]),
                     metadata=dict(parent_id=user_id, is_visually_hidden_from_conversation=True))

        def event(body, event_type=""):
            return (f"event: {event_type}\n" if event_type else "") + f"data: {b.encoded(body)}\n\n"

        body = event("v1", "delta_encoding")
        body += event(dict(type="input_message", conversation_id=cid, input_message=prompt))
        body += event(dict(type="title_generation", conversation_id=cid, title="Observed chat"))
        body += event(dict(o="add", p="", c=0, v=dict(conversation_id=cid, message=reply)), "delta")
        body += event(dict(o="append", p="/message/content/parts/0", v="Full "), "delta")
        body += event(dict(v=f"reply {start}"), "delta")
        body += event(dict(o="patch", p="", v=[
            dict(o="replace", p="/message/status", v="finished_successfully"),
            dict(o="add", p="/message/end_turn", v=True),
            dict(o="remove", p="/message/metadata/is_visually_hidden_from_conversation"),
        ]), "delta")
        if terminal:
            body += event(dict(type="message_stream_complete", conversation_id=cid)) + "data: [DONE]\n\n"
        records = [
            dict(kind="start", request=request), dict(kind="headers", status=200, contentType="text/event-stream"),
            dict(kind="chunk", text=body[:150]), dict(kind="chunk", text=body[150:]),
            dict(kind="end", complete=False, reason="AbortError", finishedAt=(start + 3) * 1000),
        ]
        for i, record in enumerate(records):
            (directory / f"{i:05}.json").write_text(b.encoded(dict(
                record, index=i, startedAt=start * 1000, captureId=capture, method="POST", path=path)))
        return directory, prompt, dict(reply, status="finished_successfully", end_turn=True,
                                        content=dict(content_type="text", parts=[f"Full reply {start}"]),
                                        metadata=dict(parent_id=user_id))

    cache = tmp_path / "cache.json"

    def run(dry_run):
        assert b.raw_backup(raw, output, dry_run, "jsonl", verbose=True, cache_path=cache) == 0
        return json.loads(capsys.readouterr().out)

    _, prompt, reply = stream("client-created-root", prompt_id, reply_id, 20)
    assert run(True)["status"] == "would-create"
    assert not output.exists()
    assert run(False)["sourceType"] == "stream-replay"
    path = output / "Observed chat.md"
    first = path.read_text()
    assert 'capture: "stream-replay"' in first and "Full reply 20" in first
    assert run(False)["status"] == "up-to-date"

    incomplete, _, _ = stream(reply_id, follow_id, answer_id, 30, terminal=False)
    assert run(False)["status"] == "missing"
    assert path.read_text() == first
    fragment = incomplete / "00003.json"
    partial_fragment = json.loads(fragment.read_bytes())
    complete_fragment = dict(partial_fragment, text=partial_fragment["text"] + (
        f'data: {b.encoded(dict(type="message_stream_complete", conversation_id=cid))}\n\ndata: [DONE]\n\n'
    ))
    fragment.write_text(b.encoded(complete_fragment))
    assert run(True)["status"] == "would-update"
    assert path.read_text() == first
    incomplete.rename(tmp_path / "incomplete")
    branch, _, _ = stream(prompt_id, follow_id, answer_id, 30)
    assert run(False)["status"] == "missing"
    assert path.read_text() == first
    branch.rename(tmp_path / "other-branch")
    _, follow, answer = stream(reply_id, follow_id, answer_id, 30)
    edited = first.replace("Full reply 20", "My local notes")
    path.write_text(edited)
    assert run(False)["status"] == "replay-held"
    assert path.read_text() == edited
    path.write_text(first)
    assert run(False)["status"] == "updated"
    combined = path.read_text()
    assert combined.index("Full reply 20") < combined.index("Prompt 30") < combined.index("Full reply 30")
    assert run(False)["status"] == "up-to-date"

    native = b.encoded(dict(conversation_id=cid, title="Observed chat", update_time=31, current_node=answer_id,
                            page_info=dict(has_previous_page=False, has_next_page=False),
                            messages=[prompt, reply, follow, answer]))
    (raw / f"{cid}.json").write_text(native)
    (raw / f"{cid}.backup.json").write_text(b.encoded(dict(
        coverage="branch", hash=b.hashlib.sha256(native.encode()).hexdigest(), updateTime=31)))
    assert run(False)["status"] == "updated"
    assert 'capture: "stream-replay"' not in path.read_text()


def test_prompt_only_check_requires_reply_after_a_matching_prompt():
    user, other = str(uuid4()), str(uuid4())
    prompt = {"id": user, "author": {"role": "user"}}
    reply = {"id": other, "status": "finished_successfully", "channel": "final", "author": {"role": "assistant"}}
    assert b.raw_has_reply({"messages": [prompt, reply]}, {user})
    assert not b.raw_has_reply({"messages": [reply, prompt]}, {user})
    assert not b.raw_has_reply({"messages": [prompt, {**reply, "channel": "commentary"}]}, {user})


@pytest.mark.parametrize("new_title", ["New title", "OLD title", "Old title!"])
def test_raw_same_version_rename_preserves_export_transcript(tmp_path, capsys, new_title):
    raw, output = tmp_path / "raw", tmp_path / "md"
    raw.mkdir()
    output.mkdir()
    cid, mid, other = (str(uuid4()) for _ in range(3))
    payload = b.encoded(dict(conversation_id=cid, title=new_title, update_time=30, current_node=mid,
                             page_info=dict(has_previous_page=False, has_next_page=False), messages=[dict(id=mid, author=dict(role="user"),
                                            content=dict(content_type="text", parts=["Raw prompt only"]))]))
    (raw / f"{cid}.json").write_text(payload)
    (raw / f"{cid}.backup.json").write_text(b.encoded(dict(
        coverage="branch", hash=b.hashlib.sha256(payload.encode()).hexdigest(), updateTime=30)))

    def export(title, date, owner):
        return (f'---\ntitle: "{title}"\ndate: 1970-01-01T00:00:{date}Z\n'
                f'source: "https://chatgpt.com/c/{owner}"\n---\n\nOfficial transcript with assets\n')

    old = output / "Old title.md"
    previous = export("Old title", 30, cid)
    old.write_text(previous)
    collision = output / f"{new_title.lower()}.md"
    if new_title == "New title":
        collision.write_text(export("Unrelated title", 30, other))
    newer = output / "Newer export.md"
    newer.write_text(export("Newer export", 31, cid))
    assert b.raw_backup(raw, output, True, "jsonl", verbose=True) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "up-to-date"
    newer.unlink()

    expected_name = "New title (1).md" if new_title == "New title" else b.markdown_stem(new_title, cid) + ".md"
    for dry_run, status in [(True, "would-rename"), (False, "renamed")]:
        assert b.raw_backup(raw, output, dry_run, "jsonl", verbose=True) == 0
        row = json.loads(capsys.readouterr().out)
        assert row["status"] == status
        assert row["file"] == expected_name
        assert old.exists() == (dry_run or old.name == expected_name)
    target = output / expected_name
    assert target.read_text() == export(new_title, 30, cid)
    assert next((output / ".revisions" / cid).glob("*.md")).read_text() == previous
    if new_title == "New title":
        assert b.markdown_owner(collision) == other
    assert b.raw_backup(raw, output, False, "jsonl", verbose=True) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "up-to-date"


@pytest.mark.parametrize("problem", [None, "gap", "other-tab", "new-visit", "duplicate", "bad-hash", "conflict",
                                     "changed-branch", "hidden-message", "held-branch"])
def test_raw_backup_recovers_only_a_proven_page_chain(tmp_path, capsys, problem):
    raw, output = tmp_path / "raw", tmp_path / "md"
    cid = str(uuid4())
    versions = raw / "versions" / cid
    observations = raw / "observations"
    versions.mkdir(parents=True)
    observations.mkdir()

    def message(mid):
        return dict(id=mid, author=dict(role="user"), content=dict(content_type="text", parts=[f"Message {mid}"]))

    def window(ids, previous, following):
        return dict(messages=[message(mid) for mid in ids], page_info=dict(
            start_cursor=ids[0], end_cursor=ids[-1], has_previous_page=previous, has_next_page=following))

    endpoint = f"/backend-api/conversations/{cid}"

    def observe(value, start, before=None, tab=1):
        data = b.encoded(value)
        fingerprint = b.hashlib.sha256(data.encode()).hexdigest()
        (versions / f"{fingerprint}.json").write_text(data)
        query = {"num_turns": "10"}
        if before:
            query["before"] = before
        meta = dict(id=cid, path=f"{endpoint}/messages" if before else endpoint, tabId=tab,
                    startedAt=start, finishedAt=start + 1, query=query, queryKeys=list(query),
                    hash=fingerprint, updateTime=value.get("update_time"), coverage="partial", format=1)
        (observations / f"{start}.json").write_text(b.encoded(meta))
        return data, meta

    base = dict(window(["c", "d"], True, False), conversation_id=cid, current_node="d", update_time=30, title="Paged")
    data, meta = observe(base, 10)
    if problem in {"changed-branch", "hidden-message", "held-branch"}:
        previous = {**base, **window(["a", "d"], False, False), "update_time": 20}
        if problem == "hidden-message":
            base["messages"][-1]["metadata"] = {"is_visually_hidden_from_conversation": True}
            observe(base, 11)
        else:
            previous["messages"][0]["content"]["parts"] = ["An earlier branch"]
        data = b.encoded(previous)
        meta = dict(coverage="branch", updateTime=20, hash=b.hashlib.sha256(data.encode()).hexdigest())
        (raw / "catalog.json").write_text(b.encoded({cid: 30}))
    (raw / f"{cid}.json").write_text(data)
    (raw / f"{cid}.backup.json").write_text(b.encoded(meta))
    observe(window(["b"], True, True), 20, before="c")
    if problem == "new-visit":
        observe(base, 25)
    if problem == "conflict":
        observe(window(["x"], True, True), 21, before="c")
    oldest_data, oldest = observe(window(["a", "c"] if problem == "duplicate" else ["a"], False, True),
                        30, before="x" if problem == "gap" else "b", tab=2 if problem == "other-tab" else 1)
    oldest_path = versions / f"{oldest['hash']}.json"
    if problem == "bad-hash":
        oldest_path.write_text("{}")
    # A later equivalent window can update advisory metadata without invalidating an earlier chain.
    if problem is None:
        observe(dict(base, safe_urls=["https://example.com"]), 40)
    if problem == "held-branch":
        _, held = observe(dict(base, **window(["y", "z"], False, False), current_node="z", update_time=35), 40)
        held.update(coverage="branch", decision="missing-messages")
        (observations / "40.json").write_text(b.encoded(held))

    assert b.raw_backup(raw, output, True, "jsonl", verbose=True) == 0
    row = json.loads(capsys.readouterr().out)
    if problem:
        assert row["status"] == ("stale-capture" if problem in {"changed-branch", "hidden-message", "held-branch"} else "deferred")
        if problem == "held-branch":
            assert "preserved in version history" in row["reason"]
        assert not output.exists()
        if problem in {"bad-hash", "gap"}:
            cache = tmp_path / "cache.json"
            assert b.raw_backup(raw, output, False, "jsonl", verbose=True, cache_path=cache) == 0
            assert json.loads(capsys.readouterr().out) == row
            if problem == "bad-hash":
                oldest_path.write_text(oldest_data)
            else:
                observe(window(["a"], False, True), 35, before="b")
            assert b.raw_backup(raw, output, True, "jsonl", verbose=True, cache_path=cache) == 0
            assert json.loads(capsys.readouterr().out)["status"] == "would-create"
    else:
        assert row["status"] == "would-create"
        assert row["sourceType"] == "cursor-pages"
        assert b.raw_backup(raw, output, False, "jsonl", verbose=True) == 0
        text = (output / "Paged.md").read_text()
        assert [text.index(f"Message {mid}") for mid in "abcd"] == sorted(text.index(f"Message {mid}") for mid in "abcd")
        assert (raw / f"{cid}.json").read_text() == data
        capsys.readouterr()
        assert b.raw_backup(raw, output, False, "jsonl", verbose=True) == 0
        assert json.loads(capsys.readouterr().out)["status"] == "up-to-date"
