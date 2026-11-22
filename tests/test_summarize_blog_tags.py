'''
Run with:

cd ~/code/scripts
uv run --no-project \
  --with pytest \
  --with typer \
  --with google-genai \
  --with 'openai>=3.28' \
  --with 'pyjwt[crypto]' \
  --with python-dotenv \
  --with ruamel.yaml \
  --with rich \
  --with pydantic \
  --with tenacity \
  pytest -q tests/test_summarize_blog_tags.py
'''

import base64
import hashlib
import importlib.util
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import urlopen

import pytest
from typer.testing import CliRunner


SPEC = importlib.util.spec_from_file_location(
    "summarize", Path(__file__).parents[1] / "summarize.py"
)
summarize = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = summarize
SPEC.loader.exec_module(summarize)


def write_tags(path: Path) -> None:
    path.write_text(
        """tags:
  llms:
    description: Posts about LLMs.
    aliases: [large language models, llm]
    count: 66
  data-visualization:
    description: Posts about data visualization.
    aliases: [dataviz]
    count: 90
  india:
    description: Posts about india.
    aliases: []
    count: 102
""",
        encoding="utf-8",
    )


def test_blog_defaults_to_more_workers_without_changing_transcript_default():
    assert summarize.CONTENT_SET_MAP["blog"].default_workers == 8
    assert summarize.CONTENT_SET_MAP["transcript"].default_workers == 4


def test_blog_prompt_uses_compact_candidate_tags(tmp_path, monkeypatch):
    tags_path = tmp_path / "metadata-tags.yml"
    write_tags(tags_path)
    monkeypatch.setattr(summarize, "BLOG_TAGS_PATH", tags_path)
    summarize.blog_tag_vocabulary.cache_clear()

    prompt = summarize.blog_prompt("I used an LLM to improve a dataviz workflow.")

    assert "Candidate canonical tag shortlist:" in prompt
    assert "- llms (66 posts):" in prompt
    assert "- data-visualization (90 posts):" in prompt
    assert len(prompt) < 4000


def test_blog_prompt_uses_human_first_low_density_descriptions_and_precise_tags(tmp_path, monkeypatch):
    tags_path = tmp_path / "metadata-tags.yml"
    write_tags(tags_path)
    monkeypatch.setattr(summarize, "BLOG_TAGS_PATH", tags_path)
    summarize.blog_tag_vocabulary.cache_clear()

    prompt = summarize.blog_prompt("I used an LLM to improve a dataviz workflow.")

    assert "human scanning Anand's blog" in prompt
    assert "search or an LLM agent" in prompt
    assert "Use first person when" in prompt
    assert "I found a page" in prompt
    assert "distinctive/personal x surprising" in prompt
    assert "at most 2 illustrative findings" in prompt
    assert "baseline and the standout result" in prompt
    assert "what the action lets someone conclude or prove" in prompt
    assert "Omission is a feature" in prompt
    assert "Silently verify every remaining concrete fact" in prompt
    assert "choose 2-4 canonical tags" in prompt
    assert "organizing question or lens" in prompt
    assert "future outcomes -> forecasting" in prompt
    assert "shortlist is not exhaustive" in prompt
    assert "(66 posts)" in prompt


def test_blog_prompt_can_request_only_tags(tmp_path, monkeypatch):
    tags_path = tmp_path / "metadata-tags.yml"
    write_tags(tags_path)
    monkeypatch.setattr(summarize, "BLOG_TAGS_PATH", tags_path)
    summarize.blog_tag_vocabulary.cache_clear()

    tags_field = next(field for field in summarize.CONTENT_SET_MAP["blog"].fields if field.name == "tags")
    prompt = summarize.blog_prompt("I used an LLM to improve a dataviz workflow.", [tags_field])

    assert "Generate only canonical tags" in prompt
    assert "Generate a description" not in prompt
    assert "- llms (66 posts):" in prompt
    assert "- data-visualization (90 posts):" in prompt


def test_clean_blog_tags_keeps_canonical_and_flags_proposals(tmp_path, monkeypatch):
    tags_path = tmp_path / "metadata-tags.yml"
    write_tags(tags_path)
    monkeypatch.setattr(summarize, "BLOG_TAGS_PATH", tags_path)
    summarize.blog_tag_vocabulary.cache_clear()

    tags = summarize.clean_blog_tags(["LLM", "dataviz", "proposed:agent-memory", "unknown topic"])

    assert tags == ["llms", "data-visualization"]


def test_split_blog_tags_returns_normalized_deduplicated_proposals(tmp_path, monkeypatch):
    tags_path = tmp_path / "metadata-tags.yml"
    write_tags(tags_path)
    monkeypatch.setattr(summarize, "BLOG_TAGS_PATH", tags_path)
    summarize.blog_tag_vocabulary.cache_clear()

    tags, proposals = summarize.split_blog_tags(
        ["LLM", "proposed:Agent Memory", "agent-memory", "proposed:agent_memory"]
    )

    assert tags == ["llms"]
    assert proposals == ["agent-memory"]


