"""Offline contract tests; all Google and model calls are replaced."""
import importlib.util
import sys
from datetime import datetime
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def forbid_real_subprocesses(monkeypatch):
    import subprocess
    def forbidden(*args, **kwargs):
        pytest.fail(f'Unit test attempted a real subprocess: {args[0][0]}')
    monkeypatch.setattr(subprocess, 'run', forbidden)


def load():
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    spec = importlib.util.spec_from_loader('meetcall', SourceFileLoader('meetcall', str(root / 'meetcall')))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def event(title='TDS', start='2026-11-04T09:30:00+05:30', **extra):
    return dict(summary=title, start={'dateTime': start}, end={'dateTime': start}, **extra)


def test_match_latest_exact_and_substring():
    m = load()
    rows = [event(), event('TDS Workshop', '2026-11-09T10:00:00+05:30'), event('tds', '2026-11-11T09:30:00+05:30')]
    assert m.choose(rows, 'TDS')['start']['dateTime'].startswith('2026-11-11')
    assert m.choose(rows, 'work')['summary'] == 'TDS Workshop'
    assert m.choose(rows, '2026-11-04 TDS')['start']['dateTime'].startswith('2026-11-04')
    with pytest.raises(ValueError, match='No completed meeting'):
        m.choose(rows, 'absent')


def test_date_bounds():
    m = load()
    now = datetime.fromisoformat('2026-11-12T20:00:00+08:00')
    low, high = m.bounds('yesterday', None, None, now)
    assert low.isoformat() == '2026-11-11T00:00:00+08:00'
    assert high.isoformat() == '2026-11-12T00:00:00+08:00'
    low, high = m.bounds(None, 'Nov 10 2026', 'Nov 4 2026', now)
    assert low.day == 5 and high.day == 10
    assert m.bounds('last Wednesday', None, None, now)[0].day == 11
    with pytest.raises(ValueError):
        m.bounds('nonsense', None, None, now)
    with pytest.raises(ValueError):
        m.bounds('yesterday', 'today', None, now)


RAW = '''*Please **rate the new Quick notes tab** survey*\n\n## **TDS**\n\nNov 4, 2026\n\n[A](mailto:a@example.com)\n\nA useful overview.\n\n## **Design decisions**\n\n* Keep SQLite.\n\n## **Next steps**\n\n- [ ] Ship on Friday.\n\n**Want to see more?** [View the full notes]()\nTip: sidebar\n\n### **Summary**\n\nA duplicate overview.\n\n### **Details**\n\nLots of verbose detail.\n\n## **TDS \\- Transcript**\n\n### **00:00:05** {#00:00:05}\n\n**Anand S:** Hello.\n\n**Other:** Yes.\n\n### **00:01:10**\n\n**Anand S:** Keep the literal [document](https://example.com).\n\n### **Transcription ended after 00:02:00**\n\n*This editable transcript was computer generated*\n\n[image1]: <data:image/png;base64,NOPE>\n'''


def test_clean_summary_transcript():
    m = load()
    summary, transcript = m.clean_document(RAW)
    assert 'Keep SQLite' in summary and 'Ship on Friday' in summary
    assert 'duplicate' not in summary and 'verbose detail' not in summary
    assert '**Anand S**: [00:00:05] Hello.' in transcript
    assert '**Other**: [00:00:05] Yes.' in transcript
    assert '[00:01:10]' in transcript and 'https://example.com' in transcript
    assert not any(word in summary + transcript for word in ['survey', 'sidebar', 'base64', 'computer generated', 'Transcription ended'])


def test_summary_only_is_not_a_transcript():
    m = load()
    summary, transcript = m.clean_document(RAW.split('## **TDS \\- Transcript**')[0])
    assert summary and not transcript


def test_update_preserves_other_sections_and_skips_nonempty(tmp_path):
    m = load()
    path = tmp_path / 'note.md'
    path.write_text('---\ntags: [mine]\n---\n\n# Note\n\n## Actions\n\nKeep me.\n\n## Transcript\n\n## Later\n\nAlso keep.\n')
    m.save_note(path, 'Note', 'Summary', '**A**: [00:00] Hello', ['https://docs.google.com/document/d/id/edit'])
    text = path.read_text()
    assert 'tags: [mine]' in text and 'Keep me.' in text and 'Also keep.' in text
    assert '## Summary\n\nSummary' in text
    assert m.call.has_transcript_content(text)
    m.save_note(path, 'Note', 'Different summary', 'Different transcript', [])
    assert path.read_text() == text


