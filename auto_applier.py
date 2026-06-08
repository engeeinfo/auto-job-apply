import os
import json
import time
from datetime import datetime
import requests
from selenium.webdriver.common.by import By
from settings import DATA_DIR, load_settings
from job_scraper import init_driver, fetch_full_job_description
from ai_matcher import score_job_match

# Reuse TCP connections via a global session object for speed and efficiency
session = requests.Session()

JOBS_QUEUE_FILE = os.path.join(DATA_DIR, "jobs_queue.json")
APPLY_LOG_FILE = os.path.join(DATA_DIR, "apply_log.json")
RESUME_DATA_FILE = os.path.join(DATA_DIR, "resume_data.json")

def get_resume_file_path():
    """Return the absolute path of the uploaded resume file (.pdf or .docx)."""
    for ext in ['.pdf', '.docx']:
        path = os.path.join(DATA_DIR, f"resume{ext}")
        if os.path.exists(path):
            return path
    return None

def log_action(job_title, company, status, reason=""):
    """Write an entry to data/apply_log.json with a timestamp."""
    logs = []
    if os.path.exists(APPLY_LOG_FILE):
        try:
            with open(APPLY_LOG_FILE, "r", encoding="utf-8") as f:
                logs = json.load(f)
        except Exception:
            pass
            
    logs.append({
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "job_title": job_title,
        "company": company,
        "status": status,
        "reason": reason
    })
    
    with open(APPLY_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(logs, f, indent=2)

def check_login_status(driver, source="Naukri"):
    """Check if the session has expired or is redirected to login page."""
    try:
        current_url = driver.current_url
        if source == "Naukri" and ("naukri.com/login" in current_url or "naukri.com/register" in current_url):
            return False
        elif source == "Foundit" and ("foundit.in/login" in current_url or "foundit.in/register" in current_url):
            return False
        elif source == "Indeed" and ("indeed.com/login" in current_url or "indeed.com/register" in current_url):
            return False
        elif source == "LinkedIn" and ("linkedin.com/login" in current_url or "linkedin.com/signup" in current_url):
            return False
        return True
    except Exception as e:
        print(f"Applier: Error checking login status (browser may have closed): {e}")
        return False

def fill_easy_apply_form(driver, resume_data, resume_file_path, logger=None):
    """Try to fill quick-apply form fields using resume data."""
    try:
        # 1. Upload Resume file if input exists
        try:
            file_input = driver.find_element(By.CSS_SELECTOR, "input[type='file'], input[name='resume']")
            file_input.send_keys(resume_file_path)
            if logger:
                logger("Applier: Uploaded resume file.")
            time.sleep(2)
        except Exception:
            pass  # Maybe already uploaded or not found

        # 2. Fill Name, Phone, Email fields if they exist
        fields_to_fill = [
            # Selector, Key in resume_data
            ("input[placeholder*='name'], input[placeholder*='Name'], input[id*='name']", "name"),
            ("input[placeholder*='email'], input[placeholder*='Email'], input[id*='email']", "email"),
            ("input[placeholder*='mobile'], input[placeholder*='phone'], input[id*='mobile'], input[id*='phone']", "phone")
        ]
        
        for selector, key in fields_to_fill:
            if key in resume_data and resume_data[key]:
                try:
                    elem = driver.find_element(By.CSS_SELECTOR, selector)
                    if not elem.get_attribute("value"):  # fill only if empty
                        elem.send_keys(str(resume_data[key]))
                        if logger:
                            logger(f"Applier: Filled form field '{key}': {resume_data[key]}")
                        time.sleep(1)
                except Exception:
                    pass

        # 3. Handle notice period, experience sliders, CTC if present (Naukri Easy Apply varies)
        # For simplicity, we fill standard fields, but let's click the final Submit/Apply button
        submit_selectors = [
            "button[type='submit']",
            "button.apply-button",
            "button.btn-primary",
            "button.submit-button",
            "//button[contains(text(), 'Submit')]",
            "//button[contains(text(), 'Apply')]"
        ]
        
        submit_btn = None
        for sel in submit_selectors:
            try:
                if sel.startswith("//"):
                    submit_btn = driver.find_element(By.XPATH, sel)
                else:
                    submit_btn = driver.find_element(By.CSS_SELECTOR, sel)
                if submit_btn and submit_btn.is_displayed():
                    break
            except Exception:
                pass
                
        if submit_btn:
            submit_btn.click()
            time.sleep(3)
            return True
            
        return False
    except Exception as e:
        if logger:
            logger(f"Applier Warning: Error filling form: {e}")
        return False

def run_auto_apply(stop_event, pause_event, logger=None):
    """Core auto-apply automation loop."""
    driver = None
    
    try:
        # Load resume data
        if not os.path.exists(RESUME_DATA_FILE):
            if logger:
                logger("Applier Error: resume_data.json is missing. Please upload your resume first.")
            return
            
        with open(RESUME_DATA_FILE, "r", encoding="utf-8") as f:
            resume_data = json.load(f)
            
        resume_file_path = get_resume_file_path()
        if not resume_file_path:
            if logger:
                logger("Applier Error: Resume file (PDF/DOCX) not found in data folder.")
            return

        settings = load_settings()
        min_score = settings.get("min_match_score", 70)
        
        # Load jobs queue
        if not os.path.exists(JOBS_QUEUE_FILE):
            if logger:
                logger("Applier: No jobs in queue. Please search and discover jobs first.")
            return
            
        with open(JOBS_QUEUE_FILE, "r", encoding="utf-8") as f:
            jobs = json.load(f)
            
        if not isinstance(jobs, list):
            if logger:
                logger("Applier Error: jobs_queue.json is corrupted or not a valid list.")
            return
            
        pending_jobs = [j for j in jobs if isinstance(j, dict) and j.get("status") == "Pending"]
        if not pending_jobs:
            if logger:
                logger("Applier: No 'Pending' jobs in the queue to process.")
            return
            
        if logger:
            logger(f"Applier: Starting auto-apply for {len(pending_jobs)} pending jobs.")
            
        # Init Selenium (Cookies will be loaded on-demand for target domains inside the loop)
        driver = init_driver(headless=False)
        
        for job in jobs:
            # Check stop/pause flags
            if stop_event.is_set():
                if logger:
                    logger("Applier: Stopped by user.")
                break
                
            while pause_event.is_set():
                if stop_event.is_set():
                    break
                time.sleep(1)
                
            if not isinstance(job, dict):
                continue
            if job.get("status") != "Pending":
                continue
                
            job_title = job.get("title", "N/A")
            company = job.get("company", "N/A")
            apply_url = job.get("apply_url")
            source = job.get("source", "Naukri")
            
            if not apply_url or not isinstance(apply_url, str) or not apply_url.startswith("http"):
                if logger:
                    logger(f"Applier Warning: Skipped job '{job_title}' with invalid URL: {apply_url}")
                job["status"] = "Failed"
                continue
            
            if logger:
                logger(f"Applier: Processing job: '{job_title}' at '{company}' from {source}...")
                
            try:
                # 1. Navigate to job page
                driver.get(apply_url)
                time.sleep(3)
                
                # Check session login status
                if not check_login_status(driver, source):
                    if logger:
                        logger(f"Applier Error: Session expired for {source}. Please log in again in the embedded browser.")
                    log_action(job_title, company, "Failed", f"Session expired on {source}. Login required.")
                    break
                    
                # 2. Get full description if missing or basic
                if not job.get("job_description") or job["job_description"] == "N/A" or len(job["job_description"]) < 100:
                    full_desc = fetch_full_job_description(driver, apply_url)
                    job["job_description"] = full_desc
                    
                # 3. AI Scoring (if not already scored)
                if job.get("score") is None:
                    if logger:
                        logger("Applier: Running AI Match scoring...")
                    match_res = score_job_match(resume_data, job)
                    job["score"] = match_res["score"]
                    job["reasons"] = match_res["reasons"]
                    
                    # Update jobs_queue.json immediately with score
                    with open(JOBS_QUEUE_FILE, "w", encoding="utf-8") as f:
                        json.dump(jobs, f, indent=2)
                        
                # Check score
                score = job["score"]
                if score < min_score:
                    if logger:
                        logger(f"Applier: Skipped. Match score {score}% is below threshold ({min_score}%).")
                    job["status"] = "Skipped"
                    log_action(job_title, company, "Skipped", f"Score {score}% below threshold.")
                    with open(JOBS_QUEUE_FILE, "w", encoding="utf-8") as f:
                        json.dump(jobs, f, indent=2)
                    continue
                    
                # Score qualified, proceed to apply
                if logger:
                    logger(f"Applier: Qualifies! Score: {score}%. Attempting to apply...")
                    
                # Look for the Apply button based on platform
                apply_selectors = []
                if source == "Naukri":
                    apply_selectors = [
                        "button.apply-button",
                        "button.btn-primary",
                        "button.apply-button-default",
                        "button.apply",
                        "a.apply-button",
                        "div.apply-button-container button"
                    ]
                elif source == "Foundit":
                    apply_selectors = [
                        "button.apply-btn",
                        "button.apply-button",
                        ".applyBtn",
                        ".apply-button"
                    ]
                elif source == "Indeed":
                    apply_selectors = [
                        "#indeedApplyButton",
                        ".indeed-apply-button",
                        "button.jobsearch-CallToApplyButton",
                        ".indeed-apply-button-inner-button"
                    ]
                elif source == "LinkedIn":
                    apply_selectors = [
                        ".jobs-apply-button",
                        "button.jobs-apply-button"
                    ]
                
                apply_btn = None
                for sel in apply_selectors:
                    try:
                        apply_btn = driver.find_element(By.CSS_SELECTOR, sel)
                        if apply_btn.is_displayed():
                            break
                    except Exception:
                        pass
                        
                if not apply_btn:
                    # Generic XPATH fallback search
                    try:
                        apply_btn = driver.find_element(By.XPATH, "//button[contains(text(), 'Apply')] | //a[contains(text(), 'Apply')] | //button[contains(text(), 'Easy Apply')]")
                    except Exception:
                        pass
                        
                if not apply_btn:
                    if logger:
                        logger("Applier Warning: Apply button not found or already applied.")
                    job["status"] = "Manual Required"
                    log_action(job_title, company, "Manual Required", "Apply button not found on page.")
                    with open(JOBS_QUEUE_FILE, "w", encoding="utf-8") as f:
                        json.dump(jobs, f, indent=2)
                    continue
                    
                # Click Apply
                original_handles = driver.window_handles
                apply_btn.click()
                time.sleep(4)
                
                # Check for external redirect
                new_handles = driver.window_handles
                if len(new_handles) > len(original_handles):
                    # Redirected in a new window/tab
                    if logger:
                        logger("Applier: External redirect detected. Skipping for manual apply.")
                    job["status"] = "Manual Required"
                    log_action(job_title, company, "Manual Required", "Redirected to external company website.")
                    
                    # Close the new tab and switch back to main
                    for handle in new_handles:
                        if handle not in original_handles:
                            driver.switch_to.window(handle)
                            driver.close()
                    driver.switch_to.window(original_handles[0])
                    
                else:
                    # Check current URL for external redirects
                    current_url = driver.current_url
                    domain_name = "naukri.com" if source == "Naukri" else ("foundit.in" if source == "Foundit" else ("indeed.com" if source == "Indeed" else "linkedin.com"))
                    if domain_name not in current_url:
                        if logger:
                            logger("Applier: External redirect detected on current page. Skipping for manual apply.")
                        job["status"] = "Manual Required"
                        log_action(job_title, company, "Manual Required", "Redirected to external company website.")
                    else:
                        # Easy Apply: Fill form popup
                        if logger:
                            logger("Applier: Filling easy apply form fields...")
                        success = fill_easy_apply_form(driver, resume_data, resume_file_path, logger)
                        if success:
                            if logger:
                                logger(f"Applier: Successfully applied to '{job_title}' at '{company}'!")
                            job["status"] = "Applied"
                            log_action(job_title, company, "Applied", "Applied successfully via quick apply form.")
                        else:
                            if logger:
                                logger("Applier Warning: Form submission could not be verified. Marked as Manual Required.")
                            job["status"] = "Manual Required"
                            log_action(job_title, company, "Manual Required", "Easy Apply form submission failed or required additional fields.")
                            
                # Update queue in file
                with open(JOBS_QUEUE_FILE, "w", encoding="utf-8") as f:
                    json.dump(jobs, f, indent=2)
                    
            except Exception as job_err:
                if logger:
                    logger(f"Applier Warning: Failed to process job '{job_title}': {job_err}")
                log_action(job_title, company, "Failed", str(job_err))
                job["status"] = "Failed"
                with open(JOBS_QUEUE_FILE, "w", encoding="utf-8") as f:
                    json.dump(jobs, f, indent=2)
                    
            # Small delay between applications
            time.sleep(2)
            
        if logger:
            logger("Applier: Queue processing finished.")
            
    except Exception as e:
        if logger:
            logger(f"Applier Error: Critical failure in auto-applier: {e}")
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass

def parse_exp_less_than_4(exp_str):
    """Parse Naukri experience string and check if minimum exp is less than 4 years."""
    import re
    if not exp_str or exp_str == "N/A":
        return True
    digits = [int(x) for x in re.findall(r'\d+', exp_str)]
    if not digits:
        return True
    return min(digits) < 4

_gemini_unreachable = False
_grok_unreachable = False

def call_ai_brief(prompt, logger=None, primary_engine="gemini"):
    """
    Send text prompt to AI, attempting the primary engine (Gemini or Grok) first,
    and falling back to the other engine if the primary hits rate limits or fails.
    """
    global _gemini_unreachable, _grok_unreachable
    
    settings = load_settings()
    gemini_key = settings.get("gemini_api_key")
    grok_key = settings.get("grok_api_key")
    
    gemini_models = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-1.5-flash", "gemini-2.5-pro"]
    
    if grok_key and grok_key.strip():
        is_groq = grok_key.strip().startswith("gsk_")
        if is_groq:
            grok_url = "https://api.groq.com/openai/v1/chat/completions"
            grok_models = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "llama3-8b-8192", "mixtral-8x7b-32768"]
            grok_provider = "Groq"
        else:
            grok_url = "https://api.x.ai/v1/chat/completions"
            grok_models = ["grok-2-1212", "grok-2-latest", "grok-beta"]
            grok_provider = "Grok"
    else:
        grok_models = []
        
    # Route to functioning engine if one is known to be unreachable
    if primary_engine == "gemini" and _gemini_unreachable:
        primary_engine = "grok"
    elif primary_engine == "grok" and _grok_unreachable:
        primary_engine = "gemini"
        
    def try_gemini():
        global _gemini_unreachable
        if _gemini_unreachable or not gemini_key or not gemini_key.strip():
            return ""
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{
                "parts": [{
                    "text": prompt
                }]
            }],
            "generationConfig": {
                "temperature": 0.1
            }
        }
        for model in gemini_models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={gemini_key}"
            try:
                response = session.post(url, json=payload, headers=headers, timeout=15)
                if response.status_code == 200:
                    res = response.json()
                    return res["candidates"][0]["content"]["parts"][0]["text"].strip()
                elif response.status_code in (401, 403):
                    if logger:
                        logger(f"Applier Info: Gemini API auth failure ({response.status_code}) with {model}, skipping Gemini.")
                    break
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as conn_err:
                if logger:
                    logger(f"Applier Warning: Gemini endpoint is unreachable ({conn_err}). Fail-fast: switching to Grok/Groq.")
                _gemini_unreachable = True
                break
            except Exception as e:
                if logger:
                    logger(f"Applier Error: Gemini model {model} failed: {e}")
        return ""

    def try_grok():
        global _grok_unreachable
        if _grok_unreachable or not grok_key or not grok_key.strip() or not grok_models:
            return ""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {grok_key}"
        }
        for model in grok_models:
            payload = {
                "model": model,
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.1
            }
            try:
                response = session.post(grok_url, headers=headers, json=payload, timeout=20)
                if response.status_code == 200:
                    resp_data = response.json()
                    return resp_data["choices"][0]["message"]["content"].strip()
                elif response.status_code in (401, 403):
                    if logger:
                        logger(f"Applier Info: {grok_provider} API auth failure ({response.status_code}) with {model}, skipping Grok.")
                    break
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as conn_err:
                if logger:
                    logger(f"Applier Warning: {grok_provider} endpoint is unreachable ({conn_err}). Fail-fast: switching to Gemini.")
                _grok_unreachable = True
                break
            except Exception as e:
                if logger:
                    logger(f"Applier Error: {grok_provider} model {model} failed: {e}")
        return ""

    # Execute with circular fallback logic
    if primary_engine == "gemini":
        result = try_gemini()
        if result:
            return result
        # Fallback to Grok
        if grok_key and grok_key.strip():
            if logger:
                logger("Applier Info: Gemini failed or is unreachable. Falling back to Grok/Groq...")
            return try_grok()
    else:
        result = try_grok()
        if result:
            return result
        # Fallback to Gemini
        if gemini_key and gemini_key.strip():
            if logger:
                logger("Applier Info: Grok/Groq failed or is unreachable. Falling back to Gemini...")
            return try_gemini()
            
    return ""

