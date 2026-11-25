#!/usr/bin/env -S uv run --script
"""Patch the Windows SSH bootstrap in the latest installed VS Code Remote SSH."""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

OLD = '''function getSshdParentPid {
	$currentPID = $PID
	while ($True) {
		$parentPID = (gcim win32_process | ? processid -eq $currentPID).parentprocessid
		if (!$parentPID) {
			"no sshd parent proc"
			exit 0
		}

		if ((gps -Id $parentPID).Name -eq 'sshd') {
			return $parentPID
		}

		$currentPID = $parentPID
	}
}'''
NEW = OLD.replace('$currentPID = $PID', '$currentPID = $PID\n\t$processes = gcim win32_process -Property ProcessId,ParentProcessId').replace('gcim win32_process | ?', '$processes | ?')
FUNCTION = re.compile(r'"function getSshdParentPid\s*\{(?:\\.|[^"\\])*"')


def patch(source: str) -> str:
    """Fail closed if Microsoft changes the function or bundle structure."""
    matches = list(FUNCTION.finditer(source))
    if len(matches) != 1:
        raise ValueError(f'Expected one getSshdParentPid function, found {len(matches)}')
    match = matches[0]
    body = json.loads(match[0])
    if body == NEW:
        return source
    if body != OLD:
        raise ValueError('Unrecognized function: review the new upstream code before patching')
    return source[:match.start()] + json.dumps(NEW) + source[match.end():]


def latest() -> Path:
    """Select the newest numeric extension version, not lexicographic order."""
    paths = Path.home().joinpath('.vscode/extensions').glob('ms-vscode-remote.remote-ssh-*')
    versions = [(tuple(map(int, m[1].split('.'))), p) for p in paths
                if p.is_dir() and (m := re.fullmatch(r'ms-vscode-remote\.remote-ssh-(\d+\.\d+\.\d+)(?:-[\w-]+)?', p.name))]
    if not versions:
        raise SystemExit('Remote SSH extension not found; pass its directory explicitly')
    return max(versions)[1]


def main(directory: Path) -> None:
    backup = Path.home() / '.cache/vscode-remote-ssh-patch' / directory.name
    files = [directory / 'out' / name for name in ('extension.js', 'resolver.js')]
    # Validate both bundles before modifying either. Stage on the same filesystem.
    with TemporaryDirectory(dir=directory / 'out') as temp:
        changes = []
        for file in files:
            original = file.read_bytes()
            updated = patch(original.decode('utf-8')).encode('utf-8')
            if updated == original:
                print(f'Already patched: {file.name}')
                continue
            saved = backup / file.name
            if saved.exists() and saved.read_bytes() != original:
                raise ValueError(f'Backup differs: {saved}; refusing to overwrite')
            staged = Path(temp) / file.name
            staged.write_bytes(updated)
            shutil.copymode(file, staged)
            subprocess.run(['node', '--check', str(staged)], check=True)
            changes.append((file, saved, staged))
        for file, saved, _ in changes:
            backup.mkdir(parents=True, exist_ok=True)
            if not saved.exists():
                shutil.copy2(file, saved)
        for file, _, staged in changes:
            os.replace(staged, file)
            print(f'Patched: {file}')
    if changes:
        print(f'Backups: {backup}\nRestart VS Code to activate.')


if __name__ == '__main__':
    if len(sys.argv) > 2:
        raise SystemExit(f'Usage: {sys.argv[0]} [extension-directory]')
    main(Path(sys.argv[1]).expanduser().resolve() if len(sys.argv) == 2 else latest())
