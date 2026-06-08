import os
import sys
import time
import json

# Ensure parent directory is in python path to allow importing modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from settings import load_settings
from ai_matcher import call_gemini_score, call_grok_score

def mask_key(key):
    """Mask the API key, showing only the first and last 4 characters."""
    if not key:
        return "Not Set"
    key = key.strip()
    if len(key) <= 8:
        return "***"
    return f"{key[:4]}...{key[-4:]}"

def test_gemini(settings):
    print("\n--- Testing Gemini AI connection ---")
    api_key = settings.get("gemini_api_key")
    if not api_key:
        print("[-] Gemini API Key is not configured in settings.json.")
        return False
        
    print(f"[+] Loaded Gemini API Key: {mask_key(api_key)}")
    
    mock_resume = {"name": "Test Candidate", "skills": ["Python", "Machine Learning"]}
    mock_job = {"title": "AI Engineer", "requirements": ["Python", "PyTorch"]}
    
    start_time = time.time()
    try:
        res = call_gemini_score(mock_resume, mock_job, api_key)
        latency = (time.time() - start_time) * 1000
        if res and "score" in res:
            print(f"[+] SUCCESS: Gemini response received in {latency:.1f}ms")
            print(f"[+] Score: {res['score']}%")
            print(f"[+] Reason: {res.get('reason', 'N/A')}")
            return True
        else:
            print(f"[-] FAILURE: Gemini responded but response structure is invalid: {res}")
            return False
    except Exception as e:
        latency = (time.time() - start_time) * 1000
        print(f"[-] FAILURE: Gemini call failed after {latency:.1f}ms with error: {e}")
        return False

def test_groq_grok(settings):
    print("\n--- Testing Groq/Grok AI connection ---")
    api_key = settings.get("grok_api_key")
    if not api_key:
        print("[-] Groq/Grok API Key is not configured in settings.json.")
        return False
        
    is_groq = api_key.strip().startswith("gsk_")
    provider = "Groq" if is_groq else "xAI Grok"
    print(f"[+] Loaded {provider} API Key: {mask_key(api_key)}")
    
    mock_resume = {"name": "Test Candidate", "skills": ["Python", "Machine Learning"]}
    mock_job = {"title": "AI Engineer", "requirements": ["Python", "PyTorch"]}
    
    start_time = time.time()
    try:
        res = call_grok_score(mock_resume, mock_job, api_key)
        latency = (time.time() - start_time) * 1000
        if res and "score" in res:
            print(f"[+] SUCCESS: {provider} response received in {latency:.1f}ms")
            print(f"[+] Score: {res['score']}%")
            print(f"[+] Reason: {res.get('reason', 'N/A')}")
            return True
        else:
            print(f"[-] FAILURE: {provider} responded but response structure was invalid/empty: {res}")
            print("    Check console output above for error logs and status codes.")
            return False
    except Exception as e:
        latency = (time.time() - start_time) * 1000
        print(f"[-] FAILURE: {provider} call failed after {latency:.1f}ms with error: {e}")
        return False

def main():
    print("==================================================")
    print("         AI Connectivity Diagnostics Tool         ")
    print("==================================================")
    
    settings = load_settings()
    
    gemini_ok = test_gemini(settings)
    grok_ok = test_groq_grok(settings)
    
    print("\n==================================================")
    print("Summary:")
    print(f"  Gemini Integration:   {'[ OK ]' if gemini_ok else '[ FAILED ]'}")
    print(f"  Groq/Grok Integration: {'[ OK ]' if grok_ok else '[ FAILED ]'}")
    print("==================================================")

if __name__ == "__main__":
    main()