def test_merge_blog_tag_proposals_reconciles_sources_and_sorts(tmp_path):
    ledger = tmp_path / "metadata-tag-proposals.yml"
    ledger.write_text(
        """version: 1
proposals:
  obsolete:
    sources:
      posts/a.md: {content_hash: old}
  retained:
    sources:
      posts/untouched.md: {content_hash: keep}
""",
        encoding="utf-8",
    )

    summarize.merge_blog_tag_proposals(
        ledger,
        [
            {"source": "posts/a.md", "content_hash": "new-a", "proposals": ["z-tag", "new-tag"]},
            {"source": "posts/b.md", "content_hash": "new-b", "proposals": ["new-tag", "new-tag"]},
        ],
    )

    data = summarize.make_yaml().load(ledger)
    assert list(data["proposals"]) == ["new-tag", "retained", "z-tag"]
    assert list(data["proposals"]["new-tag"]["sources"]) == ["posts/a.md", "posts/b.md"]
    assert "obsolete" not in data["proposals"]
    assert data["proposals"]["retained"]["sources"]["posts/untouched.md"]["content_hash"] == "keep"


def test_summarize_dry_run_does_not_write_proposal_ledger(tmp_path, monkeypatch):
    post = tmp_path / "post.md"
    post.write_text("# Title\n\nOne\nTwo\nThree\nFour\nFive\n", encoding="utf-8")
    ledger = tmp_path / "metadata-tag-proposals.yml"
    monkeypatch.setattr(summarize, "BLOG_PROPOSALS_PATH", ledger)
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setattr(summarize, "resolve_files", lambda *_: [post])
    monkeypatch.setattr(summarize, "call_ai", lambda *_: (_FakeMeta(), summarize.Usage()))
    monkeypatch.setitem(summarize.CONTENT_SET_MAP, "blog-test", summarize.CONTENT_SET_MAP["blog"])
    monkeypatch.setattr("openai.OpenAI", lambda **_: object())

    result = CliRunner().invoke(summarize.app, ["blog-test", "--dry-run", "--format", "json"])

    assert result.exit_code == 0
    assert '"status": "dry-run"' in result.stdout
    assert '"proposals": ["agent-memory"]' in result.stdout
    assert not ledger.exists()


def test_summarize_merges_proposals_once_after_workers(tmp_path, monkeypatch):
    posts = []
    for name in ["a.md", "b.md"]:
        post = tmp_path / name
        post.write_text("# Title\n\nOne\nTwo\nThree\nFour\nFive\n", encoding="utf-8")
        posts.append(post)
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setattr(summarize, "resolve_files", lambda *_: posts)
    monkeypatch.setattr(summarize, "call_ai", lambda *_: (_FakeMeta(), summarize.Usage()))
    monkeypatch.setitem(summarize.CONTENT_SET_MAP, "blog-test", summarize.CONTENT_SET_MAP["blog"])
    monkeypatch.setattr("openai.OpenAI", lambda **_: object())
    calls = []
    monkeypatch.setattr(summarize, "merge_blog_tag_proposals", lambda path, evidence: calls.append((path, evidence)))

    result = CliRunner().invoke(summarize.app, ["blog-test", "--workers", "2", "--format", "json"])

    assert result.exit_code == 0
    assert len(calls) == 1
    assert len(calls[0][1]) == 2
    assert all(item["proposals"] == ["agent-memory"] for item in calls[0][1])
    for post in posts:
        metadata = summarize.parse_frontmatter(post.read_text(encoding="utf-8"))[0]
        assert metadata["tags"] == ["llms"]


def test_blog_generates_description_and_tags_in_separate_ai_calls(tmp_path, monkeypatch):
    post = tmp_path / "post.md"
    post.write_text("# Title\n\nOne\nTwo\nThree\nFour\nFive\n", encoding="utf-8")
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setattr(summarize, "resolve_files", lambda *_: [post])
    monkeypatch.setitem(summarize.CONTENT_SET_MAP, "blog-test", summarize.CONTENT_SET_MAP["blog"])
    monkeypatch.setattr("openai.OpenAI", lambda **_: object())
    calls = []

    def fake_call_ai(provider, client, model, content_set, text, fields):
        calls.append([field.name for field in fields])
        return _FakeMeta(), summarize.Usage(prompt=10, output=2, calls=1)

    monkeypatch.setattr(summarize, "call_ai", fake_call_ai)
    result = CliRunner().invoke(summarize.app, ["blog-test", "--dry-run", "--format", "json"])

    assert result.exit_code == 0
    assert calls == [["description"], ["tags"]]
    assert '"calls": 2' in result.stdout



