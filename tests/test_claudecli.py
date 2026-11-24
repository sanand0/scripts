from __future__ import annotations

import hashlib
import json
from pathlib import Path
import runpy
from uuid import UUID

import pytest
from typer.testing import CliRunner

CLI = Path(__file__).resolve().parents[1] / "claudecli"
ORG, OTHER, CID, HUMAN, ANSWER, REGEN = (str(UUID(int=i)) for i in range(1, 7))
ROOT = "00000000-0000-4000-8000-000000000000"


@pytest.fixture
def cli(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(CLI.parent))
    cli = runpy.run_path(str(CLI))
    monkeypatch.setitem(cli["backup"].__globals__, "CACHE_DIR", tmp_path / "cache")
    return cli


def message(id, parent, sender, text, **kwargs):
    return dict(uuid=id, parent_message_uuid=parent, sender=sender,
                content=[dict(type="text", text=text)], **kwargs)


def capture(raw, text="First answer", *, org=ORG, when=1795000000000, current=True,
            coverage="branch", hub=True, messages=None, tip=ANSWER, mode="full"):
    folder = raw / org
    folder.mkdir(parents=True, exist_ok=True)
    if messages is None:
        messages = [message(HUMAN, ROOT, "human", "The prompt", files=[{"file_name": "report.pdf"}]),
                    message(ANSWER, HUMAN, "assistant", text, stop_reason="end_turn")]
    if hub:
        value = dict(kind="hub_transcript", conversationUuid=CID, historyWindow=dict(mode=mode),
                     treeSize=len(messages), messages=messages)
        path = f"/local/claude-conversation-store/trees/{org}/{CID}"
    else:
        value = dict(uuid=CID, name="Official title", chat_messages=messages, current_leaf_message_uuid=tip)
        path = f"/api/organizations/{org}/chat_conversations/{CID}"
    data = json.dumps(value).encode()
    hash = hashlib.sha256(data).hexdigest()
    info = dict(format=1, organizationId=org, hash=hash, coverage=coverage, updateTime=when, path=path)
    if current:
        (folder / f"{CID}.json").write_bytes(data)
        (folder / f"{CID}.backup.json").write_text(json.dumps(info))
    else:
        versions = folder / "versions" / CID
        versions.mkdir(parents=True, exist_ok=True)
        (versions / f"{hash}.json").write_bytes(data)
        observations = folder / "observations"
        observations.mkdir(exist_ok=True)
        (observations / f"{hash}.json").write_text(json.dumps(dict(info, id=CID)))
    return folder / f"{CID}.json"


def backup(cli, raw, output, *opts):
    return CliRunner().invoke(cli["backup_app"], [
        "--raw-dir", str(raw), "--markdown-dir", str(output), "--format", "jsonl", *opts,
    ])


def test_dry_run_publish_and_idempotence(cli, tmp_path, monkeypatch):
    raw, output = tmp_path / "raw", tmp_path / "out"
    capture(raw)
    result = backup(cli, raw, output, "--dry-run")
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["status"] == "would-create"
    assert not output.exists()
    assert not (tmp_path / "cache").exists()
    result = backup(cli, raw, output)
    assert result.exit_code == 0, result.output
    assert not result.stdout
    target, = output.glob("*.md")
    assert f"- Link: https://claude.ai/chat/{CID}" in target.read_text()
    assert "## User\n\nThe prompt" in target.read_text()
    assert "report.pdf" in target.read_text()
    assert "## Assistant\n\nFirst answer" in target.read_text()
    previous = target.stat().st_mtime_ns
    result = backup(cli, raw, output, "--verbose")
    assert result.exit_code == 0
    assert json.loads(result.stdout)["status"] == "up-to-date"
    assert target.stat().st_mtime_ns == previous

    reads = []
    snapshot = cli["snapshot"]
    read_markdown = cli["read_markdown"]

    def track_snapshot(path, info, cid):
        reads.append(path)
        return snapshot(path, info, cid)

    def track_markdown(path):
        reads.append(path)
        return read_markdown(path)

    monkeypatch.setitem(snapshot.__globals__, "snapshot", track_snapshot)
    monkeypatch.setitem(snapshot.__globals__, "read_markdown", track_markdown)
    assert json.loads(backup(cli, raw, output, "--dry-run", "--verbose").stdout)["status"] == "up-to-date"
    assert not reads
    target.unlink()
    assert json.loads(backup(cli, raw, output, "--dry-run").stdout)["status"] == "would-create"
    assert reads == [raw / ORG / f"{CID}.json"]
    assert not target.exists()


