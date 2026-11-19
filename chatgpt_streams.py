"""Recover complete, linked ChatGPT turns from the extension's saved SSE records."""

from collections import defaultdict
from dataclasses import dataclass
import json
import math
from pathlib import Path
import re


ROOT = "client-created-root"
UUID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", re.I)


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


def captured_turns(events_dir: Path) -> dict[str, list[tuple[float, Turn | None]]]:
    """Read generation captures once. Known incomplete captures block older replay."""
    turns = defaultdict(list)
    for start in events_dir.glob("*/00000.json"):
        try:
            record = json.loads(start.read_bytes())
            if record["method"] != "POST" or record["path"] not in {"/backend-api/f/conversation", "/backend-api/conversation"}:
                continue
            started = record["startedAt"] / 1000
            request = record.get("request") or {}
            known_id = request.get("conversation_id") or record.get("pageConversationId")
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            continue
        try:
            files = sorted(p for p in start.parent.iterdir() if re.fullmatch(r"\d{5}\.json", p.name))
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
            cid, turn = stream_turn(request, body, started, finished)
        except (OSError, ValueError, TypeError, KeyError, AttributeError, IndexError):
            if isinstance(known_id, str) and UUID.fullmatch(known_id) and timestamp(started):
                turns[known_id].append((started, None))
        else:
            turns[cid].append((started, turn))
    return turns


def replay_branch(turns: list[tuple[float, Turn | None]], messages: list[dict], tip: str,
                  snapshot_time: float, catalog_time: float) -> tuple[list[dict], str, float] | None:
    """Extend only the active tip. An unlinked or unfinished later turn blocks publication."""
    seen = {msg["id"] for msg in messages}
    added = []
    last = None
    title = ""
    for started, turn in sorted(turns, key=lambda item: item[0]):
        # Older captures, including the original stream for a saved snapshot, are superseded.
        if started <= snapshot_time or (turn and turn.messages[-1]["id"] in seen):
            continue
        if turn is None or turn.parent != tip or seen.intersection(msg["id"] for msg in turn.messages):
            return None
        added.extend(turn.messages)
        seen.update(msg["id"] for msg in turn.messages)
        tip = turn.messages[-1]["id"]
        last = turn
        title = turn.title or title
    if last is None or catalog_time > last.finished + 1:
        return None
    # Local receipt time proves when a capture was observed. The Markdown date comes from the server.
    updated = max(v for msg in last.messages for v in (msg.get("create_time"), msg.get("update_time"))
                  if timestamp(v))
    if last.started <= catalog_time <= last.finished + 1:
        updated = max(updated, catalog_time)
    if updated <= snapshot_time:
        return None
    return messages + added, title, updated
