from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap


def load_module():
    script_path = Path(__file__).resolve().parents[1] / "transcribe_calls.py"
    spec = importlib.util.spec_from_file_location("transcribe_calls", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def run_script(
    script_path: Path,
    *args: Path | str,
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "run", str(script_path), *(str(arg) for arg in args)],
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd,
        check=False,
    )


def write_fake_google_genai(package_root: Path) -> Path:
    genai_package = package_root / "google" / "genai"
    genai_package.mkdir(parents=True)
    (package_root / "google" / "__init__.py").write_text("from . import genai\n", encoding="utf-8")
    (genai_package / "__init__.py").write_text(
        textwrap.dedent(
            """\
            from __future__ import annotations
            
            import json
            import os
            from pathlib import Path

            class APIError(Exception):
                pass


            class _Errors:
                APIError = APIError


            errors = _Errors()


            class GenerateContentConfig:
                def __init__(self, system_instruction=None, **kwargs):
                    self.system_instruction = system_instruction


            class _Types:
                GenerateContentConfig = GenerateContentConfig


            types = _Types()


            class _UploadedFile:
                def __init__(self, file):
                    self.file = str(file)
                    self.name = f"files/{Path(file).name}"


            class _FilesAPI:
                def upload(self, *, file, config=None):
                    return _UploadedFile(file)


            class _ModelsAPI:
                def generate_content(self, *, model, contents, config=None):
                    log_path = os.environ["FAKE_GENAI_LOG"]
                    audio = next(item for item in contents if hasattr(item, "file"))
                    user_prompts = [item for item in contents if isinstance(item, str)]
                    with open(log_path, "a", encoding="utf-8") as handle:
                        handle.write(f"MODEL\\t{model}\\n")
                        handle.write(f"AUDIO\\t{audio.file}\\n")
                        handle.write(f"SYSTEM_PROMPT\\t{getattr(config, 'system_instruction', '')}\\n")
                        if user_prompts:
                            handle.write(f"USER_PROMPT\\t{user_prompts[0]}\\n")
                    prompt_tokens = int(os.environ.get("FAKE_PROMPT_TOKENS", "100"))
                    output_tokens = int(os.environ.get("FAKE_OUTPUT_TOKENS", "50"))
                    thought_tokens = int(os.environ.get("FAKE_THOUGHT_TOKENS", "0"))
                    total_tokens = int(
                        os.environ.get(
                            "FAKE_TOTAL_TOKENS",
                            str(prompt_tokens + output_tokens + thought_tokens),
                        )
                    )
                    response_by_file = json.loads(os.environ.get("FAKE_GENAI_RESPONSE_BY_FILE", "{}"))
                    default_text = "\\n".join(
                        f"**Speaker**: [00:0{index}] Transcript for {Path(audio.file).name} line {index}"
                        for index in range(1, 6)
                    )
                    usage = type(
                        "UsageMetadata",
                        (),
                        {
                            "prompt_token_count": prompt_tokens,
                            "cached_content_token_count": 0,
                            "candidates_token_count": output_tokens,
                            "thoughts_token_count": thought_tokens,
                            "total_token_count": total_tokens,
                        },
                    )()
                    return type(
                        "Response",
                        (),
                        {
                            "text": response_by_file.get(
                                Path(audio.file).name,
                                os.environ.get("FAKE_GENAI_TRANSCRIPT_TEXT", default_text),
                            ),
                            "usage_metadata": usage,
                            "model_version": model,
                        },
                    )()


            class Client:
                def __init__(self, *, api_key=None, **kwargs):
                    if not api_key:
                        raise APIError("missing api key")
                    log_path = os.environ.get("FAKE_GENAI_LOG")
                    if log_path:
                        with open(log_path, "a", encoding="utf-8") as handle:
                            handle.write(f"APIKEY\\t{api_key}\\n")
                    self.files = _FilesAPI()
                    self.models = _ModelsAPI()
            """
        ),
        encoding="utf-8",
    )
    return package_root


def write_fake_ffmpeg_tools(bin_dir: Path) -> Path:
    bin_dir.mkdir(parents=True, exist_ok=True)
    (bin_dir / "ffprobe").write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            set -euo pipefail
            printf '%s\\n' "${FAKE_FFPROBE_DURATION:-60}"
            """
        ),
        encoding="utf-8",
    )
    (bin_dir / "ffmpeg").write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            set -euo pipefail
            output="${@: -1}"
            mkdir -p "$(dirname "$output")"
            if [[ -n "${FAKE_FFMPEG_LOG:-}" ]]; then
              printf '%s\\n' "$*" >> "$FAKE_FFMPEG_LOG"
            fi
            printf 'chunk' > "$output"
            """
        ),
        encoding="utf-8",
    )
    (bin_dir / "ffprobe").chmod(0o755)
    (bin_dir / "ffmpeg").chmod(0o755)
    return bin_dir


