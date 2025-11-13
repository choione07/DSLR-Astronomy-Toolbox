#!/usr/bin/env python3
"""
DSLR Telescope Aperture Photometry GUI
A robust tool for performing aperture photometry on star field images with automatic tracking.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import numpy as np

# Force matplotlib to use TkAgg backend before importing pyplot
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
from matplotlib.patches import Circle
import os
import glob
from pathlib import Path
import threading
import time
import csv
import logging
from datetime import datetime
import json
import copy

try:
    from astropy.io import fits

    from astropy.stats import sigma_clipped_stats
    from astropy.time import Time
    from photutils.detection import DAOStarFinder
    from photutils.aperture import CircularAperture, CircularAnnulus
    from photutils.aperture import aperture_photometry
    from photutils.centroids import centroid_sources
except ImportError as e:
    print(f"Required astronomy libraries not found: {e}")
    print("Please install: pip install astropy photutils")
    exit(1)


class AperturePhotometryGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("DSLR Telescope Aperture Photometry")
        self.root.geometry("1400x1000")  # Larger window size

        # Setup logging - suppress matplotlib font debug messages
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

        # Suppress matplotlib font loading debug messages
        logging.getLogger('matplotlib.font_manager').setLevel(logging.WARNING)
        logging.getLogger('PIL.PngImagePlugin').setLevel(logging.WARNING)

        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG)  # Keep our app's debug messages

        # Application state
        self.fits_files = []
        self.current_image_data = None
        self.current_image_header = None
        self.selected_star_pos = None
        self.star_name = ""
        self.aperture_params = {'inner_radius': 9, 'inner_annulus': 12, 'outer_annulus': 17}
        
        self.processing = False
        self.stop_processing = False
        self.paused = False  # NEW: Track pause state
        self.paused_tracking_mode = None  # Track what mode tracking was in when paused
        self.zoom_active = False
        self.aperture_adjust_mode = False

        # Sequential tracking state (PASCO Capstone style)
        self.sequential_mode = False
        self.current_frame_index = 0
        self.frame_positions = []  # Store clicked positions for each frame
        self.sequential_results = []  # Store results for each frame (for going back)

        # NEW: Two-phase workflow state (your improvement!)
        self.preselection_mode = False
        self.preselected_positions = []  # Store all pre-selected positions
        self.batch_processing_mode = False
        self.stop_preselection = False  # Flag to stop pre-selection early

        # IMPROVED: Advanced tracking state - momentum and history
        self.position_history = []  # Store (x, y) for last N frames
        self.velocity_history = []  # Store (vx, vy) velocity vectors
        self.tracking_history_size = 5  # Number of frames to remember
        self.tracking_confidence = []  # Track confidence scores

        # Results storage
        self.photometry_results = []

        # Visualization window
        self.viz_window = None
        self.viz_figures = {}
        self.viz_axes = {}

        self.logger.info("Initializing GUI application")
        self.setup_gui()
        self.log_status("Application initialized successfully")


    def setup_gui(self):
        """Initialize the GUI layout"""
        # Main frame
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Left panel for controls - compact and scrollable
        control_outer_frame = ttk.Frame(main_frame, width=300)
        control_outer_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 5))
        control_outer_frame.pack_propagate(False)

        # Create scrollable canvas for controls
        canvas = tk.Canvas(control_outer_frame, width=290, highlightthickness=0)
        scrollbar = ttk.Scrollbar(control_outer_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        # Configure scrolling
        canvas.configure(yscrollcommand=scrollbar.set)

        # Pack scrollbar and canvas
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        # Create window for the scrollable frame
        canvas_window = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")

        def configure_scroll_region(event=None):
            """Update scroll region and canvas width"""
            canvas.configure(scrollregion=canvas.bbox("all"))
            # Ensure the scrollable frame spans the full width of canvas
            canvas_width = canvas.winfo_width()
            if canvas_width > 1:  # Avoid issues during initialization
                canvas.itemconfig(canvas_window, width=canvas_width)

        def configure_canvas_width(event):
            """Update canvas window width when canvas is resized"""
            configure_scroll_region()

        # Bind configuration events
        scrollable_frame.bind("<Configure>", configure_scroll_region)
        canvas.bind("<Configure>", configure_canvas_width)

        # Simplified mouse wheel scrolling that actually works
        def on_mousewheel(event):
            # Determine scroll direction and amount
            if event.delta:
                # Windows and MacOS
                delta = -1 * int(event.delta / 120)
            else:
                # Linux
                delta = -1 if event.num == 4 else 1

            # Only scroll if there's actually content to scroll
            if canvas.bbox("all"):
                canvas.yview_scroll(delta, "units")

        # Universal mouse wheel binding for all platforms
        def bind_mousewheel_universal(widget):
            # Windows and MacOS
            widget.bind("<MouseWheel>", on_mousewheel)
            # Linux
            widget.bind("<Button-4>", on_mousewheel)
            widget.bind("<Button-5>", on_mousewheel)

        # Apply mouse wheel to canvas and outer frame
        bind_mousewheel_universal(canvas)
        bind_mousewheel_universal(control_outer_frame)

        # Function to recursively apply mousewheel to all child widgets
        def apply_mousewheel_to_children():
            def recursive_bind(widget):
                bind_mousewheel_universal(widget)
                for child in widget.winfo_children():
                    recursive_bind(child)
            recursive_bind(scrollable_frame)

        # Store the binding function to call after controls are created
        self.bind_control_mousewheel = apply_mousewheel_to_children

        # Right panel for image display
        image_frame = ttk.Frame(main_frame)
        image_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        self.setup_control_panel(scrollable_frame)
        self.setup_image_display(image_frame)

    def setup_control_panel(self, parent):
        """Setup the control panel with all buttons and settings"""

        # STEP 1: Load Files
        load_section = ttk.LabelFrame(parent, text="1. Load Images", padding=8)
        load_section.pack(fill=tk.X, pady=(0, 8))

        ttk.Button(load_section, text="Select FITS Folder",
                  command=self.select_fits_folder).pack(fill=tk.X, pady=2)
        self.file_count_label = ttk.Label(load_section, text="No files loaded", foreground="gray")
        self.file_count_label.pack(pady=2)

        # STEP 2: Star Setup
        star_section = ttk.LabelFrame(parent, text="2. Star Setup", padding=8)
        star_section.pack(fill=tk.X, pady=(0, 8))

        # Compact star name input
        name_frame = ttk.Frame(star_section)
        name_frame.pack(fill=tk.X, pady=2)
        ttk.Label(name_frame, text="Name:", width=6).pack(side=tk.LEFT)
        self.star_name_var = tk.StringVar()
        ttk.Entry(name_frame, textvariable=self.star_name_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5,0))

        self.star_pos_label = ttk.Label(star_section, text="Click on image to select star", foreground="gray")
        self.star_pos_label.pack(pady=(5,2))

        # Compact sensitivity control
        sens_frame = ttk.Frame(star_section)
        sens_frame.pack(fill=tk.X, pady=2)
        ttk.Label(sens_frame, text="Sensitivity:", width=9).pack(side=tk.LEFT)

        self.sensitivity_var = tk.DoubleVar(value=2.0)
        sensitivity_scale = ttk.Scale(sens_frame, from_=0.5, to=3.0,
                                    variable=self.sensitivity_var, orient=tk.HORIZONTAL, length=120)
        sensitivity_scale.pack(side=tk.LEFT, padx=(5,5))

        self.sensitivity_label = ttk.Label(sens_frame, text="2.0σ", width=6)
        self.sensitivity_label.pack(side=tk.LEFT)

        # Update sensitivity display
        def update_sensitivity_display(*args):
            value = self.sensitivity_var.get()
            self.sensitivity_label.config(text=f"{value:.1f}σ")
        self.sensitivity_var.trace('w', update_sensitivity_display)

        # Compact tracking toggle
        self.tracking_enabled_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(star_section, text="Enable auto-tracking",
                       variable=self.tracking_enabled_var).pack(anchor=tk.W, pady=(5,2))

        # STEP 3: Aperture Setup
        aperture_section = ttk.LabelFrame(parent, text="3. Aperture Setup", padding=8)
        aperture_section.pack(fill=tk.X, pady=(0, 8))

        # Compact radius controls
        for param, label in [('inner_radius', 'Star Radius'),
                             ('inner_annulus', 'Inner Sky'),
                             ('outer_annulus', 'Outer Sky')]:
            var = tk.DoubleVar(value=self.aperture_params[param])
            setattr(self, f"{param}_var", var)

            # Compact horizontal layout
            control_frame = ttk.Frame(aperture_section)
            control_frame.pack(fill=tk.X, pady=1)

            # Short label
            ttk.Label(control_frame, text=f"{label}:", width=9).pack(side=tk.LEFT)

            # Compact slider
            scale = ttk.Scale(control_frame, from_=1, to=20, variable=var, length=100,
                            command=lambda v, p=param: self.update_aperture_preview(p, v))
            scale.pack(side=tk.LEFT, padx=(5,5))

            # Small value entry
            entry = ttk.Entry(control_frame, textvariable=var, width=6)
            entry.pack(side=tk.LEFT)
            entry.bind('<Return>', lambda e, p=param: self.update_aperture_preview(p, getattr(self, f"{p}_var").get()))
            entry.bind('<FocusOut>', lambda e, p=param: self.update_aperture_preview(p, getattr(self, f"{p}_var").get()))

        # Auto-tracking search radius control
        search_frame = ttk.Frame(aperture_section)
        search_frame.pack(fill=tk.X, pady=(8,2))

        ttk.Label(search_frame, text="Search Radius:", width=9).pack(side=tk.LEFT)

        # Search radius variable with good default
        self.search_radius_var = tk.IntVar(value=25)

        # Search radius slider (10 to 100 pixels)
        search_scale = ttk.Scale(search_frame, from_=10, to=100, variable=self.search_radius_var,
                                orient=tk.HORIZONTAL, length=100,
                                command=self.update_search_radius_display)
        search_scale.pack(side=tk.LEFT, padx=(5,5))

        # Search radius value display
        self.search_radius_label = ttk.Label(search_frame, text="25px", width=6)
        self.search_radius_label.pack(side=tk.LEFT)


        # Compact controls
        controls_frame = ttk.Frame(aperture_section)
        controls_frame.pack(fill=tk.X, pady=(5,2))
        ttk.Button(controls_frame, text="Zoom", width=8,
                  command=self.toggle_zoom).pack(side=tk.LEFT, padx=(0,5))

        self.refresh_button = ttk.Button(controls_frame, text="Refresh", width=8,
                                        command=self.refresh_display, state=tk.DISABLED)
        self.refresh_button.pack(side=tk.LEFT)

        # STEP 4: Processing Workflow
        process_section = ttk.LabelFrame(parent, text="4. Processing Workflow", padding=8)
        process_section.pack(fill=tk.X, pady=(0, 8))

        # Quick workflow buttons
        quick_frame = ttk.Frame(process_section)
        quick_frame.pack(fill=tk.X, pady=(0, 8))

        self.preselect_button = ttk.Button(quick_frame, text="Pre-select Positions",
                                          command=self.start_preselection_mode)
        self.preselect_button.pack(fill=tk.X, pady=2)

        self.pause_preselect_button = ttk.Button(process_section, text="Pause & Navigate",
                                                command=self.toggle_preselection_pause, state=tk.DISABLED)
        self.pause_preselect_button.pack(fill=tk.X, pady=2)

        self.stop_preselect_button = ttk.Button(process_section, text="Stop & Save",
                                               command=self.stop_preselection_mode, state=tk.DISABLED)
        self.stop_preselect_button.pack(fill=tk.X, pady=2)

        self.clear_position_button = ttk.Button(process_section, text="Clear Position",
                                               command=self.clear_current_frame_position, state=tk.DISABLED)
        self.clear_position_button.pack(fill=tk.X, pady=2)

        self.stop_button = ttk.Button(process_section, text="Stop Processing",
                                     command=self.stop_photometry_processing, state=tk.DISABLED)
        self.stop_button.pack(fill=tk.X, pady=(5, 2))

        # Navigation controls
        nav_frame = ttk.Frame(process_section)
        nav_frame.pack(fill=tk.X, pady=(8, 2))

        self.go_back_button = ttk.Button(nav_frame, text="Previous",
                                        command=self.go_back_frame, state=tk.DISABLED)
        self.go_back_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 2))

        self.skip_frame_button = ttk.Button(nav_frame, text="Next",
                                           command=self.skip_frame, state=tk.DISABLED)
        self.skip_frame_button.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(2, 0))

        # Run Photometry button (moved here below navigation)
        self.batch_process_button = ttk.Button(process_section, text="Run Photometry",
                                              command=self.start_batch_processing)
        self.batch_process_button.pack(fill=tk.X, pady=(8,2))

        # Progress bar (moved up for better visibility)
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(process_section, variable=self.progress_var,
                                          maximum=100)
        self.progress_bar.pack(fill=tk.X, pady=(8, 2), ipady=3)

        # STEP 5: Results
        results_section = ttk.LabelFrame(parent, text="5. Results", padding=8)
        results_section.pack(fill=tk.X, pady=(0, 8))

        # Compact results buttons
        results_frame = ttk.Frame(results_section)
        results_frame.pack(fill=tk.X)

        self.save_csv_button = ttk.Button(results_frame, text="Save CSV",
                                         command=self.save_results)
        self.save_csv_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0,2))
        self.save_csv_button.config(state=tk.DISABLED)

        self.quick_viz_button = ttk.Button(results_frame, text="Visualize",
                                          command=self.open_visualization_window)
        self.quick_viz_button.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(2,0))
        self.quick_viz_button.config(state=tk.DISABLED)

        # Progress Info
        info_frame = ttk.Frame(parent)
        info_frame.pack(fill=tk.X, pady=(0, 6))

        # Frame counter
        self.frame_counter_label = ttk.Label(info_frame, text="Ready", font=('Arial', 10, 'bold'),
                                           foreground='blue')
        self.frame_counter_label.pack(side=tk.LEFT)

        # Processed counter
        self.processed_counter_label = ttk.Label(info_frame, text="", font=('Arial', 10),
                                                foreground='green')
        self.processed_counter_label.pack(side=tk.RIGHT)

        # Status Log
        status_section = ttk.LabelFrame(parent, text="Status Log", padding=6)
        status_section.pack(fill=tk.BOTH, expand=True)

        # Status with scrollbar in single frame
        status_frame = ttk.Frame(status_section)
        status_frame.pack(fill=tk.BOTH, expand=True)

        self.status_text = tk.Text(status_frame, height=6, width=30, wrap=tk.WORD,
                                 font=('Consolas', 9), background='#f8f9fa')
        self.status_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        status_scroll = ttk.Scrollbar(status_frame, orient=tk.VERTICAL,
                                    command=self.status_text.yview)
        status_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.status_text.configure(yscrollcommand=status_scroll.set)

        # Apply enhanced mousewheel scrolling to all control widgets
        if hasattr(self, 'bind_control_mousewheel'):
            self.bind_control_mousewheel()

        # Set up auto-save for aperture settings

    def setup_image_display(self, parent):
        """Setup matplotlib canvas for image display"""
        # Create matplotlib figure exactly like working fitsviewer.py
        self.fig = Figure(figsize=(8, 8))
        self.ax = self.fig.add_subplot(111)

        # Create canvas exactly like working fitsviewer.py
        self.canvas = FigureCanvasTkAgg(self.fig, master=parent)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=1)

        # Add toolbar
        toolbar_frame = ttk.Frame(parent)
        toolbar_frame.pack(fill=tk.X)
        self.toolbar = NavigationToolbar2Tk(self.canvas, toolbar_frame)

        # Connect mouse click event
        self.canvas.mpl_connect('button_press_event', self.on_image_click)

        # Initial display
        self.ax.text(0.5, 0.5, 'No image loaded', transform=self.ax.transAxes,
                    ha='center', va='center', fontsize=16)
        self.ax.set_xticks([])
        self.ax.set_yticks([])
        self.canvas.draw()

    def log_status(self, message):
        """Add message to status display"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.status_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.status_text.see(tk.END)
        self.root.update_idletasks()

    def update_frame_counter(self, current_frame=None, total_frames=None, mode="Ready"):
        """Update the frame counter display"""
        if current_frame is not None and total_frames is not None:
            self.frame_counter_label.config(text=f"{mode}: Frame {current_frame + 1}/{total_frames}")
        else:
            self.frame_counter_label.config(text=mode)

    def update_processed_counter(self, processed_count=0, total_count=0):
        """Update the processed items counter"""
        if processed_count > 0:
            self.processed_counter_label.config(text=f"Processed: {processed_count}/{total_count}")
        else:
            self.processed_counter_label.config(text="")

    def select_fits_folder(self):
        """Select folder containing FITS files"""
        self.logger.debug("Opening folder selection dialog")
        folder_path = filedialog.askdirectory(title="Select FITS Image Folder")
        if folder_path:
            self.logger.info(f"Selected folder: {folder_path}")
            self.fits_files = sorted(glob.glob(os.path.join(folder_path, "*.fit*")))
            count = len(self.fits_files)
            self.file_count_label.config(text=f"{count} FITS files loaded")

            self.logger.debug(f"Found files: {[os.path.basename(f) for f in self.fits_files[:5]]}")
            if len(self.fits_files) > 5:
                self.logger.debug(f"... and {len(self.fits_files) - 5} more files")

            if count > 0:
                self.load_first_image()
                self.log_status(f"Loaded {count} FITS files from {folder_path}")

                # Update counter to show loaded files
                self.update_frame_counter(None, None, f"Loaded {count} files")
                self.update_processed_counter(0, 0)
            else:
                self.logger.warning("No FITS files found in selected folder")
                messagebox.showwarning("No Files", "No FITS files found in selected folder")
                self.update_frame_counter(None, None, "No files loaded")
                self.update_processed_counter(0, 0)

    def refresh_display(self):
        """Manually refresh the image display with complete reset"""
        if self.current_image_data is not None:
            self.logger.info("Manual refresh requested - performing complete display reset")

            # Store current state
            current_star_pos = self.selected_star_pos
            show_aperture = self.selected_star_pos is not None

            # Force complete matplotlib reset
            try:
                # Clear everything completely
                self.ax.clear()
                self.fig.clear()

                # Recreate the subplot from scratch
                self.ax = self.fig.add_subplot(111)

                # Reset zoom state
                self.zoom_active = False

                # Redraw the image with proper error handling
                self.display_image_robust(show_aperture=show_aperture)

                self.log_status("Display refreshed successfully")
                self.logger.info("Display refresh completed")

            except Exception as e:
                self.logger.error(f"Error during display refresh: {e}")
                # Emergency fallback - create completely new figure
                self.setup_image_display_emergency()
                self.log_status(f"Display refresh failed, reset to default: {e}")
        else:
            self.logger.warning("No image data available for refresh")

    def display_image_robust(self, show_aperture=False):
        """Robust image display with extensive error handling"""
        if self.current_image_data is None:
            self.logger.warning("display_image_robust called but no image data available")
            return

        try:
            # Use the fitsviewer.py approach directly for maximum robustness
            self.logger.info("Using robust display approach based on fitsviewer.py")

            # Store zoom state
            current_xlim = None
            current_ylim = None
            if self.zoom_active and hasattr(self.ax, 'get_xlim'):
                try:
                    current_xlim = self.ax.get_xlim()
                    current_ylim = self.ax.get_ylim()
                except:
                    pass

            # Clear axis completely
            self.ax.clear()

            # Determine image type and handle accordingly
            if hasattr(self, 'current_image_rgb') and self.current_image_rgb is not None:
                # RGB Color display - exactly like fitsviewer.py
                data = self.current_image_rgb.astype(np.float32)

                # Transpose from (C, H, W) to (H, W, C) for matplotlib
                if data.shape[0] in [3, 4]:  # Color axis first
                    display_data = np.moveaxis(data, 0, -1)
                elif data.shape[2] in [3, 4]:  # Color axis last
                    display_data = data
                else:
                    raise ValueError(f"Invalid RGB data shape: {data.shape}")

                # Normalize exactly like fitsviewer.py
                vmin, vmax = np.percentile(display_data, [0.5, 99.5])
                display_data = np.clip(display_data, vmin, vmax)
                display_data = (display_data - vmin) / (vmax - vmin)

                # Display
                self.ax.imshow(display_data, origin='lower')

                # Title
                if hasattr(self, 'fits_files') and self.fits_files:
                    filename = os.path.basename(self.fits_files[0])
                    self.ax.set_title(f"RGB: {filename}")
                else:
                    self.ax.set_title("RGB Image")

            else:
                # Grayscale display - exactly like fitsviewer.py
                data = self.current_image_data.astype(np.float32)

                # Use percentile for robust contrast stretching
                vmin, vmax = np.percentile(data, [0.5, 99.5])

                self.ax.imshow(data, cmap='gray', origin='lower', vmin=vmin, vmax=vmax)

                # Title
                if hasattr(self, 'fits_files') and self.fits_files:
                    filename = os.path.basename(self.fits_files[0])
                    self.ax.set_title(f"Grayscale: {filename}")
                else:
                    self.ax.set_title("Grayscale Image")

            # Add aperture circles if requested
            if show_aperture and self.selected_star_pos:
                self.draw_aperture_circles()

            # Restore zoom if it was active
            if self.zoom_active and current_xlim is not None and current_ylim is not None:
                try:
                    self.ax.set_xlim(current_xlim)
                    self.ax.set_ylim(current_ylim)
                except:
                    pass

            # Force canvas refresh with multiple methods
            try:
                self.canvas.draw()
                self.canvas.flush_events()
                self.root.update_idletasks()
                self.logger.info("Robust display completed successfully")
            except Exception as canvas_error:
                self.logger.warning(f"Canvas refresh issue: {canvas_error}")
                # Try alternative refresh
                self.canvas.get_tk_widget().update()

        except Exception as e:
            self.logger.error(f"Robust display failed: {e}")
            # Final fallback - show error message
            try:
                self.ax.clear()
                self.ax.text(0.5, 0.5, f'Display Error: {str(e)}',
                           transform=self.ax.transAxes, ha='center', va='center',
                           fontsize=12, color='red')
                self.canvas.draw()
            except:
                self.logger.error("Even error display failed - complete display system breakdown")

    def setup_image_display_emergency(self):
        """Emergency fallback to recreate the entire image display system"""
        self.logger.warning("Emergency image display reset in progress")

        try:
            # Get parent frame
            parent = self.canvas.get_tk_widget().master

            # Destroy old canvas
            try:
                self.canvas.get_tk_widget().destroy()
                if hasattr(self, 'toolbar'):
                    self.toolbar.destroy()
            except:
                pass

            # Recreate matplotlib components from scratch
            self.fig = Figure(figsize=(8, 8))
            self.ax = self.fig.add_subplot(111)

            # Recreate canvas
            self.canvas = FigureCanvasTkAgg(self.fig, master=parent)
            self.canvas.draw()
            self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=1)

            # Reconnect mouse events
            self.canvas.mpl_connect('button_press_event', self.on_image_click)

            # Show default message
            self.ax.text(0.5, 0.5, 'Display reset - no image loaded',
                        transform=self.ax.transAxes, ha='center', va='center', fontsize=16)
            self.ax.set_xticks([])
            self.ax.set_yticks([])
            self.canvas.draw()

            self.logger.info("Emergency display reset completed successfully")

        except Exception as e:
            self.logger.error(f"Emergency display reset failed: {e}")
            # Show error in status
            self.log_status("CRITICAL: Display system failure - please restart application")

    def load_first_image(self):
        """Load and display the first image for star selection"""
        if not self.fits_files:
            self.logger.warning("load_first_image called but no FITS files available")
            return

        try:
            first_file = self.fits_files[0]
            self.logger.info(f"Loading first FITS file: {os.path.basename(first_file)}")

            with fits.open(first_file) as hdul:
                self.current_image_data = hdul[0].data
                self.current_image_header = hdul[0].header

                # Log image information
                self.logger.debug(f"Image shape: {self.current_image_data.shape}")
                self.logger.debug(f"Data type: {self.current_image_data.dtype}")
                self.logger.debug(f"Data range: {np.min(self.current_image_data):.1f} to {np.max(self.current_image_data):.1f}")

                # Store original RGB data and create grayscale version
                if len(self.current_image_data.shape) == 3:
                    self.logger.info(f"Color image detected with {self.current_image_data.shape[0]} channels")
                    if self.current_image_data.shape[0] == 3:
                        # Keep original RGB data for photometry
                        self.current_image_rgb = self.current_image_data.copy()
                        # Create grayscale version for fallback
                        self.current_image_grayscale = np.mean(self.current_image_data, axis=0)
                        self.logger.info("RGB data stored, grayscale version created")
                    else:
                        self.current_image_rgb = None
                        self.current_image_grayscale = self.current_image_data
                else:
                    self.logger.info("Grayscale image detected")
                    self.current_image_rgb = None
                    self.current_image_grayscale = self.current_image_data

            self.display_image()
            self.log_status("First image loaded for star selection")
            self.logger.info("First image successfully loaded and displayed")

        except Exception as e:
            self.logger.error(f"Failed to load FITS file {first_file}: {e}")
            messagebox.showerror("Error", f"Failed to load FITS file: {e}")

    def display_image(self, show_aperture=False):
        """Display the current image"""
        if self.current_image_data is None:
            self.logger.warning("display_image called but no image data available")
            return

        self.logger.info("Starting image display process...")

        # Store current zoom state if active
        current_xlim = None
        current_ylim = None
        if self.zoom_active and hasattr(self.ax, 'get_xlim'):
            current_xlim = self.ax.get_xlim()
            current_ylim = self.ax.get_ylim()

        self.ax.clear()

        try:
            # Check if we have RGB data to display in color
            if hasattr(self, 'current_image_rgb') and self.current_image_rgb is not None:
                self.logger.debug("Displaying RGB color image")
                # Handle RGB data exactly like fitsviewer.py
                data = self.current_image_rgb.astype(np.float32)

                # Transpose from (C, H, W) to (H, W, C) for matplotlib
                display_data = np.moveaxis(data, 0, -1)

                # Normalize the data for display using percentile clipping
                vmin, vmax = np.percentile(display_data, [0.5, 99.5])
                display_data = np.clip(display_data, vmin, vmax)
                # Scale to [0, 1] range for imshow
                display_data = (display_data - vmin) / (vmax - vmin)

                self.logger.debug(f"RGB display data shape: {display_data.shape}")
                self.logger.debug(f"RGB display range: {np.min(display_data):.3f} to {np.max(display_data):.3f}")

                img = self.ax.imshow(display_data, origin='lower')
                # Create helpful title with filename if available
                if hasattr(self, 'fits_files') and self.fits_files:
                    filename = os.path.basename(self.fits_files[0])
                    self.ax.set_title(f"RGB: {filename} - Click to select star")
                else:
                    self.ax.set_title(f"FITS RGB Image - Click to select star")

            else:
                # Fallback to grayscale display
                self.logger.debug("Displaying grayscale image")
                data = self.current_image_data.astype(np.float32)

                # Use percentile for robust contrast stretching
                vmin, vmax = np.percentile(data, [0.5, 99.5])

                self.logger.debug(f"Grayscale scaling: vmin={vmin:.1f}, vmax={vmax:.1f}")
                self.logger.debug(f"Grayscale shape: {data.shape}")

                img = self.ax.imshow(data, cmap='gray', origin='lower', vmin=vmin, vmax=vmax)
                # Create helpful title with filename if available
                if hasattr(self, 'fits_files') and self.fits_files:
                    filename = os.path.basename(self.fits_files[0])
                    self.ax.set_title(f"Grayscale: {filename} - Click to select star")
                else:
                    self.ax.set_title(f"FITS Image - Click to select star")

            # Show aperture if star is selected
            if show_aperture and self.selected_star_pos:
                self.draw_aperture_circles()

            # Restore zoom state if it was active
            if self.zoom_active and current_xlim is not None and current_ylim is not None:
                self.ax.set_xlim(current_xlim)
                self.ax.set_ylim(current_ylim)
                self.logger.debug("Zoom state restored")

            # Force update with multiple methods
            self.fig.canvas.draw()
            self.fig.canvas.flush_events()

            # Make sure canvas is visible
            canvas_widget = self.canvas.get_tk_widget()
            canvas_widget.update()
            canvas_widget.update_idletasks()

            self.root.update()
            self.root.update_idletasks()

            self.logger.info("Image display completed successfully")

        except Exception as e:
            self.logger.error(f"Error displaying image: {e}")
            # Show error message on canvas
            self.ax.text(0.5, 0.5, f'Display Error: {str(e)}',
                        transform=self.ax.transAxes, ha='center', va='center',
                        fontsize=12, bbox=dict(boxstyle="round,pad=0.3", facecolor="red", alpha=0.7))
            self.canvas.draw()

    def on_image_click(self, event):
        """Handle mouse click on image for star selection or aperture adjustment"""
        if event.inaxes != self.ax:
            return

        if event.xdata is None or event.ydata is None:
            return

        # NEW: Check if we're paused - clicking updates position for current frame
        if self.paused:
            self.update_position_during_pause(event)
            return
        
        # Skip click handling if processing and not paused
        if self.processing:
            return

        # Check if we're in pre-selection mode (NEW - your improvement!)
        if self.preselection_mode:
            if self.on_preselection_click(event):
                return  # Pre-selection handled the click

        # Check if we're in sequential tracking mode
        if self.sequential_mode:
            if self.on_sequential_tracking_click(event):
                return  # Sequential tracking handled the click

        x, y = event.xdata, event.ydata

        # Check if we're in aperture adjustment mode
        if self.aperture_adjust_mode and self.selected_star_pos:
            # Move the aperture to the clicked position
            self.selected_star_pos = (x, y)
            self.star_pos_label.config(text=f"Star at ({x:.1f}, {y:.1f})")

            # Auto-center zoom on new aperture position (like sequential tracking)
            if self.zoom_active:
                # Calculate zoom size proportional to outermost annulus radius
                outer_radius = self.aperture_params['outer_annulus']
                zoom_size = max(30, min(200, outer_radius * 3))

                # Center the view on the new aperture position
                self.ax.set_xlim(x - zoom_size, x + zoom_size)
                self.ax.set_ylim(y - zoom_size, y + zoom_size)

                self.log_status(f"Aperture adjusted and zoom centered at ({x:.1f}, {y:.1f})")
            else:
                self.log_status(f"Aperture position adjusted to ({x:.1f}, {y:.1f})")

            self.display_image(show_aperture=True)
            return

        # Normal star selection mode - prioritize user's exact click intent
        # Always use the exact click position for most precise control
        self.selected_star_pos = (x, y)
        self.star_pos_label.config(text=f"Star at ({x:.1f}, {y:.1f})")
        self.display_image(show_aperture=True)
        self.refresh_button.config(state=tk.NORMAL)  # Enable refresh button
        self.log_status(f"Aperture positioned at exact click: ({x:.1f}, {y:.1f})")

    def find_nearest_star_old_unused(self, x, y, search_radius=20):
        """Find the nearest star centroid to the clicked position"""
        if self.current_image_data is None:
            self.logger.warning("find_nearest_star called but no image data available")
            return None

        # Use grayscale data for star detection
        if hasattr(self, 'current_image_grayscale') and self.current_image_grayscale is not None:
            detection_data = self.current_image_grayscale
            self.logger.debug("Using grayscale data for star detection")
        else:
            detection_data = self.current_image_data
            self.logger.debug("Using original data for star detection")

        try:
            self.logger.debug(f"Searching for star near clicked position ({x:.1f}, {y:.1f})")

            # Create a cutout around the clicked position
            x_int, y_int = int(x), int(y)
            x_min = max(0, x_int - search_radius)
            x_max = min(detection_data.shape[1], x_int + search_radius)
            y_min = max(0, y_int - search_radius)
            y_max = min(detection_data.shape[0], y_int + search_radius)

            self.logger.debug(f"Cutout region: x[{x_min}:{x_max}], y[{y_min}:{y_max}]")
            cutout = detection_data[y_min:y_max, x_min:x_max]

            # Find stars in the cutout - try multiple approaches
            mean, median, std = sigma_clipped_stats(cutout, sigma=3.0)
            self.logger.debug(f"Cutout stats: mean={mean:.1f}, median={median:.1f}, std={std:.1f}")
            self.logger.debug(f"Cutout data range: {np.min(cutout):.1f} to {np.max(cutout):.1f}")

            # Enhanced star detection with multiple methods

            # Method 1: DAOStarFinder with multiple parameters
            user_threshold = median + self.sensitivity_var.get() * std
            thresholds = [user_threshold, median + 1.5 * std, median + 1 * std, median + 0.5 * std]
            thresholds = sorted(list(set(thresholds)), reverse=True)

            # Try different FWHM values as well
            fwhm_values = [3.0, 2.0, 4.0, 1.5]

            for fwhm in fwhm_values:
                for i, threshold in enumerate(thresholds):
                    try:
                        self.logger.debug(f"DAOStarFinder: FWHM={fwhm}, threshold={threshold:.1f}")
                        daofind = DAOStarFinder(fwhm=fwhm, threshold=threshold)
                        sources = daofind(cutout)

                        if sources and len(sources) > 0:
                            self.logger.debug(f"Found {len(sources)} sources")

                            # Find the closest source to click position
                            distances = []
                            for source in sources:
                                src_x = source['xcentroid'] + x_min
                                src_y = source['ycentroid'] + y_min
                                dist = np.sqrt((src_x - x)**2 + (src_y - y)**2)
                                distances.append((dist, src_x, src_y))
                                self.logger.debug(f"Source at ({src_x:.1f}, {src_y:.1f}), distance {dist:.1f}")

                            distances.sort()
                            closest_dist, closest_x, closest_y = distances[0]

                            if closest_dist < search_radius:
                                self.logger.info(f"DAOStarFinder success: ({closest_x:.1f}, {closest_y:.1f}), distance {closest_dist:.1f}")
                                return (closest_x, closest_y)
                    except Exception as e:
                        self.logger.debug(f"DAOStarFinder failed with FWHM={fwhm}, threshold={threshold:.1f}: {e}")
                        continue

            # Method 2: Local maximum detection
            self.logger.debug("Trying local maximum detection")
            try:
                from scipy.ndimage import maximum_filter
                # Apply maximum filter to find local maxima
                max_filtered = maximum_filter(cutout, size=5)
                maxima = (cutout == max_filtered) & (cutout > median + 1.0 * std)

                if np.any(maxima):
                    # Get coordinates of maxima
                    max_coords = np.where(maxima)
                    max_values = cutout[max_coords]

                    # Find closest maximum to click position
                    distances = []
                    for i in range(len(max_coords[0])):
                        max_y_local, max_x_local = max_coords[0][i], max_coords[1][i]
                        max_x_global = max_x_local + x_min
                        max_y_global = max_y_local + y_min
                        dist = np.sqrt((max_x_global - x)**2 + (max_y_global - y)**2)
                        distances.append((dist, max_x_global, max_y_global, max_values[i]))

                    distances.sort()
                    closest_dist, closest_x, closest_y, intensity = distances[0]

                    if closest_dist < search_radius:
                        self.logger.info(f"Local maximum detection: ({closest_x:.1f}, {closest_y:.1f}), intensity={intensity:.1f}")
                        return (closest_x, closest_y)
            except ImportError:
                self.logger.debug("scipy not available for local maximum detection")
            except Exception as e:
                self.logger.debug(f"Local maximum detection failed: {e}")

            # Method 3: Simple brightest pixel
            self.logger.debug("Using brightest pixel fallback")
            max_y, max_x = np.unravel_index(np.argmax(cutout), cutout.shape)
            fallback_x = max_x + x_min
            fallback_y = max_y + y_min
            fallback_dist = np.sqrt((fallback_x - x)**2 + (fallback_y - y)**2)

            if fallback_dist < search_radius:
                self.logger.info(f"Brightest pixel: ({fallback_x:.1f}, {fallback_y:.1f}), distance {fallback_dist:.1f}")
                return (fallback_x, fallback_y)
            else:
                self.logger.debug(f"Brightest pixel too far: {fallback_dist:.1f} > {search_radius}")

            # Method 4: Final fallback - use click position exactly as user intended
            self.logger.debug(f"All detection methods failed - using exact click position ({x:.1f}, {y:.1f})")
            return (x, y)

        except Exception as e:
            self.logger.error(f"Error finding star: {e}")
            self.log_status(f"Error finding star: {e}")

        return None

    def draw_aperture_circles(self):
        """Draw aperture circles on the image"""
        if not self.selected_star_pos:
            return

        x, y = self.selected_star_pos

        # Update aperture parameters from GUI
        self.aperture_params['inner_radius'] = self.inner_radius_var.get()
        self.aperture_params['inner_annulus'] = self.inner_annulus_var.get()
        self.aperture_params['outer_annulus'] = self.outer_annulus_var.get()

        # Draw circles
        circle1 = Circle((x, y), self.aperture_params['inner_radius'],
                        fill=False, color='red', linewidth=2, label='Star Aperture')
        circle2 = Circle((x, y), self.aperture_params['inner_annulus'],
                        fill=False, color='yellow', linewidth=2, label='Inner Sky')
        circle3 = Circle((x, y), self.aperture_params['outer_annulus'],
                        fill=False, color='green', linewidth=2, label='Outer Sky')

        self.ax.add_patch(circle1)
        self.ax.add_patch(circle2)
        self.ax.add_patch(circle3)

        # Add legend
        self.ax.legend(loc='upper right')

        

    def update_aperture_preview(self, param, value):
        """Update aperture preview when sliders change"""
        self.aperture_params[param] = float(value)
        if self.selected_star_pos:
            self.display_image(show_aperture=True)

    def toggle_zoom(self):
        """Toggle zoom mode with proportional sizing based on outermost annulus"""
        if not self.selected_star_pos:
            messagebox.showwarning("No Star", "Please select a star first")
            return

        self.zoom_active = not self.zoom_active

        if self.zoom_active:
            # Calculate zoom size proportional to outermost annulus radius
            x, y = self.selected_star_pos
            outer_radius = self.aperture_params['outer_annulus']
            # Zoom size is 3x the outer annulus radius, with minimum of 30px and maximum of 200px
            zoom_size = max(30, min(200, outer_radius * 3))

            self.ax.set_xlim(x - zoom_size, x + zoom_size)
            self.ax.set_ylim(y - zoom_size, y + zoom_size)
            self.log_status(f"Zoom enabled: {zoom_size*2}x{zoom_size*2}px window (3x outer annulus)")
        else:
            # Reset zoom - need to redisplay the image properly
            if self.current_image_data is not None:
                # Use proper image dimensions
                height, width = self.current_image_data.shape[:2]
                self.ax.set_xlim(0, width)
                self.ax.set_ylim(0, height)
                # Redisplay the image to ensure it shows properly
                self.display_image(show_aperture=True)
            self.log_status("Zoom disabled - full image view restored")

        # Only draw canvas if not calling display_image (which draws itself)
        if self.zoom_active:
            self.canvas.draw()

    def toggle_aperture_adjust(self):
        """Toggle aperture adjustment mode"""
        if not self.selected_star_pos:
            messagebox.showwarning("No Star", "Please select a star first")
            return

        self.aperture_adjust_mode = not self.aperture_adjust_mode

        if self.aperture_adjust_mode:
            # Adjust mode no longer exists - refresh is always available
            self.log_status("Aperture adjustment mode enabled - click to reposition")

            # Auto-center zoom on current star position (like sequential tracking)
            if self.selected_star_pos:
                star_x, star_y = self.selected_star_pos

                # Calculate zoom size proportional to outermost annulus radius (same as toggle_zoom)
                outer_radius = self.aperture_params['outer_annulus']
                zoom_size = max(30, min(200, outer_radius * 3))

                # Center the view on the current star position and enable zoom
                self.zoom_active = True
                self.ax.set_xlim(star_x - zoom_size, star_x + zoom_size)
                self.ax.set_ylim(star_y - zoom_size, star_y + zoom_size)

                self.log_status(f"Auto-centered zoom on aperture at ({star_x:.1f}, {star_y:.1f}) with {zoom_size*2}px window")

            # Update title to show adjustment mode
            if hasattr(self, 'current_image_rgb') and self.current_image_rgb is not None:
                title = f"FITS RGB Image - ADJUST MODE: Click to reposition aperture"
            else:
                title = f"FITS Image - ADJUST MODE: Click to reposition aperture"
            self.ax.set_title(title)
            self.canvas.draw()
        else:
            # Adjust mode no longer exists - refresh is always available
            self.log_status("Aperture adjustment mode disabled")
            # Restore normal title
            self.display_image(show_aperture=True)


    def go_back_frame(self):
        """Go back one frame - works during preselection pause"""
        if self.current_frame_index <= 0:
            self.log_status("Already at the first frame")
            return

        # Only allow navigation during preselection pause or when completely stopped
        if self.preselection_mode and not getattr(self, 'preselection_paused', False):
            self.log_status("Navigation only available when paused")
            return

        # Navigate to previous frame
        self.current_frame_index -= 1

        if self.preselection_mode and getattr(self, 'preselection_paused', False):
            # During preselection pause - load frame without auto-skip logic
            self.load_frame_for_preselection_pause(self.current_frame_index)
        elif hasattr(self, 'fits_files') and self.fits_files:
            # When stopped - allow navigation for review
            self.load_frame_for_pause_navigation(self.current_frame_index)

        self.log_status(f"Navigated to frame {self.current_frame_index + 1} of {len(self.fits_files)}")

    def refresh_display(self):
        """Refresh the current image display"""
        if hasattr(self, 'current_image_data') and self.current_image_data is not None:
            self.display_image(show_aperture=self.selected_star_pos is not None)
            self.log_status("Display refreshed")
        else:
            self.log_status("No image loaded to refresh")

    def update_search_radius_display(self, value):
        """Update the search radius display label"""
        radius = int(float(value))
        self.search_radius_label.config(text=f"{radius}px")
        self.log_status(f"Auto-tracking search radius: {radius} pixels")


    def skip_frame(self):
        """Navigate forward to next frame during preselection pause"""
        # Check bounds
        if self.current_frame_index >= len(self.fits_files) - 1:
            self.log_status("Already at the last frame")
            return

        # Only allow navigation during preselection pause or when completely stopped
        if self.preselection_mode and not getattr(self, 'preselection_paused', False):
            self.log_status("Navigation only available when paused")
            return

        # Navigate to next frame
        self.current_frame_index += 1

        if self.preselection_mode and getattr(self, 'preselection_paused', False):
            # During preselection pause - load frame without auto-skip logic
            self.load_frame_for_preselection_pause(self.current_frame_index)
        elif hasattr(self, 'fits_files') and self.fits_files:
            # When stopped - allow navigation for review
            self.load_frame_for_pause_navigation(self.current_frame_index)

        self.log_status(f"Navigated to frame {self.current_frame_index + 1} of {len(self.fits_files)}")

    def update_position_after_navigation(self, x, y):
        """Update position data during pause navigation and mark frames for reprocessing"""
        if self.paused:
            # During pause - update the current frame position and mark for reprocessing
            if hasattr(self, 'paused_tracking_mode'):
                if self.paused_tracking_mode == 'preselection':
                    # Ensure the preselected_positions list is long enough
                    while len(self.preselected_positions) <= self.current_frame_index:
                        self.preselected_positions.append(None)

                    old_pos = self.preselected_positions[self.current_frame_index]
                    self.preselected_positions[self.current_frame_index] = (x, y)

                    # Mark all frames from this point forward for reprocessing
                    self.mark_frames_for_reprocessing_from(self.current_frame_index)

                elif self.paused_tracking_mode == 'sequential':
                    # Ensure the frame_positions list is long enough
                    while len(self.frame_positions) <= self.current_frame_index:
                        self.frame_positions.append(None)

                    old_pos = self.frame_positions[self.current_frame_index] if self.current_frame_index < len(self.frame_positions) else None
                    self.frame_positions[self.current_frame_index] = (x, y)

                    # Mark all frames from this point forward for reprocessing
                    self.mark_frames_for_reprocessing_from(self.current_frame_index)

                if old_pos:
                    self.log_status(f"Updated position for frame {self.current_frame_index + 1}: {old_pos} → ({x:.1f}, {y:.1f})")
                else:
                    self.log_status(f"Set position for frame {self.current_frame_index + 1}: ({x:.1f}, {y:.1f})")

                self.log_status(f"Frames {self.current_frame_index + 1} onwards marked for reprocessing")

    def mark_frames_for_reprocessing_from(self, start_frame):
        """Mark frames from start_frame onwards for reprocessing when resumed"""
        if hasattr(self, 'paused_tracking_mode'):
            if self.paused_tracking_mode == 'preselection':
                # Remove preselected positions from start_frame+1 onwards
                while len(self.preselected_positions) > start_frame + 1:
                    self.preselected_positions.pop()

            elif self.paused_tracking_mode == 'sequential':
                # Remove frame positions and results from start_frame+1 onwards
                while len(self.frame_positions) > start_frame + 1:
                    self.frame_positions.pop()
                while len(self.photometry_results) > start_frame + 1:
                    self.photometry_results.pop()

    def validate_inputs(self):
        """Validate all inputs before starting processing"""
        if not self.fits_files:
            messagebox.showerror("No Files", "Please select a FITS folder first")
            return False

        if not self.selected_star_pos:
            messagebox.showerror("No Star", "Please select a star first")
            return False

        if not self.star_name_var.get().strip():
            messagebox.showerror("No Star Name", "Please enter a name for the star")
            return False

        self.star_name = self.star_name_var.get().strip()
        return True

    def process_photometry(self):
        """Main photometry processing loop"""
        try:
            self.log_status(f"Starting photometry for star: {self.star_name}")
            self.log_status(f"Processing {len(self.fits_files)} images...")

            current_star_pos = self.selected_star_pos

            for i, fits_file in enumerate(self.fits_files):
                if self.stop_processing:
                    self.log_status("Processing stopped by user")
                    break

                # Update progress
                progress = (i / len(self.fits_files)) * 100
                self.progress_var.set(progress)

                # Process single image
                result = self.process_single_image(fits_file, current_star_pos, i)

                if result is None:
                    self.log_status(f"Lost tracking at image {i+1}: {os.path.basename(fits_file)}")
                    messagebox.showerror("Tracking Lost",
                                       f"Lost star tracking at image {i+1}. Please check and reselect.")
                    break

                self.photometry_results.append(result)
                current_star_pos = result['tracked_position']

                if i % 10 == 0:  # Log every 10 images
                    self.log_status(f"Processed {i+1}/{len(self.fits_files)} images")

            self.progress_var.set(100)
            self.log_status(f"Photometry completed! Processed {len(self.photometry_results)} images")

            # Enable result buttons when processing completes successfully
            self.enable_result_buttons()

        except Exception as e:
            self.log_status(f"Error during processing: {e}")
            messagebox.showerror("Processing Error", str(e))
        finally:
            self.processing = False
            self.stop_button.config(state=tk.DISABLED)

    def enable_result_buttons(self):
        """Enable save and visualization buttons when results are available"""
        if len(self.photometry_results) > 0:
            if hasattr(self, 'save_csv_button'):
                self.save_csv_button.config(state=tk.NORMAL)
            if hasattr(self, 'quick_viz_button'):
                self.quick_viz_button.config(state=tk.NORMAL)
            if hasattr(self, 'viz_update_button'):
                self.viz_update_button.config(state=tk.NORMAL)

    def disable_result_buttons(self):
        """Disable save and visualization buttons when no results available"""
        if hasattr(self, 'save_csv_button'):
            self.save_csv_button.config(state=tk.DISABLED)
        if hasattr(self, 'quick_viz_button'):
            self.quick_viz_button.config(state=tk.DISABLED)
        if hasattr(self, 'viz_update_button'):
            self.viz_update_button.config(state=tk.DISABLED)

    def process_single_image(self, fits_file, expected_pos, image_index):
        """Process photometry for a single image - supports both RGB and grayscale"""
        try:
            filename = os.path.basename(fits_file)
            self.logger.debug(f"Processing image {image_index+1}: {filename}")

            with fits.open(fits_file) as hdul:
                original_data = hdul[0].data
                header = hdul[0].header

                # Check if we have RGB data
                is_rgb = len(original_data.shape) == 3 and original_data.shape[0] == 3

                if is_rgb:
                    self.logger.debug(f"Processing RGB image: {filename}")
                    # Avoid copying large RGB data unless necessary - use view when possible
                    rgb_data = original_data  # Use direct reference for batch processing
                    # Create grayscale for tracking (optimized calculation)
                    tracking_data = np.mean(original_data, axis=0, dtype=np.float32)  # Faster with explicit dtype
                else:
                    self.logger.debug(f"Processing grayscale image: {filename}")
                    rgb_data = None
                    tracking_data = original_data

            # Handle different processing modes
            if self.batch_processing_mode:
                # Batch processing mode - use pre-selected positions directly
                tracked_pos = expected_pos
                movement = 0.0 if image_index == 0 else np.sqrt((tracked_pos[0] - self.preselected_positions[0][0])**2 + (tracked_pos[1] - self.preselected_positions[0][1])**2)
                self.logger.debug(f"Batch mode: using pre-selected position ({tracked_pos[0]:.1f}, {tracked_pos[1]:.1f})")
            elif image_index == 0:
                # First image - use the selected position directly
                tracked_pos = expected_pos
                movement = 0.0
                self.logger.debug(f"First image: using selected position ({tracked_pos[0]:.1f}, {tracked_pos[1]:.1f})")
            else:
                # Check if star tracking is enabled
                if self.tracking_enabled_var.get():
                    # Track star position using grayscale/tracking data with user-configured radius
                    search_radius = self.search_radius_var.get()
                    self.logger.debug(f"Tracking star from expected position ({expected_pos[0]:.1f}, {expected_pos[1]:.1f}), search radius {search_radius}px")
                    tracked_pos = self.track_star_position(tracking_data, expected_pos, search_radius)
                    if tracked_pos is None:
                        self.logger.warning(f"Failed to track star in {filename}")
                        # Allow user to manually reposition
                        tracked_pos = self.manual_star_reposition(original_data if not is_rgb else rgb_data,
                                                                filename, image_index, expected_pos)
                        if tracked_pos is None:
                            return None

                    movement = np.sqrt((tracked_pos[0] - expected_pos[0])**2 + (tracked_pos[1] - expected_pos[1])**2)
                    self.logger.debug(f"Star tracked to ({tracked_pos[0]:.1f}, {tracked_pos[1]:.1f}), moved {movement:.1f} pixels")
                else:
                    # Star tracking disabled - use previous position or ask user
                    self.logger.debug(f"Star tracking disabled - using manual positioning")
                    tracked_pos = self.manual_star_reposition(original_data if not is_rgb else rgb_data,
                                                            filename, image_index, expected_pos)
                    if tracked_pos is None:
                        return None
                    movement = np.sqrt((tracked_pos[0] - expected_pos[0])**2 + (tracked_pos[1] - expected_pos[1])**2)

            # Update GUI display to show current processing image with aperture
            self.update_processing_display(original_data if not is_rgb else rgb_data,
                                         tracked_pos, filename, image_index)

            # Perform photometry
            if is_rgb:
                # RGB photometry: measure each channel + grayscale
                phot_results = self.perform_rgb_photometry(rgb_data, tracking_data, tracked_pos)
                self.logger.debug(f"RGB photometry completed: R={phot_results['r_flux_corrected']:.1f}, "
                                f"G={phot_results['g_flux_corrected']:.1f}, B={phot_results['b_flux_corrected']:.1f}, "
                                f"Gray={phot_results['gray_flux_corrected']:.1f}")
            else:
                # Standard grayscale photometry
                phot_results = self.perform_aperture_photometry(tracking_data, tracked_pos)
                # Add prefix to distinguish from RGB results
                phot_results = {f"gray_{k}" if not k.startswith(('x_', 'y_', 'aperture_', 'sky_')) else k: v
                              for k, v in phot_results.items()}
                self.logger.debug(f"Grayscale photometry completed: flux={phot_results['gray_star_flux_corrected']:.1f}")

            # Extract metadata from FITS header
            metadata = self.extract_fits_metadata(header, fits_file)

            # Combine results
            result = {
                'image_index': image_index,
                'filename': filename,
                'star_name': self.star_name,
                'tracked_position': tracked_pos,
                'movement_pixels': movement,
                'is_rgb': is_rgb,
                **phot_results,
                **metadata
            }

            return result

        except Exception as e:
            self.logger.error(f"Error processing {fits_file}: {e}")
            self.log_status(f"Error processing {os.path.basename(fits_file)}: {e}")
            return None

    def track_star_position(self, image_data, expected_pos, search_radius=25):
        """
        IMPROVED ROBUST STAR TRACKING with adaptive threshold and multiple methods

        Uses momentum prediction, adaptive search radius, and fallback methods
        """
        try:
            x, y = expected_pos

            # STEP 1: Use momentum prediction if we have tracking history
            predicted_pos = self._predict_position_with_momentum(expected_pos)
            if predicted_pos != expected_pos:
                search_x, search_y = predicted_pos
            else:
                search_x, search_y = x, y

            # STEP 2: Calculate adaptive search radius
            adaptive_radius = self._calculate_adaptive_search_radius(search_radius)

            # STEP 3: Extract search region
            x_int, y_int = int(search_x), int(search_y)
            x_min = max(0, x_int - adaptive_radius)
            x_max = min(image_data.shape[1], x_int + adaptive_radius)
            y_min = max(0, y_int - adaptive_radius)
            y_max = min(image_data.shape[0], y_int + adaptive_radius)

            cutout = image_data[y_min:y_max, x_min:x_max]

            if cutout.size == 0:
                return expected_pos

            # STEP 4: Calculate adaptive threshold
            threshold, peak_brightness = self._calculate_adaptive_threshold(cutout)

            # STEP 5: Try simple center-of-mass first (most reliable)
            try:
                from photutils.centroids import centroid_com

                # Threshold the cutout
                star_region = np.maximum(cutout - threshold, 0)

                if np.sum(star_region) > 0:
                    x_cen, y_cen = centroid_com(star_region)

                    if not (np.isnan(x_cen) or np.isnan(y_cen)):
                        tracked_x = x_cen + x_min
                        tracked_y = y_cen + y_min

                        # Basic validation: within search radius and image bounds
                        distance = np.sqrt((tracked_x - expected_pos[0])**2 + (tracked_y - expected_pos[1])**2)
                        if (distance <= adaptive_radius * 1.5 and
                            5 < tracked_x < image_data.shape[1] - 5 and
                            5 < tracked_y < image_data.shape[0] - 5):

                            self._update_tracking_history((tracked_x, tracked_y), 0.8)
                            self.logger.debug(f"Tracked star: ({tracked_x:.1f}, {tracked_y:.1f}), moved {distance:.1f}px")
                            return (tracked_x, tracked_y)
            except Exception as e:
                self.logger.debug(f"Center-of-mass failed: {e}")

            # STEP 6: Fallback - try peak finding
            try:
                # Find brightest pixel in cutout
                peak_y, peak_x = np.unravel_index(np.argmax(cutout), cutout.shape)

                # Refine with weighted centroid around peak
                window_size = 5
                y_start = max(0, peak_y - window_size)
                y_end = min(cutout.shape[0], peak_y + window_size + 1)
                x_start = max(0, peak_x - window_size)
                x_end = min(cutout.shape[1], peak_x + window_size + 1)

                window = cutout[y_start:y_end, x_start:x_end]
                window_weights = np.maximum(window - threshold, 0)

                if np.sum(window_weights) > 0:
                    y_coords, x_coords = np.mgrid[0:window.shape[0], 0:window.shape[1]]
                    cx = np.sum(x_coords * window_weights) / np.sum(window_weights)
                    cy = np.sum(y_coords * window_weights) / np.sum(window_weights)

                    tracked_x = cx + x_start + x_min
                    tracked_y = cy + y_start + y_min

                    distance = np.sqrt((tracked_x - expected_pos[0])**2 + (tracked_y - expected_pos[1])**2)
                    if (distance <= adaptive_radius * 1.5 and
                        5 < tracked_x < image_data.shape[1] - 5 and
                        5 < tracked_y < image_data.shape[0] - 5):

                        self._update_tracking_history((tracked_x, tracked_y), 0.6)
                        self.logger.debug(f"Tracked via peak: ({tracked_x:.1f}, {tracked_y:.1f}), moved {distance:.1f}px")
                        return (tracked_x, tracked_y)
            except Exception as e:
                self.logger.debug(f"Peak finding failed: {e}")

            # STEP 7: Use momentum prediction if reasonable
            if predicted_pos != expected_pos:
                pred_distance = np.sqrt((predicted_pos[0] - expected_pos[0])**2 +
                                      (predicted_pos[1] - expected_pos[1])**2)
                if pred_distance <= adaptive_radius:
                    self._update_tracking_history(predicted_pos, 0.3)
                    self.logger.debug(f"Using momentum prediction: ({predicted_pos[0]:.1f}, {predicted_pos[1]:.1f})")
                    return predicted_pos

            # STEP 8: Final fallback - use expected position
            self._update_tracking_history(expected_pos, 0.1)
            self.logger.debug(f"Tracking failed - using expected position: ({x:.1f}, {y:.1f})")
            return expected_pos

        except Exception as e:
            self.logger.error(f"Error in tracking: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return expected_pos

    # ============================================================================
    # ADVANCED TRACKING HELPER METHODS
    # ============================================================================

    def _predict_position_with_momentum(self, expected_pos):
        """Predict next position using velocity history (Kalman-style prediction)"""
        if len(self.position_history) < 2:
            return expected_pos

        # Calculate weighted average velocity from recent history
        velocities = []
        weights = []
        for i in range(len(self.velocity_history)):
            # More recent velocities get higher weight
            weight = (i + 1) / len(self.velocity_history)
            velocities.append(self.velocity_history[i])
            weights.append(weight)

        if velocities:
            avg_vx = sum(vx * w for (vx, vy), w in zip(velocities, weights)) / sum(weights)
            avg_vy = sum(vy * w for (vx, vy), w in zip(velocities, weights)) / sum(weights)

            # Predict next position
            predicted_x = expected_pos[0] + avg_vx
            predicted_y = expected_pos[1] + avg_vy

            return (predicted_x, predicted_y)

        return expected_pos

    def _calculate_adaptive_search_radius(self, base_radius):
        """Calculate adaptive search radius based on recent position variance"""
        if len(self.position_history) < 3:
            return base_radius

        # Calculate standard deviation of recent positions
        recent_positions = self.position_history[-5:]  # Last 5 frames
        x_positions = [pos[0] for pos in recent_positions]
        y_positions = [pos[1] for pos in recent_positions]

        x_std = np.std(x_positions)
        y_std = np.std(y_positions)
        position_variance = np.sqrt(x_std**2 + y_std**2)

        # Adaptive radius: base + 2*variance (covers ~95% of normal distribution)
        adaptive_radius = int(base_radius + 2 * position_variance)

        # Clamp to reasonable bounds
        adaptive_radius = max(base_radius, min(adaptive_radius, base_radius * 2))

        return adaptive_radius

    def _calculate_adaptive_threshold(self, cutout):
        """Calculate adaptive threshold using robust statistics"""
        # Use sigma-clipped statistics to remove outliers
        try:
            from astropy.stats import sigma_clipped_stats
            mean, median, std = sigma_clipped_stats(cutout, sigma=3.0)
        except:
            mean = np.mean(cutout)
            median = np.median(cutout)
            std = np.std(cutout)

        # Find peak brightness
        peak_brightness = np.max(cutout)

        # Adaptive threshold: median + N*std, where N adapts to peak brightness
        # Brighter stars use lower threshold multiplier
        brightness_ratio = (peak_brightness - median) / (std + 1e-6)
        if brightness_ratio > 10:
            threshold_multiplier = 2.0  # Bright star - use lower threshold
        elif brightness_ratio > 5:
            threshold_multiplier = 2.5
        else:
            threshold_multiplier = 3.0  # Faint star - use higher threshold

        threshold = median + threshold_multiplier * std

        return threshold, peak_brightness

    def _method_iterative_gaussian_centroid(self, cutout, x_min, y_min, threshold, iterations=3):
        """Iterative Gaussian centroid - refines position by re-centering"""
        try:
            from photutils.centroids import centroid_com

            # Start with center of cutout
            cy, cx = cutout.shape[0] / 2, cutout.shape[1] / 2

            for _ in range(iterations):
                # Extract small window around current estimate
                window_size = 7
                y_start = max(0, int(cy) - window_size // 2)
                y_end = min(cutout.shape[0], int(cy) + window_size // 2 + 1)
                x_start = max(0, int(cx) - window_size // 2)
                x_end = min(cutout.shape[1], int(cx) + window_size // 2 + 1)

                window = cutout[y_start:y_end, x_start:x_end]

                if window.size == 0:
                    break

                # Calculate centroid in window
                x_cen, y_cen = centroid_com(window)

                if np.isnan(x_cen) or np.isnan(y_cen):
                    break

                # Update position
                cx = x_start + x_cen
                cy = y_start + y_cen

            if not (np.isnan(cx) or np.isnan(cy)):
                tracked_x = cx + x_min
                tracked_y = cy + y_min

                # Confidence based on peak brightness in window
                confidence = self._calculate_confidence(cutout, cx, cy, threshold)
                return (tracked_x, tracked_y, confidence)

        except Exception as e:
            self.logger.debug(f"Iterative Gaussian failed: {e}")

        return None

    def _method_gaussian_2d_fit(self, cutout, x_min, y_min):
        """2D Gaussian fitting centroid"""
        try:
            from photutils.centroids import centroid_2dg

            x_cen, y_cen = centroid_2dg(cutout)

            if not (np.isnan(x_cen) or np.isnan(y_cen)):
                tracked_x = x_cen + x_min
                tracked_y = y_cen + y_min

                # Confidence from Gaussian fit quality
                confidence = 0.8  # Default confidence for successful fit
                return (tracked_x, tracked_y, confidence)

        except Exception as e:
            self.logger.debug(f"2D Gaussian fit failed: {e}")

        return None

    def _method_moment_based(self, cutout, x_min, y_min, threshold):
        """Moment-based centroid with outlier rejection"""
        try:
            # Threshold the image
            star_pixels = cutout > threshold

            if not np.any(star_pixels):
                return None

            # Calculate moments with outlier rejection
            # Only use pixels above threshold
            weights = np.maximum(cutout - threshold, 0) * star_pixels

            if np.sum(weights) == 0:
                return None

            # Calculate weighted centroid
            y_coords, x_coords = np.mgrid[0:cutout.shape[0], 0:cutout.shape[1]]
            cx = np.sum(x_coords * weights) / np.sum(weights)
            cy = np.sum(y_coords * weights) / np.sum(weights)

            tracked_x = cx + x_min
            tracked_y = cy + y_min

            # Confidence from compactness (star should be compact)
            star_size = np.sum(star_pixels)
            confidence = min(1.0, 50.0 / (star_size + 10))  # Smaller is better

            return (tracked_x, tracked_y, confidence)

        except Exception as e:
            self.logger.debug(f"Moment-based failed: {e}")

        return None

    def _method_connected_components(self, cutout, x_min, y_min, threshold, search_x, search_y):
        """Connected component analysis - isolates the target star"""
        try:
            from scipy.ndimage import label, center_of_mass

            # Create binary mask
            star_mask = cutout > threshold
            labeled_array, num_features = label(star_mask)

            if num_features == 0:
                return None

            # Find component closest to search position
            best_component = 1
            min_distance = float('inf')

            for i in range(1, num_features + 1):
                component_mask = (labeled_array == i)
                component_size = np.sum(component_mask)

                # Skip very small or very large components
                if component_size < 4 or component_size > 500:
                    continue

                cy, cx = center_of_mass(component_mask)
                abs_x = cx + x_min
                abs_y = cy + y_min
                dist = np.sqrt((abs_x - search_x)**2 + (abs_y - search_y)**2)

                if dist < min_distance:
                    min_distance = dist
                    best_component = i

            # Calculate intensity-weighted center for best component
            component_mask = (labeled_array == best_component)
            if np.sum(component_mask) >= 4:
                star_region = cutout * component_mask
                cy, cx = center_of_mass(star_region)

                tracked_x = cx + x_min
                tracked_y = cy + y_min

                # Confidence from distance to search center
                confidence = max(0.0, 1.0 - min_distance / 20.0)

                return (tracked_x, tracked_y, confidence)

        except Exception as e:
            self.logger.debug(f"Connected components failed: {e}")

        return None

    def _method_peak_weighted_centroid(self, cutout, x_min, y_min, threshold, peak_brightness):
        """Peak-weighted centroid - emphasizes brightest pixels"""
        try:
            # Use squared intensities to emphasize peak
            weights = np.maximum(cutout - threshold, 0)**1.5

            if np.sum(weights) == 0:
                return None

            y_coords, x_coords = np.mgrid[0:cutout.shape[0], 0:cutout.shape[1]]
            cx = np.sum(x_coords * weights) / np.sum(weights)
            cy = np.sum(y_coords * weights) / np.sum(weights)

            tracked_x = cx + x_min
            tracked_y = cy + y_min

            # Confidence from peak brightness
            confidence = min(1.0, (peak_brightness - threshold) / (peak_brightness + 1))

            return (tracked_x, tracked_y, confidence)

        except Exception as e:
            self.logger.debug(f"Peak-weighted failed: {e}")

        return None

    def _calculate_confidence(self, cutout, cx, cy, threshold):
        """Calculate confidence score for a centroid position"""
        try:
            # Extract small window around centroid
            window_size = 3
            y_start = max(0, int(cy) - window_size)
            y_end = min(cutout.shape[0], int(cy) + window_size + 1)
            x_start = max(0, int(cx) - window_size)
            x_end = min(cutout.shape[1], int(cx) + window_size + 1)

            window = cutout[y_start:y_end, x_start:x_end]

            if window.size == 0:
                return 0.0

            # Confidence from peak-to-threshold ratio
            peak = np.max(window)
            confidence = min(1.0, (peak - threshold) / (threshold + 1))

            return max(0.0, confidence)

        except:
            return 0.5

    def _select_best_candidate(self, candidates, search_x, search_y, search_radius):
        """Select best candidate from multiple methods using consensus"""
        if not candidates:
            return None

        # Calculate consensus position (median of all candidates)
        x_positions = [x for (_, x, y, _) in candidates]
        y_positions = [y for (_, x, y, _) in candidates]
        consensus_x = np.median(x_positions)
        consensus_y = np.median(y_positions)

        # Score each candidate based on:
        # 1. Confidence score from method
        # 2. Distance to consensus
        # 3. Distance to search center
        scored_candidates = []

        for method, x, y, confidence in candidates:
            # Distance to consensus (should be small for good candidates)
            consensus_dist = np.sqrt((x - consensus_x)**2 + (y - consensus_y)**2)
            consensus_score = max(0.0, 1.0 - consensus_dist / 5.0)  # Penalty for outliers

            # Distance to search center (should be within search radius)
            search_dist = np.sqrt((x - search_x)**2 + (y - search_y)**2)
            search_score = max(0.0, 1.0 - search_dist / search_radius)

            # Combined score
            total_score = confidence * 0.5 + consensus_score * 0.3 + search_score * 0.2

            scored_candidates.append((total_score, method, x, y, confidence))

        # Sort by score (descending)
        scored_candidates.sort(reverse=True, key=lambda x: x[0])

        # Return best candidate
        if scored_candidates:
            _, method, x, y, confidence = scored_candidates[0]
            self.logger.debug(f"Best candidate: {method} at ({x:.1f}, {y:.1f}), "
                            f"score={scored_candidates[0][0]:.2f}")
            return (method, x, y, confidence)

        return None

    def _validate_tracked_position(self, image_data, tracked_pos, expected_pos, threshold, search_radius):
        """Validate that tracked position is actually a star"""
        try:
            x, y = tracked_pos

            # Check 1: Within search radius
            distance = np.sqrt((x - expected_pos[0])**2 + (y - expected_pos[1])**2)
            if distance > search_radius:
                self.logger.debug(f"Validation failed: distance {distance:.1f} > radius {search_radius}")
                return False

            # Check 2: Within image bounds
            if x < 5 or y < 5 or x >= image_data.shape[1] - 5 or y >= image_data.shape[0] - 5:
                self.logger.debug(f"Validation failed: too close to edge")
                return False

            # Check 3: Local brightness check - should be brighter than surroundings
            x_int, y_int = int(x), int(y)
            window_size = 5
            y_min = max(0, y_int - window_size)
            y_max = min(image_data.shape[0], y_int + window_size + 1)
            x_min = max(0, x_int - window_size)
            x_max = min(image_data.shape[1], x_int + window_size + 1)

            window = image_data[y_min:y_max, x_min:x_max]
            center_brightness = image_data[y_int, x_int]
            median_brightness = np.median(window)

            if center_brightness < median_brightness * 1.2:
                self.logger.debug(f"Validation failed: not bright enough (center={center_brightness:.1f}, "
                                f"median={median_brightness:.1f})")
                return False

            # All checks passed
            return True

        except Exception as e:
            self.logger.debug(f"Validation error: {e}")
            return False

    def _update_tracking_history(self, position, confidence):
        """Update position and velocity history for momentum tracking"""
        try:
            # Add to position history
            self.position_history.append(position)
            self.tracking_confidence.append(confidence)

            # Calculate velocity if we have previous position
            if len(self.position_history) >= 2:
                prev_pos = self.position_history[-2]
                velocity = (position[0] - prev_pos[0], position[1] - prev_pos[1])
                self.velocity_history.append(velocity)

            # Keep only recent history
            if len(self.position_history) > self.tracking_history_size:
                self.position_history.pop(0)
                self.tracking_confidence.pop(0)

            if len(self.velocity_history) > self.tracking_history_size:
                self.velocity_history.pop(0)

        except Exception as e:
            self.logger.debug(f"Error updating tracking history: {e}")

    # ============================================================================
    # END OF ADVANCED TRACKING HELPER METHODS
    # ============================================================================

    def manual_star_reposition(self, image_data, filename, image_index, expected_pos):
        """Allow user to manually reposition star when tracking fails"""
        try:
            self.logger.info(f"Manual star repositioning required for {filename}")

            # Show the current image with aperture at expected position for user reference
            self.update_processing_display(image_data, expected_pos, filename, image_index)

            # Temporarily enable aperture adjustment mode for user interaction
            was_processing = self.processing
            self.processing = False  # Allow user interaction

            # Show dialog asking user to reposition the star
            response = messagebox.askyesno(
                "Manual Star Repositioning Required",
                f"Tracking failed for {filename} (Image {image_index + 1}).\n\n"
                f"Would you like to manually reposition the aperture?\n\n"
                f"Click 'Yes' to click on the star in the image,\n"
                f"or 'No' to stop processing."
            )

            if not response:
                self.logger.info("User chose to stop processing")
                self.processing = was_processing
                return None

            # Enable aperture adjustment mode temporarily
            self.log_status("Click on the star to reposition the aperture...")
            original_adjust_mode = self.aperture_adjust_mode
            self.aperture_adjust_mode = True

            # Store the current selected position
            original_pos = self.selected_star_pos
            self.selected_star_pos = expected_pos  # Start with expected position

            # Show instructions
            self.ax.set_title(f"MANUAL REPOSITION: Click on the star in {filename}")
            self.canvas.draw()

            # Wait for user to click (this is handled by on_image_click)
            # We'll check if the position changed after a brief pause
            start_time = time.time()
            timeout = 60  # 60 second timeout

            while (self.selected_star_pos == expected_pos or
                   (self.selected_star_pos and
                    np.sqrt((self.selected_star_pos[0] - expected_pos[0])**2 +
                           (self.selected_star_pos[1] - expected_pos[1])**2) < 1)):
                self.root.update()
                time.sleep(0.1)

                # Check timeout
                if time.time() - start_time > timeout:
                    messagebox.showwarning("Timeout", "Repositioning timed out. Stopping processing.")
                    self.aperture_adjust_mode = original_adjust_mode
                    self.selected_star_pos = original_pos
                    self.processing = was_processing
                    return None

                # Check if user stopped
                if self.stop_processing:
                    self.aperture_adjust_mode = original_adjust_mode
                    self.selected_star_pos = original_pos
                    self.processing = was_processing
                    return None

            # Get the new position
            new_pos = self.selected_star_pos

            # Restore states
            self.aperture_adjust_mode = original_adjust_mode
            self.processing = was_processing

            if new_pos and new_pos != expected_pos:
                movement = np.sqrt((new_pos[0] - expected_pos[0])**2 + (new_pos[1] - expected_pos[1])**2)
                self.logger.info(f"User repositioned star: ({new_pos[0]:.1f}, {new_pos[1]:.1f}), moved {movement:.1f}px")
                self.log_status(f"Star repositioned to ({new_pos[0]:.1f}, {new_pos[1]:.1f})")
                return new_pos
            else:
                self.logger.warning("No valid repositioning detected")
                return None

        except Exception as e:
            self.logger.error(f"Error in manual_star_reposition: {e}")
            return None

    def update_processing_display(self, image_data, star_pos, filename, image_index):
        """Update the GUI display during processing to show current image with aperture"""
        try:
            # Store current state
            original_image = self.current_image_data
            original_rgb = getattr(self, 'current_image_rgb', None)
            original_star_pos = self.selected_star_pos

            # Temporarily set processing image as current
            if len(image_data.shape) == 3 and image_data.shape[0] == 3:
                # RGB image
                self.current_image_data = image_data
                self.current_image_rgb = image_data
                is_rgb = True
            else:
                # Grayscale image
                self.current_image_data = image_data
                self.current_image_rgb = None
                is_rgb = False

            # Set current star position for aperture drawing
            self.selected_star_pos = star_pos

            # Store zoom state
            current_xlim, current_ylim = None, None
            if self.zoom_active and hasattr(self.ax, 'get_xlim'):
                current_xlim = self.ax.get_xlim()
                current_ylim = self.ax.get_ylim()

            # Clear and redraw with new image
            self.ax.clear()

            # Display the processing image
            if is_rgb:
                data = image_data.astype(np.float32)
                display_data = np.moveaxis(data, 0, -1)
                vmin, vmax = np.percentile(display_data, [0.5, 99.5])
                display_data = np.clip(display_data, vmin, vmax)
                display_data = (display_data - vmin) / (vmax - vmin)
                self.ax.imshow(display_data, origin='lower')
                title = f"Processing: {filename} (Image {image_index + 1})"
            else:
                data = image_data.astype(np.float32)
                vmin, vmax = np.percentile(data, [0.5, 99.5])
                self.ax.imshow(data, cmap='gray', origin='lower', vmin=vmin, vmax=vmax)
                title = f"Processing: {filename} (Image {image_index + 1})"

            self.ax.set_title(title)

            # Draw aperture circles at tracked position
            self.draw_aperture_circles()

            # Handle zoom during processing - center on current star position (like preselection mode)
            if self.zoom_active:
                # Calculate zoom size proportional to outermost annulus radius (same as preselection)
                outer_radius = self.aperture_params['outer_annulus']
                zoom_size = max(30, min(200, outer_radius * 3))
                
                # Center the view on the current star position to follow the aperture
                star_x, star_y = star_pos
                self.ax.set_xlim(star_x - zoom_size, star_x + zoom_size)
                self.ax.set_ylim(star_y - zoom_size, star_y + zoom_size)
                
                self.logger.debug(f"Display centered on aperture at ({star_x:.1f}, {star_y:.1f}) with {zoom_size*2}px window")

            # Force display update
            self.canvas.draw()
            self.canvas.flush_events()
            self.root.update()

            # Restore original state
            self.current_image_data = original_image
            if original_rgb is not None:
                self.current_image_rgb = original_rgb
            self.selected_star_pos = original_star_pos

        except Exception as e:
            self.logger.error(f"Error updating processing display: {e}")

    def perform_aperture_photometry(self, image_data, star_pos):
        """Perform aperture photometry using professional methodology:
        1. Use sigma-clipped median for robust sky background estimation
        2. Handle cases where no sky subtraction is desired (inner_annulus >= outer_annulus)
        3. Use photutils ApertureStats for robust calculations
        """
        from astropy.stats import SigmaClip
        from photutils.aperture import ApertureStats

        x, y = star_pos

        # Create star aperture
        star_aperture = CircularAperture((x, y), r=self.aperture_params['inner_radius'])

        # Check if sky subtraction is disabled (inner_annulus >= outer_annulus)
        if self.aperture_params['inner_annulus'] >= self.aperture_params['outer_annulus']:
            # No sky subtraction - use raw star flux directly
            aper_stats = ApertureStats(image_data, star_aperture)
            star_flux_raw = float(aper_stats.sum)
            star_flux_corrected = star_flux_raw  # No sky correction

            # Set sky values to zero since no subtraction is performed
            sky_median = 0.0
            sky_std = 0.0
            sky_background_total = 0.0
            sky_pixels_count = 0

            self.logger.debug(f"Sky subtraction disabled - using raw flux: {star_flux_corrected:.1f}")
        else:
            # Normal sky subtraction using professional method
            sky_annulus = CircularAnnulus((x, y),
                                        r_in=self.aperture_params['inner_annulus'],
                                        r_out=self.aperture_params['outer_annulus'])

            # Configure sigma clipping for robust background estimation
            sigclip = SigmaClip(sigma=3.0, maxiters=10)

            # Compute source aperture statistics
            aper_stats = ApertureStats(image_data, star_aperture)

            # Compute background statistics using sigma-clipped median
            bkg_stats = ApertureStats(image_data, sky_annulus, sigma_clip=sigclip)

            # Extract values
            star_flux_raw = float(aper_stats.sum)
            sky_median = float(bkg_stats.median)
            sky_std = float(bkg_stats.std)
            sky_pixels_count = int(bkg_stats.sum_aper_area.value)

            # Calculate background-subtracted flux using professional method
            sky_background_total = sky_median * float(aper_stats.sum_aper_area.value)
            star_flux_corrected = star_flux_raw - sky_background_total

            self.logger.debug(f"Professional sky subtraction - Raw: {star_flux_raw:.1f}, "
                            f"Sky: {sky_background_total:.1f}, Corrected: {star_flux_corrected:.1f}")

        # Calculate Poisson noise from RAW counts (√N_raw before background subtraction)
        # This is the correct photon counting noise from the source
        poisson_noise = np.sqrt(abs(star_flux_raw)) if star_flux_raw > 0 else 0

        return {
            'x_position': x,
            'y_position': y,
            'star_flux_raw': float(star_flux_raw),
            'sky_background_total': float(sky_background_total),
            'sky_per_pixel': float(sky_median),
            'sky_std': float(sky_std),
            'star_flux_corrected': float(star_flux_corrected),
            'poisson_noise': float(poisson_noise),
            'aperture_area': float(star_aperture.area),
            'sky_annulus_area': sky_pixels_count
        }

    def perform_rgb_photometry(self, rgb_data, gray_data, star_pos):
        """Perform aperture photometry on all 3 RGB channels + grayscale"""
        from astropy.stats import SigmaClip
        from photutils.aperture import ApertureStats

        x, y = star_pos

        # Create apertures (same for all channels)
        star_aperture = CircularAperture((x, y), r=self.aperture_params['inner_radius'])
        sky_annulus = CircularAnnulus((x, y),
                                    r_in=self.aperture_params['inner_annulus'],
                                    r_out=self.aperture_params['outer_annulus'])

        # Configure sigma clipping for robust background estimation
        sigclip = SigmaClip(sigma=3.0, maxiters=10)

        results = {
            'x_position': x,
            'y_position': y,
            'aperture_area': float(star_aperture.area),
            'sky_annulus_area': float(sky_annulus.area)
        }

        # Process each RGB channel using robust sigma-clipped statistics
        channel_names = ['r', 'g', 'b']
        for i, channel_name in enumerate(channel_names):
            channel_data = rgb_data[i, :, :]  # Extract single channel

            # Get sky statistics using sigma-clipped median for robustness
            bkg_stats = ApertureStats(channel_data, sky_annulus, sigma_clip=sigclip)
            sky_median = float(bkg_stats.median)
            sky_std = float(bkg_stats.std)

            # Perform star photometry
            star_phot = aperture_photometry(channel_data, star_aperture)
            star_flux_raw = float(star_phot['aperture_sum'][0])

            # Calculate sky background using sigma-clipped MEDIAN
            sky_background_total = sky_median * star_aperture.area
            star_flux_corrected = star_flux_raw - sky_background_total

            # Calculate Poisson noise from RAW counts (before background subtraction)
            poisson_noise = np.sqrt(abs(star_flux_raw)) if star_flux_raw > 0 else 0

            # Store results with channel prefix
            results.update({
                f'{channel_name}_star_flux_raw': float(star_flux_raw),
                f'{channel_name}_sky_background_total': float(sky_background_total),
                f'{channel_name}_sky_per_pixel': float(sky_median),
                f'{channel_name}_sky_std': float(sky_std),
                f'{channel_name}_flux_corrected': float(star_flux_corrected),
                f'{channel_name}_poisson_noise': float(poisson_noise)
            })

        # Also process grayscale version using robust sigma-clipped statistics
        bkg_stats_gray = ApertureStats(gray_data, sky_annulus, sigma_clip=sigclip)
        sky_median_gray = float(bkg_stats_gray.median)
        sky_std_gray = float(bkg_stats_gray.std)

        star_phot_gray = aperture_photometry(gray_data, star_aperture)
        star_flux_raw_gray = float(star_phot_gray['aperture_sum'][0])

        sky_background_gray = sky_median_gray * star_aperture.area
        star_flux_corrected_gray = star_flux_raw_gray - sky_background_gray

        # Calculate Poisson noise from RAW counts (before background subtraction)
        poisson_noise_gray = np.sqrt(abs(star_flux_raw_gray)) if star_flux_raw_gray > 0 else 0

        results.update({
            'gray_star_flux_raw': float(star_flux_raw_gray),
            'gray_sky_background_total': float(sky_background_gray),
            'gray_sky_per_pixel': float(sky_median_gray),
            'gray_sky_std': float(sky_std_gray),
            'gray_flux_corrected': float(star_flux_corrected_gray),
            'gray_poisson_noise': float(poisson_noise_gray)
        })

        return results

    def extract_fits_metadata(self, header, filename):
        """Extract relevant metadata from FITS header"""
        metadata = {}

        # Common FITS keywords for time
        time_keywords = ['DATE-OBS', 'TIME-OBS', 'JD', 'MJD', 'DATEOBS']
        for keyword in time_keywords:
            if keyword in header:
                metadata[f'fits_{keyword.lower()}'] = str(header[keyword])

        # Other useful keywords
        useful_keywords = ['EXPTIME', 'EXPOSURE', 'FILTER', 'OBJECT', 'OBSERVER',
                          'TELESCOP', 'INSTRUME', 'XPIXSZ', 'YPIXSZ']
        for keyword in useful_keywords:
            if keyword in header:
                metadata[f'fits_{keyword.lower()}'] = str(header[keyword])

        # File modification time as fallback
        metadata['file_mtime'] = os.path.getmtime(filename)

        return metadata

    def stop_photometry_processing(self):
        """Toggle between pause/resume processing and stop"""
        if not self.processing and not self.batch_processing_mode and not self.preselection_mode:
            # No processing is running - this shouldn't happen but handle gracefully
            self.log_status("No processing is currently running")
            return
            
        # Check if we're currently paused
        if self.paused:
            # Resume processing
            self.resume_from_button()
        else:
            # First click - pause processing
            if self.processing or self.batch_processing_mode or self.preselection_mode:
                self.pause_processing()
            else:
                # Final stop - this happens if pause timeout occurred or user chose to stop
                self.stop_processing = True
                self.paused = False
                self.stop_button.config(text="Stop Processing")
                self.log_status("Stop signal sent...")
                # Auto-save progress if we have results
                if self.photometry_results or self.preselected_positions:
                    self.auto_save_results()
                    if self.preselected_positions:
                        self.auto_save_star_positions()
                    self.log_status("Progress automatically saved")
                # Disable result buttons when stopping
                self.disable_result_buttons()
                
    def pause_processing(self):
        """Pause the current processing with frame navigation capability"""
        self.paused = True

        # Store current tracking mode and frame position for proper resumption
        if self.preselection_mode:
            self.paused_tracking_mode = 'preselection'
            self.paused_frame_index = self.current_frame_index
        elif self.batch_processing_mode:
            self.paused_tracking_mode = 'batch'
            self.paused_frame_index = getattr(self, 'current_batch_index', 0)
        elif self.sequential_mode:
            self.paused_tracking_mode = 'sequential'
            self.paused_frame_index = self.current_frame_index
        else:
            self.paused_tracking_mode = 'regular'
            self.paused_frame_index = 0

        self.stop_button.config(text="Resume from Current Frame")

        # Enable frame navigation during pause
        self.enable_pause_navigation()

        self.log_status("Processing PAUSED - Navigation enabled")
        self.log_status("Use Previous/Next buttons to navigate frames")
        self.log_status("Click Resume to continue from current frame, or click on star to resume from that position")

        # Check if tracking is enabled for appropriate message
        if self.tracking_enabled_var.get() and self.paused_tracking_mode in ['preselection', 'batch']:
            self.log_status("Auto-tracking will resume when you click on star")
        else:
            self.log_status("Manual mode will continue when you click on star")

        # Start a timer - if user doesn't resume within 30 seconds, offer stop option
        self.root.after(30000, self._check_pause_timeout)

    def enable_pause_navigation(self):
        """Enable frame navigation during pause mode"""
        # Always enable navigation buttons during pause
        if hasattr(self, 'go_back_button'):
            self.go_back_button.config(state=tk.NORMAL, text="← Previous Frame")
        if hasattr(self, 'skip_frame_button'):
            self.skip_frame_button.config(state=tk.NORMAL, text="Next Frame →")

        # Load current frame for navigation
        if hasattr(self, 'paused_frame_index') and self.fits_files:
            self.current_frame_index = self.paused_frame_index
            self.load_frame_for_pause_navigation(self.current_frame_index)

    def load_frame_for_pause_navigation(self, frame_index):
        """Load a frame during pause mode for navigation"""
        if frame_index < 0 or frame_index >= len(self.fits_files):
            return

        try:
            fits_file = self.fits_files[frame_index]
            filename = os.path.basename(fits_file)

            self.log_status(f"Navigating to frame {frame_index + 1}/{len(self.fits_files)}: {filename}")

            # Update frame counter for navigation
            self.update_frame_counter(frame_index, len(self.fits_files), "PAUSED - Frame")

            # Load the image
            with fits.open(fits_file) as hdul:
                image_data = hdul[0].data
                header = hdul[0].header

                # Store current image data
                self.current_image_data = image_data
                self.current_image_header = header

                # Handle RGB vs grayscale
                if len(image_data.shape) == 3 and image_data.shape[0] == 3:
                    self.current_image_rgb = image_data.copy()
                    self.current_image_grayscale = np.mean(image_data, axis=0)
                else:
                    self.current_image_rgb = None
                    self.current_image_grayscale = image_data

            # Display the frame without aperture initially
            self.display_image(show_aperture=False)

            # Show previous star position if available for reference
            if (hasattr(self, 'preselected_positions') and
                frame_index < len(self.preselected_positions) and
                self.preselected_positions[frame_index] is not None):
                prev_pos = self.preselected_positions[frame_index]
                self.selected_star_pos = prev_pos
                self.display_image(show_aperture=True)
                self.log_status(f"Previous star position: ({prev_pos[0]:.1f}, {prev_pos[1]:.1f})")

            # Set title to show pause navigation mode
            title = f"PAUSED - Frame {frame_index + 1}/{len(self.fits_files)} - Navigate or Resume"
            self.ax.set_title(title)
            self.canvas.draw()

        except Exception as e:
            self.log_status(f"Error loading frame {frame_index + 1}: {e}")
    
    def resume_from_button(self):
        """Resume processing from button click - waits for user to click a position"""
        if not self.paused:
            return

        # Don't unpause yet - wait for user to click a position first
        self.log_status(f"Click on star position to resume processing from frame {self.current_frame_index + 1}")

        # Change state to indicate we're waiting for resume click
        self.waiting_for_resume_click = True

        # Show which mode we'll resume in
        if hasattr(self, 'paused_tracking_mode') and self.paused_tracking_mode == 'preselection':
            if self.tracking_enabled_var.get():
                self.log_status("Will resume with auto-tracking (position will be refined)")
            else:
                self.log_status("Will resume in manual mode")
        else:
            self.log_status("Will resume sequential tracking")

    def disable_pause_navigation(self):
        """Disable frame navigation when resuming"""
        # Disable navigation buttons when tracking resumes (they should only work during pause)
        if hasattr(self, 'go_back_button'):
            self.go_back_button.config(state=tk.DISABLED, text="Previous")
        if hasattr(self, 'skip_frame_button'):
            self.skip_frame_button.config(state=tk.DISABLED, text="Next")

    def clear_data_from_current_frame(self):
        """Clear all data from current frame index onwards (for data overwrite)"""
        current_idx = self.current_frame_index

        if hasattr(self, 'preselected_positions') and self.preselected_positions:
            # Remove positions from current frame onwards
            original_length = len(self.preselected_positions)
            self.preselected_positions = self.preselected_positions[:current_idx]
            removed_count = original_length - len(self.preselected_positions)
            if removed_count > 0:
                self.log_status(f"Cleared {removed_count} pre-selected positions from frame {current_idx + 1} onwards")

        if hasattr(self, 'photometry_results') and self.photometry_results:
            # Remove results from current frame onwards
            original_length = len(self.photometry_results)
            # Filter results to keep only those with image_index < current_idx
            self.photometry_results = [r for r in self.photometry_results if r.get('image_index', 0) < current_idx]
            removed_count = original_length - len(self.photometry_results)
            if removed_count > 0:
                self.log_status(f"Cleared {removed_count} photometry results from frame {current_idx + 1} onwards")

        if hasattr(self, 'frame_positions') and self.frame_positions:
            # Remove frame positions from current index onwards
            original_length = len(self.frame_positions)
            self.frame_positions = self.frame_positions[:current_idx]
            removed_count = original_length - len(self.frame_positions)
            if removed_count > 0:
                self.log_status(f"Cleared {removed_count} frame positions from frame {current_idx + 1} onwards")
    
    def resume_from_pause(self, event):
        """Handle image click during pause to resume processing from clicked position"""
        if not self.paused:
            return

        x, y = event.xdata, event.ydata
        if x is None or y is None:
            return

        # Clear old data from current frame onwards (data overwrite)
        self.clear_data_from_current_frame()

        # Disable navigation buttons
        self.disable_pause_navigation()

        self.paused = False
        self.stop_button.config(text="Pause Processing")

        # Resume with clicked position as new reference
        if self.paused_tracking_mode == 'preselection':
            # Apply star tracking refinement if auto-tracking is enabled
            refined_pos = (x, y)
            if self.tracking_enabled_var.get() and self.current_image_data is not None:
                try:
                    # Determine which data to use for tracking
                    if hasattr(self, 'current_image_grayscale') and self.current_image_grayscale is not None:
                        tracking_data = self.current_image_grayscale
                    else:
                        tracking_data = self.current_image_data
                        if len(tracking_data.shape) == 3 and tracking_data.shape[0] == 3:
                            tracking_data = np.mean(tracking_data, axis=0)

                    # Apply tracking refinement to clicked position
                    search_radius = self.search_radius_var.get()
                    tracked_pos = self.track_star_position(tracking_data, (x, y), search_radius)

                    if tracked_pos is not None:
                        refined_pos = tracked_pos
                        self.log_status(f"Applied tracking refinement: ({x:.1f}, {y:.1f}) → ({refined_pos[0]:.1f}, {refined_pos[1]:.1f})")
                    else:
                        self.log_status(f"Tracking refinement failed - using clicked position ({x:.1f}, {y:.1f})")
                except Exception as e:
                    self.log_status(f"Tracking refinement error - using clicked position ({x:.1f}, {y:.1f})")

            # Store the refined position for current frame
            self.update_position_after_navigation(refined_pos[0], refined_pos[1])

            # Update selected star position for aperture display
            self.selected_star_pos = refined_pos
            self.display_image(show_aperture=True)

            if self.tracking_enabled_var.get():
                self.log_status(f"Auto-tracking resumed from frame {self.current_frame_index + 1} at ({refined_pos[0]:.1f}, {refined_pos[1]:.1f})")
                self.log_status("Auto-tracking will continue from this position")
                # Continue to next frame with auto-tracking
                self.root.after(500, self.advance_to_next_preselection_frame)
            else:
                self.log_status(f"Manual mode resumed from frame {self.current_frame_index + 1} at ({refined_pos[0]:.1f}, {refined_pos[1]:.1f})")
                self.log_status("Manual mode will continue - click each star")
                # Continue to next frame in manual mode
                self.root.after(500, self.advance_to_next_preselection_frame)

        elif self.paused_tracking_mode == 'batch':
            self.log_status("Batch processing resumed - restarting from current position")
            # Resume batch processing would need additional implementation

        elif self.paused_tracking_mode == 'sequential':
            # Apply star tracking refinement if auto-tracking is enabled for sequential mode too
            refined_pos = (x, y)
            if self.tracking_enabled_var.get() and self.current_image_data is not None:
                try:
                    # Determine which data to use for tracking
                    if hasattr(self, 'current_image_grayscale') and self.current_image_grayscale is not None:
                        tracking_data = self.current_image_grayscale
                    else:
                        tracking_data = self.current_image_data
                        if len(tracking_data.shape) == 3 and tracking_data.shape[0] == 3:
                            tracking_data = np.mean(tracking_data, axis=0)

                    # Apply tracking refinement to clicked position
                    search_radius = self.search_radius_var.get()
                    tracked_pos = self.track_star_position(tracking_data, (x, y), search_radius)

                    if tracked_pos is not None:
                        refined_pos = tracked_pos
                        self.log_status(f"Applied tracking refinement: ({x:.1f}, {y:.1f}) → ({refined_pos[0]:.1f}, {refined_pos[1]:.1f})")
                    else:
                        self.log_status(f"Tracking refinement failed - using clicked position ({x:.1f}, {y:.1f})")
                except Exception as e:
                    self.log_status(f"Tracking refinement error - using clicked position ({x:.1f}, {y:.1f})")

            self.log_status(f"Sequential mode resumed from frame {self.current_frame_index + 1} at ({refined_pos[0]:.1f}, {refined_pos[1]:.1f})")

            # Store the refined position and continue sequential tracking
            self.update_position_after_navigation(refined_pos[0], refined_pos[1])
            self.selected_star_pos = refined_pos
            self.display_image(show_aperture=True)

            # Continue sequential tracking from this frame
            self.root.after(500, self.advance_to_next_frame)

        else:
            self.log_status(f"Processing resumed from clicked position ({x:.1f}, {y:.1f})")

        # Clear the pause tracking mode
        self.paused_tracking_mode = None

    def update_position_during_pause(self, event):
        """Handle clicking during pause to update position for current frame or resume"""
        if not self.paused:
            return

        x, y = event.xdata, event.ydata
        if x is None or y is None:
            return

        # Check if user clicked Resume button and is now clicking to resume
        if hasattr(self, 'waiting_for_resume_click') and self.waiting_for_resume_click:
            self.waiting_for_resume_click = False
            self.resume_from_pause(event)
            return

        # Normal case: update position for the current frame during pause navigation
        self.update_position_after_navigation(x, y)

        # Update visual display
        self.selected_star_pos = (x, y)
        self.display_image(show_aperture=True)

        self.log_status(f"Updated position for frame {self.current_frame_index + 1}: ({x:.1f}, {y:.1f}) - Use Resume to continue processing")
    
    def _check_pause_timeout(self):
        """Check if pause has timed out and offer stop option"""
        if self.paused and (self.processing or self.batch_processing_mode or self.preselection_mode):
            # Still paused after timeout - change button text to show stop option
            self.stop_button.config(text="Resume / Stop Processing")
            self.log_status("Pause timeout - click button to resume or stop processing")

    def start_sequential_tracking(self):
        """Start PASCO Capstone-style sequential tracking mode"""
        if not self.validate_inputs():
            return

        # Initialize sequential tracking state
        self.sequential_mode = True
        self.current_frame_index = 0
        self.frame_positions = []
        self.sequential_results = []
        self.photometry_results = []

        # Keep navigation buttons DISABLED during active processing
        # They will only be enabled when user pauses
        if hasattr(self, 'go_back_button'):
            self.go_back_button.config(state=tk.DISABLED)
        if hasattr(self, 'skip_frame_button'):
            self.skip_frame_button.config(state=tk.DISABLED)

        self.log_status("Starting PASCO Capstone-style sequential tracking...")
        self.log_status(f"Total frames to process: {len(self.fits_files)}")
        self.log_status("Click on star to advance, or use Go Back/Skip buttons")

        # Start with the first frame
        self.load_frame_for_tracking(0)

    def load_frame_for_tracking(self, frame_index):
        """Load a specific frame for manual tracking, centered on previous star position"""
        if frame_index >= len(self.fits_files):
            # All frames processed, finish sequential tracking
            self.finish_sequential_tracking()
            return

        try:
            fits_file = self.fits_files[frame_index]
            filename = os.path.basename(fits_file)

            self.log_status(f"Frame {frame_index + 1}/{len(self.fits_files)}: {filename}")

            # Load the image
            with fits.open(fits_file) as hdul:
                image_data = hdul[0].data
                header = hdul[0].header

                # Store current image data
                self.current_image_data = image_data
                self.current_image_header = header

                # Handle RGB vs grayscale
                if len(image_data.shape) == 3 and image_data.shape[0] == 3:
                    self.current_image_rgb = image_data.copy()
                    self.current_image_grayscale = np.mean(image_data, axis=0)
                else:
                    self.current_image_rgb = None
                    self.current_image_grayscale = image_data

            # Display the frame
            self.display_image(show_aperture=False)

            # Auto-center on previous star position if we have one and zoom is active
            if frame_index > 0 and len(self.frame_positions) > 0 and self.zoom_active:
                prev_star_pos = self.frame_positions[-1]  # Last recorded position

                # Calculate zoom size proportional to outermost annulus radius (same as toggle_zoom)
                outer_radius = self.aperture_params['outer_annulus']
                zoom_size = max(30, min(200, outer_radius * 3))

                # Center the view on the previous star position
                self.ax.set_xlim(prev_star_pos[0] - zoom_size, prev_star_pos[0] + zoom_size)
                self.ax.set_ylim(prev_star_pos[1] - zoom_size, prev_star_pos[1] + zoom_size)

                self.log_status(f"Auto-centered on previous star position ({prev_star_pos[0]:.1f}, {prev_star_pos[1]:.1f}) with {zoom_size*2}px window")

            # Set title to show sequential tracking mode with filename
            filename = os.path.basename(self.fits_files[frame_index])
            title = f"Manual Mode {frame_index + 1}/{len(self.fits_files)}: {filename} - Click star"
            self.ax.set_title(title)
            self.canvas.draw()

            # Update progress
            progress = (frame_index / len(self.fits_files)) * 100
            self.progress_var.set(progress)

        except Exception as e:
            self.log_status(f"Error loading frame {frame_index + 1}: {e}")
            messagebox.showerror("Frame Load Error", f"Failed to load frame {frame_index + 1}: {e}")
            self.sequential_mode = False

    def on_sequential_tracking_click(self, event):
        """Handle clicks during sequential tracking mode"""
        if not self.sequential_mode:
            return False

        if event.inaxes != self.ax:
            return False

        if event.xdata is None or event.ydata is None:
            return False

        x, y = event.xdata, event.ydata

        # Use exact click position for precise user control
        star_pos = (x, y)
        self.log_status(f"Sequential tracking: exact click position ({x:.1f}, {y:.1f})")

        # Store the position for this frame
        self.frame_positions.append(star_pos)

        # Show aperture at selected position immediately
        self.selected_star_pos = star_pos
        self.star_pos_label.config(text=f"Star at ({star_pos[0]:.1f}, {star_pos[1]:.1f})")

        # Store current zoom state BEFORE clearing
        current_xlim = None
        current_ylim = None
        if self.zoom_active and hasattr(self.ax, 'get_xlim'):
            try:
                current_xlim = self.ax.get_xlim()
                current_ylim = self.ax.get_ylim()
            except:
                pass

        # Clear and redraw with aperture circles
        self.ax.clear()

        # Redisplay the image with aperture
        if hasattr(self, 'current_image_rgb') and self.current_image_rgb is not None:
            # RGB display
            data = self.current_image_rgb.astype(np.float32)
            display_data = np.moveaxis(data, 0, -1)
            vmin, vmax = np.percentile(display_data, [0.5, 99.5])
            display_data = np.clip(display_data, vmin, vmax)
            display_data = (display_data - vmin) / (vmax - vmin)
            self.ax.imshow(display_data, origin='lower')
        else:
            # Grayscale display
            data = self.current_image_data.astype(np.float32)
            vmin, vmax = np.percentile(data, [0.5, 99.5])
            self.ax.imshow(data, cmap='gray', origin='lower', vmin=vmin, vmax=vmax)

        # Draw aperture circles at clicked position
        self.draw_aperture_circles()

        # RESTORE zoom state if it was active
        if self.zoom_active and current_xlim is not None and current_ylim is not None:
            try:
                self.ax.set_xlim(current_xlim)
                self.ax.set_ylim(current_ylim)
            except:
                pass

        # Update title
        title = f"Sequential Tracking: Frame {self.current_frame_index + 1}/{len(self.fits_files)} - Processing..."
        self.ax.set_title(title)
        self.canvas.draw()
        self.canvas.flush_events()

        # Process photometry for this frame
        self.process_current_frame(star_pos)

        # Move to next frame after a pause to see the aperture
        self.root.after(800, self.advance_to_next_frame)

        return True  # Indicate we handled the click

    def process_current_frame(self, star_pos):
        """Process photometry for the current frame in sequential mode"""
        try:
            frame_index = self.current_frame_index
            fits_file = self.fits_files[frame_index]

            # Determine if RGB or grayscale
            is_rgb = hasattr(self, 'current_image_rgb') and self.current_image_rgb is not None

            if is_rgb:
                # RGB photometry
                phot_results = self.perform_rgb_photometry(self.current_image_rgb,
                                                         self.current_image_grayscale,
                                                         star_pos)
            else:
                # Grayscale photometry
                phot_results = self.perform_aperture_photometry(self.current_image_grayscale, star_pos)
                # Add gray prefix for consistency
                phot_results = {f"gray_{k}" if not k.startswith(('x_', 'y_', 'aperture_', 'sky_')) else k: v
                              for k, v in phot_results.items()}

            # Extract metadata
            metadata = self.extract_fits_metadata(self.current_image_header, fits_file)

            # Calculate movement from previous frame
            movement = 0.0
            if frame_index > 0 and len(self.frame_positions) > 1:
                prev_pos = self.frame_positions[frame_index - 1]
                movement = np.sqrt((star_pos[0] - prev_pos[0])**2 + (star_pos[1] - prev_pos[1])**2)

            # Create result record
            result = {
                'image_index': frame_index,
                'filename': os.path.basename(fits_file),
                'star_name': self.star_name,
                'tracked_position': star_pos,
                'movement_pixels': movement,
                'is_rgb': is_rgb,
                **phot_results,
                **metadata
            }

            self.photometry_results.append(result)

            # Enable result buttons when we have results
            self.enable_result_buttons()

            self.log_status(f"Frame {frame_index + 1} processed: star at ({star_pos[0]:.1f}, {star_pos[1]:.1f})")

        except Exception as e:
            self.log_status(f"Error processing frame {self.current_frame_index + 1}: {e}")

    def advance_to_next_frame(self):
        """Move to the next frame in sequential tracking"""
        self.current_frame_index += 1
        self.advance_to_next_frame_direct()

    def advance_to_next_frame_direct(self):
        """Direct advance without incrementing (used by skip)"""
        if self.current_frame_index >= len(self.fits_files):
            # All frames processed
            self.finish_sequential_tracking()
        else:
            # Load next frame
            self.load_frame_for_tracking(self.current_frame_index)

    def finish_sequential_tracking(self):
        """Complete sequential tracking and show results"""
        self.sequential_mode = False
        self.progress_var.set(100)

        # Disable navigation buttons
        if hasattr(self, 'go_back_button'):
            self.go_back_button.config(state=tk.DISABLED)
        if hasattr(self, 'skip_frame_button'):
            self.skip_frame_button.config(state=tk.DISABLED)

        processed_count = len(self.photometry_results)
        total_count = len(self.fits_files)

        self.log_status(f"Sequential tracking completed!")
        self.log_status(f"Processed {processed_count}/{total_count} frames")

        # Enable result buttons when we have completed results
        self.enable_result_buttons()

        # Show completion message
        completion_msg = (f"Sequential tracking completed!\n\n"
                         f"Processed: {processed_count} frames\n"
                         f"Total frames: {total_count}\n\n"
                         f"You can now save the results using the 'Save Results as CSV' button.")

        messagebox.showinfo("Sequential Tracking Complete", completion_msg)

        # Reset to first image with results
        if self.photometry_results:
            self.load_first_image()

    # NEW: Two-phase workflow methods (your improvement!)

    def prompt_star_name(self, reason="missing"):
        """Show popup dialog for star name entry"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Star Name Required")
        dialog.geometry("400x200")
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Center the dialog
        dialog.geometry("+%d+%d" % (self.root.winfo_rootx() + 50, self.root.winfo_rooty() + 50))
        
        result = {"name": None}
        
        # Message based on reason
        if reason == "duplicate":
            message = "Star name already exists in saved positions.\nPlease enter a different name:"
        else:
            message = "Star name is required to proceed.\nPlease enter the star name:"
        
        ttk.Label(dialog, text=message, wraplength=350).pack(pady=10)
        
        # Entry field
        name_var = tk.StringVar(value=self.star_name_var.get().strip())
        entry = ttk.Entry(dialog, textvariable=name_var, width=30)
        entry.pack(pady=5)
        entry.focus_set()
        
        # Buttons
        button_frame = ttk.Frame(dialog)
        button_frame.pack(pady=10)
        
        def ok_clicked():
            name = name_var.get().strip()
            if name:
                result["name"] = name
                dialog.destroy()
            else:
                messagebox.showwarning("Invalid Name", "Please enter a valid star name.")
        
        def cancel_clicked():
            dialog.destroy()
        
        ttk.Button(button_frame, text="OK", command=ok_clicked).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=cancel_clicked).pack(side=tk.LEFT, padx=5)
        
        # Enter key binding
        entry.bind('<Return>', lambda e: ok_clicked())
        
        # Wait for dialog to close
        dialog.wait_window()
        
        return result["name"]

    def check_star_name_conflict(self, star_name):
        """Check if star name already exists in positions folder"""
        if not star_name:
            return True  # Empty name is always a conflict
            
        positions_dir = os.path.join(os.getcwd(), "positions")
        if not os.path.exists(positions_dir):
            return False  # No conflicts if directory doesn't exist
            
        # Look for existing files with this star name
        pattern = f"{star_name}_positions_*.csv"
        existing_files = glob.glob(os.path.join(positions_dir, pattern))
        
        return len(existing_files) > 0

    def validate_star_name_for_processing(self):
        """Validate star name before starting processing, show popup if needed"""
        star_name = self.star_name_var.get().strip()
        
        # Check if name is missing
        if not star_name:
            new_name = self.prompt_star_name("missing")
            if not new_name:
                return False  # User cancelled
            star_name = new_name
            
        # Check for conflicts
        if self.check_star_name_conflict(star_name):
            new_name = self.prompt_star_name("duplicate")
            if not new_name:
                return False  # User cancelled
            star_name = new_name
            
        # Update the star name field
        self.star_name_var.set(star_name)
        self.star_name = star_name
        
        return True

    def start_preselection_mode(self):
        """Start Phase 1: Pre-select star positions in all frames"""
        # Check basic inputs first
        if not self.fits_files:
            messagebox.showerror("No Files", "Please select a FITS folder first")
            return

        if not self.selected_star_pos:
            messagebox.showerror("No Star", "Please select a star first")
            return

        # Validate star name with popup if needed
        if not self.validate_star_name_for_processing():
            return

        # Initialize pre-selection state
        self.preselection_mode = True
        self.preselected_positions = []
        self.current_frame_index = 0
        self.photometry_results = []  # Clear previous results

        # Initialize the preselected positions list
        self.preselected_positions = []

        # Initialize stop flag
        self.stop_preselection = False

        # IMPROVED: Reset tracking history for new session
        self.position_history = []
        self.velocity_history = []
        self.tracking_confidence = []

        # Update button states
        self.preselect_button.config(state=tk.DISABLED, text="Selecting...")
        self.pause_preselect_button.config(state=tk.NORMAL)
        self.stop_preselect_button.config(state=tk.NORMAL)
        self.batch_process_button.config(state=tk.DISABLED)

        # Keep navigation buttons DISABLED during active processing
        # They will only be enabled when user pauses
        if hasattr(self, 'go_back_button'):
            self.go_back_button.config(state=tk.DISABLED)
        if hasattr(self, 'skip_frame_button'):
            self.skip_frame_button.config(state=tk.DISABLED)

        self.log_status("Starting pre-selection mode...")
        if self.tracking_enabled_var.get():
            self.log_status(f"Click stars in {len(self.fits_files)} frames (auto-tracking enabled)")
        else:
            self.log_status(f"Click stars in {len(self.fits_files)} frames (manual mode)")
        self.log_status("Pause anytime to navigate frames")

        # Update counters
        self.update_frame_counter(0, len(self.fits_files), "Pre-selecting")
        self.update_processed_counter(0, len(self.fits_files))  # No frames done yet

        # Start with the first frame
        self.load_frame_for_preselection(0)

    def toggle_preselection_pause(self):
        """Toggle pause/resume for pre-selection mode"""
        if not self.preselection_mode:
            return

        if not hasattr(self, 'preselection_paused'):
            self.preselection_paused = False

        if self.preselection_paused:
            # Resume pre-selection
            self.resume_preselection()
        else:
            # Pause pre-selection
            self.pause_preselection()

    def pause_preselection(self):
        """Pause pre-selection mode and enable navigation"""
        self.preselection_paused = True
        self.pause_preselect_button.config(text="Resume Selection")

        # Enable navigation buttons during pause
        if hasattr(self, 'go_back_button'):
            self.go_back_button.config(state=tk.NORMAL, text="← Previous Frame")
        if hasattr(self, 'skip_frame_button'):
            self.skip_frame_button.config(state=tk.NORMAL, text="Next Frame →")
        if hasattr(self, 'clear_position_button'):
            self.clear_position_button.config(state=tk.NORMAL)

        self.log_status("Pre-selection PAUSED - Use Previous/Next to navigate frames")
        self.log_status("Click on star to update position, right-click to clear position, then Resume to continue")

    def resume_preselection(self):
        """Resume pre-selection mode from current frame"""
        self.preselection_paused = False
        self.pause_preselect_button.config(text="Pause & Navigate")

        # Disable navigation buttons during active selection
        if hasattr(self, 'go_back_button'):
            self.go_back_button.config(state=tk.DISABLED, text="Previous")
        if hasattr(self, 'skip_frame_button'):
            self.skip_frame_button.config(state=tk.DISABLED, text="Next")
        if hasattr(self, 'clear_position_button'):
            self.clear_position_button.config(state=tk.DISABLED)

        # Remove any positions from current frame onwards to ensure proper sequential processing
        while len(self.preselected_positions) > self.current_frame_index:
            self.preselected_positions.pop()

        if self.tracking_enabled_var.get():
            # Auto-tracking mode: wait for user to click reference point
            self.log_status(f"Pre-selection RESUMED from frame {self.current_frame_index + 1}")
            self.log_status("AUTO-TRACKING MODE: Click on star to set reference point for tracking")
            self.waiting_for_resume_reference = True
        else:
            # Manual mode: continue directly
            self.log_status(f"Pre-selection RESUMED from frame {self.current_frame_index + 1}")
            self.log_status("MANUAL MODE: Click on each star position")
            # Start sequential processing from current frame
            self.root.after(100, lambda: self.load_frame_for_preselection(self.current_frame_index))

    def update_preselection_position_during_pause(self, x, y, event=None):
        """Update preselected position for current frame during pause"""
        # Check for right-click to clear position
        if event and event.button == 3:  # Right-click
            self.clear_current_frame_position()
            return
        # Apply star tracking refinement if enabled
        refined_pos = (x, y)
        if self.tracking_enabled_var.get() and self.current_image_data is not None:
            try:
                # Determine which data to use for tracking
                if hasattr(self, 'current_image_grayscale') and self.current_image_grayscale is not None:
                    tracking_data = self.current_image_grayscale
                else:
                    tracking_data = self.current_image_data
                    if len(tracking_data.shape) == 3 and tracking_data.shape[0] == 3:
                        tracking_data = np.mean(tracking_data, axis=0)

                # Apply tracking refinement to clicked position
                search_radius = self.search_radius_var.get()
                tracked_pos = self.track_star_position(tracking_data, (x, y), search_radius)

                if tracked_pos is not None:
                    refined_pos = tracked_pos
                    self.log_status(f"Applied tracking refinement: ({x:.1f}, {y:.1f}) → ({refined_pos[0]:.1f}, {refined_pos[1]:.1f})")
                else:
                    self.log_status(f"Tracking refinement failed - using clicked position ({x:.1f}, {y:.1f})")
            except Exception as e:
                self.log_status(f"Tracking refinement error - using clicked position ({x:.1f}, {y:.1f})")

        # Ensure the preselected_positions list is long enough
        while len(self.preselected_positions) <= self.current_frame_index:
            self.preselected_positions.append(None)

        # Update position for current frame
        old_pos = self.preselected_positions[self.current_frame_index]
        self.preselected_positions[self.current_frame_index] = refined_pos

        # Important: Do NOT remove positions from frames after this one during pause navigation
        # This preserves existing work and allows proper frame skipping
        # Only remove positions when resuming (handled in resume logic)

        # Update visual display
        self.selected_star_pos = refined_pos
        self.display_image(show_aperture=True)

        if old_pos:
            self.log_status(f"Updated position for frame {self.current_frame_index + 1}: {old_pos} → ({refined_pos[0]:.1f}, {refined_pos[1]:.1f})")
        else:
            self.log_status(f"Set position for frame {self.current_frame_index + 1}: ({refined_pos[0]:.1f}, {refined_pos[1]:.1f})")

        self.log_status(f"Position updated - Resume will continue from frame {self.current_frame_index + 1}")

    def set_resume_reference_point(self, x, y):
        """Set reference point for resuming auto-tracking"""
        self.waiting_for_resume_reference = False

        # Apply star tracking refinement to clicked position
        refined_pos = (x, y)
        if self.current_image_data is not None:
            try:
                # Determine which data to use for tracking
                if hasattr(self, 'current_image_grayscale') and self.current_image_grayscale is not None:
                    tracking_data = self.current_image_grayscale
                else:
                    tracking_data = self.current_image_data
                    if len(tracking_data.shape) == 3 and tracking_data.shape[0] == 3:
                        tracking_data = np.mean(tracking_data, axis=0)

                # Apply tracking refinement to clicked position
                search_radius = self.search_radius_var.get()
                tracked_pos = self.track_star_position(tracking_data, (x, y), search_radius)

                if tracked_pos is not None:
                    refined_pos = tracked_pos
                    self.log_status(f"Reference point set with tracking refinement: ({x:.1f}, {y:.1f}) → ({refined_pos[0]:.1f}, {refined_pos[1]:.1f})")
                else:
                    self.log_status(f"Tracking refinement failed - using clicked reference point ({x:.1f}, {y:.1f})")
            except Exception as e:
                self.log_status(f"Tracking refinement error - using clicked reference point ({x:.1f}, {y:.1f})")

        # Set the reference position for current frame
        while len(self.preselected_positions) <= self.current_frame_index:
            self.preselected_positions.append(None)
        self.preselected_positions[self.current_frame_index] = refined_pos

        # Update visual display
        self.selected_star_pos = refined_pos
        self.display_image(show_aperture=True)

        self.log_status(f"Auto-tracking reference set at ({refined_pos[0]:.1f}, {refined_pos[1]:.1f}) - continuing to next frame")

        # Continue to next frame with auto-tracking
        self.root.after(500, self.advance_to_next_preselection_frame)

    def clear_current_frame_position(self):
        """Clear the position for the current frame during pause"""
        if self.current_frame_index < len(self.preselected_positions):
            old_pos = self.preselected_positions[self.current_frame_index]
            self.preselected_positions[self.current_frame_index] = None

            if old_pos:
                self.log_status(f"Cleared position for frame {self.current_frame_index + 1}: {old_pos}")
            else:
                self.log_status(f"No position to clear for frame {self.current_frame_index + 1}")
        else:
            self.log_status(f"No position to clear for frame {self.current_frame_index + 1}")

        # Update visual display
        self.selected_star_pos = None
        self.display_image(show_aperture=False)

        # Update title
        title = f"PAUSED - Frame {self.current_frame_index + 1}/{len(self.fits_files)} - Position Cleared"
        self.ax.set_title(title)
        self.canvas.draw()

    def load_frame_for_preselection_pause(self, frame_index):
        """Load a frame during preselection pause - no auto-skip logic"""
        if frame_index < 0 or frame_index >= len(self.fits_files):
            return

        try:
            fits_file = self.fits_files[frame_index]
            filename = os.path.basename(fits_file)

            self.log_status(f"PAUSED - Viewing frame {frame_index + 1}/{len(self.fits_files)}: {filename}")

            # Update frame counter for pause navigation
            self.update_frame_counter(frame_index, len(self.fits_files), "PAUSED - Frame")

            # Load the image
            with fits.open(fits_file) as hdul:
                image_data = hdul[0].data
                header = hdul[0].header

                # Store current image data
                self.current_image_data = image_data
                self.current_image_header = header

                # Handle RGB vs grayscale
                if len(image_data.shape) == 3 and image_data.shape[0] == 3:
                    self.current_image_rgb = image_data.copy()
                    self.current_image_grayscale = np.mean(image_data, axis=0)
                else:
                    self.current_image_rgb = None
                    self.current_image_grayscale = image_data

                # Show existing preselected position if available
                if frame_index < len(self.preselected_positions) and self.preselected_positions[frame_index] is not None:
                    existing_pos = self.preselected_positions[frame_index]
                    self.selected_star_pos = existing_pos
                    self.log_status(f"Showing existing position: ({existing_pos[0]:.1f}, {existing_pos[1]:.1f})")
                else:
                    self.selected_star_pos = None
                    self.log_status("No position set for this frame")

                # Display the image with frame counter in title
                self.display_image(show_aperture=self.selected_star_pos is not None)

                # Set title to show frame counter and filename during pause navigation
                filename = os.path.basename(self.fits_files[frame_index])
                title = f"PAUSED - Frame {frame_index + 1}/{len(self.fits_files)}: {filename} - Navigate or Resume"
                self.ax.set_title(title)
                self.canvas.draw()

        except Exception as e:
            self.log_status(f"Error loading frame {frame_index + 1}: {e}")

    def stop_preselection_mode(self):
        """Stop pre-selection mode early and save current progress"""
        if not self.preselection_mode:
            return

        self.stop_preselection = True
        self.preselection_mode = False
        self.preselection_paused = False

        # Update button states
        self.preselect_button.config(state=tk.NORMAL, text="Pre-select Positions")
        self.pause_preselect_button.config(state=tk.DISABLED, text="Pause & Navigate")
        self.stop_preselect_button.config(state=tk.DISABLED)

        # Disable navigation buttons
        if hasattr(self, 'go_back_button'):
            self.go_back_button.config(state=tk.DISABLED)
        if hasattr(self, 'skip_frame_button'):
            self.skip_frame_button.config(state=tk.DISABLED)

        preselected_count = len(self.preselected_positions)

        if preselected_count > 0:
            # Auto-save what we have so far
            self.auto_save_star_positions()

            # Enable batch processing button
            self.batch_process_button.config(state=tk.NORMAL)
            
            self.log_status(f"Pre-selection stopped early - saved {preselected_count} positions")
            
            # Show message about partial completion
            completion_msg = (f"Pre-selection stopped early!\n\n"
                            f"Saved positions: {preselected_count} frames\n"
                            f"Total frames: {len(self.fits_files)}\n\n"
                            f"Your progress has been automatically saved.")
            
            messagebox.showinfo("Pre-selection Stopped - Progress Saved", completion_msg)
        else:
            self.log_status("Pre-selection stopped - no positions selected")
        
        # Reset to first image
        self.load_first_image()

    def load_frame_for_preselection(self, frame_index):
        """Load a specific frame for pre-selection (Phase 1)"""
        if frame_index >= len(self.fits_files):
            # All frames pre-selected, finish Phase 1
            self.finish_preselection_phase()
            return

        # Check if this frame already has a preselected position
        if frame_index < len(self.preselected_positions):
            self.log_status(f"Frame {frame_index + 1} already has preselected position - skipping to next")
            self.current_frame_index = frame_index + 1
            self.root.after(100, lambda: self.load_frame_for_preselection(self.current_frame_index))
            return

        try:
            fits_file = self.fits_files[frame_index]
            filename = os.path.basename(fits_file)

            self.log_status(f"Pre-select frame {frame_index + 1}/{len(self.fits_files)}: {filename}")

            # Update frame counter
            self.update_frame_counter(frame_index, len(self.fits_files), "Pre-selecting")

            # Update progress bar during pre-selection
            progress = (frame_index / len(self.fits_files)) * 100
            self.progress_var.set(progress)

            # Load the image
            with fits.open(fits_file) as hdul:
                image_data = hdul[0].data
                header = hdul[0].header

                # Store current image data
                self.current_image_data = image_data
                self.current_image_header = header

                # Handle RGB vs grayscale
                if len(image_data.shape) == 3 and image_data.shape[0] == 3:
                    self.current_image_rgb = image_data.copy()
                    self.current_image_grayscale = np.mean(image_data, axis=0)
                else:
                    self.current_image_rgb = None
                    self.current_image_grayscale = image_data

            # Display the frame with counter in title
            self.display_image(show_aperture=False)

            # Set title to show frame counter and filename during preselection
            title = f"Pre-selecting - Frame {frame_index + 1}/{len(self.fits_files)}: {filename} - Click on star"
            self.ax.set_title(title)
            self.canvas.draw()

            # Auto-center on previous star position if we have one and zoom is active
            if frame_index > 0 and len(self.preselected_positions) > 0 and self.zoom_active:
                # Find the most recent valid preselected position
                prev_star_pos = None
                for i in range(len(self.preselected_positions) - 1, -1, -1):
                    if self.preselected_positions[i] is not None:
                        prev_star_pos = self.preselected_positions[i]
                        break

                if prev_star_pos is not None:
                    # Calculate zoom size (same as sequential tracking)
                    outer_radius = self.aperture_params['outer_annulus']
                    zoom_size = max(30, min(200, outer_radius * 3))

                    # Center the view on the previous star position
                    self.ax.set_xlim(prev_star_pos[0] - zoom_size, prev_star_pos[0] + zoom_size)
                    self.ax.set_ylim(prev_star_pos[1] - zoom_size, prev_star_pos[1] + zoom_size)

                    self.log_status(f"Auto-centered on previous position ({prev_star_pos[0]:.1f}, {prev_star_pos[1]:.1f})")
                else:
                    self.log_status("No previous position found for auto-centering")

            # NEW: Automatic star tracking for frames after the first one
            if (self.tracking_enabled_var.get() and
                frame_index > 0 and
                len(self.preselected_positions) > 0 and
                not self.stop_preselection and
                not self.paused):  # Don't auto-track while paused

                # Find the most recent valid preselected position for tracking
                prev_pos = None
                for i in range(len(self.preselected_positions) - 1, -1, -1):
                    if self.preselected_positions[i] is not None:
                        prev_pos = self.preselected_positions[i]
                        break

                if prev_pos is not None:
                    try:
                        # Determine tracking data
                        tracking_data = self.current_image_grayscale if self.current_image_grayscale is not None else self.current_image_data
                        if len(tracking_data.shape) == 3 and tracking_data.shape[0] == 3:
                            tracking_data = np.mean(tracking_data, axis=0)

                        # Attempt automatic tracking with user-configured search radius
                        search_radius = self.search_radius_var.get()
                        tracked_pos = self.track_star_position(tracking_data, prev_pos, search_radius)

                        if tracked_pos is not None:
                            # Successful automatic tracking - store at correct index
                            while len(self.preselected_positions) <= frame_index:
                                self.preselected_positions.append(None)
                            self.preselected_positions[frame_index] = tracked_pos
                            self.log_status(f"AUTO-TRACKED: Star found at ({tracked_pos[0]:.1f}, {tracked_pos[1]:.1f})")

                            # Update processed counter
                            processed = len([pos for pos in self.preselected_positions if pos is not None])
                            self.update_processed_counter(processed, len(self.fits_files))

                            # Show aperture overlay to confirm auto-tracking worked
                            self.selected_star_pos = tracked_pos
                            self.display_image(show_aperture=True)

                            # Auto-advance to next frame after successful tracking
                            self.root.after(500, self.advance_to_next_preselection_frame)
                            return
                        else:
                            self.log_status(f"Auto-tracking failed - please click to select star position")
                    except Exception as e:
                        self.logger.warning(f"Auto-tracking error: {e}")
                        self.log_status(f"Auto-tracking error - please click to select star position")

            # Set title to show pre-selection mode (updated for auto-tracking status)
            if self.tracking_enabled_var.get() and frame_index > 0 and len(self.preselected_positions) > 0:
                title = f"Pre-select {frame_index + 1}/{len(self.fits_files)} - Auto-tracking"
            else:
                title = f"Pre-select {frame_index + 1}/{len(self.fits_files)} - Click star"
            self.ax.set_title(title)
            self.canvas.draw()

            # Update progress - pre-selection uses the full progress bar
            progress = (frame_index / len(self.fits_files)) * 100
            self.progress_var.set(progress)

        except Exception as e:
            self.log_status(f"Error loading frame {frame_index + 1}: {e}")
            messagebox.showerror("Frame Load Error", f"Failed to load frame {frame_index + 1}: {e}")
            self.finish_preselection_phase()

    def on_preselection_click(self, event):
        """Handle clicks during pre-selection mode (Phase 1)"""
        if not self.preselection_mode:
            return False

        if event.inaxes != self.ax:
            return False

        if event.xdata is None or event.ydata is None:
            return False

        x, y = event.xdata, event.ydata

        # Handle clicks during preselection pause (for position updates)
        if getattr(self, 'preselection_paused', False):
            self.update_preselection_position_during_pause(x, y, event)
            return True

        # Handle clicks for setting resume reference point in auto-tracking mode
        if getattr(self, 'waiting_for_resume_reference', False):
            self.set_resume_reference_point(x, y)
            return True

        # Apply star tracking if enabled
        if self.tracking_enabled_var.get() and self.current_image_data is not None:
            try:
                # Determine which data to use for tracking
                if hasattr(self, 'current_image_grayscale') and self.current_image_grayscale is not None:
                    tracking_data = self.current_image_grayscale
                else:
                    # Use original data if no grayscale version
                    tracking_data = self.current_image_data
                    # If RGB, convert to grayscale for tracking
                    if len(tracking_data.shape) == 3 and tracking_data.shape[0] == 3:
                        tracking_data = np.mean(tracking_data, axis=0)

                # Track star position using the clicked position as initial guess
                # Use user-configured search radius for manual clicks too
                search_radius = self.search_radius_var.get()
                tracked_pos = self.track_star_position(tracking_data, (x, y), search_radius)
                
                if tracked_pos is not None:
                    star_pos = tracked_pos
                    self.log_status(f"Star tracked to ({tracked_pos[0]:.1f}, {tracked_pos[1]:.1f}) from click ({x:.1f}, {y:.1f})")
                else:
                    # Fall back to clicked position if tracking fails
                    star_pos = (x, y)
                    self.log_status(f"Star tracking failed - using clicked position ({x:.1f}, {y:.1f})")
            except Exception as e:
                # Fall back to clicked position if any error occurs
                star_pos = (x, y)
                self.logger.warning(f"Star tracking error in preselection: {e}")
                self.log_status(f"Star tracking error - using clicked position ({x:.1f}, {y:.1f})")
        else:
            # Star tracking disabled - use clicked position directly
            star_pos = (x, y)

        # Store the pre-selected position at the correct index (either tracked or clicked)
        # Extend the list if necessary to accommodate this frame index
        while len(self.preselected_positions) <= self.current_frame_index:
            self.preselected_positions.append(None)

        self.preselected_positions[self.current_frame_index] = star_pos

        # Update position text only - skip expensive aperture display
        # Removed redundant position display as it shows in the visual display already

        # Move to next frame immediately with minimal delay for faster workflow
        self.root.after(100, self.advance_to_next_preselection_frame)

        return True  # Indicate we handled the click

    def advance_to_next_preselection_frame(self):
        """Move to the next frame in pre-selection"""
        # Check if preselection is paused - if so, don't advance
        if getattr(self, 'preselection_paused', False):
            self.log_status("Pre-selection paused - auto-advance stopped")
            return

        self.current_frame_index += 1
        self.load_frame_for_preselection(self.current_frame_index)

    def finish_preselection_phase(self):
        """Complete Phase 1 - pre-selection process finished"""
        self.preselection_mode = False

        # Disable navigation buttons
        if hasattr(self, 'go_back_button'):
            self.go_back_button.config(state=tk.DISABLED)
        if hasattr(self, 'skip_frame_button'):
            self.skip_frame_button.config(state=tk.DISABLED)

        preselected_count = len(self.preselected_positions)
        total_count = len(self.fits_files)

        # Set progress to 100% to show pre-selection is complete
        self.progress_var.set(100)

        # Update counters to show completion
        self.update_frame_counter(len(self.fits_files) - 1, len(self.fits_files), "Pre-selection Complete")
        self.update_processed_counter(preselected_count, len(self.fits_files))

        # Auto-save star positions to positions folder
        if preselected_count > 0:
            self.auto_save_star_positions()

        # Update button states
        self.preselect_button.config(state=tk.NORMAL, text="Pre-select Positions")

        if preselected_count > 0:
            self.batch_process_button.config(state=tk.NORMAL)

            # Phase 1 complete - user can now choose to run Phase 2 manually
            self.log_status("Pre-selection completed. Click 'Run Photometry' to analyze stars.")
            messagebox.showinfo("Pre-selection Complete",
                              f"Pre-selection completed successfully!\n\n"
                              f"Pre-selected positions: {preselected_count}/{total_count} frames\n\n"
                              f"Next step: Click 'Process All Pre-selections' button to run photometry analysis.")
        else:
            messagebox.showwarning("No Selections", "No star positions found. Please run Pre-select Positions first.")
            # Reset to first image
            self.load_first_image()

    def start_automatic_batch_processing(self):
        """Start automatic batch processing using preselected positions"""
        # Initialize batch processing
        self.batch_processing_mode = True
        self.processing = True
        self.stop_processing = False
        self.photometry_results = []

        # IMPROVED: Reset tracking history for new batch session
        self.position_history = []
        self.velocity_history = []
        self.tracking_confidence = []

        # Update button states
        self.batch_process_button.config(state=tk.DISABLED, text="Processing...")
        self.stop_button.config(state=tk.NORMAL)

        self.log_status("Starting automatic batch processing...")
        self.log_status(f"Processing {len(self.preselected_positions)} frames automatically")

        # Initialize counters
        self.update_frame_counter(0, len(self.preselected_positions), "Processing")
        self.update_processed_counter(0, len(self.preselected_positions))

        # Start batch processing thread
        thread = threading.Thread(target=self.process_batch_photometry)
        thread.daemon = True
        thread.start()

    def start_manual_tracking_mode(self):
        """Start manual tracking mode using preselected positions"""
        # Initialize sequential tracking state using preselected positions
        self.sequential_mode = True
        self.current_frame_index = 0
        self.frame_positions = self.preselected_positions.copy()  # Use preselected as starting points
        self.sequential_results = []
        self.photometry_results = []

        # Keep navigation buttons DISABLED during active processing
        # They will only be enabled when user pauses
        if hasattr(self, 'go_back_button'):
            self.go_back_button.config(state=tk.DISABLED)
        if hasattr(self, 'skip_frame_button'):
            self.skip_frame_button.config(state=tk.DISABLED)

        self.log_status("Starting manual tracking mode...")
        self.log_status(f"Click to refine positions for {len(self.preselected_positions)} frames")
        self.log_status("Use navigation buttons to go back or skip frames")

        # Start with the first frame
        self.load_frame_for_tracking(0)

    def start_batch_processing(self):
        """Start Phase 2: Process all pre-selected positions from CSV file"""
        # Open file browser to select positions CSV file
        current_dir = os.getcwd()
        positions_dir = os.path.join(current_dir, "positions")
        
        # Use positions directory if it exists, otherwise current directory
        initial_dir = positions_dir if os.path.exists(positions_dir) else current_dir
        
        filename = filedialog.askopenfilename(
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            title="Select star positions CSV file for batch processing",
            initialdir=initial_dir
        )
        
        if not filename:
            return
            
        # Load positions from CSV file
        try:
            positions = []
            star_name = ""
            folder_path = ""
            fits_file_paths = []
            
            with open(filename, 'r') as csvfile:
                reader = csv.DictReader(csvfile)
                
                for row in reader:
                    x = float(row['x_position'])
                    y = float(row['y_position'])
                    positions.append((x, y))
                    
                    # Get star name from first row
                    if not star_name:
                        star_name = row.get('star_name', '')
                        
                    # Get folder path from first row
                    if not folder_path:
                        folder_path = row.get('folder_path', '')
                        
                    # Collect file paths
                    full_file_path = row.get('full_file_path', '')
                    if full_file_path:
                        fits_file_paths.append(full_file_path)
                        
                    # Skip loading aperture parameters from CSV - use current GUI values instead
            
            if not positions:
                messagebox.showerror("No Positions", "No valid star positions found in the selected CSV file.")
                return
                
            # Auto-load FITS files if folder path is available and files aren't already loaded
            if folder_path and not self.fits_files:
                if os.path.exists(folder_path):
                    self.fits_files = sorted(glob.glob(os.path.join(folder_path, "*.fit*")))
                    if self.fits_files:
                        self.file_count_label.config(text=f"{len(self.fits_files)} FITS files auto-loaded")
                        self.load_first_image()
                        self.log_status(f"Auto-loaded {len(self.fits_files)} FITS files from saved folder path")
                    else:
                        self.log_status(f"Warning: No FITS files found in saved folder: {folder_path}")
                else:
                    self.log_status(f"Warning: Saved folder path not found: {folder_path}")
            elif fits_file_paths:
                # Try to use specific file paths if available
                valid_files = [f for f in fits_file_paths if os.path.exists(f)]
                if valid_files and not self.fits_files:
                    self.fits_files = valid_files
                    self.file_count_label.config(text=f"{len(self.fits_files)} FITS files auto-loaded")
                    self.load_first_image()
                    self.log_status(f"Auto-loaded {len(self.fits_files)} FITS files from saved file paths")
                
            # Update application state with loaded positions
            self.preselected_positions = positions
            
            # Update star name if provided
            if star_name:
                self.star_name_var.set(star_name)
                self.star_name = star_name
            
            # Use current GUI aperture values (don't load from CSV)
            self.log_status(f"Using current aperture radii: {self.aperture_params['inner_radius']:.1f}, {self.aperture_params['inner_annulus']:.1f}, {self.aperture_params['outer_annulus']:.1f}")
                
            self.log_status(f"Loaded {len(positions)} positions from {os.path.basename(filename)}")
            
        except Exception as e:
            messagebox.showerror("Load Error", f"Failed to load positions file:\n{str(e)}\n\nPlease check the file format.")
            return
        
        # Confirm batch processing
        response = messagebox.askyesno(
            "Start Batch Processing",
            f"Process photometry for {len(self.preselected_positions)} positions from CSV?\n\n"
            f"File: {os.path.basename(filename)}\n"
            f"Star: {star_name or 'unnamed'}\n\n"
            f"This will run in the background while you can do other tasks.\n\n"
            f"Click 'Yes' to start batch processing."
        )

        if not response:
            return

        # Initialize batch processing
        self.batch_processing_mode = True
        self.processing = True
        self.stop_processing = False
        self.photometry_results = []

        # IMPROVED: Reset tracking history for CSV batch session
        self.position_history = []
        self.velocity_history = []
        self.tracking_confidence = []

        # Update button states
        self.batch_process_button.config(state=tk.DISABLED, text="Processing...")
        self.stop_button.config(state=tk.NORMAL)

        self.log_status("Starting auto processing from saved positions...")
        self.log_status(f"Processing {len(self.preselected_positions)} frames in background")
        self.log_status("You can now do other tasks while processing continues")

        # Start batch processing thread
        thread = threading.Thread(target=self.process_batch_photometry)
        thread.daemon = True
        thread.start()

    def process_batch_photometry(self):
        """Process photometry for all pre-selected positions (Phase 2)"""
        try:
            self.log_status(f"Batch processing started: {self.star_name}")
            self.log_status(f"Processing {len(self.preselected_positions)} pre-selected frames...")

            for i, (fits_file, star_pos) in enumerate(zip(self.fits_files[:len(self.preselected_positions)], self.preselected_positions)):
                if self.stop_processing:
                    self.log_status("Batch processing stopped by user")
                    break
                
                # Wait while paused
                while self.paused and not self.stop_processing:
                    time.sleep(0.1)
                    
                # Check stop again after pause
                if self.stop_processing:
                    self.log_status("Batch processing stopped by user")
                    break

                # Update progress (Phase 2 is 50% to 100%)
                progress = 50 + (i / len(self.preselected_positions)) * 50
                self.progress_var.set(progress)

                # Process single image with pre-selected position
                result = self.process_single_image(fits_file, star_pos, i)

                if result is not None:
                    self.photometry_results.append(result)

                if i % 5 == 0:  # Log every 5 images
                    self.log_status(f"Batch processed {i+1}/{len(self.preselected_positions)} frames")
                    # Update counters every 5 frames
                    self.root.after(0, lambda idx=i: self.update_processed_counter(idx+1, len(self.preselected_positions)))

            self.progress_var.set(100)

            # Update final counter
            final_count = len(self.preselected_positions)
            self.root.after(0, lambda: self.update_frame_counter(final_count - 1, final_count, "Batch Complete"))
            self.root.after(0, lambda: self.update_processed_counter(len(self.photometry_results), final_count))

            if not self.stop_processing:
                self.log_status(f"Batch processing completed!")
                self.log_status(f"Successfully processed {len(self.photometry_results)} frames")

                # Enable result buttons
                self.enable_result_buttons()

                # Schedule GUI operations on main thread to prevent freezing
                self.root.after(0, self.batch_completion_gui_updates)

        except Exception as e:
            self.log_status(f"Error during batch processing: {e}")
            messagebox.showerror("Batch Processing Error", str(e))

        finally:
            # Reset states
            self.batch_processing_mode = False
            self.processing = False
            self.batch_process_button.config(state=tk.NORMAL, text="2. Process All Pre-selections")
            self.stop_button.config(state=tk.DISABLED)

    def save_results(self):
        """Save photometry results to CSV file"""
        if not self.photometry_results:
            messagebox.showwarning("No Results", "No photometry results to save")
            return

        # Use current working directory for results - easier to find
        import os
        current_dir = os.getcwd()
        results_dir = os.path.join(current_dir, "results")

        # Create results directory if it doesn't exist
        try:
            os.makedirs(results_dir, exist_ok=True)
            self.log_status(f"Using results directory: {results_dir}")
        except Exception as e:
            self.log_status(f"Could not create results directory: {e}")
            results_dir = current_dir  # Fallback to current directory

        default_filename = f"{self.star_name}_photometry_{len(self.photometry_results)}images.csv"

        filename = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile=default_filename,
            initialdir=results_dir,
            title=f"Save {len(self.photometry_results)} photometry results"
        )

        if filename:
            try:
                with open(filename, 'w', newline='') as csvfile:
                    if self.photometry_results:
                        fieldnames = list(self.photometry_results[0].keys())
                        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

                        writer.writeheader()
                        for result in self.photometry_results:
                            writer.writerow(result)

                # Show success with clear file location
                file_dir = os.path.dirname(filename)
                file_name = os.path.basename(filename)
                self.log_status(f"✓ CSV saved: {file_name}")
                self.log_status(f"  Location: {file_dir}")

                # Results are saved - buttons should already be enabled
                self.enable_result_buttons()

                # More prominent success message
                success_msg = (f"✓ Photometry results saved successfully!\n\n"
                             f"File: {file_name}\n"
                             f"Location: {file_dir}\n"
                             f"Records: {len(self.photometry_results)} images\n\n"
                             f"You can now open this CSV file in Excel, Python, or any data analysis software.")

                messagebox.showinfo("Results Saved Successfully", success_msg)

            except Exception as e:
                error_msg = f"Failed to save CSV file:\n{str(e)}\n\nTry saving to a different location."
                messagebox.showerror("Save Error", error_msg)

    def auto_save_results(self):
        """Automatically save results without user dialog"""
        if not self.photometry_results:
            return
            
        try:
            # Create results directory
            current_dir = os.getcwd()
            results_dir = os.path.join(current_dir, "results")
            os.makedirs(results_dir, exist_ok=True)
            
            # Generate filename with timestamp
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = os.path.join(results_dir, f"{self.star_name}_photometry_{timestamp}.csv")
            
            # Save CSV file
            with open(filename, 'w', newline='') as csvfile:
                if self.photometry_results:
                    fieldnames = list(self.photometry_results[0].keys())
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                    writer.writeheader()
                    for result in self.photometry_results:
                        writer.writerow(result)
            
            self.log_status(f"Results auto-saved: {os.path.basename(filename)}")
            self.log_status(f"  Location: {results_dir}")
            
        except Exception as e:
            self.log_status(f"Auto-save failed: {e}")

    def auto_open_visualization(self):
        """Automatically open visualization window"""
        try:
            # Use the existing visualization function
            self.open_visualization_window()
            self.log_status("✓ Visualization window opened automatically")
        except Exception as e:
            self.log_status(f"Auto-visualization failed: {e}")

    def batch_completion_gui_updates(self):
        """Handle GUI updates after batch processing completion - runs on main thread"""
        try:
            # Auto-save results immediately
            self.auto_save_results()

            # Auto-open visualization window (now safely on main thread)
            self.auto_open_visualization()

            # Show completion message for Phase 2
            success_msg = (f"Auto processing completed successfully!\n\n"
                         f"Processed: {len(self.photometry_results)} frames\n"
                         f"Pre-selected: {len(self.preselected_positions)} frames\n\n"
                         f"Results automatically saved and visualization opened.")

            messagebox.showinfo("Batch Processing Complete", success_msg)
            
        except Exception as e:
            self.log_status(f"Error in batch completion updates: {e}")

    def open_visualization_window(self):
        """Open a new window for data visualization"""
        if not self.photometry_results:
            messagebox.showwarning("No Data", "No photometry results available for visualization.\nPlease run photometry first.")
            return

        if self.viz_window and self.viz_window.winfo_exists():
            # Window already exists, bring it to front
            self.viz_window.lift()
            self.viz_window.focus_force()
            return

        # Create new visualization window
        self.viz_window = tk.Toplevel(self.root)
        self.viz_window.title(f"Photometry Data Visualization - {self.star_name}")
        self.viz_window.geometry("1600x1200")

        # Create notebook for multiple tabs
        notebook = ttk.Notebook(self.viz_window)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Create tabs
        self.setup_lightcurve_tab(notebook)
        self.setup_rgb_comparison_tab(notebook)
        self.setup_quality_metrics_tab(notebook)
        self.setup_tracking_tab(notebook)

        # Update all plots
        self.update_all_plots()

        self.log_status("Visualization window opened")

    def setup_lightcurve_tab(self, parent):
        """Setup the light curve visualization tab"""
        frame = ttk.Frame(parent)
        parent.add(frame, text="Light Curves")

        # Create matplotlib figure with proper spacing
        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(16, 12))
        fig.suptitle('Star Light Curves Analysis', fontsize=16, fontweight='bold')
        plt.subplots_adjust(hspace=0.4, wspace=0.3)

        self.viz_figures['lightcurve'] = fig
        self.viz_axes['lightcurve'] = {
            'combined': ax1,
            'rgb_separate': ax2,
            'raw_vs_corrected': ax3,
            'snr': ax4
        }

        canvas = FigureCanvasTkAgg(fig, frame)
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def setup_rgb_comparison_tab(self, parent):
        """Setup RGB channel comparison tab"""
        frame = ttk.Frame(parent)
        parent.add(frame, text="RGB Analysis")

        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(16, 12))
        fig.suptitle('RGB Channel Analysis', fontsize=16, fontweight='bold')
        plt.subplots_adjust(hspace=0.4, wspace=0.3)

        self.viz_figures['rgb'] = fig
        self.viz_axes['rgb'] = {
            'channels': ax1,
            'ratios': ax2,
            'color_index': ax3,
            'channel_noise': ax4
        }

        canvas = FigureCanvasTkAgg(fig, frame)
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def setup_quality_metrics_tab(self, parent):
        """Setup data quality metrics tab"""
        frame = ttk.Frame(parent)
        parent.add(frame, text="Quality Metrics")

        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(16, 12))
        fig.suptitle('Data Quality Analysis', fontsize=16, fontweight='bold')
        plt.subplots_adjust(hspace=0.4, wspace=0.3)

        self.viz_figures['quality'] = fig
        self.viz_axes['quality'] = {
            'sky_background': ax1,
            'sky_noise': ax2,
            'poisson_noise': ax3,
            'total_snr': ax4
        }

        canvas = FigureCanvasTkAgg(fig, frame)
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def setup_tracking_tab(self, parent):
        """Setup star tracking analysis tab"""
        frame = ttk.Frame(parent)
        parent.add(frame, text="Tracking Analysis")

        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(16, 12))
        fig.suptitle('Star Tracking Analysis', fontsize=16, fontweight='bold')
        plt.subplots_adjust(hspace=0.4, wspace=0.3)

        self.viz_figures['tracking'] = fig
        self.viz_axes['tracking'] = {
            'position_drift': ax1,
            'movement_per_frame': ax2,
            'position_scatter': ax3,
            'drift_stats': ax4
        }

        canvas = FigureCanvasTkAgg(fig, frame)
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def update_all_plots(self):
        """Update all visualization plots with current data"""
        if not self.photometry_results or not hasattr(self, 'viz_figures'):
            return

        try:
            self.update_lightcurve_plots()
            self.update_rgb_plots()
            self.update_quality_plots()
            self.update_tracking_plots()

            # Refresh all canvases
            for fig in self.viz_figures.values():
                fig.canvas.draw()

            self.log_status("All plots updated successfully")

        except Exception as e:
            self.log_status(f"Error updating plots: {e}")
            self.logger.error(f"Visualization update error: {e}")

    def update_lightcurve_plots(self):
        """Update light curve plots"""
        data = self.photometry_results
        indices = [r['image_index'] for r in data]

        # Determine if we have RGB data
        has_rgb = any('r_flux_corrected' in r for r in data)

        axes = self.viz_axes['lightcurve']

        # Clear all axes
        for ax in axes.values():
            ax.clear()

        if has_rgb:
            # RGB + Grayscale combined plot
            r_flux = [r.get('r_flux_corrected', 0) for r in data]
            g_flux = [r.get('g_flux_corrected', 0) for r in data]
            b_flux = [r.get('b_flux_corrected', 0) for r in data]
            gray_flux = [r.get('gray_flux_corrected', 0) for r in data]

            axes['combined'].plot(indices, r_flux, 'r-', label='Red', linewidth=2, alpha=0.8)
            axes['combined'].plot(indices, g_flux, 'g-', label='Green', linewidth=2, alpha=0.8)
            axes['combined'].plot(indices, b_flux, 'b-', label='Blue', linewidth=2, alpha=0.8)
            axes['combined'].plot(indices, gray_flux, 'k-', label='Grayscale', linewidth=2, alpha=0.6)
            axes['combined'].set_title('Combined RGB + Grayscale Light Curves')
            axes['combined'].set_xlabel('Image Index')
            axes['combined'].set_ylabel('Flux (ADU)')
            axes['combined'].legend()
            axes['combined'].grid(True, alpha=0.3)

            # RGB channels separate
            axes['rgb_separate'].plot(indices, r_flux, 'r-', label='Red', linewidth=3)
            axes['rgb_separate'].plot(indices, g_flux, 'g-', label='Green', linewidth=3)
            axes['rgb_separate'].plot(indices, b_flux, 'b-', label='Blue', linewidth=3)
            axes['rgb_separate'].set_title('RGB Channels Comparison')
            axes['rgb_separate'].set_xlabel('Image Index')
            axes['rgb_separate'].set_ylabel('Flux (ADU)')
            axes['rgb_separate'].legend()
            axes['rgb_separate'].grid(True, alpha=0.3)

            # Raw vs Corrected (using grayscale)
            raw_flux = [r.get('gray_star_flux_raw', 0) for r in data]
            axes['raw_vs_corrected'].plot(indices, raw_flux, 'r-', label='Raw Flux', linewidth=2, alpha=0.7)
            axes['raw_vs_corrected'].plot(indices, gray_flux, 'b-', label='Sky-Corrected Flux', linewidth=2)
            axes['raw_vs_corrected'].set_title('Raw vs Sky-Corrected Flux')
            axes['raw_vs_corrected'].set_xlabel('Image Index')
            axes['raw_vs_corrected'].set_ylabel('Flux (ADU)')
            axes['raw_vs_corrected'].legend()
            axes['raw_vs_corrected'].grid(True, alpha=0.3)

            # Signal-to-Noise Ratios
            r_snr = [r.get('r_flux_corrected', 0) / max(r.get('r_poisson_noise', 1), 1) for r in data]
            g_snr = [r.get('g_flux_corrected', 0) / max(r.get('g_poisson_noise', 1), 1) for r in data]
            b_snr = [r.get('b_flux_corrected', 0) / max(r.get('b_poisson_noise', 1), 1) for r in data]

            axes['snr'].plot(indices, r_snr, 'r-', label='Red S/N', linewidth=2)
            axes['snr'].plot(indices, g_snr, 'g-', label='Green S/N', linewidth=2)
            axes['snr'].plot(indices, b_snr, 'b-', label='Blue S/N', linewidth=2)

        else:
            # Grayscale only
            gray_flux = [r.get('gray_flux_corrected', 0) for r in data]
            raw_flux = [r.get('gray_star_flux_raw', 0) for r in data]

            axes['combined'].plot(indices, gray_flux, 'k-', linewidth=3, label='Star Flux')
            axes['combined'].set_title('Grayscale Light Curve')
            axes['combined'].set_xlabel('Image Index')
            axes['combined'].set_ylabel('Flux (ADU)')
            axes['combined'].legend()
            axes['combined'].grid(True, alpha=0.3)

            # Raw vs Corrected
            axes['raw_vs_corrected'].plot(indices, raw_flux, 'r-', label='Raw Flux', linewidth=2, alpha=0.7)
            axes['raw_vs_corrected'].plot(indices, gray_flux, 'b-', label='Sky-Corrected Flux', linewidth=2)
            axes['raw_vs_corrected'].set_title('Raw vs Sky-Corrected Flux')
            axes['raw_vs_corrected'].set_xlabel('Image Index')
            axes['raw_vs_corrected'].set_ylabel('Flux (ADU)')
            axes['raw_vs_corrected'].legend()
            axes['raw_vs_corrected'].grid(True, alpha=0.3)

            # Signal-to-Noise
            snr = [r.get('gray_flux_corrected', 0) / max(r.get('gray_poisson_noise', 1), 1) for r in data]
            axes['snr'].plot(indices, snr, 'k-', linewidth=3, label='S/N Ratio')

            # Show RGB plot as "No RGB data"
            axes['rgb_separate'].text(0.5, 0.5, 'No RGB Data Available\n(Grayscale only)',
                                    transform=axes['rgb_separate'].transAxes,
                                    ha='center', va='center', fontsize=16, alpha=0.5)
            axes['rgb_separate'].set_title('RGB Channels (Not Available)')

        axes['snr'].set_title('Signal-to-Noise Ratio')
        axes['snr'].set_xlabel('Image Index')
        axes['snr'].set_ylabel('S/N Ratio')
        axes['snr'].legend()
        axes['snr'].grid(True, alpha=0.3)

    def update_rgb_plots(self):
        """Update RGB-specific analysis plots"""
        data = self.photometry_results
        has_rgb = any('r_flux_corrected' in r for r in data)

        axes = self.viz_axes['rgb']

        # Clear all axes
        for ax in axes.values():
            ax.clear()

        if not has_rgb:
            # Show "No RGB data" message on all plots
            for ax_name, ax in axes.items():
                ax.text(0.5, 0.5, 'No RGB Data Available\n(Grayscale images only)',
                       transform=ax.transAxes, ha='center', va='center',
                       fontsize=16, alpha=0.5)
                ax.set_title(f'{ax_name.replace("_", " ").title()} (RGB Not Available)')
            return

        indices = [r['image_index'] for r in data]
        r_flux = [r.get('r_flux_corrected', 0) for r in data]
        g_flux = [r.get('g_flux_corrected', 0) for r in data]
        b_flux = [r.get('b_flux_corrected', 0) for r in data]

        # Channel comparison
        axes['channels'].plot(indices, r_flux, 'r-', label='Red', linewidth=3, alpha=0.8)
        axes['channels'].plot(indices, g_flux, 'g-', label='Green', linewidth=3, alpha=0.8)
        axes['channels'].plot(indices, b_flux, 'b-', label='Blue', linewidth=3, alpha=0.8)
        axes['channels'].set_title('RGB Channel Flux Comparison')
        axes['channels'].set_xlabel('Image Index')
        axes['channels'].set_ylabel('Flux (ADU)')
        axes['channels'].legend()
        axes['channels'].grid(True, alpha=0.3)

        # Color ratios
        r_g_ratio = [r/max(g, 1) for r, g in zip(r_flux, g_flux)]
        b_g_ratio = [b/max(g, 1) for b, g in zip(b_flux, g_flux)]
        r_b_ratio = [r/max(b, 1) for r, b in zip(r_flux, b_flux)]

        axes['ratios'].plot(indices, r_g_ratio, 'orange', label='Red/Green', linewidth=2)
        axes['ratios'].plot(indices, b_g_ratio, 'purple', label='Blue/Green', linewidth=2)
        axes['ratios'].plot(indices, r_b_ratio, 'brown', label='Red/Blue', linewidth=2)
        axes['ratios'].set_title('Color Ratios Over Time')
        axes['ratios'].set_xlabel('Image Index')
        axes['ratios'].set_ylabel('Flux Ratio')
        axes['ratios'].legend()
        axes['ratios'].grid(True, alpha=0.3)

        # Color index (astronomical)
        b_v_index = [-2.5 * np.log10(max(b, 1) / max(g, 1)) for b, g in zip(b_flux, g_flux)]
        v_r_index = [-2.5 * np.log10(max(g, 1) / max(r, 1)) for g, r in zip(g_flux, r_flux)]

        axes['color_index'].plot(indices, b_v_index, 'cyan', label='B-V Index', linewidth=2)
        axes['color_index'].plot(indices, v_r_index, 'magenta', label='V-R Index', linewidth=2)
        axes['color_index'].set_title('Astronomical Color Indices')
        axes['color_index'].set_xlabel('Image Index')
        axes['color_index'].set_ylabel('Color Index (mag)')
        axes['color_index'].legend()
        axes['color_index'].grid(True, alpha=0.3)

        # Channel noise comparison
        r_noise = [r.get('r_poisson_noise', 0) for r in data]
        g_noise = [r.get('g_poisson_noise', 0) for r in data]
        b_noise = [r.get('b_poisson_noise', 0) for r in data]

        axes['channel_noise'].plot(indices, r_noise, 'r-', label='Red Noise', linewidth=2, alpha=0.7)
        axes['channel_noise'].plot(indices, g_noise, 'g-', label='Green Noise', linewidth=2, alpha=0.7)
        axes['channel_noise'].plot(indices, b_noise, 'b-', label='Blue Noise', linewidth=2, alpha=0.7)
        axes['channel_noise'].set_title('Poisson Noise by Channel')
        axes['channel_noise'].set_xlabel('Image Index')
        axes['channel_noise'].set_ylabel('Poisson Noise (ADU)')
        axes['channel_noise'].legend()
        axes['channel_noise'].grid(True, alpha=0.3)

    def update_quality_plots(self):
        """Update data quality metric plots"""
        data = self.photometry_results
        indices = [r['image_index'] for r in data]

        axes = self.viz_axes['quality']

        # Clear all axes
        for ax in axes.values():
            ax.clear()

        # Sky background levels
        has_rgb = any('r_sky_per_pixel' in r for r in data)

        if has_rgb:
            r_sky = [r.get('r_sky_per_pixel', 0) for r in data]
            g_sky = [r.get('g_sky_per_pixel', 0) for r in data]
            b_sky = [r.get('b_sky_per_pixel', 0) for r in data]
            gray_sky = [r.get('gray_sky_per_pixel', 0) for r in data]

            axes['sky_background'].plot(indices, r_sky, 'r-', label='Red Sky', linewidth=2, alpha=0.7)
            axes['sky_background'].plot(indices, g_sky, 'g-', label='Green Sky', linewidth=2, alpha=0.7)
            axes['sky_background'].plot(indices, b_sky, 'b-', label='Blue Sky', linewidth=2, alpha=0.7)
            axes['sky_background'].plot(indices, gray_sky, 'k-', label='Grayscale Sky', linewidth=2)
        else:
            gray_sky = [r.get('gray_sky_per_pixel', 0) for r in data]
            axes['sky_background'].plot(indices, gray_sky, 'k-', linewidth=3, label='Sky Background')

        axes['sky_background'].set_title('Sky Background Variation')
        axes['sky_background'].set_xlabel('Image Index')
        axes['sky_background'].set_ylabel('Sky Level (ADU/pixel)')
        axes['sky_background'].legend()
        axes['sky_background'].grid(True, alpha=0.3)

        # Sky noise (standard deviation)
        if has_rgb:
            r_sky_std = [r.get('r_sky_std', 0) for r in data]
            g_sky_std = [r.get('g_sky_std', 0) for r in data]
            b_sky_std = [r.get('b_sky_std', 0) for r in data]
            gray_sky_std = [r.get('gray_sky_std', 0) for r in data]

            axes['sky_noise'].plot(indices, r_sky_std, 'r-', label='Red Sky σ', linewidth=2, alpha=0.7)
            axes['sky_noise'].plot(indices, g_sky_std, 'g-', label='Green Sky σ', linewidth=2, alpha=0.7)
            axes['sky_noise'].plot(indices, b_sky_std, 'b-', label='Blue Sky σ', linewidth=2, alpha=0.7)
            axes['sky_noise'].plot(indices, gray_sky_std, 'k-', label='Gray Sky σ', linewidth=2)
        else:
            gray_sky_std = [r.get('gray_sky_std', 0) for r in data]
            axes['sky_noise'].plot(indices, gray_sky_std, 'k-', linewidth=3, label='Sky Noise')

        axes['sky_noise'].set_title('Sky Background Noise (σ)')
        axes['sky_noise'].set_xlabel('Image Index')
        axes['sky_noise'].set_ylabel('Sky Standard Deviation (ADU)')
        axes['sky_noise'].legend()
        axes['sky_noise'].grid(True, alpha=0.3)

        # Poisson noise
        if has_rgb:
            r_poisson = [r.get('r_poisson_noise', 0) for r in data]
            g_poisson = [r.get('g_poisson_noise', 0) for r in data]
            b_poisson = [r.get('b_poisson_noise', 0) for r in data]

            axes['poisson_noise'].plot(indices, r_poisson, 'r-', label='Red Poisson', linewidth=2, alpha=0.7)
            axes['poisson_noise'].plot(indices, g_poisson, 'g-', label='Green Poisson', linewidth=2, alpha=0.7)
            axes['poisson_noise'].plot(indices, b_poisson, 'b-', label='Blue Poisson', linewidth=2, alpha=0.7)

        gray_poisson = [r.get('gray_poisson_noise', 0) for r in data]
        axes['poisson_noise'].plot(indices, gray_poisson, 'k-', linewidth=3, alpha=0.8, label='Grayscale Poisson')
        axes['poisson_noise'].set_title('Poisson Noise (√N)')
        axes['poisson_noise'].set_xlabel('Image Index')
        axes['poisson_noise'].set_ylabel('Poisson Noise (ADU)')
        axes['poisson_noise'].legend()
        axes['poisson_noise'].grid(True, alpha=0.3)

        # Total Signal-to-Noise Ratio
        if has_rgb:
            r_snr = [r.get('r_flux_corrected', 0) / max(r.get('r_poisson_noise', 1), 1) for r in data]
            g_snr = [r.get('g_flux_corrected', 0) / max(r.get('g_poisson_noise', 1), 1) for r in data]
            b_snr = [r.get('b_flux_corrected', 0) / max(r.get('b_poisson_noise', 1), 1) for r in data]
            gray_snr = [r.get('gray_flux_corrected', 0) / max(r.get('gray_poisson_noise', 1), 1) for r in data]

            axes['total_snr'].plot(indices, r_snr, 'r-', label='Red S/N', linewidth=2)
            axes['total_snr'].plot(indices, g_snr, 'g-', label='Green S/N', linewidth=2)
            axes['total_snr'].plot(indices, b_snr, 'b-', label='Blue S/N', linewidth=2)
            axes['total_snr'].plot(indices, gray_snr, 'k-', label='Grayscale S/N', linewidth=2, alpha=0.8)
        else:
            gray_snr = [r.get('gray_flux_corrected', 0) / max(r.get('gray_poisson_noise', 1), 1) for r in data]
            axes['total_snr'].plot(indices, gray_snr, 'k-', linewidth=3, label='S/N Ratio')

        axes['total_snr'].set_title('Signal-to-Noise Ratio')
        axes['total_snr'].set_xlabel('Image Index')
        axes['total_snr'].set_ylabel('S/N Ratio')
        axes['total_snr'].legend()
        axes['total_snr'].grid(True, alpha=0.3)

    def update_tracking_plots(self):
        """Update star tracking analysis plots"""
        data = self.photometry_results
        indices = [r['image_index'] for r in data]

        axes = self.viz_axes['tracking']

        # Clear all axes
        for ax in axes.values():
            ax.clear()

        # Extract position data
        x_positions = [r.get('x_position', 0) for r in data]
        y_positions = [r.get('y_position', 0) for r in data]
        movements = [r.get('movement_pixels', 0) for r in data]

        # Position drift over time
        axes['position_drift'].plot(indices, x_positions, 'r-', label='X Position', linewidth=2)
        axes['position_drift'].plot(indices, y_positions, 'b-', label='Y Position', linewidth=2)
        axes['position_drift'].set_title('Star Position Drift Over Time')
        axes['position_drift'].set_xlabel('Image Index')
        axes['position_drift'].set_ylabel('Position (pixels)')
        axes['position_drift'].legend()
        axes['position_drift'].grid(True, alpha=0.3)

        # Movement per frame
        axes['movement_per_frame'].plot(indices, movements, 'g-o', linewidth=2, markersize=4, alpha=0.7)
        axes['movement_per_frame'].set_title('Star Movement Between Frames')
        axes['movement_per_frame'].set_xlabel('Image Index')
        axes['movement_per_frame'].set_ylabel('Movement (pixels)')
        axes['movement_per_frame'].grid(True, alpha=0.3)

        # Position scatter plot
        if len(x_positions) > 1:
            scatter = axes['position_scatter'].scatter(x_positions, y_positions, c=indices, cmap='viridis',
                                           s=50, alpha=0.7, edgecolors='black', linewidth=0.5)
            axes['position_scatter'].plot(x_positions, y_positions, 'k-', alpha=0.3, linewidth=1)

            # Add colorbar for scatter plot
            cbar = self.viz_figures['tracking'].colorbar(scatter, ax=axes['position_scatter'])
            cbar.set_label('Image Index')

        axes['position_scatter'].set_title('Star Position Scatter Plot')
        axes['position_scatter'].set_xlabel('X Position (pixels)')
        axes['position_scatter'].set_ylabel('Y Position (pixels)')
        axes['position_scatter'].set_aspect('equal', adjustable='box')
        axes['position_scatter'].grid(True, alpha=0.3)

        # Drift statistics
        if len(x_positions) > 1:
            x_drift = max(x_positions) - min(x_positions)
            y_drift = max(y_positions) - min(y_positions)
            total_drift = np.sqrt(x_drift**2 + y_drift**2)
            mean_movement = np.mean(movements[1:]) if len(movements) > 1 else 0
            max_movement = max(movements)

            stats_text = f"""Tracking Statistics:
            
Total X Drift: {x_drift:.2f} px
Total Y Drift: {y_drift:.2f} px
Total Drift Distance: {total_drift:.2f} px
            
Mean Movement/Frame: {mean_movement:.2f} px
Max Movement/Frame: {max_movement:.2f} px
            
Tracking Quality: {'Good' if max_movement < 5 else 'Fair' if max_movement < 10 else 'Poor'}"""

            axes['drift_stats'].text(0.1, 0.9, stats_text, transform=axes['drift_stats'].transAxes,
                                   fontsize=12, verticalalignment='top', fontfamily='monospace',
                                   bbox=dict(boxstyle="round,pad=0.5", facecolor="lightblue", alpha=0.8))

        axes['drift_stats'].set_title('Tracking Statistics Summary')
        axes['drift_stats'].set_xlim(0, 1)
        axes['drift_stats'].set_ylim(0, 1)
        axes['drift_stats'].axis('off')

    def save_star_positions(self):
        """Save pre-selected star positions to CSV file"""
        if not self.preselected_positions and not self.frame_positions:
            messagebox.showwarning("No Positions", "No star positions to save. Please select star positions first.")
            return

        # Determine which positions to save
        positions_to_save = self.preselected_positions if self.preselected_positions else self.frame_positions
        position_type = "pre-selected" if self.preselected_positions else "sequential"
        
        # Get star name
        star_name = self.star_name_var.get().strip() if self.star_name_var.get().strip() else "unnamed_star"
        
        # Create default filename
        default_filename = f"{star_name}_positions_{len(positions_to_save)}frames.csv"

        # Use current working directory with dedicated positions folder
        current_dir = os.getcwd()
        positions_dir = os.path.join(current_dir, "positions")
        
        # Create positions directory if it doesn't exist
        try:
            os.makedirs(positions_dir, exist_ok=True)
            self.log_status(f"Using positions directory: {positions_dir}")
        except Exception as e:
            self.log_status(f"Could not create positions directory: {e}")
            positions_dir = current_dir  # Fallback to current directory

        filename = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile=default_filename,
            initialdir=positions_dir,
            title=f"Save {len(positions_to_save)} star positions"
        )

        if filename:
            try:
                with open(filename, 'w', newline='') as csvfile:
                    fieldnames = ['image_index', 'filename', 'star_name', 'x_position', 'y_position', 
                                  'position_type', 'aperture_inner_radius', 'aperture_inner_annulus', 
                                  'aperture_outer_annulus', 'folder_path', 'full_file_path', 'timestamp']
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                    
                    writer.writeheader()
                    
                    timestamp = datetime.now().isoformat()
                    
                    # Get folder path once for all files
                    folder_path = os.path.dirname(self.fits_files[0]) if self.fits_files else ""
                    
                    for frame_index, position in enumerate(positions_to_save):
                        if position is not None:
                            x, y = position
                            if frame_index < len(self.fits_files):
                                full_file_path = self.fits_files[frame_index]
                                filename_base = os.path.basename(full_file_path)
                            else:
                                full_file_path = f"frame_{frame_index+1}"
                                filename_base = f"frame_{frame_index+1}"

                            writer.writerow({
                                'image_index': frame_index,  # Use actual frame index
                                'filename': filename_base,
                            'star_name': star_name,
                            'x_position': f"{x:.2f}",
                            'y_position': f"{y:.2f}",
                            'position_type': position_type,
                            'aperture_inner_radius': f"{self.aperture_params['inner_radius']:.2f}",
                            'aperture_inner_annulus': f"{self.aperture_params['inner_annulus']:.2f}",
                            'aperture_outer_annulus': f"{self.aperture_params['outer_annulus']:.2f}",
                            'folder_path': folder_path,
                            'full_file_path': full_file_path,
                            'timestamp': timestamp
                        })

                # Show success
                file_dir = os.path.dirname(filename)
                file_name = os.path.basename(filename)
                self.log_status(f"✓ Star positions saved: {file_name}")
                self.log_status(f"  Location: {file_dir}")

                success_msg = (f"Star positions saved successfully!\n\n"
                             f"File: {file_name}\n"
                             f"Location: positions/\n"
                             f"Positions: {len(positions_to_save)} frames\n"
                             f"Type: {position_type}\n\n"
                             f"Workflow Benefits:\n"
                             f"Load these positions to redo photometry with different aperture settings\n"
                             f"Skip the tedious clicking process for the same star\n"
                             f"Process the same data with different conditions instantly\n"
                             f"Share position files with colleagues for consistent analysis")

                messagebox.showinfo("Positions Saved Successfully", success_msg)

            except Exception as e:
                error_msg = f"Failed to save positions file:\n{str(e)}\n\nTry saving to a different location."
                messagebox.showerror("Save Error", error_msg)
                self.log_status(f"Save failed: {e}")

    def auto_save_star_positions(self):
        """Automatically save star positions to positions folder"""
        if not self.preselected_positions:
            return
            
        # Get star name
        star_name = self.star_name_var.get().strip() if self.star_name_var.get().strip() else "unnamed_star"
        
        # Create positions directory
        current_dir = os.getcwd()
        positions_dir = os.path.join(current_dir, "positions")
        os.makedirs(positions_dir, exist_ok=True)
        
        # Check for existing files with same star name and handle conflicts
        existing_files = [f for f in os.listdir(positions_dir) if f.startswith(f"{star_name}_positions_") and f.endswith(".csv")]
        
        if existing_files:
            # Star name conflict detected - ask user what to do
            response = messagebox.askyesnocancel(
                "Star Name Conflict",
                f"A position file for star '{star_name}' already exists.\n\n"
                f"Do you want to:\n"
                f"• Yes: Overwrite the existing file\n"
                f"• No: Create a new file with timestamp\n"
                f"• Cancel: Skip saving positions"
            )
            
            if response is None:  # Cancel
                self.log_status("Position auto-save cancelled by user")
                return
            elif response:  # Yes - overwrite
                filename = os.path.join(positions_dir, existing_files[0])
            else:  # No - create new with timestamp
                timestamp_suffix = datetime.now().strftime("_%Y%m%d_%H%M%S")
                filename = os.path.join(positions_dir, f"{star_name}_positions_{len(self.preselected_positions)}frames{timestamp_suffix}.csv")
        else:
            # No conflict - create new file
            filename = os.path.join(positions_dir, f"{star_name}_positions_{len(self.preselected_positions)}frames.csv")
        
        try:
            with open(filename, 'w', newline='') as csvfile:
                fieldnames = ['image_index', 'filename', 'star_name', 'x_position', 'y_position', 
                              'position_type', 'aperture_inner_radius', 'aperture_inner_annulus', 
                              'aperture_outer_annulus', 'folder_path', 'full_file_path', 'timestamp']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                
                writer.writeheader()
                
                timestamp = datetime.now().isoformat()
                
                # Get folder path once for all files
                folder_path = os.path.dirname(self.fits_files[0]) if self.fits_files else ""
                
                for frame_index, position in enumerate(self.preselected_positions):
                    if position is not None and frame_index < len(self.fits_files):
                        x, y = position
                        full_file_path = self.fits_files[frame_index]
                        filename_base = os.path.basename(full_file_path)
                        writer.writerow({
                            'image_index': frame_index,  # Use actual frame index, not sequential
                            'filename': filename_base,
                            'star_name': star_name,
                            'x_position': f"{x:.2f}",
                            'y_position': f"{y:.2f}",
                            'position_type': 'pre-selected',
                            'aperture_inner_radius': f"{self.inner_radius_var.get():.2f}",
                            'aperture_inner_annulus': f"{self.inner_annulus_var.get():.2f}",
                            'aperture_outer_annulus': f"{self.outer_annulus_var.get():.2f}",
                            'folder_path': folder_path,
                            'full_file_path': full_file_path,
                            'timestamp': timestamp
                        })
                
                self.log_status(f"Auto-saved star positions to: {os.path.basename(filename)}")
                
        except Exception as e:
            self.log_status(f"Error auto-saving positions: {e}")

    def load_star_positions(self):
        """Load star positions from CSV file"""
        # Default to positions directory
        current_dir = os.getcwd()
        positions_dir = os.path.join(current_dir, "positions")
        
        # Use positions directory if it exists, otherwise current directory
        initial_dir = positions_dir if os.path.exists(positions_dir) else current_dir
        
        filename = filedialog.askopenfilename(
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            title="Load star positions",
            initialdir=initial_dir
        )

        if filename:
            try:
                positions = []
                star_name = ""
                aperture_params = None
                
                with open(filename, 'r') as csvfile:
                    reader = csv.DictReader(csvfile)
                    
                    for row in reader:
                        x = float(row['x_position'])
                        y = float(row['y_position'])
                        positions.append((x, y))
                        
                        # Get star name from first row
                        if not star_name:
                            star_name = row.get('star_name', '')
                            
                        # Get aperture parameters from first row
                        if aperture_params is None:
                            aperture_params = {
                                'inner_radius': float(row.get('aperture_inner_radius', 5)),
                                'inner_annulus': float(row.get('aperture_inner_annulus', 8)),
                                'outer_annulus': float(row.get('aperture_outer_annulus', 12))
                            }

                if positions:
                    # Store loaded positions as pre-selected positions
                    self.preselected_positions = positions
                    
                    # Update star name if provided
                    if star_name:
                        self.star_name_var.set(star_name)
                        self.star_name = star_name
                    
                    # Update aperture parameters if provided
                    if aperture_params:
                        self.aperture_params.update(aperture_params)
                        # Update GUI sliders
                        self.inner_radius_var.set(aperture_params['inner_radius'])
                        self.inner_annulus_var.set(aperture_params['inner_annulus'])
                        self.outer_annulus_var.set(aperture_params['outer_annulus'])
                    
                    # Enable batch processing button
                    self.batch_process_button.config(state=tk.NORMAL)
                    
                    # Show first position on current image if available
                    if self.current_image_data is not None and positions:
                        first_pos = positions[0]
                        self.selected_star_pos = first_pos
                        self.star_pos_label.config(text=f"Loaded at ({first_pos[0]:.1f}, {first_pos[1]:.1f})")
                        self.display_image(show_aperture=True)
                        self.refresh_button.config(state=tk.NORMAL)

                    # Show success message
                    file_name = os.path.basename(filename)
                    success_msg = (f"✓ Star positions loaded successfully!\n\n"
                                 f"File: {file_name}\n"
                                 f"Positions loaded: {len(positions)} frames\n"
                                 f"Star name: {star_name or 'Not specified'}\n\n"
                                 f"Ready for batch processing! Click 'Process All Pre-selections' to run photometry.")

                    messagebox.showinfo("Positions Loaded Successfully", success_msg)
                    self.log_status(f"✓ Loaded {len(positions)} star positions from {file_name}")
                    
                else:
                    messagebox.showwarning("No Data", "No valid star positions found in the file.")
            except Exception as e:
                error_msg = f"Failed to load positions file:\n{str(e)}\n\nPlease check the file format."
                messagebox.showerror("Load Error", error_msg)
                self.log_status(f"✗ Load failed: {e}")


def main():
    """Main application entry point"""
    root = tk.Tk()
    app = AperturePhotometryGUI(root)

    # Handle window closing
    def on_closing():
        if app.processing:
            if messagebox.askokcancel("Quit", "Processing is running. Do you want to quit?"):
                app.stop_processing = True
                root.destroy()
        else:
            root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()