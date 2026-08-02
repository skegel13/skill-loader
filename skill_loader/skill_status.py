from __future__ import annotations

import argparse
from dataclasses import dataclass
import difflib
import hashlib
import os
from pathlib import Path
import shutil
import sys
import tempfile

from skill_loader.manifest import ManifestError, Skill, load_manifest


PROJECT_DIRECTORY = Path(__file__).resolve().parent.parent


class UnsafeSkillError(RuntimeError):
    pass


@dataclass(frozen=True)
class Review:
    skill: Skill
    source: Path
    active: Path | None
    status: str


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _validate_tree(root: Path, *, label: str) -> None:
    if root.is_symlink() or not root.is_dir():
        raise UnsafeSkillError(f"{label} must be a directory, not a symlink: {root}")
    resolved_root = root.resolve()
    for path in root.rglob("*"):
        if path.is_symlink():
            target = path.readlink()
            resolved = (path.parent / target).resolve(strict=False)
            if not resolved.exists() or not _is_within(resolved, resolved_root):
                raise UnsafeSkillError(f"Source symlink is unsafe: {path}")
        elif not (path.is_dir() or path.is_file()):
            raise UnsafeSkillError(f"Unsupported file type in skill: {path}")


def tree_digest(root: Path) -> str:
    _validate_tree(root, label="Skill path")
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix().encode()
        mode = (path.lstat().st_mode & 0o7777).to_bytes(2, "big")
        if path.is_symlink():
            digest.update(b"L\0" + relative + b"\0" + mode + b"\0" + os.fsencode(path.readlink()))
        elif path.is_dir():
            digest.update(b"D\0" + relative + b"\0" + mode)
        else:
            digest.update(b"F\0" + relative + b"\0" + mode + b"\0" + path.read_bytes())
    return digest.hexdigest()


def _valid_skill_directory(path: Path, *, label: str) -> None:
    if path.is_symlink() or not path.is_dir():
        raise UnsafeSkillError(f"{label} must be a directory, not a symlink: {path}")
    skill_file = path / "SKILL.md"
    if not skill_file.is_file():
        raise UnsafeSkillError(f"Configured skill is missing SKILL.md: {path}")
    _validate_tree(path, label=label)


def inspect_skill(skill: Skill, repositories_directory: Path, active_directory: Path) -> Review:
    checkout = repositories_directory / skill.repository_name
    active = active_directory / skill.name
    if active.exists() or active.is_symlink():
        _valid_skill_directory(active, label="Active skill path")
    if not checkout.exists():
        if checkout.is_symlink():
            raise UnsafeSkillError(f"Repository checkout must not be a symlink: {checkout}")
        return Review(skill, checkout / skill.path, active if active.exists() else None, "missing")
    if checkout.is_symlink() or not checkout.is_dir():
        raise UnsafeSkillError(f"Repository checkout must be a directory, not a symlink: {checkout}")
    source = checkout / skill.path
    if not _is_within(source.resolve(strict=False), checkout.resolve()):
        raise UnsafeSkillError(f"Configured skill directory escapes repository checkout: {source}")
    _valid_skill_directory(source, label="Configured skill directory")
    if not active.exists() and not active.is_symlink():
        tree_digest(source)
        return Review(skill, source, None, "new")
    _valid_skill_directory(active, label="Active skill path")
    return Review(skill, source, active, "unchanged" if tree_digest(source) == tree_digest(active) else "changed")


def _readable_lines(path: Path) -> list[str] | None:
    data = path.read_bytes()
    if b"\0" in data:
        return None
    try:
        return data.decode("utf-8").splitlines(keepends=True)
    except UnicodeDecodeError:
        return None


def _tree_entries(root: Path | None) -> dict[str, Path]:
    if root is None:
        return {}
    return {path.relative_to(root).as_posix(): path for path in root.rglob("*")}


def _entry_lines(path: Path | None) -> list[str] | None:
    if path is None:
        return []
    mode = path.lstat().st_mode & 0o7777
    if path.is_symlink():
        return [f"mode {mode:o}\n", f"symlink -> {path.readlink()}\n"]
    if path.is_dir():
        return [f"mode {mode:o}\n", "directory\n"]
    lines = _readable_lines(path)
    return None if lines is None else [f"mode {mode:o}\n", *lines]


def review_diff(review: Review) -> str:
    active_entries = _tree_entries(review.active)
    source_entries = _tree_entries(review.source)
    output: list[str] = []
    active_prefix = f"active/{review.skill.name}"
    source_prefix = f"repos/{review.skill.repository_name}/{review.skill.path.as_posix()}"
    for relative in sorted(set(active_entries) | set(source_entries)):
        old, new = active_entries.get(relative), source_entries.get(relative)
        old_name, new_name = f"{active_prefix}/{relative}", f"{source_prefix}/{relative}"
        old_lines, new_lines = _entry_lines(old), _entry_lines(new)
        if old_lines is None or new_lines is None:
            if old is not None and new is not None and old.is_file() and new.is_file() and old.read_bytes() == new.read_bytes() and (old.lstat().st_mode & 0o7777) == (new.lstat().st_mode & 0o7777):
                continue
            output.append(f"Binary or type-changing entry: {old_name} -> {new_name}\n")
            continue
        if old_lines != new_lines:
            output.extend(difflib.unified_diff(old_lines, new_lines, fromfile=old_name, tofile=new_name))
    return "".join(output)


