import json
import time
import requests
import re
from settings import load_settings
from resume_parser import extract_json_from_response

def parse_score(res):
    """Safely extract and convert score from dictionary or string value using regex fallback."""
    if not res or "score" not in res:
        raise ValueError("Response dictionary is missing 'score' key.")
    raw_score = res["score"]
    try:
        return float(raw_score)
    except (ValueError, TypeError):
        # Fallback: extract first digit sequence from string (e.g. "85%", "score is 90")
        score_str = str(raw_score)
        match = re.search(r'\d+', score_str)
        if match:
            return float(match.group())
        raise ValueError(f"Could not convert score value to number: {raw_score}")

def call_gemini_score(resume_json, job_json, api_key):
    """Call Gemini score matching with fallback model hierarchy."""
    models_to_try = ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-1.5-flash-latest", "gemini-flash-latest"]
    
    prompt = (
        f"Score this job match from 0-100. "
        f"Resume: {json.dumps(resume_json)}. "
        f"Job: {json.dumps(job_json)}. "
        f"Reply ONLY with a JSON: {{\"score\": int, \"reason\": \"str\"}}"
    )
    
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{
            "parts": [{
                "text": prompt
            }]
        }]
    }
    
    last_error = None
    for model_name in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        
        for attempt in range(2):  # Try up to 2 attempts per model
            try:
                response = requests.post(url, headers=headers, json=payload, timeout=20)
                if response.status_code == 429:
                    if attempt < 1:
                        time.sleep(3)
                        continue
                    else:
                        raise Exception(f"Gemini model {model_name} rate limit hit.")
                
                if response.status_code != 200:
                    try:
                        err_json = response.json()
                        err_msg = err_json.get("error", {}).get("message", response.text)
                    except Exception:
                        err_msg = response.text
                        
                    if response.status_code in (401, 403):
                        raise PermissionError(f"Gemini API Authentication/Permission Error ({response.status_code}): {err_msg}")
                    if response.status_code in (400, 404):
                        raise LookupError(f"Gemini API Bad Request/Not Found ({response.status_code}): {err_msg}")
                        
                    raise ValueError(f"Gemini API Error ({response.status_code}): {err_msg}")
                    
                resp_data = response.json()
                try:
                    ai_text = resp_data["candidates"][0]["content"]["parts"][0]["text"]
                except (KeyError, IndexError) as format_err:
                    raise ValueError("Invalid response structure or empty candidates received from Gemini API.") from format_err
                return extract_json_from_response(ai_text)
            except PermissionError as pe:
                print(f"Gemini: Unrecoverable API permission error: {pe}")
                raise pe
            except LookupError as le:
                print(f"Gemini: Model {model_name} is invalid/not found: {le}")
                last_error = le
                break  # Skip to next model
            except Exception as e:
                last_error = e
                print(f"Gemini: Attempt failed with model {model_name}: {e}")
                if attempt < 1:
                    time.sleep(1)
                    
    raise last_error if last_error else ValueError("All Gemini scoring attempts failed.")

def call_grok_score(resume_json, job_json, api_key):
    """Call Grok or Groq API to score the job match, dynamically routing based on the API key prefix."""
    is_groq = api_key.strip().startswith("gsk_")
    
    if is_groq:
        url = "https://api.groq.com/openai/v1/chat/completions"
        models = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "llama3-8b-8192", "mixtral-8x7b-32768"]
        provider_name = "Groq"
    else:
        url = "https://api.x.ai/v1/chat/completions"
        models = ["grok-4.3", "grok-4.20", "grok-4.1-fast", "grok-build-0.1", "grok-beta"]
        provider_name = "Grok"
        
    prompt = (
        f"Score this job match from 0-100. "
        f"Resume: {json.dumps(resume_json)}. "
        f"Job: {json.dumps(job_json)}. "
        f"Reply ONLY with a JSON: {{\"score\": int, \"reason\": \"str\"}}"
    )
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    for model in models:
        payload = {
            "model": model,
            "messages": [
                {"role": "user", "content": prompt}
            ]
        }
        if is_groq:
            payload["response_format"] = {"type": "json_object"}
            
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=25)
            if response.status_code == 429:
                print(f"{provider_name} rate limit hit for model {model}. Trying next fallback model...")
                continue
                
            if response.status_code in (401, 403):
                print(f"{provider_name} authentication failure ({response.status_code}): {response.text}")
                return None
                
            response.raise_for_status()
            
            resp_data = response.json()
            ai_text = resp_data["choices"][0]["message"]["content"]
            return extract_json_from_response(ai_text)
        except Exception as e:
            print(f"{provider_name} API call failed for model {model}: {e}")
            continue
            
    return None

def score_job_match(resume_json, job_json):
    """Get dual AI score and return final score, reasons, and whether it qualifies."""
    settings = load_settings()
    gemini_key = settings.get("gemini_api_key")
    grok_key = settings.get("grok_api_key")
    min_score = settings.get("min_match_score", 70)
    
    gemini_score = None
    gemini_reason = "Not attempted"
    grok_score = None
    grok_reason = "Not attempted"
    
    # Try Gemini scoring
    if gemini_key and gemini_key.strip():
        try:
            gemini_res = call_gemini_score(resume_json, job_json, gemini_key)
            if gemini_res and "score" in gemini_res:
                gemini_score = parse_score(gemini_res)
                gemini_reason = gemini_res.get("reason", "N/A")
            else:
                gemini_reason = "Failed to obtain score from Gemini response"
        except Exception as gemini_err:
            gemini_reason = f"Gemini error: {gemini_err}"
            print(f"Scoring: Gemini failed, attempting fallback. Error: {gemini_err}")
            
    # Try Grok/Groq scoring
    if grok_key and grok_key.strip():
        try:
            grok_res = call_grok_score(resume_json, job_json, grok_key)
            if grok_res and "score" in grok_res:
                try:
                    grok_score = parse_score(grok_res)
                    grok_reason = grok_res.get("reason", "N/A")
                except Exception as parse_err:
                    grok_reason = f"Grok score parsing failed: {parse_err}"
            else:
                grok_reason = "Failed to obtain score from Grok response"
        except Exception as grok_err:
            grok_reason = f"Grok error: {grok_err}"
            print(f"Scoring: Grok failed, attempting fallback. Error: {grok_err}")
            
    # Raise error only if BOTH failed
    if gemini_score is None and grok_score is None:
        raise ValueError(f"All AI scoring engines failed. Gemini status: {gemini_reason}. Grok status: {grok_reason}")
        
    # Calculate final score and reasons
    if gemini_score is not None and grok_score is not None:
        final_score = (gemini_score + grok_score) / 2.0
        reasons = f"Gemini ({int(gemini_score)}%): {gemini_reason} | Grok ({int(grok_score)}%): {grok_reason}"
    elif gemini_score is not None:
        final_score = gemini_score
        reasons = f"Gemini ({int(gemini_score)}%): {gemini_reason} | Grok: skipped/failed ({grok_reason})"
    else:
        final_score = grok_score
        reasons = f"Grok ({int(grok_score)}%): {grok_reason} | Gemini: skipped/failed ({gemini_reason})"
        
    return {
        "score": round(final_score, 1),
        "reasons": reasons,
        "qualified": final_score >= min_score
    }