class _FakeMeta:
    description = "A useful post."
    tags = ["llms", "proposed:agent-memory"]


def test_chatgpt_login_paste_reuses_registration_and_private_state(tmp_path, monkeypatch):
    root = tmp_path / "chatgpt"
    monkeypatch.setattr(summarize, "CHATGPT_STATE", root)
    attempts = []
    expected = {"issuer": summarize.CHATGPT_ISSUER, "subject": "user", "email": "user@example.com"}

    def echo(message, *, err=False):
        if message.startswith("Continue with ChatGPT\n"):
            params = {k: v[0] for k, v in parse_qs(urlsplit(message.splitlines()[1]).query).items()}
            attempts.append(params)

    def callback():
        attempt = attempts[-1]
        params = dict(state=attempt["state"], code="code")
        if attempt["client_id"] == summarize.CHATGPT_REGISTER:
            params["client_id"] = "oaiapp_test"
        return f"{attempt['redirect_uri']}?{urlencode(params)}\n"

    def exchange(client_id, **grant):
        assert client_id == "oaiapp_test"
        assert grant["grant_type"] == "authorization_code"
        assert grant["code"] == "code"
        assert grant["redirect_uri"] == attempts[-1]["redirect_uri"]
        digest = hashlib.sha256(grant["code_verifier"].encode()).digest()
        assert base64.urlsafe_b64encode(digest).decode().rstrip("=") == attempts[-1]["code_challenge"]
        return {"id_token": "id", "access_token": "access", "refresh_token": "refresh",
                "scope": summarize.CHATGPT_SCOPES, "expires_in": 3600}

    with monkeypatch.context() as patch:
        patch.setattr(summarize.typer, "echo", echo)
        patch.setattr(sys.stdin, "readline", callback)
        patch.setattr(summarize, "chatgpt_exchange", exchange)
        patch.setattr(summarize, "chatgpt_identity", lambda *_: expected)
        summarize.login_chatgpt(None, True, False, False)
        summarize.login_chatgpt(None, True, False, False)

    assert attempts[0]["client_id"] == summarize.CHATGPT_REGISTER
    assert attempts[0]["agent_name_hint"] == "summarize.py"
    assert attempts[1]["client_id"] == "oaiapp_test"
    assert "agent_name_hint" not in attempts[1] and "id_token_hint" not in attempts[1]
    assert attempts[0]["state"] != attempts[1]["state"]
    assert attempts[0]["ext_agent_host_id"] == attempts[1]["ext_agent_host_id"]
    record = root / "user@example.com/oaiapp_test.json"
    assert summarize.chatgpt_record(None) == record
    assert os.stat(root).st_mode & 0o777 == 0o700
    assert os.stat(record).st_mode & 0o777 == 0o600
    assert summarize.chatgpt_access_token(record) == "access"
    listed = CliRunner().invoke(summarize.app, ["login", "chatgpt", "--accounts"])
    assert listed.stdout == "user@example.com/oaiapp_test\tactive\n"


def test_chatgpt_login_accepts_loopback_callback(monkeypatch):
    with ThreadPoolExecutor(1) as pool:
        callbacks = []

        def echo(message, **kwargs):
            if message.startswith("Continue with ChatGPT\n"):
                params = parse_qs(urlsplit(message.splitlines()[1]).query)
                query = urlencode(dict(state=params["state"][0], code="code", client_id="oaiapp_test"))
                callbacks.append(pool.submit(urlopen, f"{params['redirect_uri'][0]}?{query}", timeout=5))

        monkeypatch.setattr(summarize.typer, "echo", echo)
        monkeypatch.setattr(summarize, "chatgpt_exchange", lambda *_args, **_kwargs: {
            "id_token": "id", "access_token": "access", "scope": summarize.CHATGPT_SCOPES, "expires_in": 3600,
        })
        monkeypatch.setattr(summarize, "chatgpt_identity", lambda *_: {"subject": "user"})
        record = summarize.authorize_chatgpt("urn:uuid:host", {}, False)
        with callbacks[0].result(timeout=5) as response:
            assert response.status == 200
            assert response.headers["Cache-Control"] == "no-store"
    assert record["client_id"] == "oaiapp_test"


@pytest.mark.parametrize("suffix, client_id", [
    ("state=other&code=code&client_id=oaiapp_test", "dynamic_agent_client"),
    ("state=state&error=access_denied", "dynamic_agent_client"),
    ("state=state&code=code", "dynamic_agent_client"),
    ("state=state&code=code&client_id=oaiapp_other", "oaiapp_test"),
])
def test_chatgpt_callback_rejects_wrong_state_client_or_decline(suffix, client_id):
    redirect = "http://127.0.0.1:1234/auth/callback"
    with pytest.raises(summarize.ChatGPTError):
        summarize.chatgpt_callback(f"{redirect}?{suffix}", redirect, "state", client_id)


