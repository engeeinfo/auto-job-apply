import os
import sys
import time
import json
import shutil
import threading
import multiprocessing
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime

from settings import DATA_DIR, load_settings, save_settings, reset_all_data
from resume_parser import parse_and_save_resume, RESUME_DATA_FILE
from job_scraper import scrape_job_search_results, JOBS_QUEUE_FILE
from auto_applier import run_auto_apply

# Neobrutalism Design Tokens
NEO_PRIMARY = "#FDC800"      # Yellow accent
NEO_SECONDARY = "#432DD7"    # Vivid blue-purple
NEO_SUCCESS = "#16A34A"      # Success green
NEO_WARNING = "#D97706"      # Warning orange
NEO_DANGER = "#DC2626"       # Danger red
NEO_SURFACE = "#FBFBF9"      # Surface warm cream
NEO_CANVAS = "#EDECE9"       # Canvas background
NEO_TEXT = "#1C293C"         # Text charcoal
NEO_WHITE = "#FFFFFF"

class NeoButton(tk.Frame):
    def __init__(self, parent, text, command=None, bg=NEO_PRIMARY, fg=NEO_TEXT, font=("Segoe UI", 9, "bold"), padding=(8, 4), **kwargs):
        # Container frame has the shadow color (NEO_TEXT)
        super().__init__(parent, bg=NEO_TEXT, bd=0, highlightthickness=0)
        self.bg = bg
        self.fg = fg
        self.command = command
        
        self.btn = tk.Button(
            self,
            text=text,
            command=self._on_click,
            bg=bg,
            fg=fg,
            font=font,
            bd=2,
            relief="solid",
            highlightthickness=0,
            activebackground=bg,
            activeforeground=fg,
            cursor="hand2",
            padx=padding[0],
            pady=padding[1]
        )
        self.btn.pack(fill="both", expand=True, padx=(0, 3), pady=(0, 3))
        
        self.btn.bind("<Enter>", self._on_enter)
        self.btn.bind("<Leave>", self._on_leave)
        self.btn.bind("<Button-1>", self._on_press)
        self.btn.bind("<ButtonRelease-1>", self._on_release)
        
    def _on_click(self):
        if self.command:
            self.command()
            
    def _on_enter(self, e):
        if self.btn['state'] != 'disabled':
            self.btn.config(bg=NEO_SECONDARY if self.bg != NEO_SECONDARY else NEO_PRIMARY, fg=NEO_WHITE if self.bg != NEO_SECONDARY else NEO_TEXT)
            
    def _on_leave(self, e):
        if self.btn['state'] != 'disabled':
            self.btn.config(bg=self.bg, fg=self.fg)
            
    def _on_press(self, e):
        if self.btn['state'] != 'disabled':
            self.btn.pack_configure(padx=(3, 0), pady=(3, 0))
            
    def _on_release(self, e):
        if self.btn['state'] != 'disabled':
            self.btn.pack_configure(padx=(0, 3), pady=(0, 3))
            
    def config(self, **kwargs):
        state = kwargs.pop('state', None)
        text = kwargs.pop('text', None)
        
        if state is not None:
            self.btn.config(state=state)
            if state == 'disabled':
                self.btn.config(bg="#E0E0DB", fg="#888888")
            else:
                self.btn.config(bg=self.bg, fg=self.fg)
                
        if text is not None:
            self.btn.config(text=text)
            
        if kwargs:
            super().config(**kwargs)
            
    def configure(self, **kwargs):
        self.config(**kwargs)

def start_devtools_proxy_server():
    """Start local proxy on 9889 that forwards to 9888 and overrides Chrome version in /json/version."""
    import socket
    import threading
    import urllib.request
    import json
    import re
    import glob

    def get_target_chrome_version():
        cache_pattern = os.path.expanduser("~/.cache/selenium/chromedriver/*/*")
        dirs = glob.glob(cache_pattern)
        versions = []
        for d in dirs:
            v_str = os.path.basename(d)
            if re.match(r'^\d+(\.\d+)+$', v_str):
                versions.append(v_str)
        if versions:
            versions.sort(key=lambda s: list(map(int, s.split('.'))))
            return f"Chrome/{versions[-1]}"
            
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon") as key:
                version, _ = winreg.QueryValueEx(key, "version")
                return f"Chrome/{version}"
        except Exception:
            pass
        return "Chrome/120.0.0.0"

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server.bind(('127.0.0.1', 9889))
        server.listen(5)
    except Exception as e:
        print(f"Proxy: DevTools Proxy port 9889 failed to bind: {e}")
        return

    def handle_client(client_sock):
        try:
            data = client_sock.recv(4096)
            if not data:
                client_sock.close()
                return

            if b"GET /json/version" in data:
                try:
                    with urllib.request.urlopen("http://127.0.0.1:9888/json/version") as response:
                        res_data = response.read().decode('utf-8')
                    parsed = json.loads(res_data)
                    
                    target_version = get_target_chrome_version()
                    parsed["Browser"] = target_version
                    if "User-Agent" in parsed:
                        ua = parsed["User-Agent"]
                        match = re.search(r'Chrome/([\d\.]+)', ua)
                        if match:
                            parsed["User-Agent"] = ua.replace(match.group(0), target_version)
                    
                    if "webSocketDebuggerUrl" in parsed:
                        parsed["webSocketDebuggerUrl"] = parsed["webSocketDebuggerUrl"].replace("9888", "9889")
                    
                    body = json.dumps(parsed).encode('utf-8')
                    http_response = (
                        b"HTTP/1.1 200 OK\r\n"
                        b"Content-Type: application/json; charset=UTF-8\r\n"
                        b"Content-Length: " + str(len(body)).encode('ascii') + b"\r\n"
                        b"Connection: close\r\n\r\n" + body
                    )
                    client_sock.sendall(http_response)
                except Exception as ex:
                    print("Proxy: Error modifying /json/version:", ex)
                client_sock.close()
                return

            target_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            target_sock.connect(('127.0.0.1', 9888))
            target_sock.sendall(data)

            def forward(src, dst):
                try:
                    while True:
                        buf = src.recv(4096)
                        if not buf:
                            break
                        dst.sendall(buf)
                except Exception:
                    pass
                finally:
                    src.close()
                    dst.close()

            threading.Thread(target=forward, args=(client_sock, target_sock), daemon=True).start()
            threading.Thread(target=forward, args=(target_sock, client_sock), daemon=True).start()

        except Exception:
            try:
                client_sock.close()
            except Exception:
                pass

    while True:
        try:
            sock, _ = server.accept()
            threading.Thread(target=handle_client, args=(sock,), daemon=True).start()
        except Exception:
            break

