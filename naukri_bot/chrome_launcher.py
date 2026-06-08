import os
import sys
import socket
import subprocess
import asyncio
from typing import Optional, Tuple
from playwright.async_api import async_playwright, Playwright, Browser, BrowserContext, Page

def find_chrome_path() -> Optional[str]:
    """
    Search for Google Chrome executable path across different operating systems.
    Returns the absolute path if found, otherwise None.
    """
    if sys.platform.startswith("win"):
        # 1. Check registry (both HKLM and HKCU)
        try:
            import winreg
            for hkey in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                try:
                    key = winreg.OpenKey(hkey, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe")
                    path, _ = winreg.QueryValueEx(key, "")
                    winreg.CloseKey(key)
                    if os.path.exists(path):
                        return path
                except OSError:
                    continue
        except ImportError:
            pass

        # 2. Check standard Windows installations
        standard_paths = [
            os.path.join(os.environ.get("PROGRAMFILES", "C:\\Program Files"), "Google\\Chrome\\Application\\chrome.exe"),
            os.path.join(os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)"), "Google\\Chrome\\Application\\chrome.exe"),
            os.path.join(os.environ.get("LOCALAPPDATA", "C:\\Users\\Default\\AppData\\Local"), "Google\\Chrome\\Application\\chrome.exe"),
        ]
        for path in standard_paths:
            if os.path.exists(path):
                return path

    elif sys.platform.startswith("darwin"):
        # macOS standard path
        mac_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        if os.path.exists(mac_path):
            return mac_path

    elif sys.platform.startswith("linux"):
        # Linux standard locations and commands
        import shutil
        for cmd in ("google-chrome", "google-chrome-stable", "chromium-browser", "chromium"):
            path = shutil.which(cmd)
            if path:
                return path
        
        linux_paths = [
            "/usr/bin/google-chrome",
            "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
            "/usr/lib/chromium-browser/chromium-browser"
        ]
        for path in linux_paths:
            if os.path.exists(path):
                return path

    return None

def is_chrome_running(port: int = 9222) -> bool:
    """
    Check if a process is listening on the remote debugging port.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1.0)
        return s.connect_ex(("127.0.0.1", port)) == 0

def kill_chrome_on_port(port: int) -> None:
    """
    Finds and terminates any process listening on the specified port.
    Highly targeted so it only kills the zombie debugging process, not the user's main Chrome.
    """
    if sys.platform.startswith("win"):
        try:
            # Find the PID listening on the port
            cmd = f"netstat -ano | findstr LISTENING | findstr :{port}"
            # Run in shell to support pipe and findstr
            output = subprocess.check_output(cmd, shell=True, text=True)
            for line in output.strip().splitlines():
                parts = line.split()
                if len(parts) >= 5:
                    pid = parts[-1]
                    print(f"[ChromeLauncher] Found zombie Chrome process on port {port} with PID {pid}. Killing it...")
                    subprocess.run(f"taskkill /F /PID {pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass  # No process found or taskkill failed
            
    else:  # macOS / Linux
        try:
            # Find the PID listening on the port
            cmd = f"lsof -i :{port} -t"
            pid = subprocess.check_output(cmd, shell=True, text=True).strip()
            if pid:
                print(f"[ChromeLauncher] Found zombie Chrome process on port {port} with PID {pid}. Killing it...")
                subprocess.run(f"kill -9 {pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

class ChromeLauncher:
    """
    Manages Chrome subprocess launching and Playwright CDP connection.
    """
    def __init__(self, profile_dir: str = "data/chrome_profile", port: int = 9222):
        # Resolve absolute path for user data profile directory
        self.profile_dir = os.path.abspath(profile_dir)
        self.port = port
        self.process: Optional[subprocess.Popen] = None
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

    async def launch_and_connect(self) -> Tuple[Browser, BrowserContext, Page]:
        """
        Launches Chrome with CDP enabled if it's not already running,
        then connects Playwright over CDP. Returns (Browser, Context, Page).
        """
        # Create profile directory if it doesn't exist
        os.makedirs(self.profile_dir, exist_ok=True)

        connected = False
        try:
            if is_chrome_running(self.port):
                self.playwright = await async_playwright().start()
                self.browser = await self.playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{self.port}")
                if self.browser.contexts:
                    self.context = self.browser.contexts[0]
                else:
                    self.context = await self.browser.new_context()
                if self.context.pages:
                    self.page = self.context.pages[0]
                else:
                    self.page = await self.context.new_page()
                
                # Check if the page is actually healthy and usable
                await self.page.evaluate("1 + 1")
                connected = True
        except Exception as e:
            print(f"[ChromeLauncher] Connected to existing port {self.port} but browser was unhealthy: {e}. Cleaning up...")
            await self.close()

        if not connected:
            # Kill any zombie process on our port to avoid port-in-use / locking issues
            kill_chrome_on_port(self.port)
            
            chrome_path = find_chrome_path()
            if not chrome_path:
                raise FileNotFoundError("Google Chrome was not found on this system. Please install Chrome or add it to your PATH.")

            chrome_args = [
                chrome_path,
                f"--remote-debugging-port={self.port}",
                f"--user-data-dir={self.profile_dir}",
                "--no-first-run",
                "--no-default-browser-check",
                "--excludeSwitches=enable-automation",
            ]
            
            # Use subprocess flag to avoid console windows on Windows
            creationflags = 0
            if sys.platform == "win32":
                creationflags = subprocess.CREATE_NO_WINDOW

            self.process = subprocess.Popen(
                chrome_args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags
            )
            # Give Chrome a moment to initialize and open the port
            await asyncio.sleep(2.0)

            # Initialize Playwright and connect over CDP
            if not self.playwright:
                self.playwright = await async_playwright().start()
            
            self.browser = await self.playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{self.port}")
            
            if self.browser.contexts:
                self.context = self.browser.contexts[0]
            else:
                self.context = await self.browser.new_context()

            if self.context.pages:
                self.page = self.context.pages[0]
            else:
                self.page = await self.context.new_page()

        return self.browser, self.context, self.page

    async def close(self) -> None:
        """
        Closes Playwright connection and terminates Chrome subprocess (if it was launched by us).
        """
        try:
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
        except Exception:
            pass  # Suppress errors during shutdown

        if self.process:
            self.process.terminate()
            try:
                # Wait for up to 3 seconds for graceful shutdown
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None