def test_newer_observed_branch_replaces_and_revisions_preserve_exact_bytes(cli, tmp_path):
    raw, output = tmp_path / "raw", tmp_path / "out"
    capture(raw)
    assert backup(cli, raw, output).exit_code == 0
    assert backup(cli, raw, output).exit_code == 0
    target, = output.glob("*.md")
    old = target.read_bytes()
    messages = [message(HUMAN, ROOT, "human", "First question"), message(ANSWER, HUMAN, "assistant", "Old branch"),
                message(REGEN, HUMAN, "assistant", "Regenerated")]
    capture(raw, current=False, when=1795000001000, hub=False, messages=messages, tip=REGEN)
    result = backup(cli, raw, output, "--verbose")
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["source"] == "history"
    assert "Regenerated" in target.read_text()
    assert "Old branch" not in target.read_text()
    revision, = (output / ".revisions").rglob("*.md")
    assert revision.read_bytes() == old
    assert backup(cli, raw, output).exit_code == 0
    history, = (raw / ORG / "versions" / CID).glob("*.json")
    latest = target.read_bytes()
    history.write_text("{}")
    result = backup(cli, raw, output)
    assert result.exit_code == 0, result.output
    assert "Snapshot hash does not match" in result.stderr
    assert target.read_bytes() == latest


def test_catalog_titles_update_warm_backups_without_replacing_transcripts(cli, tmp_path):
    raw, output = tmp_path / "raw", tmp_path / "out"
    capture(raw)
    capture(raw, org=OTHER, hub=False)
    assert backup(cli, raw, output).exit_code == 0
    assert backup(cli, raw, output).exit_code == 0  # Warm per-chat cache.
    target = output / f"{CID} [{ORG}].md"
    other = output / f"{CID} [{OTHER}].md"
    original = target.read_bytes() + b"\nLocal notes\n"
    target.write_bytes(original)
    catalog = raw / ORG / "catalog.json"
    catalog.write_text(json.dumps({CID: dict(updateTime=1795000000000, title="  T3 Code\nuse cases  ")}))
    (raw / OTHER / "catalog.json").write_text(json.dumps({
        CID: dict(updateTime=1794999999000, title="Stale title"),
    }))
    before = other.read_bytes()
    dry_run = backup(cli, raw, output, "--dry-run")
    assert dry_run.exit_code == 0, dry_run.output
    assert json.loads(dry_run.stdout)["title"] == "T3 Code use cases"
    assert target.read_bytes() == original
    assert backup(cli, raw, output).exit_code == 0
    assert target.read_bytes() == b"# T3 Code use cases\n" + original.split(b"\n", 1)[1]
    assert other.read_bytes() == before
    revision, = (output / ".revisions").rglob("*.md")
    assert revision.read_bytes() == original
    assert backup(cli, raw, output).exit_code == 0
    renamed = target.read_bytes()
    catalog.write_text(json.dumps({CID: dict(updateTime=1795000001000, title="Renamed in Claude")}))
    assert backup(cli, raw, output).exit_code == 0
    assert target.read_bytes() == b"# Renamed in Claude\n" + renamed.split(b"\n", 1)[1]
    fresh = tmp_path / "fresh"
    assert backup(cli, raw, fresh).exit_code == 0
    assert (fresh / target.name).read_text().startswith("# Renamed in Claude\n")


