from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import sys

from skill_loader.manifest import ManifestError, Skill, load_manifest


PROJECT_DIRECTORY = Path(__file__).resolve().parent.parent


class UnsafeSkillError(RuntimeError):
    pass


def tree_digest(root: Path) -> str:
    if root.is_symlink() or not root.is_dir():
        raise UnsafeSkillError(f"Skill path must be a directory, not a symlink: {root}")
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix().encode()
        if path.is_symlink():
            target = path.readlink()
            resolved = (path.parent / target).resolve(strict=False)
            if not resolved.exists() or not _is_within(resolved, root.resolve()):
                raise UnsafeSkillError(f"Source symlink is unsafe: {path}")
            digest.update(b"L\0" + relative + b"\0" + os.fsencode(target))
        elif path.is_dir():
            digest.update(b"D\0" + relative)
        elif path.is_file():
            digest.update(b"F\0" + relative + b"\0")
            digest.update(path.read_bytes())
        else:
            raise UnsafeSkillError(f"Unsupported file type in skill: {path}")
    return digest.hexdigest()


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def configured_status(skill: Skill, repositories_directory: Path, active_directory: Path) -> str:
    source = repositories_directory / skill.repository_name / skill.path
    if not (repositories_directory / skill.repository_name).is_dir():
        return "missing"
    if not source.is_dir() or source.is_symlink():
        raise UnsafeSkillError(f"Configured skill directory is missing or unsafe: {source}")
    if not (source / "SKILL.md").is_file():
        raise UnsafeSkillError(f"Configured skill is missing SKILL.md: {source}")
    active = active_directory / skill.name
    if not active.exists() and not active.is_symlink():
        tree_digest(source)
        return "new"
    if not active.is_dir() or active.is_symlink():
        raise UnsafeSkillError(f"Active skill path must be a directory, not a symlink: {active}")
    return "unchanged" if tree_digest(source) == tree_digest(active) else "changed"


def orphan_lines(manifest_skill_names: set[str], active_directory: Path, agent_paths: tuple[Path, ...]) -> list[str]:
    lines: list[str] = []
    if active_directory.is_dir():
        for entry in sorted(active_directory.iterdir(), key=lambda item: item.name):
            if entry.name not in manifest_skill_names:
                lines.append(f"active/{entry.name}: orphan")
    active_root = active_directory.resolve(strict=False)
    for agent_path in agent_paths:
        if not agent_path.is_dir():
            continue
        for entry in sorted(agent_path.iterdir(), key=lambda item: item.name):
            if not entry.is_symlink() or entry.name in manifest_skill_names:
                continue
            target = entry.resolve(strict=False)
            if _is_within(target, active_root):
                lines.append(f"{entry}: orphan link")
    return lines


def main(arguments: list[str] | None = None) -> int:
    argparse.ArgumentParser(description="Report configured skill review status.").parse_args(arguments)
    config_file = PROJECT_DIRECTORY / "config.toml"
    if not config_file.is_file():
        print(f"Configuration file not found: {config_file}", file=sys.stderr)
        return 2
    try:
        manifest = load_manifest(config_file)
        repositories_directory = PROJECT_DIRECTORY / "repos"
        active_directory = PROJECT_DIRECTORY / "active"
        lines = [
            f"{skill.repository_name}/{skill.name}: {configured_status(skill, repositories_directory, active_directory)}"
            for skill in manifest.skills
        ]
        lines.extend(
            orphan_lines({skill.name for skill in manifest.skills}, active_directory, manifest.agent_paths)
        )
    except (ManifestError, UnsafeSkillError) as error:
        print(error, file=sys.stderr)
        return 2
    if lines:
        print(*lines, sep="\n")
    return 1 if any(not line.endswith(": unchanged") for line in lines) else 0


if __name__ == "__main__":
    raise SystemExit(main())