def test_download_uses_opus_settings_and_reuses_file(tmp_path, monkeypatch):
    m = load()
    commands = []
    def fake_run(args, **kwargs):
        commands.append(args)
        Path(args[-1]).write_bytes(b'opus')
    def fake_gws(args, profile, cwd):
        (Path(cwd) / args[-1]).write_bytes(b'video')
    monkeypatch.setattr(m, 'run', fake_run)
    monkeypatch.setattr(m, 'gws', fake_gws)
    path = tmp_path / 'call.opus'
    m.download_audio('profile', [{'fileId': 'recording'}], path)
    assert commands[0][commands[0].index('-b:a') + 1] == '12k'
    assert commands[0][commands[0].index('-vbr') + 1] == 'on'
    m.download_audio('profile', [{'fileId': 'recording'}], path)
    assert len(commands) == 1


def test_dry_run_has_no_writes_or_model_requests(tmp_path, monkeypatch):
    m = load()
    e = event(attachments=[{'fileId': 'doc', 'mimeType': 'application/vnd.google-apps.document'}], _profile='p', _account='me')
    monkeypatch.setattr(m, 'search', lambda *args: [e])
    def forbidden(*args, **kwargs):
        pytest.fail('dry-run performed a write/download/model call')
    monkeypatch.setattr(m, 'export_documents', forbidden)
    monkeypatch.setattr(m, 'download_audio', forbidden)
    monkeypatch.setattr(m.call, 'preflight_write', forbidden)
    m.main('TDS', date=None, before=None, after=None, account=[], dry_run=True, input_dir=tmp_path/'audio', out_dir=tmp_path/'notes', describe=False)
    assert not (tmp_path/'audio').exists() and not (tmp_path/'notes').exists()


def test_no_sources_and_summary_only_fail_without_creating_note(tmp_path, monkeypatch):
    m = load()
    e = event(_profile='p', _account='me')
    monkeypatch.setattr(m, 'search', lambda *args: [e])
    with pytest.raises(ValueError, match='no recording or transcript'):
        m.main('TDS', date=None, before=None, after=None, account=[], dry_run=False, input_dir=tmp_path/'audio', out_dir=tmp_path/'notes', describe=False)
    with pytest.raises(ValueError, match='no transcript speaker turns'):
        m.save_note(tmp_path/'note.md', 'Title', 'Only a summary', '', [])
    assert not (tmp_path/'note.md').exists()


def test_context_uses_requested_fragment_model_and_thinking(tmp_path, monkeypatch):
    from types import SimpleNamespace
    m = load()
    fragment = tmp_path/'fragments.md'
    fragment.write_text('## Other\n\nWrong\n\n## Meeting transcript context\n\n```markdown\nRight instruction\n```\n\n## End\n')
    monkeypatch.setattr(m, 'FRAGMENTS', fragment)
    monkeypatch.setattr(m, 'CACHE', tmp_path/'cache')
    requests = []
    def fake_run(args, **kwargs):
        requests.append((args, kwargs))
        return SimpleNamespace(stdout='Anand led the discussion.\n')
    monkeypatch.setattr(m, 'run', fake_run)
    assert m.context_prompt('Speaker turns', 'me@example.com') == 'Anand led the discussion.'
    args, kwargs = requests[0]
    assert args[args.index('-m')+1] == 'gpt-6-luna'
    assert args[args.index('-o')+1:args.index('-o')+3] == ['reasoning_effort', 'high']
    assert args[args.index('-s')+1] == 'Right instruction'
    assert kwargs['input'] == 'Speaker turns'
    m.context_prompt('Speaker turns', 'me@example.com')
    assert len(requests) == 1


def test_search_expands_series_and_handles_midnight(tmp_path, monkeypatch):
    m = load()
    monkeypatch.setattr(m.Path, 'home', lambda: tmp_path)
    monkeypatch.delenv('GOOGLE_WORKSPACE_CLI_CONFIG_DIR', raising=False)
    monkeypatch.setattr(m, 'gws_json', lambda *a, **kw: {'user': {'emailAddress': 'me'}})
    def fake_items(profile, resource, params, key):
        if resource.endswith('calendarList list'):
            return [{'id': 'primary'}]
        if resource.endswith('events list'):
            return [event('TDS', id='series', recurrence=['RRULE:FREQ=WEEKLY'])]
        assert resource.endswith('events instances') and params['eventId'] == 'series'
        return [
            {'summary': 'TDS', 'start': {'dateTime': '2026-11-10T23:00:00+08:00'}, 'end': {'dateTime': '2026-11-11T01:00:00+08:00'}},
            event('TDS', status='cancelled'),
        ]
    monkeypatch.setattr(m, 'items', fake_items)
    rows = m.search('TDS', datetime.fromisoformat('2026-11-10T00:00:00+08:00'), datetime.fromisoformat('2026-11-11T00:00:00+08:00'), [])
    assert len(rows) == 1 and rows[0]['_account'] == 'me'


def test_paginate_without_silent_page_limit(monkeypatch):
    m = load()
    requests = []
    def response(args, **kwargs):
        params = __import__('json').loads(args[-1])
        requests.append(params)
        return {'items': [2]} if params.get('pageToken') else {'items': [1], 'nextPageToken': 'next'}
    monkeypatch.setattr(m, 'gws_json', response)
    assert list(m.items('p', 'calendar events list', {}, 'items')) == [1, 2]
    assert requests == [{}, {'pageToken': 'next'}]