@pytest.mark.parametrize("issue", ["partial", "unfinished", "dangling", "ambiguous", "truncated", "empty"])
def test_incomplete_newer_snapshot_preserves_published_markdown(cli, tmp_path, issue):
    raw, output = tmp_path / "raw", tmp_path / "out"
    capture(raw)
    assert backup(cli, raw, output).exit_code == 0
    target, = output.glob("*.md")
    before = target.read_bytes()
    messages = [message(HUMAN, ROOT, "human", "The prompt"), message(ANSWER, HUMAN, "assistant", "New text")]
    if issue == "unfinished":
        messages[-1]["content"][0]["stopped"] = False
    if issue == "dangling":
        messages[0]["parent_message_uuid"] = REGEN
    if issue == "ambiguous":
        messages.append(message(REGEN, HUMAN, "assistant", "Other"))
    if issue == "truncated":
        messages[-1]["truncated"] = True
    if issue == "empty":
        messages[-1]["content"] = []
    capture(raw, messages=messages, when=1795000001000, mode="tail" if issue == "partial" else "full")
    result = backup(cli, raw, output, "--verbose")
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["status"] == "deferred"
    assert target.read_bytes() == before


def test_hash_mismatch_is_actionable_and_recovers_from_immutable_version(cli, tmp_path):
    raw, output = tmp_path / "raw", tmp_path / "out"
    current = capture(raw)
    current.write_text("{}")
    result = backup(cli, raw, output)
    assert result.exit_code == 1
    assert "hash" in result.stderr
    assert not list(output.glob("*.md"))
    capture(raw, current=False)
    result = backup(cli, raw, output)
    assert result.exit_code == 0, result.output
    assert "hash" in result.stderr
    assert len(list(output.glob("*.md"))) == 1


def test_organizations_are_independent_and_equal_version_conflicts_stay_deferred(cli, tmp_path):
    raw, output = tmp_path / "raw", tmp_path / "out"
    capture(raw, text="First workspace")
    capture(raw, org=OTHER, text="Other workspace", current=False)
    capture(raw, org=OTHER, text="Conflicts", current=False)
    result = backup(cli, raw, output, "--verbose")
    assert result.exit_code == 0, result.output
    assert {json.loads(s)["status"] for s in result.stdout.splitlines()} == {"done", "deferred"}
    target, = output.glob("*.md")
    assert "First workspace" in target.read_text()


def test_existing_export_protects_newer_or_unversioned_transcript(cli, tmp_path):
    raw, output = tmp_path / "raw", tmp_path / "out"
    capture(raw)
    output.mkdir()
    target = output / "Imported title.md"
    for timestamp in ("2030-01-01T00:00:00Z", "unknown"):
        old = f"# Imported title\n\n- Link: https://claude.ai/chat/{CID}\n- Updated: {timestamp}\n\n## Assistant\n\nExport\n"
        target.write_text(old)
        result = backup(cli, raw, output, "--verbose")
        assert result.exit_code == 0, result.output
        assert target.read_text() == old
        assert list(output.glob("*.md")) == [target]
    target.write_text(old.replace("unknown", "2020-01-01T00:00:00Z"))
    assert backup(cli, raw, output).exit_code == 0
    assert target.read_text().startswith("# Imported title\n")
    assert "First answer" in target.read_text()


def test_prompt_dry_run_validates_attachments_and_reads_stdin(cli, tmp_path):
    attachment = tmp_path / "report.txt"
    result = CliRunner().invoke(cli["app"], ["--dry-run", "--file", str(attachment)], input="prompt")
    assert result.exit_code != 0
    attachment.write_text("notes")
    result = CliRunner().invoke(cli["app"], ["--dry-run", "--file", str(attachment)], input="from stdin")
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["prompt"] == "from stdin"


def test_text_logs_match_chatcli_and_show_one_id(cli, tmp_path):
    raw, output = tmp_path / "raw", tmp_path / "out"
    args = ["--raw-dir", str(raw), "--markdown-dir", str(output), "--verbose"]
    runner = CliRunner()
    capture(raw)
    result = runner.invoke(cli["backup_app"], args + ["--dry-run"])
    assert result.stdout.split("\t") == ["🟢 would-create", CID, "2026-11-18T11:06:40Z", "The prompt\n"]
    preview = runner.invoke(cli["backup_app"], args[:-1] + ["--dry-run"])
    assert preview.stdout == f"{CID}\twould-create\tThe prompt\n"
    capture(raw, coverage="partial")
    result = runner.invoke(cli["backup_app"], args)
    assert result.stdout.startswith(f"🟡 part   \t{CID}\t")
    assert not result.stderr
    current = capture(raw)
    current.write_text("{}")
    result = runner.invoke(cli["backup_app"], args)
    assert result.stdout.startswith(f"🔴 check  \t{CID}\t")
    assert result.stderr.startswith(f"error[claudecli-backup]: {CID} ")
    assert ORG not in result.output


