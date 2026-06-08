import os
import json
import time
import winreg
import pickle
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from settings import DATA_DIR

JOBS_QUEUE_FILE = os.path.join(DATA_DIR, "jobs_queue.json")
COOKIES_FILE = os.path.join(DATA_DIR, "cookies.json")
RESUME_DATA_FILE = os.path.join(DATA_DIR, "resume_data.json")

def get_chrome_major_version():
    """Query Windows registry to find the installed Google Chrome major version."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon") as key:
            version, _ = winreg.QueryValueEx(key, "version")
            return int(version.split('.')[0])
    except Exception:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Google Chrome") as key:
                version, _ = winreg.QueryValueEx(key, "DisplayVersion")
                return int(version.split('.')[0])
        except Exception:
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe") as key:
                    # Just return a default or None if we can't extract version directly from file
                    return None
            except Exception:
                return None

def get_chrome_executable_path():
    """Locate the Google Chrome executable path on Windows."""
    import winreg
    for hkey in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            with winreg.OpenKey(hkey, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe") as key:
                path, _ = winreg.QueryValueEx(key, "")
                if os.path.exists(path):
                    return path
        except Exception:
            pass
            
    standard_paths = [
        os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "Google\\Chrome\\Application\\chrome.exe"),
        os.path.join(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"), "Google\\Chrome\\Application\\chrome.exe"),
        os.path.join(os.environ.get("LocalAppData", "C:\\Users\\default\\AppData\\Local"), "Google\\Chrome\\Application\\chrome.exe")
    ]
    for path in standard_paths:
        if os.path.exists(path):
            return path
            
    return None

def is_port_active(port=9222):
    """Check if the given port is open on localhost."""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.2)
    active = s.connect_ex(('127.0.0.1', port)) == 0
    s.close()
    return active

def kill_our_chrome_processes():
    """Safely terminate only Chrome processes launched by this application (using our profile or debugging port)."""
    import os
    profile_dir = os.path.abspath(os.path.join(DATA_DIR, "chrome_profile"))
    
    try:
        import psutil
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                name = proc.info['name']
                if name and 'chrome' in name.lower():
                    cmdline = proc.info['cmdline'] or []
                    cmdline_str = " ".join(cmdline).lower()
                    if "9222" in cmdline_str or "chrome_profile" in cmdline_str:
                        proc.kill()
                        print(f"System: Killed orphaned Chrome process PID {proc.info['pid']}")
            except Exception:
                pass
    except Exception as e:
        print(f"System: Error listing/killing processes with psutil: {e}")

def launch_chrome_debugging(port=9222, url=None):
    """Launch Google Chrome with remote debugging enabled, optionally opening a URL."""
    # Force kill any orphaned Chrome processes using our profile or port to release locks
    kill_our_chrome_processes()
    
    chrome_path = get_chrome_executable_path()
    if not chrome_path:
        raise FileNotFoundError("Google Chrome executable could not be located on this system. Please install Google Chrome.")
        
    profile_dir = os.path.abspath(os.path.join(DATA_DIR, "chrome_profile"))
    os.makedirs(profile_dir, exist_ok=True)
    
    import subprocess
    cmd = [
        chrome_path,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile_dir}",
        "--remote-allow-origins=*",
        "--no-first-run",
        "--no-default-browser-check",
        "--start-maximized"
    ]
    if url:
        cmd.append(url)
        
    print(f"Launching Chrome: {' '.join(cmd)}")
    if os.name == 'nt':
        return subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    else:
        return subprocess.Popen(cmd, start_new_session=True)

def apply_stealth_overrides(driver):
    """Prevent navigator.webdriver detection dynamically via CDP on new documents."""
    try:
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        })
    except Exception as e:
        print(f"Scraper Stealth: Error injecting CDP webdriver override: {e}")

def init_driver(headless=False):
    """Initialize driver, connecting to Google Chrome on port 9222, launching it if necessary."""
    # Ensure Google Chrome is running on debugging port 9222
    if not is_port_active(9222):
        print("Scraper: Chrome debugging port 9222 is not active. Auto-launching Chrome browser...")
        try:
            launch_chrome_debugging(9222)
            # Wait up to 5 seconds for port to become active
            for _ in range(25):
                if is_port_active(9222):
                    break
                time.sleep(0.2)
        except Exception as launch_err:
            print(f"Scraper: Error auto-launching Chrome: {launch_err}")

    # Connect to the debugging port 9222 via Selenium
    print("Scraper: Connecting Selenium driver to Google Chrome on port 9222...")
    
    # Connection Attempt 1: Standard Selenium (Cleanest, does not trigger fresh launches/resets)
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        options = Options()
        options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
        driver = webdriver.Chrome(options=options)
        
        apply_stealth_overrides(driver)
        # Override quit/close to keep the Chrome window open
        driver.quit = lambda: print("Scraper: Kept Google Chrome window alive on quit()")
        driver.close = lambda: print("Scraper: Kept Google Chrome window alive on close()")
        return driver
    except Exception as e:
        print(f"Scraper: Failed to connect via standard Selenium: {e}. Trying undetected_chromedriver remote fallback...")

    # Connection Attempt 2: undetected_chromedriver remote connection
    try:
        options = uc.ChromeOptions()
        options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
        
        chrome_version = get_chrome_major_version()
        if chrome_version:
            driver = uc.Chrome(options=options, version_main=chrome_version)
        else:
            driver = uc.Chrome(options=options)
            
        apply_stealth_overrides(driver)
        # Override quit/close to keep the Chrome window open
        driver.quit = lambda: print("Scraper: Kept Google Chrome window alive on quit()")
        driver.close = lambda: print("Scraper: Kept Google Chrome window alive on close()")
        return driver
    except Exception as e2:
        print(f"Scraper: Failed to connect via undetected_chromedriver remote: {e2}. Spawning standalone Chrome window.")
        
    # Standalone Chrome Window (Final fallback, uses same user data profile to persist sessions)
    options = uc.ChromeOptions()
    if headless:
        options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1280,800")
    
    # Apply profile dir so cookies/session still persist
    profile_dir = os.path.abspath(os.path.join(DATA_DIR, "chrome_profile"))
    options.add_argument(f"--user-data-dir={profile_dir}")
    options.add_argument("--remote-allow-origins=*")
    
    # We must release the profile lock by killing any conflicting background chrome.exe processes first
    kill_our_chrome_processes()
    
    chrome_version = get_chrome_major_version()
    if chrome_version:
        driver = uc.Chrome(options=options, use_subprocess=True, version_main=chrome_version)
    else:
        driver = uc.Chrome(options=options, use_subprocess=True)
        
    apply_stealth_overrides(driver)
    return driver

def load_cookies_into_driver(driver, target_domain, target_url, logger=None):
    """Load pickled cookies matching target_domain from cookies.json into Selenium."""
    if os.path.exists(COOKIES_FILE):
        try:
            with open(COOKIES_FILE, 'rb') as f:
                cookies = pickle.load(f)
            
            driver.get(target_url)
            time.sleep(2)
            
            loaded_count = 0
            for cookie in cookies:
                c_domain = cookie.get("domain", "")
                if target_domain not in c_domain.lower():
                    continue
                
                c_data = {
                    "name": cookie["name"],
                    "value": cookie["value"],
                    "domain": c_domain if c_domain else f".{target_domain}",
                    "path": cookie.get("path", "/")
                }
                if "expiry" in cookie:
                    c_data["expiry"] = int(cookie["expiry"])
                if "secure" in cookie:
                    c_data["secure"] = cookie["secure"]
                
                try:
                    driver.add_cookie(c_data)
                    loaded_count += 1
                except Exception:
                    pass
                    
            if logger:
                logger(f"Scraper: Loaded {loaded_count} session cookies for {target_domain}.")
            driver.refresh()
            time.sleep(2)
            return True
        except Exception as e:
            if logger:
                logger(f"Scraper Warning: Failed to load cookies for {target_domain}: {e}")
    return False

def scrape_naukri(driver, role, exp, page, logger=None):
    search_role = role.replace(" ", "-").lower()
    search_query = role.replace(" ", "+")
    url = f"https://www.naukri.com/{search_role}-jobs-{page}?k={search_query}&experience={exp}"
    if logger:
        logger(f"Scraper: [Naukri] Navigating to page {page} - {url}")
    driver.get(url)
    time.sleep(5)
    
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.srp-jobtuple-wrapper, div.cust-job-tuple, div[data-job-id]"))
        )
    except Exception:
        if logger:
            logger(f"Scraper: [Naukri] No job listings found on page {page}.")
        return []
        
    cards = driver.find_elements(By.CSS_SELECTOR, "div.srp-jobtuple-wrapper, div.cust-job-tuple, div[data-job-id]")
    jobs = []
    for card in cards:
        try:
            title_elem = card.find_element(By.CSS_SELECTOR, "a.title, a.job-title, .title")
            title = title_elem.text.strip()
            apply_url = title_elem.get_attribute("href")
            
            try:
                company = card.find_element(By.CSS_SELECTOR, "a.comp-name, .comp-name").text.strip()
            except Exception:
                company = "N/A"
                
            try:
                location = card.find_element(By.CSS_SELECTOR, "span.loc-wrap, span.locWdth, .location").text.strip()
            except Exception:
                location = "N/A"
                
            try:
                experience_required = card.find_element(By.CSS_SELECTOR, "span.exp-wrap, span.exp, .experience").text.strip()
            except Exception:
                experience_required = "N/A"
                
            try:
                skills_elems = card.find_elements(By.CSS_SELECTOR, "ul.skills-list li, ul.tags-list li, .tags-gt")
                skills_mentioned = [s.text.strip() for s in skills_elems if s.text.strip()]
            except Exception:
                skills_mentioned = []
                
            try:
                job_description = card.find_element(By.CSS_SELECTOR, "span.job-desc, .job-description, .desc").text.strip()
            except Exception:
                job_description = "N/A"
                
            jobs.append({
                "title": title,
                "company": company,
                "location": location,
                "experience_required": experience_required,
                "skills_mentioned": skills_mentioned,
                "job_description": job_description,
                "apply_url": apply_url,
                "status": "Pending",
                "score": None,
                "reasons": "",
                "source": "Naukri"
            })
        except Exception as err:
            print(f"Scraper: Error parsing Naukri card: {err}")
    return jobs

def scrape_foundit(driver, role, exp, page, logger=None):
    search_query = role.replace(" ", "+")
    offset = (page - 1) * 15
    url = f"https://www.foundit.in/srp/results?query={search_query}&experience={exp}&start={offset}&limit=15"
    if logger:
        logger(f"Scraper: [Foundit] Navigating to page {page} - {url}")
    driver.get(url)
    time.sleep(5)
    
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.srpCardCard, div.srpCard, div.card-apply-val, div.job-description-wrapper"))
        )
    except Exception:
        if logger:
            logger(f"Scraper: [Foundit] No job listings found on page {page}.")
        return []
        
    cards = driver.find_elements(By.CSS_SELECTOR, "div.srpCardCard, div.srpCard, div.card-apply-val, div.job-description-wrapper")
    jobs = []
    for card in cards:
        try:
            title_elem = card.find_element(By.CSS_SELECTOR, "a.jobTitle, .jobTitle, .title, h3 a")
            title = title_elem.text.strip()
            apply_url = title_elem.get_attribute("href")
            
            try:
                company = card.find_element(By.CSS_SELECTOR, "a.companyName, .companyName, .company, .company-name").text.strip()
            except Exception:
                company = "N/A"
                
            try:
                location = card.find_element(By.CSS_SELECTOR, "div.info-locations, div.location, .location, .loc").text.strip()
            except Exception:
                location = "N/A"
                
            try:
                experience_required = card.find_element(By.CSS_SELECTOR, "div.experience, .experience, .exp").text.strip()
            except Exception:
                experience_required = "N/A"
                
            try:
                skills_elems = card.find_elements(By.CSS_SELECTOR, ".skills-tag, div.skill-details span, .skills")
                skills_mentioned = [s.text.strip() for s in skills_elems if s.text.strip()]
            except Exception:
                skills_mentioned = []
                
            try:
                job_description = card.find_element(By.CSS_SELECTOR, "div.jobDesc, .job-desc-text, .desc").text.strip()
            except Exception:
                job_description = "N/A"
                
            jobs.append({
                "title": title,
                "company": company,
                "location": location,
                "experience_required": experience_required,
                "skills_mentioned": skills_mentioned,
                "job_description": job_description,
                "apply_url": apply_url,
                "status": "Pending",
                "score": None,
                "reasons": "",
                "source": "Foundit"
            })
        except Exception as err:
            print(f"Scraper: Error parsing Foundit card: {err}")
    return jobs

def scrape_indeed(driver, role, exp, page, logger=None):
    search_query = role.replace(" ", "+")
    if exp and int(exp) > 0:
        search_query += f"+{exp}+years+experience"
    offset = (page - 1) * 10
    url = f"https://in.indeed.com/jobs?q={search_query}&start={offset}"
    if logger:
        logger(f"Scraper: [Indeed] Navigating to page {page} - {url}")
    driver.get(url)
    time.sleep(5)
    
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.job_seen_beacon, td.resultContent, div.slider_container"))
        )
    except Exception:
        if logger:
            logger(f"Scraper: [Indeed] No job listings found on page {page}.")
        return []
        
    cards = driver.find_elements(By.CSS_SELECTOR, "div.job_seen_beacon, td.resultContent, div.slider_container")
    jobs = []
    for card in cards:
        try:
            title_elem = card.find_element(By.CSS_SELECTOR, "h2.jobTitle a, a.jcs-JobDetails-title")
            title = title_elem.text.strip()
            apply_url = title_elem.get_attribute("href")
            
            try:
                company = card.find_element(By.CSS_SELECTOR, "span[data-testid='company-name'], .companyName").text.strip()
            except Exception:
                company = "N/A"
                
            try:
                location = card.find_element(By.CSS_SELECTOR, "div[data-testid='text-location'], .companyLocation").text.strip()
            except Exception:
                location = "N/A"
                
            experience_required = f"{exp} years"
            
            try:
                desc_elem = card.find_element(By.CSS_SELECTOR, "div.job-snippet, ul.job-snippet, .jobCardShelfContainer")
                job_description = desc_elem.text.strip()
            except Exception:
                job_description = "N/A"
                
            jobs.append({
                "title": title,
                "company": company,
                "location": location,
                "experience_required": experience_required,
                "skills_mentioned": [],
                "job_description": job_description,
                "apply_url": apply_url,
                "status": "Pending",
                "score": None,
                "reasons": "",
                "source": "Indeed"
            })
        except Exception as err:
            print(f"Scraper: Error parsing Indeed card: {err}")
    return jobs

def scrape_linkedin(driver, role, exp, page, logger=None):
    search_query = role.replace(" ", "%20")
    start = (page - 1) * 25
    url = f"https://www.linkedin.com/jobs/search/?keywords={search_query}&start={start}"
    if logger:
        logger(f"Scraper: [LinkedIn] Navigating to page {page} - {url}")
    driver.get(url)
    time.sleep(5)
    
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.job-search-card, li.jobs-search-results__list-item, div.base-search-card"))
        )
    except Exception:
        if logger:
            logger(f"Scraper: [LinkedIn] No job listings found on page {page}.")
        return []
        
    cards = driver.find_elements(By.CSS_SELECTOR, "div.job-search-card, li.jobs-search-results__list-item, div.base-search-card")
    jobs = []
    for card in cards:
        try:
            try:
                title_elem = card.find_element(By.CSS_SELECTOR, "a.base-card__full-link, a.job-card-list__title, h3.base-search-card__title a")
                title = title_elem.text.strip()
                apply_url = title_elem.get_attribute("href")
            except Exception:
                title_elem = card.find_element(By.CSS_SELECTOR, "h3.base-search-card__title")
                title = title_elem.text.strip()
                apply_url = card.find_element(By.CSS_SELECTOR, "a").get_attribute("href")
                
            try:
                company = card.find_element(By.CSS_SELECTOR, "h4.base-search-card__subtitle, a.job-card-container__company-name, .job-card-container__company-name").text.strip()
            except Exception:
                company = "N/A"
                
            try:
                location = card.find_element(By.CSS_SELECTOR, "span.job-search-card__location, li.job-card-container__metadata-item, .job-search-card__location").text.strip()
            except Exception:
                location = "N/A"
                
            experience_required = f"{exp} years"
            
            jobs.append({
                "title": title,
                "company": company,
                "location": location,
                "experience_required": experience_required,
                "skills_mentioned": [],
                "job_description": "N/A",
                "apply_url": apply_url,
                "status": "Pending",
                "score": None,
                "reasons": "",
                "source": "LinkedIn"
            })
        except Exception as err:
            print(f"Scraper: Error parsing LinkedIn card: {err}")
    return jobs

def scrape_job_search_results(role, exp, enabled_boards, num_pages=1, logger=None):
    """Scrape search results for a specific role across all enabled boards."""
    driver = None
    scraped_jobs = []
    
    try:
        driver = init_driver(headless=False)
        
        # Sequentially scrape from each active job board
        for board in enabled_boards:
            if board == "Naukri":
                driver.get("https://www.naukri.com")
                time.sleep(2)
                for page in range(1, num_pages + 1):
                    scraped_jobs.extend(scrape_naukri(driver, role, exp, page, logger))
            elif board == "Foundit":
                driver.get("https://www.foundit.in")
                time.sleep(2)
                for page in range(1, num_pages + 1):
                    scraped_jobs.extend(scrape_foundit(driver, role, exp, page, logger))
            elif board == "Indeed":
                driver.get("https://in.indeed.com")
                time.sleep(2)
                for page in range(1, num_pages + 1):
                    scraped_jobs.extend(scrape_indeed(driver, role, exp, page, logger))
            elif board == "LinkedIn":
                driver.get("https://www.linkedin.com")
                time.sleep(2)
                for page in range(1, num_pages + 1):
                    scraped_jobs.extend(scrape_linkedin(driver, role, exp, page, logger))

        # Save scraped jobs to data/jobs_queue.json
        # Merge with existing queue if present
        existing_jobs = []
        if os.path.exists(JOBS_QUEUE_FILE):
            try:
                with open(JOBS_QUEUE_FILE, "r", encoding="utf-8") as f:
                    existing_jobs = json.load(f)
            except Exception:
                pass
                
        # Simple deduplication by apply_url
        existing_urls = {j["apply_url"] for j in existing_jobs if isinstance(j, dict) and "apply_url" in j}
        new_jobs_added = 0
        for job in scraped_jobs:
            if isinstance(job, dict) and "apply_url" in job:
                if job["apply_url"] not in existing_urls:
                    existing_jobs.append(job)
                    new_jobs_added += 1
                
        with open(JOBS_QUEUE_FILE, "w", encoding="utf-8") as f:
            json.dump(existing_jobs, f, indent=2)
            
        if logger:
            logger(f"Scraper: Search complete. Added {new_jobs_added} new jobs to the queue. Total queue size: {len(existing_jobs)}.")
            
    except Exception as e:
        if logger:
            logger(f"Scraper Error: Scraper failed: {e}")
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass

def fetch_full_job_description(driver, apply_url):
    """Loads the job details page and extracts the full description text."""
    try:
        driver.get(apply_url)
        time.sleep(3)
        
        # Try different selectors for full description
        description_selectors = [
            "section.job-desc",
            "div.job-desc",
            ".job-description",
            "#job-desc",
            "div.clearBoth"
        ]
        
        for selector in description_selectors:
            try:
                elem = driver.find_element(By.CSS_SELECTOR, selector)
                text = elem.text.strip()
                if text and len(text) > 100:
                    return text
            except Exception:
                pass
                
        # Fallback to body text or basic scraping if not found
        try:
            return driver.find_element(By.TAG_NAME, "body").text[:2000]
        except Exception:
            return "N/A"
            
    except Exception as e:
        print(f"Scraper: Error fetching full description for {apply_url}: {e}")
        return "N/A"
