import re
import os
import asyncio
from typing import Tuple, List, Dict, Any
from playwright.async_api import Page, Locator

from .chrome_launcher import ChromeLauncher
from .session_manager import SessionManager
from .human_sim import human_delay, human_type, human_move_and_click

def parse_experience_range(exp_str: str) -> Tuple[int, int]:
    if not exp_str:
        return 0, 0
    # Match numbers like "2 - 5 Years" or "3-7 Yrs" or "5 Yrs"
    numbers = [int(s) for s in re.findall(r'\d+', exp_str)]
    if len(numbers) >= 2:
        return numbers[0], numbers[1]
    elif len(numbers) == 1:
        return numbers[0], numbers[0]
    return 0, 0

async def safe_text(element, selector: str) -> str:
    try:
        el = element.locator(selector).first
        if await el.is_visible():
            text = await el.inner_text()
            return text.strip()
    except Exception:
        pass
    return ""

async def safe_texts(element, selector: str) -> List[str]:
    try:
        locators = element.locator(selector)
        count = await locators.count()
        texts = []
        for i in range(count):
            t = await locators.nth(i).inner_text()
            texts.append(t.strip())
        return texts
    except Exception:
        pass
    return []

class NaukriAutomation:
    def __init__(
        self,
        settings,
        ai_engine,
        apply_logger,
        resume_data,
        log_callback,
        status_callback
    ):
        self.settings = settings
        self.ai = ai_engine
        self.apply_logger = apply_logger
        self.resume_data = resume_data
        self.log_callback = log_callback
        self.status_callback = status_callback
        
        self.launcher = None
        self.browser = None
        self.context = None
        self.page = None
        self.session_manager = SessionManager()
        
        self.applied_today = 0
        self.skipped_count = 0
        self.selected_jobs = []

    def log(self, message: str) -> None:
        self.log_callback(message)
        print(f"[NaukriAutomation] {message}")

    async def solve_questionnaire(self, stop_event: asyncio.Event) -> None:
        self.log("Checking for popups or questionnaire forms...")
        
        # Max steps in a questionnaire to avoid infinite loops
        max_questionnaire_steps = 15
        
        for step in range(max_questionnaire_steps):
            if stop_event.is_set():
                break
                
            await asyncio.sleep(2)  # Give time for form transition
            
            # Check for DONE button
            done_btn = self.page.locator("button:has-text('DONE'), [class*='done'], :text('DONE')").first
            if await done_btn.is_visible():
                self.log("Found 'DONE' button. Clicking to finish...")
                await done_btn.click()
                await asyncio.sleep(1)
                
                # Check for Save or Submit button if visible
                save_btn = self.page.locator("button:has-text('Save'), [class*='save'], :text('Save')").first
                if await save_btn.is_visible():
                    await save_btn.click()
                    await asyncio.sleep(1)
                break
                
            # Attempt to extract question context
            question_text = ""
            try:
                # Find message elements
                bot_messages = self.page.locator(".botMsg, .chatbot_Message, .ssrc__question-text, .msg")
                msg_count = await bot_messages.count()
                if msg_count > 0:
                    question_text = await bot_messages.nth(msg_count - 1).inner_text()
                else:
                    # Fallback context from headers/paragraphs in the container
                    headers = self.page.locator(".chatbot_Header, h3, h4, p, span")
                    h_count = await headers.count()
                    for idx in range(max(0, h_count - 3), h_count):
                        txt = await headers.nth(idx).inner_text()
                        if txt.strip():
                            question_text += " " + txt.strip()
            except Exception:
                pass
                
            question_text = question_text.strip() if question_text else "General application question"
            self.log(f"Question context: '{question_text}'")
            
            # Look for elements
            text_inputs = self.page.locator("input[id^='userInput__'], textarea[id^='userInput__'], .chatbot_InputContainer input, .chatbot_InputContainer textarea, input.chatbot_InputBox, textarea.chatbot_InputBox")
            radio_options = self.page.locator(".ssrc__radio-btn-container, [id^='ssrc__'], [id*='RadioButton'], .ssrc__chip, [id*='chips_container'] .chip")
            
            action_taken = False
            
            # Handle text input fields
            if await text_inputs.count() > 0 and await text_inputs.first.is_visible():
                input_field = text_inputs.first
                self.log("Detected text input field.")
                
                answer = await self.ai.answer_question(self.resume_data, question_text, input_type="text")
                answer = answer.strip()
                self.log(f"AI suggested answer: '{answer}'")
                
                await input_field.click()
                await input_field.fill("")
                await human_type(input_field, answer)
                await asyncio.sleep(0.5)
                
                # Check for Save or Send/Submit buttons
                save_btn = self.page.locator("button:has-text('Save'), :text('Save'), [id^='sendMsgbtn_container'], [class*='save']").first
                if await save_btn.is_visible():
                    await save_btn.click()
                    self.log("Clicked Save/Submit button.")
                    action_taken = True
                    
            # Handle option selection (radio / chips)
            elif await radio_options.count() > 0 and await radio_options.first.is_visible():
                self.log("Detected choice options.")
                options_count = await radio_options.count()
                options_list = []
                element_map = {}
                
                for idx in range(options_count):
                    opt = radio_options.nth(idx)
                    opt_text = await opt.inner_text()
                    opt_text = opt_text.strip()
                    if opt_text:
                        options_list.append(opt_text)
                        element_map[opt_text.lower()] = opt
                        
                if options_list:
                    self.log(f"Options: {options_list}")
                    answer = await self.ai.answer_question(self.resume_data, question_text, input_type="radio", options=options_list)
                    answer = answer.strip()
                    self.log(f"AI selected option: '{answer}'")
                    
                    target_opt = None
                    for opt_text in options_list:
                        if opt_text.lower() == answer.lower():
                            target_opt = element_map[opt_text.lower()]
                            break
                            
                    if not target_opt:
                        # Fallback to fuzzy match
                        for opt_text in options_list:
                            if answer.lower() in opt_text.lower() or opt_text.lower() in answer.lower():
                                target_opt = element_map[opt_text.lower()]
                                break
                                
                    if not target_opt:
                        target_opt = radio_options.first
                        
                    if target_opt:
                        await target_opt.click()
                        await asyncio.sleep(1)
                        
                        # Click Save button if present
                        save_btn = self.page.locator("button:has-text('Save'), :text('Save'), [class*='save']").first
                        if await save_btn.is_visible():
                            await save_btn.click()
                            self.log("Clicked Save option.")
                        action_taken = True
            
            if not action_taken:
                # Standalone Save check
                save_btn = self.page.locator("button:has-text('Save'), :text('Save'), [class*='save']").first
                if await save_btn.is_visible():
                    await save_btn.click()
                    self.log("Clicked standalone Save.")
                    action_taken = True
                else:
                    # Check for Skip
                    skip_btn = self.page.locator("button:has-text('Skip this question'), :text('Skip this question'), [class*='skip']").first
                    if await skip_btn.is_visible():
                        await skip_btn.click()
                        self.log("Clicked Skip.")
                        action_taken = True
            
            if not action_taken:
                # Fallback DONE button check
                done_btn = self.page.locator("button:has-text('DONE'), :text('DONE')").first
                if await done_btn.is_visible():
                    await done_btn.click()
                    self.log("Clicked DONE.")
                    break
                else:
                    self.log("No active questionnaire fields found. Questionnaire complete.")
                    break

    async def run(self, stop_event: asyncio.Event, pause_event: asyncio.Event) -> None:
        self.log("Starting async Chrome remote Playwright automation...")
        self.status_callback("Running", 0, 0)
        
        # Initialize ChromeLauncher with persistent data directory
        profile_dir = self.settings.get("chrome_profile_dir", "data/chrome_profile")
        chrome_port = self.settings.get("chrome_port", 9222)
        
        self.launcher = ChromeLauncher(profile_dir=profile_dir, port=chrome_port)
        
        try:
            self.log("Launching browser...")
            self.browser, self.context, self.page = await self.launcher.launch_and_connect()
            
            # Navigate to Naukri
            self.log("Navigating to Naukri homepage...")
            await self.page.goto("https://www.naukri.com/")
            await asyncio.sleep(3)
            
            if stop_event.is_set():
                return
                
            # Session Check
            self.log("Checking session state...")
            is_logged_in = await self.session_manager.check_logged_in(self.page)
            
            if not is_logged_in:
                self.log("Session not authenticated on recommended jobs. Restoring cookies/localStorage...")
                restored = await self.session_manager.load_session(self.context, self.page)
                if restored:
                    is_logged_in = await self.session_manager.check_logged_in(self.page)
            
            # Perform manual login if session is still invalid
            if not is_logged_in:
                self.log("Session not found or expired. Performing fresh login...")
                await self.page.goto("https://www.naukri.com/")
                await asyncio.sleep(2)
                
                login_btn = self.page.get_by_role("link", name="Login", exact=True)
                if await login_btn.is_visible():
                    await login_btn.click()
                    await asyncio.sleep(2)
                    
                    # Fill default credentials if present
                    # Note: We can also wait for the user to solve captcha if it appears
                    try:
                        email_box = self.page.get_by_role("textbox", name="Enter your active Email ID /")
                        if await email_box.is_visible(timeout=3000):
                            self.log("Entering credentials...")
                            await email_box.fill("r4900221@gmail.com")
                            pw_box = self.page.get_by_role("textbox", name="Enter your password")
                            await pw_box.fill("prasadok1@")
                            
                            login_submit = self.page.get_by_role("button", name="Login", exact=True)
                            await login_submit.click()
                            await asyncio.sleep(5)
                    except Exception as e:
                        self.log(f"Auto-login credential filling bypassed: {e}")
                
                # Check login again
                is_logged_in = await self.session_manager.check_logged_in(self.page)
                if not is_logged_in:
                    self.log("Please log in manually in the opened Chrome window. Waiting for session...")
                    for _ in range(60): # Wait up to 2 minutes
                        if stop_event.is_set():
                            return
                        await asyncio.sleep(2)
                        is_logged_in = await self.session_manager.check_logged_in(self.page)
                        if is_logged_in:
                            self.log("Manual login detected successfully!")
                            break
                            
                if is_logged_in:
                    self.log("Saving new session state to session file...")
                    await self.session_manager.save_session(self.context)
                else:
                    self.log("Failed to authenticate session. Stopping automation.")
                    return
            else:
                self.log("Session verified! Already logged in.")
            
            # Main automation loop
            max_loops = 5
            for loop_idx in range(max_loops):
                if stop_event.is_set():
                    break
                    
                # Pause Handling
                while pause_event.is_set() and not stop_event.is_set():
                    self.status_callback("Paused", self.applied_today, self.skipped_count)
                    await asyncio.sleep(1)
                    
                if stop_event.is_set():
                    break
                    
                self.status_callback("Running", self.applied_today, self.skipped_count)
                self.log(f"--- Loop {loop_idx + 1} of {max_loops} ---")
                
                # Navigate to Recommended Jobs
                self.log("Navigating to recommended jobs page...")
                await self.page.goto("https://www.naukri.com/mnjuser/recommendedjobs")
                await asyncio.sleep(5)
                
                # Screen job cards using AI
                job_cards = self.page.locator("div[class*='recommendedJob'], article[class*='jobTuple'], div[class*='jobTuple']")
                card_count = await job_cards.count()
                self.log(f"Found {card_count} job cards on page.")
                
                jobs_to_apply = [] # Stores (checkbox_locator, title, company, score, reason)
                
                for i in range(card_count):
                    if stop_event.is_set() or len(jobs_to_apply) >= 5:
                        break
                        
                    card = job_cards.nth(i)
                    
                    title = await safe_text(card, ".title, [class*='title'], a[class*='title']")
                    company = await safe_text(card, ".company, [class*='company'], a[class*='company']")
                    experience = await safe_text(card, ".experience, span[class*='exp'], li[class*='experience']")
                    skills = await safe_texts(card, ".skills li, .keySkills li, [class*='keySkills'] li, .skills span")
                    
                    if not title or not company:
                        continue
                        
                    self.log(f"Screening Job {i+1}: '{title}' at '{company}'...")
                    
                    job_details = {
                        "title": title,
                        "company": company,
                        "experience": experience,
                        "skills": skills
                    }
                    
                    decision = await self.ai.score_job(job_details, self.resume_data)
                    score = decision.get("score", 50)
                    reason = decision.get("reason", "No match reasoning supplied.")
                    decision_action = decision.get("decision", "SKIP")
                    
                    self.log(f"Result: Score {score}/100 -> {decision_action}. Reason: {reason}")
                    
                    min_threshold = self.settings.get("min_score", 70)
                    if decision_action == "APPLY" and score >= min_threshold:
                        cb = card.locator(".dspIB.naukicon.naukicon-ot-checkbox").first
                        if await cb.is_visible():
                            jobs_to_apply.append((cb, title, company, score, reason))
                            self.log(f"Added to selection: '{title}'")
                    else:
                        self.skipped_count += 1
                        self.apply_logger.log_apply(title, company, "Skipped", score, reason)
                        
                # Fallback if selectors failed but checkboxes exist
                if not jobs_to_apply and card_count == 0:
                    self.log("Running fallback checkbox scanner...")
                    checkboxes = self.page.locator(".dspIB.naukicon.naukicon-ot-checkbox")
                    cb_count = await checkboxes.count()
                    for idx in range(min(5, cb_count)):
                        cb = checkboxes.nth(idx)
                        if await cb.is_visible():
                            jobs_to_apply.append((cb, f"Naukri Recommended Job {idx+1}", "Unknown Company", 70, "Applied via generic checkbox click."))
                
                if not jobs_to_apply:
                    self.log("No matching jobs to apply in this loop. Finished.")
                    break
                    
                # Select checkboxes
                selected_count = 0
                for cb, title, company, score, reason in jobs_to_apply:
                    if stop_event.is_set():
                        break
                    self.log(f"Clicking checkbox for '{title}'...")
                    await cb.click()
                    await asyncio.sleep(1)
                    selected_count += 1
                    
                if stop_event.is_set() or selected_count == 0:
                    break
                    
                # Click Apply button
                self.log(f"Applying to {selected_count} selected jobs...")
                try:
                    apply_btn = self.page.get_by_role("button", name=re.compile(rf"Apply {selected_count} Jobs|Apply.*Jobs", re.IGNORECASE)).first
                    await apply_btn.wait_for(state="visible", timeout=5000)
                    await apply_btn.click()
                    await asyncio.sleep(3)
                    
                    # Run questionnaire solver
                    await self.solve_questionnaire(stop_event)
                    
                    # Log applications
                    for cb, title, company, score, reason in jobs_to_apply:
                        self.applied_today += 1
                        self.apply_logger.log_apply(title, company, "Applied", score, reason)
                        
                except Exception as e:
                    self.log(f"Apply action failed: {e}")
                    for cb, title, company, score, reason in jobs_to_apply:
                        self.apply_logger.log_apply(title, company, "Failed", score, f"Failed to complete apply action: {e}")
                        
                self.status_callback("Running", self.applied_today, self.skipped_count)
                await asyncio.sleep(3)
                
        except Exception as e:
            self.log(f"An unexpected error occurred during execution: {e}")
        finally:
            self.log("Closing browser context...")
            if self.launcher:
                await self.launcher.close()
            self.log("Browser closed.")
            
        self.status_callback("Stopped", self.applied_today, self.skipped_count)
        self.log("Automation finished.")