def test_recording_handoff_uses_call_output_option(tmp_path, monkeypatch):
    m = load()
    e = event(attachments=[{'fileId': 'video', 'mimeType': 'video/mp4'}], _profile='p', _account='me')
    monkeypatch.setattr(m, 'search', lambda *args: [e])
    monkeypatch.setattr(m, 'download_audio', lambda *args: None)
    requests = []
    monkeypatch.setattr(m, 'run', lambda args, **kwargs: requests.append(args))
    m.main('TDS', date=None, before=None, after=None, account=[], dry_run=False, input_dir=tmp_path/'audio', out_dir=tmp_path/'notes', describe=False)
    assert requests == [[str(Path(m.__file__).with_name('call')), str(tmp_path/'audio/2026-11-04 TDS.opus'), '--out', str(tmp_path/'notes')]]


def test_plain_transcript_heading():
    m = load()
    assert m.clean_document('## Transcript\n\n**A:** Hello.')[1] == '**A**: [00:00:00] Hello.'


def test_exact_dated_name_beats_newer_substring(tmp_path, monkeypatch):
    m = load()
    monkeypatch.setattr(m.Path, 'home', lambda: tmp_path)
    monkeypatch.delenv('GOOGLE_WORKSPACE_CLI_CONFIG_DIR', raising=False)
    monkeypatch.setattr(m, 'gws_json', lambda *a, **kw: {'user': {'emailAddress': 'me'}})
    def fake_items(profile, resource, params, key):
        if resource.endswith('calendarList list'):
            return [{'id': 'primary'}]
        if resource.endswith('events list'):
            return [event('2025-01-01 TDS workshop', id='newer'), event('TDS', '2020-01-01T09:30:00+05:30', id='series', recurrence=['RRULE:FREQ=WEEKLY'])]
        assert params['timeMin'].startswith('2019-')
        return [event('TDS', '2025-01-01T09:30:00+05:30')]
    monkeypatch.setattr(m, 'items', fake_items)
    rows = m.search('2025-01-01 TDS', datetime.fromisoformat('2019-01-01T00:00:00+08:00'), datetime.fromisoformat('2026-11-12T00:00:00+08:00'), [])
    assert m.choose(rows, '2025-01-01 TDS')['start']['dateTime'].startswith('2025-')


def test_bare_title_does_not_hide_more_recent_substring():
    m = load()
    assert m.choose([event('TDS', '2026-02-19T15:00:00+08:00'), event('TDS Weekly Catchup')], 'TDS')['summary'] == 'TDS Weekly Catchup'


def test_chat_included_without_retranscribing_completed_note(tmp_path, monkeypatch):
    m = load()
    out = tmp_path/'notes'
    out.mkdir()
    note = out/'2026-11-04 TDS.md'
    note.write_text('# TDS\n\n## Transcript\n\n**A**: Hello.\n')
    e = event(attachments=[{'fileId': 'chat', 'mimeType': 'text/plain', 'title': 'Meeting - Chat'}], _profile='p', _account='me')
    monkeypatch.setattr(m, 'search', lambda *args: [e])
    monkeypatch.setattr(m, 'export_chats', lambda *args: '00:01 A: https://example.com\n## Transcript\nLiteral chat.')
    monkeypatch.setattr(m, 'run', lambda *args, **kwargs: pytest.fail('retranscribed existing audio'))
    m.main('TDS', date=None, before=None, after=None, account=[], dry_run=False, input_dir=tmp_path/'audio', out_dir=out, describe=False)
    text = note.read_text()
    assert '## Chat\n\n> 00:01 A: https://example.com' in text
    assert m.call.count_transcript_sections(text) == 1
    m.add_chat(note, 'different chat')
    assert note.read_text() == text


def test_chat_export_preserves_text_and_skips_restricted_files(tmp_path, monkeypatch):
    m = load()
    monkeypatch.setattr(m, 'gws_json', lambda args, **kwargs: {'capabilities': {'canDownload': 'blocked' not in args[-1]}})
    def download(args, profile, cwd):
        (cwd/args[-1]).write_text('00:01 Anand: Hello\n00:02 A: link https://example.com')
    monkeypatch.setattr(m, 'gws', download)
    text = m.export_chats('p', [{'fileId': 'allowed'}, {'fileId': 'blocked'}])
    assert text.count('Hello') == 1 and 'https://example.com' in text


