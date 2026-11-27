"""Offline tests of memory change detection and evidence validation."""
import json
import sqlite3
from pathlib import Path

from typer.testing import CliRunner
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import memory

runner = CliRunner()


def test_incremental(tmp_path, monkeypatch):
    monkeypatch.setattr(memory.platform, "node", lambda: "graphene")
    index, state = tmp_path / "index.sqlite", tmp_path / "state.sqlite"
    db = sqlite3.connect(index)
    db.executescript("""
      CREATE TABLE items(source,native_id,account,timestamp,title,body,summary,locator,role,author);
      CREATE TABLE source_status(source,row_count,latest_item_time,warning);
      INSERT INTO source_status VALUES ('chatgpt', 3, '2026-11-21', '');
      INSERT INTO items VALUES ('chatgpt','a','','2026-11-15T00:00:00Z','A','I prefer tea.','','a.md#L1','user','');
      INSERT INTO items VALUES ('chatgpt','old','','2026-11-01','Old','Old text','','old.md#L1','user','');
      INSERT INTO items VALUES ('chatgpt','later','','2026-11-22','Later','Future text','','later.md#L1','user','');
    """)
    db.commit()

    def run(*args, ok=True):
        result = runner.invoke(memory.app, ["--index", str(index), "--state", str(state), *args])
        assert (result.exit_code == 0) == ok, result.output
        return result.stdout

    def prepare(*args):
        return [json.loads(line) for line in run("prepare", *args).splitlines()]

    assert len(prepare("--since", "2026-11-15", "--until", "2026-11-22", "--dry-run")) == 1
    assert not state.exists()
    a, = prepare("--since", "2026-11-15", "--until", "2026-11-22")
    assert prepare() == [a]  # pending until reviewed
    assert prepare("--week", "2026-11-15") == [a]
    assert prepare("--week", "2026-11-08") == []
    run("prepare", "--week", "2026-11-16", ok=False)
    run("prepare", "--week", "2026-11-15", "--weekly", ok=False)
    proposal = tmp_path / "review.jsonl"
    def write(quote):
        proposal.write_text(json.dumps({"id": a["id"], "hash": a["hash"], "claims": [
            {"kind":"preference","scope":"personal","claim":"Prefers tea","quote":quote,"authority":"user_explicit"}
        ]}) + "\n")
    write("I prefer coffee.")
    run("review", str(proposal), "--apply", ok=False)
    assert prepare() == [a]
    write("I prefer tea.")
    run("review", str(proposal))
    assert prepare() == [a]
    run("review", str(proposal), "--apply")
    assert prepare() == []
    assert "Prefers tea" in run("build")
    claim = json.loads(run("build", "--format", "jsonl"))
    routes = tmp_path / "routes.jsonl"
    target = tmp_path / "canonical.md"
    target.write_text("Existing preference note")
    route = {"claim_id": claim["claim_id"], "action": "update",
             "target": str(target), "reason": "Candidate evidence"}
    routes.write_text(json.dumps(route) + "\n")
    assert "1 routed claims, 1 groups, 0 unrouted" in run("plan", str(routes))
    assert run("build", "--format", "jsonl", "--unrouted", str(routes)) == ""
    assert target.read_text() == "Existing preference note"
    routes.write_text(json.dumps(route) + "\n" + json.dumps(route) + "\n")
    run("plan", str(routes), ok=False)
    routes.write_text(json.dumps(route) + "\n")
    db.execute("UPDATE items SET body='I prefer coffee.' WHERE native_id='a'")
    db.execute("INSERT INTO items VALUES ('chatgpt','backfill','','2026-11-05','Old','Late arrival','','late.md','user','')")
    db.commit()
    assert "Prefers tea" not in run("build")  # stale even before prepare
    run("plan", str(routes), ok=False)  # stale route cannot be used
    run("review", str(proposal), "--apply", ok=False)
    pending = prepare()
    assert {r["native_id"] for r in pending} == {"a", "backfill"}
    assert "Prefers tea" not in run("build")
    db.execute("DELETE FROM items WHERE native_id='a'")
    db.commit()
    assert len(prepare()) == 1
    assert json.loads(run("status"))["missing"] == 1
    db.execute("INSERT INTO items VALUES ('chatgpt','a','','2026-11-15T00:00:00Z','A','I prefer tea.','','a.md#L99','user','')")
    db.commit()
    assert len(prepare()) == 1  # identical evidence reuses review; locator can move
    assert "a.md#L99" in run("build")


def test_sgt_date():
    assert memory.day("2026-11-14T16:00:00+00:00") == "2026-11-15"
    assert memory.day("2026-11-15") == "2026-11-15"
    assert memory.day("") == ""


def test_structural_exclusions_and_legacy_preview():
    row = dict(source="chatgpt", author="", title="x", body="> I prefer tea.\n>\n> Not coffee.", summary="")
    assert not memory.exclusion(row)
    assert "I prefer tea." in memory.preview(row)
    assert memory.exclusion(row | {"body": "> audio_transcription\n>"}) == "media_placeholder"
    mail = row | {"source": "mail", "author": "TDS Trading Games <anand@study.iitm.ac.in>",
                  "title": "1 thing is waiting for you in TDS trading games", "body": "Notice"}
    assert memory.exclusion(mail) == "automated_tds_notification"
    assert not memory.exclusion(mail | {"author": "Other sender"})
    assert memory.exclusion(row | {"source": "whatsapp", "author": "Another person"}) == "whatsapp_attribution_unverified"
    assert not memory.exclusion(row | {"source": "whatsapp", "author": "me"})


def test_preview_removes_structured_injection_not_user_json():
    fence = chr(96) * 3
    row = dict(source="claude", author="", title="x", summary="", body="My message.\n    " + fence +
               'json\n    {"type":"injected_prompt_block","start_timestamp":null,"stop_timestamp":null,"prompt":"injected"}\n    ' +
               fence + "\n" + fence + 'json\n{"type":"example","value":1}\n' + fence)
    text = memory.preview(row)
    assert "My message." in text and "injected" not in text and '"type":"example"' in text


def test_plutonium_read_only(tmp_path, monkeypatch):
    import pytest
    monkeypatch.setattr(memory.platform, "node", lambda: "Plutonium")
    state = tmp_path / "state.sqlite"
    with pytest.raises(memory.typer.BadParameter, match="Graphene"):
        memory.open_state(state)
    with memory.open_state(state, True) as db:
        assert db.execute("SELECT count(*) FROM seen").fetchone()[0] == 0
    assert not state.exists()


def test_completed_week():
    import datetime as dt
    for date in ("2026-11-22", "2026-11-26", "2026-11-28"):
        assert memory.completed_week(dt.date.fromisoformat(date)) == ("2026-11-15", "2026-11-22")
    assert memory.completed_week(dt.date(2026, 11, 29)) == ("2026-11-22", "2026-11-29")
