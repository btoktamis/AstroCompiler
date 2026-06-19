import os
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime, timezone

from spaceweather.engine import SpaceWeatherCompiler, ap_sum_to_cp, cp_to_c9
from spaceweather.eop_engine import EOPCompiler

# Import matplotlib if available, otherwise use Tkinter Canvas fallback
try:
    import matplotlib
    matplotlib.use("TkAgg")
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

# Import pandas if available, otherwise parse lines manually
try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False


class SpaceWeatherGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Antigravity Space Weather Compiler & Analyzer")
        self.root.geometry("1000x700")
        self.root.minsize(800, 600)
        
        # Color Palette - Modern Dark Theme
        self.colors = {
            "bg": "#181825",          # Main window bg
            "card": "#1e1e2e",        # Panel bg
            "border": "#313244",      # Borders
            "text": "#cdd6f4",        # Main text
            "text_sub": "#a6adc8",    # Secondary text
            "accent": "#89b4fa",      # Accent blue
            "accent_hover": "#b4befe",# Active hover
            "success": "#a6e3a1",     # Green
            "error": "#f38ba8",       # Red
            "warning": "#f9e2af"      # Yellow
        }
        
        self.compiler = None
        self.compiled_data = None
        self.current_output_path = "SW-All.txt"
        
        self.configure_styles()
        self.build_ui()
        
    def configure_styles(self):
        self.root.configure(bg=self.colors["bg"])
        
        style = ttk.Style()
        style.theme_use("clam")
        
        # Style notebook (tabs)
        style.configure("TNotebook", background=self.colors["bg"], borderwidth=0)
        style.configure("TNotebook.Tab", 
                        background=self.colors["card"], 
                        foreground=self.colors["text_sub"], 
                        padding=[15, 6], 
                        font=("Segoe UI", 10, "bold"),
                        borderwidth=1,
                        bordercolor=self.colors["border"])
        style.map("TNotebook.Tab", 
                  background=[("selected", self.colors["bg"])], 
                  foreground=[("selected", self.colors["accent"])])
        
        # Frame styles
        style.configure("TFrame", background=self.colors["bg"])
        style.configure("Card.TFrame", background=self.colors["card"], borderwidth=1, relief="flat")
        
        # Label styles
        style.configure("TLabel", background=self.colors["bg"], foreground=self.colors["text"], font=("Segoe UI", 10))
        style.configure("Card.TLabel", background=self.colors["card"], foreground=self.colors["text"], font=("Segoe UI", 10))
        style.configure("Title.TLabel", background=self.colors["card"], foreground=self.colors["accent"], font=("Segoe UI", 14, "bold"))
        style.configure("Sub.TLabel", background=self.colors["card"], foreground=self.colors["text_sub"], font=("Segoe UI", 9, "italic"))
        style.configure("Status.TLabel", background=self.colors["card"], foreground=self.colors["text_sub"], font=("Segoe UI", 10))
        
        # Button styles
        style.configure("TButton", 
                        background=self.colors["border"], 
                        foreground=self.colors["text"], 
                        borderwidth=0, 
                        font=("Segoe UI", 10, "bold"),
                        padding=[12, 6])
        style.map("TButton", 
                  background=[("active", self.colors["accent"]), ("pressed", self.colors["accent_hover"])],
                  foreground=[("active", "#11111b")])
                  
        style.configure("Accent.TButton", 
                        background=self.colors["accent"], 
                        foreground="#11111b", 
                        borderwidth=0, 
                        font=("Segoe UI", 10, "bold"),
                        padding=[15, 8])
        style.map("Accent.TButton", 
                  background=[("active", self.colors["accent_hover"])])
        
        # Entry and Combobox styles
        style.configure("TEntry", fieldbackground=self.colors["bg"], foreground=self.colors["text"], borderwidth=1)
        style.configure("TCombobox", fieldbackground=self.colors["bg"], foreground=self.colors["text"], selectbackground=self.colors["accent"])
        
        # Treeview (table) styles
        style.configure("Treeview", 
                        background=self.colors["card"], 
                        fieldbackground=self.colors["card"], 
                        foreground=self.colors["text"],
                        rowheight=25,
                        font=("Segoe UI", 9))
        style.configure("Treeview.Heading", 
                        background=self.colors["border"], 
                        foreground=self.colors["accent"], 
                        font=("Segoe UI", 9, "bold"),
                        borderwidth=1)
        style.map("Treeview", 
                  background=[("selected", self.colors["accent"])], 
                  foreground=[("selected", "#11111b")])

    def build_ui(self):
        # Header banner
        header = tk.Frame(self.root, bg=self.colors["card"], height=60)
        header.pack(fill="x", side="top")
        
        lbl_title = tk.Label(header, text="OFFLINE SPACE WEATHER DASHBOARD & COMPILER", 
                             fg=self.colors["accent"], bg=self.colors["card"], 
                             font=("Segoe UI", 14, "bold"))
        lbl_title.pack(side="left", padx=20, pady=15)
        
        # Notebook for Tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Compile Tab
        self.tab_compile = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_compile, text="COMPILER")
        self.build_compile_tab()
        
        # Data Viewer Tab
        self.tab_viewer = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_viewer, text="DATA VIEWER")
        self.build_viewer_tab()
        
        # Visualization Tab
        self.tab_vis = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_vis, text="VISUALIZATION")
        self.build_vis_tab()
        
        # EOP Compiler Tab
        self.tab_eop = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_eop, text="EOP COMPILER")
        self.build_eop_tab()

    def build_compile_tab(self):
        # Left Panel (Settings)
        left_frame = ttk.Frame(self.tab_compile, style="Card.TFrame")
        left_frame.pack(side="left", fill="both", expand=False, padx=(5, 10), pady=5)
        left_frame.configure(width=300)
        left_frame.pack_propagate(False)
        
        lbl_cfg = ttk.Label(left_frame, text="COMPILER CONFIGURATION", style="Title.TLabel")
        lbl_cfg.pack(anchor="w", padx=15, pady=(15, 5))
        
        lbl_desc = ttk.Label(left_frame, 
                             text="Fetch raw datasets directly from GFZ Potsdam, SILSO Brussels, Penticton Canada, NOAA SWPC, and NASA, and build SW-All.txt format offline.", 
                             style="Sub.TLabel", wraplength=270)
        lbl_desc.pack(anchor="w", padx=15, pady=(0, 20))
        
        # Output Path Config
        lbl_path = ttk.Label(left_frame, text="Output File Path:", style="Card.TLabel")
        lbl_path.pack(anchor="w", padx=15, pady=2)
        
        path_frame = ttk.Frame(left_frame, style="Card.TFrame")
        path_frame.pack(fill="x", padx=15, pady=(0, 10))
        
        self.ent_path = ttk.Entry(path_frame)
        self.ent_path.insert(0, self.current_output_path)
        self.ent_path.pack(side="left", fill="x", expand=True, ipady=3)
        
        btn_browse = ttk.Button(path_frame, text="...", width=3, command=self.browse_output_path)
        btn_browse.pack(side="right", padx=(5, 0))
        
        # Output Format
        lbl_format = ttk.Label(left_frame, text="Output Format:", style="Card.TLabel")
        lbl_format.pack(anchor="w", padx=15, pady=2)
        self.cb_format = ttk.Combobox(left_frame, values=["Legacy Text (SW-All.txt)", "CSV Table"], state="readonly")
        self.cb_format.current(0)
        self.cb_format.pack(fill="x", padx=15, pady=(0, 15))
        self.cb_format.bind("<<ComboboxSelected>>", self.on_format_changed)
        
        # Cache Directory
        lbl_cache = ttk.Label(left_frame, text="Cache Directory:", style="Card.TLabel")
        lbl_cache.pack(anchor="w", padx=15, pady=2)
        self.ent_cache = ttk.Entry(left_frame)
        self.ent_cache.insert(0, "./cache")
        self.ent_cache.pack(fill="x", padx=15, pady=(0, 25))
        
        # Action Buttons
        self.btn_compile = ttk.Button(left_frame, text="Download & Compile", style="Accent.TButton", command=self.start_compilation)
        self.btn_compile.pack(fill="x", padx=15, pady=5)
        
        self.btn_verify = ttk.Button(left_frame, text="Verify CelesTrak Compatibility", command=self.start_verification)
        self.btn_verify.pack(fill="x", padx=15, pady=5)
        
        # Progress status
        self.lbl_status = ttk.Label(left_frame, text="Status: Ready", style="Status.TLabel")
        self.lbl_status.pack(anchor="w", padx=15, pady=(20, 2))
        
        self.progress = ttk.Progressbar(left_frame, mode="indeterminate")
        self.progress.pack(fill="x", padx=15, pady=5)
        
        # Right Panel (Console Logs)
        right_frame = ttk.Frame(self.tab_compile, style="Card.TFrame")
        right_frame.pack(side="right", fill="both", expand=True, padx=5, pady=5)
        
        lbl_log = ttk.Label(right_frame, text="COMPILER LOGS & OUTPUT", style="Title.TLabel")
        lbl_log.pack(anchor="w", padx=15, pady=15)
        
        # Console output text box
        self.txt_log = tk.Text(right_frame, bg=self.colors["bg"], fg=self.colors["text"], 
                              insertbackground=self.colors["text"], font=("Consolas", 9), 
                              borderwidth=1, relief="flat")
        self.txt_log.pack(fill="both", expand=True, padx=15, pady=(0, 15))
        
        # Append initial instructions
        self.append_log("System initialized. Click 'Download & Compile' to begin.\n")

    def build_viewer_tab(self):
        # Top Panel (Search and Filters)
        top_frame = ttk.Frame(self.tab_viewer, style="Card.TFrame")
        top_frame.pack(side="top", fill="x", padx=5, pady=5)
        
        lbl_filter = ttk.Label(top_frame, text="SEARCH & FILTER DATABASE", style="Title.TLabel")
        lbl_filter.grid(row=0, column=0, columnspan=4, sticky="w", padx=15, pady=(15, 10))
        
        # Date Filter
        ttk.Label(top_frame, text="Start Date (YYYY-MM-DD):", style="Card.TLabel").grid(row=1, column=0, padx=(15, 5), pady=5, sticky="e")
        self.ent_start_date = ttk.Entry(top_frame, width=15)
        self.ent_start_date.insert(0, "2000-01-01")
        self.ent_start_date.grid(row=1, column=1, padx=5, pady=5, sticky="w")
        
        ttk.Label(top_frame, text="End Date (YYYY-MM-DD):", style="Card.TLabel").grid(row=1, column=2, padx=15, pady=5, sticky="e")
        self.ent_end_date = ttk.Entry(top_frame, width=15)
        self.ent_end_date.insert(0, "2026-06-30")
        self.ent_end_date.grid(row=1, column=3, padx=5, pady=5, sticky="w")
        
        # Kp filter
        ttk.Label(top_frame, text="Min Kp (x10, e.g. 50=5o):", style="Card.TLabel").grid(row=1, column=4, padx=15, pady=5, sticky="e")
        self.ent_min_kp = ttk.Entry(top_frame, width=8)
        self.ent_min_kp.grid(row=1, column=5, padx=5, pady=5, sticky="w")
        
        btn_apply = ttk.Button(top_frame, text="Apply Filters", command=self.apply_grid_filters)
        btn_apply.grid(row=1, column=6, padx=15, pady=5)
        
        btn_load = ttk.Button(top_frame, text="Load Generated File", command=self.load_file_to_viewer)
        btn_load.grid(row=1, column=7, padx=5, pady=5)
        
        # Grid/Table Panel
        grid_frame = ttk.Frame(self.tab_viewer, style="Card.TFrame")
        grid_frame.pack(side="bottom", fill="both", expand=True, padx=5, pady=5)
        
        # Table Scrollbar
        scroll_y = ttk.Scrollbar(grid_frame, orient="vertical")
        scroll_x = ttk.Scrollbar(grid_frame, orient="horizontal")
        
        # Treeview definition
        cols = ["DATE", "BSRN", "ND", "KP_SUM", "AP_AVG", "CP", "C9", "ISN", "F10.7_OBS", "F10.7_ADJ", "DATA_TYPE"]
        self.tree = ttk.Treeview(grid_frame, columns=cols, show="headings", 
                                 yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        
        scroll_y.config(command=self.tree.yview)
        scroll_x.config(command=self.tree.xview)
        
        scroll_y.pack(side="right", fill="y")
        scroll_x.pack(side="bottom", fill="x")
        self.tree.pack(fill="both", expand=True)
        
        for col in cols:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=80, anchor="center")
        self.tree.column("DATE", width=120)
        self.tree.column("DATA_TYPE", width=100)

    def build_vis_tab(self):
        # Controls Frame
        ctrl_frame = ttk.Frame(self.tab_vis, style="Card.TFrame")
        ctrl_frame.pack(side="top", fill="x", padx=5, pady=5)
        
        lbl_vis = ttk.Label(ctrl_frame, text="SPACE WEATHER TREND VISUALIZATION", style="Title.TLabel")
        lbl_vis.grid(row=0, column=0, columnspan=4, sticky="w", padx=15, pady=(15, 10))
        
        ttk.Label(ctrl_frame, text="Plot Param:", style="Card.TLabel").grid(row=1, column=0, padx=(15, 5), pady=5, sticky="e")
        self.cb_param = ttk.Combobox(ctrl_frame, values=["Solar Flux F10.7 (Observed vs Adjusted)", "Geomagnetic Index Ap (Daily Average)"], state="readonly", width=40)
        self.cb_param.current(0)
        self.cb_param.grid(row=1, column=1, padx=5, pady=5, sticky="w")
        self.cb_param.bind("<<ComboboxSelected>>", lambda e: self.update_chart())
        
        # Plot Frame
        self.plot_frame = ttk.Frame(self.tab_vis, style="Card.TFrame")
        self.plot_frame.pack(side="bottom", fill="both", expand=True, padx=5, pady=5)
        
        # Initial chart placeholder
        self.chart_canvas = None
        
        # Info label inside plot frame
        self.lbl_no_plot = ttk.Label(self.plot_frame, text="No compiled data loaded. Run the Compiler first.", style="Card.TLabel")
        self.lbl_no_plot.pack(expand=True)

    def browse_output_path(self):
        ext = ".txt" if self.cb_format.current() == 0 else ".csv"
        filename = filedialog.asksaveasfilename(
            defaultextension=ext,
            filetypes=[("Legacy Text", "*.txt"), ("CSV Table", "*.csv")]
        )
        if filename:
            self.current_output_path = filename
            self.ent_path.delete(0, tk.END)
            self.ent_path.insert(0, filename)

    def on_format_changed(self, event):
        path = self.ent_path.get()
        base, _ = os.path.splitext(path)
        if self.cb_format.current() == 0:
            new_path = base + ".txt"
        else:
            new_path = base + ".csv"
        self.ent_path.delete(0, tk.END)
        self.ent_path.insert(0, new_path)
        self.current_output_path = new_path

    def append_log(self, text):
        self.txt_log.insert(tk.END, text)
        self.txt_log.see(tk.END)

    def start_compilation(self):
        self.btn_compile.config(state="disabled")
        self.btn_verify.config(state="disabled")
        self.lbl_status.config(text="Status: Compiling...")
        self.progress.start(10)
        self.txt_log.delete("1.0", tk.END)
        self.append_log("Starting Offline Compilation Process...\n")
        
        # Retrieve values
        output_path = self.ent_path.get()
        cache_dir = self.ent_cache.get()
        fmt_idx = self.cb_format.current()
        
        # Execute in thread to keep UI alive
        t = threading.Thread(
            target=self.thread_compile,
            args=(output_path, cache_dir, fmt_idx)
        )
        t.daemon = True
        t.start()

    def thread_compile(self, output_path, cache_dir, fmt_idx):
        try:
            compiler = SpaceWeatherCompiler(
                cache_dir=cache_dir,
                log_callback=lambda msg: self.root.after(0, self.append_log, msg + "\n")
            )
            self.compiler = compiler
            
            data = compiler.compile()
            self.compiled_data = data
            
            # Write file
            if fmt_idx == 0:
                compiler.write_to_legacy_txt(data, output_path)
            else:
                compiler.write_to_csv(data, output_path)
                
            self.root.after(0, self.on_compilation_success, output_path)
        except Exception as e:
            self.root.after(0, self.on_compilation_error, str(e))

    def on_compilation_success(self, filepath):
        self.lbl_status.config(text="Status: Compilation Success!")
        self.progress.stop()
        self.btn_compile.config(state="normal")
        self.btn_verify.config(state="normal")
        self.append_log(f"\nCompilation finished successfully! Saved to: {filepath}\n")
        
        # Populate table and visualization automatically
        self.populate_data_grid(self.compiled_data)
        self.update_chart()
        
        messagebox.showinfo("Success", f"Space Weather database successfully compiled and written to:\n{filepath}")

    def on_compilation_error(self, err_msg):
        self.lbl_status.config(text="Status: Compilation Failed")
        self.progress.stop()
        self.btn_compile.config(state="normal")
        self.btn_verify.config(state="normal")
        self.append_log(f"\nError: {err_msg}\n")
        messagebox.showerror("Compilation Error", f"An error occurred during compilation:\n{err_msg}")

    def start_verification(self):
        self.btn_compile.config(state="disabled")
        self.btn_verify.config(state="disabled")
        self.lbl_status.config(text="Status: Verifying compatibility...")
        self.progress.start(10)
        self.txt_log.delete("1.0", tk.END)
        self.append_log("Starting side-by-side verification with live CelesTrak database...\n")
        
        cache_dir = self.ent_cache.get()
        
        t = threading.Thread(target=self.thread_verify, args=(cache_dir,))
        t.daemon = True
        t.start()

    def thread_verify(self, cache_dir):
        try:
            if not self.compiler or not self.compiled_data:
                # Need to compile first
                compiler = SpaceWeatherCompiler(
                    cache_dir=cache_dir,
                    log_callback=lambda msg: self.root.after(0, self.append_log, msg + "\n")
                )
                self.compiler = compiler
                data = compiler.compile()
                self.compiled_data = data
            else:
                compiler = self.compiler
                data = self.compiled_data
                
            temp_output = os.path.join(cache_dir, "temp_verify.txt")
            compiler.write_to_legacy_txt(data, temp_output)
            
            report = compiler.verify_with_celestrak(temp_output)
            
            if os.path.exists(temp_output):
                os.remove(temp_output)
                
            self.root.after(0, self.on_verification_finished, report)
        except Exception as e:
            self.root.after(0, self.on_compilation_error, str(e))

    def on_verification_finished(self, report):
        self.lbl_status.config(text="Status: Verification Finished")
        self.progress.stop()
        self.btn_compile.config(state="normal")
        self.btn_verify.config(state="normal")
        
        matches = report["obs_match_rate"]
        pred_matches = report["pred_match_rate"]
        discrepancies = len(report["discrepancies"])
        
        self.append_log(f"\n--- Live Verification Report Completed ---\n")
        self.append_log(f"Observed compatibility rate: {matches * 100:.2f}%\n")
        self.append_log(f"Predictions compatibility rate: {pred_matches * 100:.2f}%\n")
        self.append_log(f"Total discrepancies: {discrepancies}\n")
        
        if matches >= 0.98:
            messagebox.showinfo(
                "Verification Passed",
                f"Compatibility Check PASSED!\n\n"
                f"Your offline compiler matches CelesTrak output at:\n"
                f"Observed: {matches * 100:.2f}%\n"
                f"Predicted: {pred_matches * 100:.2f}%\n"
                f"Discrepancies: {discrepancies}"
            )
        else:
            messagebox.showwarning(
                "Verification Discrepancy",
                f"Compatibility Check finished with discrepancies.\n\n"
                f"Match Rate: {matches * 100:.2f}%\n"
                f"See logs for list of specific date variations."
            )

    def populate_data_grid(self, compiled_dict):
        # Clear existing rows
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        if not compiled_dict:
            return
            
        # Merge all lists for display
        all_rows = []
        for r in compiled_dict["observed"]:
            all_rows.append(self.format_row_for_grid(r, "OBSERVED"))
        for r in compiled_dict["daily"]:
            all_rows.append(self.format_row_for_grid(r, "DAILY_PREDICTED"))
        for r in compiled_dict["monthly"]:
            all_rows.append(self.format_row_for_grid(r, "MONTHLY_PREDICTED"))
            
        # Store for filtering
        self.grid_rows = all_rows
        
        # Load first 200 items by default (to avoid freezing Tkinter Treeview on huge dataset)
        self.render_grid_rows(self.grid_rows[:1000])

    def format_row_for_grid(self, r, dtype):
        # Calculate summary parameters
        if dtype == "MONTHLY_PREDICTED":
            kp_sum = ""
            ap_avg = ""
            cp = ""
            c9 = ""
        else:
            kp_sum = sum(r["kp_vals"]) if min(r["kp_vals"]) >= 0 else ""
            ap_avg = r["ap_avg"]
            cp_val = ap_sum_to_cp(sum(r["ap_vals"]))
            cp = f"{cp_val:.1f}"
            c9 = str(cp_to_c9(cp_val))
            
        return (
            r["date"],
            str(r["bsrn"]),
            str(r["nd"]),
            str(kp_sum),
            str(ap_avg),
            cp,
            c9,
            str(r["isn"]),
            f"{r['f107_obs']:.1f}",
            f"{r['f107_adj']:.1f}",
            dtype
        )

    def render_grid_rows(self, rows):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for row in rows:
            self.tree.insert("", "end", values=row)

    def apply_grid_filters(self):
        if not hasattr(self, "grid_rows"):
            messagebox.showwarning("No Data", "Please compile or load data first.")
            return
            
        start_date = self.ent_start_date.get().strip()
        end_date = self.ent_end_date.get().strip()
        min_kp_str = self.ent_min_kp.get().strip()
        
        filtered = self.grid_rows
        
        # Filter dates
        if start_date:
            filtered = [r for r in filtered if r[0] >= start_date]
        if end_date:
            filtered = [r for r in filtered if r[0] <= end_date]
            
        # Filter min Kp
        if min_kp_str:
            try:
                min_kp = int(min_kp_str)
                # Kp_sum is index 3
                filtered = [r for r in filtered if r[3] and int(r[3]) >= min_kp]
            except ValueError:
                pass
                
        self.render_grid_rows(filtered[:1000])
        self.lbl_status.config(text=f"Filtered: showing {min(len(filtered), 1000)} of {len(filtered)} rows")

    def load_file_to_viewer(self):
        filename = filedialog.askopenfilename(
            filetypes=[("Space Weather TXT/CSV", "*.txt *.csv")]
        )
        if not filename:
            return
            
        try:
            # Simple parse
            _, ext = os.path.splitext(filename)
            compiled_dict = {"observed": [], "daily": [], "monthly": []}
            
            with open(filename, "r", encoding="utf-8") as f:
                content = f.read()
                
            if ext.lower() == ".csv":
                # Parse CSV
                lines = content.splitlines()
                if not lines:
                    return
                # Headers: DATE:0, BSRN:1, ND:2, KP1..KP8:3..10, KP_SUM:11, AP1..AP8:12..19, AP_AVG:20, CP:21, C9:22, ISN:23, F10.7_OBS:24, F10.7_ADJ:25, TYPE:26
                for line in lines[1:]:
                    parts = line.split(",")
                    if len(parts) < 27:
                        continue
                    dtype = parts[26].strip()
                    r = {
                        "date": parts[0],
                        "year": int(parts[0][:4]),
                        "month": int(parts[0][5:7]),
                        "day": int(parts[0][8:10]),
                        "bsrn": int(parts[1]),
                        "nd": int(parts[2]),
                        "isn": int(parts[23]) if parts[23] else 0,
                        "f107_obs": float(parts[24]) if parts[24] else 0.0,
                        "f107_adj": float(parts[25]) if parts[25] else 0.0,
                    }
                    if dtype == "OBS":
                        r["kp_vals"] = [int(x) if x else -1 for x in parts[3:11]]
                        r["ap_vals"] = [int(x) if x else -1 for x in parts[12:20]]
                        r["ap_avg"] = int(parts[20]) if parts[20] else 0
                        compiled_dict["observed"].append(r)
                    elif dtype == "PRD":
                        r["kp_vals"] = [int(x) if x else -1 for x in parts[3:11]]
                        r["ap_vals"] = [int(x) if x else -1 for x in parts[12:20]]
                        r["ap_avg"] = int(parts[20]) if parts[20] else 0
                        compiled_dict["daily"].append(r)
                    elif dtype == "PRM":
                        compiled_dict["monthly"].append(r)
            else:
                # Parse legacy text format
                current_section = None
                for line in content.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    if line == "BEGIN OBSERVED":
                        current_section = "OBS"
                        continue
                    elif line == "END OBSERVED":
                        current_section = None
                        continue
                    elif line == "BEGIN DAILY_PREDICTED":
                        current_section = "DAILY"
                        continue
                    elif line == "END DAILY_PREDICTED":
                        current_section = None
                        continue
                    elif line == "BEGIN MONTHLY_PREDICTED":
                        current_section = "MONTHLY"
                        continue
                    elif line == "END MONTHLY_PREDICTED":
                        current_section = None
                        continue
                        
                    if current_section:
                        parts = line.split()
                        if len(parts) >= 5:
                            r = {
                                "date": f"{parts[0]}-{parts[1]}-{parts[2]}",
                                "year": int(parts[0]),
                                "month": int(parts[1]),
                                "day": int(parts[2]),
                                "bsrn": int(parts[3]),
                                "nd": int(parts[4]),
                            }
                            # Parse rest based on sections
                            if current_section == "OBS" or current_section == "DAILY":
                                # Kp values are at fixed widths
                                kp_str = line[18:42]
                                r["kp_vals"] = [int(kp_str[i:i+3].strip()) if kp_str[i:i+3].strip() else -1 for i in range(0, 24, 3)]
                                ap_str = line[46:78]
                                r["ap_vals"] = [int(ap_str[i:i+4].strip()) for i in range(0, 32, 4)]
                                r["ap_avg"] = int(line[78:82].strip())
                                r["isn"] = int(line[88:92].strip())
                                r["f107_adj"] = float(line[92:98].strip())
                                r["f107_obs"] = float(line[112:118].strip())
                                if current_section == "OBS":
                                    compiled_dict["observed"].append(r)
                                else:
                                    compiled_dict["daily"].append(r)
                            elif current_section == "MONTHLY":
                                r["isn"] = int(line[88:92].strip())
                                r["f107_adj"] = float(line[92:98].strip())
                                r["f107_obs"] = float(line[112:118].strip())
                                compiled_dict["monthly"].append(r)

            self.compiled_data = compiled_dict
            self.populate_data_grid(self.compiled_data)
            self.update_chart()
            messagebox.showinfo("File Loaded", f"Loaded successfully: {len(self.grid_rows)} entries found.")
        except Exception as e:
            messagebox.showerror("Load Error", f"Could not load data file: {e}")

    def update_chart(self):
        if not self.compiled_data:
            return
            
        # Clear previous plot
        if self.chart_canvas:
            self.chart_canvas.get_tk_widget().destroy()
            self.chart_canvas = None
            
        self.lbl_no_plot.pack_forget()
        
        # Prepare recent Observed + Daily Predicted timeline for plotting
        # Let's take the last 30 days of Observed data and all 45 days of predictions
        obs_recs = self.compiled_data["observed"][-30:]
        daily_recs = self.compiled_data["daily"]
        plot_data = obs_recs + daily_recs
        
        dates = [datetime.strptime(r["date"], "%Y-%m-%d") for r in plot_data]
        obs_f107 = [r["f107_obs"] for r in plot_data]
        adj_f107 = [r["f107_adj"] for r in plot_data]
        ap_avgs = [r["ap_avg"] for r in plot_data]
        
        param_idx = self.cb_param.current()
        
        if HAS_MATPLOTLIB:
            # Plot using Matplotlib
            fig = Figure(figsize=(8, 4.5), dpi=100, facecolor=self.colors["card"])
            ax = fig.add_subplot(111)
            ax.set_facecolor(self.colors["bg"])
            
            # Format axes colors
            ax.spines['bottom'].set_color(self.colors['border'])
            ax.spines['top'].set_color(self.colors['border'])
            ax.spines['right'].set_color(self.colors['border'])
            ax.spines['left'].set_color(self.colors['border'])
            ax.tick_params(colors=self.colors['text'], labelsize=8)
            ax.grid(True, color=self.colors['border'], linestyle="--", alpha=0.5)
            
            # Divide into Observed and Predicted segments for visual distinction
            split_idx = len(obs_recs)
            
            if param_idx == 0:
                # Solar Flux F10.7
                ax.plot(dates[:split_idx], obs_f107[:split_idx], label="Observed Flux (Measured)", color=self.colors["accent"], linewidth=2)
                ax.plot(dates[split_idx-1:], obs_f107[split_idx-1:], label="Predicted Flux", color=self.colors["accent"], linestyle="--", linewidth=1.5)
                ax.plot(dates[:split_idx], adj_f107[:split_idx], label="Adjusted Flux (1 AU)", color=self.colors["success"], linewidth=1.5, alpha=0.8)
                ax.plot(dates[split_idx-1:], adj_f107[split_idx-1:], color=self.colors["success"], linestyle="--", linewidth=1.2, alpha=0.8)
                ax.set_ylabel("Solar Radio Flux F10.7 (sfu)", color=self.colors["text"], fontsize=9)
            else:
                # Geomagnetic Index Ap
                ax.bar(dates[:split_idx], ap_avgs[:split_idx], label="Observed Ap (Daily Avg)", color=self.colors["accent"], width=0.8)
                ax.bar(dates[split_idx:], ap_avgs[split_idx:], label="Predicted Ap (Daily Avg)", color=self.colors["warning"], width=0.8, alpha=0.6)
                ax.set_ylabel("Planetary Equivalent Amplitude Ap (nT)", color=self.colors["text"], fontsize=9)
                
            ax.axvline(x=dates[split_idx-1], color=self.colors["error"], linestyle="-.", linewidth=1, label="Forecast Horizon")
            
            ax.set_title(self.cb_param.get(), color=self.colors["accent"], fontsize=11, fontweight="bold")
            ax.legend(facecolor=self.colors["card"], edgecolor=self.colors["border"], labelcolor=self.colors["text"], fontsize=8)
            fig.autofmt_xdate()
            
            self.chart_canvas = FigureCanvasTkAgg(fig, master=self.plot_frame)
            self.chart_canvas.draw()
            self.chart_canvas.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=10)
        else:
            # Fallback to standard Tkinter Canvas drawing
            self.lbl_no_plot.pack_forget()
            canvas = tk.Canvas(self.plot_frame, bg=self.colors["bg"], highlightthickness=0)
            canvas.pack(fill="both", expand=True)
            
            # Simple line graph drawing
            width = 800
            height = 400
            padding = 50
            
            # Draw borders
            canvas.create_line(padding, padding, padding, height - padding, fill=self.colors["border"])
            canvas.create_line(padding, height - padding, width - padding, height - padding, fill=self.colors["border"])
            
            # Draw titles
            canvas.create_text(width // 2, padding // 2, text=self.cb_param.get(), fill=self.colors["accent"], font=("Segoe UI", 12, "bold"))
            
            # Calculate ranges
            if param_idx == 0:
                ys = obs_f107
                lbl = "F10.7"
            else:
                ys = ap_avgs
                lbl = "Ap"
                
            y_min = min(ys)
            y_max = max(ys)
            if y_max == y_min:
                y_max += 10
            
            # Plot points
            n_points = len(ys)
            dx = (width - 2 * padding) / (n_points - 1)
            dy = (height - 2 * padding) / (y_max - y_min)
            
            prev_x, prev_y = None, None
            split_idx = len(obs_recs)
            
            for idx, y_val in enumerate(ys):
                x = padding + idx * dx
                y = height - padding - (y_val - y_min) * dy
                
                # Draw grid lines for splits
                if idx == split_idx - 1:
                    canvas.create_line(x, padding, x, height - padding, fill=self.colors["error"], dash=(4, 2))
                    canvas.create_text(x, padding + 10, text="Forecast Horizon", fill=self.colors["error"], font=("Segoe UI", 8))
                
                # Draw lines
                if prev_x is not None:
                    color = self.colors["accent"] if idx < split_idx else self.colors["success"]
                    dash = () if idx < split_idx else (2, 2)
                    canvas.create_line(prev_x, prev_y, x, y, fill=color, width=2, dash=dash)
                    
                prev_x, prev_y = x, y
                
            # Draw y axis labels
            canvas.create_text(padding - 20, padding, text=f"{int(y_max)}", fill=self.colors["text_sub"], font=("Consolas", 8))
            canvas.create_text(padding - 20, height - padding, text=f"{int(y_min)}", fill=self.colors["text_sub"], font=("Consolas", 8))
            
            # Legend
            canvas.create_line(width - 200, padding, width - 170, padding, fill=self.colors["accent"], width=2)
            canvas.create_text(width - 120, padding, text="Observed (Last 30d)", fill=self.colors["text"], font=("Segoe UI", 8))
            canvas.create_line(width - 200, padding + 20, width - 170, padding + 20, fill=self.colors["success"], width=2, dash=(2,2))
            canvas.create_text(width - 120, padding + 20, text="Predicted (Next 45d)", fill=self.colors["text"], font=("Segoe UI", 8))
            
            self.chart_canvas = canvas # Store reference to destroy later
            
        self.lbl_status.config(text="Status: Visualization Chart Updated")

    def build_eop_tab(self):
        # Left Panel (Settings)
        left_frame = ttk.Frame(self.tab_eop, style="Card.TFrame")
        left_frame.pack(side="left", fill="both", expand=False, padx=(5, 10), pady=5)
        left_frame.configure(width=320)
        left_frame.pack_propagate(False)
        
        lbl_cfg = ttk.Label(left_frame, text="EOP COMPILER CONFIGURATION", style="Title.TLabel")
        lbl_cfg.pack(anchor="w", padx=15, pady=(15, 5))
        
        lbl_desc = ttk.Label(left_frame, 
                             text="Fetch raw Earth Orientation Parameters from IERS Paris Observatory and USNO, and compile EOP legacy text or CSV files offline.", 
                             style="Sub.TLabel", wraplength=290)
        lbl_desc.pack(anchor="w", padx=15, pady=(0, 20))
        
        # Output Path Config
        lbl_path = ttk.Label(left_frame, text="Output File Path:", style="Card.TLabel")
        lbl_path.pack(anchor="w", padx=15, pady=2)
        
        path_frame = ttk.Frame(left_frame, style="Card.TFrame")
        path_frame.pack(fill="x", padx=15, pady=(0, 10))
        
        self.ent_eop_path = ttk.Entry(path_frame)
        self.ent_eop_path.insert(0, "C:/Users/baris/Desktop/90-tool/05_TKS_Conj_Auto/Inputs/AppData/eop19620101.txt")
        self.ent_eop_path.pack(side="left", fill="x", expand=True, ipady=3)
        
        btn_browse = ttk.Button(path_frame, text="...", width=3, command=self.browse_eop_output_path)
        btn_browse.pack(side="right", padx=(5, 0))
        
        # Legacy format Checkbox
        self.var_eop_legacy = tk.BooleanVar(value=True)
        self.chk_eop_legacy = tk.Checkbutton(
            left_frame, text="Legacy Format (Include NGA)",
            variable=self.var_eop_legacy,
            bg=self.colors["card"], fg=self.colors["text"],
            selectcolor=self.colors["bg"],
            activebackground=self.colors["card"],
            activeforeground=self.colors["accent"],
            font=("Segoe UI", 10, "bold")
        )
        self.chk_eop_legacy.pack(anchor="w", padx=15, pady=(5, 10))
        
        # Compile Mode
        lbl_mode = ttk.Label(left_frame, text="Compile Source Mode:", style="Card.TLabel")
        lbl_mode.pack(anchor="w", padx=15, pady=2)
        self.cb_eop_mode = ttk.Combobox(left_frame, values=["Offline Compile (USNO/IERS Raw)", "Download & Transform (CelesTrak)"], state="readonly")
        self.cb_eop_mode.current(0)
        self.cb_eop_mode.pack(fill="x", padx=15, pady=(0, 15))
        
        # Action Buttons
        self.btn_eop_compile = ttk.Button(left_frame, text="Compile EOP", style="Accent.TButton", command=self.start_eop_compilation)
        self.btn_eop_compile.pack(fill="x", padx=15, pady=5)
        
        self.btn_eop_verify = ttk.Button(left_frame, text="Verify with CelesTrak", command=self.start_eop_verification)
        self.btn_eop_verify.pack(fill="x", padx=15, pady=5)
        
        # Progress status
        self.lbl_eop_status = ttk.Label(left_frame, text="Status: Ready", style="Status.TLabel")
        self.lbl_eop_status.pack(anchor="w", padx=15, pady=(20, 2))
        
        self.eop_progress = ttk.Progressbar(left_frame, mode="indeterminate")
        self.eop_progress.pack(fill="x", padx=15, pady=5)
        
        # Right Panel (Console Logs)
        right_frame = ttk.Frame(self.tab_eop, style="Card.TFrame")
        right_frame.pack(side="right", fill="both", expand=True, padx=5, pady=5)
        
        lbl_log = ttk.Label(right_frame, text="EOP COMPILER LOGS & OUTPUT", style="Title.TLabel")
        lbl_log.pack(anchor="w", padx=15, pady=15)
        
        # Console output text box
        self.txt_eop_log = tk.Text(right_frame, bg=self.colors["bg"], fg=self.colors["text"], 
                                  insertbackground=self.colors["text"], font=("Consolas", 9), 
                                  borderwidth=1, relief="flat")
        self.txt_eop_log.pack(fill="both", expand=True, padx=15, pady=(0, 15))
        
        # Append initial instructions
        self.append_eop_log("EOP compiler initialized. Click 'Compile EOP' to begin.\n")

    # Legacy toggle no longer needed as coefficients are embedded

    def browse_eop_output_path(self):
        filename = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text File", "*.txt"), ("CSV File", "*.csv")]
        )
        if filename:
            self.ent_eop_path.delete(0, tk.END)
            self.ent_eop_path.insert(0, filename)

    # Browse NGE path no longer needed

    def append_eop_log(self, text):
        self.txt_eop_log.insert(tk.END, text)
        self.txt_eop_log.see(tk.END)

    def start_eop_compilation(self):
        self.btn_eop_compile.config(state="disabled")
        self.btn_eop_verify.config(state="disabled")
        self.lbl_eop_status.config(text="Status: Compiling EOP...")
        self.eop_progress.start(10)
        self.txt_eop_log.delete("1.0", tk.END)
        self.append_eop_log("Starting EOP Compilation...\n")
        
        # Retrieve values
        output_path = self.ent_eop_path.get()
        legacy_mode = self.var_eop_legacy.get()
        offline_mode = (self.cb_eop_mode.current() == 0)
        cache_dir = self.ent_cache.get()
        
        t = threading.Thread(
            target=self.thread_eop_compile,
            args=(output_path, legacy_mode, offline_mode, cache_dir)
        )
        t.daemon = True
        t.start()

    def thread_eop_compile(self, output_path, legacy_mode, offline_mode, cache_dir):
        try:
            compiler = EOPCompiler(
                cache_dir=cache_dir,
                log_callback=lambda msg: self.root.after(0, self.append_eop_log, msg + "\n")
            )
            
            data = compiler.compile(offline_mode=offline_mode)
            
            _, ext = os.path.splitext(output_path)
            if ext.lower() == ".csv":
                compiler.write_to_csv(data, output_path)
            else:
                compiler.write_to_legacy_txt(data, output_path, legacy_mode=legacy_mode)
                
            self.root.after(0, self.on_eop_compilation_success, output_path)
        except Exception as e:
            self.root.after(0, self.on_eop_compilation_error, str(e))

    def on_eop_compilation_success(self, filepath):
        self.lbl_eop_status.config(text="Status: Compilation Success!")
        self.eop_progress.stop()
        self.btn_eop_compile.config(state="normal")
        self.btn_eop_verify.config(state="normal")
        self.append_eop_log(f"\nCompilation finished successfully! Saved to: {filepath}\n")
        messagebox.showinfo("Success", f"EOP database successfully compiled and written to:\n{filepath}")

    def on_eop_compilation_error(self, err_msg):
        self.lbl_eop_status.config(text="Status: Compilation Failed")
        self.eop_progress.stop()
        self.btn_eop_compile.config(state="normal")
        self.btn_eop_verify.config(state="normal")
        self.append_eop_log(f"\nError during compile: {err_msg}\n")
        messagebox.showerror("EOP Compilation Error", f"An error occurred during EOP compilation:\n{err_msg}")

    def start_eop_verification(self):
        self.btn_eop_compile.config(state="disabled")
        self.btn_eop_verify.config(state="disabled")
        self.lbl_eop_status.config(text="Status: Verifying EOP...")
        self.eop_progress.start(10)
        self.txt_eop_log.delete("1.0", tk.END)
        self.append_eop_log("Starting verification with live CelesTrak database...\n")
        
        output_path = self.ent_eop_path.get()
        cache_dir = self.ent_cache.get()
        
        t = threading.Thread(target=self.thread_eop_verify, args=(output_path, cache_dir))
        t.daemon = True
        t.start()

    def thread_eop_verify(self, output_path, cache_dir):
        try:
            compiler = EOPCompiler(
                cache_dir=cache_dir,
                log_callback=lambda msg: self.root.after(0, self.append_eop_log, msg + "\n")
            )
            report = compiler.verify_with_celestrak(output_path)
            self.root.after(0, self.on_eop_verification_finished, report)
        except Exception as e:
            self.root.after(0, self.on_eop_compilation_error, str(e))

    def on_eop_verification_finished(self, report):
        self.lbl_eop_status.config(text="Status: Verification Finished")
        self.eop_progress.stop()
        self.btn_eop_compile.config(state="normal")
        self.btn_eop_verify.config(state="normal")
        
        obs_matches = report["obs_match_rate"]
        pred_matches = report["pred_match_rate"]
        discrepancies = len(report["discrepancies"])
        is_legacy = report["is_legacy"]
        
        self.append_eop_log(f"\n--- Live Verification Report Completed ---\n")
        self.append_eop_log(f"Legacy Format detected: {'YES' if is_legacy else 'NO'}\n")
        self.append_eop_log(f"Observed compatibility rate: {obs_matches * 100:.2f}%\n")
        self.append_eop_log(f"Predictions compatibility rate: {pred_matches * 100:.2f}%\n")
        self.append_eop_log(f"Total discrepancies: {discrepancies}\n")
        
        if obs_matches >= 0.98:
            messagebox.showinfo(
                "EOP Verification Passed",
                f"Compatibility Check PASSED!\n\n"
                f"Legacy Format: {'YES' if is_legacy else 'NO'}\n"
                f"Observed: {obs_matches * 100:.2f}%\n"
                f"Predicted: {pred_matches * 100:.2f}%\n"
                f"Discrepancies: {discrepancies}"
            )
        else:
            messagebox.showwarning(
                "EOP Verification Discrepancy",
                f"Compatibility Check finished with discrepancies.\n\n"
                f"Match Rate: {obs_matches * 100:.2f}%\n"
                f"See logs for details."
            )


def start_gui():
    root = tk.Tk()
    app = SpaceWeatherGUI(root)
    root.mainloop()

if __name__ == "__main__":
    start_gui()
