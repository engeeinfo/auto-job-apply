import os
import json
from typing import Dict, Any

class Settings:
    """
    Handles loading and saving of user configuration options in data/settings.json.
    """
    def __init__(self, settings_path: str = None):
        if settings_path is None:
            # Default to naukri_bot/data/settings.json relative to this file
            base_dir = os.path.dirname(os.path.abspath(__file__))
            self.settings_path = os.path.join(base_dir, "data", "settings.json")
        else:
            self.settings_path = os.path.abspath(settings_path)

        self.defaults = {
            "gemini_api_key": "",
            "groq_api_key": "",
            "target_roles": "Python Developer, Software Engineer, Fullstack Developer",
            "min_score": 70,
            "daily_limit": 50,
            "chrome_profile_dir": "data/chrome_profile",
            "resume_path": "",
            "chrome_port": 9222,
            "gemini_model": "gemini-2.5-flash",
            "groq_model": "llama-3.3-70b-versatile",
        }
        self.data = self.defaults.copy()
        self.data = self.load()

    def load(self) -> Dict[str, Any]:
        """
        Loads configuration from the JSON file. Fallback to default values.
        """
        if not os.path.exists(self.settings_path):
            self.save(self.defaults)
            return self.defaults.copy()
        
        try:
            with open(self.settings_path, "r", encoding="utf-8") as f:
                loaded_data = json.load(f)
                
            # Merge loaded data with defaults to ensure any new keys are populated
            complete_data = self.defaults.copy()
            if isinstance(loaded_data, dict):
                complete_data.update(loaded_data)
            return complete_data
        except Exception as e:
            print(f"[Settings] Error loading configuration: {e}")
            return self.defaults.copy()

    def save(self, updated_data: Dict[str, Any] = None) -> None:
        """
        Writes the current configuration dictionary to disk.
        """
        if updated_data is not None:
            self.data.update(updated_data)

        os.makedirs(os.path.dirname(self.settings_path), exist_ok=True)
        try:
            with open(self.settings_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
        except Exception as e:
            print(f"[Settings] Error saving configuration: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """
        Retrieves a single configuration value by key.
        """
        # If not specified, check defaults list
        if default is None:
            default = self.defaults.get(key)
        return self.data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """
        Updates a single configuration key and immediately writes changes to disk.
        """
        self.data[key] = value
        self.save()
