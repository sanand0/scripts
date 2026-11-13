"""Offline output contracts for caption matching and the executable transcription queue."""
import importlib.util
import os
import shlex
import subprocess
import sys
from datetime import datetime
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest
from typer.testing import CliRunner


@pytest.fixture
def m(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_loader('callprompt', SourceFileLoader('callprompt', str(root / 'callprompt')))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, 'QUEUE', tmp_path / 'transcribe.sh')
    monkeypatch.setattr(module.call, 'DEFAULT_INPUT_DIR', tmp_path)
    monkeypatch.setattr(module.call, 'DEFAULT_OUTPUT_DIR', tmp_path / 'notes')
    return module


def row(tmp_path, name='gmeet.md', header='# IITM', day='2026-11-13', mtime=1000):
    path = tmp_path / name
    path.write_text(header + '\n## Speaker [0:00]\nHello')
    return {'path': path, 'header': header, 'started': datetime.fromisoformat(day + 'T12:00:00'), 'mtime': mtime}


def test_match_day_header_explicit_latest_and_ambiguity(m, tmp_path):
    audio = tmp_path / '2026-11-13 IITM.opus'
    audio.touch()
    os.utime(audio, (1000, 1000))
    good = row(tmp_path)
    other = row(tmp_path, 'teams.md', '# Something else', mtime=1100)
    stale = row(tmp_path, 'gmeet-old.md', '# IITM', day='2026-11-12')
    assert m.match_caption(audio, [other, stale, good])[0] == good['path']
    assert m.match_caption(audio, [stale])[0] is None
    assert m.match_caption(audio, [other, stale, good], 'IITM')[0] == good['path']
    good['header'] = '# unrelated'
    assert m.match_caption(audio, [other, good])[0] is None
    assert m.match_caption(audio, [good])[0] == good['path']
    with pytest.raises(ValueError, match='No caption'):
        m.match_caption(audio, [good], 'missing')


def test_queue_round_trip_and_shell_safety(m, tmp_path):
    audio = tmp_path / "2026-11-13 O'Brien $test.opus"
    audio.touch()
    prompt = 'A says "hello"; $(touch BAD) `touch BAD` $HOME \\ end\nNext'
    line = m.command(audio, prompt)
    m.QUEUE.write_text('#!/bin/sh\n# Don\'t delete history\n# call --patch "older.opus" --prompt "old"\n')
    m.QUEUE.chmod(0o755)
    assert m.prepend(m.QUEUE, line)
    assert not m.prepend(m.QUEUE, line)
    assert m.queued_files(m.QUEUE.read_text()) == {audio.name, 'older.opus'}
    assert m.QUEUE.read_text().startswith('#!/bin/sh\ncall ')
    assert m.QUEUE.stat().st_mode & 0o777 == 0o755
    result = subprocess.run(['bash', '-c', 'call() { printf "%s\\0" "$@"; }; ' + line], cwd=tmp_path, capture_output=True, check=True)
    assert result.stdout.decode().split('\0')[:-1] == [str(audio), '--prompt', ' '.join(prompt.splitlines())]
    assert not (tmp_path / 'BAD').exists()
    assert shlex.split(line)[1] == str(audio)


def test_latest_repeated_export(m, tmp_path):
    audio = tmp_path / '2026-11-13 IITM.opus'
    audio.touch()
    older = row(tmp_path, 'gmeet-old.md')
    newer = row(tmp_path, 'gmeet-new.md', mtime=2000)
    assert m.match_caption(audio, [older, newer])[0] == newer['path']


def test_caption_export_utc_date_and_header_search(m, tmp_path, monkeypatch):
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    (tmp_path / 'Downloads').mkdir()
    (tmp_path / 'Documents').mkdir()
    path = tmp_path / 'Downloads/gmeet-code-2026-11-12-23-30-00.md'
    path.write_text('# Title\n- **Meeting code**: abc-defg-hij\n' + '\n' * 20 + 'BodyOnly')
    rows = m.captions()
    assert rows[0]['started'].timestamp() == datetime.fromisoformat('2026-11-12T23:30:00+00:00').timestamp()
    assert m.match_caption(tmp_path / 'anything.opus', rows, 'abc-defg-hij')[0] == path
    with pytest.raises(ValueError):
        m.match_caption(tmp_path / 'anything.opus', rows, 'BodyOnly')


