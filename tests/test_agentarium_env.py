import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentarium.env import load_env_file


class EnvironmentFileTests(unittest.TestCase):
    def test_loads_unset_values_without_overwriting_shell_values(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / ".env"
            path.write_text(
                "OPENAI_API_KEY=file-key\nTAVILY_API_KEY='tavily key'\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"OPENAI_API_KEY": "shell-key"}, clear=True):
                self.assertTrue(load_env_file(path))
                self.assertEqual(os.environ["OPENAI_API_KEY"], "shell-key")
                self.assertEqual(os.environ["TAVILY_API_KEY"], "tavily key")

    def test_reports_a_missing_file(self):
        self.assertFalse(load_env_file(Path("/tmp/no-agentarium-env-file")))


if __name__ == "__main__":
    unittest.main()
