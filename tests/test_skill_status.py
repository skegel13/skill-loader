from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from skill_loader import skill_status


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

    def run_status(
        self, project: Path, *arguments: str, input: str | None = None
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(project / "bin" / "skill-status"), *arguments],
            cwd=project,
            text=True,
            capture_output=True,
            input=input,
        )

    def create_source_skill(self, project: Path, contents: str = "# Release checklist\n") -> Path:
        skill = project / "repos" / "fixture" / "skills" / "release-checklist"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(contents, encoding="utf-8")
        return skill

    def test_approves_a_new_skill_after_showing_its_complete_diff(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project = self.make_project(temporary_directory)
            source = self.create_source_skill(project)
            (source / "notes.md").write_text("Inspect this\n", encoding="utf-8")
            result = self.run_status(project, input="a\n")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("fixture/release-checklist: new", result.stdout)
            self.assertIn("--- active/release-checklist/SKILL.md", result.stdout)
            self.assertIn("+++ repos/fixture/skills/release-checklist/SKILL.md", result.stdout)
            self.assertIn("+Inspect this", result.stdout)
            active = project / "active" / "release-checklist"
            self.assertEqual((active / "notes.md").read_text(encoding="utf-8"), "Inspect this\n")
            link = project / "agents" / "skills" / "release-checklist"
            self.assertTrue(link.is_symlink())
            self.assertEqual(link.resolve(), active.resolve())

    def test_dry_run_shows_diffs_without_prompting_or_creating_runtime_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project = self.make_project(temporary_directory)
            self.create_source_skill(project)

            result = self.run_status(project, "--dry-run")

            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertIn("fixture/release-checklist: new", result.stdout)
            self.assertIn("--- active/release-checklist/SKILL.md", result.stdout)
            self.assertNotIn("Activate", result.stdout)
            self.assertFalse((project / "active").exists())
            self.assertFalse((project / "agents").exists())

    def test_diff_marks_binary_files_and_preserves_an_internal_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project = self.make_project(temporary_directory)
            source = self.create_source_skill(project)
            (source / "payload.bin").write_bytes(b"\x00new")
            (source / "guide.md").write_text("guide\n", encoding="utf-8")
            (source / "guide-link.md").symlink_to("guide.md")
            (source / "empty").mkdir()

            result = self.run_status(project, input="a\n")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Binary or type-changing entry", result.stdout)
            self.assertIn("+directory", result.stdout)
            active_link = project / "active" / "release-checklist" / "guide-link.md"
            self.assertTrue(active_link.is_symlink())
            self.assertEqual(active_link.readlink(), Path("guide.md"))

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
            result = self.run_status(project, input="r\n")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("fixture/release-checklist: changed", result.stdout)
            self.assertIn("-first", result.stdout)
            self.assertIn("+second", result.stdout)
            self.assertEqual((active / "notes.md").read_text(encoding="utf-8"), "first\n")

    def test_approved_update_replaces_the_active_snapshot_and_existing_managed_link(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project = self.make_project(temporary_directory)
            source = self.create_source_skill(project, "# New\n")
            active = project / "active" / "release-checklist"
            active.mkdir(parents=True)
            (active / "SKILL.md").write_text("# Old\n", encoding="utf-8")
            link = project / "agents" / "skills" / "release-checklist"
            link.parent.mkdir(parents=True)
            link.symlink_to(active)

            result = self.run_status(project, input="a\n")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((active / "SKILL.md").read_text(encoding="utf-8"), "# New\n")
            self.assertTrue(link.is_symlink())
            self.assertEqual(link.resolve(), active.resolve())

    def test_removes_confirmed_orphan_but_preserves_unmanaged_entries(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project = self.make_project(temporary_directory)
            active = project / "active"
            orphan = active / "old-skill"
            orphan.mkdir(parents=True)
            (orphan / "SKILL.md").write_text("# Old\n", encoding="utf-8")
            agent_path = project / "agents" / "skills"
            agent_path.mkdir(parents=True)
            (agent_path / "old-skill").symlink_to(orphan)
            unmanaged = active / "notes.txt"
            unmanaged.write_text("keep\n", encoding="utf-8")

            result = self.run_status(project, input="y\n")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("fixture/release-checklist: missing", result.stdout)
            self.assertIn("active/old-skill: orphan", result.stdout)
            self.assertFalse(orphan.exists())
            self.assertFalse((agent_path / "old-skill").exists())
            self.assertEqual(unmanaged.read_text(encoding="utf-8"), "keep\n")

    def test_quit_leaves_review_candidates_and_orphans_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project = self.make_project(temporary_directory)
            self.create_source_skill(project)
            orphan = project / "active" / "old-skill"
            orphan.mkdir(parents=True)
            (orphan / "SKILL.md").write_text("# Old\n", encoding="utf-8")

            result = self.run_status(project, input="q\n")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((project / "active" / "release-checklist").exists())
            self.assertTrue(orphan.is_dir())

    def test_refuses_to_replace_an_unmanaged_agent_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project = self.make_project(temporary_directory)
            self.create_source_skill(project)
            target = project / "agents" / "skills" / "release-checklist"
            target.mkdir(parents=True)
            (target / "keep.txt").write_text("keep\n", encoding="utf-8")

            result = self.run_status(project)

            self.assertEqual(result.returncode, 2)
            self.assertIn("Unmanaged agent target conflicts", result.stderr)
            self.assertTrue((target / "keep.txt").is_file())
            self.assertFalse((project / "active").exists())

    def test_reports_a_standalone_orphan_link_and_removes_it_on_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project = self.make_project(temporary_directory)
            agent_path = project / "agents" / "skills"
            agent_path.mkdir(parents=True)
            link = agent_path / "old-skill"
            link.symlink_to(project / "active" / "old-skill")

            result = self.run_status(project, input="y\n")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("orphan link", result.stdout)
            self.assertFalse(link.exists())
            self.assertFalse(link.is_symlink())

    def test_rejects_symlinked_agent_path_before_orphan_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project = self.make_project(temporary_directory)
            outside = project / "outside"
            outside.mkdir()
            (project / "agents").symlink_to(outside)
            (project / "config.toml").write_text(
                "[agent_paths]\npaths = [\"./agents\"]\n\n"
                "[[repository]]\nname = \"fixture\"\nurl = \"https://example.invalid/fixture.git\"\nbranch = \"main\"\nskills = []\n",
                encoding="utf-8",
            )

            result = self.run_status(project)

            self.assertEqual(result.returncode, 2)
            self.assertIn("Agent path must be a directory, not a symlink", result.stderr)

    def test_rejects_a_symlinked_agent_path_ancestor(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project = self.make_project(temporary_directory)
            outside = project / "outside"
            outside.mkdir()
            (project / "agents").symlink_to(outside)

            result = self.run_status(project, "--dry-run")

            self.assertEqual(result.returncode, 2)
            self.assertIn("Agent path must not have a symlinked ancestor", result.stderr)

    def test_rejects_malformed_active_snapshot_when_checkout_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project = self.make_project(temporary_directory)
            active = project / "active" / "release-checklist"
            active.parent.mkdir()
            active.symlink_to(project / "outside")

            result = self.run_status(project)

            self.assertEqual(result.returncode, 2)
            self.assertIn("Active skill path must be a directory, not a symlink", result.stderr)

    def test_promotion_failure_restores_a_previous_active_skill_and_link(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project = Path(temporary_directory)
            source = project / "source"
            source.mkdir()
            (source / "SKILL.md").write_text("# New\n", encoding="utf-8")
            active_root = project / "active"
            active = active_root / "release-checklist"
            active.mkdir(parents=True)
            (active / "SKILL.md").write_text("# Old\n", encoding="utf-8")
            agent_path = project / "agent"
            agent_path.mkdir()
            link = agent_path / "release-checklist"
            link.symlink_to(active)
            review = skill_status.Review(
                skill_status.Skill("fixture", "release-checklist", Path("skills/release-checklist")),
                source,
                active,
                "changed",
            )
            real_replace = skill_status.os.replace
            calls = 0

            def fail_link_swap(source_path: Path | str, target_path: Path | str) -> None:
                nonlocal calls
                calls += 1
                if calls == 4:
                    raise OSError("injected link failure")
                real_replace(source_path, target_path)

            with mock.patch.object(skill_status.os, "replace", side_effect=fail_link_swap):
                with self.assertRaises(OSError):
                    skill_status.promote(review, active_root, (agent_path,))

            self.assertEqual((active / "SKILL.md").read_text(encoding="utf-8"), "# Old\n")
            self.assertTrue(link.is_symlink())
            self.assertEqual(link.resolve(), active.resolve())
            self.assertFalse(list(active_root.glob(".*")))

    def test_active_swap_failure_restores_the_previous_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project = Path(temporary_directory)
            source = project / "source"
            source.mkdir()
            (source / "SKILL.md").write_text("# New\n", encoding="utf-8")
            active_root = project / "active"
            active = active_root / "release-checklist"
            active.mkdir(parents=True)
            (active / "SKILL.md").write_text("# Old\n", encoding="utf-8")
            review = skill_status.Review(skill_status.Skill("fixture", "release-checklist", Path("skills/release-checklist")), source, active, "changed")
            real_replace = skill_status.os.replace
            calls = 0

            def fail_active_swap(source_path: Path | str, target_path: Path | str) -> None:
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("injected active swap failure")
                real_replace(source_path, target_path)

            with mock.patch.object(skill_status.os, "replace", side_effect=fail_active_swap):
                with self.assertRaises(OSError):
                    skill_status.promote(review, active_root, ())

            self.assertEqual((active / "SKILL.md").read_text(encoding="utf-8"), "# Old\n")
            self.assertFalse(list(active_root.glob(".*")))

    def test_promotion_failure_removes_a_new_active_skill_and_temporary_link(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project = Path(temporary_directory)
            source = project / "source"
            source.mkdir()
            (source / "SKILL.md").write_text("# New\n", encoding="utf-8")
            active_root = project / "active"
            agent_path = project / "agent"
            agent_path.mkdir()
            review = skill_status.Review(
                skill_status.Skill("fixture", "release-checklist", Path("skills/release-checklist")),
                source,
                None,
                "new",
            )
            real_replace = skill_status.os.replace
            calls = 0

            def fail_new_link_swap(source_path: Path | str, target_path: Path | str) -> None:
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("injected link failure")
                real_replace(source_path, target_path)

            with mock.patch.object(skill_status.os, "replace", side_effect=fail_new_link_swap):
                with self.assertRaises(OSError):
                    skill_status.promote(review, active_root, (agent_path,))

            self.assertFalse((active_root / "release-checklist").exists())
            self.assertFalse((agent_path / "release-checklist").is_symlink())
            self.assertFalse(list(active_root.glob(".*")))

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