@pytest.mark.parametrize('local', [False, True])
def test_chat_is_in_luna_input_and_final_recording_note(tmp_path, monkeypatch, local):
    m = load()
    e = event(attachments=[{'fileId': 'v', 'mimeType': 'video/mp4'}, {'fileId': 'd', 'mimeType': 'application/vnd.google-apps.document'}, {'fileId': 'c', 'mimeType': 'text/plain', 'title': 'Meeting Chat'}], _profile='p', _account='me')
    monkeypatch.setattr(m, 'search', lambda *a: [e])
    monkeypatch.setattr(m, 'download_audio', lambda *a: None)
    monkeypatch.setattr(m, 'export_documents', lambda *a: ('Summary', '**A**: Spoken', 'Original transcript'))
    monkeypatch.setattr(m, 'export_chats', lambda *a: '00:01 A: The shared link')
    prompts = []
    monkeypatch.setattr(m, 'context_prompt', lambda original, account: prompts.append(original) or 'Context')
    note = tmp_path/'notes/2026-11-04 TDS.md'
    def fake_call(*args, **kwargs):
        note.write_text('# TDS\n\n## Transcript\n\n**A**: Spoken\n')
    monkeypatch.setattr(m, 'run', fake_call)
    chat_file = tmp_path/'messages.txt'
    chat_file.write_text('00:01 A: The shared link')
    if local:
        monkeypatch.setattr(m, 'export_chats', lambda *a: pytest.fail('downloaded despite local file'))
    m.main('TDS', date=None, before=None, after=None, account=[], dry_run=False, input_dir=tmp_path/'audio', out_dir=note.parent, describe=False, chat_file=chat_file if local else None)
    assert 'Original transcript' in prompts[0] and '00:01 A: The shared link' in prompts[0]
    assert '## Chat' in note.read_text()


def test_local_chat_overrides_download_and_replaces_existing_section(tmp_path, monkeypatch):
    m = load()
    note = tmp_path/'2026-11-04 TDS.md'
    note.write_text('# TDS\n\n## Transcript\n\n**A**: Spoken\n\n## Chat\n\n> Old chat\n\n## Actions\n\nKeep me.\n')
    chat = tmp_path/'messages.txt'
    chat.write_text('New chat\n00:01 A: https://example.com')
    monkeypatch.setattr(m, 'search', lambda *a: [event(_profile='p', _account='me')])
    monkeypatch.setattr(m, 'export_chats', lambda *a: pytest.fail('downloaded despite local override'))
    monkeypatch.setattr(m, 'run', lambda *a, **kw: pytest.fail('retranscribed completed note'))
    from typer.testing import CliRunner
    result = CliRunner().invoke(m.app, ['TDS', '--out-dir', str(tmp_path), '--chat', str(chat)])
    assert result.exit_code == 0, result.output
    assert 'Action: Update chat' in result.output
    text = note.read_text()
    assert 'New chat' in text and 'Old chat' not in text and 'Keep me.' in text and '**A**: Spoken' in text
    assert text.count('## Chat') == 1


def test_empty_local_chat_fails_before_search(tmp_path, monkeypatch):
    m = load()
    chat = tmp_path/'empty.txt'
    chat.write_text(' ')
    monkeypatch.setattr(m, 'search', lambda *a: pytest.fail('searched with invalid local chat'))
    with pytest.raises(ValueError, match='Chat file is empty'):
        m.main('TDS', date=None, before=None, after=None, account=[], dry_run=False, input_dir=tmp_path, out_dir=tmp_path, describe=False, chat_file=chat)


def test_search_stops_after_first_matching_calendar_and_account(tmp_path, monkeypatch):
    m = load()
    monkeypatch.setattr(m.Path, 'home', lambda: tmp_path)
    monkeypatch.delenv('GOOGLE_WORKSPACE_CLI_CONFIG_DIR', raising=False)
    another = tmp_path/'.config/gws-other@example.com'
    another.mkdir(parents=True)
    (another/'credentials.enc').touch()
    identities = []
    def identity(*args, config_dir):
        identities.append(config_dir)
        assert config_dir.endswith('/gws'), 'searched another account after a match'
        return {'user': {'emailAddress': 'first@example.com'}}
    monkeypatch.setattr(m, 'gws_json', identity)
    def responses(profile, resource, params, key):
        if resource.endswith('calendarList list'):
            yield {'id': 'primary'}
            pytest.fail('continued listing calendars after a match')
        else:
            yield event('TDS', id='older')
            yield event('TDS Weekly Catchup', '2026-11-11T09:30:00+05:30', id='newest')
    monkeypatch.setattr(m, 'items', responses)
    rows = m.search('TDS', datetime.fromisoformat('2026-11-01T00:00:00+08:00'), datetime.fromisoformat('2026-11-12T00:00:00+08:00'), [])
    assert m.choose(rows, 'TDS')['id'] == 'newest'
    assert len(identities) == 1


