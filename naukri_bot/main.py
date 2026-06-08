import os
import sys
import queue
import threading
import asyncio
import json
from datetime import datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText

# Absolute imports within package folder
from .settings import Settings
from .ai_engine import AIEngine
from .apply_logger import ApplyLogger
from .resume_parser import ResumeParser
from .naukri_bot import NaukriAutomation

# Custom Palette - Catppuccin Macchiato/Mocha Inspired
COLOR_BG = "#1e1e2e"       # Main background
COLOR_CONTAINER = "#252538"# Sub-containers
COLOR_INPUT_BG = "#181825" # Text fields / Terminal
COLOR_TEXT = "#cdd6f4"     # Standard text
COLOR_ACCENT = "#89b4fa"   # Primary action blue
COLOR_ACCENT_HOVER = "#a6adc8"
COLOR_SUCCESS = "#a6e3a1"  # Green
COLOR_DANGER = "#f38ba8"   # Red
COLOR_WARNING = "#f9e2af"  # Yellow

class ModernBotApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Naukri.com AI Auto-Apply Assistant")
        self.root.geometry("900x650")
        self.root.configure(bg=COLOR_BG)

        # Initialize configurations & data layers
        self.settings = Settings()
        self.apply_logger = ApplyLogger()
        self.resume_parser = ResumeParser()

        # Threading state variables
        self.running = False
        self.stop_event = asyncio.Event()
        self.pause_event = asyncio.Event()
        self.log_queue = queue.Queue()
        
        # Keep track of counts for display
        self.applied_count = self.apply_logger.get_daily_applied_count()
        self.skipped_count = 0
        self.session_status = "Active"

        # Apply general UI styling configuration
        self.setup_styles()

        # Create Layout
        self.create_widgets()

        # Start periodic log polling
        self.root.after(100, self.poll_log_queue)

        # Dynamically suggest targeted roles on launch based on the cached resume
        self.root.after(1000, self.suggest_roles_on_launch)

    def setup_styles(self) -> None:
        """Configures ttk layouts, borders, and styles."""
        self.style = ttk.Style()
        self.style.theme_use("default")
        
        # Notebook (Tabs) Styling
        self.style.configure("TNotebook", background=COLOR_BG, borderwidth=0)
        self.style.configure(
            "TNotebook.Tab", 
            background=COLOR_CONTAINER, 
            foreground=COLOR_TEXT, 
            padding=[20, 8], 
            font=("Segoe UI", 10, "bold"),
            borderwidth=0
        )
        self.style.map(
            "TNotebook.Tab", 
            background=[("selected", COLOR_ACCENT)], 
            foreground=[("selected", "#11111b")]
        )

        # Treeview (Log Table) Styling
        self.style.configure(
            "Treeview", 
            background=COLOR_CONTAINER, 
            foreground=COLOR_TEXT, 
            fieldbackground=COLOR_CONTAINER, 
            rowheight=25,
            font=("Segoe UI", 9)
        )
        self.style.configure(
            "Treeview.Heading", 
            background=COLOR_INPUT_BG, 
            foreground=COLOR_TEXT, 
            font=("Segoe UI", 10, "bold"),
            borderwidth=0
        )
        self.style.map(
            "Treeview", 
            background=[("selected", COLOR_ACCENT)], 
            foreground=[("selected", "#11111b")]
        )

        # Scrollbar Styling
        self.style.configure("Vertical.TScrollbar", background=COLOR_CONTAINER, borderwidth=0)

    def create_custom_button(self, parent, text, command, bg=COLOR_ACCENT, fg="#11111b", active_bg=COLOR_ACCENT_HOVER, active_fg="#11111b") -> tk.Button:
        """Generates a flat, modern-looking Tkinter button with hover interactions."""
        btn = tk.Button(
            parent,
            text=text,
            command=command,
            bg=bg,
            fg=fg,
            activebackground=active_bg,
            activeforeground=active_fg,
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            bd=0,
            padx=15,
            pady=8,
            cursor="hand2"
        )
        btn.bind("<Enter>", lambda e: btn.config(bg=active_bg))
        btn.bind("<Leave>", lambda e: btn.config(bg=bg))
        return btn

    def create_custom_entry(self, parent, width=35, show=None) -> tk.Entry:
        """Generates a matching flat, themed input field."""
        return tk.Entry(
            parent,
            width=width,
            show=show,
            bg=COLOR_INPUT_BG,
            fg=COLOR_TEXT,
            insertbackground=COLOR_TEXT,
            relief="flat",
            bd=5,
            font=("Segoe UI", 10)
        )

    def create_widgets(self) -> None:
        """Assembles frames and pages."""
        # Top Header Bar
        header = tk.Frame(self.root, bg=COLOR_CONTAINER, height=60)
        header.pack(fill="x", side="top")
        
        lbl_title = tk.Label(
            header, 
            text="NAUKRI.COM AUTO-APPLIER (AI-UPGRADED)", 
            font=("Segoe UI", 14, "bold"), 
            bg=COLOR_CONTAINER, 
            fg=COLOR_ACCENT
        )
        lbl_title.pack(side="left", padx=20, pady=15)

        # Main Tab Control Frame
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)

        # Tab Frames
        self.tab_settings = tk.Frame(self.notebook, bg=COLOR_BG)
        self.tab_automation = tk.Frame(self.notebook, bg=COLOR_BG)
        self.tab_logs = tk.Frame(self.notebook, bg=COLOR_BG)
        self.tab_resume = tk.Frame(self.notebook, bg=COLOR_BG)

        self.notebook.add(self.tab_settings, text=" Settings ")
        self.notebook.add(self.tab_automation, text=" Automation ")
        self.notebook.add(self.tab_logs, text=" Apply Log ")
        self.notebook.add(self.tab_resume, text=" Resume Parsing ")

        # Draw tabs
        self.draw_settings_tab()
        self.draw_automation_tab()
        self.draw_logs_tab()
        self.draw_resume_tab()

        # Bottom Status Bar
        self.status_bar = tk.Frame(self.root, bg=COLOR_CONTAINER, height=30)
        self.status_bar.pack(fill="x", side="bottom")
        
        self.lbl_status = tk.Label(
            self.status_bar, 
            text=f"Status: Stopped | Applied: {self.applied_count} | Skipped: {self.skipped_count} | Session: {self.session_status}",
            bg=COLOR_CONTAINER, 
            fg=COLOR_TEXT, 
            font=("Segoe UI", 9)
        )
        self.lbl_status.pack(side="left", padx=15, pady=5)

        # Hook notebook change to load apply logs dynamically
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)

    # ==========================================
    # TAB 1: SETTINGS
    # ==========================================
    def draw_settings_tab(self) -> None:
        container = tk.Frame(self.tab_settings, bg=COLOR_CONTAINER, padx=25, pady=25)
        container.pack(fill="both", expand=True, padx=20, pady=20)

        # Row 0: Gemini Key
        tk.Label(container, text="Gemini API Key:", bg=COLOR_CONTAINER, fg=COLOR_TEXT, font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w", pady=10)
        self.ent_gemini = self.create_custom_entry(container, show="*")
        self.ent_gemini.insert(0, self.settings.get("gemini_api_key", ""))
        self.ent_gemini.grid(row=0, column=1, padx=20, pady=10, sticky="w")

        # Row 1: Groq Key
        tk.Label(container, text="Groq API Key (Fallback):", bg=COLOR_CONTAINER, fg=COLOR_TEXT, font=("Segoe UI", 10, "bold")).grid(row=1, column=0, sticky="w", pady=10)
        self.ent_groq = self.create_custom_entry(container, show="*")
        self.ent_groq.insert(0, self.settings.get("groq_api_key", ""))
        self.ent_groq.grid(row=1, column=1, padx=20, pady=10, sticky="w")

        # Row 2: Target Roles
        tk.Label(container, text="Target Role Keywords:", bg=COLOR_CONTAINER, fg=COLOR_TEXT, font=("Segoe UI", 10, "bold")).grid(row=2, column=0, sticky="w", pady=10)
        self.ent_roles = self.create_custom_entry(container, width=50)
        self.ent_roles.insert(0, self.settings.get("target_roles", ""))
        self.ent_roles.grid(row=2, column=1, padx=20, pady=10, sticky="w")
        tk.Label(container, text="Comma separated (e.g. Python Developer, Data Engineer)", bg=COLOR_CONTAINER, fg=COLOR_ACCENT_HOVER, font=("Segoe UI", 8)).grid(row=3, column=1, padx=20, sticky="w")

        # Row 4: Score Slider
        tk.Label(container, text="Min Score Threshold:", bg=COLOR_CONTAINER, fg=COLOR_TEXT, font=("Segoe UI", 10, "bold")).grid(row=4, column=0, sticky="w", pady=15)
        
        slider_frame = tk.Frame(container, bg=COLOR_CONTAINER)
        slider_frame.grid(row=4, column=1, padx=20, pady=15, sticky="w")
        
        self.slider_val = tk.IntVar(value=self.settings.get("min_score", 70))
        self.lbl_slider_display = tk.Label(slider_frame, textvariable=self.slider_val, bg=COLOR_CONTAINER, fg=COLOR_ACCENT, font=("Segoe UI", 10, "bold"), width=3)
        self.lbl_slider_display.pack(side="right", padx=10)

        self.slider_score = tk.Scale(
            slider_frame, 
            from_=0, 
            to=100, 
            orient="horizontal", 
            variable=self.slider_val, 
            bg=COLOR_CONTAINER, 
            fg=COLOR_TEXT,
            troughcolor=COLOR_INPUT_BG,
            highlightthickness=0, 
            bd=0, 
            showvalue=False,
            width=12,
            length=200
        )
        self.slider_score.pack(side="left")

        # Row 5: Daily Limit
        tk.Label(container, text="Daily Application Limit:", bg=COLOR_CONTAINER, fg=COLOR_TEXT, font=("Segoe UI", 10, "bold")).grid(row=5, column=0, sticky="w", pady=10)
        self.ent_limit = self.create_custom_entry(container, width=10)
        self.ent_limit.insert(0, str(self.settings.get("daily_limit", 50)))
        self.ent_limit.grid(row=5, column=1, padx=20, pady=10, sticky="w")

        # Save Button
        btn_save = self.create_custom_button(container, "Save Configuration", self.save_settings)
        btn_save.grid(row=6, column=1, padx=20, pady=25, sticky="w")

    def save_settings(self) -> None:
        """Saves values to persistent store."""
        try:
            limit = int(self.ent_limit.get().strip())
            score = self.slider_val.get()
        except ValueError:
            messagebox.showerror("Validation Error", "Please provide integer values for Score and Daily Limit.")
            return

        self.settings.save({
            "gemini_api_key": self.ent_gemini.get().strip(),
            "groq_api_key": self.ent_groq.get().strip(),
            "target_roles": self.ent_roles.get().strip(),
            "min_score": score,
            "daily_limit": limit
        })
        messagebox.showinfo("Success", "Configuration settings saved successfully.")

    # ==========================================
    # TAB 2: AUTOMATION DASHBOARD
    # ==========================================
    def draw_automation_tab(self) -> None:
        # Controls panel (Start, Pause, Stop)
        controls = tk.Frame(self.tab_automation, bg=COLOR_CONTAINER, padx=15, pady=15)
        controls.pack(fill="x", padx=15, pady=10)

        self.btn_start = self.create_custom_button(controls, "▶ Start Bot", self.start_bot, bg=COLOR_SUCCESS)
        self.btn_start.pack(side="left", padx=10)

        self.btn_pause = self.create_custom_button(controls, "⏸ Pause", self.pause_bot, bg=COLOR_WARNING)
        self.btn_pause.pack(side="left", padx=10)

        self.btn_stop = self.create_custom_button(controls, "⏹ Stop Bot", self.stop_bot, bg=COLOR_DANGER)
        self.btn_stop.pack(side="left", padx=10)

        # Scrolled terminal logs
        log_frame = tk.Frame(self.tab_automation, bg=COLOR_BG)
        log_frame.pack(fill="both", expand=True, padx=15, pady=10)

        tk.Label(log_frame, text="Live Execution Logs:", bg=COLOR_BG, fg=COLOR_TEXT, font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=5)
        
        self.txt_logs = ScrolledText(
            log_frame, 
            bg=COLOR_INPUT_BG, 
            fg=COLOR_TEXT, 
            insertbackground=COLOR_TEXT,
            relief="flat", 
            bd=0,
            font=("Consolas", 9),
            padx=10,
            pady=10
        )
        self.txt_logs.pack(fill="both", expand=True)

    def log_message(self, message: str) -> None:
        """Appends log text to terminal screen safely."""
        self.txt_logs.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] {message}\n")
        self.txt_logs.see(tk.END)

    def poll_log_queue(self) -> None:
        """Reads items from background thread logger and outputs to terminal screen."""
        while not self.log_queue.empty():
            try:
                msg = self.log_queue.get_nowait()
                self.log_message(msg)
            except queue.Empty:
                break
        self.root.after(100, self.poll_log_queue)

    def update_status_from_thread(self, status: str, applied: int, skipped: int) -> None:
        """Callback to update GUI stats from automation threads safely."""
        self.applied_count = applied
        self.skipped_count = skipped
        self.root.after(0, lambda: self.lbl_status.config(
            text=f"Status: {status} | Applied: {applied} | Skipped: {skipped} | Session: {self.session_status}"
        ))

    def start_bot(self) -> None:
        if self.running:
            return
        
        # Load resume data
        resume_data = self.resume_parser.load_cached_resume()
        if not resume_data:
            messagebox.showerror("Missing Resume", "Please upload and parse your resume in the 'Resume' tab first.")
            return

        # Check API keys are loaded
        gemini_key = self.settings.get("gemini_api_key")
        if not gemini_key:
            messagebox.showerror("Config Error", "Gemini API key is required in Settings to start AI matching.")
            return

        self.running = True
        self.stop_event.clear()
        self.pause_event.clear()

        # Update button states
        self.btn_start.config(state="disabled")
        self.btn_pause.config(text="⏸ Pause")
        
        self.log_message("Starting Naukri Auto-Apply Engine...")

        # Worker Thread
        def thread_target():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            ai = AIEngine(
                gemini_key=self.settings.get("gemini_api_key"),
                groq_key=self.settings.get("groq_api_key"),
                gemini_model=self.settings.get("gemini_model"),
                groq_model=self.settings.get("groq_model")
            )
            
            bot = NaukriAutomation(
                settings=self.settings,
                ai_engine=ai,
                apply_logger=self.apply_logger,
                resume_data=resume_data,
                log_callback=lambda msg: self.log_queue.put(msg),
                status_callback=self.update_status_from_thread
            )

            try:
                loop.run_until_complete(bot.run(self.stop_event, self.pause_event))
            except Exception as e:
                self.log_queue.put(f"[Thread Crash] {e}")
            finally:
                loop.close()
                self.running = False
                self.root.after(0, self.reset_control_buttons)

        self.worker_thread = threading.Thread(target=thread_target, daemon=True)
        self.worker_thread.start()

    def pause_bot(self) -> None:
        if not self.running:
            return
        if self.pause_event.is_set():
            self.pause_event.clear()
            self.btn_pause.config(text="⏸ Pause", bg=COLOR_WARNING)
            self.log_message("Requesting Resume...")
        else:
            self.pause_event.set()
            self.btn_pause.config(text="▶ Resume", bg=COLOR_SUCCESS)
            self.log_message("Requesting Pause...")

    def stop_bot(self) -> None:
        if not self.running:
            return
        self.stop_event.set()
        self.log_message("Stopping automation loop gracefully...")

    def reset_control_buttons(self) -> None:
        """Restores dashboard buttons after execution ends."""
        self.btn_start.config(state="normal")
        self.btn_pause.config(text="⏸ Pause", bg=COLOR_WARNING)
        self.update_status_from_thread("Stopped", self.applied_count, self.skipped_count)

    # ==========================================
    # TAB 3: APPLY LOG TABLE
    # ==========================================
    def draw_logs_tab(self) -> None:
        container = tk.Frame(self.tab_logs, bg=COLOR_BG)
        container.pack(fill="both", expand=True, padx=15, pady=15)

        tk.Label(container, text="Logged Applications:", bg=COLOR_BG, fg=COLOR_TEXT, font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=5)

        # Table scrollbar
        scroll = ttk.Scrollbar(container, orient="vertical")
        scroll.pack(side="right", fill="y")

        # Treeview setup
        self.tree = ttk.Treeview(
            container, 
            columns=("date", "title", "company", "score", "status"), 
            show="headings", 
            yscrollcommand=scroll.set
        )
        scroll.config(command=self.tree.yview)

        # Column headings
        self.tree.heading("date", text="Date/Time")
        self.tree.heading("title", text="Job Title")
        self.tree.heading("company", text="Company")
        self.tree.heading("score", text="Score")
        self.tree.heading("status", text="Status")

        self.tree.column("date", width=120, anchor="center")
        self.tree.column("title", width=220, anchor="w")
        self.tree.column("company", width=180, anchor="w")
        self.tree.column("score", width=60, anchor="center")
        self.tree.column("status", width=90, anchor="center")

        self.tree.pack(fill="both", expand=True)

        # Treeview double click to show log reason dialog
        self.tree.bind("<Double-1>", self.show_log_details)

    def on_tab_changed(self, event) -> None:
        """Listens to notebook changes and updates tables/states."""
        active_tab = self.notebook.tab(self.notebook.select(), "text").strip()
        if active_tab == "Apply Log":
            self.load_apply_logs_into_table()

    def load_apply_logs_into_table(self) -> None:
        """Clears and re-populates applied logs from json."""
        # Clear existing logs
        for row in self.tree.get_children():
            self.tree.delete(row)

        logs = self.apply_logger.get_all_logs()
        # Sort logs by newest first
        logs.reverse()

        for entry in logs:
            ts = entry.get("timestamp", "")
            # Clean timestamp for display
            if ts:
                try:
                    ts = datetime.fromisoformat(ts).strftime("%m-%d %H:%M")
                except ValueError:
                    pass
            
            self.tree.insert(
                "", 
                "end", 
                values=(
                    ts,
                    entry.get("title", ""),
                    entry.get("company", ""),
                    entry.get("score", 0),
                    entry.get("status", "")
                ),
                tags=(entry.get("status", "").lower(),)
            )

        # Status row tag highlighting
        self.tree.tag_configure("applied", foreground=COLOR_SUCCESS)
        self.tree.tag_configure("failed", foreground=COLOR_DANGER)
        self.tree.tag_configure("skipped", foreground=COLOR_WARNING)

    def show_log_details(self, event) -> None:
        """Shows compatibility justification popup on double click."""
        selected_item = self.tree.focus()
        if not selected_item:
            return
            
        values = self.tree.item(selected_item, "values")
        if not values:
            return
            
        # Re-fetch from log file using title + company key
        logs = self.apply_logger.get_all_logs()
        matching_entry = None
        for entry in logs:
            if entry.get("title") == values[1] and entry.get("company") == values[2]:
                matching_entry = entry
                break
                
        if matching_entry:
            reason = matching_entry.get("reason", "No reason provided.")
            messagebox.showinfo(
                "Match Analysis Details", 
                f"Job: {matching_entry.get('title')} at {matching_entry.get('company')}\n\n"
                f"Compatibility Score: {matching_entry.get('score')}/100\n"
                f"AI Justification:\n{reason}"
            )

    # ==========================================
    # TAB 4: RESUME PARSING
    # ==========================================
    def draw_resume_tab(self) -> None:
        container = tk.Frame(self.tab_resume, bg=COLOR_BG, padx=20, pady=20)
        container.pack(fill="both", expand=True)

        header_frame = tk.Frame(container, bg=COLOR_BG)
        header_frame.pack(fill="x", pady=10)

        # Upload Button
        btn_upload = self.create_custom_button(header_frame, "📁 Select Resume (PDF/DOCX)", self.select_and_parse_resume)
        btn_upload.pack(side="left")

        self.lbl_resume_path = tk.Label(
            header_frame, 
            text="No file selected.", 
            bg=COLOR_BG, 
            fg=COLOR_ACCENT_HOVER, 
            font=("Segoe UI", 9, "italic")
        )
        self.lbl_resume_path.pack(side="left", padx=15)
        
        # Display saved path if any
        saved_path = self.settings.get("resume_path", "")
        if saved_path:
            self.lbl_resume_path.config(text=os.path.basename(saved_path))

        # JSON Preview Panel
        preview_frame = tk.Frame(container, bg=COLOR_BG)
        preview_frame.pack(fill="both", expand=True, pady=10)

        tk.Label(preview_frame, text="Structured Resume Data JSON Preview:", bg=COLOR_BG, fg=COLOR_TEXT, font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=5)

        self.txt_resume_preview = ScrolledText(
            preview_frame, 
            bg=COLOR_INPUT_BG, 
            fg=COLOR_TEXT, 
            insertbackground=COLOR_TEXT,
            relief="flat", 
            bd=0,
            font=("Consolas", 9)
        )
        self.txt_resume_preview.pack(fill="both", expand=True)

        # Load cached resume preview if present
        cached_data = self.resume_parser.load_cached_resume()
        if cached_data:
            self.txt_resume_preview.insert(tk.END, json.dumps(cached_data, indent=2))

    def select_and_parse_resume(self) -> None:
        """Opens file selection dialog and runs parser in background thread."""
        file_path = filedialog.askopenfilename(
            title="Select Resume Document",
            filetypes=[("Resume Documents", "*.pdf *.docx *.txt"), ("All Files", "*.*")]
        )
        
        if not file_path:
            return

        gemini_key = self.settings.get("gemini_api_key")
        if not gemini_key:
            messagebox.showerror("API Configuration Error", "Please configure and save your Gemini API Key in the Settings tab before parsing the resume.")
            return

        self.lbl_resume_path.config(text=f"Parsing: {os.path.basename(file_path)}...")
        self.txt_resume_preview.delete("1.0", tk.END)
        self.txt_resume_preview.insert(tk.END, "Extracting text and structure via AI model... Please wait.")

        # Parse in thread
        def parse_thread():
            try:
                ai = AIEngine(
                    gemini_key=self.settings.get("gemini_api_key"),
                    groq_key=self.settings.get("groq_api_key"),
                    gemini_model=self.settings.get("gemini_model"),
                    groq_model=self.settings.get("groq_model")
                )
                
                # Async-to-sync runner wrapper
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                parsed_data = loop.run_until_complete(self.resume_parser.parse_resume(file_path, ai))
                
                # Dynamically suggest roles based on parsed resume
                suggested_roles = ""
                try:
                    suggested_roles = loop.run_until_complete(ai.suggest_target_roles(parsed_data))
                except Exception as ex:
                    print(f"[ModernBotApp] AI target roles suggestion failed: {ex}")
                loop.close()

                # Update settings with resume path and suggested roles
                self.settings.set("resume_path", file_path)
                if suggested_roles:
                    self.settings.set("target_roles", suggested_roles)

                # Update UI
                self.root.after(0, lambda: self.on_parse_success(file_path, parsed_data, suggested_roles))
            except Exception as e:
                self.root.after(0, lambda: self.on_parse_failure(e))

        threading.Thread(target=parse_thread, daemon=True).start()

    def on_parse_success(self, file_path: str, parsed_data: dict, suggested_roles: str = "") -> None:
        """Saves path details and prints structured JSON to preview window."""
        self.lbl_resume_path.config(text=os.path.basename(file_path))
        self.txt_resume_preview.delete("1.0", tk.END)
        self.txt_resume_preview.insert(tk.END, json.dumps(parsed_data, indent=2))
        if suggested_roles:
            self.update_roles_ui(suggested_roles)
        messagebox.showinfo("Parsing Complete", "Resume text successfully structured, cached, and targeted roles updated by AI.")

    def on_parse_failure(self, error: Exception) -> None:
        """Handles parsing exceptions gracefully."""
        self.lbl_resume_path.config(text="Parsing Failed.")
        self.txt_resume_preview.delete("1.0", tk.END)
        self.txt_resume_preview.insert(tk.END, f"Error occurred during parsing:\n{error}")
        messagebox.showerror("Parsing Failure", f"An error occurred while parsing the resume: {error}")

    def suggest_roles_on_launch(self) -> None:
        """
        Dynamically suggests target role keywords at launch based on cached resume.
        """
        cached_data = self.resume_parser.load_cached_resume()
        if not cached_data:
            return

        gemini_key = self.settings.get("gemini_api_key")
        if not gemini_key:
            return

        def suggest_thread():
            try:
                ai = AIEngine(
                    gemini_key=self.settings.get("gemini_api_key"),
                    groq_key=self.settings.get("groq_api_key"),
                    gemini_model=self.settings.get("gemini_model"),
                    groq_model=self.settings.get("groq_model")
                )
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                suggested_roles = loop.run_until_complete(ai.suggest_target_roles(cached_data))
                loop.close()

                if suggested_roles:
                    self.settings.set("target_roles", suggested_roles)
                    self.root.after(0, lambda: self.update_roles_ui(suggested_roles))
            except Exception as e:
                print(f"[ModernBotApp] Failed to dynamically generate roles on launch: {e}")

        threading.Thread(target=suggest_thread, daemon=True).start()

    def update_roles_ui(self, suggested_roles: str) -> None:
        """Helper to update UI text entry field for roles."""
        if hasattr(self, 'ent_roles') and self.ent_roles:
            self.ent_roles.delete(0, tk.END)
            self.ent_roles.insert(0, suggested_roles)

def main() -> None:
    root = tk.Tk()
    app = ModernBotApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