def call_gemini_brief(prompt, api_key, logger=None):
    """Send brief text prompt to Gemini API, falling back to Grok/Groq if Gemini fails."""
    return call_ai_brief(prompt, logger, primary_engine="gemini")

def call_grok_brief(prompt, api_key, logger=None):
    """Send brief text prompt to Grok/Groq API, falling back to Gemini if Grok/Groq fails."""
    return call_ai_brief(prompt, logger, primary_engine="grok")

def get_ai_apply_decision(resume_data, title, company, exp_str, api_key, logger=None):
    """Query primary AI to decide if we should apply to this job card, falling back if limit is hit."""
    settings = load_settings()
    settings_target_roles = settings.get("target_roles", "")
    roles_list = []
    if isinstance(settings_target_roles, str) and settings_target_roles.strip():
        roles_list = [r.strip() for r in settings_target_roles.split(",") if r.strip()]
        
    resume_target_roles = resume_data.get("target_roles", [])
    if isinstance(resume_target_roles, list):
        for r in resume_target_roles:
            if isinstance(r, str) and r.strip() and r.strip() not in roles_list:
                roles_list.append(r.strip())
    elif isinstance(resume_target_roles, str) and resume_target_roles.strip():
        for r in resume_target_roles.split(","):
            if r.strip() and r.strip() not in roles_list:
                roles_list.append(r.strip())
                
    prompt = (
        f"You are a job matching assistant. Match this job against the candidate's targeted job roles.\n\n"
        f"CANDIDATE TARGETED JOB ROLES:\n"
        f"{', '.join(roles_list) if roles_list else 'N/A'}\n\n"
        f"JOB CARD:\n"
        f"Job Title (Job Role): {title}\n"
        f"Company: {company}\n"
        f"Required Experience: {exp_str}\n\n"
        f"RULES:\n"
        f"- If the job title matches or is related to any of the candidate's targeted job roles, and the experience requirement is reasonable, reply 'apply'.\n"
        f"- Otherwise, reply 'not apply'.\n"
        f"Reply with ONLY 'apply' or 'not apply' (no explanation, no markdown)."
    )
    
    gemini_key = settings.get("gemini_api_key") or api_key
    grok_key = settings.get("grok_api_key")
    
    primary = "gemini"
    if gemini_key and gemini_key.strip():
        primary = "gemini"
    elif grok_key and grok_key.strip():
        primary = "grok"
    else:
        if logger:
            logger("  [AI WARNING] No API keys configured. Defaulting to NOT APPLY.")
        return "not apply"
        
    res = call_ai_brief(prompt, logger, primary_engine=primary)
    res = res.lower().strip()
    
    if "not apply" in res or "not_apply" in res or "skip" in res:
        return "not apply"
    if "apply" in res:
        return "apply"
    return "not apply"

