import os
import json
import time
from datetime import datetime

class VisualActionRecorder:
    def __init__(self, driver=None, session_name="Naukri_AutoApply", base_dir=None):
        from settings import DATA_DIR
        self.driver = driver    
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Resolve recordings directory relative to data directory
        if not base_dir:
            base_dir = os.path.join(DATA_DIR, "recordings")
            
        self.session_dir = os.path.join(base_dir, f"{session_name}_{self.session_id}")
        self.screenshots_dir = os.path.join(self.session_dir, "screenshots")
        os.makedirs(self.screenshots_dir, exist_ok=True)
        self.steps = []
        self.step_counter = 0

    def record_action(self, action_name, description="", capture_screenshot=True, code_selenium="", code_playwright=""):
        """Record a single step, optionally capture a screenshot, and register Selenium/Playwright replay code."""
        self.step_counter += 1
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        screenshot_path = ""
        
        if capture_screenshot and self.driver:
            screenshot_filename = f"step_{self.step_counter:03d}_{action_name.replace(' ', '_').lower()}.png"
            # Keep path relative to session_dir for easy HTML loading
            screenshot_path = os.path.join("screenshots", screenshot_filename)
            absolute_path = os.path.join(self.screenshots_dir, screenshot_filename)
            try:
                # Slight wait to make sure elements are visually stable before capture
                time.sleep(0.3)
                self.driver.save_screenshot(absolute_path)
            except Exception as e:
                screenshot_path = ""
                print(f"Recorder Error: Could not save screenshot: {e}")

        # If specific code is not provided, generate helper/comment placeholders
        if not code_selenium:
            code_selenium = f"# Action: {action_name}\n# Description: {description}\npass"
        if not code_playwright:
            code_playwright = f"# Action: {action_name}\n# Description: {description}\npass"

        step_data = {
            "step": self.step_counter,
            "timestamp": timestamp,
            "action": action_name,
            "description": description,
            "screenshot": screenshot_path,
            "code_selenium": code_selenium,
            "code_playwright": code_playwright
        }
        self.steps.append(step_data)
        
        # Write JSON logs dynamically
        try:
            log_file = os.path.join(self.session_dir, "recording_log.json")
            with open(log_file, "w", encoding="utf-8") as f:
                json.dump(self.steps, f, indent=2)
        except Exception:
            pass

    def generate_report(self):
        """Generate a beautiful, premium visual walkthrough HTML report with replay script compilation."""
        report_path = os.path.join(self.session_dir, "index.html")
        
        # 1. Compile Selenium Replay Script
        sel_script_path = os.path.join(self.session_dir, "selenium_replay.py")
        sel_script_content = self._compile_selenium_script()
        try:
            with open(sel_script_path, "w", encoding="utf-8") as f:
                f.write(sel_script_content)
        except Exception as e:
            print(f"Recorder: Error compiling selenium_replay.py: {e}")

        # 2. Compile Playwright Replay Script
        pw_script_path = os.path.join(self.session_dir, "playwright_replay.py")
        pw_script_content = self._compile_playwright_script()
        try:
            with open(pw_script_path, "w", encoding="utf-8") as f:
                f.write(pw_script_content)
        except Exception as e:
            print(f"Recorder: Error compiling playwright_replay.py: {e}")

        # 3. Generate HTML Content
        html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Visual Execution Log - {self.session_id}</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-canvas: #0b0f19;
            --bg-surface: #151c2c;
            --bg-code: #1e293b;
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --accent-primary: #38bdf8;
            --accent-secondary: #818cf8;
            --accent-success: #34d399;
            --border-color: #334155;
        }}
        body {{
            font-family: 'Outfit', sans-serif;
            background-color: var(--bg-canvas);
            color: var(--text-primary);
            margin: 0;
            padding: 30px;
            line-height: 1.5;
        }}
        .container {{
            max-width: 1300px;
            margin: 0 auto;
            background-color: var(--bg-surface);
            padding: 40px;
            border: 1px solid var(--border-color);
            border-radius: 16px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.5);
        }}
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 24px;
            margin-bottom: 30px;
        }}
        h1 {{
            color: var(--text-primary);
            margin: 0;
            font-size: 2.2em;
            font-weight: 700;
            background: linear-gradient(135deg, var(--accent-primary), var(--accent-secondary));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        .badge {{
            background: rgba(56, 189, 248, 0.15);
            color: var(--accent-primary);
            border: 1px solid rgba(56, 189, 248, 0.3);
            padding: 4px 12px;
            border-radius: 9999px;
            font-size: 0.85em;
            font-weight: 600;
        }}
        .meta-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 20px;
            margin-bottom: 40px;
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid var(--border-color);
            padding: 20px;
            border-radius: 12px;
        }}
        .meta-item {{
            display: flex;
            flex-direction: column;
        }}
        .meta-label {{
            font-size: 0.85em;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 4px;
        }}
        .meta-val {{
            font-weight: 600;
            font-size: 1.05em;
        }}
        .download-buttons {{
            display: flex;
            gap: 15px;
            margin-bottom: 40px;
        }}
        .btn {{
            display: inline-flex;
            align-items: center;
            padding: 10px 20px;
            border-radius: 8px;
            font-weight: 600;
            text-decoration: none;
            cursor: pointer;
            transition: all 0.2s;
            border: none;
            font-size: 0.95em;
        }}
        .btn-selenium {{
            background-color: #0284c7;
            color: white;
        }}
        .btn-selenium:hover {{
            background-color: #0369a1;
        }}
        .btn-playwright {{
            background-color: #4f46e5;
            color: white;
        }}
        .btn-playwright:hover {{
            background-color: #4338ca;
        }}
        .timeline {{
            position: relative;
        }}
        .step {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 30px;
            margin-bottom: 50px;
            border-bottom: 1px solid rgba(51, 65, 85, 0.5);
            padding-bottom: 40px;
        }}
        .step:last-child {{
            border-bottom: none;
            padding-bottom: 0;
        }}
        .step-details {{
            display: flex;
            flex-direction: column;
        }}
        .step-header {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 10px;
        }}
        .step-num {{
            font-size: 1.3em;
            font-weight: 700;
            color: var(--accent-primary);
        }}
        .step-time {{
            font-size: 0.85em;
            color: var(--text-secondary);
        }}
        .step-desc {{
            font-size: 1.05em;
            color: #e2e8f0;
            margin-bottom: 20px;
            background: rgba(255, 255, 255, 0.01);
            padding: 12px;
            border-left: 3px solid var(--accent-secondary);
            border-radius: 0 6px 6px 0;
        }}
        /* Tabs for Replay Code */
        .code-tabs {{
            display: flex;
            border-bottom: 1px solid var(--border-color);
            margin-bottom: 10px;
        }}
        .code-tab-btn {{
            background: none;
            border: none;
            color: var(--text-secondary);
            padding: 8px 16px;
            cursor: pointer;
            font-weight: 600;
            font-size: 0.9em;
            border-bottom: 2px solid transparent;
            transition: all 0.2s;
        }}
        .code-tab-btn.active {{
            color: var(--accent-primary);
            border-bottom-color: var(--accent-primary);
        }}
        .code-container {{
            background-color: var(--bg-code);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 15px;
            overflow-x: auto;
            max-height: 250px;
            display: none;
        }}
        .code-container.active {{
            display: block;
        }}
        .code-container pre {{
            margin: 0;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.85em;
            color: #cbd5e1;
        }}
        .step-media img {{
            width: 100%;
            border: 1px solid var(--border-color);
            border-radius: 10px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.3);
            transition: transform 0.2s;
            cursor: zoom-in;
        }}
        .step-media img:hover {{
            transform: scale(1.01);
        }}
        .no-media {{
            color: var(--text-secondary);
            font-style: italic;
            padding: 50px 20px;
            border: 2px dashed var(--border-color);
            text-align: center;
            border-radius: 10px;
            background-color: rgba(255, 255, 255, 0.01);
        }}
    </style>
    <script>
        function switchTab(stepIndex, tabName) {{
            // Deactivate all tab buttons in this step
            var buttons = document.querySelectorAll('.step-' + stepIndex + ' .code-tab-btn');
            buttons.forEach(btn => btn.classList.remove('active'));
            
            // Deactivate all code containers in this step
            var containers = document.querySelectorAll('.step-' + stepIndex + ' .code-container');
            containers.forEach(cnt => cnt.classList.remove('active'));
            
            // Activate target button and container
            var targetBtn = document.querySelector('.step-' + stepIndex + ' .btn-' + tabName);
            if (targetBtn) targetBtn.classList.add('active');
            
            var targetCnt = document.querySelector('.step-' + stepIndex + ' .code-' + tabName);
            if (targetCnt) targetCnt.classList.add('active');
        }}
    </script>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Eggplant-Style Visual Automation Execution Report</h1>
            <span class="badge">Session Active</span>
        </div>
        
        <div class="meta-grid">
            <div class="meta-item">
                <span class="meta-label">Session ID</span>
                <span class="meta-val">{self.session_id}</span>
            </div>
            <div class="meta-item">
                <span class="meta-label">Report Compiled</span>
                <span class="meta-val">{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</span>
            </div>
            <div class="meta-item">
                <span class="meta-label">Total Steps</span>
                <span class="meta-val">{len(self.steps)}</span>
            </div>
        </div>

        <div class="download-buttons">
            <a href="selenium_replay.py" download class="btn btn-selenium">
                <svg style="margin-right:8px;" width="16" height="16" fill="white" viewBox="0 0 16 16"><path d="M.5 9.9a.5.5 0 0 1 .5.5v2.5a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-2.5a.5.5 0 0 1 1 0v2.5a2 2 0 0 1-2 2H2a2 2 0 0 1-2-2v-2.5a.5.5 0 0 1 .5-.5z"/><path d="M7.646 11.854a.5.5 0 0 0 .708 0l3-3a.5.5 0 0 0-.708-.708L8.5 10.293V1.5a.5.5 0 0 0-1 0v8.793L5.354 8.146a.5.5 0 1 0-.708.708l3 3z"/></svg>
                Download Selenium Replay Script
            </a>
            <a href="playwright_replay.py" download class="btn btn-playwright">
                <svg style="margin-right:8px;" width="16" height="16" fill="white" viewBox="0 0 16 16"><path d="M.5 9.9a.5.5 0 0 1 .5.5v2.5a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-2.5a.5.5 0 0 1 1 0v2.5a2 2 0 0 1-2 2H2a2 2 0 0 1-2-2v-2.5a.5.5 0 0 1 .5-.5z"/><path d="M7.646 11.854a.5.5 0 0 0 .708 0l3-3a.5.5 0 0 0-.708-.708L8.5 10.293V1.5a.5.5 0 0 0-1 0v8.793L5.354 8.146a.5.5 0 1 0-.708.708l3 3z"/></svg>
                Download Playwright Replay Script
            </a>
        </div>

        <div class="timeline">
        """
        
        for idx, step in enumerate(self.steps):
            img_html = f'<a href="{step["screenshot"]}" target="_blank"><img src="{step["screenshot"]}" alt="{step["action"]}"></a>' if step["screenshot"] else '<div class="no-media">No Screenshot Captured for this action</div>'
            
            # Clean and escape code block for HTML
            sel_code = step["code_selenium"].replace("<", "&lt;").replace(">", "&gt;")
            pw_code = step["code_playwright"].replace("<", "&lt;").replace(">", "&gt;")
            
            html_content += f"""
            <div class="step step-{idx}">
                <div class="step-details">
                    <div class="step-header">
                        <div class="step-num">Step {step["step"]}: {step["action"]}</div>
                        <div class="step-time">{step["timestamp"]}</div>
                    </div>
                    <div class="step-desc">{step["description"]}</div>
                    
                    <div class="code-tabs">
                        <button class="code-tab-btn btn-selenium active" onclick="switchTab({idx}, 'selenium')">Selenium Code</button>
                        <button class="code-tab-btn btn-playwright" onclick="switchTab({idx}, 'playwright')">Playwright Code</button>
                    </div>
                    
                    <div class="code-container code-selenium active">
                        <pre><code>{sel_code}</code></pre>
                    </div>
                    <div class="code-container code-playwright">
                        <pre><code>{pw_code}</code></pre>
                    </div>
                </div>
                <div class="step-media">
                    {img_html}
                </div>
            </div>
            """
            
        html_content += """
        </div>
    </div>
</body>
</html>
        """
        
        try:
            with open(report_path, "w", encoding="utf-8") as f:
                f.write(html_content)
            print(f"Recorder: Generated Visual Log Report at {report_path}")
            return report_path
        except Exception as e:
            print(f"Recorder: Error writing HTML report: {e}")
            return None

    def _compile_selenium_script(self):
        """Assemble all step-by-step Selenium code blocks into a single executable .py file."""
        code_blocks = []
        for step in self.steps:
            # Indent each line by 4 spaces to place it inside the runner function
            indented_lines = []
            for line in step["code_selenium"].splitlines():
                indented_lines.append("    " + line)
            indented_code = "\n".join(indented_lines)
            
            step_header = f"""
    # ----------------------------------------------------------------------
    # STEP {step['step']}: {step['action']}
    # {step['description']}
    # ----------------------------------------------------------------------
{indented_code}
            """
            code_blocks.append(step_header)
            
        full_script = f"""# ======================================================================
# Selenium Replay Script (Eggplant-style Recording Replay)
# Session ID: {self.session_id}
# Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
# ======================================================================

import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

def run_selenium_replay():
    print("[Replay] Connecting to Google Chrome on port 9222...")
    options = Options()
    options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
    
    try:
        driver = webdriver.Chrome(options=options)
    except Exception as e:
        print(f"[Replay] Failed to connect: {{e}}")
        return

    print("[Replay] Starting step-by-step execution...")
    # --- STEPS EXECUTION ---
{"".join(code_blocks)}

    print("[Replay] Done! Kept Google Chrome window alive.")

if __name__ == '__main__':
    run_selenium_replay()
"""
        return full_script

    def _compile_playwright_script(self):
        """Assemble all step-by-step Playwright code blocks into a single executable .py file."""
        code_blocks = []
        for step in self.steps:
            # Indent each line by 8 spaces to place inside context block
            indented_lines = []
            for line in step["code_playwright"].splitlines():
                indented_lines.append("        " + line)
            indented_code = "\n".join(indented_lines)
            
            step_header = f"""
        # ----------------------------------------------------------------------
        # STEP {step['step']}: {step['action']}
        # {step['description']}
        # ----------------------------------------------------------------------
{indented_code}
            """
            code_blocks.append(step_header)
            
        full_script = f"""# ======================================================================
# Playwright Replay Script (Eggplant-style Recording Replay)
# Session ID: {self.session_id}
# Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
# ======================================================================

import time
from playwright.sync_api import sync_playwright

def run_playwright_replay():
    print("[Replay] Connecting to Google Chrome on port 9222...")
    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
            context = browser.contexts[0]
            page = context.pages[0]
        except Exception as e:
            print(f"[Replay] Failed to connect via Playwright: {{e}}")
            return

        print("[Replay] Starting step-by-step execution...")
        # --- STEPS EXECUTION ---
{"".join(code_blocks)}

        print("[Replay] Playwright session complete.")

if __name__ == '__main__':
    run_playwright_replay()
"""
        return full_script
