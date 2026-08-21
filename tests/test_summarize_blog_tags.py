'''
Run with:

cd ~/code/scripts
uv run --no-project \
  --with pytest \
  --with typer \
  --with google-genai \
  --with python-dotenv \
  --with ruamel.yaml \
  --with rich \
  --with pydantic \
  --with tenacity \
  pytest -q tests/test_summarize_blog_tags.py
'''

from pathlib import Path
import importlib.util
import sys

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