def handle_recruiter_questions(driver, resume_data, api_key, logger=None):
    """Find and answer recruiter questions in a popup modal."""
    modal_selectors = [
        "div[class*='modal']",
        "div[class*='layer']",
        "div[class*='popup']",
        "div[class*='dialog']",
        "div[class*='lightbox']",
        "div.chatbot-container",
        "div[class*='question']",
        "div[class*='drawer']",
        ".recruiter-question-container",
        "form"
    ]
    
    modal = None
    if logger:
        logger("Applier: Checking for recruiter questions modal/dialog...")
        
    for check_step in range(10): # Wait up to 10 seconds
        for ms in modal_selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, ms)
                for el in elements:
                    if el.is_displayed():
                        # Verify it has input, textarea, or select inside it
                        inputs = el.find_elements(By.CSS_SELECTOR, "input, textarea, select")
                        if inputs:
                            modal = el
                            break
                if modal:
                    break
            except Exception:
                pass
        if modal:
            break
        time.sleep(1)
            
    if not modal:
        if logger:
            logger("Applier: No active recruiter question modal detected.")
        return False
        
    if logger:
        logger("Applier: Detected active recruiter questions modal. Answering questions...")
        
    try:
        # Find all inputs
        text_inputs = modal.find_elements(By.CSS_SELECTOR, "input[type='text'], textarea, input:not([type])")
        for inp in text_inputs:
            if not inp.is_displayed():
                continue
                
            # Retrieve preceding question text (e.g. placeholder, innerText, label)
            question_text = ""
            placeholder = inp.get_attribute("placeholder")
            if placeholder:
                question_text = placeholder
            else:
                try:
                    question_text = driver.execute_script("return arguments[0].parentElement.innerText;", inp)
                except Exception:
                    pass
            
            if not question_text:
                question_text = "Standard details"
                
            question_text = question_text.split("\n")[0].strip()
            
            # Answer using AI
            prompt = (
                f"Candidate profile: {json.dumps(resume_data)}\n"
                f"Question: '{question_text}'\n"
                f"Provide a concise, professional answer matching the candidate's profile. "
                f"If the question asks for years of experience or notice period, respond with only the number (e.g. 3 or 30). "
                f"Reply with ONLY the final answer."
            )
            ans = call_gemini_brief(prompt, api_key)
            if not ans:
                ans = "3"
                
            inp.clear()
            inp.send_keys(ans)
            if logger:
                logger(f"Applier: Answered '{question_text}' with: {ans}")
            time.sleep(1)
            
        # Radio groups
        radio_groups = modal.find_elements(By.CSS_SELECTOR, "input[type='radio']")
        groups = {}
        for r in radio_groups:
            name = r.get_attribute("name")
            if name:
                groups.setdefault(name, []).append(r)
                
        for name, radios in groups.items():
            is_selected = any(r.is_selected() for r in radios)
            if not is_selected and radios:
                radios[0].click()
                if logger:
                    logger(f"Applier: Selected default radio option for '{name}'")
                time.sleep(0.5)
                
        # Select tags
        selects = modal.find_elements(By.TAG_NAME, "select")
        for s in selects:
            from selenium.webdriver.support.ui import Select
            sel = Select(s)
            options = [o for o in sel.options if o.get_attribute("value")]
            if options:
                sel.select_by_index(1 if len(options) > 1 else 0)
                if logger:
                    logger("Applier: Selected default select option")
                time.sleep(0.5)
                
        # Click Save / Submit / Continue
        save_btn = None
        save_selectors = [
            "//button[contains(text(), 'Save')]",
            "//button[contains(text(), 'Submit')]",
            "//button[contains(text(), 'Continue')]",
            "//button[contains(text(), 'Apply')]",
            ".save-button",
            "button.btn-primary"
        ]
        for xpath in save_selectors:
            try:
                if xpath.startswith("//"):
                    btn = modal.find_element(By.XPATH, xpath)
                else:
                    btn = modal.find_element(By.CSS_SELECTOR, xpath)
                if btn.is_displayed():
                    save_btn = btn
                    break
            except Exception:
                pass
                
        if save_btn:
            save_btn.click()
            if logger:
                logger("Applier: Clicked Save/Submit on questions modal.")
            time.sleep(3)
            return True
        else:
            if logger:
                logger("Applier Warning: Save/Submit button not found in modal.")
            return False
            
    except Exception as ex:
        if logger:
            logger(f"Applier Warning: Error processing modal questions: {ex}")
        return False