@pytest.mark.parametrize('stage', ['metadata', 'download'])
@pytest.mark.parametrize('code', [403, 404])
def test_optional_chat_failure_is_one_warning_without_raw_api_error(tmp_path, monkeypatch, capsys, stage, code):
    import json
    import subprocess
    m = load()
    def request(args, **kwargs):
        is_metadata = 'capabilities' in ' '.join(args)
        if is_metadata and stage == 'download':
            return subprocess.CompletedProcess(args, 0, json.dumps({'capabilities': {'canDownload': True}}), '')
        assert kwargs.get('capture_output'), 'optional gws requests leaked raw errors'
        raise subprocess.CalledProcessError(2, args, json.dumps({'error': {'code': code, 'reason': 'notFound', 'message': 'File not found: private-chat-id'}}), 'error[api]: File not found: private-chat-id')
    monkeypatch.setattr(m, 'run', request)
    assert m.export_chats('profile', [{'fileId': 'private-chat-id', 'title': 'TDS - Chat'}]) == ''
    captured = capsys.readouterr()
    assert 'error[api]' not in captured.err and 'private-chat-id' not in captured.err
    assert captured.err.count('WARNING') == 1 and '--chat' in captured.err


@pytest.mark.parametrize('code,reason', [(401, 'authError'), (429, 'rateLimitExceeded'), (500, 'backendError'), (403, 'rateLimitExceeded'), (403, 'downloadQuotaExceeded')])
def test_optional_chat_does_not_hide_auth_network_or_quota_errors(monkeypatch, code, reason):
    import json
    import subprocess
    m = load()
    def request(*args, **kwargs):
        raise subprocess.CalledProcessError(2, ['gws'], json.dumps({'error': {'code': code, 'reason': reason}}), 'Failure')
    monkeypatch.setattr(m, 'run', request)
    with pytest.raises(subprocess.CalledProcessError):
        m.export_chats('profile', [{'fileId': 'chat'}])


def test_recording_with_missing_google_doc_still_transcribes(tmp_path, monkeypatch, capsys):
    import json
    import subprocess
    m = load()
    e = event(attachments=[{'fileId': 'video', 'mimeType': 'video/mp4'}, {'fileId': 'deleted-doc', 'mimeType': 'application/vnd.google-apps.document'}], _profile='p', _account='me')
    monkeypatch.setattr(m, 'search', lambda *a: [e])
    monkeypatch.setattr(m, 'download_audio', lambda *a: None)
    calls = []
    def request(args, **kwargs):
        if args[0] == 'gws':
            raise subprocess.CalledProcessError(2, args, json.dumps({'error': {'code': 404, 'message': 'File not found'}}), 'error[api]: File not found')
        calls.append(args)
        (tmp_path/'2026-11-04 TDS.md').write_text('# TDS\n\n## Transcript\n\n**A**: [00:00] Hello.\n')
    monkeypatch.setattr(m, 'run', request)
    m.main('TDS', date=None, before=None, after=None, account=[], dry_run=False, input_dir=tmp_path/'audio', out_dir=tmp_path, describe=False)
    assert len(calls) == 1 and '--prompt' not in calls[0]
    output = capsys.readouterr()
    assert 'WARNING skipping inaccessible transcript document' in output.err
    assert 'error[api]' not in output.err


def test_incomplete_note_resumes_with_stored_context_instead_of_skipping(tmp_path, monkeypatch):
    m = load()
    note = tmp_path/'2026-11-04 TDS.md'
    note.write_text('---\ntranscription_status: incomplete\nprompt: Stored speaker context\n---\n\n# TDS\n\n## Transcript\n\n[Transcription failed: rerun call.]\n')
    e = event(attachments=[{'fileId': 'video', 'mimeType': 'video/mp4'}, {'fileId': 'notes', 'mimeType': 'application/vnd.google-apps.document'}], _profile='p', _account='me')
    monkeypatch.setattr(m, 'search', lambda *a: [e])
    monkeypatch.setattr(m, 'download_audio', lambda *a: None)
    monkeypatch.setattr(m, 'export_documents', lambda *a: ('Summary', '**A**: [00:00] Words', 'Original transcript'))
    monkeypatch.setattr(m, 'context_prompt', lambda *a: pytest.fail('generated paid context again'))
    calls = []
    monkeypatch.setattr(m, 'run', lambda args, **kwargs: calls.append(args))
    m.main('TDS', date=None, before=None, after=None, account=[], dry_run=False, input_dir=tmp_path/'audio', out_dir=tmp_path, describe=False)
    assert len(calls) == 1 and calls[0][-2:] == ['--prompt', 'Stored speaker context']



