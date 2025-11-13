#!/usr/bin/env python3
"""
FITS Image Calibration GUI
A user-friendly graphical interface for the FITS calibration tool
Based on DeepSkyStacker methodology for 3D RGB FITS files
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import queue
import logging
import sys
import json
import os
from pathlib import Path
from typing import Optional

# Import the calibration module
try:
    import calibration
except ImportError:
    messagebox.showerror("Import Error", "Failed to import calibration module")
    sys.exit(1)

# Import the FITS viewer
try:
    from viewer import FitsViewer
except ImportError:
    messagebox.showerror("Import Error", "Failed to import FitsViewer module")
    sys.exit(1)

class LogHandler(logging.Handler):
    """Custom log handler to redirect logs to GUI"""
    
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue
    
    def emit(self, record):
        self.log_queue.put(self.format(record))

class FITSCalibrationGUI:
    """Main GUI application for FITS calibration"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("FITS Image Calibration Tool - DSS Style")
        self.root.geometry("1000x1000")  # Further increased height to prevent overlap
        
        # Variables for folder paths
        self.input_folder = tk.StringVar()  # Main input folder
        self.bias_folder = tk.StringVar()
        self.dark_folder = tk.StringVar()
        self.flat_folder = tk.StringVar()
        self.darkflat_folder = tk.StringVar()  # Optional darkflat folder
        self.light_folder = tk.StringVar()
        
        # File counter labels - will be created in create_folder_selection
        self.folder_counters = {}
        
        # Processing options with default values
        self.master_method = tk.StringVar(value='median')
        self.optimize_dark = tk.BooleanVar(value=True)
        self.verbose_logging = tk.BooleanVar(value=False)
        
        # Processing state
        self.is_processing = False
        self.processing_thread = None
        
        # Set up logging
        self.log_queue = queue.Queue()
        self.setup_logging()
        
        # Create GUI
        self.create_widgets()
        self.check_log_queue()
    
    
    def setup_logging(self):
        """Set up logging to redirect to GUI"""
        # Create custom handler
        self.log_handler = LogHandler(self.log_queue)
        self.log_handler.setFormatter(
            logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        )
        
        # Configure the calibration logger
        logger = logging.getLogger()
        logger.handlers.clear()  # Remove existing handlers
        logger.addHandler(self.log_handler)
        logger.setLevel(logging.INFO)
    
    def create_widgets(self):
        """Create and arrange GUI widgets"""
        
        # Main frame with padding
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        
        # Title
        title_label = ttk.Label(main_frame, text="FITS Image Calibration Tool", 
                               font=("Arial", 16, "bold"))
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 20))
        
        # File/Folder Selection Section (rows 1-11)
        self.create_folder_selection(main_frame, row_start=1)

        # Processing Options Section (rows 14-17)
        self.create_options_section(main_frame, row_start=14)

        # Control Buttons (row 20)
        self.create_control_buttons(main_frame, row_start=20)

        # Progress Bar (rows 22-23)
        self.progress_var = tk.StringVar(value="Ready")
        self.create_progress_section(main_frame, row_start=22)

        # Log Display (rows 25-26)
        self.create_log_section(main_frame, row_start=25)
    
    def create_folder_selection(self, parent, row_start):
        """Create folder selection widgets"""
        
        # Section header
        ttk.Label(parent, text="Folder Selection", font=("Arial", 12, "bold")).grid(
            row=row_start, column=0, columnspan=3, sticky=tk.W, pady=(0, 10))
        
        # Main input folder (new streamlined approach)
        ttk.Label(parent, text="Input Folder:", font=("Arial", 10, "bold")).grid(
            row=row_start + 1, column=0, sticky=tk.W, padx=(20, 10), pady=2)
        
        input_entry = ttk.Entry(parent, textvariable=self.input_folder, width=50)
        input_entry.grid(row=row_start + 1, column=1, sticky=(tk.W, tk.E), padx=(0, 10), pady=2)
        
        input_browse_btn = ttk.Button(parent, text="Browse",
                                     command=lambda: self.browse_folder(self.input_folder))
        input_browse_btn.grid(row=row_start + 1, column=2, pady=2)
        
        # Explanation text
        explanation_label = ttk.Label(parent,
                              text="Input Folder = parent folder containing all your calibration data organized into subfolders",
                              font=("Arial", 12, "italic"), foreground="gray")
        explanation_label.grid(row=row_start + 2, column=1, columnspan=2, sticky=tk.W, pady=(0, 5))

        # Auto-populate button with help text
        auto_frame = ttk.Frame(parent)
        auto_frame.grid(row=row_start + 3, column=1, columnspan=2, sticky=tk.W, pady=5)

        auto_btn = ttk.Button(auto_frame, text="Auto-Detect Subfolders",
                             command=self.auto_detect_folders)
        auto_btn.pack(side=tk.LEFT, padx=(0, 10))

        # Info button for help
        info_btn = ttk.Button(auto_frame, text="?", width=3,
                             command=self.show_auto_detect_help)
        info_btn.pack(side=tk.LEFT)

        # Brief hint text
        hint_label = ttk.Label(parent,
                              text="Searches for 'light/', 'bias/', 'dark/', 'flat/' subfolders in your input folder",
                              font=("Arial", 12), foreground="gray")
        hint_label.grid(row=row_start + 4, column=1, columnspan=2, sticky=tk.W, pady=(0, 10))

        # Individual folder overrides (optional)
        ttk.Label(parent, text="Or Manually Select Folders:", font=("Arial", 12, "italic")).grid(
            row=row_start + 5, column=0, columnspan=3, sticky=tk.W, padx=(20, 10), pady=(10, 5))
        
        # Folder selection rows (now optional overrides)
        folders = [
            ("Bias Frames:", self.bias_folder, "bias"),
            ("Dark Frames:", self.dark_folder, "dark"),
            ("Flat Frames:", self.flat_folder, "flat"),
            ("Dark Flat Frames (Optional):", self.darkflat_folder, "darkflat"),
            ("Light Frames:", self.light_folder, "light")
        ]
        
        for i, (label_text, var, folder_key) in enumerate(folders):
            row = row_start + 6 + i
            
            # Label
            ttk.Label(parent, text=label_text).grid(
                row=row, column=0, sticky=tk.W, padx=(20, 10), pady=2)
            
            # Entry
            entry = ttk.Entry(parent, textvariable=var, width=50)
            entry.grid(row=row, column=1, sticky=(tk.W, tk.E), padx=(0, 10), pady=2)
            
            # Browse button
            browse_btn = ttk.Button(parent, text="Browse",
                                  command=lambda v=var, k=folder_key: self.browse_folder_with_counter(v, k))
            browse_btn.grid(row=row, column=2, pady=2)
            
            # File counter label
            counter_label = ttk.Label(parent, text="(0 files)", font=("Arial", 9), foreground="gray")
            counter_label.grid(row=row, column=3, sticky=tk.W, padx=(5, 0), pady=2)
            self.folder_counters[folder_key] = counter_label
    
    def create_options_section(self, parent, row_start):
        """Create processing options widgets"""
        
        # Section header
        ttk.Label(parent, text="Processing Options", font=("Arial", 12, "bold")).grid(
            row=row_start, column=0, columnspan=3, sticky=tk.W, pady=(20, 10))
        
        # Master frame method
        ttk.Label(parent, text="Master Frame Method:").grid(
            row=row_start + 1, column=0, sticky=tk.W, padx=(20, 10), pady=2)
        
        method_frame = ttk.Frame(parent)
        method_frame.grid(row=row_start + 1, column=1, sticky=tk.W, pady=2)
        
        ttk.Radiobutton(method_frame, text="Median", variable=self.master_method,
                       value="median").pack(side=tk.LEFT, padx=(0, 20))
        ttk.Radiobutton(method_frame, text="Mean", variable=self.master_method,
                       value="mean").pack(side=tk.LEFT)
        
        # Checkboxes
        ttk.Checkbutton(parent, text="Optimize Dark Frame Matching",
                       variable=self.optimize_dark).grid(
            row=row_start + 2, column=0, columnspan=2, sticky=tk.W, padx=(20, 0), pady=2)
        
        ttk.Checkbutton(parent, text="Verbose Logging",
                       variable=self.verbose_logging).grid(
            row=row_start + 3, column=0, columnspan=2, sticky=tk.W, padx=(20, 0), pady=2)
    
    def create_control_buttons(self, parent, row_start):
        """Create control buttons"""
        
        button_frame = ttk.Frame(parent)
        button_frame.grid(row=row_start, column=0, columnspan=3, pady=20)
        
        self.start_btn = ttk.Button(button_frame, text="Start Calibration",
                                   command=self.start_calibration,
                                   style="Accent.TButton")
        self.start_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        self.stop_btn = ttk.Button(button_frame, text="Stop",
                                  command=self.stop_calibration,
                                  state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        # Viewer buttons
        self.view_btn = ttk.Button(button_frame, text="View Original",
                                  command=self.view_original_image)
        self.view_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        self.view_calibrated_btn = ttk.Button(button_frame, text="View Calibrated",
                                             command=self.view_calibrated_image)
        self.view_calibrated_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Button(button_frame, text="Clear Log",
                  command=self.clear_log).pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Button(button_frame, text="Exit",
                  command=self.root.quit).pack(side=tk.LEFT)
    
    def create_progress_section(self, parent, row_start):
        """Create progress display"""
        
        # Progress label
        self.progress_label = ttk.Label(parent, textvariable=self.progress_var)
        self.progress_label.grid(row=row_start, column=0, columnspan=3, 
                                sticky=(tk.W, tk.E), pady=(0, 5))
        
        # Progress bar
        self.progress_bar = ttk.Progressbar(parent, mode='indeterminate')
        self.progress_bar.grid(row=row_start + 1, column=0, columnspan=3,
                              sticky=(tk.W, tk.E), pady=(0, 10))
    
    def create_log_section(self, parent, row_start):
        """Create log display area"""
        
        # Log label
        ttk.Label(parent, text="Processing Log", font=("Arial", 12, "bold")).grid(
            row=row_start, column=0, columnspan=3, sticky=tk.W, pady=(10, 5))
        
        # Log text area
        self.log_text = scrolledtext.ScrolledText(parent, height=12, width=80,
                                                 font=("Courier", 9))
        self.log_text.grid(row=row_start + 1, column=0, columnspan=3,
                          sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        
        # Configure text area to expand
        parent.rowconfigure(row_start + 1, weight=1)
    
    def browse_folder(self, var):
        """Open folder browser dialog"""
        folder = filedialog.askdirectory(title="Select Folder")
        if folder:
            var.set(folder)
    
    def browse_folder_with_counter(self, var, folder_key):
        """Open folder browser dialog and update file counter"""
        folder = filedialog.askdirectory(title="Select Folder")
        if folder:
            var.set(folder)
            self.update_folder_counter(folder_key, folder)
    
    def update_folder_counter(self, folder_key, folder_path):
        """Update the file counter for a specific folder"""
        if folder_key in self.folder_counters and folder_path:
            try:
                from pathlib import Path
                folder = Path(folder_path)
                if folder.exists():
                    fits_count = self.count_fits_files(folder)
                    counter_text = f"({fits_count} files)"
                    color = "green" if fits_count > 0 else "orange"
                    self.folder_counters[folder_key].config(text=counter_text, foreground=color)
                else:
                    self.folder_counters[folder_key].config(text="(folder not found)", foreground="red")
            except Exception as e:
                self.folder_counters[folder_key].config(text="(error)", foreground="red")
        elif folder_key in self.folder_counters:
            self.folder_counters[folder_key].config(text="(0 files)", foreground="gray")
    
    def update_all_folder_counters(self):
        """Update all folder counters after auto-detection"""
        folder_vars = {
            "bias": self.bias_folder.get(),
            "dark": self.dark_folder.get(),
            "flat": self.flat_folder.get(),
            "darkflat": self.darkflat_folder.get(),
            "light": self.light_folder.get()
        }
        
        for folder_key, folder_path in folder_vars.items():
            self.update_folder_counter(folder_key, folder_path)
    
    def count_fits_files(self, folder_path):
        """Count the number of FITS files in a folder"""
        try:
            fits_files = calibration.find_fits_files(folder_path)
            return len(fits_files)
        except Exception as e:
            self.log_queue.put(f"Error counting FITS files in {folder_path}: {str(e)}")
            return 0
    
    def show_auto_detect_help(self):
        """Show help dialog for auto-detect feature"""
        help_text = """Auto-Detect Subfolders Feature

This feature automatically finds calibration frame folders inside your main input folder.

Expected Folder Structure:
  YourInputFolder/
  |-- light/          (Your science images)
  |-- bias/           (Bias frames)
  |-- dark/           (Dark frames)
  |-- flat/           (Flat frames)
  +-- darkflat/       (Dark flat frames - optional)

How it works:
1. Searches for subfolders named: light, bias, dark, flat, darkflat
2. Also checks for: light_fits, bias_fits, etc.
3. Counts FITS files in each folder
4. Automatically fills in the paths below

Tips:
- Works best with standard folder names
- Prefers folders ending with '_fits'
- Shows how many FITS files found in each folder
- You can still manually override any folder after auto-detection"""

        messagebox.showinfo("Auto-Detect Help", help_text)

    def auto_detect_folders(self):
        """Enhanced auto-detect subfolders with priority system and FITS file validation"""
        input_path = self.input_folder.get()
        if not input_path:
            messagebox.showwarning("Input Folder Required",
                                 "Please select an input folder first.\n\n" +
                                 "The input folder should contain subfolders like:\n" +
                                 "- light/\n- bias/\n- dark/\n- flat/")
            return

        input_folder = Path(input_path)
        if not input_folder.exists():
            messagebox.showerror("Folder Not Found",
                               f"Input folder does not exist:\n{input_path}")
            return
        
        # Frame types with their corresponding GUI variables
        frame_types = {
            'light': self.light_folder,
            'bias': self.bias_folder,
            'dark': self.dark_folder,
            'flat': self.flat_folder,
            'darkflat': self.darkflat_folder
        }
        
        # Priority search patterns for each frame type (higher priority first)
        search_patterns = {
            'light': ['light_fits', 'light'],
            'bias': ['bias_fits', 'bias'], 
            'dark': ['dark_fits', 'dark'],
            'flat': ['flat_fits', 'flat'],
            'darkflat': ['darkflat_fits', 'darkflat']
        }
        
        found_folders = []
        detection_log = []
        
        # Auto-detect each frame type using priority system
        for frame_type, var in frame_types.items():
            patterns = search_patterns[frame_type]
            best_folder = None
            best_count = 0
            search_log = []
            
            for pattern in patterns:
                folder_path = input_folder / pattern
                if folder_path.exists() and folder_path.is_dir():
                    fits_count = self.count_fits_files(folder_path)
                    search_log.append(f"  {pattern}: {fits_count} FITS files")
                    
                    # Priority logic: prefer _fits suffix, then higher count
                    if fits_count > 0:
                        if best_folder is None or fits_count > best_count or \
                           (pattern.endswith('_fits') and not str(best_folder).endswith('_fits')):
                            best_folder = folder_path
                            best_count = fits_count
                else:
                    search_log.append(f"  {pattern}: folder not found")
            
            # Set the best folder found
            if best_folder and best_count > 0:
                var.set(str(best_folder))
                found_folders.append(frame_type)
                detection_log.append(f"✓ {frame_type.upper()}: {best_folder.name} ({best_count} FITS files)")
                self.log_queue.put(f"Auto-detected {frame_type}: {best_folder} ({best_count} files)")
            else:
                detection_log.append(f"✗ {frame_type.upper()}: No valid folder found")
                self.log_queue.put(f"No valid {frame_type} folder found")
            
            # Log search details
            for log_entry in search_log:
                self.log_queue.put(log_entry)
        
        # Show comprehensive results with improved formatting
        if found_folders:
            result_msg = "Auto-Detection Successful!\n\n"
            result_msg += "Found folders:\n" + "\n".join(f"  {log}" for log in detection_log if log.startswith("✓"))

            # Show what wasn't found (if any)
            not_found = [log for log in detection_log if log.startswith("✗")]
            if not_found and len(not_found) < len(detection_log):
                result_msg += "\n\nNot found (optional):\n" + "\n".join(f"  {log}" for log in not_found)

            result_msg += f"\n\nReady to calibrate with {len(found_folders)} frame type(s)!"
            result_msg += "\n\nYou can manually adjust any folder below if needed."
            messagebox.showinfo("Auto-Detection Complete", result_msg)
        else:
            result_msg = "No calibration folders found\n\n"
            result_msg += "Searched for subfolders named:\n"
            result_msg += "  - light_fits or light\n"
            result_msg += "  - bias_fits or bias\n"
            result_msg += "  - dark_fits or dark\n"
            result_msg += "  - flat_fits or flat\n\n"
            result_msg += f"In folder: {input_folder}\n\n"
            result_msg += "Click the '?' button for help setting up folders"
            messagebox.showwarning("No Folders Found", result_msg)
    
        # Update all folder counters after auto-detection
        self.update_all_folder_counters()
    
    def validate_inputs(self):
        """Validate user inputs before starting calibration"""
        errors = []
        
        # Check if light folder is specified and exists
        if not self.light_folder.get():
            errors.append("Light frames folder is required")
        elif not Path(self.light_folder.get()).exists():
            errors.append("Light frames folder does not exist")
        
        # Check if at least one calibration frame type is specified
        has_calibration_frames = any([
            self.bias_folder.get() and Path(self.bias_folder.get()).exists(),
            self.dark_folder.get() and Path(self.dark_folder.get()).exists(),
            self.flat_folder.get() and Path(self.flat_folder.get()).exists()
        ])
        
        if not has_calibration_frames:
            errors.append("At least one calibration frame type (bias, dark, or flat) is required")
        
        return errors
    
    def start_calibration(self):
        """Start the calibration process in a separate thread"""
        
        # Validate inputs
        errors = self.validate_inputs()
        if errors:
            messagebox.showerror("Validation Error", "\\n".join(errors))
            return
        
        # Update UI state
        self.is_processing = True
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.progress_var.set("Starting calibration...")
        self.progress_bar.start()
        
        # Set logging level
        logger = logging.getLogger()
        if self.verbose_logging.get():
            logger.setLevel(logging.DEBUG)
        else:
            logger.setLevel(logging.INFO)
        
        # Start processing thread
        self.processing_thread = threading.Thread(target=self.run_calibration, daemon=True)
        self.processing_thread.start()
    
    def run_calibration(self):
        """Run the calibration process (in separate thread)"""
        try:
            # Create paths
            input_folder = Path(self.input_folder.get()) if self.input_folder.get() else None
            light_folder = Path(self.light_folder.get())
            
            # Enhanced output folder logic - save calibrated and masters in input parent directory
            if input_folder:
                # Output folders will be created directly in the input parent directory
                base_output_folder = input_folder
                self.log_queue.put(f"Output will be saved in input directory: {base_output_folder}")
            else:
                # Fallback to parent of light folder
                base_output_folder = light_folder.parent
                self.log_queue.put(f"No input folder specified, using light folder parent: {base_output_folder}")
            
            # Create the calibrated and masters directories
            calibrated_folder = base_output_folder / "calibrated"
            masters_folder = base_output_folder / "masters"
            
            # Create output directories
            calibrated_folder.mkdir(exist_ok=True)
            masters_folder.mkdir(exist_ok=True)
            
            self.log_queue.put(f"Created output directories:")
            self.log_queue.put(f"  - Calibrated images: {calibrated_folder}")
            self.log_queue.put(f"  - Master frames: {masters_folder}")
            
            # Check for existing master frames first
            existing_masters = calibration.check_existing_master_frames(masters_folder)
            
            # Initialize master frame creator
            master_creator = calibration.MasterFrameCreator(method=self.master_method.get())
            
            # Initialize processors
            bias_processor = None
            dark_processor = None
            flat_processor = None
            darkflat_processor = None
            
            # Get folder paths with fallback to input subfolders
            bias_folder = None
            dark_folder = None
            flat_folder = None
            darkflat_folder = None
            
            if self.bias_folder.get():
                bias_folder = Path(self.bias_folder.get())
            elif input_folder:
                bias_folder = input_folder / "bias"
                
            if self.dark_folder.get():
                dark_folder = Path(self.dark_folder.get())
            elif input_folder:
                dark_folder = input_folder / "dark"
                
            if self.flat_folder.get():
                flat_folder = Path(self.flat_folder.get())
            elif input_folder:
                flat_folder = input_folder / "flat"
                
            if self.darkflat_folder.get():
                darkflat_folder = Path(self.darkflat_folder.get())
            elif input_folder:
                darkflat_folder = input_folder / "darkflat"
            
            # Handle bias frames (check existing or create new)
            if 'bias' in existing_masters:
                self.progress_var.set("Using existing master bias frame...")
                master_bias = calibration.FITSImage.from_file(existing_masters['bias'])
                bias_processor = calibration.BiasFrameProcessor(master_bias)
            elif bias_folder and bias_folder.exists():
                bias_files = calibration.find_fits_files(bias_folder)
                if bias_files:
                    self.progress_var.set("Creating new master bias frame...")
                    master_bias = master_creator.create_master_frame(bias_files)
                    master_bias.save_to_file(masters_folder / "master_bias.fits")
                    bias_processor = calibration.BiasFrameProcessor(master_bias)
                else:
                    self.log_queue.put("No bias frames found in bias folder")
            else:
                self.log_queue.put("No bias folder found - skipping bias correction")
            
            # Handle dark frames (check existing or create new)
            if 'dark' in existing_masters:
                self.progress_var.set("Using existing master dark frame...")
                master_dark = calibration.FITSImage.from_file(existing_masters['dark'])
                dark_processor = calibration.DarkFrameProcessor(master_dark, optimize_factor=self.optimize_dark.get())
            elif dark_folder and dark_folder.exists():
                dark_files = calibration.find_fits_files(dark_folder)
                if dark_files:
                    self.progress_var.set("Creating new master dark frame...")
                    master_dark = master_creator.create_master_frame(dark_files)
                    master_dark.save_to_file(masters_folder / "master_dark.fits")
                    dark_processor = calibration.DarkFrameProcessor(master_dark, optimize_factor=self.optimize_dark.get())
                else:
                    self.log_queue.put("No dark frames found in dark folder")
            else:
                self.log_queue.put("No dark folder found - skipping dark correction")
            
            # Handle flat frames (check existing or create new)
            if 'flat' in existing_masters:
                self.progress_var.set("Using existing master flat frame...")
                master_flat = calibration.FITSImage.from_file(existing_masters['flat'])
                flat_processor = calibration.FlatFrameProcessor(master_flat)
            elif flat_folder and flat_folder.exists():
                flat_files = calibration.find_fits_files(flat_folder)
                if flat_files:
                    self.progress_var.set("Creating new master flat frame with color balance...")
                    master_flat = master_creator.create_master_frame(flat_files)
                    master_flat.save_to_file(masters_folder / "master_flat.fits")
                    flat_processor = calibration.FlatFrameProcessor(master_flat)
                else:
                    self.log_queue.put("No flat frames found in flat folder")
            else:
                self.log_queue.put("No flat folder found - skipping flat correction")
            
            # Handle dark flat frames (optional - check existing or create new)
            if 'darkflat' in existing_masters:
                self.progress_var.set("Using existing master dark flat frame...")
                master_darkflat = calibration.FITSImage.from_file(existing_masters['darkflat'])
                darkflat_processor = calibration.DarkFlatFrameProcessor(master_darkflat)
            elif darkflat_folder and darkflat_folder.exists():
                darkflat_files = calibration.find_fits_files(darkflat_folder)
                if darkflat_files:
                    self.progress_var.set("Creating new master dark flat frame...")
                    master_darkflat = master_creator.create_master_frame(darkflat_files)
                    master_darkflat.save_to_file(masters_folder / "master_darkflat.fits")
                    darkflat_processor = calibration.DarkFlatFrameProcessor(master_darkflat)
                else:
                    self.log_queue.put("Dark flat folder exists but no dark flat frames found")
            else:
                self.log_queue.put("No dark flat folder found - skipping dark flat correction (optional)")
            
            # Initialize calibrator with all processors (including optional darkflat)
            calibrator = calibration.FITSCalibrator(bias_processor, dark_processor, flat_processor, darkflat_processor)
            
            # Process light frames
            light_files = calibration.find_fits_files(light_folder)
            if not light_files:
                raise calibration.FITSCalibrationError("No light frames found")
            
            # Process each light frame
            for i, light_file in enumerate(light_files):
                if not self.is_processing:  # Check for stop signal
                    break
                
                self.progress_var.set(f"Processing {i+1}/{len(light_files)}: {light_file.name}")
                
                # Load light frame
                light_image = calibration.FITSImage.from_file(light_file)
                
                # Apply calibration
                calibrated_image = calibrator.calibrate_image(light_image)
                
                # Save calibrated image
                output_filename = light_file.stem + "_calibrated.fits"
                output_path = calibrated_folder / output_filename
                calibrated_image.save_to_file(output_path)
            
            if self.is_processing:
                self.progress_var.set("Calibration completed successfully!")
                self.log_queue.put("\\n=== CALIBRATION COMPLETED SUCCESSFULLY ===\\n")
                
                # Offer to view the results
                self.root.after(1000, self.offer_to_view_results)
            else:
                self.progress_var.set("Calibration stopped by user")
                self.log_queue.put("\\n=== CALIBRATION STOPPED BY USER ===\\n")
                
        except Exception as e:
            self.progress_var.set(f"Calibration failed: {str(e)}")
            self.log_queue.put(f"\\nERROR: {str(e)}\\n")
        
        finally:
            # Reset UI state
            self.root.after(0, self.calibration_finished)
    
    def stop_calibration(self):
        """Stop the calibration process"""
        self.is_processing = False
        self.stop_btn.config(state=tk.DISABLED)
        self.progress_var.set("Stopping calibration...")
    
    def calibration_finished(self):
        """Clean up after calibration is finished"""
        self.is_processing = False
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.progress_bar.stop()
    
    def clear_log(self):
        """Clear the log display"""
        self.log_text.delete(1.0, tk.END)
    
    def view_original_image(self):
        """Open FITS viewer for original light frames"""
        light_folder = self.light_folder.get()
        if not light_folder:
            messagebox.showwarning("No Folder Selected", "Please select a light frames folder first.")
            return
        
        light_path = Path(light_folder)
        if not light_path.exists():
            messagebox.showerror("Folder Not Found", f"Light frames folder does not exist: {light_folder}")
            return
        
        # Find FITS files in light folder
        fits_files = calibration.find_fits_files(light_path)
        if not fits_files:
            messagebox.showwarning("No FITS Files", "No FITS files found in the light frames folder.")
            return
        
        # Create a selection dialog for multiple files
        self.create_file_selection_dialog("Select Original FITS File to View", fits_files, self.open_fits_viewer)
    
    def view_calibrated_image(self):
        """Open FITS viewer for calibrated images"""
         # Try to find calibrated images from auto-detected output
        input_folder = Path(self.input_folder.get()) if self.input_folder.get() else None
        light_folder = Path(self.light_folder.get()) if self.light_folder.get() else None
        
        # Auto-detect output folder
        if input_folder:
            base_output_folder = input_folder
        elif light_folder:
            base_output_folder = light_folder.parent
        else:
            messagebox.showwarning("No Output Found", "Cannot determine output location. Please run calibration first.")
            return
        
        calibrated_path = base_output_folder / "calibrated"
        if not calibrated_path.exists():
            messagebox.showwarning("No Calibrated Images", "No calibrated images found. Please run calibration first.")
            return
        
        # Find calibrated FITS files
        fits_files = calibration.find_fits_files(calibrated_path)
        if not fits_files:
            messagebox.showwarning("No Calibrated Files", "No calibrated FITS files found.")
            return
        
        # Create a selection dialog for multiple files
        self.create_file_selection_dialog("Select Calibrated FITS File to View", fits_files, self.open_fits_viewer)
    
    def create_file_selection_dialog(self, title, files, callback):
        """Create a dialog to select from multiple FITS files"""
        if len(files) == 1:
            # Only one file, open it directly
            callback(str(files[0]))
            return
        
        # Multiple files, show selection dialog
        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.geometry("600x400")
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Create listbox with scrollbar
        frame = ttk.Frame(dialog, padding="10")
        frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(frame, text="Select a FITS file to view:").pack(pady=(0, 10))
        
        # Listbox with scrollbar
        list_frame = ttk.Frame(frame)
        list_frame.pack(fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set)
        listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=listbox.yview)
        
        # Add files to listbox
        for file_path in files:
            listbox.insert(tk.END, file_path.name)
        
        # Select first item by default
        if files:
            listbox.selection_set(0)
        
        # Buttons
        button_frame = ttk.Frame(frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        
        def on_view():
            selection = listbox.curselection()
            if selection:
                selected_file = files[selection[0]]
                dialog.destroy()
                callback(str(selected_file))
            else:
                messagebox.showwarning("No Selection", "Please select a file to view.")
        
        def on_cancel():
            dialog.destroy()
        
        ttk.Button(button_frame, text="View", command=on_view).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(button_frame, text="Cancel", command=on_cancel).pack(side=tk.LEFT)
        
        # Double-click to view
        listbox.bind('<Double-Button-1>', lambda e: on_view())
        
        # Center the dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")
    
    def open_fits_viewer(self, filename):
        """Open the FITS viewer for a specific file"""
        try:
            viewer_window = tk.Toplevel()
            viewer_window.title(f"FITS Viewer - {Path(filename).name}")
            viewer_window.geometry("800x600")
            
            # Make window independent and not modal
            viewer_window.transient()  # Remove parent binding
            viewer_window.lift()
            viewer_window.focus_set()
            
            # Initialize viewer directly without threading to avoid UI issues
            try:
                FitsViewer(viewer_window, filename=filename)
            except Exception as e:
                messagebox.showerror("Viewer Error", f"Failed to load FITS file: {str(e)}")
                viewer_window.destroy()
            
        except Exception as e:
            messagebox.showerror("Viewer Error", f"Failed to open FITS viewer: {str(e)}")
    
    def offer_to_view_results(self):
        """Offer to view calibration results after completion"""
        response = messagebox.askyesno(
            "Calibration Complete", 
            "Calibration completed successfully!\\n\\nWould you like to view the calibrated results?"
        )
        if response:
            self.view_calibrated_image()
    
    def check_log_queue(self):
        """Check for new log messages and update display"""
        try:
            while True:
                message = self.log_queue.get_nowait()
                self.log_text.insert(tk.END, message + "\\n")
                self.log_text.see(tk.END)
                self.log_text.update()
        except queue.Empty:
            pass
        
        # Schedule next check
        self.root.after(100, self.check_log_queue)

def main():
    """Main function to start the GUI application"""
    
    # Create root window
    root = tk.Tk()
    
    # Apply a modern theme if available
    try:
        style = ttk.Style()
        available_themes = style.theme_names()
        if 'aqua' in available_themes:  # macOS
            style.theme_use('aqua')
        elif 'vista' in available_themes:  # Windows
            style.theme_use('vista')
        elif 'clam' in available_themes:  # Cross-platform
            style.theme_use('clam')
    except:
        pass  # Use default theme if there's an issue
    
    # Create and run the application
    app = FITSCalibrationGUI(root)
    
    # Center the window
    root.update_idletasks()
    width = root.winfo_width()
    height = root.winfo_height()
    x = (root.winfo_screenwidth() // 2) - (width // 2)
    y = (root.winfo_screenheight() // 2) - (height // 2)
    root.geometry(f"{width}x{height}+{x}+{y}")
    
    # Start the GUI
    try:
        root.mainloop()
    except KeyboardInterrupt:
        root.quit()

if __name__ == "__main__":
    main()