def test_chatgpt_verifies_id_token_signature_and_nonce(monkeypatch):
    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwks_key = jwt.PyJWK.from_dict(json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key())))
    monkeypatch.setattr(jwt.PyJWKClient, "get_signing_key_from_jwt", lambda *_: jwks_key)
    claims = dict(iss=summarize.CHATGPT_ISSUER, sub="user", aud="oaiapp_test", nonce="nonce",
                  exp=int(time.time()) + 300, email="user@example.com")
    token = jwt.encode(claims, key, algorithm="RS256")
    assert summarize.chatgpt_identity(token, "oaiapp_test", "nonce")["email"] == claims["email"]
    with pytest.raises(summarize.ChatGPTError, match="sign-in attempt"):
        summarize.chatgpt_identity(token, "oaiapp_test", "other")
    with pytest.raises(summarize.ChatGPTError, match="validate"):
        summarize.chatgpt_identity(token, "oaiapp_other", "nonce")


def test_chatgpt_refresh_serializes_rotation(tmp_path, monkeypatch):
    monkeypatch.setattr(summarize, "CHATGPT_STATE", tmp_path)
    record = tmp_path / "user@example.com/oaiapp_test.json"
    summarize.save_chatgpt_state(record, dict(client_id="oaiapp_test", refresh_token="original",
                                              expires_at=0, scopes=[summarize.CHATGPT_SCOPE]))
    exchanged = []

    def exchange(client_id, **grant):
        exchanged.append((client_id, grant))
        return dict(access_token="renewed", refresh_token="rotated", expires_in=3600,
                    scope=summarize.CHATGPT_SCOPES)

    monkeypatch.setattr(summarize, "chatgpt_exchange", exchange)
    with ThreadPoolExecutor(4) as pool:
        assert list(pool.map(summarize.chatgpt_access_token, [record] * 4)) == ["renewed"] * 4
    assert exchanged == [("oaiapp_test", {"grant_type": "refresh_token", "refresh_token": "original"})]
    assert json.loads(record.read_text())["refresh_token"] == "rotated"


@pytest.mark.parametrize("completed", [True, False])
def test_chatgpt_structured_stream_through_cli(tmp_path, monkeypatch, completed):
    import httpx2
    import openai

    post = tmp_path / "post.md"
    text = "# Title\n\nOne\nTwo\nThree\nFour\nFive\n"
    post.write_text(text)
    monkeypatch.setattr(summarize, "CHATGPT_STATE", tmp_path / "chatgpt")
    account = "user@example.com/oaiapp_test"
    summarize.save_chatgpt_state(summarize.CHATGPT_STATE / "active", account)
    summarize.save_chatgpt_state(summarize.CHATGPT_STATE / f"{account}.json", dict(
        scopes=[summarize.CHATGPT_SCOPE], access_token="test-oauth", expires_at=time.time() + 3600,
    ))

    def send(request):
        assert str(request.url) == "https://api.openai.com/v1/responses"
        assert request.headers["Authorization"] == "Bearer test-oauth"
        params = json.loads(request.content)
        assert params["model"] == "gpt-6-luna"
        assert params["store"] is False and params["stream"] is True
        assert params["input"][0]["role"] == "user" and text in params["input"][0]["content"]
        assert params["text"]["format"]["type"] == "json_schema"
        response = dict(id="resp_test", model="gpt-6-luna", object="response", created_at=1,
                        status="in_progress", output=[])
        events = [dict(type="response.created", sequence_number=0, response=response)]
        if completed:
            output = [dict(type="message", role="assistant", id="msg_test", status="completed", content=[
                dict(type="output_text", text='{"description":"A short description."}', annotations=[]),
            ])]
            usage = dict(input_tokens=50, output_tokens=10, total_tokens=60)
            events.append(dict(type="response.completed", sequence_number=1,
                               response=dict(response, status="completed", output=output, usage=usage)))
        return httpx2.Response(200, headers={"Content-Type": "text/event-stream"},
                               text="".join(f"data: {json.dumps(event)}\n\n" for event in events))

    real_client = openai.OpenAI
    monkeypatch.setattr(openai, "OpenAI", lambda **kwargs: real_client(
        **kwargs, http_client=httpx2.Client(transport=httpx2.MockTransport(send)),
    ))
    result = CliRunner().invoke(summarize.app, ["blog", str(post), "--provider", "chatgpt", "--fields",
                                              "description", "--dry-run", "--format", "json"])
    assert post.read_text() == text
    row = json.loads(result.stdout)
    if completed:
        assert result.exit_code == 0, row
        assert row["status"] == "dry-run" and row["tokens"]["output"] == 10
        assert row["cost_usd"] is None
    else:
        assert result.exit_code == 1
        assert "stream ended before response.completed" in row["error"]
