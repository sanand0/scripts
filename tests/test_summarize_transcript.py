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
  pytest -q tests/test_summarize_transcript.py
'''

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

SCRIPT = Path(__file__).parents[1] / "summarize.py"
spec = importlib.util.spec_from_file_location('summarize_revised', SCRIPT)
assert spec and spec.loader
summarize = importlib.util.module_from_spec(spec)
spec.loader.exec_module(summarize)


def transcript_set():
    return summarize.CONTENT_SET_MAP['transcript']


def transcript_text(frontmatter: str = '') -> str:
    speakers = '\n\n'.join(
        f'**Person**: [00:{i:02d}] This is substantive transcript content line {i} with enough detail.'
        for i in range(1, 8)
    )
    prefix = f'---\n{frontmatter.strip()}\n---\n\n' if frontmatter else ''
    return f'{prefix}# 2026-07-20 Test call\n\n## Transcript\n\n{speakers}\n'


def test_field_order_places_what_i_missed_after_actions() -> None:
    names = transcript_set().meta_keys
    assert names[names.index('actions') + 1] == 'what-i-missed'
    assert names[names.index('what-i-missed') + 1] == 'ideas'


def test_without_frontmatter_fields_removes_only_regenerated_fields() -> None:
    text = transcript_text(
        '''summary:\n- Existing summary\nactions:\n- Old action\nwhat-i-missed:\n- Old miss\nkeywords: [alpha]'''
    )
    cleaned = summarize.without_frontmatter_fields(text, {'actions', 'what-i-missed'})
    assert 'Old action' not in cleaned
    assert 'Old miss' not in cleaned
    assert 'Existing summary' in cleaned
    assert 'keywords: [alpha]' in cleaned
    assert '## Transcript' in cleaned


def test_call_gemini_does_not_send_old_selected_field() -> None:
    captured: dict[str, object] = {}

    class FakeModels:
        def generate_content(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                text=json.dumps({'actions': ['Owner: New action.']}),
                usage_metadata=None,
                candidates=[],
            )

    client = SimpleNamespace(models=FakeModels())
    action_field = next(field for field in transcript_set().fields if field.name == 'actions')
    text = transcript_text('summary:\n- Existing summary\nactions:\n- Old action')
    result, _ = summarize.call_gemini(client, 'fake-model', transcript_set(), text, [action_field])

    assert result.actions == ['Owner: New action.']
    assert captured['config'].temperature == 0
    contents = str(captured['contents'])
    assert 'Old action' not in contents
    assert 'Existing summary' in contents


def test_force_selected_field_preserves_unselected_metadata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / '2026-07-20 Test.md'
    path.write_text(
        transcript_text(
            '''summary:\n- Keep this summary\nactions:\n- Old action\nwhat-i-missed:\n- Keep this miss\nideas:\n- Keep this idea'''
        ),
        encoding='utf-8',
    )

    def fake_call(*_args, **_kwargs):
        return SimpleNamespace(actions=['Owner: By 20 Jul 2026. Send the report.']), summarize.Usage()

    monkeypatch.setattr(summarize, 'call_ai', fake_call)
    result = summarize.process_file(
        path=path, provider='gemini', client=None, model='fake-model', dry_run=False, force=True,
        content_set=transcript_set(), selected_fields={'actions'},
    )
    metadata, _, _ = summarize.parse_frontmatter(path.read_text(encoding='utf-8'))

    assert result['status'] == 'updated'
    assert result['added_fields'] == ['actions']
    assert metadata['actions'] == ['Owner: By 20 Jul 2026. Send the report.']
    assert metadata['summary'] == ['Keep this summary']
    assert metadata['what-i-missed'] == ['Keep this miss']
    assert metadata['ideas'] == ['Keep this idea']


def test_missing_selected_field_is_added_without_regenerating_existing_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / '2026-07-20 Test.md'
    path.write_text(
        transcript_text('summary:\n- Keep this summary\nactions:\n- Keep this action'),
        encoding='utf-8',
    )

    def fake_call(*_args, **_kwargs):
        return SimpleNamespace(**{'what-i-missed': []}), summarize.Usage()

    monkeypatch.setattr(summarize, 'call_ai', fake_call)
    result = summarize.process_file(
        path=path, provider='gemini', client=None, model='fake-model', dry_run=False, force=False,
        content_set=transcript_set(), selected_fields={'what-i-missed'},
    )
    metadata, _, _ = summarize.parse_frontmatter(path.read_text(encoding='utf-8'))

    assert result['added_fields'] == ['what-i-missed']
    assert metadata['summary'] == ['Keep this summary']
    assert metadata['actions'] == ['Keep this action']
    assert metadata['what-i-missed'] == []


def test_extract_speakers_ignores_bulleted_analysis_labels_and_generic_roles() -> None:
    body = """**Fact-checks cited**: not a speaker
- **Persona**: profile
- **Insights**: observation
## Transcript
**Anand**: [00:01] Hello.
**Arvind:** [00:02] Hi.
**Question**: Not a named speaker.
**Team:** Also not a named speaker.
"""
    assert summarize.extract_speakers(body) == ['Anand', 'Arvind']


@pytest.mark.parametrize("name", [
    "Kamalesh", "Maleeha Khan", "Alice Hostetter", "Mark Staffieri", "Bhalchandra Doctor",
    "Dr. Harsh Vardhan", "A. P. J. Abdul Kalam", "Syed Abdullah M J Shah",
    "Nguyễn Thị Minh", "José Ángel", "Ai Tanaka", "Howe", "Whyte", "James Reason", "Pavan/Varun",
])
def test_real_name_filter_accepts_likely_future_names(name: str) -> None:
    assert summarize.clean_people([name]) == [name]


@pytest.mark.parametrize("label", [
    "Speaker 1", "Female Speaker", "Multiple Speakers", "Team Member", "Participants", "Audience Question",
    "Client Lead", "Straive Tech", "ACS Staff", "EU Holidays Rep", "Background Voice",
    "Video Narration", "Debjani's assistant", "Perplexity AI", "NotebookLM Video",
    "Krishna's Insight", "Key Takeaways", "What you meant", "Why it matters",
    "How they responded", "Next steps", "Better move", "Possibly-invalid assumptions",
    "Question", "Answer", "All", "Someone", "Cashier", "Doctor", "Student", "Group",
    "To recap", "Then, last iteration", "Engagement Strategy", "Measurable outcome",
    "Behavior change", "My response", "Our strategy", "Potentially invalid assumptions",
    "Action item", "Step one", "Client", "Research Partner", "Source",
])
def test_real_name_filter_rejects_generic_roles_and_analysis_labels(label: str) -> None:
    assert summarize.clean_people([label]) == []


def test_clean_what_i_missed_normalizes_reason_taxonomy() -> None:
    cleaned = summarize.clean_what_i_missed(
        ['Mayank — Bid: x. Better move: y. Possible reason: topic.']
    )
    assert cleaned == ['Mayank — Bid: x. Better move: y. Possible reason: topic shift.']


def test_cli_rejects_unknown_selected_field() -> None:
    runner = CliRunner()
    result = runner.invoke(summarize.app, ['transcript', '--fields', 'actions,bogus'])
    assert result.exit_code == 1
    assert 'Unknown fields: bogus' in result.output


def test_process_file_generates_what_i_missed_in_one_model_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / '2026-07-20 Test.md'
    path.write_text(transcript_text(), encoding='utf-8')
    calls = 0

    def fake_call(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        usage = summarize.Usage()
        usage.add(100, 20)
        return SimpleNamespace(**{'what-i-missed': [
            'Vel — Bid: I lost track. Better move: What part should I revisit? '
            'Possible reason: topic.'
        ]}), usage

    monkeypatch.setattr(summarize, 'call_ai', fake_call)
    result = summarize.process_file(
        path=path, provider='gemini', client=None, model='fake-model', dry_run=False, force=False,
        content_set=transcript_set(), selected_fields={'what-i-missed'},
    )
    metadata, _, _ = summarize.parse_frontmatter(path.read_text(encoding='utf-8'))

    assert calls == 1
    assert result['tokens'] == {'prompt': 100, 'output': 20, 'calls': 1}
    assert metadata['what-i-missed'] == [
        'Vel — Bid: I lost track. Better move: What part should I revisit? '
        'Possible reason: topic shift.'
    ]


def test_what_i_missed_prompt_requires_evidence_and_avoids_invented_reasons() -> None:
    field = next(field for field in transcript_set().fields if field.name == 'what-i-missed')
    assert 'anchored to transcript evidence' in field.description
    assert 'exact quote, fragment, or close paraphrase' in field.description
    assert 'Do not invent a psychological explanation' in field.description
    assert 'Reserve an empty list for transcripts with essentially no meaningful bids' in field.description
