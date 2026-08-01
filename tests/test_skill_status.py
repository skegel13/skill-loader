from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class SkillStatusTests(unittest.TestCase):
    def make_project(self, directory: str) -> Path:
        project = Path(directory) / "loader"
        project.mkdir()
        shutil.copytree(PROJECT_ROOT / "bin", project / "bin")
        shutil.copytree(PROJECT_ROOT / "skill_loader", project / "skill_loader")
        (project / "config.toml").write_text(
            "[agent_paths]\npaths = [\"./agents/skills\"]\n\n"
            "[[repository]]\n"
            "name = \"fixture\"\nurl = \"https://example.invalid/fixture.git\"\nbranch = \"main\"\n"
            "skills = [{ name = \"release-checklist\", path = \"skills/release-checklist\" }]\n",
            encoding="utf-8",
        )
        return project

    def run_status(self, project: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(project / "bin" / "skill-status")],
            cwd=project,
            text=True,
            capture_output=True,
        )

    def create_source_skill(self, project: Path, contents: str = "# Release checklist\n") -> Path:
        skill = project / "repos" / "fixture" / "skills" / "release-checklist"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(contents, encoding="utf-8")
        return skill

    def test_reports_a_new_skill_without_creating_active_or_agent_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project = self.make_project(temporary_directory)
            self.create_source_skill(project)
            result = self.run_status(project)

            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertEqual(result.stdout, "fixture/release-checklist: new\n")
            self.assertFalse((project / "active").exists())
            self.assertFalse((project / "agents").exists())

    def test_reports_unchanged_then_changed_from_complete_tree_contents(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project = self.make_project(temporary_directory)
            source = self.create_source_skill(project)
            (source / "notes.md").write_text("first\n", encoding="utf-8")
            active = project / "active" / "release-checklist"
            active.mkdir(parents=True)
            shutil.copy2(source / "SKILL.md", active / "SKILL.md")
            shutil.copy2(source / "notes.md", active / "notes.md")

            result = self.run_status(project)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "fixture/release-checklist: unchanged\n")

            (source / "notes.md").write_text("second\n", encoding="utf-8")
            result = self.run_status(project)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertEqual(result.stdout, "fixture/release-checklist: changed\n")
            self.assertEqual((active / "notes.md").read_text(encoding="utf-8"), "first\n")

    def test_reports_missing_checkout_and_preserves_active_and_managed_orphans(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project = self.make_project(temporary_directory)
            active = project / "active"
            orphan = active / "old-skill"
            orphan.mkdir(parents=True)
            (orphan / "SKILL.md").write_text("# Old\n", encoding="utf-8")
            agent_path = project / "agents" / "skills"
            agent_path.mkdir(parents=True)
            (agent_path / "old-skill").symlink_to(orphan)

            result = self.run_status(project)

            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertEqual(
                result.stdout.splitlines()[:2],
                ["fixture/release-checklist: missing", "active/old-skill: orphan"],
            )
            self.assertTrue(result.stdout.splitlines()[2].endswith("/agents/skills/old-skill: orphan link"))
            self.assertTrue(orphan.is_dir())
            self.assertTrue((agent_path / "old-skill").is_symlink())

    def test_rejects_missing_skill_markdown_and_escaping_source_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project = self.make_project(temporary_directory)
            source = project / "repos" / "fixture" / "skills" / "release-checklist"
            source.mkdir(parents=True)
            result = self.run_status(project)
            self.assertEqual(result.returncode, 2)
            self.assertIn("missing SKILL.md", result.stderr)

            outside = project / "outside.md"
            outside.write_text("# Outside\n", encoding="utf-8")
            (source / "SKILL.md").symlink_to(outside)
            result = self.run_status(project)
            self.assertEqual(result.returncode, 2)
            self.assertIn("Source symlink is unsafe", result.stderr)

            (source / "SKILL.md").unlink()
            (source / "SKILL.md").symlink_to(source / "missing.md")
            result = self.run_status(project)
            self.assertEqual(result.returncode, 2)
            self.assertIn("missing SKILL.md", result.stderr)

    def test_rejects_unsafe_manifest_paths_before_reading_runtime_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project = self.make_project(temporary_directory)
            config = project / "config.toml"
            for agent_path, skills, message in (
                ("~/.agents/skills", '[{ name = "release-checklist", path = "../escape" }]', "Unsafe skill path"),
                ("$AGENT_PATH", '[{ name = "release-checklist", path = "skills/release-checklist" }]', "Agent path must not use expansion"),
                ("./agents/skills", '[{ name = "release-checklist", path = "/absolute" }]', "Unsafe skill path"),
                (
                    "./agents/skills",
                    '[{ name = "release-checklist", path = "skills/one" }, { name = "release-checklist", path = "skills/two" }]',
                    "Duplicate skill name",
                ),
            ):
                config.write_text(
                    f"[agent_paths]\npaths = [\"{agent_path}\"]\n\n"
                    "[[repository]]\n"
                    "name = \"fixture\"\nurl = \"https://example.invalid/fixture.git\"\nbranch = \"main\"\n"
                    f"skills = {skills}\n",
                    encoding="utf-8",
                )

                with self.subTest(message=message):
                    result = self.run_status(project)
                    self.assertEqual(result.returncode, 2)
                    self.assertIn(message, result.stderr)
                    self.assertFalse((project / "active").exists())


if __name__ == "__main__":
    unittest.main()
