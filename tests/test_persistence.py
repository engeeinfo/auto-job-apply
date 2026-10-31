import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from naukri_bot.apply_logger import ApplyLogger
from naukri_bot.settings import Settings


class PersistenceTests(unittest.TestCase):
    def test_settings_merge_defaults_and_persist_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            settings = Settings(str(path))
            settings.set("daily_limit", 3)

            reloaded = Settings(str(path))
            self.assertEqual(reloaded.get("daily_limit"), 3)
            self.assertEqual(reloaded.get("target_roles"), settings.defaults["target_roles"])

    def test_logger_counts_only_applied_entries_today(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "apply_log.json"
            today = datetime.now().isoformat()
            path.write_text(json.dumps([
                {"timestamp": today, "status": "Applied"},
                {"timestamp": today, "status": "Skipped"},
                {"timestamp": "2000-01-01T00:00:00", "status": "Applied"},
            ]), encoding="utf-8")

            self.assertEqual(ApplyLogger(str(path)).get_daily_applied_count(), 1)


if __name__ == "__main__":
    unittest.main()
