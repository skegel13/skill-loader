from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class SyncReposTests(unittest.TestCase):
    def test_rejects_python_older_than_3_11(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fake_bin = Path(temporary_directory) / "bin"
            fake_bin.mkdir()
            python = fake_bin / "python3"
            python.write_text("#!/bin/sh\necho 3.10.14\n", encoding="utf-8")
            python.chmod(0o755)

            result = subprocess.run(
                ["/bin/bash", str(PROJECT_ROOT / "bin" / "sync-repos")],
                env={**os.environ, "PATH": f"{fake_bin}:/usr/bin:/bin"},
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("requires Python 3.11+ (found Python 3.10.14)", result.stderr)

    def test_rejects_missing_python3(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fake_bin = Path(temporary_directory) / "bin"
            fake_bin.mkdir()
            (fake_bin / "dirname").symlink_to("/usr/bin/dirname")

            result = subprocess.run(
                ["/bin/bash", str(PROJECT_ROOT / "bin" / "sync-repos")],
                env={**os.environ, "PATH": str(fake_bin)},
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("python3 was not found", result.stderr)

    def test_rejects_malformed_toml_before_creating_repositories_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project = Path(temporary_directory) / "loader"
            project.mkdir()
            (project / "bin").mkdir()
            shutil.copy2(PROJECT_ROOT / "bin" / "sync-repos", project / "bin")
            shutil.copytree(PROJECT_ROOT / "skill_loader", project / "skill_loader")
            (project / "config.toml").write_text(
                "[[repository]]\nname = \"unterminated\n", encoding="utf-8"
            )

            result = subprocess.run(
                [str(project / "bin" / "sync-repos")],
                cwd=project,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Invalid TOML", result.stderr)
            self.assertFalse((project / "repos").exists())

    def test_clones_a_repository_from_valid_single_quoted_toml(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory)
            remote = workspace / "remote.git"
            project = workspace / "loader"
            project.mkdir()
            (project / "bin").mkdir()
            shutil.copy2(PROJECT_ROOT / "bin" / "sync-repos", project / "bin")
            shutil.copytree(PROJECT_ROOT / "skill_loader", project / "skill_loader")

            subprocess.run(
                ["git", "init", "--bare", str(remote)], check=True, capture_output=True
            )
            seed = workspace / "seed"
            subprocess.run(["git", "init", str(seed)], check=True, capture_output=True)
            subprocess.run(
                ["git", "-C", str(seed), "config", "user.name", "Test User"], check=True
            )
            subprocess.run(
                ["git", "-C", str(seed), "config", "user.email", "test@example.com"],
                check=True,
            )
            (seed / "README.md").write_text("fixture\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(seed), "add", "README.md"], check=True)
            subprocess.run(
                ["git", "-C", str(seed), "commit", "-m", "seed"],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "-C", str(seed), "branch", "-M", "main"], check=True
            )
            subprocess.run(
                ["git", "-C", str(seed), "remote", "add", "origin", str(remote)],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(seed), "push", "origin", "main"],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "--git-dir", str(remote), "symbolic-ref", "HEAD", "refs/heads/main"],
                check=True,
            )

            (project / "config.toml").write_text(
                "[agent_paths]\n"
                "paths = []\n\n"
                "[[repository]]\n"
                "name = 'fixture'\n"
                f"url = '{remote}'\n"
                "branch = 'main'\n"
                "skills = []\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [str(project / "bin" / "sync-repos")],
                cwd=project,
                env={**os.environ, "GIT_CONFIG_NOSYSTEM": "1"},
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((project / "repos" / "fixture" / ".git").is_dir())

            (seed / "README.md").write_text("updated\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(seed), "add", "README.md"], check=True)
            subprocess.run(
                ["git", "-C", str(seed), "commit", "-m", "update"],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "-C", str(seed), "push", "origin", "main"],
                check=True,
                capture_output=True,
            )
            result = subprocess.run(
                [str(project / "bin" / "sync-repos")],
                cwd=project,
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                (project / "repos" / "fixture" / "README.md").read_text(encoding="utf-8"),
                "updated\n",
            )

            target = project / "repos" / "fixture"
            (target / "dirty.txt").write_text("dirty\n", encoding="utf-8")
            result = subprocess.run(
                [str(project / "bin" / "sync-repos")], cwd=project, text=True, capture_output=True
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Refusing to update dirty checkout", result.stderr)
            (target / "dirty.txt").unlink()

            config_file = project / "config.toml"
            configured_toml = config_file.read_text(encoding="utf-8")
            config_file.write_text(
                configured_toml.replace(str(remote), str(workspace / "other.git")), encoding="utf-8"
            )
            result = subprocess.run(
                [str(project / "bin" / "sync-repos")], cwd=project, text=True, capture_output=True
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Origin URL does not match", result.stderr)
            config_file.write_text(configured_toml, encoding="utf-8")

            subprocess.run(["git", "-C", str(target), "switch", "-c", "other"], check=True)
            result = subprocess.run(
                [str(project / "bin" / "sync-repos")], cwd=project, text=True, capture_output=True
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Checkout is not on configured branch", result.stderr)
            subprocess.run(["git", "-C", str(target), "switch", "main"], check=True)

            subprocess.run(
                ["git", "-C", str(target), "config", "user.name", "Test User"], check=True
            )
            subprocess.run(
                ["git", "-C", str(target), "config", "user.email", "test@example.com"], check=True
            )
            (target / "local.md").write_text("local\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(target), "add", "local.md"], check=True)
            subprocess.run(
                ["git", "-C", str(target), "commit", "-m", "local"], check=True, capture_output=True
            )
            (seed / "remote.md").write_text("remote\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(seed), "add", "remote.md"], check=True)
            subprocess.run(
                ["git", "-C", str(seed), "commit", "-m", "remote"], check=True, capture_output=True
            )
            subprocess.run(
                ["git", "-C", str(seed), "push", "origin", "main"],
                check=True,
                capture_output=True,
            )
            result = subprocess.run(
                [str(project / "bin" / "sync-repos")], cwd=project, text=True, capture_output=True
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Refusing non-fast-forward update", result.stderr)

    def test_dry_run_does_not_create_a_missing_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project = Path(temporary_directory) / "loader"
            project.mkdir()
            (project / "bin").mkdir()
            shutil.copy2(PROJECT_ROOT / "bin" / "sync-repos", project / "bin")
            shutil.copytree(PROJECT_ROOT / "skill_loader", project / "skill_loader")
            (project / "config.toml").write_text(
                "[[repository]]\n"
                "name = 'fixture'\n"
                "url = 'https://example.invalid/fixture.git'\n"
                "branch = 'main'\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [str(project / "bin" / "sync-repos"), "--dry-run"],
                cwd=project,
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Would clone fixture", result.stdout)
            self.assertFalse((project / "repos").exists())

    def test_rejects_a_repository_name_that_escapes_repositories(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project = Path(temporary_directory) / "loader"
            project.mkdir()
            (project / "bin").mkdir()
            shutil.copy2(PROJECT_ROOT / "bin" / "sync-repos", project / "bin")
            shutil.copytree(PROJECT_ROOT / "skill_loader", project / "skill_loader")
            (project / "config.toml").write_text(
                "[[repository]]\nname = '..'\nurl = 'https://example.invalid/fixture.git'\nbranch = 'main'\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [str(project / "bin" / "sync-repos")],
                cwd=project,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Unsafe repository name", result.stderr)
            self.assertFalse((project / "repos").exists())


if __name__ == "__main__":
    unittest.main()
