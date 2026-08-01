from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

from skill_loader.manifest import ManifestError, Repository, load_repositories


PROJECT_DIRECTORY = Path(__file__).resolve().parent.parent


def run_git(*arguments: str, cwd: Path | None = None, capture_output: bool = False) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=cwd,
        check=True,
        text=True,
        capture_output=capture_output,
    )
    return result.stdout if capture_output else ""


def inspect_repository(repository: Repository, repositories_directory: Path) -> bool:
    target = repositories_directory / repository.name
    if not target.exists():
        if target.is_symlink():
            raise RuntimeError(f"Repository target is a broken symlink: {target}")
        return True

    if target.is_symlink():
        raise RuntimeError(f"Repository target must not be a symlink: {target}")

    if not (target / ".git").is_dir():
        raise RuntimeError(f"Repository target is not a Git checkout: {target}")

    origin_url = run_git("remote", "get-url", "origin", cwd=target, capture_output=True).strip()
    if origin_url != repository.url:
        raise RuntimeError(f"Origin URL does not match configuration for {repository.name}")

    if run_git("status", "--porcelain", cwd=target, capture_output=True).strip():
        raise RuntimeError(f"Refusing to update dirty checkout: {target}")

    current_branch = run_git("branch", "--show-current", cwd=target, capture_output=True).strip()
    if current_branch != repository.branch:
        raise RuntimeError(
            f"Checkout is not on configured branch {repository.branch}: {target}"
        )

    return False


def sync_repository(repository: Repository, repositories_directory: Path, clone: bool) -> None:
    target = repositories_directory / repository.name
    if clone:
        print(f"Cloning {repository.name} into {target}")
        run_git("clone", "--branch", repository.branch, "--single-branch", repository.url, str(target))
        return

    print(f"Fast-forwarding {repository.name} in {target}")
    run_git("fetch", "origin", repository.branch, cwd=target)
    if subprocess.run(
        ["git", "merge-base", "--is-ancestor", "HEAD", "FETCH_HEAD"], cwd=target
    ).returncode:
        raise RuntimeError(f"Refusing non-fast-forward update for {repository.name}")
    run_git("merge", "--ff-only", "FETCH_HEAD", cwd=target)


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Synchronize configured skill repositories.")
    parser.add_argument(
        "--dry-run", action="store_true", help="Print planned changes without modifying checkouts."
    )
    options = parser.parse_args(arguments)
    config_file = PROJECT_DIRECTORY / "config.toml"
    if not config_file.is_file():
        print(f"Configuration file not found: {config_file}", file=sys.stderr)
        return 1

    try:
        repositories = load_repositories(config_file)
        repositories_directory = PROJECT_DIRECTORY / "repos"
        checkout_plans = [
            (repository, inspect_repository(repository, repositories_directory))
            for repository in repositories
        ]
        if options.dry_run:
            for repository, clone in checkout_plans:
                action = "clone" if clone else "fast-forward"
                print(f"Would {action} {repository.name} at {repositories_directory / repository.name}")
            return 0
        repositories_directory.mkdir(exist_ok=True)
        for repository, clone in checkout_plans:
            sync_repository(repository, repositories_directory, clone)
    except (ManifestError, RuntimeError, subprocess.CalledProcessError) as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