class NaukriAutoApplyApp:
    def __init__(self, root):
        # Start local DevTools proxy server in a background thread
        threading.Thread(target=start_devtools_proxy_server, daemon=True).start()
        
        self.root = root
        self.root.title("Naukri Auto Apply App — AI Prompt Generator Stack")
        self.root.geometry("1200x750")
        self.root.minsize(1000, 600)
        
        # State events for control
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.apply_thread = None
        
        # Window Canvas Background
        self.root.config(bg=NEO_CANVAS)
        
        # Style
        self.style = ttk.Style()
        self.style.theme_use('clam')
        
        # Custom style for Treeview
        self.style.configure(
            "Treeview",
            background=NEO_WHITE,
            foreground=NEO_TEXT,
            fieldbackground=NEO_WHITE,
            rowheight=25,
            font=("Segoe UI", 9)
        )
        self.style.map(
            "Treeview",
            background=[("selected", NEO_SECONDARY)],
            foreground=[("selected", NEO_WHITE)]
        )
        
        self.style.configure(
            "Heading",
            background=NEO_PRIMARY,
            foreground=NEO_TEXT,
            font=("Segoe UI", 9, "bold"),
            relief="solid",
            borderwidth=2
        )
        self.style.map(
            "Heading",
            background=[("active", NEO_SECONDARY)],
            foreground=[("active", NEO_WHITE)]
        )
        
        # Create Main Layout Panels
        self.create_panels()
        
        # Load Settings & Init UI Fields
        self.settings = load_settings()
        self.load_settings_into_ui()
        
        # Start Chrome status polling and stats updating loop
        self.poll_chrome_status()
        
        # Window Close Hook
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def create_panels(self):
        """Build Top, Left, Center, and Right panels."""
        # Main Frame container
        main_container = tk.Frame(self.root, bg=NEO_CANVAS)
        main_container.pack(fill="both", expand=True)

        # Top Bar for quick actions & layout toggles
        self.top_bar = tk.Frame(main_container, bg=NEO_SURFACE, bd=2, relief="solid")
        self.top_bar.pack(side="top", fill="x", padx=10, pady=(10, 5))

        # Left label/title in top bar
        title_lbl = tk.Label(self.top_bar, text="⚡ Naukri Auto Apply Robot", font=("Segoe UI", 12, "bold"), bg=NEO_SURFACE, fg=NEO_TEXT)
        title_lbl.pack(side="left", padx=10, pady=5)

        # Right side layout controls
        self.show_left_var = tk.BooleanVar(value=True)
        self.show_right_var = tk.BooleanVar(value=True)

        self.toggle_left_btn = NeoButton(
            self.top_bar, 
            text="Hide Settings & Resume", 
            command=self.toggle_left_panel,
            bg=NEO_PRIMARY
        )
        self.toggle_left_btn.pack(side="right", padx=5, pady=5)

        self.toggle_right_btn = NeoButton(
            self.top_bar, 
            text="Hide Queue & Logs", 
            command=self.toggle_right_panel,
            bg=NEO_PRIMARY
        )
        self.toggle_right_btn.pack(side="right", padx=5, pady=5)

        # Frame for content (vertical panels)
        self.content_frame = tk.Frame(main_container, bg=NEO_CANVAS)
        self.content_frame.pack(fill="both", expand=True)

        # 1. LEFT PANEL (Settings & Resume)
        self.left_panel = tk.Frame(self.content_frame, width=270, bg=NEO_SURFACE, bd=2, relief="solid")
        self.left_panel.pack(side="left", fill="y", expand=False, padx=(10, 5), pady=(5, 10))
        self.left_panel.pack_propagate(False) # lock width to 270px
        
        # 2. RIGHT PANEL (Queue & Logs - packed first to allow center to fill remaining)
        self.right_panel = tk.Frame(self.content_frame, width=330, bg=NEO_SURFACE, bd=2, relief="solid")
        self.right_panel.pack(side="right", fill="y", expand=False, padx=(5, 10), pady=(5, 10))
        self.right_panel.pack_propagate(False) # lock width to 330px
        
        # 3. CENTER PANEL (Embedded Browser)
        self.center_panel = tk.Frame(self.content_frame, bg=NEO_SURFACE, bd=2, relief="solid")
        self.center_panel.pack(side="left", fill="both", expand=True, padx=5, pady=(5, 10))

        # Build panel contents
        self.build_left_panel()
        self.build_center_panel()
        self.build_right_panel()

    def build_left_panel(self):
        """Construct Settings and Resume Upload components in Left Panel."""
        # Inner container for padding
        container = tk.Frame(self.left_panel, bg=NEO_SURFACE)
        container.pack(fill="both", expand=True, padx=12, pady=12)

        # Title
        title = tk.Label(container, text="Settings & Resume", font=("Segoe UI", 12, "bold"), bg=NEO_SURFACE, fg=NEO_TEXT)
        title.pack(anchor="w", pady=(0, 10))

        # Resume section
        resume_lbl = tk.Label(container, text="Resume Upload (.pdf or .docx):", font=("Segoe UI", 9, "bold"), bg=NEO_SURFACE, fg=NEO_TEXT)
        resume_lbl.pack(anchor="w", pady=(5, 2))
        
        self.upload_btn = NeoButton(container, text="Upload Resume", command=self.upload_resume, bg=NEO_PRIMARY)
        self.upload_btn.pack(fill="x", pady=2)
        
        self.resume_status_lbl = tk.Label(
            container, 
            text="No resume uploaded", 
            font=("Segoe UI", 8, "bold"), 
            bg="#EDECE9", 
            fg="#888888",
            bd=1,
            relief="solid",
            padx=5,
            pady=2
        )
        self.resume_status_lbl.pack(anchor="w", pady=(4, 10))
        self.update_resume_status_label()

        # Profile Links section
        links_frame = tk.LabelFrame(
            container, 
            text="Social & Profile Links", 
            font=("Segoe UI", 9, "bold"),
            bg=NEO_SURFACE, 
            fg=NEO_TEXT, 
            bd=2, 
            relief="solid",
            padx=8,
            pady=8
        )
        links_frame.pack(fill="x", pady=(5, 10))
        
        # Helper function for link rows
        def create_link_row(parent, label_text, key_name):
            row = tk.Frame(parent, bg=NEO_SURFACE)
            row.pack(fill="x", pady=4)
            tk.Label(row, text=label_text, width=8, anchor="w", font=("Segoe UI", 8, "bold"), bg=NEO_SURFACE, fg=NEO_TEXT).pack(side="left")
            entry = tk.Entry(
                row, 
                bg=NEO_WHITE, 
                fg=NEO_TEXT, 
                insertbackground=NEO_TEXT,
                font=("Segoe UI", 8),
                bd=2,
                relief="solid",
                highlightthickness=0
            )
            entry.pack(side="left", fill="x", expand=True, padx=(2, 4))
            btn = NeoButton(row, text="Go", command=lambda: self.open_link_from_entry(entry), bg=NEO_PRIMARY, font=("Segoe UI", 8, "bold"), padding=(4, 1))
            btn.pack(side="right")
            setattr(self, f"{key_name}_entry", entry)

        create_link_row(links_frame, "LinkedIn:", "linkedin")
        create_link_row(links_frame, "GitHub:", "github")
        create_link_row(links_frame, "Portfolio:", "portfolio")

        # Target Roles input
        roles_lbl = tk.Label(container, text="Target Roles (comma separated):", font=("Segoe UI", 9, "bold"), bg=NEO_SURFACE, fg=NEO_TEXT)
        roles_lbl.pack(anchor="w", pady=(5, 2))
        self.roles_entry = tk.Entry(
            container,
            bg=NEO_WHITE,
            fg=NEO_TEXT,
            insertbackground=NEO_TEXT,
            font=("Segoe UI", 9),
            bd=2,
            relief="solid",
            highlightthickness=0
        )
        self.roles_entry.pack(fill="x", pady=2)

        # Min Match Score slider
        score_lbl_frame = tk.Frame(container, bg=NEO_SURFACE)
        score_lbl_frame.pack(fill="x", pady=(10, 2))
        tk.Label(score_lbl_frame, text="Min Match Score:", font=("Segoe UI", 9, "bold"), bg=NEO_SURFACE, fg=NEO_TEXT).pack(side="left")
        self.score_val_lbl = tk.Label(score_lbl_frame, text="70%", font=("Segoe UI", 9, "bold"), bg=NEO_SURFACE, fg=NEO_TEXT)
        self.score_val_lbl.pack(side="right")
        
        self.score_slider = tk.Scale(
            container, 
            from_=0, 
            to=100, 
            orient=tk.HORIZONTAL,
            command=self.on_slider_move,
            bg=NEO_SURFACE,
            troughcolor="#EDECE9",
            activebackground=NEO_PRIMARY,
            highlightthickness=0,
            bd=2,
            relief="solid",
            showvalue=False
        )
        self.score_slider.pack(fill="x", pady=2)

        # Job Boards selection
        boards_lbl = tk.Label(container, text="Job Boards to Search:", font=("Segoe UI", 9, "bold"), bg=NEO_SURFACE, fg=NEO_TEXT)
        boards_lbl.pack(anchor="w", pady=(10, 2))
        
        self.board_vars = {}
        for board in ["Naukri", "Foundit", "Indeed", "LinkedIn"]:
            var = tk.BooleanVar(value=True if board == "Naukri" else False)
            self.board_vars[board] = var
            chk = tk.Checkbutton(
                container, 
                text=board, 
                variable=var,
                font=("Segoe UI", 9, "bold"),
                bg=NEO_SURFACE,
                fg=NEO_TEXT,
                activebackground=NEO_SURFACE,
                activeforeground=NEO_TEXT,
                selectcolor=NEO_WHITE,
                bd=0,
                highlightthickness=0
            )
            chk.pack(anchor="w", pady=1)

        # Gemini Key
        gemini_lbl = tk.Label(container, text="Gemini API Key:", font=("Segoe UI", 9, "bold"), bg=NEO_SURFACE, fg=NEO_TEXT)
        gemini_lbl.pack(anchor="w", pady=(10, 2))
        self.gemini_entry = tk.Entry(
            container, 
            show="*",
            bg=NEO_WHITE,
            fg=NEO_TEXT,
            insertbackground=NEO_TEXT,
            font=("Segoe UI", 9),
            bd=2,
            relief="solid",
            highlightthickness=0
        )
        self.gemini_entry.pack(fill="x", pady=2)

        # Grok Key
        grok_lbl = tk.Label(container, text="Grok API Key:", font=("Segoe UI", 9, "bold"), bg=NEO_SURFACE, fg=NEO_TEXT)
        grok_lbl.pack(anchor="w", pady=(10, 2))
        self.grok_entry = tk.Entry(
            container, 
            show="*",
            bg=NEO_WHITE,
            fg=NEO_TEXT,
            insertbackground=NEO_TEXT,
            font=("Segoe UI", 9),
            bd=2,
            relief="solid",
            highlightthickness=0
        )
        self.grok_entry.pack(fill="x", pady=2)

        # Action buttons
        self.save_btn = NeoButton(container, text="Save Settings", command=self.save_settings_from_ui, bg=NEO_SECONDARY, fg=NEO_WHITE)
        self.save_btn.pack(fill="x", pady=(15, 5))

        self.reset_btn = NeoButton(container, text="Reset All Data", command=self.trigger_reset, bg=NEO_DANGER, fg=NEO_WHITE)
        self.reset_btn.pack(fill="x", pady=5)

    def build_center_panel(self):
        """Construct Center Panel control dashboard."""
        container = tk.Frame(self.center_panel, bg=NEO_SURFACE)
        container.pack(fill="both", expand=True, padx=15, pady=15)
        
        # 1. Header Section
        header_lbl = tk.Label(
            container, 
            text="⚡ ROBOT CONTROL CENTER", 
            font=("Segoe UI", 14, "bold"), 
            bg=NEO_PRIMARY, 
            fg=NEO_TEXT,
            bd=2,
            relief="solid",
            padx=10,
            pady=5
        )
        header_lbl.pack(fill="x", pady=(0, 15))
        
        # 2. Chrome Status Section
        status_frame = tk.LabelFrame(
            container, 
            text="Chrome Automation Status", 
            font=("Segoe UI", 10, "bold"),
            bg=NEO_SURFACE, 
            fg=NEO_TEXT, 
            bd=2, 
            relief="solid",
            padx=10,
            pady=10
        )
        status_frame.pack(fill="x", pady=(0, 15))
        
        status_row = tk.Frame(status_frame, bg=NEO_SURFACE)
        status_row.pack(fill="x", pady=5)
        
        tk.Label(status_row, text="Browser Connection:", font=("Segoe UI", 9, "bold"), bg=NEO_SURFACE, fg=NEO_TEXT).pack(side="left")
        self.chrome_status_val = tk.Label(
            status_row, 
            text="DISCONNECTED (Inactive)", 
            font=("Segoe UI", 9, "bold"), 
            bg="#FEF3C7", 
            fg=NEO_WARNING,
            bd=1,
            relief="solid",
            padx=6,
            pady=2
        )
        self.chrome_status_val.pack(side="left", padx=10)
        
        self.launch_chrome_btn = NeoButton(
            status_frame, 
            text="🚀 Launch Google Chrome Browser", 
            command=self.launch_chrome_ui, 
            bg=NEO_PRIMARY
        )
        self.launch_chrome_btn.pack(fill="x", pady=(10, 5))
        
        note_lbl = tk.Label(
            status_frame, 
            text="Note: Logging into Naukri, Indeed, LinkedIn, etc., in this Chrome window once\nkeeps you signed in permanently due to the persistent automation profile.", 
            font=("Segoe UI", 8, "italic"), 
            bg=NEO_SURFACE, 
            fg="#555555",
            justify="left"
        )
        note_lbl.pack(anchor="w", pady=(5, 0))
        
        # 3. Statistics Section
        stats_frame = tk.LabelFrame(
            container, 
            text="Automation Queue Statistics", 
            font=("Segoe UI", 10, "bold"),
            bg=NEO_SURFACE, 
            fg=NEO_TEXT, 
            bd=2, 
            relief="solid",
            padx=10,
            pady=10
        )
        stats_frame.pack(fill="x", pady=(0, 15))
        
        # Helper for a stats card inside a grid
        stats_grid = tk.Frame(stats_frame, bg=NEO_SURFACE)
        stats_grid.pack(fill="x", expand=True)
        
        def make_stat_card(parent, title, val_attr, color, col_idx):
            card = tk.Frame(parent, bg=NEO_SURFACE, bd=2, relief="solid")
            card.grid(row=0, column=col_idx, sticky="nsew", padx=5, pady=5)
            parent.grid_columnconfigure(col_idx, weight=1)
            
            tk.Label(card, text=title, font=("Segoe UI", 8, "bold"), bg=NEO_SURFACE, fg="#666666").pack(pady=(4, 2))
            val_lbl = tk.Label(card, text="0", font=("Segoe UI", 16, "bold"), bg=NEO_SURFACE, fg=color)
            val_lbl.pack(pady=(2, 4))
            setattr(self, val_attr, val_lbl)
            
        make_stat_card(stats_grid, "Total Scraped", "stats_scraped_val", NEO_TEXT, 0)
        make_stat_card(stats_grid, "Jobs Applied", "stats_applied_val", NEO_SUCCESS, 1)
        make_stat_card(stats_grid, "Skipped / Manual", "stats_skipped_val", NEO_WARNING, 2)
        
        # 4. User Guide Section
        guide_frame = tk.LabelFrame(
            container, 
            text="Workflow Instructions", 
            font=("Segoe UI", 10, "bold"),
            bg=NEO_SURFACE, 
            fg=NEO_TEXT, 
            bd=2, 
            relief="solid",
            padx=10,
            pady=10
        )
        guide_frame.pack(fill="both", expand=True)
        
        instructions = (
            "1. Click the 'Launch Google Chrome Browser' button above.\n"
            "2. In the opened Chrome window, navigate to your job boards (Naukri, etc.) and complete your sign-in.\n"
            "3. Upload your resume and update target job roles on the left panel, then save settings.\n"
            "4. Press 'Start Auto Apply' on the right panel to run the scraper and apply automatically.\n"
            "5. Keep the Chrome browser window open while the automation is running."
        )
        
        guide_lbl = tk.Label(
            guide_frame, 
            text=instructions, 
            font=("Segoe UI", 9), 
            bg=NEO_SURFACE, 
            fg=NEO_TEXT, 
            justify="left", 
            anchor="nw"
        )
        guide_lbl.pack(fill="both", expand=True, pady=5)

    def build_right_panel(self):
        """Construct Queue and Live Logs in Right Panel."""
        # Inner container for padding
        container = tk.Frame(self.right_panel, bg=NEO_SURFACE)
        container.pack(fill="both", expand=True, padx=12, pady=12)

        # Controls Frame
        ctrl_frame = tk.Frame(container, bg=NEO_SURFACE)
        ctrl_frame.pack(fill="x", pady=(0, 10))
        
        self.start_btn = NeoButton(ctrl_frame, text="Start Auto Apply", command=self.start_apply_flow, bg=NEO_SUCCESS, fg=NEO_WHITE)
        self.start_btn.pack(fill="x", pady=2)
        
        btn_sub_frame = tk.Frame(ctrl_frame, bg=NEO_SURFACE)
        btn_sub_frame.pack(fill="x", pady=2)
        
        self.pause_btn = NeoButton(btn_sub_frame, text="Pause", command=self.toggle_pause, bg=NEO_WARNING, fg=NEO_WHITE)
        self.pause_btn.pack(side="left", fill="x", expand=True, padx=(0, 2))
        self.pause_btn.config(state="disabled")
        
        self.stop_btn = NeoButton(btn_sub_frame, text="Stop", command=self.stop_apply_flow, bg=NEO_DANGER, fg=NEO_WHITE)
        self.stop_btn.pack(side="right", fill="x", expand=True, padx=(2, 0))
        self.stop_btn.config(state="disabled")

        # Jobs Queue List (Treeview)
        queue_lbl = tk.Label(container, text="Jobs Queue:", font=("Segoe UI", 9, "bold"), bg=NEO_SURFACE, fg=NEO_TEXT)
        queue_lbl.pack(anchor="w", pady=(10, 2))
        
        columns = ("title", "company", "score", "status")
        self.tree = ttk.Treeview(container, columns=columns, show="headings", height=8)
        self.tree.heading("title", text="Job Title")
        self.tree.heading("company", text="Company")
        self.tree.heading("score", text="Match")
        self.tree.heading("status", text="Status")
        
        self.tree.column("title", width=95, anchor="w")
        self.tree.column("company", width=80, anchor="w")
        self.tree.column("score", width=45, anchor="center")
        self.tree.column("status", width=65, anchor="center")
        
        # Add scrollbar to Treeview
        tree_scroll = ttk.Scrollbar(container, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        
        self.tree.pack(fill="x", expand=False)
        tree_scroll.pack(fill="x", pady=(0, 2))

        # Open Selected Job in Browser
        self.open_job_btn = NeoButton(container, text="Open Selected Job in Browser", command=self.open_selected_job, bg=NEO_PRIMARY)
        self.open_job_btn.pack(fill="x", pady=(2, 10))
        
        # Bind double click event
        self.tree.bind("<Double-1>", lambda event: self.open_selected_job())

        # Live Logs text area
        log_lbl = tk.Label(container, text="Live Log output:", font=("Segoe UI", 9, "bold"), bg=NEO_SURFACE, fg=NEO_TEXT)
        log_lbl.pack(anchor="w", pady=(5, 2))
        
        self.log_txt = tk.Text(
            container, 
            height=12, 
            wrap="word", 
            font=("Consolas", 8),
            bg=NEO_TEXT,
            fg=NEO_PRIMARY,
            insertbackground=NEO_PRIMARY,
            bd=2,
            relief="solid",
            highlightthickness=0
        )
        self.log_txt.pack(fill="both", expand=True)
        
        # Setup polling for queue updates
        self.poll_queue_updates()

    # Callback Logic
    def on_slider_move(self, val):
        self.score_val_lbl.config(text=f"{int(float(val))}%")

    def load_settings_into_ui(self):
        """Populate settings fields on startup."""
        self.roles_entry.delete(0, tk.END)
        self.roles_entry.insert(0, self.settings.get("target_roles", ""))
        
        score = self.settings.get("min_match_score", 70)
        self.score_slider.set(score)
        self.score_val_lbl.config(text=f"{score}%")
        
        self.gemini_entry.delete(0, tk.END)
        self.gemini_entry.insert(0, self.settings.get("gemini_api_key", ""))
        
        self.grok_entry.delete(0, tk.END)
        self.grok_entry.insert(0, self.settings.get("grok_api_key", ""))
        
        enabled_boards = self.settings.get("enabled_boards", ["Naukri"])
        for board, var in self.board_vars.items():
            var.set(board in enabled_boards)

        # Load links
        linkedin_val = self.settings.get("linkedin_url", "")
        github_val = self.settings.get("github_url", "")
        portfolio_val = self.settings.get("portfolio_url", "")
        
        # Fallback to resume data if not set in settings
        if not linkedin_val or not github_val or not portfolio_val:
            if os.path.exists(RESUME_DATA_FILE):
                try:
                    with open(RESUME_DATA_FILE, "r", encoding="utf-8") as f:
                        resume_data = json.load(f)
                    links = resume_data.get("links", {})
                    if not linkedin_val:
                        linkedin_val = links.get("linkedin") or ""
                    if not github_val:
                        github_val = links.get("github") or ""
                    if not portfolio_val:
                        portfolio_val = links.get("portfolio") or ""
                except Exception:
                    pass
                    
        self.linkedin_entry.delete(0, tk.END)
        self.linkedin_entry.insert(0, linkedin_val)
        
        self.github_entry.delete(0, tk.END)
        self.github_entry.insert(0, github_val)
        
        self.portfolio_entry.delete(0, tk.END)
        self.portfolio_entry.insert(0, portfolio_val)

    def save_settings_from_ui(self):
        """Read UI inputs and save to settings.json."""
        enabled_boards = [board for board, var in self.board_vars.items() if var.get()]
        if not enabled_boards:
            messagebox.showerror("Error", "Please select at least one job board.")
            return
            
        self.settings["target_roles"] = self.roles_entry.get().strip()
        self.settings["min_match_score"] = int(self.score_slider.get())
        self.settings["gemini_api_key"] = self.gemini_entry.get().strip()
        self.settings["grok_api_key"] = self.grok_entry.get().strip()
        self.settings["enabled_boards"] = enabled_boards
        
        self.settings["linkedin_url"] = self.linkedin_entry.get().strip()
        self.settings["github_url"] = self.github_entry.get().strip()
        self.settings["portfolio_url"] = self.portfolio_entry.get().strip()
        
        # Sync to resume_data.json if it exists
        if os.path.exists(RESUME_DATA_FILE):
            try:
                with open(RESUME_DATA_FILE, "r", encoding="utf-8") as f:
                    resume_data = json.load(f)
                if "links" not in resume_data:
                    resume_data["links"] = {}
                resume_data["links"]["linkedin"] = self.linkedin_entry.get().strip() or None
                resume_data["links"]["github"] = self.github_entry.get().strip() or None
                resume_data["links"]["portfolio"] = self.portfolio_entry.get().strip() or None
                with open(RESUME_DATA_FILE, "w", encoding="utf-8") as f:
                    json.dump(resume_data, f, indent=2)
            except Exception as e:
                print(f"Error syncing links to resume data: {e}")
        
        if save_settings(self.settings):
            messagebox.showinfo("Settings Saved", "Settings successfully saved to settings.json.")
            self.log("System: Settings updated successfully.")
        else:
            messagebox.showerror("Error", "Failed to save settings.")

    def trigger_reset(self):
        """Prompt to clear user data and delete files."""
        confirm = messagebox.askyesno(
            "Confirm Reset", 
            "Are you sure you want to reset all data?\nThis will delete your resume, cookies, queue, and logs. Settings will be preserved."
        )
        if confirm:
            from resume_parser import clear_cache
            clear_cache()
            deleted = reset_all_data()
            self.update_resume_status_label()
            self.log_txt.delete("1.0", tk.END)
            self.log(f"System: Data reset complete. Deleted files: {', '.join(deleted) if deleted else 'None'}")
            messagebox.showinfo("Reset Complete", "All data files have been cleared successfully.")

    def update_resume_status_label(self):
        """Check if parsed resume data exists and update UI label."""
        if os.path.exists(RESUME_DATA_FILE):
            try:
                with open(RESUME_DATA_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                name = data.get("name", "Candidate")
                exp = data.get("total_years_experience", "N/A")
                self.resume_status_lbl.config(
                    text=f"Uploaded: {name} (Exp: {exp})", 
                    bg="#DCFCE7", 
                    fg="#16A34A"
                )
            except Exception:
                self.resume_status_lbl.config(
                    text="Corrupt resume data", 
                    bg="#FEE2E2", 
                    fg="#DC2626"
                )
        else:
            self.resume_status_lbl.config(
                text="No resume uploaded", 
                bg="#EDECE9", 
                fg="#888888"
            )

    def upload_resume(self):
        """Open file dialog, extract text, call Gemini parsing, copy original file."""
        file_path = filedialog.askopenfilename(
            title="Select Resume File",
            filetypes=[("Resume Files", "*.pdf;*.docx"), ("PDF Files", "*.pdf"), ("Word Files", "*.docx")]
        )
        if not file_path:
            return

        self.log(f"System: Selected resume: {os.path.basename(file_path)}")
        self.upload_btn.config(state="disabled")
        self.resume_status_lbl.config(text="Processing...", foreground="blue")
        
        def run_parser():
            try:
                # 1. Parse using Gemini
                data = parse_and_save_resume(file_path)
                
                # 2. Copy the actual resume file to static location in data/
                ext = os.path.splitext(file_path)[1].lower()
                dest_path = os.path.join(DATA_DIR, f"resume{ext}")
                
                # Remove old file if it exists with a different extension
                for old_ext in ['.pdf', '.docx']:
                    old_path = os.path.join(DATA_DIR, f"resume{old_ext}")
                    if os.path.exists(old_path):
                        os.remove(old_path)
                        
                shutil.copy(file_path, dest_path)
                
                self.root.after(0, lambda: self.on_parser_success(data))
            except Exception as e:
                err_msg = str(e)
                self.root.after(0, lambda: self.on_parser_error(err_msg))
                
        threading.Thread(target=run_parser, daemon=True).start()

    def on_parser_success(self, data):
        self.upload_btn.config(state="normal")
        self.update_resume_status_label()
        self.log(f"System: Resume parsed successfully. Candidate name: {data.get('name')}")
        
        # Save parsed links from resume data directly to settings
        links = data.get("links", {})
        if isinstance(links, dict):
            self.settings["linkedin_url"] = links.get("linkedin") or ""
            self.settings["github_url"] = links.get("github") or ""
            self.settings["portfolio_url"] = links.get("portfolio") or ""
            
        # Automatically update target roles based on AI recommendations from the resume
        target_roles = data.get("target_roles")
        if target_roles and isinstance(target_roles, list):
            roles_str = ", ".join([r.strip() for r in target_roles if r.strip()])
            if roles_str:
                self.settings["target_roles"] = roles_str
                
        save_settings(self.settings)
        self.load_settings_into_ui()
        if target_roles:
            self.log(f"System: Automatically set target roles: {roles_str}")
                
        messagebox.showinfo("Resume Processed", f"Successfully parsed resume for {data.get('name')}.")

    def on_parser_error(self, err_msg):
        self.upload_btn.config(state="normal")
        self.update_resume_status_label()
        self.log(f"System Error parsing resume: {err_msg}")
        messagebox.showerror("Error Parsing Resume", f"Failed to parse resume:\n{err_msg}")

    def launch_chrome_ui(self):
        """Launch Google Chrome debugging session from the UI."""
        from job_scraper import launch_chrome_debugging, is_port_active
        if is_port_active(9222):
            messagebox.showinfo("Browser Running", "Google Chrome is already running on debugging port 9222.")
            return
            
        self.log("System: Starting Google Chrome debugging browser...")
        try:
            launch_chrome_debugging(9222)
            self.log("System: Google Chrome debugging browser launched successfully.")
        except Exception as e:
            self.log(f"System Error launching Chrome: {e}")
            messagebox.showerror("Launch Error", f"Failed to launch Google Chrome:\n{e}")

    def poll_chrome_status(self):
        """Check if Chrome debugging port 9222 is active and update dashboard status."""
        from job_scraper import is_port_active
        active = is_port_active(9222)
        if active:
            if hasattr(self, 'chrome_status_val') and self.chrome_status_val.winfo_exists():
                self.chrome_status_val.config(text="CONNECTED (Port 9222)", fg=NEO_SUCCESS, bg="#DCFCE7")
        else:
            if hasattr(self, 'chrome_status_val') and self.chrome_status_val.winfo_exists():
                self.chrome_status_val.config(text="DISCONNECTED (Inactive)", fg=NEO_WARNING, bg="#FEF3C7")
            
        self.update_dashboard_stats()
        self.root.after(2000, self.poll_chrome_status)

    def update_dashboard_stats(self):
        """Read jobs queue and update stats on the dashboard."""
        scraped_cnt = 0
        applied_cnt = 0
        skipped_cnt = 0
        
        if os.path.exists(JOBS_QUEUE_FILE):
            try:
                with open(JOBS_QUEUE_FILE, "r", encoding="utf-8") as f:
                    jobs = json.load(f)
                if isinstance(jobs, list):
                    scraped_cnt = len(jobs)
                    for j in jobs:
                        status = j.get("status")
                        if status == "Applied":
                            applied_cnt += 1
                        elif status in ("Skipped", "Manual Required"):
                            skipped_cnt += 1
            except Exception:
                pass
                
        if hasattr(self, 'stats_scraped_val') and self.stats_scraped_val.winfo_exists():
            self.stats_scraped_val.config(text=str(scraped_cnt))
        if hasattr(self, 'stats_applied_val') and self.stats_applied_val.winfo_exists():
            self.stats_applied_val.config(text=str(applied_cnt))
        if hasattr(self, 'stats_skipped_val') and self.stats_skipped_val.winfo_exists():
            self.stats_skipped_val.config(text=str(skipped_cnt))

    # Logging helper
    def log(self, msg):
        """Add message to live logs in a thread-safe way."""
        def append():
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.log_txt.insert(tk.END, f"[{timestamp}] {msg}\n")
            self.log_txt.see(tk.END)
        self.root.after(0, append)

    # Queue Polling
    def poll_queue_updates(self):
        """Periodically refresh Treeview from jobs_queue.json."""
        if os.path.exists(JOBS_QUEUE_FILE):
            try:
                # Store selection
                selected = self.tree.selection()
                selected_idx = int(selected[0]) if selected else None
                
                # Clear
                for item in self.tree.get_children():
                    self.tree.delete(item)
                    
                with open(JOBS_QUEUE_FILE, "r", encoding="utf-8") as f:
                    jobs = json.load(f)
                    
                for idx, j in enumerate(jobs):
                    title = j.get("title", "N/A")
                    company = j.get("company", "N/A")
                    score = f"{int(j['score'])}%" if j.get("score") is not None else "N/A"
                    status = j.get("status", "Pending")
                    
                    item = self.tree.insert("", "end", iid=str(idx), values=(title, company, score, status))
                    if selected_idx is not None and idx == selected_idx:
                        self.tree.selection_set(item)
            except Exception:
                pass
        self.root.after(2000, self.poll_queue_updates)

    def set_left_panel_state(self, state):
        """Enable or disable all inputs within the left panel recursively."""
        def set_state_recursive(widget):
            try:
                widget.config(state=state)
            except tk.TclError:
                pass
            for child in widget.winfo_children():
                set_state_recursive(child)
        set_state_recursive(self.left_panel)

    # Flow controllers
    def start_apply_flow(self):
        """Start job scraping and application loop in a thread."""
        if not os.path.exists(RESUME_DATA_FILE):
            messagebox.showerror("Resume Required", "Please upload and parse your resume before starting.")
            return
            
        self.start_btn.config(state="disabled")
        self.pause_btn.config(state="normal", text="Pause")
        self.stop_btn.config(state="normal")
        self.set_left_panel_state("disabled")
        
        self.stop_event.clear()
        self.pause_event.clear()
        
        def execution_loop():
            try:
                self.log("Workflow: Starting auto apply workflow (Bulk Recommended Jobs)...")
                from auto_applier import run_bulk_recommended_apply
                run_bulk_recommended_apply(self.stop_event, self.pause_event, logger=self.log)
                self.log("Workflow: Process finished.")
            except Exception as e:
                self.log(f"Workflow Critical Error: {e}")
            finally:
                self.root.after(0, self.on_flow_complete)

        self.apply_thread = threading.Thread(target=execution_loop, daemon=True)
        self.apply_thread.start()

    def on_flow_complete(self):
        self.start_btn.config(state="normal")
        self.pause_btn.config(state="disabled", text="Pause")
        self.stop_btn.config(state="disabled")
        self.set_left_panel_state("normal")
        self.log("System: Core applier thread has completed execution.")

    def toggle_pause(self):
        if self.pause_event.is_set():
            self.pause_event.clear()
            self.pause_btn.config(text="Pause")
            self.log("Workflow: Resumed.")
        else:
            self.pause_event.set()
            self.pause_btn.config(text="Resume")
            self.log("Workflow: Paused.")

    def stop_apply_flow(self):
        self.stop_event.set()
        self.pause_event.clear()
        self.log("Workflow: Stopping... please wait for thread cleanup.")
        self.stop_btn.config(state="disabled")

    def open_link_from_entry(self, entry):
        url = entry.get().strip()
        if url:
            if not url.startswith("http://") and not url.startswith("https://"):
                url = "https://" + url
            self.open_url_in_browser(url)
        else:
            messagebox.showwarning("No Link", "This profile link field is empty.")

    def open_url_in_browser(self, url):
        """Open URL in the Chrome debugging browser window, reusing existing session tabs if active."""
        from job_scraper import get_chrome_executable_path, is_port_active, launch_chrome_debugging
        
        if not url.startswith("http://") and not url.startswith("https://"):
            url = "https://" + url
            
        if is_port_active(9222):
            try:
                from selenium import webdriver
                from selenium.webdriver.chrome.options import Options
                options = Options()
                options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
                driver = webdriver.Chrome(options=options)
                # Inject JS to open URL in a new tab of the existing Chrome instance, inheriting cookies/login natively
                driver.execute_script("window.open(arguments[0], '_blank');", url)
                self.log(f"System: Opened URL in a new tab of the active Chrome session: {url}")
                return
            except Exception as e:
                self.log(f"System Warning: Failed to open tab via running session: {e}. Attempting full launch fallback...")
                
        # Fallback if port 9222 is inactive or connection failed: launch Chrome cleanly
        self.log(f"System: Launching Chrome with remote debugging on port 9222 to open: {url}")
        try:
            launch_chrome_debugging(9222, url)
        except Exception as e:
            self.log(f"System Error launching Chrome: {e}. Falling back to default OS web browser.")
            import webbrowser
            webbrowser.open(url)

    def open_selected_job(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Selection Required", "Please select a job from the queue first.")
            return
        
        idx_str = selected[0]
        try:
            idx = int(idx_str)
            if os.path.exists(JOBS_QUEUE_FILE):
                with open(JOBS_QUEUE_FILE, "r", encoding="utf-8") as f:
                    jobs = json.load(f)
                if 0 <= idx < len(jobs):
                    url = jobs[idx].get("apply_url")
                    if url:
                        self.open_url_in_browser(url)
                    else:
                        messagebox.showerror("Error", "No URL found for the selected job.")
        except Exception as e:
            self.log(f"System Error: Failed to open job URL: {e}")

    def on_close(self):
        """Clean up background threads and processes on window close."""
        self.stop_event.set()
        self.root.destroy()

    def toggle_left_panel(self):
        if self.show_left_var.get():
            self.show_left_var.set(False)
            self.toggle_left_btn.config(text="Show Settings & Resume")
        else:
            self.show_left_var.set(True)
            self.toggle_left_btn.config(text="Hide Settings & Resume")
        self.update_panel_layout()

    def toggle_right_panel(self):
        if self.show_right_var.get():
            self.show_right_var.set(False)
            self.toggle_right_btn.config(text="Show Queue & Logs")
        else:
            self.show_right_var.set(True)
            self.toggle_right_btn.config(text="Hide Queue & Logs")
        self.update_panel_layout()

    def update_panel_layout(self):
        # Unpack all three
        self.left_panel.pack_forget()
        self.right_panel.pack_forget()
        self.center_panel.pack_forget()
        
        # Pack Left if visible
        if self.show_left_var.get():
            self.left_panel.pack(side="left", fill="y", expand=False, padx=(10, 5), pady=(5, 10))
            
        # Pack Right if visible
        if self.show_right_var.get():
            self.right_panel.pack(side="right", fill="y", expand=False, padx=(5, 10), pady=(5, 10))
            
        # Pack Center to fill remaining space
        self.center_panel.pack(side="left", fill="both", expand=True, padx=5, pady=(5, 10))

def main():
    # Set Windows DPI Awareness
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    # Start the Tkinter UI in the main process
    root = tk.Tk()
    _ = NaukriAutoApplyApp(root)
    root.mainloop()

if __name__ == '__main__':
    main()
