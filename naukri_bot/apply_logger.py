import os
import json
from datetime import datetime
from typing import List, Dict, Any

class ApplyLogger:
    """
    Manages job application logging to data/apply_log.json
    and enforces daily application limits.
    """
    def __init__(self, log_path: str = None):
        if log_path is None:
            # Default to naukri_bot/data/apply_log.json relative to this file
            base_dir = os.path.dirname(os.path.abspath(__file__))
            self.log_path = os.path.join(base_dir, "data", "apply_log.json")
        else:
            self.log_path = os.path.abspath(log_path)

    def _read_logs(self) -> List[Dict[str, Any]]:
        """
        Reads logs from the JSON file safely.
        """
        if not os.path.exists(self.log_path):
            return []
        try:
            with open(self.log_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
                return []
        except Exception as e:
            print(f"[ApplyLogger] Error reading logs: {e}")
            return []

    def _write_logs(self, logs: List[Dict[str, Any]]) -> None:
        """
        Writes logs to the JSON file, ensuring the directory exists.
        """
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        try:
            with open(self.log_path, "w", encoding="utf-8") as f:
                json.dump(logs, f, indent=2)
        except Exception as e:
            print(f"[ApplyLogger] Error writing logs: {e}")

    def log_apply(self, title: str, company: str, status: str, score: int, reason: str) -> None:
        """
        Appends a new job application try/status to the log file.
        """
        logs = self._read_logs()
        new_entry = {
            "timestamp": datetime.now().isoformat(),
            "title": title,
            "company": company,
            "status": status,
            "score": score,
            "reason": reason
        }
        logs.append(new_entry)
        self._write_logs(logs)

    def get_daily_applied_count(self) -> int:
        """
        Counts the number of jobs successfully 'Applied' during the current calendar day.
        """
        logs = self._read_logs()
        today = datetime.now().strftime("%Y-%m-%d")
        count = 0
        for entry in logs:
            ts = entry.get("timestamp", "")
            if ts.startswith(today) and entry.get("status") == "Applied":
                count += 1
        return count

    def get_all_logs(self) -> List[Dict[str, Any]]:
        """
        Fetches all stored log entries.
        """
        return self._read_logs()
