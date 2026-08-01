from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import tomllib
from typing import Any


SAFE_REPOSITORY_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class ManifestError(ValueError):
    """Raised when the manifest cannot safely describe a repository checkout."""


@dataclass(frozen=True)
class Repository:
    name: str
    url: str
    branch: str


@dataclass(frozen=True)
class Skill:
    repository_name: str
    name: str
    path: Path


@dataclass(frozen=True)
class Manifest:
    agent_paths: tuple[Path, ...]
    repositories: tuple[Repository, ...]
    skills: tuple[Skill, ...]


def load_repositories(config_file: Path) -> list[Repository]:
    manifest = _load_toml(config_file)
    return _load_repositories(manifest, config_file, require_skills=False)[0]


def load_manifest(config_file: Path) -> Manifest:
    manifest = _load_toml(config_file)
    repositories, skills = _load_repositories(manifest, config_file, require_skills=True)
    agent_paths = _load_agent_paths(manifest, config_file)
    return Manifest(tuple(agent_paths), tuple(repositories), tuple(skills))


def _load_toml(config_file: Path) -> Any:
    try:
        with config_file.open("rb") as file:
            manifest: Any = tomllib.load(file)
    except tomllib.TOMLDecodeError as error:
        raise ManifestError(f"Invalid TOML in {config_file}: {error}") from error

    return manifest


def _load_repositories(
    manifest: Any, config_file: Path, *, require_skills: bool
) -> tuple[list[Repository], list[Skill]]:
    repositories = manifest.get("repository")
    if not isinstance(repositories, list) or not repositories:
        raise ManifestError(f"No repositories configured in {config_file}")

    parsed_repositories: list[Repository] = []
    parsed_skills: list[Skill] = []
    names: set[str] = set()
    skill_names: set[str] = set()
    for index, repository in enumerate(repositories, start=1):
        if not isinstance(repository, dict):
            raise ManifestError(f"Repository {index} must be a TOML table")

        fields = {
            field: repository.get(field)
            for field in ("name", "url", "branch")
        }
        missing_fields = [
            field for field, value in fields.items() if not isinstance(value, str) or not value
        ]
        if missing_fields:
            missing = ", ".join(missing_fields)
            raise ManifestError(f"Repository {index} is missing a non-empty {missing}")

        name = fields["name"]
        url = fields["url"]
        branch = fields["branch"]
        assert isinstance(name, str) and isinstance(url, str) and isinstance(branch, str)

        if name in {".", ".."} or not SAFE_REPOSITORY_NAME.fullmatch(name):
            raise ManifestError(f"Unsafe repository name: {name}")
        if name in names:
            raise ManifestError(f"Duplicate repository name: {name}")
        names.add(name)
        parsed_repositories.append(Repository(name=name, url=url, branch=branch))

        raw_skills = repository.get("skills", [] if not require_skills else None)
        if not isinstance(raw_skills, list):
            raise ManifestError(f"Repository {name} skills must be an array")
        for skill_index, skill in enumerate(raw_skills, start=1):
            if not isinstance(skill, dict):
                raise ManifestError(f"Skill {skill_index} in {name} must be a TOML table")
            skill_name = skill.get("name")
            skill_path = skill.get("path")
            if not isinstance(skill_name, str) or not skill_name:
                raise ManifestError(f"Skill {skill_index} in {name} is missing a non-empty name")
            if not isinstance(skill_path, str) or not skill_path:
                raise ManifestError(f"Skill {skill_name} in {name} is missing a non-empty path")
            if skill_name in {".", ".."} or not SAFE_REPOSITORY_NAME.fullmatch(skill_name):
                raise ManifestError(f"Unsafe skill name: {skill_name}")
            if skill_name in skill_names:
                raise ManifestError(f"Duplicate skill name: {skill_name}")
            relative_path = Path(skill_path)
            if relative_path.is_absolute() or ".." in relative_path.parts:
                raise ManifestError(f"Unsafe skill path for {skill_name}: {skill_path}")
            skill_names.add(skill_name)
            parsed_skills.append(Skill(name, skill_name, relative_path))

    return parsed_repositories, parsed_skills


def _load_agent_paths(manifest: Any, config_file: Path) -> list[Path]:
    agent_paths_table = manifest.get("agent_paths")
    if not isinstance(agent_paths_table, dict) or not isinstance(agent_paths_table.get("paths"), list):
        raise ManifestError(f"agent_paths.paths must be an array in {config_file}")

    configured_paths: list[Path] = []
    for value in agent_paths_table["paths"]:
        if not isinstance(value, str) or not value:
            raise ManifestError("Agent path must be a non-empty string")
        if "~" in value or "$" in value or "%" in value:
            raise ManifestError(f"Agent path must not use expansion: {value}")
        path = Path(value)
        configured_paths.append(path if path.is_absolute() else config_file.parent / path)
    return configured_paths