def write_fake_google_prices(prices_path: Path) -> Path:
    prices_path.write_text(
        json.dumps(
            {
                "vendor": "google",
                "models": [
                    {
                        "id": "gemini-3-1-pro-preview",
                        "name": "Gemini 3.1 Pro <=200k",
                        "price_history": [
                            {"input": 2.0, "output": 12.0, "input_cached": None}
                        ],
                    },
                    {
                        "id": "gemini-3-1-pro-preview-200k",
                        "name": "Gemini 3.1 Pro >200k",
                        "price_history": [
                            {"input": 4.0, "output": 18.0, "input_cached": None}
                        ],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return prices_path


def test_extract_system_prompt_prefers_first_code_fence() -> None:
    module = load_module()
    prompt = textwrap.dedent(
        """
        Intro text.

        ```markdown
        First prompt
        line two
        ```

        ```markdown
        Second prompt
        ```
        """
    )
    assert module.extract_system_prompt(prompt) == "First prompt\nline two"


def test_has_transcript_content_requires_non_empty_body() -> None:
    module = load_module()
    empty = "# Demo\n\n## Transcript\n\n"
    filled = "# Demo\n\n## Transcript\n\nHello there\n"

    assert module.has_transcript_content(empty) is False
    assert module.has_transcript_content(filled) is True


def test_upsert_transcript_section_preserves_existing_notes() -> None:
    module = load_module()
    existing = "# Demo\n\n## Notes\n\nAlready here.\n"
    updated = module.upsert_transcript_section(existing, "Demo", "Generated transcript")

    assert "## Notes\n\nAlready here." in updated
    assert "## Transcript\n\nGenerated transcript" in updated


def test_upsert_transcript_section_updates_prompt_metadata() -> None:
    module = load_module()
    existing = "---\ntags:\n---\n\n# Demo\n\n## Notes\n\nAlready here.\n"

    updated = module.upsert_transcript_section(
        existing,
        "Demo",
        "Generated transcript",
        prompt="Focus on action items",
    )

    assert "prompt: |-" in updated
    assert "  Focus on action items" in updated
    assert "## Transcript\n\nGenerated transcript" in updated


def test_upsert_transcript_section_rejects_duplicate_sections() -> None:
    module = load_module()
    markdown = "# Demo\n\n## Transcript\n\nFirst\n\n## Notes\n\nKeep me\n\n## Transcript\n\nSecond\n"

    try:
        module.upsert_transcript_section(markdown, "Demo", "Generated transcript")
    except ValueError as exc:
        assert "multiple ## Transcript sections" in str(exc)
    else:
        raise AssertionError("Expected duplicate transcript sections to be rejected")


def test_patch_transcript_section_replaces_requested_part() -> None:
    module = load_module()
    markdown = (
        "# Demo\n\n## Transcript\n\n"
        "first chunk\n\n---\n\nsecond chunk\n\n---\n\nthird chunk\n"
    )

    patched = module.patch_transcript_section(markdown, 2, "replacement chunk")

    assert "first chunk\n\n---\n\nreplacement chunk\n\n---\n\nthird chunk" in patched


def test_looks_like_transcript_requires_five_matching_lines() -> None:
    module = load_module()
    valid = "\n".join(
        f"**Speaker**: [00:0{index}] line {index}"
        for index in range(1, 6)
    )
    invalid = "It appears that you forgot to attach the audio file."

    assert module.looks_like_transcript(valid) is True
    assert module.looks_like_transcript(invalid) is False


def test_extract_prompt_metadata_reads_block_scalar() -> None:
    module = load_module()
    markdown = (
        "---\n"
        "tags:\n"
        "prompt: |-\n"
        "  Focus on action items\n"
        "---\n\n"
        "# Demo\n"
    )

    extracted = module.extract_prompt_metadata(markdown)

    assert extracted == "Focus on action items"


def test_find_invalid_transcript_sections_returns_bad_part_indices() -> None:
    module = load_module()
    markdown = (
        "# Demo\n\n## Transcript\n\n"
        "**Speaker**: [00:01] okay\n"
        "**Speaker**: [00:02] fine\n"
        "**Speaker**: [00:03] yes\n"
        "**Speaker**: [00:04] sure\n"
        "**Speaker**: [00:05] done\n"
        "\n---\n\n"
        "It appears that you forgot to attach the audio file.\n"
        "\n---\n\n"
        "It looks like you forgot to attach the transcript.\n"
    )

    assert module.find_invalid_transcript_sections(markdown) == [2, 3]


def test_build_chunk_windows_prefers_friendly_nominal_size_and_uses_one_second_overlap() -> None:
    module = load_module()

    windows = module.build_chunk_windows(duration_seconds=3900, chunk_seconds=1800, overlap_seconds=1.0)

    assert windows == [(0.0, 1500.0), (1499.0, 1501.0), (2999.0, 901.0)]


def test_build_chunk_windows_uses_twenty_minute_chunks_for_forty_minutes() -> None:
    module = load_module()

    windows = module.build_chunk_windows(duration_seconds=2400, chunk_seconds=1800, overlap_seconds=1.0)

    assert windows == [(0.0, 1200.0), (1199.0, 1201.0)]


def test_build_chunk_windows_prefers_twenty_five_over_odd_even_splits() -> None:
    module = load_module()

    windows = module.build_chunk_windows(duration_seconds=5580, chunk_seconds=1800, overlap_seconds=1.0)

    assert windows == [(0.0, 1500.0), (1499.0, 1501.0), (2999.0, 1501.0), (4499.0, 1081.0)]


def test_build_chunk_windows_rejects_overlap_not_smaller_than_chunk() -> None:
    module = load_module()

    try:
        module.build_chunk_windows(duration_seconds=10, chunk_seconds=0.5, overlap_seconds=1.0)
    except ValueError as exc:
        assert "overlap_seconds must be smaller than chunk_seconds" in str(exc)
    else:
        raise AssertionError("Expected tiny chunks to be rejected")


def test_find_base_transcript_path_only_for_trailing_single_digit() -> None:
    module = load_module()
    output_dir = Path("/tmp/transcripts")

    assert (
        module.find_base_transcript_path(output_dir, "2025-08-23 Debanshu Bhaumik 4")
        == output_dir / "2025-08-23 Debanshu Bhaumik.md"
    )
    assert module.find_base_transcript_path(output_dir, "2026-01-13 Sandeep Bhat 12") is None
    assert module.find_base_transcript_path(output_dir, "2025-09-10 VIA Talks") is None


def test_build_chunk_user_prompt_appends_part_context() -> None:
    module = load_module()

    prompt = module.build_chunk_user_prompt("Focus on action items", chunk_index=2, chunk_count=4)

    assert prompt.startswith("Focus on action items\n\n")
    assert "part 2/4 of a longer recording" in prompt


def test_script_processes_missing_transcripts_and_skips_existing(tmp_path: Path) -> None:
    script_path = Path(__file__).resolve().parents[1] / "transcribe_calls.py"
    input_dir = tmp_path / "calls"
    output_dir = tmp_path / "transcripts"
    package_root = tmp_path / "pydeps"
    bin_dir = tmp_path / "bin"
    prompt_file = tmp_path / "prompt.md"
    log_path = tmp_path / "genai.log"
    prices_path = tmp_path / "google-prices.json"

    input_dir.mkdir()
    output_dir.mkdir()

    for name in ("call-a.opus", "call-b.opus", "call-c.wav"):
        (input_dir / name).write_bytes(b"fake audio")

    (output_dir / "call-b.md").write_text(
        "# call-b\n\n## Transcript\n\nExisting transcript\n",
        encoding="utf-8",
    )
    (output_dir / "call-c.md").write_text(
        "# call-c\n\n## Notes\n\nNeeds transcript\n",
        encoding="utf-8",
    )
    prompt_file.write_text(
        textwrap.dedent(
            """
            Intro text

            ```markdown
            Use this exact prompt
            ```
            """
        ),
        encoding="utf-8",
    )

    write_fake_google_genai(package_root)
    write_fake_ffmpeg_tools(bin_dir)
    write_fake_google_prices(prices_path)
    (tmp_path / ".env").write_text("GEMINI_API_KEY=test-key-from-dotenv\n", encoding="utf-8")

    env = os.environ.copy()
    env["PYTHONPATH"] = f"{package_root}:{env.get('PYTHONPATH', '')}".rstrip(":")
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["FAKE_GENAI_LOG"] = str(log_path)
    env["FAKE_FFPROBE_DURATION"] = "60"
    env["TRANSCRIBE_CALLS_PRICES_URL"] = prices_path.as_uri()
    env.pop("GEMINI_API_KEY", None)

    first = run_script(script_path, input_dir, output_dir, prompt_file, env=env, cwd=tmp_path)
    assert first.returncode == 0, first.stderr
    assert "[2/3] skip call-b.opus -> call-b.md" not in first.stdout
    assert "existing file missing transcript section" in first.stdout
    assert "tokens=150 cost=$0.000800 total_cost=$0.001600" in first.stdout

    log_text = log_path.read_text(encoding="utf-8")
    assert "APIKEY\ttest-key-from-dotenv" in log_text
    assert f"AUDIO\t{input_dir / 'call-a.opus'}" in log_text
    assert f"AUDIO\t{input_dir / 'call-c.wav'}" in log_text
    assert "SYSTEM_PROMPT\tUse this exact prompt" in log_text
    assert "USER_PROMPT\t" not in log_text

    call_a = (output_dir / "call-a.md").read_text(encoding="utf-8")
    call_b = (output_dir / "call-b.md").read_text(encoding="utf-8")
    call_c = (output_dir / "call-c.md").read_text(encoding="utf-8")

    assert call_a.startswith("---\ntags:\ngoal:\nkind candor:\neffectiveness:\nprompt: |-\n  Use this exact prompt\n---\n\n# call-a\n")
    assert "## Transcript\n\n**Speaker**: [00:01] Transcript for call-a.opus line 1" in call_a
    assert "prompt: |-\n  Use this exact prompt" in call_b
    assert call_b.endswith("# call-b\n\n## Transcript\n\nExisting transcript\n")
    assert "## Notes\n\nNeeds transcript" in call_c
    assert "## Transcript\n\n**Speaker**: [00:01] Transcript for call-c.wav line 1" in call_c

    second = run_script(script_path, input_dir, output_dir, prompt_file, env=env, cwd=tmp_path)
    assert second.returncode == 0, second.stderr
    assert log_path.read_text(encoding="utf-8") == log_text
    assert second.stdout.strip() == "created=0 updated=0 skipped=3 errors=0"


def test_script_skips_trailing_digit_audio_when_base_note_has_transcript(tmp_path: Path) -> None:
    script_path = Path(__file__).resolve().parents[1] / "transcribe_calls.py"
    input_dir = tmp_path / "calls"
    output_dir = tmp_path / "transcripts"
    prompt_file = tmp_path / "prompt.md"

    input_dir.mkdir()
    output_dir.mkdir()
    (input_dir / "2025-08-23 Debanshu Bhaumik 4.opus").write_bytes(b"audio")
    (output_dir / "2025-08-23 Debanshu Bhaumik.md").write_text(
        "# 2025-08-23 Debanshu Bhaumik\n\n## Transcript\n\nAlready transcribed\n",
        encoding="utf-8",
    )
    prompt_file.write_text("Prompt text", encoding="utf-8")

    env = os.environ.copy()
    env.pop("GEMINI_API_KEY", None)

    result = run_script(script_path, input_dir, output_dir, prompt_file, env=env, cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "created=0 updated=0 skipped=1 errors=0"
    assert not (output_dir / "2025-08-23 Debanshu Bhaumik 4.md").exists()


def test_script_transcribes_trailing_digit_audio_normally_when_base_note_lacks_transcript(
    tmp_path: Path,
) -> None:
    script_path = Path(__file__).resolve().parents[1] / "transcribe_calls.py"
    input_dir = tmp_path / "calls"
    output_dir = tmp_path / "transcripts"
    package_root = tmp_path / "pydeps"
    bin_dir = tmp_path / "bin"
    prompt_file = tmp_path / "prompt.md"
    log_path = tmp_path / "genai.log"
    prices_path = tmp_path / "google-prices.json"

    input_dir.mkdir()
    output_dir.mkdir()
    (input_dir / "2026-01-13 Sandeep Bhat 1.opus").write_bytes(b"audio")
    base_note = "# 2026-01-13 Sandeep Bhat\n\n## Notes\n\nNeeds transcript elsewhere\n"
    (output_dir / "2026-01-13 Sandeep Bhat.md").write_text(base_note, encoding="utf-8")
    prompt_file.write_text("Prompt text", encoding="utf-8")

    write_fake_google_genai(package_root)
    write_fake_ffmpeg_tools(bin_dir)
    write_fake_google_prices(prices_path)
    (tmp_path / ".env").write_text("GEMINI_API_KEY=test-key-from-dotenv\n", encoding="utf-8")

    env = os.environ.copy()
    env["PYTHONPATH"] = f"{package_root}:{env.get('PYTHONPATH', '')}".rstrip(":")
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["FAKE_GENAI_LOG"] = str(log_path)
    env["FAKE_FFPROBE_DURATION"] = "60"
    env["TRANSCRIBE_CALLS_PRICES_URL"] = prices_path.as_uri()
    env.pop("GEMINI_API_KEY", None)

    result = run_script(script_path, input_dir, output_dir, prompt_file, env=env, cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert (
        "[1/1] create 2026-01-13 Sandeep Bhat 1.opus -> 2026-01-13 Sandeep Bhat 1.md"
        in result.stdout
    )
    assert "existing file missing transcript section" not in result.stdout
    assert "tokens=150 cost=$0.000800 total_cost=$0.000800" in result.stdout
    assert (output_dir / "2026-01-13 Sandeep Bhat.md").read_text(encoding="utf-8") == base_note
    numbered_note = (output_dir / "2026-01-13 Sandeep Bhat 1.md").read_text(encoding="utf-8")
    assert "## Transcript\n\n**Speaker**: [00:01] Transcript for 2026-01-13 Sandeep Bhat 1.opus line 1" in numbered_note
    assert f"AUDIO\t{input_dir / '2026-01-13 Sandeep Bhat 1.opus'}" in log_path.read_text(encoding="utf-8")


def test_script_rejects_duplicate_audio_stems(tmp_path: Path) -> None:
    script_path = Path(__file__).resolve().parents[1] / "transcribe_calls.py"
    input_dir = tmp_path / "calls"
    output_dir = tmp_path / "transcripts"
    prompt_file = tmp_path / "prompt.md"

    input_dir.mkdir()
    output_dir.mkdir()
    (input_dir / "call.opus").write_bytes(b"one")
    (input_dir / "call.wav").write_bytes(b"two")
    prompt_file.write_text("Prompt text", encoding="utf-8")

    result = run_script(script_path, input_dir, output_dir, prompt_file)

    assert result.returncode != 0
    assert "Duplicate audio basenames would collide in output: call" in (result.stderr + result.stdout)


def test_script_reports_invalid_existing_markdown(tmp_path: Path) -> None:
    script_path = Path(__file__).resolve().parents[1] / "transcribe_calls.py"
    input_dir = tmp_path / "calls"
    output_dir = tmp_path / "transcripts"
    prompt_file = tmp_path / "prompt.md"

    input_dir.mkdir()
    output_dir.mkdir()

    (input_dir / "call.opus").write_bytes(b"audio")
    (output_dir / "call.md").write_bytes(b"\xff\xfe")
    prompt_file.write_text("Prompt text", encoding="utf-8")

    result = run_script(script_path, input_dir, output_dir, prompt_file)

    assert result.returncode == 1
    assert "failed to read existing Markdown" in result.stderr


def test_script_reports_duplicate_transcript_sections(tmp_path: Path) -> None:
    script_path = Path(__file__).resolve().parents[1] / "transcribe_calls.py"
    input_dir = tmp_path / "calls"
    output_dir = tmp_path / "transcripts"
    prompt_file = tmp_path / "prompt.md"

    input_dir.mkdir()
    output_dir.mkdir()

    (input_dir / "call.opus").write_bytes(b"audio")
    (output_dir / "call.md").write_text(
        "# call\n\n## Transcript\n\nFirst\n\n## Notes\n\nKeep\n\n## Transcript\n\nSecond\n",
        encoding="utf-8",
    )
    prompt_file.write_text("Prompt text", encoding="utf-8")

    result = run_script(script_path, input_dir, output_dir, prompt_file)

    assert result.returncode == 1
    assert "multiple ## Transcript sections" in result.stderr


def test_script_requires_gemini_api_key_when_transcription_needed(tmp_path: Path) -> None:
    script_path = Path(__file__).resolve().parents[1] / "transcribe_calls.py"
    input_dir = tmp_path / "calls"
    output_dir = tmp_path / "transcripts"
    prompt_file = tmp_path / "prompt.md"

    input_dir.mkdir()
    output_dir.mkdir()
    (input_dir / "call.opus").write_bytes(b"audio")
    prompt_file.write_text("Prompt text", encoding="utf-8")

    env = os.environ.copy()
    env.pop("GEMINI_API_KEY", None)

    result = run_script(script_path, input_dir, output_dir, prompt_file, env=env, cwd=tmp_path)

    assert result.returncode == 1
    assert "GEMINI_API_KEY is not set" in result.stderr


def test_script_filters_input_files_with_glob(tmp_path: Path) -> None:
    script_path = Path(__file__).resolve().parents[1] / "transcribe_calls.py"
    input_dir = tmp_path / "calls"
    output_dir = tmp_path / "transcripts"
    package_root = tmp_path / "pydeps"
    bin_dir = tmp_path / "bin"
    prompt_file = tmp_path / "prompt.md"
    log_path = tmp_path / "genai.log"
    prices_path = tmp_path / "google-prices.json"

    input_dir.mkdir()
    output_dir.mkdir()
    for name in ("call-a.opus", "call-b.wav", "notes.txt"):
        (input_dir / name).write_bytes(b"audio")

    prompt_file.write_text("Prompt text", encoding="utf-8")
    write_fake_google_genai(package_root)
    write_fake_ffmpeg_tools(bin_dir)
    write_fake_google_prices(prices_path)
    (tmp_path / ".env").write_text("GEMINI_API_KEY=test-key-from-dotenv\n", encoding="utf-8")

    env = os.environ.copy()
    env["PYTHONPATH"] = f"{package_root}:{env.get('PYTHONPATH', '')}".rstrip(":")
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["FAKE_GENAI_LOG"] = str(log_path)
    env["FAKE_FFPROBE_DURATION"] = "60"
    env["TRANSCRIBE_CALLS_PRICES_URL"] = prices_path.as_uri()
    env.pop("GEMINI_API_KEY", None)

    result = run_script(
        script_path,
        input_dir,
        output_dir,
        prompt_file,
        "--glob",
        "*.opus",
        env=env,
        cwd=tmp_path,
    )

    assert result.returncode == 0, result.stderr
    assert (output_dir / "call-a.md").exists()
    assert not (output_dir / "call-b.md").exists()
    log_text = log_path.read_text(encoding="utf-8")
    assert f"AUDIO\t{input_dir / 'call-a.opus'}" in log_text
    assert f"AUDIO\t{input_dir / 'call-b.wav'}" not in log_text


def test_script_sends_user_prompt_with_small_audio_file(tmp_path: Path) -> None:
    script_path = Path(__file__).resolve().parents[1] / "transcribe_calls.py"
    input_dir = tmp_path / "calls"
    output_dir = tmp_path / "transcripts"
    package_root = tmp_path / "pydeps"
    bin_dir = tmp_path / "bin"
    prompt_file = tmp_path / "prompt.md"
    log_path = tmp_path / "genai.log"
    prices_path = tmp_path / "google-prices.json"

    input_dir.mkdir()
    output_dir.mkdir()
    (input_dir / "test.opus").write_bytes(
        (Path(__file__).resolve().parents[1] / "tests" / "test.opus").read_bytes()
    )
    prompt_file.write_text("System prompt text", encoding="utf-8")

    write_fake_google_genai(package_root)
    write_fake_ffmpeg_tools(bin_dir)
    write_fake_google_prices(prices_path)
    (tmp_path / ".env").write_text("GEMINI_API_KEY=test-key-from-dotenv\n", encoding="utf-8")

    env = os.environ.copy()
    env["PYTHONPATH"] = f"{package_root}:{env.get('PYTHONPATH', '')}".rstrip(":")
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["FAKE_GENAI_LOG"] = str(log_path)
    env["FAKE_FFPROBE_DURATION"] = "12"
    env["TRANSCRIBE_CALLS_PRICES_URL"] = prices_path.as_uri()
    env.pop("GEMINI_API_KEY", None)

    result = run_script(
        script_path,
        input_dir,
        output_dir,
        prompt_file,
        "--prompt",
        "Focus on action items",
        env=env,
        cwd=tmp_path,
    )

    assert result.returncode == 0, result.stderr
    transcript = (output_dir / "test.md").read_text(encoding="utf-8")
    assert "Transcript for test.opus" in transcript
    assert "prompt: |-" in transcript
    assert "  Focus on action items" in transcript

    log_text = log_path.read_text(encoding="utf-8")
    assert f"AUDIO\t{input_dir / 'test.opus'}" in log_text
    assert "SYSTEM_PROMPT\tSystem prompt text" in log_text
    assert "USER_PROMPT\tFocus on action items" in log_text
    assert "tokens=150 cost=$0.000800 total_cost=$0.000800" in result.stdout


def test_script_backfills_prompt_metadata_without_transcribing(tmp_path: Path) -> None:
    script_path = Path(__file__).resolve().parents[1] / "transcribe_calls.py"
    input_dir = tmp_path / "calls"
    output_dir = tmp_path / "transcripts"
    package_root = tmp_path / "pydeps"
    bin_dir = tmp_path / "bin"
    prompt_file = tmp_path / "prompt.md"
    log_path = tmp_path / "genai.log"

    input_dir.mkdir()
    output_dir.mkdir()
    (input_dir / "call.opus").write_bytes(b"audio")
    (output_dir / "call.md").write_text(
        "# call\n\n## Transcript\n\n**Speaker**: [00:01] line 1\n**Speaker**: [00:02] line 2\n**Speaker**: [00:03] line 3\n**Speaker**: [00:04] line 4\n**Speaker**: [00:05] line 5\n",
        encoding="utf-8",
    )
    prompt_file.write_text("System prompt text", encoding="utf-8")

    write_fake_google_genai(package_root)
    write_fake_ffmpeg_tools(bin_dir)

    env = os.environ.copy()
    env["PYTHONPATH"] = f"{package_root}:{env.get('PYTHONPATH', '')}".rstrip(":")
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["FAKE_GENAI_LOG"] = str(log_path)
    env["FAKE_FFPROBE_DURATION"] = "12"
    env.pop("GEMINI_API_KEY", None)

    result = run_script(script_path, input_dir, output_dir, prompt_file, env=env, cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert "[1/1] update metadata call.opus -> call.md" in result.stdout
    transcript = (output_dir / "call.md").read_text(encoding="utf-8")
    assert "prompt: |-" in transcript
    assert "  System prompt text" in transcript
    assert not log_path.exists()


def test_script_chunks_long_audio_and_joins_chunk_transcripts(tmp_path: Path) -> None:
    script_path = Path(__file__).resolve().parents[1] / "transcribe_calls.py"
    input_dir = tmp_path / "calls"
    output_dir = tmp_path / "transcripts"
    package_root = tmp_path / "pydeps"
    bin_dir = tmp_path / "bin"
    prompt_file = tmp_path / "prompt.md"
    log_path = tmp_path / "genai.log"
    ffmpeg_log_path = tmp_path / "ffmpeg.log"
    prices_path = tmp_path / "google-prices.json"

    input_dir.mkdir()
    output_dir.mkdir()
    (input_dir / "long.opus").write_bytes(b"audio")
    prompt_file.write_text("Prompt text", encoding="utf-8")

    write_fake_google_genai(package_root)
    write_fake_ffmpeg_tools(bin_dir)
    write_fake_google_prices(prices_path)
    (tmp_path / ".env").write_text("GEMINI_API_KEY=test-key-from-dotenv\n", encoding="utf-8")

    env = os.environ.copy()
    env["PYTHONPATH"] = f"{package_root}:{env.get('PYTHONPATH', '')}".rstrip(":")
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["FAKE_GENAI_LOG"] = str(log_path)
    env["FAKE_FFMPEG_LOG"] = str(ffmpeg_log_path)
    env["FAKE_FFPROBE_DURATION"] = "3900"
    env["TRANSCRIBE_CALLS_PRICES_URL"] = prices_path.as_uri()
    env.pop("GEMINI_API_KEY", None)

    result = run_script(
        script_path,
        input_dir,
        output_dir,
        prompt_file,
        "--chunk",
        "30",
        env=env,
        cwd=tmp_path,
    )

    assert result.returncode == 0, result.stderr
    assert "tokens=450 cost=$0.002400 total_cost=$0.002400" in result.stdout
    transcript = (output_dir / "long.md").read_text(encoding="utf-8")
    assert "Transcript for long.part001.opus line 1" in transcript
    assert "\n\n---\n\n" in transcript
    assert "Transcript for long.part002.opus line 1" in transcript
    assert "Transcript for long.part003.opus line 1" in transcript

    ffmpeg_log = ffmpeg_log_path.read_text(encoding="utf-8").splitlines()
    assert len(ffmpeg_log) == 3
    assert "-ss 0.000 -t 1500.000 -i" in ffmpeg_log[0]
    assert "-ss 1499.000 -t 1501.000 -i" in ffmpeg_log[1]
    assert "-ss 2999.000 -t 901.000 -i" in ffmpeg_log[2]

    genai_log = log_path.read_text(encoding="utf-8")
    assert "AUDIO\t" in genai_log
    assert "long.part001.opus" in genai_log
    assert "long.part002.opus" in genai_log
    assert "long.part003.opus" in genai_log
    assert "USER_PROMPT\tThis audio is part 1/3 of a longer recording." in genai_log
    assert "USER_PROMPT\tThis audio is part 2/3 of a longer recording." in genai_log
    assert "USER_PROMPT\tThis audio is part 3/3 of a longer recording." in genai_log


def test_script_warns_when_chunk_response_does_not_look_like_transcript(tmp_path: Path) -> None:
    script_path = Path(__file__).resolve().parents[1] / "transcribe_calls.py"
    input_dir = tmp_path / "calls"
    output_dir = tmp_path / "transcripts"
    package_root = tmp_path / "pydeps"
    bin_dir = tmp_path / "bin"
    prompt_file = tmp_path / "prompt.md"
    log_path = tmp_path / "genai.log"
    prices_path = tmp_path / "google-prices.json"

    input_dir.mkdir()
    output_dir.mkdir()
    (input_dir / "long.opus").write_bytes(b"audio")
    prompt_file.write_text("Prompt text", encoding="utf-8")

    write_fake_google_genai(package_root)
    write_fake_ffmpeg_tools(bin_dir)
    write_fake_google_prices(prices_path)
    (tmp_path / ".env").write_text("GEMINI_API_KEY=test-key-from-dotenv\n", encoding="utf-8")

    env = os.environ.copy()
    env["PYTHONPATH"] = f"{package_root}:{env.get('PYTHONPATH', '')}".rstrip(":")
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["FAKE_GENAI_LOG"] = str(log_path)
    env["FAKE_FFPROBE_DURATION"] = "3900"
    env["TRANSCRIBE_CALLS_PRICES_URL"] = prices_path.as_uri()
    env["FAKE_GENAI_RESPONSE_BY_FILE"] = json.dumps(
        {"long.part002.opus": "It appears that you forgot to attach the audio file."}
    )
    env.pop("GEMINI_API_KEY", None)

    result = run_script(
        script_path,
        input_dir,
        output_dir,
        prompt_file,
        "--chunk",
        "30",
        env=env,
        cwd=tmp_path,
    )

    assert result.returncode == 0, result.stderr
    assert "WARNING long.opus: section 2/3 matched only 0 transcript-format lines" in result.stderr
    assert "Patch command for long.md section 2:" in result.stderr
    assert "--patch-section 2" in result.stderr
    assert "Transcript for long.part001.opus line 1" in (output_dir / "long.md").read_text(encoding="utf-8")
    assert "It appears that you forgot to attach the audio file." in (output_dir / "long.md").read_text(
        encoding="utf-8"
    )


def test_script_patch_section_retranscribes_only_requested_chunk(tmp_path: Path) -> None:
    script_path = Path(__file__).resolve().parents[1] / "transcribe_calls.py"
    input_dir = tmp_path / "calls"
    output_dir = tmp_path / "transcripts"
    package_root = tmp_path / "pydeps"
    bin_dir = tmp_path / "bin"
    prompt_file = tmp_path / "prompt.md"
    log_path = tmp_path / "genai.log"
    ffmpeg_log_path = tmp_path / "ffmpeg.log"
    prices_path = tmp_path / "google-prices.json"

    input_dir.mkdir()
    output_dir.mkdir()
    (input_dir / "long.opus").write_bytes(b"audio")
    (output_dir / "long.md").write_text(
        "---\n"
        "prompt: |-\n"
        "  Stored patch prompt\n"
        "---\n\n"
        "# long\n\n## Transcript\n\nfirst chunk\n\n---\n\nsecond chunk\n\n---\n\nthird chunk\n",
        encoding="utf-8",
    )
    prompt_file.write_text("Prompt text", encoding="utf-8")

    write_fake_google_genai(package_root)
    write_fake_ffmpeg_tools(bin_dir)
    write_fake_google_prices(prices_path)
    (tmp_path / ".env").write_text("GEMINI_API_KEY=test-key-from-dotenv\n", encoding="utf-8")

    env = os.environ.copy()
    env["PYTHONPATH"] = f"{package_root}:{env.get('PYTHONPATH', '')}".rstrip(":")
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["FAKE_GENAI_LOG"] = str(log_path)
    env["FAKE_FFMPEG_LOG"] = str(ffmpeg_log_path)
    env["FAKE_FFPROBE_DURATION"] = "3900"
    env["TRANSCRIBE_CALLS_PRICES_URL"] = prices_path.as_uri()
    env["FAKE_GENAI_RESPONSE_BY_FILE"] = json.dumps(
        {
            "long.part002.opus": "\n".join(
                f"**Speaker**: [00:0{index}] patched line {index}"
                for index in range(1, 6)
            )
        }
    )
    env.pop("GEMINI_API_KEY", None)

    result = run_script(
        script_path,
        input_dir,
        output_dir,
        prompt_file,
        "--chunk",
        "30",
        "--patch-section",
        "2",
        env=env,
        cwd=tmp_path,
    )

    assert result.returncode == 0, result.stderr
    assert "[1/1] patch section 2 long.opus -> long.md" in result.stdout
    transcript = (output_dir / "long.md").read_text(encoding="utf-8")
    assert "first chunk\n\n---\n\n**Speaker**: [00:01] patched line 1" in transcript
    assert "third chunk" in transcript
    assert "prompt: |-\n  Stored patch prompt" in transcript
    ffmpeg_log = ffmpeg_log_path.read_text(encoding="utf-8").splitlines()
    assert len(ffmpeg_log) == 3
    genai_log = log_path.read_text(encoding="utf-8")
    assert "long.part001.opus" not in genai_log
    assert "long.part002.opus" in genai_log
    assert "long.part003.opus" not in genai_log
    assert "SYSTEM_PROMPT\tPrompt text" in genai_log
    assert "USER_PROMPT\tStored patch prompt" in genai_log


def test_script_patch_invalid_sections_retranscribes_all_bad_chunks(tmp_path: Path) -> None:
    script_path = Path(__file__).resolve().parents[1] / "transcribe_calls.py"
    input_dir = tmp_path / "calls"
    output_dir = tmp_path / "transcripts"
    package_root = tmp_path / "pydeps"
    bin_dir = tmp_path / "bin"
    prompt_file = tmp_path / "prompt.md"
    log_path = tmp_path / "genai.log"
    prices_path = tmp_path / "google-prices.json"

    input_dir.mkdir()
    output_dir.mkdir()
    (input_dir / "long.opus").write_bytes(b"audio")
    (output_dir / "long.md").write_text(
        "# long\n\n## Transcript\n\n"
        "**Speaker**: [00:01] first line\n"
        "**Speaker**: [00:02] first line\n"
        "**Speaker**: [00:03] first line\n"
        "**Speaker**: [00:04] first line\n"
        "**Speaker**: [00:05] first line\n"
        "\n\n---\n\n"
        "It appears that you forgot to attach the audio file.\n"
        "\n\n---\n\n"
        "It looks like you forgot to attach the raw transcript.\n",
        encoding="utf-8",
    )
    prompt_file.write_text("Prompt text", encoding="utf-8")

    write_fake_google_genai(package_root)
    write_fake_ffmpeg_tools(bin_dir)
    write_fake_google_prices(prices_path)
    (tmp_path / ".env").write_text("GEMINI_API_KEY=test-key-from-dotenv\n", encoding="utf-8")

    env = os.environ.copy()
    env["PYTHONPATH"] = f"{package_root}:{env.get('PYTHONPATH', '')}".rstrip(":")
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["FAKE_GENAI_LOG"] = str(log_path)
    env["FAKE_FFPROBE_DURATION"] = "3900"
    env["TRANSCRIBE_CALLS_PRICES_URL"] = prices_path.as_uri()
    env["FAKE_GENAI_RESPONSE_BY_FILE"] = json.dumps(
        {
            "long.part002.opus": "\n".join(
                f"**Speaker**: [00:0{index}] repaired second {index}"
                for index in range(1, 6)
            ),
            "long.part003.opus": "\n".join(
                f"**Speaker**: [00:0{index}] repaired third {index}"
                for index in range(1, 6)
            ),
        }
    )
    env.pop("GEMINI_API_KEY", None)

    result = run_script(
        script_path,
        input_dir,
        output_dir,
        prompt_file,
        "--chunk",
        "30",
        "--patch-invalid-sections",
        env=env,
        cwd=tmp_path,
    )

    assert result.returncode == 0, result.stderr
    assert "[1/1] patch invalid sections 2,3 long.opus -> long.md" in result.stdout
    transcript = (output_dir / "long.md").read_text(encoding="utf-8")
    assert "repaired second 1" in transcript
    assert "repaired third 1" in transcript
    assert "It appears that you forgot to attach the audio file." not in transcript
    assert "It looks like you forgot to attach the raw transcript." not in transcript
    genai_log = log_path.read_text(encoding="utf-8")
    assert "long.part001.opus" not in genai_log
    assert "long.part002.opus" in genai_log
    assert "long.part003.opus" in genai_log


def test_script_dry_run_reports_duration_and_chunks_without_side_effects(tmp_path: Path) -> None:
    script_path = Path(__file__).resolve().parents[1] / "transcribe_calls.py"
    input_dir = tmp_path / "calls"
    output_dir = tmp_path / "transcripts"
    package_root = tmp_path / "pydeps"
    bin_dir = tmp_path / "bin"
    prompt_file = tmp_path / "prompt.md"
    ffmpeg_log_path = tmp_path / "ffmpeg.log"
    genai_log_path = tmp_path / "genai.log"
    existing_note = "# long\n\n## Notes\n\nNeeds transcript\n"

    input_dir.mkdir()
    output_dir.mkdir()
    (input_dir / "long.opus").write_bytes(b"audio")
    (output_dir / "long.md").write_text(existing_note, encoding="utf-8")
    prompt_file.write_text("Prompt text", encoding="utf-8")

    write_fake_google_genai(package_root)
    write_fake_ffmpeg_tools(bin_dir)

    env = os.environ.copy()
    env["PYTHONPATH"] = f"{package_root}:{env.get('PYTHONPATH', '')}".rstrip(":")
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["FAKE_FFMPEG_LOG"] = str(ffmpeg_log_path)
    env["FAKE_GENAI_LOG"] = str(genai_log_path)
    env["FAKE_FFPROBE_DURATION"] = "3900"
    env.pop("GEMINI_API_KEY", None)

    result = run_script(
        script_path,
        input_dir,
        output_dir,
        prompt_file,
        "--dry-run",
        "--chunk",
        "30",
        env=env,
        cwd=tmp_path,
    )

    assert result.returncode == 0, result.stderr
    assert "duration=3900.0s chunks=3" in result.stdout
    assert "existing file missing transcript section" in result.stdout
    assert result.stdout.strip().endswith("created=0 updated=0 skipped=0 errors=0")
    assert (output_dir / "long.md").read_text(encoding="utf-8") == existing_note
    assert not ffmpeg_log_path.exists()
    assert not genai_log_path.exists()


def test_script_rejects_chunk_size_at_or_below_overlap(tmp_path: Path) -> None:
    script_path = Path(__file__).resolve().parents[1] / "transcribe_calls.py"
    input_dir = tmp_path / "calls"
    output_dir = tmp_path / "transcripts"
    package_root = tmp_path / "pydeps"
    bin_dir = tmp_path / "bin"
    prompt_file = tmp_path / "prompt.md"
    prices_path = tmp_path / "google-prices.json"

    input_dir.mkdir()
    output_dir.mkdir()
    (input_dir / "tiny.opus").write_bytes(b"audio")
    prompt_file.write_text("Prompt text", encoding="utf-8")

    write_fake_google_genai(package_root)
    write_fake_ffmpeg_tools(bin_dir)
    write_fake_google_prices(prices_path)
    (tmp_path / ".env").write_text("GEMINI_API_KEY=test-key-from-dotenv\n", encoding="utf-8")

    env = os.environ.copy()
    env["PYTHONPATH"] = f"{package_root}:{env.get('PYTHONPATH', '')}".rstrip(":")
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["FAKE_FFPROBE_DURATION"] = "3900"
    env["TRANSCRIBE_CALLS_PRICES_URL"] = prices_path.as_uri()
    env.pop("GEMINI_API_KEY", None)

    result = run_script(
        script_path,
        input_dir,
        output_dir,
        prompt_file,
        "--chunk",
        "0.01",
        env=env,
        cwd=tmp_path,
    )

    assert result.returncode == 1
    assert "greater than 1/60 minute" in result.stderr
