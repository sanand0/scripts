"""Recover complete, linked ChatGPT turns from the extension's saved SSE records."""

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
import hashlib
import json
import math
from pathlib import Path
import re

from conversation_backup_cache import file_stamp


ROOT = "client-created-root"
UUID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", re.I)
StartRecord = tuple[dict, float, dict, str | None]


@dataclass(frozen=True)
class Turn:
    parent: str
    messages: list[dict]
    started: float
    finished: float
    title: str = ""


def timestamp(value) -> bool:
    return type(value) in (int, float) and 0 < value < 253402300800 and math.isfinite(value)


def apply_delta(document: dict, operation: str, path: str, value) -> None:
    """Apply the observed Delta v1 operations to a single stream document."""
    if not path.startswith("/"):
        raise ValueError("Expected a JSON pointer")
    parts = [part.replace("~1", "/").replace("~0", "~") for part in path[1:].split("/")]
    node = document
    for part in parts[:-1]:
        node = node[int(part) if isinstance(node, list) else part]
    key = parts[-1]
    if isinstance(node, list):
        key = len(node) if key == "-" else int(key)
        if not 0 <= key <= len(node):
            raise ValueError("Array index out of range")
    if operation == "add":
        if isinstance(node, list):
            node.insert(key, value)
        else:
            node[key] = value
    elif operation == "replace":
        node[key] = value
    elif operation == "remove":
        del node[key]
    elif operation == "append":
        old = node[key]
        if isinstance(old, dict) and isinstance(value, dict):
            old.update(value)
        elif type(old) is type(value) and isinstance(old, (str, list)):
            node[key] = old + value
        else:
            raise ValueError("Unsupported delta append")
    elif operation == "truncate" and type(value) is int and value >= 0 and isinstance(node[key], list):
        del node[key][value:]
    else:
        raise ValueError("Unsupported delta operation")


def stream_turn(request: dict, body: str, started: float, finished: float) -> tuple[str, Turn]:
    """Decode a terminal next-turn response and verify its message ancestry."""
    parent = request["parent_message_id"]
    if request["action"] != "next" or not isinstance(parent, str):
        raise ValueError("Unsupported generation action")
    documents = {}
    channel = pointer = operation = None
    conversation_ids = set()
    messages = {}
    title = ""
    done = complete = False
    # The patch target and omitted fields inherit from the last outer delta.
    for block in body.replace("\r\n", "\n").split("\n\n"):
        lines = block.split("\n")
        event = next((line[6:].strip() for line in lines if line.startswith("event:")), "")
        data = "\n".join(line[5:].removeprefix(" ") for line in lines if line.startswith("data:"))
        if not data:
            continue
        if done:
            raise ValueError("Data after stream terminator")
        if data == "[DONE]":
            done = True
            continue
        if event == "delta_encoding":
            if json.loads(data) != "v1":
                raise ValueError("Unknown delta encoding")
            continue
        payload = json.loads(data)
        if event == "delta":
            operation = payload.get("o", operation)
            pointer = payload.get("p", pointer)
            channel = payload.get("c", channel)
            value = payload["v"]
            if operation == "add" and pointer == "":
                if type(channel) is not int or channel in documents:
                    raise ValueError("Invalid delta document index")
                documents[channel] = value
                payload = value
            elif operation == "patch" and isinstance(value, list):
                for change in value:
                    apply_delta(documents[channel], change["o"], change["p"], change.get("v"))
                continue
            else:
                apply_delta(documents[channel], operation, pointer, value)
                continue
        if cid := payload.get("conversation_id"):
            conversation_ids.add(cid)
        if payload.get("error") or payload.get("type") in {"error", "streaming_parent_patch"}:
            raise ValueError("Unsupported conversation event")
        if payload.get("type") == "input_message":
            msg = payload["input_message"]
            messages[msg["id"]] = msg
        if payload.get("type") == "title_generation" and isinstance(payload.get("title"), str):
            title = payload["title"].strip()
        if payload.get("type") == "message_stream_complete":
            complete = True

    if not (done and complete) or len(conversation_ids) != 1:
        raise ValueError("Missing stream completion or identity")
    cid, = conversation_ids
    requested_id = request.get("conversation_id")
    if not UUID.fullmatch(cid) or requested_id not in (None, cid):
        raise ValueError("Mismatched conversation identity")
    for document in documents.values():
        msg = document["message"]
        if msg["id"] in messages:
            raise ValueError("Duplicate stream message")
        messages[msg["id"]] = msg

    prompt, = request["messages"]
    prompt_id = prompt["id"]
    user = messages[prompt_id]
    if (user["author"]["role"] != "user" or user["status"] != "finished_successfully"
            or not isinstance(user.get("content"), dict) or not timestamp(user.get("create_time"))
            or user.get("metadata", {}).get("parent_id", ROOT) != parent):
        raise ValueError("Unconfirmed streamed prompt")
    leaf, = [msg for msg in messages.values() if msg.get("end_turn") is True
             and msg.get("status") == "finished_successfully" and timestamp(msg.get("create_time"))
             and not msg.get("metadata", {}).get("is_visually_hidden_from_conversation")
             and msg.get("channel") == "final" and has_visible_reply(msg)]
    chain = [leaf]
    while chain[-1]["id"] != prompt_id:
        previous = messages.pop(chain[-1]["metadata"]["parent_id"])
        chain.append(previous)
    if any(msg["id"] != leaf["id"] and not msg.get("metadata", {}).get("is_visually_hidden_from_conversation")
           for msg in messages.values()):
        raise ValueError("Stream contains another visible branch")
    return cid, Turn(parent, list(reversed(chain)), started, finished, title)


