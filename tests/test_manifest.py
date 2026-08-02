from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from skill_loader.manifest import ManifestError, load_manifest


class ManifestAgentPathTests(unittest.TestCase):
    def write_config(self, directory: Path, agent_path: str) -> Path:
        config = directory / "config.toml"
        config.write_text(
            f"[agent_paths]\npaths = [\"{agent_path}\"]\n\n"
            "[[repository]]\n"
            "name = \"fixture\"\n"
            "url = \"https://example.invalid/fixture.git\"\n"
            "branch = \"main\"\n"
            "skills = [{ name = \"release-checklist\", path = \"skills/release-checklist\" }]\n",
            encoding="utf-8",
        )
        return config

    def test_expands_leading_tilde_in_agent_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            config = self.write_config(Path(temporary_directory), "~/.agents/skills")

            manifest = load_manifest(config)

            self.assertEqual(
                manifest.agent_paths,
                (Path.home() / ".agents" / "skills",),
            )

    def test_rejects_environment_variable_expansion_in_agent_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            for agent_path in ("$AGENT_PATH", "%USERPROFILE%/skills"):
                with self.subTest(agent_path=agent_path):
                    config = self.write_config(Path(temporary_directory), agent_path)

                    with self.assertRaisesRegex(ManifestError, "Agent path must not use expansion"):
                        load_manifest(config)

    def test_rejects_mid_path_tilde_in_agent_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            config = self.write_config(Path(temporary_directory), "foo/~/skills")

            with self.assertRaisesRegex(ManifestError, "Agent path must not use expansion"):
                load_manifest(config)


if __name__ == "__main__":
    unittest.main()