def _managed_link(path: Path, active_skill: Path) -> bool:
    return path.is_symlink() and path.resolve(strict=False) == active_skill.resolve(strict=False)


def validate_agent_targets(review: Review, agent_paths: tuple[Path, ...], active_directory: Path) -> None:
    for agent_path in agent_paths:
        _validate_agent_path(agent_path)
        target = agent_path / review.skill.name
        if (target.exists() or target.is_symlink()) and not _managed_link(target, active_directory / review.skill.name):
            raise UnsafeSkillError(f"Unmanaged agent target conflicts: {target}")


def _validate_agent_path(agent_path: Path) -> None:
    if agent_path.is_symlink():
        raise UnsafeSkillError(f"Agent path must be a directory, not a symlink: {agent_path}")
    try:
        relative = agent_path.relative_to(PROJECT_DIRECTORY)
    except ValueError:
        relative = None
    if relative is not None:
        ancestor = PROJECT_DIRECTORY
        for part in relative.parts[:-1]:
            ancestor /= part
            if ancestor.is_symlink():
                raise UnsafeSkillError(f"Agent path must not have a symlinked ancestor: {agent_path}")
    if agent_path.exists() and not agent_path.is_dir():
        raise UnsafeSkillError(f"Agent path must be a directory, not a symlink: {agent_path}")


def _remove_tree(path: Path) -> None:
    if path.is_symlink() or not path.is_dir():
        raise UnsafeSkillError(f"Expected managed directory: {path}")
    shutil.rmtree(path)


def promote(review: Review, active_directory: Path, agent_paths: tuple[Path, ...]) -> None:
    validate_agent_targets(review, agent_paths, active_directory)
    if active_directory.exists() and (active_directory.is_symlink() or not active_directory.is_dir()):
        raise UnsafeSkillError(f"Active directory must be a directory, not a symlink: {active_directory}")
    active_directory.mkdir(parents=True, exist_ok=True)
    staging_root = Path(tempfile.mkdtemp(prefix=f".{review.skill.name}.staging-", dir=active_directory))
    staged_skill = staging_root / review.skill.name
    link_changes: list[tuple[Path, Path | None]] = []
    temporary_links: list[Path] = []
    active_backup: Path | None = None
    active_moved = False
    active_swapped = False
    active_target = active_directory / review.skill.name
    try:
        shutil.copytree(review.source, staged_skill, symlinks=True, copy_function=shutil.copy2)
        _valid_skill_directory(staged_skill, label="Staged skill path")
        planned_links: list[tuple[Path, Path]] = []
        for agent_path in agent_paths:
            agent_path.mkdir(parents=True, exist_ok=True)
            target = agent_path / review.skill.name
            temporary = agent_path / f".{review.skill.name}.new-{next(tempfile._get_candidate_names())}"
            temporary.symlink_to(os.path.relpath(active_target, agent_path))
            temporary_links.append(temporary)
            planned_links.append((target, temporary))
        if active_target.exists() or active_target.is_symlink():
            active_backup = active_directory / f".{review.skill.name}.previous-{next(tempfile._get_candidate_names())}"
            os.replace(active_target, active_backup)
            active_moved = True
        os.replace(staged_skill, active_target)
        active_swapped = True
        for target, temporary in planned_links:
            backup: Path | None = None
            if target.exists() or target.is_symlink():
                backup = target.parent / f".{target.name}.previous-{next(tempfile._get_candidate_names())}"
                os.replace(target, backup)
            link_changes.append((target, backup))
            os.replace(temporary, target)
    except Exception:
        for target, backup in reversed(link_changes):
            if target.exists() or target.is_symlink():
                target.unlink()
            if backup is not None and (backup.exists() or backup.is_symlink()):
                os.replace(backup, target)
        for temporary in temporary_links:
            if temporary.exists() or temporary.is_symlink():
                temporary.unlink()
        if active_swapped:
            if active_target.exists() or active_target.is_symlink():
                _remove_tree(active_target)
        if active_moved and active_backup is not None and (active_backup.exists() or active_backup.is_symlink()):
            os.replace(active_backup, active_target)
        raise
    finally:
        if staging_root.exists():
            shutil.rmtree(staging_root, ignore_errors=True)
    if active_backup is not None and active_backup.exists():
        try:
            _remove_tree(active_backup)
        except OSError:
            pass
    for _, backup in link_changes:
        if backup is not None and (backup.exists() or backup.is_symlink()):
            backup.unlink()


