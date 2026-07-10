from pathlib import Path
import importlib.util
import sys


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


def test_blog_prompt_uses_compact_candidate_tags(tmp_path, monkeypatch):
    tags_path = tmp_path / "metadata-tags.yml"
    write_tags(tags_path)
    monkeypatch.setattr(summarize, "BLOG_TAGS_PATH", tags_path)
    summarize.blog_tag_vocabulary.cache_clear()

    prompt = summarize.blog_prompt("I used an LLM to improve a dataviz workflow.")

    assert "Candidate canonical tags:" in prompt
    assert "- llms:" in prompt
    assert "- data-visualization:" in prompt
    assert len(prompt) < 1500


def test_clean_blog_tags_keeps_canonical_and_flags_proposals(tmp_path, monkeypatch):
    tags_path = tmp_path / "metadata-tags.yml"
    write_tags(tags_path)
    monkeypatch.setattr(summarize, "BLOG_TAGS_PATH", tags_path)
    summarize.blog_tag_vocabulary.cache_clear()

    tags = summarize.clean_blog_tags(["LLM", "dataviz", "proposed:agent-memory", "unknown topic"])

    assert tags == ["llms", "data-visualization"]
