---
name: uv-uvx
description: Tips on using uv and uvx (Python build tools) effectively with GitHub, Torch, etc.
---

## Running from GitHub

You can run `uvx --from "git+https://github.com/owner/repo.git@main" your-tool` directly without cloning a repo.

You can specify a git repo as an inline script dependency directly in a `.py` file when running with `uv`

```python
# /// script
# dependencies = ["git+https://github.com/owner/repo.git"]
# ///
```

To import static assets, use `data-files` to install them into the environment and read them using `sys.prefix`:

```toml
# pyproject.toml
[build-system]
requires = ["setuptools>=69"]
build-backend = "setuptools.build_meta"

[project]
name = "your-project"
version = "0.1.0"
requires-python = ">=3.12"

# exposes the CLI entry point for your tool
[project.scripts]
your-tool = "main:main"

# packages the single root script
[tool.setuptools]
py-modules = ["main"]

# installs static.txt into the environment root
[tool.setuptools.data-files]
"." = ["static.txt"]
```

```python
# main.py
from pathlib import Path
import sys


def main():
    path = Path(sys.prefix) / "static.txt"
    print(path.read_text())


if __name__ == "__main__":
    main()
```

This is the smallest practical proof of concept, not the most robust packaging pattern. For larger projects, prefer a real package plus `importlib.resources`.

## Tips

- Adding a `[dependency-groups]` section to `pyproject.toml` with `dev = ["pytest"]` ensures that pytest is automatically installed by `uv` because [`dev` is a default group](https://docs.astral.sh/uv/concepts/projects/dependencies/#default-groups).
- `uv run --python 3.14 --isolated --with-editable '.[test]' pytest` runs pytest on a local project with a specific Python version.
- `uv run` supports `--extra` for extra packages
- `uv run` can run _any_ command, not just Python scripts, e.g. `uv run npx` or `uv run bash`. It's the same as `npx` or `bash` except it activates the venv and loads `.env`.
- `UV_TORCH_BACKEND=auto uv pip install torch torchvision torchaudio` installs the most appropriate PyTorch version.
- `uv` supports:
  - pylock.toml, the new lock file standard PEP 0751
  - --env-file multiple times, allowing layered secrets
  - --exclude-newer installs versions before a specific date
  - --overrides overrides versions a package specifies
  - --constraints limits the version of the package