def orphan_skills(manifest_names: set[str], active_directory: Path) -> list[Path]:
    if not active_directory.is_dir() or active_directory.is_symlink():
        return []
    return [
        path for path in sorted(active_directory.iterdir(), key=lambda item: item.name)
        if path.name not in manifest_names and not path.name.startswith(".") and path.is_dir()
        and not path.is_symlink() and (path / "SKILL.md").is_file() and not (path / "SKILL.md").is_symlink()
    ]


def orphan_links(manifest_names: set[str], active_directory: Path, agent_paths: tuple[Path, ...]) -> list[Path]:
    links: list[Path] = []
    for agent_path in agent_paths:
        if not agent_path.is_dir():
            continue
        for entry in sorted(agent_path.iterdir(), key=lambda item: item.name):
            if entry.name not in manifest_names and _managed_link(entry, active_directory / entry.name):
                links.append(entry)
    return links


def remove_orphan(orphan: Path, links: list[Path]) -> None:
    backup = orphan.parent / f".{orphan.name}.orphan-{next(tempfile._get_candidate_names())}"
    link_backups: list[tuple[Path, Path]] = []
    try:
        os.replace(orphan, backup)
        for link in links:
            link_backup = link.parent / f".{link.name}.orphan-{next(tempfile._get_candidate_names())}"
            os.replace(link, link_backup)
            link_backups.append((link, link_backup))
    except Exception:
        for link, link_backup in reversed(link_backups):
            if link_backup.exists() or link_backup.is_symlink():
                os.replace(link_backup, link)
        if backup.exists() or backup.is_symlink():
            os.replace(backup, orphan)
        raise
    try:
        _remove_tree(backup)
    except OSError:
        pass
    for _, link_backup in link_backups:
        link_backup.unlink()


def _prompt(prompt: str, allowed: set[str]) -> str:
    response = input(prompt).strip().lower()
    if response not in allowed:
        raise UnsafeSkillError(f"Expected one of: {', '.join(sorted(allowed))}")
    return response


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Review and activate configured skills.")
    parser.add_argument("--dry-run", action="store_true", help="Show reviews without prompting or changing files.")
    options = parser.parse_args(arguments)
    config_file = PROJECT_DIRECTORY / "config.toml"
    if not config_file.is_file():
        print(f"Configuration file not found: {config_file}", file=sys.stderr)
        return 2
    try:
        manifest = load_manifest(config_file)
        repositories_directory = PROJECT_DIRECTORY / "repos"
        active_directory = PROJECT_DIRECTORY / "active"
        if active_directory.exists() and (active_directory.is_symlink() or not active_directory.is_dir()):
            raise UnsafeSkillError(f"Active directory must be a directory, not a symlink: {active_directory}")
        reviews = [inspect_skill(skill, repositories_directory, active_directory) for skill in manifest.skills]
        for agent_path in manifest.agent_paths:
            _validate_agent_path(agent_path)
        candidates = [review for review in reviews if review.status in {"new", "changed"}]
        for review in candidates:
            validate_agent_targets(review, manifest.agent_paths, active_directory)
    except (ManifestError, UnsafeSkillError) as error:
        print(error, file=sys.stderr)
        return 2

    for review in reviews:
        print(f"{review.skill.repository_name}/{review.skill.name}: {review.status}")
    for review in candidates:
        diff = review_diff(review)
        print(diff, end="" if diff.endswith("\n") else "\n")
    orphans = orphan_skills({skill.name for skill in manifest.skills}, active_directory)
    links = orphan_links({skill.name for skill in manifest.skills}, active_directory, manifest.agent_paths)
    for orphan in orphans:
        print(f"active/{orphan.name}: orphan")
    for link in links:
        print(f"{link}: orphan link")
    if options.dry_run:
        return 1 if candidates or orphans or links or any(review.status == "missing" for review in reviews) else 0
    try:
        for review in candidates:
            answer = _prompt(f"Activate {review.skill.repository_name}/{review.skill.name}? [a]pprove, [r]eject, [q]uit: ", {"a", "r", "q"})
            if answer == "q":
                return 0
            if answer == "a":
                print(f"Activating {review.skill.repository_name}/{review.skill.name} into {active_directory / review.skill.name}")
                promote(review, active_directory, manifest.agent_paths)
        for orphan in orphans:
            if _prompt(f"Remove orphan active/{orphan.name}? [y]es, [n]o: ", {"y", "n"}) == "y":
                print(f"Removing active/{orphan.name}")
                remove_orphan(orphan, [link for link in links if link.name == orphan.name])
        for link in links:
            if not link.exists() and not link.is_symlink():
                continue
            if link.name not in {orphan.name for orphan in orphans}:
                if _prompt(f"Remove orphan link {link}? [y]es, [n]o: ", {"y", "n"}) == "y":
                    print(f"Removing orphan link {link}")
                    link.unlink()
    except (OSError, UnsafeSkillError, EOFError) as error:
        print(error, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
