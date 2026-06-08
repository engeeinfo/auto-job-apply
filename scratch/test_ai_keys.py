import json
import requests

def test_keys():
    try:
        with open("data/settings.json", "r", encoding="utf-8") as f:
            settings = json.load(f)
    except Exception as e:
        print(f"Error loading settings.json: {e}")
        return

    gemini_key = settings.get("gemini_api_key", "").strip()
    grok_key = settings.get("grok_api_key", "").strip()

    print("=== Testing Gemini API ===")
    if gemini_key:
        # Try gemini-2.5-flash
        model = "gemini-2.5-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={gemini_key}"
        payload = {"contents": [{"parts": [{"text": "Say 'Gemini is working'"}]}]}
        headers = {"Content-Type": "application/json"}
        try:
            r = requests.post(url, json=payload, headers=headers, timeout=20)
            if r.status_code == 200:
                text = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                print(f"[OK] Gemini API Success ({model}): Response: '{text}'")
            else:
                print(f"[FAIL] Gemini API Failure ({model}): Status {r.status_code}. Response: {r.text}")
        except Exception as e:
            print(f"[ERROR] Gemini API Connection Error: {e}")
    else:
        print("No Gemini API key configured.")

    print("\n=== Testing Grok/Groq API ===")
    if grok_key:
        is_groq = grok_key.startswith("gsk_")
        if is_groq:
            url = "https://api.groq.com/openai/v1/chat/completions"
            model = "llama-3.1-8b-instant"
            provider = "Groq"
        else:
            url = "https://api.x.ai/v1/chat/completions"
            model = "grok-2-1212"
            provider = "Grok"

        payload = {
            "model": model,
            "messages": [{"role": "user", "content": f"Say '{provider} is working'"}],
            "temperature": 0.1
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {grok_key}"
        }
        try:
            r = requests.post(url, json=payload, headers=headers, timeout=20)
            if r.status_code == 200:
                text = r.json()["choices"][0]["message"]["content"].strip()
                print(f"[OK] {provider} API Success ({model}): Response: '{text}'")
            else:
                print(f"[FAIL] {provider} API Failure ({model}): Status {r.status_code}. Response: {r.text}")
        except Exception as e:
            print(f"[ERROR] {provider} API Connection Error: {e}")
    else:
        print("No Grok API key configured.")

if __name__ == "__main__":
    test_keys()