def test_scan_defaults_to_seven_days_and_has_no_downloads_in_dry_run(tmp_path, monkeypatch):
    from datetime import timedelta

    from typer.testing import CliRunner
    m = load()
    requests = []
    def search(query, low, high, accounts, *, all_calendars=False):
        requests.append((query, low, high, accounts, all_calendars))
        return [event(attachments=[{'fileId': 'video', 'mimeType': 'video/mp4'}], _profile='p', _account='me')]
    monkeypatch.setattr(m, 'search', search)
    monkeypatch.setattr(m, 'download_audio', lambda *a: pytest.fail('dry-run downloaded audio'))
    result = CliRunner().invoke(m.app, ['--scan', '--dry-run', '--out-dir', str(tmp_path/'notes')])
    assert result.exit_code == 0, result.output
    query, low, high, accounts, all_calendars = requests[0]
    assert query == '' and high-low == timedelta(days=7) and accounts == [] and all_calendars
    assert not (tmp_path/'notes').exists()
    assert 'Action: Create transcript (dry run)' in result.output


@pytest.mark.parametrize('flags,days', [(['--days', '21'], 21), (['--before', '2026-11-10', '--days', '3'], 3)])
def test_scan_range_can_be_configured(tmp_path, monkeypatch, flags, days):
    from datetime import timedelta

    from typer.testing import CliRunner
    m = load()
    ranges = []
    monkeypatch.setattr(m, 'search', lambda query, low, high, accounts, **kw: ranges.append((low,high)) or [])
    result = CliRunner().invoke(m.app, ['--scan', '--dry-run', *flags, '--out-dir', str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert ranges[0][1] - ranges[0][0] == timedelta(days=days)


def test_scan_skips_completed_and_document_only_meetings_deduplicates_and_limits(tmp_path, monkeypatch):
    from typer.testing import CliRunner
    m = load()
    (tmp_path/'2026-11-04 Complete.md').write_text('# Complete\n\n## Transcript\n\n**A**: Already done.\n')
    (tmp_path/'2026-11-04 Incomplete.md').write_text('---\ntranscription_status: incomplete\n---\n\n# Incomplete\n\n## Transcript\n\n[Pending]\n')
    def recording(title, file_id):
        return event(title, id=title, attachments=[{'fileId': file_id, 'mimeType': 'video/mp4'}], _profile='p', _account='me')
    pending = recording('Incomplete', 'pending')
    events = [recording('Complete', 'done'), event('Only document', attachments=[{'fileId': 'doc', 'mimeType': 'application/vnd.google-apps.document'}]), pending, {**pending, '_profile': 'other'}, recording('New', 'new')]
    monkeypatch.setattr(m, 'search', lambda *a, **kw: events)
    processed = []
    monkeypatch.setattr(m, 'process_meeting', lambda event, *a, **kw: processed.append(event['summary']))
    result = CliRunner().invoke(m.app, ['--scan', '--out-dir', str(tmp_path), '--limit', '1'])
    assert result.exit_code == 0, result.output
    assert processed == ['Incomplete']


def test_scan_searches_later_calendars_and_accounts_and_expands_occurrences_server_side(tmp_path, monkeypatch):
    m = load()
    monkeypatch.setattr(m.Path, 'home', lambda: tmp_path)
    monkeypatch.delenv('GOOGLE_WORKSPACE_CLI_CONFIG_DIR', raising=False)
    profile = tmp_path/'.config/gws-second@example.com'
    profile.mkdir(parents=True)
    (profile/'credentials.enc').touch()
    identities = []
    def identity(*args, config_dir):
        identities.append(config_dir)
        return {'user': {'emailAddress': 'second@example.com' if config_dir.endswith('second@example.com') else 'first@example.com'}}
    monkeypatch.setattr(m, 'gws_json', identity)
    def responses(profile, resource, params, key):
        if resource.endswith('calendarList list'):
            assert params['showHidden'] is True
            return [{'id': 'first'}, {'id': 'second'}]
        assert resource.endswith('events list') and params['singleEvents'] is True
        return [event(params['calendarId'], id=profile+params['calendarId'])]
    monkeypatch.setattr(m, 'items', responses)
    rows = m.search('', datetime.fromisoformat('2026-11-01T00:00:00+08:00'), datetime.fromisoformat('2026-11-12T00:00:00+08:00'), [], all_calendars=True)
    assert len(identities) == 2 and len(rows) == 4


@pytest.mark.parametrize('flags', [['--days', '0'], ['--chat', 'messages.txt'], ['--limit', '0']])
def test_scan_rejects_invalid_or_ambiguous_options(tmp_path, monkeypatch, flags):
    from typer.testing import CliRunner
    m = load()
    monkeypatch.chdir(tmp_path)
    (tmp_path/'messages.txt').write_text('A: Hello')
    monkeypatch.setattr(m, 'search', lambda *a, **kw: pytest.fail('searched with invalid scan flags'))
    result = CliRunner().invoke(m.app, ['--scan', *flags])
    assert result.exit_code != 0


def test_scan_explicit_after_overrides_default_lookback(tmp_path, monkeypatch):
    from typer.testing import CliRunner
    m = load()
    ranges = []
    monkeypatch.setattr(m, 'search', lambda query, low, high, accounts, **kw: ranges.append((low,high)) or [])
    result = CliRunner().invoke(m.app, ['--scan', '--after', '2026-10-20', '--before', '2026-11-01', '--dry-run'])
    assert result.exit_code == 0, result.output
    assert ranges[0][0].isoformat().startswith('2026-10-21T00:00:00')
    assert ranges[0][1].isoformat().startswith('2026-11-01T00:00:00')


def test_scan_skips_complete_document_alias_and_includes_empty_transcript(tmp_path):
    m = load()
    (tmp_path/'2026-11-04 Renamed.md').write_text('# Personal title\n\nhttps://docs.google.com/document/d/notes-id/edit\n\n## Transcript\n\n**A**: Done.\n')
    (tmp_path/'2026-11-04 Empty.md').write_text('# Empty\n\n## Transcript\n\n')
    complete = event('Calendar title', attachments=[{'fileId': 'recording', 'mimeType': 'video/mp4'}, {'fileId': 'notes-id', 'mimeType': 'application/vnd.google-apps.document'}])
    empty = event('Empty', attachments=[{'fileId': 'empty-recording', 'mimeType': 'video/mp4'}])
    assert m.pending_meetings([complete, empty], tmp_path) == [empty]


def test_scan_batch_failure_stops_before_next_recording(tmp_path, monkeypatch):
    from typer.testing import CliRunner
    m = load()
    rows = [event('First', attachments=[{'fileId': 'first', 'mimeType': 'video/mp4'}], _account='me'), event('Second', attachments=[{'fileId': 'second', 'mimeType': 'video/mp4'}], _account='me')]
    monkeypatch.setattr(m, 'search', lambda *a, **kw: rows)
    processed = []
    def process(event, *a, **kw):
        processed.append(event['summary'])
        raise RuntimeError('Model failed; recovery state saved')
    monkeypatch.setattr(m, 'process_meeting', process)
    result = CliRunner().invoke(m.app, ['--scan', '--out-dir', str(tmp_path)])
    assert result.exit_code != 0 and processed == ['First']


def test_scan_excludes_cancelled_all_day_future_and_ongoing_events(tmp_path, monkeypatch):
    from datetime import timedelta
    m = load()
    monkeypatch.setattr(m.Path, 'home', lambda: tmp_path)
    monkeypatch.delenv('GOOGLE_WORKSPACE_CLI_CONFIG_DIR', raising=False)
    monkeypatch.setattr(m, 'gws_json', lambda *a, **kw: {'user': {'emailAddress': 'me'}})
    now = datetime.now().astimezone()
    def timed(title, start, end, **fields):
        return {'id': title, 'summary': title, 'start': {'dateTime': start.isoformat()}, 'end': {'dateTime': end.isoformat()}, **fields}
    complete = timed('Complete', now-timedelta(hours=2), now-timedelta(hours=1))
    rows = [complete, timed('Cancelled', now-timedelta(hours=2), now-timedelta(hours=1), status='cancelled'), timed('Ongoing', now-timedelta(minutes=30), now+timedelta(hours=1)), timed('Future', now+timedelta(hours=2), now+timedelta(hours=3)), {'id': 'All day', 'summary': 'All day', 'start': {'date': now.date().isoformat()}}]
    monkeypatch.setattr(m, 'items', lambda profile, resource, params, key: [{'id': 'primary'}] if resource.endswith('calendarList list') else rows)
    assert [row['summary'] for row in m.search('', now-timedelta(days=7), now+timedelta(days=1), [], all_calendars=True)] == ['Complete']


def test_scan_processes_through_shared_pipeline_then_rerun_is_empty(tmp_path, monkeypatch):
    from typer.testing import CliRunner
    m = load()
    e = event('New meeting', attachments=[{'fileId': 'recording', 'mimeType': 'video/mp4'}], _profile='p', _account='me')
    monkeypatch.setattr(m, 'search', lambda *a, **kw: [e, {**e, '_profile': 'other-account'}])
    requests = []
    def download(profile, recordings, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'fixture audio; call subprocess is mocked')
    monkeypatch.setattr(m, 'download_audio', download)
    def transcribe(args, **kwargs):
        requests.append(args)
        assert args[0].endswith('/call') and '--out' in args
        note = tmp_path/'notes/2026-11-04 New meeting.md'
        m.call.atomic_write(note, '# New meeting\n\n## Transcript\n\n**A**: [00:00] Transcribed.\n')
    monkeypatch.setattr(m, 'run', transcribe)
    flags = ['--scan', '--date', '2026-11-04', '--input-dir', str(tmp_path/'audio'), '--out-dir', str(tmp_path/'notes')]
    runner = CliRunner()
    first = runner.invoke(m.app, flags)
    assert first.exit_code == 0, first.output
    second = runner.invoke(m.app, flags)
    assert second.exit_code == 0, second.output
    assert len(requests) == 1 and 'No pending meetings.' in second.output


def test_single_meeting_summary_is_readable_and_keeps_paths_and_sources(tmp_path, capsys):
    m = load()
    e = event('TDS Weekly Catchup', attachments=[{'fileId': 'video', 'mimeType': 'video/mp4'}, {'fileId': 'doc', 'mimeType': 'application/vnd.google-apps.document'}], _profile='p', _account='anand@study.iitm.ac.in')
    m.process_meeting(e, tmp_path/'audio', tmp_path/'notes', True)
    output = capsys.readouterr().out
    assert '2026-11-04' in output and '09:30' in output and 'TDS Weekly Catchup' in output
    assert 'anand@study.iitm.ac.in' in output
    assert '1 recording' in output and '1 notes document' in output
    assert 'Action: Create transcript (dry run)' in output
    assert str(tmp_path/'notes/2026-11-04 TDS Weekly Catchup.md') in output
    assert str(tmp_path/'audio/2026-11-04 TDS Weekly Catchup.opus') in output
    assert not output.lstrip().startswith('{')


@pytest.mark.parametrize('limit,processed_names', [(None, ['First meeting', 'Second meeting']), (1, ['First meeting'])])
def test_scan_lists_every_pending_meeting_before_processing_any(tmp_path, monkeypatch, capsys, limit, processed_names):
    m = load()
    rows = [event('First meeting', attachments=[{'fileId': 'first', 'mimeType': 'video/mp4'}], _account='me'), event('Second meeting', attachments=[{'fileId': 'second', 'mimeType': 'video/mp4'}], _account='me')]
    monkeypatch.setattr(m, 'search', lambda *a, **kw: rows)
    processed = []
    def process(event, *a, **kw):
        output = capsys.readouterr().out
        if not processed:
            assert 'Pending meetings (2)' in output
            assert '1. ' in output and 'First meeting' in output
            assert '2. ' in output and 'Second meeting' in output
            assert output.index('Second meeting') < output.index('Processing [1/')
        processed.append(event['summary'])
    monkeypatch.setattr(m, 'process_meeting', process)
    m.main('', date=None, before=None, after=None, account=[], dry_run=False, input_dir=tmp_path, out_dir=tmp_path, describe=False, scan=True, days=7, limit=limit)
    assert processed == processed_names


def test_recording_scaffold_exists_with_prompt_before_first_call(tmp_path, monkeypatch):
    m = load()
    e = event(attachments=[{'fileId': 'video', 'mimeType': 'video/mp4'}], _profile='p', _account='me')
    note = tmp_path/'2026-11-04 TDS.md'
    monkeypatch.setattr(m, 'download_audio', lambda *a: None)
    monkeypatch.setattr(m.call, 'load_system_prompt', lambda *a: 'Default transcription instructions')
    calls = []
    def fail_call(args, **kwargs):
        calls.append(args)
        text = note.read_text()
        assert '# 2026-11-04 TDS' in text and '## Transcript' in text
        assert m.call.extract_prompt_metadata(text) == 'Default transcription instructions'
        assert not m.call.has_transcript_content(text)
        raise RuntimeError('First transcription attempt failed')
    monkeypatch.setattr(m, 'run', fail_call)
    with pytest.raises(RuntimeError, match='First transcription attempt failed'):
        m.process_meeting(e, tmp_path/'audio', tmp_path, False)
    assert len(calls) == 1 and note.exists()


def test_generated_context_is_saved_before_call_and_existing_notes_are_preserved(tmp_path, monkeypatch):
    m = load()
    e = event(attachments=[{'fileId': 'video', 'mimeType': 'video/mp4'}, {'fileId': 'doc', 'mimeType': 'application/vnd.google-apps.document'}], _profile='p', _account='me')
    note = tmp_path/'2026-11-04 TDS.md'
    note.write_text('---\ntags: [important]\n---\n\n# My title\n\n## Actions\n\nKeep these actions.\n')
    monkeypatch.setattr(m, 'download_audio', lambda *a: None)
    monkeypatch.setattr(m, 'export_documents', lambda *a: ('Summary', '**A**: Spoken', 'Google notes'))
    monkeypatch.setattr(m.call, 'load_system_prompt', lambda *a: 'Default instructions')
    def context(*args):
        assert note.exists() and '## Transcript' in note.read_text()
        assert m.call.extract_prompt_metadata(note.read_text()) == 'Default instructions'
        return 'Speaker context from Luna'
    monkeypatch.setattr(m, 'context_prompt', context)
    def fail_call(*args, **kwargs):
        text = note.read_text()
        assert m.call.extract_prompt_metadata(text) == 'Speaker context from Luna'
        assert 'tags: [important]' in text and '# My title' in text and 'Keep these actions.' in text
        assert not m.call.has_transcript_content(text)
        raise RuntimeError('Call failed')
    monkeypatch.setattr(m, 'run', fail_call)
    with pytest.raises(RuntimeError, match='Call failed'):
        m.process_meeting(e, tmp_path/'audio', tmp_path, False)