def has_visible_reply(message: dict) -> bool:
    content = message["content"]
    parts = content.get("parts", [])
    if message["author"]["role"] == "tool":
        return any(isinstance(part, dict) and part.get("content_type") == "image_asset_pointer" for part in parts)
    return (message["author"]["role"] == "assistant" and message.get("recipient") in (None, "all")
            and content.get("content_type") in {"text", "multimodal_text", "system_error"}
            and any(isinstance(part, dict) or isinstance(part, str) and part.strip() for part in parts))


def read_start(start: Path) -> StartRecord | None:
    try:
        record = json.loads(start.read_bytes())
        if record["method"] == "POST" and record["path"] in {"/backend-api/f/conversation", "/backend-api/conversation"}:
            request = record.get("request") or {}
            known_id = request.get("conversation_id") or record.get("pageConversationId")
            started = record["startedAt"] / 1000
            if timestamp(started):
                return record, started, request, known_id if isinstance(known_id, str) and UUID.fullmatch(known_id) else None
    except (ValueError, TypeError, KeyError, AttributeError):
        pass
    return None


def read_capture(start_record: StartRecord, files: list[Path]) -> tuple[str | None, Turn | None]:
    record, started, request, known_id = start_record
    try:
        fragments = [record, *(json.loads(p.read_bytes()) for p in files[1:])]
        if (not all(r["index"] == i and all(r[k] == record[k] for k in ("captureId", "path", "method", "startedAt"))
                    for i, r in enumerate(fragments))
                or record["kind"] != "start" or fragments[-1]["kind"] != "end"
                or not any(r["kind"] == "headers" and r["status"] == 200
                           and "text/event-stream" in r["contentType"] for r in fragments)):
            raise ValueError("Incomplete stream capture")
        finished = fragments[-1]["finishedAt"] / 1000
        if not (timestamp(started) and timestamp(finished) and started <= finished):
            raise ValueError("Invalid capture times")
        body = "".join(r["text"] for r in fragments if r["kind"] == "chunk")
        return stream_turn(request, body, started, finished)
    except (ValueError, TypeError, KeyError, AttributeError, IndexError):
        return known_id, None


def reload_turn(start: Path, files: list[Path], cid: str, started: float) -> Turn | None:
    record = read_start(start)
    if record is not None and record[1] == started:
        owner, turn = read_capture(record, files)
        if owner == cid:
            return turn
    return None


