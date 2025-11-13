#!/usr/bin/env python3
"""
Star Period Analyzer
Two-tab application for magnitude calculation and Fourier period analysis
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import os

from scipy import fftpack
from scipy.signal import find_peaks
from datetime import datetime, timedelta
from astropy.time import Time

class StarPeriodAnalyzer:
    def __init__(self, root):
        self.root = root
        self.root.title("Star Period Analyzer")
        self.root.geometry("1400x800")

        # Data storage
        self.target_data = None
        self.reference_data = None
        self.magnitude_results = None
        self.fft_data = None

        # Variables for Tab 1
        self.target_file = tk.StringVar()  # Full path
        self.target_file_display = tk.StringVar()  # Display name only
        self.reference_file = tk.StringVar()  # Full path
        self.reference_file_display = tk.StringVar()  # Display name only
        self.reference_magnitude = tk.DoubleVar(value=9.8)
        self.start_date = tk.StringVar(value="2025-01-01 00:00:00")
        self.frame_gap = tk.DoubleVar(value=30.0)
        self.use_manual_date = tk.BooleanVar(value=False)
        self.r_weight = tk.DoubleVar(value=1.852)
        self.g_weight = tk.DoubleVar(value=1.0)
        self.b_weight = tk.DoubleVar(value=1.613)
        self.r_column = tk.StringVar(value="r_flux_corrected")
        self.g_column = tk.StringVar(value="g_flux_corrected")
        self.b_column = tk.StringVar(value="b_flux_corrected")

        # Variables for Tab 2
        self.analysis_file = tk.StringVar()  # Full path
        self.analysis_file_display = tk.StringVar()  # Display name only
        self.time_column = tk.StringVar()
        self.magnitude_column = tk.StringVar()
        self.analysis_data = None
        self.available_columns = []

        # Status
        self.status = tk.StringVar(value="Ready")

        self.create_gui()

    def create_gui(self):
        """Create the main GUI interface with tabs"""

        # Create notebook for tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Create tabs
        self.tab1 = ttk.Frame(self.notebook)
        self.tab2 = ttk.Frame(self.notebook)

        self.notebook.add(self.tab1, text="Magnitude Calculation")
        self.notebook.add(self.tab2, text="Fourier Period Analysis")

        # Setup each tab
        self.create_magnitude_tab()
        self.create_fourier_tab()

        # Status bar
        status_frame = ttk.Frame(self.root)
        status_frame.pack(fill=tk.X, side=tk.BOTTOM)
        ttk.Label(status_frame, textvariable=self.status).pack(side=tk.LEFT, padx=10, pady=5)

    def create_magnitude_tab(self):
        """Create Tab 1 - Magnitude Calculation"""

        # Main container
        main_frame = ttk.Frame(self.tab1)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Left panel - Controls with scrollbar
        left_panel_container = ttk.Frame(main_frame, width=400)
        left_panel_container.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        left_panel_container.pack_propagate(False)

        # Create canvas and scrollbar for left panel
        canvas = tk.Canvas(left_panel_container, width=380)
        scrollbar = ttk.Scrollbar(left_panel_container, orient="vertical", command=canvas.yview)
        left_panel = ttk.Frame(canvas)

        left_panel.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=left_panel, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Bind mousewheel to canvas
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas.bind("<MouseWheel>", _on_mousewheel)

        # Right panel - Results
        right_panel = ttk.Frame(main_frame)
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # === LEFT PANEL CONTROLS ===

        # File Selection
        file_frame = ttk.LabelFrame(left_panel, text="File Selection", padding=10)
        file_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(file_frame, text="Target Star CSV:").pack(anchor=tk.W)
        target_frame = ttk.Frame(file_frame)
        target_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Entry(target_frame, textvariable=self.target_file_display, width=30, state='readonly').pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(target_frame, text="Browse", command=self.browse_target_file).pack(side=tk.RIGHT, padx=(5, 0))

        ttk.Label(file_frame, text="Reference Star CSV:").pack(anchor=tk.W)
        ref_frame = ttk.Frame(file_frame)
        ref_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Entry(ref_frame, textvariable=self.reference_file_display, width=30, state='readonly').pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(ref_frame, text="Browse", command=self.browse_reference_file).pack(side=tk.RIGHT, padx=(5, 0))

        # Reference Magnitude
        mag_frame = ttk.LabelFrame(left_panel, text="Reference Star Settings", padding=10)
        mag_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(mag_frame, text="Reference Star Magnitude:").pack(anchor=tk.W)
        ttk.Entry(mag_frame, textvariable=self.reference_magnitude, width=10).pack(anchor=tk.W, pady=(0, 5))

        # RGB Column Names
        column_frame = ttk.LabelFrame(left_panel, text="RGB Column Names", padding=10)
        column_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(column_frame, text="R Flux Column Name:").pack(anchor=tk.W)
        ttk.Entry(column_frame, textvariable=self.r_column, width=20).pack(anchor=tk.W, pady=(0, 2))

        ttk.Label(column_frame, text="G Flux Column Name:").pack(anchor=tk.W)
        ttk.Entry(column_frame, textvariable=self.g_column, width=20).pack(anchor=tk.W, pady=(0, 2))

        ttk.Label(column_frame, text="B Flux Column Name:").pack(anchor=tk.W)
        ttk.Entry(column_frame, textvariable=self.b_column, width=20).pack(anchor=tk.W, pady=(0, 5))

        # RGB Weights
        rgb_frame = ttk.LabelFrame(left_panel, text="RGB Flux Weights", padding=10)
        rgb_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(rgb_frame, text="R Weight:").pack(anchor=tk.W)
        ttk.Entry(rgb_frame, textvariable=self.r_weight, width=10).pack(anchor=tk.W, pady=(0, 2))

        ttk.Label(rgb_frame, text="G Weight:").pack(anchor=tk.W)
        ttk.Entry(rgb_frame, textvariable=self.g_weight, width=10).pack(anchor=tk.W, pady=(0, 2))

        ttk.Label(rgb_frame, text="B Weight:").pack(anchor=tk.W)
        ttk.Entry(rgb_frame, textvariable=self.b_weight, width=10).pack(anchor=tk.W, pady=(0, 5))

        # Julian Date Settings
        date_frame = ttk.LabelFrame(left_panel, text="Julian Date Settings", padding=10)
        date_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Checkbutton(date_frame, text="Manual Date Entry (leave Julian Date column empty)",
                       variable=self.use_manual_date).pack(anchor=tk.W, pady=(0, 5))

        ttk.Label(date_frame, text="First Image Date (YYYY-MM-DD HH:MM:SS):").pack(anchor=tk.W)
        ttk.Entry(date_frame, textvariable=self.start_date, width=25).pack(anchor=tk.W, pady=(0, 5))

        ttk.Label(date_frame, text="Frame Gap (seconds):").pack(anchor=tk.W)
        ttk.Entry(date_frame, textvariable=self.frame_gap, width=10).pack(anchor=tk.W, pady=(0, 5))

        # Calculate Button
        ttk.Button(left_panel, text="Calculate Magnitudes",
                  command=self.calculate_magnitudes).pack(fill=tk.X, pady=(10, 5))

        # Export Button
        ttk.Button(left_panel, text="Export Results",
                  command=self.export_magnitude_results).pack(fill=tk.X, pady=(0, 5))

        # === RIGHT PANEL RESULTS ===

        # Results plot
        self.mag_figure = Figure(figsize=(10, 7), dpi=100)
        self.mag_canvas = FigureCanvasTkAgg(self.mag_figure, right_panel)
        self.mag_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def create_fourier_tab(self):
        """Create Tab 2 - Fourier Period Analysis"""

        # Main container
        main_frame = ttk.Frame(self.tab2)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Left panel - Controls with scrollbar
        left_panel_container = ttk.Frame(main_frame, width=400)
        left_panel_container.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        left_panel_container.pack_propagate(False)

        # Create canvas and scrollbar for left panel
        canvas2 = tk.Canvas(left_panel_container, width=380)
        scrollbar2 = ttk.Scrollbar(left_panel_container, orient="vertical", command=canvas2.yview)
        left_panel = ttk.Frame(canvas2)

        left_panel.bind(
            "<Configure>",
            lambda e: canvas2.configure(scrollregion=canvas2.bbox("all"))
        )

        canvas2.create_window((0, 0), window=left_panel, anchor="nw")
        canvas2.configure(yscrollcommand=scrollbar2.set)

        canvas2.pack(side="left", fill="both", expand=True)
        scrollbar2.pack(side="right", fill="y")

        # Bind mousewheel to canvas
        def _on_mousewheel2(event):
            canvas2.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas2.bind("<MouseWheel>", _on_mousewheel2)

        # Right panel - Results
        right_panel = ttk.Frame(main_frame)
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # === LEFT PANEL CONTROLS ===

        # File Selection
        file_frame = ttk.LabelFrame(left_panel, text="Data File Selection", padding=10)
        file_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(file_frame, text="CSV File:").pack(anchor=tk.W)
        analysis_frame = ttk.Frame(file_frame)
        analysis_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Entry(analysis_frame, textvariable=self.analysis_file_display, width=30, state='readonly').pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(analysis_frame, text="Browse", command=self.browse_analysis_file).pack(side=tk.RIGHT, padx=(5, 0))

        # Load Data Button (moved here)
        ttk.Button(file_frame, text="Load Data and Update Columns",
                  command=self.load_analysis_data).pack(fill=tk.X, pady=(5, 0))

        # Column Selection
        column_frame = ttk.LabelFrame(left_panel, text="Column Selection", padding=10)
        column_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(column_frame, text="Time Column:").pack(anchor=tk.W)
        self.time_combo = ttk.Combobox(column_frame, textvariable=self.time_column, state="readonly")
        self.time_combo.pack(fill=tk.X, pady=(0, 5))

        ttk.Label(column_frame, text="Magnitude Column:").pack(anchor=tk.W)
        self.mag_combo = ttk.Combobox(column_frame, textvariable=self.magnitude_column, state="readonly")
        self.mag_combo.pack(fill=tk.X, pady=(0, 5))

        # Analysis Buttons
        ttk.Button(left_panel, text="Perform FFT Analysis",
                  command=self.perform_fft_analysis).pack(fill=tk.X, pady=(10, 5))

        ttk.Button(left_panel, text="Export FFT Results",
                  command=self.export_fft_results).pack(fill=tk.X, pady=(0, 5))

        # === RIGHT PANEL RESULTS ===

        # Results plot
        self.fft_figure = Figure(figsize=(11, 10), dpi=100)
        self.fft_canvas = FigureCanvasTkAgg(self.fft_figure, right_panel)
        self.fft_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    # === TAB 1 METHODS ===

    def browse_target_file(self):
        """Browse for target star CSV file"""
        filename = filedialog.askopenfilename(
            title="Select Target Star CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if filename:
            self.target_file.set(filename)
            self.target_file_display.set(os.path.basename(filename))

    def browse_reference_file(self):
        """Browse for reference star CSV file"""
        filename = filedialog.askopenfilename(
            title="Select Reference Star CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if filename:
            self.reference_file.set(filename)
            self.reference_file_display.set(os.path.basename(filename))

    def calculate_julian_date(self, start_datetime, frame_number, gap_seconds):
        """Calculate Julian Date for a given frame"""
        try:
            # Parse the start datetime
            start_dt = datetime.strptime(start_datetime, "%Y-%m-%d %H:%M:%S")

            # Add the time offset for this frame
            frame_dt = start_dt + timedelta(seconds=frame_number * gap_seconds)

            # Convert to Julian Date using astropy
            t = Time(frame_dt)
            return t.jd
        except Exception as e:
            raise ValueError(f"Error calculating Julian Date: {str(e)}")

    def calculate_flux_from_rgb(self, r_flux, g_flux, b_flux, r_weight, g_weight, b_weight):
        """Calculate weighted flux from RGB values"""
        # Normalize weights
        total_weight = r_weight + g_weight + b_weight
        if total_weight == 0:
            raise ValueError("RGB weights cannot all be zero")

        r_norm = r_weight / total_weight
        g_norm = g_weight / total_weight
        b_norm = b_weight / total_weight

        return r_flux * r_norm + g_flux * g_norm + b_flux * b_norm

    def calculate_magnitudes(self):
        """Calculate absolute magnitudes from photometry data"""
        try:
            self.status.set("Calculating magnitudes...")

            # Validate inputs
            if not self.target_file.get() or not self.reference_file.get():
                messagebox.showerror("Error", "Please select both target and reference CSV files")
                return

            if not all([self.r_column.get(), self.g_column.get(), self.b_column.get()]):
                messagebox.showerror("Error", "Please enter RGB column names")
                return

            if not all([self.r_weight.get(), self.g_weight.get(), self.b_weight.get()]):
                messagebox.showerror("Error", "Please enter RGB weights")
                return

            if not self.use_manual_date.get() and not self.start_date.get():
                messagebox.showerror("Error", "Please enter the first image date")
                return

            # Load data
            target_df = pd.read_csv(self.target_file.get())
            reference_df = pd.read_csv(self.reference_file.get())

            if len(target_df) != len(reference_df):
                messagebox.showerror("Error", "Target and reference files must have the same number of rows")
                return

            # Check if specified columns exist
            for col in [self.r_column.get(), self.g_column.get(), self.b_column.get()]:
                if col not in target_df.columns:
                    messagebox.showerror("Error", f"Column '{col}' not found in target CSV")
                    return
                if col not in reference_df.columns:
                    messagebox.showerror("Error", f"Column '{col}' not found in reference CSV")
                    return

            # Calculate weighted flux for both target and reference (grayscale)
            target_flux_gray = self.calculate_flux_from_rgb(
                target_df[self.r_column.get()], target_df[self.g_column.get()], target_df[self.b_column.get()],
                self.r_weight.get(), self.g_weight.get(), self.b_weight.get()
            )

            reference_flux_gray = self.calculate_flux_from_rgb(
                reference_df[self.r_column.get()], reference_df[self.g_column.get()], reference_df[self.b_column.get()],
                self.r_weight.get(), self.g_weight.get(), self.b_weight.get()
            )

            # Extract individual R, G, B flux values
            target_flux_r = target_df[self.r_column.get()]
            target_flux_g = target_df[self.g_column.get()]
            target_flux_b = target_df[self.b_column.get()]

            reference_flux_r = reference_df[self.r_column.get()]
            reference_flux_g = reference_df[self.g_column.get()]
            reference_flux_b = reference_df[self.b_column.get()]

            # Calculate instrumental magnitudes for grayscale
            target_inst_mag_gray = -2.5 * np.log10(target_flux_gray)
            reference_inst_mag_gray = -2.5 * np.log10(reference_flux_gray)

            # Calculate differential magnitude for grayscale
            diff_mag_gray = target_inst_mag_gray - reference_inst_mag_gray

            # Calculate absolute magnitude for grayscale
            target_magnitude_gray = diff_mag_gray + self.reference_magnitude.get()

            # Replace inf values with NaN for proper handling
            target_magnitude_gray = np.where(np.isinf(target_magnitude_gray), np.nan, target_magnitude_gray)

            # Calculate instrumental magnitudes for R channel
            target_inst_mag_r = -2.5 * np.log10(target_flux_r)
            reference_inst_mag_r = -2.5 * np.log10(reference_flux_r)
            diff_mag_r = target_inst_mag_r - reference_inst_mag_r
            target_magnitude_r = diff_mag_r + self.reference_magnitude.get()
            target_magnitude_r = np.where(np.isinf(target_magnitude_r), np.nan, target_magnitude_r)

            # Calculate instrumental magnitudes for G channel
            target_inst_mag_g = -2.5 * np.log10(target_flux_g)
            reference_inst_mag_g = -2.5 * np.log10(reference_flux_g)
            diff_mag_g = target_inst_mag_g - reference_inst_mag_g
            target_magnitude_g = diff_mag_g + self.reference_magnitude.get()
            target_magnitude_g = np.where(np.isinf(target_magnitude_g), np.nan, target_magnitude_g)

            # Calculate instrumental magnitudes for B channel
            target_inst_mag_b = -2.5 * np.log10(target_flux_b)
            reference_inst_mag_b = -2.5 * np.log10(reference_flux_b)
            diff_mag_b = target_inst_mag_b - reference_inst_mag_b
            target_magnitude_b = diff_mag_b + self.reference_magnitude.get()
            target_magnitude_b = np.where(np.isinf(target_magnitude_b), np.nan, target_magnitude_b)

            # Prepare results
            results = pd.DataFrame()

            # Julian Date calculation
            if self.use_manual_date.get():
                results['Julian Date'] = [''] * len(target_df)  # Empty for manual entry
            else:
                julian_dates = []
                for i in range(len(target_df)):
                    jd = self.calculate_julian_date(
                        self.start_date.get(), i, self.frame_gap.get()
                    )
                    julian_dates.append(jd)
                results['Julian Date'] = julian_dates

            # Add all magnitude columns (R, G, B, Grayscale)
            results['Magnitude_Gray'] = target_magnitude_gray
            results['Magnitude_R'] = target_magnitude_r
            results['Magnitude_G'] = target_magnitude_g
            results['Magnitude_B'] = target_magnitude_b

            self.magnitude_results = results

            # Plot results
            self.plot_magnitude_results()

            self.status.set("Magnitude calculation completed")

        except Exception as e:
            messagebox.showerror("Error", f"Error calculating magnitudes: {str(e)}")
            self.status.set("Error in calculation")

    def plot_magnitude_results(self):
        """Plot magnitude results - all 4 channels"""
        if self.magnitude_results is None:
            return

        self.mag_figure.clear()
        ax = self.mag_figure.add_subplot(111)

        # Define colors for each channel
        colors = {
            'Magnitude_R': '#E63946',      # Red
            'Magnitude_G': '#2A9D8F',      # Green
            'Magnitude_B': '#457B9D',      # Blue
            'Magnitude_Gray': '#6C757D'    # Gray
        }

        labels = {
            'Magnitude_R': 'R Channel',
            'Magnitude_G': 'G Channel',
            'Magnitude_B': 'B Channel',
            'Magnitude_Gray': 'Grayscale (Weighted)'
        }

        # Determine x-axis data
        if not self.use_manual_date.get():
            x_data = self.magnitude_results['Julian Date']
            xlabel = 'Julian Date (JD)'
        else:
            x_data = range(len(self.magnitude_results))
            xlabel = 'Frame Number'

        # Plot all 4 magnitude curves
        for mag_col, color in colors.items():
            if mag_col in self.magnitude_results.columns:
                ax.plot(x_data, self.magnitude_results[mag_col],
                       color=color, marker='o', markersize=4, linewidth=1.5,
                       markeredgecolor='white', markeredgewidth=0.5,
                       label=labels[mag_col], alpha=0.8)

        ax.set_xlabel(xlabel, fontsize=12, fontweight='bold')
        ax.set_ylabel('Magnitude (mag)', fontsize=12, fontweight='bold')
        ax.set_title('Target Star Light Curve - All Channels', fontsize=14, fontweight='bold', pad=15)
        ax.grid(True, alpha=0.3, linestyle='--', linewidth=0.8)
        ax.invert_yaxis()  # Invert y-axis for magnitude scale
        ax.legend(loc='best', framealpha=0.95, fontsize=9)

        # Add background color
        ax.set_facecolor('#F8F9FA')

        # Add statistical info for grayscale magnitude
        mag_gray_data = self.magnitude_results['Magnitude_Gray'].dropna()
        if len(mag_gray_data) > 0:
            mean_mag = np.mean(mag_gray_data)
            std_mag = np.std(mag_gray_data)
            min_mag = np.min(mag_gray_data)
            max_mag = np.max(mag_gray_data)

            stats_text = f'Grayscale Stats:\nMean: {mean_mag:.3f}\nStd: {std_mag:.3f}\nRange: {min_mag:.3f} - {max_mag:.3f}'
            ax.text(0.02, 0.98, stats_text, transform=ax.transAxes,
                   verticalalignment='top', bbox=dict(boxstyle='round', facecolor='white', alpha=0.85),
                   fontsize=8, family='monospace')

        self.mag_figure.tight_layout()
        self.mag_canvas.draw()

    def export_magnitude_results(self):
        """Export magnitude calculation results to CSV"""
        if self.magnitude_results is None:
            messagebox.showerror("Error", "No results to export. Please calculate magnitudes first.")
            return

        filename = filedialog.asksaveasfilename(
            title="Save Magnitude Results",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )

        if filename:
            self.magnitude_results.to_csv(filename, index=False)
            self.status.set(f"Results exported to {filename}")

    # === TAB 2 METHODS ===

    def browse_analysis_file(self):
        """Browse for analysis CSV file"""
        filename = filedialog.askopenfilename(
            title="Select CSV File for Analysis",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if filename:
            self.analysis_file.set(filename)
            self.analysis_file_display.set(os.path.basename(filename))

    def load_analysis_data(self):
        """Load analysis data and update column options"""
        try:
            if not self.analysis_file.get():
                messagebox.showerror("Error", "Please select a CSV file")
                return

            # Load the data
            self.analysis_data = pd.read_csv(self.analysis_file.get())

            # Get column names
            self.available_columns = list(self.analysis_data.columns)

            # Update comboboxes
            self.time_combo['values'] = self.available_columns
            self.mag_combo['values'] = self.available_columns

            # Auto-select "Julian Date" and "Magnitude" if they exist
            for col in self.available_columns:
                if col.lower() == "julian date":
                    self.time_column.set(col)
                elif col.lower() == "magnitude":
                    self.magnitude_column.set(col)

            self.status.set(f"Loaded data with {len(self.analysis_data)} rows. Columns auto-selected.")

        except Exception as e:
            messagebox.showerror("Error", f"Error loading data: {str(e)}")

    def perform_fft_analysis(self):
        """Perform FFT analysis on selected data"""
        try:
            if self.analysis_data is None:
                messagebox.showerror("Error", "Please load data first")
                return

            if not self.time_column.get() or not self.magnitude_column.get():
                messagebox.showerror("Error", "Please select time and magnitude columns")
                return

            self.status.set("Performing FFT analysis...")

            # Extract data
            time_data = self.analysis_data[self.time_column.get()].values
            mag_data = self.analysis_data[self.magnitude_column.get()].values

            # Convert to numeric, handling any non-numeric values
            time_data = pd.to_numeric(time_data, errors='coerce')
            mag_data = pd.to_numeric(mag_data, errors='coerce')

            # Remove any NaN values or invalid data
            mask = ~(np.isnan(time_data) | np.isnan(mag_data))
            time_data = time_data[mask]
            mag_data = mag_data[mask]

            # Check if we have enough data
            if len(time_data) < 3:
                messagebox.showerror("Error", "Not enough valid data points for FFT analysis")
                return

            # Calculate sampling parameters
            dt = np.median(np.diff(time_data))  # Median time step in days
            n = len(time_data)

            # Perform FFT with time in days
            fft_result = np.fft.fft(mag_data - np.mean(mag_data))
            frequencies = np.fft.fftfreq(n, dt)  # Frequencies in 1/days

            # Take only positive frequencies
            positive_freq_mask = frequencies > 0
            frequencies = frequencies[positive_freq_mask]
            amplitudes = np.abs(fft_result[positive_freq_mask])

            # Convert frequencies to periods in DAYS
            periods = 1.0 / frequencies  # Periods in days

            # Find reasonable period range for display (in days)
            min_period = 2 * dt  # Nyquist limit in days
            max_period = (time_data[-1] - time_data[0]) / 2  # Half the total observation time in days

            period_mask = (periods >= min_period) & (periods <= max_period)
            periods = periods[period_mask]
            amplitudes = amplitudes[period_mask]
            frequencies = frequencies[period_mask]

            # Store results
            self.fft_data = pd.DataFrame({
                'Period': periods,
                'Frequency': frequencies,
                'Amplitude': amplitudes
            })

            # Store time and magnitude data for plotting
            self.time_data = time_data
            self.mag_data = mag_data

            # Find peaks
            peaks, _ = find_peaks(amplitudes, height=np.max(amplitudes) * 0.1)

            # Plot results
            self.plot_fft_results(time_data, mag_data, periods, frequencies, amplitudes, peaks)

            # Report strongest periods (convert to minutes for display)
            if len(peaks) > 0:
                peak_periods = periods[peaks] * 24 * 60  # Convert days to minutes
                peak_amplitudes = amplitudes[peaks]
                strongest_idx = np.argsort(peak_amplitudes)[::-1][:5]  # Top 5 peaks

                peak_info = "Strongest Periods Detected:\n" + "="*50 + "\n\n"
                for i in range(min(5, len(strongest_idx))):
                    idx = strongest_idx[i]
                    if idx < len(peaks):
                        peak_idx = peaks[idx]
                        period_val = peak_periods[peak_idx]
                        amp_val = peak_amplitudes[peak_idx]
                        peak_info += f"Rank #{i+1}:\n"
                        peak_info += f"  Period: {period_val:.2f} minutes\n"
                        peak_info += f"  Amplitude: {amp_val:.6f}\n\n"

                messagebox.showinfo("Peak Detection Results", peak_info)

            self.status.set("FFT analysis completed successfully")

        except Exception as e:
            messagebox.showerror("Error", f"Error in FFT analysis: {str(e)}")
            self.status.set("Error in FFT analysis")

    def plot_fft_results(self, time_data, mag_data, periods, frequencies, amplitudes, peaks):
        """Plot FFT analysis results with professional styling"""
        self.fft_figure.clear()

        # Convert periods from days to minutes for display
        periods_minutes = periods * 24 * 60  # Convert days to minutes

        # Create 2 subplot layout (2 rows, 1 column)
        gs = self.fft_figure.add_gridspec(2, 1, hspace=0.4)
        ax1 = self.fft_figure.add_subplot(gs[0])  # Top: Time series
        ax2 = self.fft_figure.add_subplot(gs[1])  # Bottom: Period spectrum

        # Color scheme
        color_data = '#2E86AB'
        color_fft = '#A23B72'
        color_peaks = '#F18F01'

        # ========== Subplot 1: Original Time Series (keep in Julian Date) ==========
        ax1.plot(time_data, mag_data, color=color_data, linewidth=1.5,
                marker='o', markersize=4, markeredgecolor='white', markeredgewidth=0.5,
                label='Observed Data')

        ax1.set_xlabel('Julian Date (JD)', fontsize=11, fontweight='bold')
        ax1.set_ylabel('Magnitude', fontsize=11, fontweight='bold')
        ax1.set_title('Time Series Data', fontsize=13, fontweight='bold', pad=10)
        ax1.grid(True, alpha=0.3, linestyle='--', linewidth=0.8)
        ax1.set_facecolor('#F8F9FA')
        ax1.legend(loc='best', framealpha=0.9, fontsize=9)

        # Add statistics
        mean_val = np.mean(mag_data)
        std_val = np.std(mag_data)
        total_duration = (time_data[-1] - time_data[0]) * 24 * 60 * 60  # Duration in seconds
        stats_text = f'Mean: {mean_val:.4f}\nStd Dev: {std_val:.4f}\nN: {len(mag_data)}\nDuration: {total_duration:.1f}s'
        ax1.text(0.02, 0.98, stats_text, transform=ax1.transAxes,
                verticalalignment='top', bbox=dict(boxstyle='round', facecolor='white', alpha=0.85),
                fontsize=8, family='monospace')

        # ========== Subplot 2: Power Spectrum vs Period (in minutes) ==========
        ax2.plot(periods_minutes, amplitudes, color=color_fft, linewidth=2, alpha=0.7, label='Power Spectrum')

        # Mark peaks
        if len(peaks) > 0:
            ax2.plot(periods_minutes[peaks], amplitudes[peaks], 'o', color=color_peaks,
                    markersize=8, markeredgecolor='white', markeredgewidth=1.5,
                    label='Detected Peaks', zorder=5)

            # Get top 3 peaks by amplitude
            peak_amplitudes = amplitudes[peaks]
            sorted_indices = np.argsort(peak_amplitudes)[::-1]
            top_3_indices = sorted_indices[:min(3, len(sorted_indices))]

            # Annotate top 3 peaks with better positioning
            for i, idx in enumerate(top_3_indices):
                peak_idx = peaks[idx]
                period_val = periods_minutes[peak_idx]
                amp_val = amplitudes[peak_idx]

                # Annotation with clean styling - show period in minutes
                ax2.annotate(f'#{i+1}: {period_val:.1f}min',
                           xy=(period_val, amp_val),
                           xytext=(15, 15 + i*30),
                           textcoords='offset points',
                           fontsize=9,
                           fontweight='bold',
                           bbox=dict(boxstyle='round,pad=0.4', facecolor=color_peaks,
                                   alpha=0.8, edgecolor='white', linewidth=1.5),
                           arrowprops=dict(arrowstyle='->', lw=1.5, color=color_peaks,
                                         connectionstyle='arc3,rad=0.2'),
                           color='white')

        ax2.set_xlabel('Period (minutes)', fontsize=11, fontweight='bold')
        ax2.set_ylabel('Power Amplitude', fontsize=11, fontweight='bold')
        ax2.set_title('Periodogram - Period vs Amplitude', fontsize=12, fontweight='bold', pad=10)
        ax2.grid(True, alpha=0.3, linestyle='--', linewidth=0.8)
        ax2.set_xscale('log')
        ax2.set_facecolor('#F8F9FA')
        ax2.legend(loc='best', framealpha=0.9, fontsize=9)

        # Overall figure styling
        self.fft_figure.patch.set_facecolor('white')
        self.fft_figure.suptitle('Fourier Transform Analysis', fontsize=15, fontweight='bold', y=0.98)

        self.fft_figure.tight_layout(rect=[0, 0, 1, 0.96])
        self.fft_canvas.draw()

    def export_fft_results(self):
        """Export FFT analysis results to CSV"""
        if self.fft_data is None:
            messagebox.showerror("Error", "No FFT results to export. Please perform FFT analysis first.")
            return

        filename = filedialog.asksaveasfilename(
            title="Save FFT Results",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )

        if filename:
            self.fft_data.to_csv(filename, index=False)
            self.status.set(f"FFT results exported to {filename}")

def main():
    root = tk.Tk()
    app = StarPeriodAnalyzer(root)
    root.mainloop()

if __name__ == "__main__":
    main()