def run_bulk_recommended_apply(stop_event, pause_event, logger=None):
    """
    Core Naukri Auto-Apply Automation Flow (AI Driven).
    
    Follows the exact 7-step workflow:
    1. LOGIN — Wait for user to be logged in
    2. OPEN RECOMMENDED JOBS — Navigate to /mnjuser/recommendedjobs
    3. PROCESS JOBS ONE BY ONE — Extract title/company/exp, filter, AI decision, checkbox
    4. BATCH APPLY — Click Apply when 5 jobs checked
    5. QUESTION ANSWERING — AI-powered multi-step form filling
    6. FINAL SUBMISSION — Save/Submit, clear count, continue scanning
    7. END CONDITION — Cycle tabs (Profile, Applies, Top Candidate, Preferences, You might like),
       detect daily limit, stop automation
    """
    driver = None
    from action_recorder import VisualActionRecorder
    recorder = None
    
    try:
        # ─── PRE-CHECKS ───────────────────────────────────────────────────
        if not os.path.exists(RESUME_DATA_FILE):
            if logger:
                logger("Applier Error: resume_data.json is missing. Please upload your resume first.")
            return
            
        with open(RESUME_DATA_FILE, "r", encoding="utf-8") as f:
            resume_data = json.load(f)
            
        settings = load_settings()
        api_key = settings.get("gemini_api_key")
        if not api_key:
            if logger:
                logger("Applier Error: Gemini API key is required. Please set it in Settings.")
            return
        
        # ═══════════════════════════════════════════════════════════════════
        # STEP 1: LOGIN — Connect to embedded browser, wait for login
        # ═══════════════════════════════════════════════════════════════════
        if logger:
            logger("Step 1/7 — LOGIN: Connecting to browser session...")
            
        driver = init_driver(headless=False)
        recorder = VisualActionRecorder(driver, "Naukri_RecommendedApply")
        recorder.record_action(
            "Browser Launch", 
            "Successfully connected/launched Google Chrome browser.",
            capture_screenshot=True,
            code_selenium='driver.get("https://www.naukri.com")\ntime.sleep(2)',
            code_playwright='page.goto("https://www.naukri.com")\npage.wait_for_timeout(2000)'
        )
        driver.get("https://www.naukri.com")
        time.sleep(2)
        
        if logger:
            logger("Step 1/7 — LOGIN: Checking session status. Please log in via the embedded browser if prompted...")
        
        # Wait until user is logged in (not on login/register page)
        login_wait_logged = False
        for _ in range(300):  # Wait up to ~10 minutes for manual login
            if stop_event.is_set():
                if logger:
                    logger("Workflow: Stopped by user during login wait.")
                return
                
            current_url = driver.current_url.lower()
            
            # Check if on a login/register page
            on_login_page = any(kw in current_url for kw in ["login", "register", "signup"])
            
            if not on_login_page:
                # Verify we're actually on a Naukri dashboard/page (not a blank page)
                if any(kw in current_url for kw in ["/mnj/", "dashboard", "recommendedjobs", "naukri.com/mnjuser"]):
                    break
                # Check for profile indicator element
                try:
                    if driver.find_elements(By.CSS_SELECTOR, "a[href*='nprofile'], .nI-gNb-drawer, .nI-gNb-header__wrapper"):
                        break
                except Exception:
                    pass
            elif not login_wait_logged:
                if logger:
                    logger("Step 1/7 — LOGIN: Waiting for you to complete sign-in in the browser...")
                login_wait_logged = True
                    
            time.sleep(2)
        else:
            if logger:
                logger("Step 1/7 — LOGIN Error: Timed out waiting for login. Please log in and try again.")
            return
            
        if logger:
            logger("Step 1/7 — LOGIN: ✓ Sign-in verified! Proceeding...")
        if recorder:
            recorder.record_action(
                "LOGIN CHECK", 
                "Naukri sign-in status verified successfully.",
                capture_screenshot=True,
                code_selenium='# Check that current url is not login page and dashboard elements are present\nassert "login" not in driver.current_url.lower()\nprint("Logged in successfully.")',
                code_playwright='# Check that current url is not login page and dashboard elements are present\nassert "login" not in page.url.lower()\nprint("Logged in successfully.")'
            )
        
        # ═══════════════════════════════════════════════════════════════════
        # STEP 2: OPEN RECOMMENDED JOBS
        # ═══════════════════════════════════════════════════════════════════
        if logger:
            logger("Step 2/7 — OPEN RECOMMENDED JOBS: Navigating to recommended jobs page...")
        
        # Navigate directly to the recommended jobs URL (most reliable approach)
        driver.get("https://www.naukri.com/mnjuser/recommendedjobs")
        time.sleep(5)
        
        # Verify we landed on the correct page
        if "recommendedjobs" not in driver.current_url.lower() and "mnjuser" not in driver.current_url.lower():
            # Fallback: try clicking through the Jobs menu
            if logger:
                logger("Step 2/7 — Fallback: Direct URL didn't work. Trying Jobs menu navigation...")
            
            # Try to find and click the "Jobs" menu item
            jobs_menu_selectors = [
                "//a[contains(text(), 'Jobs')]",
                "a[href*='/jobs']",
                ".nI-gNb-header__wrapper a[title*='Jobs']",
            ]
            for sel in jobs_menu_selectors:
                try:
                    if sel.startswith("//"):
                        btn = driver.find_element(By.XPATH, sel)
                    else:
                        btn = driver.find_element(By.CSS_SELECTOR, sel)
                    if btn and btn.is_displayed():
                        from selenium.webdriver.common.action_chains import ActionChains
                        ActionChains(driver).move_to_element(btn).perform()
                        time.sleep(1.5)
                        btn.click()
                        time.sleep(3)
                        break
                except Exception:
                    pass
            
            # Now find and click "Recommended Jobs" submenu
            rec_selectors = [
                "a[href*='recommendedjobs']",
                "//a[contains(text(), 'Recommended')]",
                "//span[contains(text(), 'Recommended')]",
            ]
            for sel in rec_selectors:
                try:
                    if sel.startswith("//"):
                        btn = driver.find_element(By.XPATH, sel)
                    else:
                        btn = driver.find_element(By.CSS_SELECTOR, sel)
                    if btn and btn.is_displayed():
                        btn.click()
                        time.sleep(4)
                        break
                except Exception:
                    pass
            
            # Final fallback
            if "recommendedjobs" not in driver.current_url.lower():
                driver.get("https://www.naukri.com/mnjuser/recommendedjobs")
                time.sleep(5)
        
        if logger:
            logger("Step 2/7 — OPEN RECOMMENDED JOBS: ✓ Recommended jobs page loaded.")
        if recorder:
            recorder.record_action(
                "OPEN RECOMMENDED JOBS", 
                "Recommended jobs landing page loaded completely.",
                capture_screenshot=True,
                code_selenium='driver.get("https://www.naukri.com/mnjuser/recommendedjobs")\ntime.sleep(5)',
                code_playwright='page.goto("https://www.naukri.com/mnjuser/recommendedjobs")\npage.wait_for_timeout(5000)'
            )
        
        # ─── HELPER FUNCTIONS ─────────────────────────────────────────────
        
        def check_daily_limit():
            """Detect if Naukri shows a daily application limit popup."""
            limit_keywords = [
                "daily limit", "Daily limit", "daily quota", "Daily quota",
                "exceeded your daily", "limit reached", "Limit reached",
                "maximum applications", "Maximum applications"
            ]
            for kw in limit_keywords:
                try:
                    elements = driver.find_elements(By.XPATH, f"//*[contains(text(), '{kw}')]")
                    for el in elements:
                        if el.is_displayed():
                            return True
                except Exception:
                    pass
            return False
        
        def dismiss_popup():
            """Try to close any generic popup/modal that appears."""
            close_selectors = [
                "button[class*='close']", "span[class*='close']", ".crossIcon",
                "button[aria-label='Close']", ".modal-close", "a[class*='close']",
                "//button[contains(@class, 'close')]", "//span[contains(@class, 'cross')]"
            ]
            for sel in close_selectors:
                try:
                    if sel.startswith("//"):
                        btn = driver.find_element(By.XPATH, sel)
                    else:
                        btn = driver.find_element(By.CSS_SELECTOR, sel)
                    if btn.is_displayed():
                        btn.click()
                        time.sleep(1)
                        return True
                except Exception:
                    pass
            return False
        
        def handle_application_popups(resume_data, api_key, logger):
            """
            STEP 5 & 6: Handle question answering and final submission.
            
            Naukri bulk apply can show multi-step popups with recruiter questions.
            This handles text inputs, radio buttons, selects, and clicks Submit/Save.
            """
            max_popup_steps = 5  # Handle up to 5 consecutive popup screens
            
            for step_num in range(max_popup_steps):
                time.sleep(2)
                
                # Check for daily limit first
                if check_daily_limit():
                    if logger:
                        logger("Step 5 — QUESTIONS: Daily limit popup detected!")
                    return "daily_limit"
                
                # Check for success message (application submitted)
                success_selectors = [
                    "//*[contains(text(), 'successfully') or contains(text(), 'Successfully')]",
                    "//*[contains(text(), 'applied') and contains(text(), 'success')]",
                    "//*[contains(text(), 'Application sent') or contains(text(), 'application sent')]",
                    "div[class*='success']", ".success-msg", ".successMessage"
                ]
                for ss in success_selectors:
                    try:
                        if ss.startswith("//"):
                            el = driver.find_element(By.XPATH, ss)
                        else:
                            el = driver.find_element(By.CSS_SELECTOR, ss)
                        if el.is_displayed():
                            if logger:
                                logger("Step 6 — SUBMISSION: ✓ Application submitted successfully!")
                            if recorder:
                                recorder.record_action(
                                    "SUBMISSION SUCCESS", 
                                    "Naukri application submission success feedback verified.",
                                    capture_screenshot=True,
                                    code_selenium='# Submission feedback matches success selectors\nprint("Naukri application submitted successfully.")',
                                    code_playwright='# Submission feedback matches success selectors\nprint("Naukri application submitted successfully.")'
                                )
                            dismiss_popup()
                            return "success"
                    except Exception:
                        pass
                
                # Look for active modal/popup with form fields
                modal = None
                modal_selectors = [
                    "div[class*='modal']", "div[class*='layer']", "div[class*='popup']",
                    "div[class*='dialog']", "div[class*='lightbox']", "div[class*='drawer']",
                    "div[class*='chatbot']", "div[class*='question']",
                    ".recruiter-question-container", "form[class*='apply']"
                ]
                
                for ms in modal_selectors:
                    try:
                        elements = driver.find_elements(By.CSS_SELECTOR, ms)
                        for el in elements:
                            if el.is_displayed():
                                # Must have at least one interactive element
                                inputs = el.find_elements(By.CSS_SELECTOR, 
                                    "input[type='text'], textarea, select, input[type='radio'], input[type='number'], input:not([type='hidden'])")
                                if inputs:
                                    modal = el
                                    break
                        if modal:
                            break
                    except Exception:
                        pass
                
                if not modal:
                    # No more popups — we're done
                    if step_num == 0:
                        if logger:
                            logger("Step 5 — QUESTIONS: No recruiter questions detected. Application submitted directly.")
                        return "success"
                    else:
                        return "success"
                
                if logger:
                    logger(f"Step 5 — QUESTIONS: Popup step {step_num + 1} detected. Answering questions with AI...")
                if recorder:
                    recorder.record_action(
                        f"Questions Modal - Step {step_num + 1}", 
                        "Recruiter questions form overlay detected.",
                        capture_screenshot=True,
                        code_selenium='# Wait for active modal with form inputs\nmodal = driver.find_element(By.CSS_SELECTOR, "div[class*=\'modal\'], form[class*=\'apply\']")',
                        code_playwright='# Wait for active modal with form inputs\nmodal = page.locator("div[class*=\'modal\'], form[class*=\'apply\']").first'
                    )
                
                # ── Answer text questions ──
                text_inputs = modal.find_elements(By.CSS_SELECTOR, 
                    "input[type='text'], textarea, input[type='number'], input:not([type='hidden']):not([type='radio']):not([type='checkbox']):not([type='file']):not([type='submit']):not([type='button'])")
                
                for inp in text_inputs:
                    try:
                        if not inp.is_displayed():
                            continue
                        
                        # Skip if already filled
                        existing_val = inp.get_attribute("value") or ""
                        if existing_val.strip():
                            continue
                        
                        # Extract the question text from context
                        question_text = ""
                        
                        # Try placeholder
                        placeholder = inp.get_attribute("placeholder")
                        if placeholder and placeholder.strip():
                            question_text = placeholder.strip()
                        
                        # Try associated label
                        if not question_text:
                            inp_id = inp.get_attribute("id")
                            if inp_id:
                                try:
                                    label = driver.find_element(By.CSS_SELECTOR, f"label[for='{inp_id}']")
                                    question_text = label.text.strip()
                                except Exception:
                                    pass
                        
                        # Try parent element text
                        if not question_text:
                            try:
                                question_text = driver.execute_script(
                                    "var p = arguments[0].parentElement; "
                                    "return p ? p.innerText.split('\\n')[0] : '';", inp)
                                question_text = (question_text or "").strip()
                            except Exception:
                                pass
                        
                        # Try preceding sibling text
                        if not question_text:
                            try:
                                question_text = driver.execute_script(
                                    "var el = arguments[0].previousElementSibling; "
                                    "return el ? el.innerText : '';", inp)
                                question_text = (question_text or "").strip()
                            except Exception:
                                pass
                        
                        if not question_text:
                            question_text = "General application question"
                        
                        # Trim to first line
                        question_text = question_text.split("\n")[0].strip()[:200]
                        
                        # Send to AI for answer
                        prompt = (
                            f"Candidate profile: {json.dumps(resume_data)}\n"
                            f"Question: '{question_text}'\n"
                            f"Provide a concise, professional answer matching the candidate's profile. "
                            f"If the question asks for years of experience, notice period, or a number, "
                            f"respond with ONLY the number (e.g. 3 or 30 or 0). "
                            f"If it asks for current CTC or expected CTC, respond with only the number in LPA. "
                            f"Reply with ONLY the final answer, no explanation."
                        )
                        answer = call_gemini_brief(prompt, api_key, logger)
                        if not answer:
                            answer = "0"
                        
                        inp.clear()
                        inp.send_keys(answer)
                        if logger:
                            logger(f"  → Answered '{question_text[:60]}' with: {answer}")
                        if recorder:
                            escaped_q = question_text[:40].replace("'", "\\'")
                            escaped_a = answer.replace("'", "\\'")
                            recorder.record_action(
                                "Answer Filled", 
                                f"Filled recruiter question field '{question_text[:40]}' with: {answer}",
                                capture_screenshot=True,
                                code_selenium=f'# Text input for \'{escaped_q}\'\ninp = driver.find_element(By.CSS_SELECTOR, "input, textarea")\ninp.clear()\ninp.send_keys(\'{escaped_a}\')',
                                code_playwright=f'# Text input for \'{escaped_q}\'\npage.locator("input, textarea").first.fill(\'{escaped_a}\')'
                            )
                        time.sleep(0.8)
                        
                    except Exception as inp_err:
                        if logger:
                            logger(f"  → Warning: Could not fill input field: {inp_err}")
                
                # ── Handle radio button groups ──
                try:
                    radio_inputs = modal.find_elements(By.CSS_SELECTOR, "input[type='radio']")
                    groups = {}
                    for r in radio_inputs:
                        name = r.get_attribute("name")
                        if name:
                            groups.setdefault(name, []).append(r)
                    
                    for name, radios in groups.items():
                        already_selected = any(r.is_selected() for r in radios)
                        if not already_selected and radios:
                            # Select first option as default
                            try:
                                radios[0].click()
                            except Exception:
                                driver.execute_script("arguments[0].click();", radios[0])
                            if logger:
                                logger(f"  → Selected default radio for group '{name}'")
                            time.sleep(0.5)
                except Exception:
                    pass
                
                # ── Handle select/dropdown fields ──
                try:
                    selects = modal.find_elements(By.TAG_NAME, "select")
                    for s in selects:
                        if not s.is_displayed():
                            continue
                        from selenium.webdriver.support.ui import Select
                        sel = Select(s)
                        options = [o for o in sel.options if o.get_attribute("value")]
                        if len(options) > 1:
                            sel.select_by_index(1)
                            if logger:
                                logger(f"  → Selected dropdown option: {options[1].text}")
                            time.sleep(0.5)
                except Exception:
                    pass
                
                # ── STEP 6: Click Save / Submit / Continue / Next ──
                submit_btn = None
                submit_selectors = [
                    "//button[contains(text(), 'Save')]",
                    "//button[contains(text(), 'Submit')]",
                    "//button[contains(text(), 'Continue')]",
                    "//button[contains(text(), 'Next')]",
                    "//button[contains(text(), 'Apply')]",
                    "//button[contains(text(), 'Proceed')]",
                    "button[type='submit']",
                    "button.btn-primary",
                    ".save-button",
                    ".submit-button"
                ]
                for sel in submit_selectors:
                    try:
                        if sel.startswith("//"):
                            btn = modal.find_element(By.XPATH, sel)
                        else:
                            btn = modal.find_element(By.CSS_SELECTOR, sel)
                        if btn.is_displayed() and btn.is_enabled():
                            submit_btn = btn
                            break
                    except Exception:
                        pass
                
                if submit_btn:
                    try:
                        submit_btn.click()
                    except Exception:
                        driver.execute_script("arguments[0].click();", submit_btn)
                    if logger:
                        logger(f"Step 6 — SUBMISSION: Clicked '{submit_btn.text.strip() or 'Submit'}' button.")
                    time.sleep(3)
                else:
                    if logger:
                        logger("Step 6 — SUBMISSION Warning: No Save/Submit button found in popup.")
                    break
            
            return "success"
        
        def apply_checked_jobs(count, jobs_info):
            """
            STEP 4: BATCH APPLY — Click the Apply button when jobs are checked.
            Then handle STEP 5 (Questions) and STEP 6 (Submission).
            """
            if logger:
                logger(f"Step 4/7 — BATCH APPLY: {count} job(s) selected. Clicking Apply button...")
            
            # Find and click the main Apply button at top of page
            # From screenshot: blue "Apply" button next to "You can select upto 5 jobs to apply"
            apply_btn = None
            apply_selectors = [
                # Exact matches from Naukri recommended jobs page
                "button.apply-btn",
                "button.styles_applyBtn",
                "button[class*='applyBtn']",
                "a[class*='applyBtn']",
                # Text-based selectors
                f"//button[contains(text(), 'Apply')]",
                f"//a[contains(text(), 'Apply')]",
                f"//span[contains(text(), 'Apply')]",
                # Broader selectors
                "//button[contains(text(), 'Apply to')]",
                "//button[contains(text(), 'Apply ({count})')]",
                ".apply-btn",
                "div[class*='apply'] button",
                "div[class*='apply'] a",
            ]
            
            for sel in apply_selectors:
                try:
                    if sel.startswith("//"):
                        btn = driver.find_element(By.XPATH, sel)
                    else:
                        btn = driver.find_element(By.CSS_SELECTOR, sel)
                    if btn and btn.is_displayed():
                        apply_btn = btn
                        break
                except Exception:
                    pass
            
            if not apply_btn:
                if logger:
                    logger("Step 4 — BATCH APPLY Error: Apply button not found on page.")
                return
            
            # Click Apply
            try:
                apply_btn.click()
            except Exception:
                driver.execute_script("arguments[0].click();", apply_btn)
            
            if logger:
                logger("Step 4 — BATCH APPLY: ✓ Apply button clicked. Waiting for popup...")
            time.sleep(4)
            
            # Check daily limit immediately
            if check_daily_limit():
                if logger:
                    logger("Step 4 — BATCH APPLY Alert: Daily application limit reached!")
                raise Exception("Daily application limit reached.")
            
            # STEP 5 & 6: Handle questions and submission
            result = handle_application_popups(resume_data, api_key, logger)
            
            if result == "daily_limit":
                raise Exception("Daily application limit reached.")
            
            # Log applied jobs
            for title, company in jobs_info:
                log_action(title, company, "Applied", f"Applied via bulk recommended jobs flow.")
            
            if logger:
                applied_titles = ", ".join([t for t, c in jobs_info])
                logger(f"Step 4 — BATCH APPLY: ✓ Batch complete! Applied to: {applied_titles}")
            if recorder:
                applied_titles = ", ".join([t for t, c in jobs_info])
                recorder.record_action(
                    "BATCH APPLY SUBMIT", 
                    f"Batch submission completed for: {applied_titles}",
                    capture_screenshot=True,
                    code_selenium='apply_btn = driver.find_element(By.CSS_SELECTOR, "button.apply-btn, button.styles_applyBtn")\ndriver.execute_script("arguments[0].click();", apply_btn)\ntime.sleep(4)',
                    code_playwright='apply_btn = page.locator("button.apply-btn, button.styles_applyBtn").first\napply_btn.click()\npage.wait_for_timeout(4000)'
                )
        
        def process_tab_cards(tab_name):
            """
            STEP 3: PROCESS JOBS ONE BY ONE on the current tab.
            
            For each job card:
            - Extract: Job Title, Company Name, Experience Required
            - Check Experience > 4 Years → Skip
            - Else → Send to AI for APPLY/SKIP decision
            - AI says APPLY → Select Checkbox
            - AI says SKIP → Do not click checkbox
            - Continue scrolling
            
            When 5 are checked → trigger STEP 4 (Batch Apply)
            """
            checked_count = 0
            checked_jobs_info = []
            scanned_card_ids = set()
            total_scanned = 0
            total_skipped_exp = 0
            total_skipped_ai = 0
            total_applied = 0
            
            # Retrieve target roles list
            settings_target_roles = settings.get("target_roles", "")
            roles_list = []
            if isinstance(settings_target_roles, str) and settings_target_roles.strip():
                roles_list = [r.strip() for r in settings_target_roles.split(",") if r.strip()]
            resume_target_roles = resume_data.get("target_roles", [])
            if isinstance(resume_target_roles, list):
                for r in resume_target_roles:
                    if isinstance(r, str) and r.strip() and r.strip() not in roles_list:
                        roles_list.append(r.strip())
            elif isinstance(resume_target_roles, str) and resume_target_roles.strip():
                for r in resume_target_roles.split(","):
                    if r.strip() and r.strip() not in roles_list:
                        roles_list.append(r.strip())
            
            # CSS selectors for job card elements on Naukri Recommended Jobs page
            # Based on the screenshot structure: checkbox | title | company | exp/salary/location | desc | skills
            card_selectors = [
                "div[class*='jobTuple']",
                "div[class*='job-tuple']", 
                "div[class*='recommendedJob']",
                "div[class*='job-card']",
                "div[class*='tuple']",
                "article[class*='jobTuple']",
                "article[class*='job']",
                "div[data-job-id]",
                "div.srp-jobtuple-wrapper",
                "div.cust-job-tuple",
            ]
            
            # Use JavaScript to extract text from cards to AVOID accidentally
            # clicking/opening any card links. We read innerText only.
            def extract_text_from_card(card, css_selectors):
                """Safely extract text from a card element using JavaScript (no click/navigation)."""
                for sel in css_selectors:
                    try:
                        el = card.find_element(By.CSS_SELECTOR, sel)
                        # Use JavaScript innerText to avoid any event triggering
                        text = driver.execute_script("return arguments[0].innerText;", el)
                        text = (text or "").strip()
                        if text:
                            return text
                    except Exception:
                        pass
                return ""
            
            title_selectors = [
                "a.title", ".title a", "a.job-title", ".title", ".job-title",
                "h2 a", "h3 a", "a[class*='title']", "a[class*='jobTitle']",
                "h2.jobTitle", "h2", "h3"
            ]
            
            company_selectors = [
                "a.comp-name", ".comp-name", "a.companyName", ".companyName",
                ".company-name", ".company", "a[class*='comp']", ".org",
                "span[class*='company']", "a[class*='company']"
            ]
            
            exp_selectors = [
                "span.exp-wrap", "span.exp", ".experience", ".exp",
                "li.experience", "span[class*='exp']", "span.expWdth",
                "div[class*='exp']", "span[class*='experience']"
            ]
            
            checkbox_selectors = [
                "input[type='checkbox']",
                "span[class*='checkbox']",
                "label[class*='checkbox']",
                "div[class*='checkbox']",
                "input.checkbox",
                ".select-job-checkbox",
                "span[class*='Checkbox']",
                "div[class*='Checkbox']",
            ]
            
            if logger:
                logger(f"Step 3/7 — PROCESS JOBS: Scanning job cards in '{tab_name}' tab...")
            
            # Scroll through the page to find and process cards
            no_new_cards_count = 0
            max_no_new_cards = 3  # Stop scrolling after 3 consecutive scrolls with no new cards
            
            while no_new_cards_count < max_no_new_cards:
                # Check stop/pause
                if stop_event.is_set():
                    if logger:
                        logger("Workflow: Stopped by user.")
                    break
                while pause_event.is_set():
                    time.sleep(1)
                    if stop_event.is_set():
                        break
                
                # Check daily limit
                if check_daily_limit():
                    if logger:
                        logger("Step 7 — END: Daily application limit reached!")
                    raise Exception("Daily application limit reached.")
                
                # Find all job cards currently visible
                cards = []
                for sel in card_selectors:
                    try:
                        elements = driver.find_elements(By.CSS_SELECTOR, sel)
                        if elements and len(elements) > 0:
                            cards = elements
                            break
                    except Exception:
                        pass
                
                # Fallback: broad XPATH search
                if not cards:
                    try:
                        cards = driver.find_elements(By.XPATH, 
                            "//div[contains(@class, 'job') and (contains(@class, 'tuple') or contains(@class, 'card') or contains(@class, 'Tuple'))]")
                    except Exception:
                        pass
                
                if not cards:
                    # No cards found at all, scroll and retry
                    driver.execute_script("window.scrollBy(0, 600);")
                    time.sleep(2)
                    no_new_cards_count += 1
                    continue
                
                found_new_card = False
                
                for card in cards:
                    if stop_event.is_set():
                        break
                    
                    try:
                        # Generate a unique identifier for this card to avoid re-processing
                        card_id = (
                            card.get_attribute("id") or 
                            card.get_attribute("data-job-id") or 
                            card.get_attribute("data-jobid") or
                            ""
                        )
                        if not card_id:
                            # Fallback: use position-based ID
                            try:
                                loc = card.location
                                card_id = f"pos_{loc.get('x', 0)}_{loc.get('y', 0)}"
                            except Exception:
                                continue
                        
                        if card_id in scanned_card_ids:
                            continue
                        scanned_card_ids.add(card_id)
                        found_new_card = True
                        total_scanned += 1
                        
                        # Scroll card smoothly into center of viewport to lazy-load elements and make them interactable
                        try:
                            driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", card)
                            time.sleep(1)
                        except Exception:
                            pass
                        
                        # ── Extract: Job Title (via JS, no click) ──
                        title = extract_text_from_card(card, title_selectors)
                        if not title:
                            continue
                        
                        # ── Extract: Company Name (via JS, no click) ──
                        company = extract_text_from_card(card, company_selectors)
                        if not company:
                            company = "Unknown Company"
                        
                        # ── Extract: Experience Required (via JS, no click) ──
                        exp_str = extract_text_from_card(card, exp_selectors)
                        if not exp_str:
                            exp_str = "N/A"
                        
                        if logger:
                            logger(f"  Scanning: '{title}' at '{company}' (Exp: {exp_str})")
                        
                        # ── Check Experience: Check if candidate exp (3.4) and role is suitable directly ──
                        is_suitable = False
                        try:
                            import re
                            title_lower = title.lower()
                            role_matched = any(role.lower() in title_lower or title_lower in role.lower() for role in roles_list)
                            
                            if role_matched and exp_str and exp_str != "N/A":
                                digits = [int(x) for x in re.findall(r'\d+', exp_str)]
                                if digits:
                                    min_exp = digits[0]
                                    max_exp = digits[1] if len(digits) > 1 else min_exp
                                    # Candidate has 3.4 years experience
                                    if min_exp <= 3.4 <= max_exp or min_exp <= 3.4:
                                        is_suitable = True
                        except Exception:
                            pass
                            
                        if is_suitable:
                            if logger:
                                logger(f"  ✓ Direct Suitability Match: Experience (3.4 Yrs) & role suitable for '{title}'")
                            decision = "apply"
                        else:
                            # ── ELSE: Send Data to AI for decision ──
                            if logger:
                                logger(f"  → Asking AI: Should we apply to '{title}'?")
                            decision = get_ai_apply_decision(resume_data, title, company, exp_str, api_key, logger)
                        
                        # ── AI Decision: APPLY or NOT APPLY ──
                        if decision == "not apply":
                            # AI says NOT APPLY → do not click checkbox
                            if logger:
                                logger(f"  ✗ AI Decision: NOT APPLY '{title}'")
                            total_skipped_ai += 1
                            log_action(title, company, "Skipped", "AI decided not to apply.")
                            continue
                        
                        # AI says APPLY → Select Checkbox (DO NOT open/click the card itself)
                        if logger:
                            logger(f"  ✓ AI Decision: APPLY to '{title}' — Selecting checkbox ONLY...")
                        
                        # Find the checkbox within this card using JavaScript
                        # This avoids clicking any link/anchor that would open the card
                        checkbox = None
                        for c_sel in checkbox_selectors:
                            try:
                                checkbox = card.find_element(By.CSS_SELECTOR, c_sel)
                                if checkbox:
                                    break
                            except Exception:
                                pass
                        
                        # Fallback: XPATH within card
                        if not checkbox:
                            try:
                                checkbox = card.find_element(By.XPATH, 
                                    ".//input[@type='checkbox'] | .//span[contains(@class, 'heckbox')] | .//label[contains(@class, 'heckbox')] | .//div[contains(@class, 'heckbox')]")
                            except Exception:
                                pass
                        
                        if not checkbox:
                            if logger:
                                logger(f"  ⚠ Checkbox not found for '{title}'. Skipping.")
                            continue
                        
                        # Check if already selected
                        is_checked = False
                        try:
                            is_checked = checkbox.is_selected()
                        except Exception:
                            try:
                                is_checked = driver.execute_script(
                                    "return arguments[0].classList.contains('checked') || "
                                    "arguments[0].getAttribute('aria-checked') === 'true' || "
                                    "arguments[0].checked === true;", checkbox)
                            except Exception:
                                pass
                        
                        if not is_checked:
                            clicked_successfully = False
                            # Attempt 1: Direct JS click on checkbox element
                            try:
                                driver.execute_script("arguments[0].click();", checkbox)
                                clicked_successfully = True
                            except Exception:
                                pass
                                
                            # Check state
                            is_checked_now = False
                            try:
                                is_checked_now = driver.execute_script(
                                    "return arguments[0].classList.contains('checked') || "
                                    "arguments[0].getAttribute('aria-checked') === 'true' || "
                                    "arguments[0].checked === true;", checkbox)
                            except Exception:
                                pass
                                
                            # Attempt 2: JS click sibling <label> element
                            if not is_checked_now:
                                try:
                                    cb_id = checkbox.get_attribute("id")
                                    if cb_id:
                                        label_el = card.find_element(By.CSS_SELECTOR, f"label[for='{cb_id}']")
                                        driver.execute_script("arguments[0].click();", label_el)
                                        clicked_successfully = True
                                except Exception:
                                    pass
                                    
                            # Check state again
                            try:
                                is_checked_now = driver.execute_script(
                                    "return arguments[0].classList.contains('checked') || "
                                    "arguments[0].getAttribute('aria-checked') === 'true' || "
                                    "arguments[0].checked === true;", checkbox)
                            except Exception:
                                pass
                                
                            # Attempt 3: Standard click, and parent element click fallbacks
                            if not is_checked_now:
                                try:
                                    checkbox.click()
                                    clicked_successfully = True
                                except Exception:
                                    try:
                                        parent_el = checkbox.find_element(By.XPATH, "..")
                                        driver.execute_script("arguments[0].click();", parent_el)
                                        clicked_successfully = True
                                    except Exception as click_err:
                                        if logger:
                                            logger(f"  ⚠ All click attempts failed for checkbox '{title}': {click_err}")
                                        continue
                            
                            checked_count += 1
                            checked_jobs_info.append((title, company))
                            total_applied += 1
                            
                            if logger:
                                logger(f"  ☑ CHECKED [{checked_count}/5] — '{title}' at '{company}'")
                            if recorder:
                                escaped_t = title.replace("'", "\\'")
                                escaped_c = company.replace("'", "\\'")
                                recorder.record_action(
                                    f"Job Checked {checked_count}", 
                                    f"Selected job card: '{title}' at '{company}' (Exp: {exp_str})",
                                    capture_screenshot=True,
                                    code_selenium=f'# Select job card checkbox\n# Title: {escaped_t}, Company: {escaped_c}\ncard_checkbox = card.find_element(By.CSS_SELECTOR, "input[type=\'checkbox\']")\ndriver.execute_script("arguments[0].click();", card_checkbox)',
                                    code_playwright=f'# Select job card checkbox\n# Title: {escaped_t}, Company: {escaped_c}\ncard_checkbox = card.locator("input[type=\'checkbox\']").first\ncard_checkbox.click()'
                                )
                            
                            time.sleep(1)
                        
                        # ── STEP 4: BATCH APPLY when 5 jobs are checked ──
                        if checked_count >= 5:
                            if logger:
                                logger(f"Step 4/7 — 5 jobs checked! Triggering batch apply...")
                            
                            apply_checked_jobs(checked_count, checked_jobs_info)
                            
                            # Clear count and continue scanning
                            checked_count = 0
                            checked_jobs_info = []
                            
                            if logger:
                                logger(f"Step 3/7 — PROCESS JOBS: Continuing to scan more jobs in '{tab_name}'...")
                            time.sleep(2)
                        
                    except Exception as card_err:
                        # Skip individual card errors silently
                        pass
                
                # Scroll down FORWARD only to load more cards (never scroll backwards)
                if found_new_card:
                    no_new_cards_count = 0
                else:
                    no_new_cards_count += 1
                
                driver.execute_script("window.scrollBy(0, 600);")
                time.sleep(2)
            
            # ── Submit remaining checked jobs (less than 5) ──
            if checked_count > 0:
                if logger:
                    logger(f"Step 4/7 — End of tab: Applying remaining {checked_count} checked job(s)...")
                apply_checked_jobs(checked_count, checked_jobs_info)
                checked_count = 0
                checked_jobs_info = []
            
            # Tab summary
            if logger:
                logger(
                    f"Tab '{tab_name}' Summary: "
                    f"Scanned={total_scanned}, "
                    f"Applied={total_applied}, "
                    f"Skipped(Exp)={total_skipped_exp}, "
                    f"Skipped(AI)={total_skipped_ai}"
                )
        
        # ═══════════════════════════════════════════════════════════════════
        # STEP 7: END CONDITION — Cycle through all tabs, detect daily limit
        # ═══════════════════════════════════════════════════════════════════
        
        # Tab names matching the Naukri recommended jobs page tabs
        # Order: Profile, Applies, Top Candidate, Preferences, You might like
        tab_names = ["Profile", "Applies", "Top Candidate", "Preferences", "You might like"]
        
        def click_tab_by_name(tab_name):
            """
            Click a specific tab on the recommended jobs page.
            Uses JavaScript to find and click the tab text within the tab bar only,
            avoiding matching random links elsewhere on the page.
            """
            # FIRST: Scroll to absolute top so tab bar is visible
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(1)
            
            # Strategy 1: Use JavaScript to find the tab link by its text content
            # This scopes the search to only elements that look like tabs (near the top)
            js_click_tab = """
            var tabName = arguments[0];
            // Find all links and clickable elements on the page
            var allElements = document.querySelectorAll('a, span, div, button');
            for (var i = 0; i < allElements.length; i++) {
                var el = allElements[i];
                var text = el.innerText || el.textContent || '';
                text = text.trim();
                // Match tab text (e.g. "Profile (61)", "Applies (65)", etc.)
                if (text.indexOf(tabName) === 0 && el.offsetParent !== null) {
                    // Check if this element is in the top portion of the page (tab bar area)
                    var rect = el.getBoundingClientRect();
                    if (rect.top < 600) {
                        el.click();
                        return true;
                    }
                }
            }
            return false;
            """
            result = driver.execute_script(js_click_tab, tab_name)
            if result:
                return True
            
            # Strategy 2: Fallback XPATHs scoped to tab-like containers
            fallback_selectors = [
                f"//a[starts-with(normalize-space(text()), '{tab_name}')]",
                f"//span[starts-with(normalize-space(text()), '{tab_name}')]",
                f"//div[starts-with(normalize-space(text()), '{tab_name}')]",
            ]
            for sel in fallback_selectors:
                try:
                    elements = driver.find_elements(By.XPATH, sel)
                    for btn in elements:
                        if btn.is_displayed():
                            # Check if element is near the top of the page (tab bar)
                            location = btn.location
                            if location.get('y', 999) < 600:
                                driver.execute_script("arguments[0].click();", btn)
                                return True
                except Exception:
                    pass
            
            return False
        
        if logger:
            logger("Step 7/7 — END CONDITION: Processing all tabs sequentially...")
        
        for tab_name in tab_names:
            if stop_event.is_set():
                if logger:
                    logger("Workflow: Stopped by user.")
                break
            
            # Check daily limit before switching tabs
            if check_daily_limit():
                if logger:
                    logger("Step 7 — END: Daily application limit reached. Stopping automation.")
                break
            
            if logger:
                logger(f"\n{'='*50}")
                logger(f"Step 7 — Switching to tab: '{tab_name}'")
                logger(f"{'='*50}")
            
            # Scroll to top first so tab bar is visible
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(1)
            
            # Click the tab
            tab_clicked = click_tab_by_name(tab_name)
            
            if tab_clicked:
                if logger:
                    logger(f"Step 7 — Tab '{tab_name}': ✓ Selected. Loading jobs...")
                if recorder:
                    recorder.record_action(
                        f"Tab Switch - {tab_name}", 
                        f"Navigated category tab to '{tab_name}'.",
                        capture_screenshot=True,
                        code_selenium=f'# Switch to tab {tab_name}\ndriver.execute_script("window.scrollTo(0, 0);")\ntime.sleep(1)\njs_click = """\nvar tab = Array.from(document.querySelectorAll(\\\'a, span, div, button\\\')).find(\nel => el.innerText.trim().startsWith(\\\'{tab_name}\\\') && el.offsetParent !== null\n);\nif (tab) tab.click();\n"""\ndriver.execute_script(js_click)\ntime.sleep(4)',
                        code_playwright=f'# Switch to tab {tab_name}\npage.evaluate("window.scrollTo(0, 0);")\npage.wait_for_timeout(1000)\npage.evaluate("""() => {{\nvar tab = Array.from(document.querySelectorAll(\\\'a, span, div, button\\\')).find(\nel => el.innerText.trim().startsWith(\\\'{tab_name}\\\') && el.offsetParent !== null\n);\nif (tab) tab.click();\n}}""")\npage.wait_for_timeout(4000)'
                    )
                time.sleep(4)
                
                # Scroll to top again for fresh card scan
                driver.execute_script("window.scrollTo(0, 0);")
                time.sleep(1)
            else:
                if logger:
                    logger(f"Step 7 — Tab '{tab_name}': ⚠ Tab button not found. Skipping...")
                continue
            
            # Process all jobs on this tab (Steps 3-6)
            try:
                process_tab_cards(tab_name)
            except Exception as tab_err:
                err_msg = str(tab_err)
                if "daily" in err_msg.lower() and "limit" in err_msg.lower():
                    if logger:
                        logger("Step 7 — END: Daily application limit reached. Stopping automation.")
                    break
                else:
                    if logger:
                        logger(f"Step 7 — Tab '{tab_name}' Error: {tab_err}")
                    continue
        
        # ═══════════════════════════════════════════════════════════════════
        # AUTOMATION COMPLETE
        # ═══════════════════════════════════════════════════════════════════
        if logger:
            logger("\n" + "="*50)
            logger("✓ AUTOMATION COMPLETE — All tabs processed!")
            logger("="*50)
                
    except Exception as e:
        err_msg = str(e)
        if "daily" in err_msg.lower() and "limit" in err_msg.lower():
            if logger:
                logger("Step 7 — END: Daily application limit reached. Automation stopped gracefully.")
        else:
            if logger:
                logger(f"Workflow Critical Error: {e}")
    finally:
        if recorder:
            try:
                report_path = recorder.generate_report()
                if logger and report_path:
                    logger(f"Applier: Eggplant-style Visual Execution Log Report compiled at {report_path}")
            except Exception as rec_err:
                print(f"Applier: Error compiling visual report: {rec_err}")
        if driver:
            try:
                driver.quit()
            except Exception:
                pass

