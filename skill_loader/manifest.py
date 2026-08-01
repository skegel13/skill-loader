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


def load_repositories(config_file: Path) -> list[Repository]:
    try:
        with config_file.open("rb") as file:
            manifest: Any = tomllib.load(file)
    except tomllib.TOMLDecodeError as error:
        raise ManifestError(f"Invalid TOML in {config_file}: {error}") from error

    repositories = manifest.get("repository")
    if not isinstance(repositories, list) or not repositories:
        raise ManifestError(f"No repositories configured in {config_file}")

    parsed_repositories: list[Repository] = []
    names: set[str] = set()
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

    return parsed_repositories
