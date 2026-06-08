import os
import json

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")

def ensure_data_dir():
    """Ensure the data directory exists."""
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)

def load_settings():
    """Load settings from data/settings.json."""
    ensure_data_dir()
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading settings: {e}")
    
    # Return defaults
    return {
        "gemini_api_key": "",
        "grok_api_key": "",
        "target_roles": "Python Developer, Backend Engineer",
        "min_match_score": 70,
        "enabled_boards": ["Naukri"]
    }

def save_settings(settings):
    """Save settings to data/settings.json."""
    ensure_data_dir()
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving settings: {e}")
        return False

def reset_all_data():
    """Delete all JSON/cookies files in data/ except settings.json."""
    ensure_data_dir()
    deleted_files = []
    for filename in os.listdir(DATA_DIR):
        if filename == "settings.json":
            continue
        file_path = os.path.join(DATA_DIR, filename)
        try:
            if os.path.isfile(file_path):
                os.remove(file_path)
                deleted_files.append(filename)
        except Exception as e:
            print(f"Error deleting {filename}: {e}")
    return deleted_files
