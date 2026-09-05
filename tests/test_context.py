from __future__ import annotations

import importlib.util
import json
import sqlite3
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "context.py"
spec = importlib.util.spec_from_file_location("context", SCRIPT)
context = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(context)


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def jsonl(path: Path, rows: list[dict]) -> Path:
    return write(path, "".join(json.dumps(row) + "\n" for row in rows))


def make_mail_index(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE sources (
          id INTEGER PRIMARY KEY, path TEXT, size INTEGER, fingerprint TEXT,
          next_offset INTEGER, message_count INTEGER, partial_bodies INTEGER, status TEXT
        );
        CREATE TABLE messages (
          id INTEGER PRIMARY KEY, source_id INTEGER, byte_offset INTEGER, byte_length INTEGER,
          date_utc TEXT, sender TEXT, recipients TEXT, subject TEXT, labels TEXT,
          message_id TEXT, in_reply_to TEXT
        );
        CREATE VIRTUAL TABLE search USING fts5(
          subject, sender, recipients, labels, body, content='', detail=column
        );
        INSERT INTO sources VALUES(1, '/archive/old.mbox', 1000, 'x', 1000, 1, 0, 'complete');
        INSERT INTO messages VALUES(
          1, 1, 120, 80, '2024-03-02T10:00:00+00:00', 'Ada <ada@example.com>',
          'Anand <me@example.com>', 'Historical launch', '', '<old-1@example.com>', ''
        );
        INSERT INTO search(rowid, subject, sender, recipients, labels, body) VALUES(
          1, 'Historical launch', 'Ada <ada@example.com>', 'Anand <me@example.com>', '',
          'The cobalt archive launched successfully'
        );
        """
    )
    connection.commit()
    connection.close()


@pytest.fixture
def corpus(tmp_path: Path):
    home = tmp_path / "home"
    transcript = write(
        home / "Dropbox/notes/transcripts/2026-08-01 Alice Project.md",
        """---
summary:
- Alice and Anand reviewed the Cobalt launch.
people: [Alice Example, Anand]
keywords: [cobalt, launch]
actions:
- 'Anand: Send Alice the launch memo by 2026-08-05'
- 'Anand: Send Alice the launch memo by 2026-08-05'
---
# Alice Project

## Transcript

**Alice**: Cobalt should launch next week.
""",
    )
    write(home / "Dropbox/notes/transcripts/not-a-date.md", "# Must not be indexed\n")
    write(home / "Dropbox/notes/transcripts/2026-08-02-Bob Project.md", "# Bob Project\n")
    about = home / "Dropbox/notes/about"
    write(
        about / "Alice Example Organization.md",
        f"""# Alice Example Organization

- Email: alice@example.com
- Chat ID: users/123
- WhatsApp ID: 15550001@lid
- Alias: Alice
- Evidence: [{transcript.name}](../transcripts/{transcript.name})
- Repeated: ~/Dropbox/notes/transcripts/{transcript.name}
- Source: ~/mail/unrelated.source@example.com/message.md

Quoted note about unrelated@example.com, users/999, and 999999@g.us.
""",
    )
    write(about / "Alice Other.md", "# Alice Other\n\n- Alias: Alice\n")
    write(about / "Casey Person Organization A.md", "# Casey Person Organization A\n")
    write(about / "Casey Person Organization B.md", "# Casey Person Organization B\n")

    account = home / "Documents/data/me@example.com"
    jsonl(
        account / "mail.jsonl",
        [
            {
                "time": "2026-08-03T10:00:00+00:00",
                "from": "Anand <me@example.com>",
                "to": "Alice Example",
                "subject": "Project Update",
                "body": "I wrote the cobalt launch memo in my concise style.",
                "snippet": "launch memo",
                "id": "gmail-1",
                "thread_id": "gmail-thread-a",
            },
            {
                "time": "2026-08-04T10:00:00+00:00",
                "from": "Bob <bob@example.com>",
                "to": "Casey Person",
                "subject": "Re: Project Update",
                "body": "A different discussion with the same normalized subject.",
                "id": "gmail-2",
                "thread_id": "gmail-thread-b",
            },
        ],
    )
    jsonl(
        account / "calendar.jsonl",
        [
            {
                "time": "2026-08-05T09:00:00+08:00",
                "title": "Cobalt review",
                "body": "Review the launch",
                "id": "event-instance",
                "recurring_event_id": "event-series",
                "original_start_time": "2026-08-05T09:00:00+08:00",
                "status": "confirmed",
                "attendees": ["me@example.com", "Alice Example"],
                "attendee_status": {"me@example.com": "accepted", "alice@example.com": "tentative"},
            }
        ],
    )
    jsonl(
        account / "chat.jsonl",
        [
            {
                "time": "2026-08-06T10:00:00Z",
                "sender_name": "Alice Example",
                "sender_id": "users/999",
                "space_name": "Cobalt Room",
                "space_id": "spaces/AAA",
                "thread_id": "spaces/AAA/threads/ONE",
                "id": "spaces/AAA/messages/1",
                "body": "Cobalt launch checklist",
            },
            {
                "time": "2026-08-06T11:00:00Z",
                "sender_name": "Bob",
                "sender_id": "users/456",
                "space_name": "Cobalt Room",
                "space_id": "spaces/AAA",
                "thread_id": "spaces/AAA/threads/TWO",
                "id": "spaces/AAA/messages/2",
                "body": "Other cobalt thread",
            },
        ],
    )
    jsonl(
        home / "Documents/data/whatsapp/Family [family@g.us].jsonl",
        [
            {
                "messageId": "wa-1",
                "conversationId": "family@g.us",
                "conversationTitle": "Family",
                "userId": "15550002@lid",
                "authorPhone": "+1 555 0001",
                "author": "Alice Example",
                "time": "2026-08-07T10:00:00Z",
                "text": "Cobalt family update",
            }
        ],
    )
    write(
        home / "Documents/chatgpt/chat-123.md",
        """# Cobalt writing

- Created: Aug 2, 2026, 9:00 AM
- Link: https://chatgpt.com/c/chat-123

## User

> My unmistakable authored phrase about cobalt.

## Assistant

Assistant-only polished cobalt prose.
""",
    )
    write(
        home / "Documents/claude/claude-123.md",
        """# Claude note

- Created: Aug 3, 2026, 9:00 AM
- Link: https://claude.ai/chat/claude-123

## human

Human-authored cobalt note.

## assistant

Assistant-only cobalt answer.
""",
    )
    jsonl(
        account / "drive.jsonl",
        [{"id": "drive-1", "name": "Cobalt plan", "modifiedTime": "2026-08-08T10:00:00Z", "webViewLink": "https://drive/drive-1", "mimeType": "text/plain"}],
    )

    write(home / "code/README.md", "# Code\n\n- [Cobalt tool](cobalt/): Useful tool.\n")
    write(home / "code/talks/README.md", "# Talks\n\n- 01 Aug 2026. **[Cobalt Talk](cobalt-talk/)** — A talk.\n")
    write(home / "code/llmevals/README.md", "# Evals\n\n- [Cobalt Eval](cobalt/): An eval.\n")
    write(home / "code/blog/description.md", "pages/cobalt.md:description: Cobalt essay\npages/cobalt.md:tags: [launch]\n")
    write(home / "code/til/README.md", "# TIL\n\n- `cobalt.md`: Cobalt notes\n")
    write(home / "code/datastories/config.json", json.dumps({"stories": [{"id": "story-a", "title": "Cobalt Story"}, {"id": "story-b", "title": "Other Story"}]}))
    write(home / "code/llmdemos/config.json", json.dumps({"demos": [{"id": "demo-a", "title": "Cobalt Demo"}, {"id": "demo-b", "title": "Other Demo"}]}))
    mail_index = home / "Documents/Mail/mail-index.sqlite"
    make_mail_index(mail_index)

    config = context.SourceConfig.for_home(home)
    db = home / "Documents/data/context/context.sqlite"
    log = home / ".cache/sanand-scripts/context/queries.jsonl"
    context.rebuild_database(db, config)
    return home, config, db, log


def rows(db: Path, sql: str, params=()):
    connection = sqlite3.connect(db)
    connection.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in connection.execute(sql, params)]
    finally:
        connection.close()


def test_atomic_rebuild_failure_leaves_live_database_untouched(corpus, monkeypatch) -> None:
    _, config, db, _ = corpus
    before = db.read_bytes()
    monkeypatch.setattr(context, "index_sources", lambda *_: (_ for _ in ()).throw(RuntimeError("boom")))

    with pytest.raises(RuntimeError, match="boom"):
        context.rebuild_database(db, config)

    assert db.read_bytes() == before
    assert not db.with_suffix(db.suffix + ".tmp").exists()


def test_rebuild_is_deterministic_and_fts_matches(corpus) -> None:
    _, config, db, _ = corpus
    first = rows(db, "SELECT source,native_id,timestamp,title,thread_id,conversation_id,role,extra FROM items ORDER BY id")
    context.rebuild_database(db, config)
    second = rows(db, "SELECT source,native_id,timestamp,title,thread_id,conversation_id,role,extra FROM items ORDER BY id")

    assert first == second
    assert rows(db, "SELECT count(*) n FROM items")[0]["n"] == rows(db, "SELECT count(*) n FROM item_fts")[0]["n"]
    assert rows(db, "PRAGMA integrity_check")[0]["integrity_check"] == "ok"
    assert rows(db, "SELECT count(*) n FROM items WHERE native_id='not-a-date.md'")[0]["n"] == 0
    assert rows(db, "SELECT count(*) n FROM items WHERE native_id='2026-08-02-Bob Project.md'")[0]["n"] == 1


def test_native_ids_metadata_actions_people_and_unique_edges(corpus) -> None:
    _, _, db, _ = corpus
    mail = rows(db, "SELECT native_id,thread_id FROM items WHERE source='mail' ORDER BY native_id")
    assert mail == [{"native_id": "gmail-1", "thread_id": "gmail-thread-a"}, {"native_id": "gmail-2", "thread_id": "gmail-thread-b"}]
    chat = rows(db, "SELECT thread_id,conversation_id,extra FROM items WHERE source='gchat' ORDER BY native_id")[0]
    assert chat["thread_id"] == "spaces/AAA/threads/ONE"
    assert chat["conversation_id"] == "spaces/AAA"
    assert json.loads(chat["extra"])["sender_id"] == "users/999"
    calendar = json.loads(rows(db, "SELECT extra FROM items WHERE source='calendar'")[0]["extra"])
    assert calendar["recurring_event_id"] == "event-series"
    assert calendar["status"] == "confirmed"
    assert calendar["attendee_status"]["alice@example.com"] == "tentative"
    wa = rows(db, "SELECT native_id,conversation_id,author,extra FROM items WHERE source='whatsapp'")[0]
    assert (wa["native_id"], wa["conversation_id"], wa["author"]) == ("wa-1", "family@g.us", "Alice Example")
    assert json.loads(wa["extra"])["userId"] == "15550002@lid"
    assert rows(db, "SELECT count(*) n FROM actions")[0]["n"] == 2
    assert rows(db, "SELECT count(DISTINCT fingerprint) n FROM actions")[0]["n"] == 1
    assert rows(db, "SELECT count(*) n FROM item_entities WHERE role='evidence'")[0]["n"] == 1


def test_search_filters_threads_and_provenance(corpus) -> None:
    _, config, db, log = corpus
    hits = context.search_database(db, "Project Update", sources=["mail"], since="2026-08-04", until="2026-08-05", config=config, log_path=log)
    assert [hit["native_id"] for hit in hits] == ["gmail-2"]
    assert context.thread_results(db, "gmail-thread-a")[0]["native_id"] == "gmail-1"
    assert [hit["native_id"] for hit in context.thread_results(db, "spaces/AAA/threads/ONE")] == ["spaces/AAA/messages/1"]
    required = {"source", "timestamp", "title", "author", "role", "native_id", "thread_id", "conversation_id", "locator", "snippet", "score", "why"}
    assert all(required <= hit.keys() and hit["locator"] and hit["why"] for hit in hits)


def test_entities_ambiguity_about_links_and_open_loops(corpus) -> None:
    _, _, db, _ = corpus
    ambiguity = context.entity_results(db, "Alice")
    assert ambiguity == [{"ambiguity": "Alice", "matches": ["Alice Example Organization", "Alice Other"]}]
    entity = context.entity_results(db, "Alice Example")
    assert len(entity) == 1
    assert {item["source"] for item in entity[0]["items"]} >= {"about", "transcript", "mail", "calendar", "gchat", "whatsapp"}
    assert context.entity_results(db, "Alice Ex")[0]["canonical_name"] == "Alice Example Organization"
    assert context.entity_results(db, "Alice O")[0]["canonical_name"] == "Alice Other"
    loops = context.open_loop_results(db, "Alice Example")
    assert len(loops) == 1
    assert len(loops[0]["occurrences"]) == 2
    assert loops[0]["completion_evidence"] is None
    assert {item["source"] for item in loops[0]["later_evidence"]} >= {"mail", "calendar", "gchat", "whatsapp"}
    identities = context.status_database(db, context.SourceConfig.for_home(corpus[0]), identities=True)
    assert any(item["alias"] == "alice" for item in identities["identities"]["ambiguous_aliases"])


def test_unique_shortened_name_links_cross_source_evidence(corpus) -> None:
    _, _, db, _ = corpus
    entity_id = rows(db, "SELECT entity_id FROM entities WHERE canonical_name=?", ("Alice Example Organization",))[0]["entity_id"]
    linked = rows(
        db,
        """SELECT i.source,ie.role FROM item_entities ie JOIN items i ON i.id=ie.item_id
           WHERE ie.entity_id=?""",
        (entity_id,),
    )
    assert {(item["source"], item["role"]) for item in linked} >= {
        ("mail", "recipient"), ("calendar", "attendee"), ("gchat", "sender"), ("whatsapp", "sender"),
    }


def test_ambiguous_shortened_name_does_not_link(corpus) -> None:
    _, _, db, _ = corpus
    ambiguity = context.entity_results(db, "Casey Person")
    assert ambiguity == [{
        "ambiguity": "Casey Person",
        "matches": ["Casey Person Organization A", "Casey Person Organization B"],
    }]
    assert not rows(
        db,
        """SELECT ie.entity_id FROM item_entities ie JOIN items i ON i.id=ie.item_id
           WHERE i.native_id='gmail-2' AND ie.role='recipient'""",
    )


def test_generic_search_boosts_unique_shortened_entity(corpus) -> None:
    _, config, db, log = corpus
    hits = context.search_database(db, "Alice Example cobalt", config=config, log_path=log)
    assert any("entity" in hit["why"] for hit in hits)


def test_only_explicit_identity_metadata_becomes_aliases(corpus) -> None:
    _, _, db, _ = corpus
    aliases = {row["alias"] for row in rows(db, "SELECT alias FROM aliases")}
    assert {"alice@example.com", "users/123", "15550001@lid"} <= aliases
    assert not {"unrelated.source@example.com", "unrelated@example.com", "users/999", "999999@g.us"} & aliases


def test_chat_roles_style_and_assets(corpus) -> None:
    _, config, db, log = corpus
    roles = rows(db, "SELECT source,role,count(*) n FROM items WHERE source IN ('chatgpt','claude') GROUP BY source,role ORDER BY source,role")
    assert roles == [
        {"source": "chatgpt", "role": "assistant", "n": 1},
        {"source": "chatgpt", "role": "user", "n": 1},
        {"source": "claude", "role": "assistant", "n": 1},
        {"source": "claude", "role": "user", "n": 1},
    ]
    style = context.style_results(db, "cobalt", config=config, log_path=log)
    assert style
    assert all(hit["role"] != "assistant" for hit in style)
    assert {hit["source"] for hit in style} >= {"chatgpt", "claude", "mail"}
    assert rows(db, "SELECT count(*) n FROM items WHERE source='asset_registry' AND locator LIKE '%config.json%'")[0]["n"] == 4
    assert context.assets_results(db, "Cobalt Story", config=config, log_path=log)[0]["native_id"].endswith("#story-a")


def test_routing_reasons_recency_and_as_of(corpus) -> None:
    _, config, db, log = corpus
    subject = context.search_database(db, "Subject: Project Update", config=config, log_path=log)
    sender = context.search_database(db, "From: Bob", config=config, log_path=log)
    entity = context.search_database(db, "Alice Example cobalt", config=config, log_path=log)
    action = context.search_database(db, "What should I follow up with Alice Example about?", config=config, log_path=log)
    open_loop = context.search_database(db, "Show open loops for Alice Example", config=config, log_path=log)
    generic_action = context.search_database(db, "Cobalt action", config=config, log_path=log)
    recent = context.search_database(db, "recent cobalt", as_of="2026-08-09", config=config, log_path=log)
    old_as_of = context.search_database(db, "recent cobalt", as_of="2026-08-03", config=config, log_path=log)

    assert "subject" in subject[0]["why"]
    assert "sender" in sender[0]["why"]
    assert any("entity" in hit["why"] and "about-link" in hit["why"] for hit in entity)
    assert action[0]["source"] == "transcript" and "action" in action[0]["why"]
    assert any("action" in hit["why"] for hit in open_loop)
    assert all("action" not in hit["why"] for hit in generic_action)
    assert any("recent" in hit["why"] for hit in recent)
    assert [hit["native_id"] for hit in recent] != [hit["native_id"] for hit in old_as_of]


@pytest.mark.parametrize(
    "phrase",
    [
        "action item", "action items", "next step", "next steps", "prepare for meeting",
        "prepare for the meeting", "prepare me for meeting", "prepare me for the meeting",
    ],
)
def test_action_intent_variants_route_actions(corpus, phrase) -> None:
    _, config, db, log = corpus
    hits = context.search_database(db, f"{phrase} Alice Example", config=config, log_path=log)
    assert any("action" in hit["why"] for hit in hits)


@pytest.mark.parametrize("phrase", ["action", "what happened"])
def test_non_action_intent_phrases_do_not_route_actions(corpus, phrase) -> None:
    _, config, db, log = corpus
    hits = context.search_database(db, f"{phrase} Alice Example", config=config, log_path=log)
    assert all("action" not in hit["why"] for hit in hits)


def test_guardrail_boilerplate_cannot_trigger_routing_modes(corpus) -> None:
    _, config, db, log = corpus
    hits = context.search_database(
        db,
        "Cobalt\n\nGuardrails:\nPrepare for a recent follow-up with Alice Example about the last meeting.",
        config=config,
        log_path=log,
    )
    assert hits
    assert all(not {"entity", "action", "recent"} & set(hit["why"]) for hit in hits)


def test_historical_mail_federation_has_no_invented_thread(corpus) -> None:
    _, config, db, log = corpus
    hits = context.search_database(db, "cobalt archive", since="2024-01-01", until="2025-01-01", config=config, log_path=log)
    hit = next(item for item in hits if item["source"] == "historical_mail")
    assert hit["native_id"] == "<old-1@example.com>"
    assert hit["thread_id"] == ""
    assert hit["locator"] == "/archive/old.mbox#byte=120,80"


@pytest.mark.parametrize("sources", [["mail"], ["historical_mail"]])
def test_historical_mail_is_part_of_logical_mail_source(corpus, sources) -> None:
    _, config, db, log = corpus
    hits = context.search_database(
        db, "cobalt archive", sources=sources, since="2024-01-01", until="2025-01-01",
        config=config, log_path=log,
    )
    assert [hit["source"] for hit in hits] == ["historical_mail"]


def test_realistic_long_prompt_search_is_fast_and_ignores_boilerplate(corpus) -> None:
    _, config, db, log = corpus
    connection = sqlite3.connect(db)
    template = (
        "INSERT INTO items(source,native_id,timestamp,title,body,summary,locator) "
        "VALUES('mail',?,?,?,?,?,?)"
    )
    connection.executemany(
        template,
        [
            (f"bulk-{index}", "2025-01-01", f"Routine newsletter {index}",
             "generic planning update and operational status", "weekly digest", f"fixture://bulk/{index}")
            for index in range(3000)
        ],
    )
    connection.execute("INSERT INTO item_fts(item_fts) VALUES('rebuild')")
    connection.commit()
    connection.close()
    prompt = """Draft a concise reply to Alice about the Cobalt launch memo.

From: Alice Example <alice@example.com>
Subject: Project Update

Guardrails:
- Use relevant skills and search past conversations extensively.
- Read all instructions, cite sources, and prepare for a recent follow-up with Alice Example.
<skill name="mail">Boilerplate that must not become retrieval terms.</skill>
"""
    context.search_database(db, prompt, config=config, log_path=log)
    timings = []
    results = []
    for _ in range(5):
        started = time.perf_counter()
        results = context.search_database(db, prompt, config=config, log_path=log)
        timings.append(time.perf_counter() - started)
    mail = next(hit for hit in results if hit["native_id"] == "gmail-1")
    assert {"subject", "entity"} <= set(mail["why"])
    assert max(timings) < 0.2


def test_long_research_prompt_matches_shortened_name_quickly(corpus) -> None:
    _, config, db, log = corpus
    prompt = """Prepare a source-grounded research brief on the Cobalt launch for an executive discussion. Search my transcripts, email, calendar, chat, and project notes, and connect evidence across sources rather than relying on a single mention. Focus especially on what Alice Example decided, said, or was asked to do, and identify the launch memo, dates, owners, open questions, risks, follow-up context, and any disagreement. Distinguish direct evidence from summaries, preserve the original source locators, and prefer the newest relevant material when multiple records overlap. Explain the sequence of events, note which claims are supported by more than one source, and call out missing evidence or uncertainty. The result should be concise enough to review quickly but detailed enough to support a research conversation about the Cobalt launch and the decisions around it."""
    assert "Guardrails:" not in prompt

    context.search_database(db, prompt, config=config, log_path=log)
    timings = []
    results = []
    for _ in range(5):
        started = time.perf_counter()
        results = context.search_database(db, prompt, config=config, log_path=log)
        timings.append(time.perf_counter() - started)

    mail = next(hit for hit in results if hit["native_id"] == "gmail-1")
    assert "entity" in mail["why"]
    assert max(timings) < 0.2


def test_status_and_compact_query_log(corpus) -> None:
    home, config, db, log = corpus
    assert config.log_path == home / "Documents/data/context/query-log.jsonl"
    status = context.status_database(db, config)
    assert status["database_bytes"] > 0
    assert status["built_at"]
    assert status["sources"]["mail"]["row_count"] == 2
    assert "latest_item_time" in status["sources"]["mail"]
    assert "source_mtime" in status["sources"]["mail"]
    assert "missing_sources" in status and "stale_sources" in status

    context.search_database(db, "secret body marker", config=config, log_path=log)
    entry = json.loads(log.read_text().splitlines()[-1])
    assert {"timestamp", "mode", "query", "filters", "result_count", "result_sources", "latency_ms"} <= entry.keys()
    assert "body" not in entry and "secret body marker" == entry["query"]
    assert str(home) not in json.dumps(entry)
