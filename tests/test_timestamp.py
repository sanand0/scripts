from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def load_module():
    script = Path(__file__).resolve().parents[1] / "timestamp.py"
    spec = importlib.util.spec_from_file_location("timestamp", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def note(body: str) -> str:
    return f"---\nsummary: keep me\n---\n\n# Call\n\n## Transcript\n\n{body}\n\n## Notes\n\nKeep [12:34] unchanged.\n"


def test_auto_offsets_reset_chunks_and_is_idempotent() -> None:
    module = load_module()
    source = note(
        "**A**: [00:00] One\n**A**: [24:32] Two"
        "\n\n---\n\n"
        "**B**: [00:00] Three\n**B**: [24:10] Four"
        "\n\n---\n\n"
        "**A**: [00:03] Five\n**A**: [10:34] Six"
    )

    first = module.update_markdown(source)
    second = module.update_markdown(first.text)

    assert "**B**: [25:00] Three" in first.text
    assert "**B**: [49:10] Four" in first.text
    assert "**A**: [50:03] Five" in first.text
    assert "**A**: [60:34] Six" in first.text
    assert first.adjusted_chunks == 2
    assert second.text == first.text
    assert second.adjusted_chunks == 0
    assert "Keep [12:34] unchanged." in first.text


def test_timestamp_ranges_and_hour_format_are_shifted() -> None:
    module = load_module()
    source = note(
        "**A**: [00:00] One\n**A**: [29:56] Two"
        "\n\n---\n\n"
        "[00:57 - 12:41] Silence\n**B**: [00:13:05] Back"
    )

    result = module.update_markdown(source)

    assert "[30:57 - 42:41] Silence" in result.text
    assert "**B**: [00:43:05] Back" in result.text


def test_separator_inside_chunk_is_not_treated_as_call_boundary() -> None:
    module = load_module()
    source = note(
        "**A**: [00:00] One\n**A**: [24:32] Two\n\n"
        "---\n**End of Part 1**\n\n"
        "---\n\n"
        "**B**: [00:00] Three"
    )

    result = module.update_markdown(source)

    assert result.chunk_count == 2
    assert "---\n**End of Part 1**" in result.text
    assert "**B**: [25:00] Three" in result.text


def test_missing_timestamp_chunk_stops_auto_inference_and_warns() -> None:
    module = load_module()
    source = note(
        "**A**: [00:00] One\n**A**: [24:30] Two"
        "\n\n---\n\n"
        "[No usable timestamps in this part]"
        "\n\n---\n\n"
        "**B**: [00:00] Three"
    )

    result = module.update_markdown(source)

    assert "**B**: [00:00] Three" in result.text
    assert any("no timestamps" in warning for warning in result.warnings)
    assert any("cannot infer" in warning for warning in result.warnings)


def test_explicit_chunk_starts_can_recover_after_timestamp_gap() -> None:
    module = load_module()
    source = note(
        "**A**: [00:00] One\n**A**: [24:30] Two"
        "\n\n---\n\n"
        "[No usable timestamps in this part]"
        "\n\n---\n\n"
        "**B**: [00:03] Three"
    )

    result = module.update_markdown(source, chunk_starts=[0, 25 * 60, 50 * 60])

    assert "**B**: [50:03] Three" in result.text
    assert any("no timestamps" in warning for warning in result.warnings)


def test_non_monotonic_chunk_is_flagged() -> None:
    module = load_module()
    source = note(
        "**A**: [00:00] One\n**A**: [29:51] Two"
        "\n\n---\n\n"
        "**A**: [29:52] Continued\n**B**: [00:13] Reset inside chunk"
    )

    result = module.update_markdown(source)

    assert result.adjusted_chunks == 0
    assert any("non-monotonic" in warning for warning in result.warnings)


def test_non_monotonic_chunk_blocks_later_auto_inference() -> None:
    module = load_module()
    source = note(
        "**A**: [00:00] One\n**A**: [29:51] Two"
        "\n\n---\n\n"
        "**A**: [29:52] Carryover\n**B**: [00:13] Reset inside chunk"
        "\n\n---\n\n"
        "**A**: [00:02] Next chunk"
    )

    result = module.update_markdown(source)

    assert "**A**: [00:02] Next chunk" in result.text
    assert any("cannot infer offset after non-monotonic chunk 2" in warning for warning in result.warnings)


def test_resolve_latest_substring_match(tmp_path: Path) -> None:
    module = load_module()
    older = tmp_path / "2026-08-21 Naveen.md"
    newer = tmp_path / "2026-08-30 Naveen Gattu.md"
    older.write_text("old")
    newer.write_text("new")

    assert module.resolve_transcript("Naveen", tmp_path) == newer


def test_parse_chunk_starts_accepts_minutes_and_timestamps() -> None:
    module = load_module()

    assert module.parse_chunk_starts("0,25,01:05:00") == [0, 1500, 3900]


def test_cli_json_params_writes_to_output_dir(tmp_path: Path) -> None:
    import json
    from typer.testing import CliRunner

    module = load_module()
    source = tmp_path / "2026-01-01 Example.md"
    source.write_text(
        note(
            "**A**: [00:00] One\n**A**: [24:30] Two"
            "\n\n---\n\n"
            "**B**: [00:03] Three"
        ),
        encoding="utf-8",
    )
    out = tmp_path / "out"
    params = json.dumps(
        {"files": [str(source)], "chunk_starts": [0, 25], "output_dir": str(out), "format": "jsonl"}
    )

    result = CliRunner().invoke(module.app, ["--params", params])

    assert result.exit_code == 0, result.output
    row = json.loads(result.stdout)
    assert row["status"] == "updated"
    assert row["adjusted_chunks"] == 1
    assert "**B**: [25:03] Three" in (out / source.name).read_text(encoding="utf-8")


def test_describe_is_machine_readable() -> None:
    import json
    from typer.testing import CliRunner

    module = load_module()
    result = CliRunner().invoke(module.app, ["--describe"])

    assert result.exit_code == 0
    description = json.loads(result.stdout)
    assert description["name"] == "timestamp.py"
    assert "chunk_starts" in description["inputs"]


def test_small_backward_overlap_is_not_retreated_as_reset() -> None:
    module = load_module()
    source = note(
        "**A**: [30:01] One\n**A**: [60:21] Two"
        "\n\n---\n\n"
        "**B**: [60:03] Three\n**B**: [88:53] Four"
    )

    result = module.update_markdown(source)

    assert result.text == source
    assert result.adjusted_chunks == 0


def test_explicit_chunk_starts_are_idempotent_even_when_previous_chunk_overruns() -> None:
    module = load_module()
    source = note(
        "**A**: [00:01] One\n**A**: [29:56] Two"
        "\n\n---\n\n"
        "**B**: [00:01] Three\n**B**: [30:21] Four"
        "\n\n---\n\n"
        "**A**: [00:03] Five\n**A**: [28:53] Six"
    )
    starts = [0, 30 * 60, 60 * 60]

    first = module.update_markdown(source, chunk_starts=starts)
    second = module.update_markdown(first.text, chunk_starts=starts)

    assert "**B**: [30:01] Three" in first.text
    assert "**A**: [60:03] Five" in first.text
    assert second.text == first.text
    assert second.adjusted_chunks == 0