def test_export_shapes_render_legacy_text_and_typed_parts(cli, tmp_path):
    raw, output = tmp_path / "raw", tmp_path / "out"
    user = message(HUMAN, ROOT, "human", "")
    user.update(text="Legacy prompt", content=[], attachments=[
        {"file_name": "", "file_type": "txt", "extracted_content": "Extracted document"},
    ])
    reply = message(ANSWER, HUMAN, "assistant", "")
    reply["content"] = [
        {"type": "thinking", "summaries": [{"summary": "Approach"}]},
        {"type": "tool_use", "id": "tool-1", "name": "artifacts",
         "input": {"title": "Demo", "language": "python", "content": "print('example')"}},
        {"type": "tool_result", "tool_use_id": "tool-1", "content": [
            {"type": "text", "text": "A result with ```"},
            {"type": "image", "file_uuid": "image-ref"},
        ]},
        {"type": "text", "text": "Answer with citation",
         "citations": [{"details": {"type": "web", "url": "https://example.org/source"}}]},
        {"type": "document", "title": "Referenced document", "file_uuid": "ref"},
        {"type": "token_budget", "remaining": 123},
        {"type": "injected_prompt_block", "prompt": "Additional context"},
    ]
    capture(raw, hub=False, messages=[user, reply])
    assert backup(cli, raw, output).exit_code == 0
    target, = output.glob("*.md")
    text = target.read_text()
    for fragment in ("Legacy prompt", "Extracted document", "<summary>Approach</summary>", "print('example')",
                     "A result with ```", "image-ref", "Answer with citation", "https://example.org/source",
                     "Referenced document", "123", "Additional context"):
        assert fragment in text
    assert text.count("Called tool:") == 1


def test_text_only_reply_and_existing_frontmatter_export(cli, tmp_path):
    raw, output = tmp_path / "raw", tmp_path / "out"
    reply = dict(uuid=ANSWER, parent_message_uuid=HUMAN, sender="assistant", text="Old-format reply")
    capture(raw, hub=False, messages=[message(HUMAN, ROOT, "human", "Prompt"), reply])
    output.mkdir()
    existing = output / "Official.md"
    existing.write_text(f'---\ntitle: "Official"\ndate: 2030-01-01T00:00:00Z\nsource: "https://claude.ai/chat/{CID}"\n---\n')
    assert backup(cli, raw, output).exit_code == 0
    assert list(output.glob("*.md")) == [existing]
    existing.write_text(existing.read_text().replace("2030", "2020"))
    assert backup(cli, raw, output).exit_code == 0
    assert "Old-format reply" in existing.read_text()


def test_refresh_original_render_but_protect_local_edits(cli, tmp_path):
    raw, output = tmp_path / "raw", tmp_path / "out"
    now = 1795000000000
    reply = message(ANSWER, HUMAN, "assistant", "Answer")
    reply["content"].append({"type": "tool_use", "name": "Lookup", "input": {"q": "example"}})
    current = capture(raw, messages=[message(HUMAN, ROOT, "human", "Prompt"), reply], when=now)
    hash = hashlib.sha256(current.read_bytes()).hexdigest()
    output.mkdir()
    target = output / "Original.md"
    header = (f"# My title\n\n- Link: https://claude.ai/chat/{CID}\n- Organization: {ORG}\n"
              f"- Updated: {cli['stamp'](now)}\n- Capture SHA-256: {hash}\n\n")
    body = "## User\n\nPrompt\n\n## Assistant\n\nAnswer\n\nTools: Lookup\n"
    target.write_text(header + body + "Manual edit\n")
    assert backup(cli, raw, output).exit_code == 0
    assert target.read_text().endswith("Manual edit\n")
    target.write_text(header + body)
    assert backup(cli, raw, output).exit_code == 0
    assert target.read_text().startswith("# My title\n")
    assert "<summary>Called tool: Lookup</summary>" in target.read_text()
    revision, = (output / ".revisions").rglob("*.md")
    assert revision.read_text() == header + body
