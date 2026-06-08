import os
import json
from typing import List, Dict, Any
from playwright.async_api import BrowserContext, Page

class SessionManager:
    """
    Manages Playwright session storage state (cookies and localStorage)
    to provide redundancy on top of Chrome's persistent user-data-dir profile.
    """
    def __init__(self, state_path: str = None):
        if state_path is None:
            # Default to naukri_bot/data/naukri_session.json relative to this file
            base_dir = os.path.dirname(os.path.abspath(__file__))
            self.state_path = os.path.join(base_dir, "data", "naukri_session.json")
        else:
            self.state_path = os.path.abspath(state_path)

    async def save_session(self, context: BrowserContext) -> None:
        """
        Saves the current storage state (cookies & localStorage) of the browser context.
        """
        os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
        try:
            await context.storage_state(path=self.state_path)
        except Exception as e:
            print(f"[SessionManager] Failed to save storage state: {e}")

    async def load_session(self, context: BrowserContext, page: Page) -> bool:
        """
        Loads a saved storage state and injects cookies and localStorage into the session.
        Returns True if successful, False otherwise.
        """
        if not os.path.exists(self.state_path):
            return False

        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                state = json.load(f)

            # 1. Inject Cookies
            cookies = state.get("cookies", [])
            if cookies:
                await context.add_cookies(cookies)

            # 2. Inject localStorage
            origins = state.get("origins", [])
            for origin_data in origins:
                origin = origin_data.get("origin")
                local_storage = origin_data.get("localStorage", [])
                
                if local_storage and origin:
                    try:
                        # Navigate to the origin page if we are not already there
                        if not page.url.startswith(origin):
                            await page.goto(origin, timeout=10000, wait_until="commit")
                        
                        # Execute JS script to load items into localStorage
                        await page.evaluate(
                            """
                            (items) => {
                                items.forEach(item => {
                                    localStorage.setItem(item.name, item.value);
                                });
                            }
                            """,
                            local_storage
                        )
                    except Exception as e:
                        print(f"[SessionManager] Error restoring localStorage for {origin}: {e}")

            print("[SessionManager] Storage state restored successfully.")
            return True
        except Exception as e:
            print(f"[SessionManager] Error loading session state: {e}")
            return False

    async def check_logged_in(self, page: Page) -> bool:
        """
        Validates if the user is authenticated by navigating to Naukri recommended jobs
        and checking if we are redirected to a login page or if dashboard elements are present.
        """
        try:
            # Navigate to recommended jobs
            await page.goto("https://www.naukri.com/mnjuser/recommendedjobs", timeout=15000, wait_until="load")
            await page.wait_for_timeout(2000)  # Wait briefly for page redirects/scripts
            
            current_url = page.url
            # If the URL contains login/register keywords, the session is not authenticated
            if "login" in current_url.lower() or "register" in current_url.lower():
                return False
                
            # Double check by looking for typical logged in element classes/IDs
            # Naukri navigation bar usually has logout/profile options, and recommended jobs has Job cards
            logged_in_selectors = [
                "div[class*='recommendedJob']",
                "a[href*='logout']",
                "div[class*='profile']",
                "div.nI-gD-profile",
                "button:has-text('Apply to')",
            ]
            
            for selector in logged_in_selectors:
                try:
                    element = await page.wait_for_selector(selector, timeout=2000)
                    if element:
                        return True
                except Exception:
                    continue

            # Fallback check on URL match
            if "recommendedjobs" in current_url.lower():
                return True
                
            return False
        except Exception as e:
            print(f"[SessionManager] Check login failed: {e}")
            return False