def test_dry_run_and_process_then_skip(m, tmp_path, monkeypatch):
    audio = tmp_path / '2026-11-13 IITM.opus'
    audio.touch()
    source = row(tmp_path)
    monkeypatch.setattr(m, 'captions', lambda: [source])
    calls = []
    monkeypatch.setattr(m.meetcall, 'context_prompt', lambda text, account: calls.append(text) or 'Speaker context')
    runner = CliRunner()
    preview = runner.invoke(m.app, ['IITM', '--dry-run', '--format', 'jsonl'])
    assert preview.exit_code == 0, preview.output
    assert 'pending' in preview.stdout
    assert not calls and not m.QUEUE.exists()
    result = runner.invoke(m.app, ['IITM'])
    assert result.exit_code == 0, result.output
    assert len(calls) == 1
    assert shlex.split(m.QUEUE.read_text()) == ['call', str(audio), '--prompt', 'Speaker context']
    result = runner.invoke(m.app, ['IITM'])
    assert result.exit_code == 0 and 'skip' in result.stdout
    assert len(calls) == 1


def test_completed_skips_but_incomplete_remains(m, tmp_path, monkeypatch):
    audio = tmp_path / '2026-11-13 IITM.opus'
    audio.touch()
    notes = m.call.DEFAULT_OUTPUT_DIR
    notes.mkdir()
    note = notes / f'{audio.stem}.md'
    note.write_text('## Transcript\n\n**Anand**: [00:00] Hello.\n')
    monkeypatch.setattr(m, 'captions', lambda: [row(tmp_path)])
    result = CliRunner().invoke(m.app, ['IITM', '--dry-run'])
    assert result.exit_code == 0 and 'skip' in result.stdout
    note.write_text('---\ntranscription_status: incomplete\n---\n' + note.read_text())
    result = CliRunner().invoke(m.app, ['IITM', '--dry-run'])
    assert result.exit_code == 0 and 'pending' in result.stdout


@pytest.mark.parametrize('dry_run', [False, True])
def test_batch_hides_unmatched_and_shortens_audio(m, tmp_path, monkeypatch, dry_run):
    matched = tmp_path / '2026-11-13 IITM.opus'
    matched.touch()
    unmatched = tmp_path / '2026-11-12 Other.opus'
    unmatched.touch()
    monkeypatch.setattr(m, 'captions', lambda: [row(tmp_path)])
    monkeypatch.setattr(m.meetcall, 'context_prompt', lambda *args: 'Speaker context')
    result = CliRunner().invoke(m.app, ['--dry-run'] if dry_run else [])
    assert result.exit_code == 0, result.output
    assert result.stdout.split('\t')[:2] == ['pending', matched.name]
    assert unmatched.name not in result.stdout
    assert str(matched) not in result.stdout
    if not dry_run:
        assert shlex.split(m.QUEUE.read_text())[1] == str(matched)
    result = CliRunner().invoke(m.app, ['Other', '--dry-run'])
    assert result.exit_code == 0 and 'unmatched' in result.stdout


def test_write_failure_precedes_paid_model(m, tmp_path, monkeypatch):
    (tmp_path / '2026-11-13 IITM.opus').touch()
    monkeypatch.setattr(m, 'captions', lambda: [row(tmp_path)])
    def fail(path):
        raise PermissionError('read-only destination')
    monkeypatch.setattr(m.call, 'preflight_write', fail)
    monkeypatch.setattr(m.meetcall, 'context_prompt', lambda *args: pytest.fail('paid request before preflight'))
    result = CliRunner().invoke(m.app, ['IITM'])
    assert result.exit_code != 0 and 'read-only' in result.output


def test_model_failure_preserves_queue(m, tmp_path, monkeypatch):
    (tmp_path / '2026-11-13 IITM.opus').touch()
    m.QUEUE.write_text('# saved history\n')
    monkeypatch.setattr(m, 'captions', lambda: [row(tmp_path)])
    def fail(*args):
        raise RuntimeError('Luna failed')
    monkeypatch.setattr(m.meetcall, 'context_prompt', fail)
    result = CliRunner().invoke(m.app, ['IITM'])
    assert result.exit_code != 0
    assert m.QUEUE.read_text() == '# saved history\n'


@pytest.mark.parametrize('args', [['--caption', 'x'], ['x', '--audio', 'y'], ['--format', 'csv']])
def test_invalid_options(m, args):
    assert CliRunner().invoke(m.app, args).exit_code != 0