def fragment_gap(files: list[Path]) -> dict:
    """Count holes between numbered records. Without an end, the tail is unknown."""
    if not files:
        return {}
    last_index = int(files[-1].stem)
    missing = last_index + 1 - len(files)
    try:
        tail = json.loads(files[-1].read_bytes())
        if tail.get("kind") == "end" and tail.get("index") == last_index:
            stream = tail.get("stream")
            complete = isinstance(stream, dict) and stream.get("doneSeen") is True and stream.get("messageStreamComplete") is True
            return {"missingFragments": missing, **({"streamComplete": True} if complete else {})}
    except (OSError, ValueError, AttributeError):
        pass
    return {"missingFragmentsAtLeast": missing, "endMissing": True}


@dataclass(frozen=True)
class CapturedTurn:
    started: float
    signature: tuple[str, str]
    load: Callable[[], Turn | None]
    files: list[Path]


def captured_turns(events_dir: Path, previous: dict, current: dict) -> dict[str, list[CapturedTurn]]:
    """Index by conversation without storing message bodies or replaying settled streams."""
    turns = defaultdict(list)
    for start in events_dir.glob("*/00000.json"):
        name = start.parent.name
        stamp = file_stamp(start)
        old = previous.get(name)
        same_start = old is not None and old[0] == stamp
        try:
            record = None if same_start else read_start(start)
        except OSError:
            continue
        if not (old[1] if same_start else record):
            current[name] = [stamp, None, None]
            continue
        try:
            files = sorted(p for p in start.parent.iterdir() if re.fullmatch(r"\d{5}\.json", p.name))
        except FileNotFoundError:
            continue
        signature = hashlib.sha256(repr([stamp, [(p.name, file_stamp(p)) for p in files[1:]]]).encode()).hexdigest()
        if same_start and old[1] == signature:
            current[name] = old
            if old[2] is not None:
                cid, started = old[2]
                turns[cid].append(CapturedTurn(started, (name, signature), partial(reload_turn, start, files, cid, started), files))
            continue
        try:
            record = record or read_start(start)
            if record is None:
                continue
            _, started, request, known_id = record
            if known_id is not None and request.get("conversation_id") == known_id:
                # A verified reply must use this ID. An incomplete capture blocks this same ID.
                cid, load = known_id, partial(reload_turn, start, files, known_id, started)
            else:
                cid, turn = read_capture(record, files)
                load = lambda turn=turn: turn
        except OSError:
            continue
        current[name] = [stamp, signature, [cid, started] if cid is not None else None]
        if cid is not None:
            turns[cid].append(CapturedTurn(started, (name, signature), load, files))
    return turns


def replay_branch(turns: list[CapturedTurn], messages: list[dict], tip: str,
                  snapshot_time: float, catalog_time: float, gap: dict) -> tuple[list[dict], str, float] | None:
    """Extend only the active tip. An unlinked or unfinished later turn blocks publication."""
    seen = {msg["id"] for msg in messages}
    added = []
    last = None
    title = ""
    # Older captures, including the original stream for a saved snapshot, are superseded.
    later = sorted((item for item in turns if item.started > snapshot_time), key=lambda item: item.started)
    for number, capture in enumerate(later, 1):
        turn = capture.load()
        if turn and turn.messages[-1]["id"] in seen:
            continue
        if turn is None or turn.parent != tip or seen.intersection(msg["id"] for msg in turn.messages):
            gap.update(kind="stream-incomplete" if turn is None else "stream-unlinked",
                       afterMessageId=tip, capturedTurns=len(later), blockedTurn=number)
            if turn is None:
                gap.update(fragment_gap(capture.files))
                if gap.get("streamComplete") and gap.get("missingFragments") == 0:
                    gap["kind"] = "stream-unverified"
            return None
        added.extend(turn.messages)
        seen.update(msg["id"] for msg in turn.messages)
        tip = turn.messages[-1]["id"]
        last = turn
        title = turn.title or title
    if last is None:
        return None
    if catalog_time > last.finished + 1:
        gap.update(kind="newer-update", afterMessageId=tip, capturedTurns=len(later))
        return None
    # Local receipt time proves when a capture was observed. The Markdown date comes from the server.
    updated = max(v for msg in last.messages for v in (msg.get("create_time"), msg.get("update_time"))
                  if timestamp(v))
    if last.started <= catalog_time <= last.finished + 1:
        updated = max(updated, catalog_time)
    if updated <= snapshot_time:
        return None
    return messages + added, title, updated
