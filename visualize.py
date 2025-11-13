#!/usr/bin/env python3
"""
Photometry Data Visualizer
A standalone tool to visualize CSV photometry results from the DSLR Telescope Astronomy Toolbox
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import numpy as np
import pandas as pd
import os
from pathlib import Path

# Force matplotlib to use TkAgg backend before importing pyplot
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

class PhotometryVisualizer:
    def __init__(self, root):
        self.root = root
        self.root.title("Photometry Data Visualizer")
        self.root.geometry("1400x900")
        
        # Data storage
        self.data = None
        self.csv_filename = ""
        self.star_name = ""
        
        # Visualization storage
        self.viz_figures = {}
        self.viz_axes = {}
        
        self.setup_gui()
        
    def setup_gui(self):
        """Initialize the GUI layout"""
        # Main frame
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Top control frame
        control_frame = ttk.Frame(main_frame)
        control_frame.pack(fill=tk.X, pady=(0, 10))
        
        # File selection section
        file_frame = ttk.LabelFrame(control_frame, text="Data Selection", padding="10")
        file_frame.pack(fill=tk.X, pady=(0, 10))
        
        # CSV file selection
        ttk.Label(file_frame, text="CSV File:").grid(row=0, column=0, sticky=tk.W, padx=(0, 10))
        
        self.file_var = tk.StringVar()
        file_entry = ttk.Entry(file_frame, textvariable=self.file_var, width=60)
        file_entry.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(0, 10))
        
        ttk.Button(file_frame, text="Browse", command=self.browse_csv_file).grid(row=0, column=2)
        ttk.Button(file_frame, text="Results Folder", command=self.browse_results_folder).grid(row=0, column=3, padx=(10, 0))
        
        file_frame.grid_columnconfigure(1, weight=1)
        
        # Load button
        button_frame = ttk.Frame(control_frame)
        button_frame.pack(fill=tk.X)
        
        ttk.Button(button_frame, text="Load & Visualize", command=self.load_and_visualize, 
                  style="Accent.TButton").pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(button_frame, text="Refresh Plots", command=self.update_all_plots).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(button_frame, text="Export Plots", command=self.export_plots).pack(side=tk.LEFT, padx=(0, 10))
        
        # Info label
        self.info_var = tk.StringVar(value="Select a CSV file to visualize photometry data")
        info_label = ttk.Label(button_frame, textvariable=self.info_var, font=("Arial", 10, "italic"))
        info_label.pack(side=tk.RIGHT)
        
        # Separator
        ttk.Separator(main_frame, orient='horizontal').pack(fill=tk.X, pady=10)
        
        # Visualization area
        self.viz_frame = ttk.Frame(main_frame)
        self.viz_frame.pack(fill=tk.BOTH, expand=True)
        
        # Initially show welcome message
        self.show_welcome_message()
        
    def show_welcome_message(self):
        """Show welcome message when no data is loaded"""
        welcome_frame = ttk.Frame(self.viz_frame)
        welcome_frame.pack(expand=True)
        
        welcome_text = """
        Welcome to Photometry Data Visualizer!
        
        This tool visualizes CSV photometry results from the DSLR Telescope Astronomy Toolbox.
        
        To get started:
        1. Click "Results Folder" to browse saved photometry results
        2. Or click "Browse" to select a specific CSV file
        3. Click "Load & Visualize" to display the graphs
        
        The visualization includes:
        • Light curves (RGB + Grayscale)
        • RGB channel analysis and color ratios
        • Data quality metrics (noise, S/N ratios)
        • Star tracking analysis and position drift
        """
        
        ttk.Label(welcome_frame, text=welcome_text, font=("Arial", 12), 
                 justify=tk.LEFT, foreground="gray").pack(expand=True)
    
    def browse_csv_file(self):
        """Browse for a specific CSV file"""
        filename = filedialog.askopenfilename(
            title="Select Photometry CSV File",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialdir=self.get_results_dir()
        )
        if filename:
            self.file_var.set(filename)
    
    def browse_results_folder(self):
        """Browse the results folder and let user select from available CSV files"""
        results_dir = self.get_results_dir()
        
        if not results_dir.exists():
            messagebox.showwarning("No Results Folder", 
                                 f"Results folder not found: {results_dir}\n\n"
                                 "Please run photometry analysis first or select a CSV file manually.")
            return
        
        # Find CSV files in results directory
        csv_files = list(results_dir.glob("*.csv"))
        
        if not csv_files:
            messagebox.showinfo("No CSV Files", 
                               f"No CSV files found in results folder: {results_dir}\n\n"
                               "Please run photometry analysis first.")
            return
        
        if len(csv_files) == 1:
            # Only one file, select it automatically
            self.file_var.set(str(csv_files[0]))
            return
        
        # Multiple files, show selection dialog
        self.show_csv_selection_dialog(csv_files)
    
    def show_csv_selection_dialog(self, csv_files):
        """Show dialog to select from multiple CSV files"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Select CSV File")
        dialog.geometry("700x400")
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Create listbox with file info
        frame = ttk.Frame(dialog, padding="10")
        frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(frame, text="Select a photometry CSV file:", font=("Arial", 12, "bold")).pack(pady=(0, 10))
        
        # Listbox with scrollbar
        list_frame = ttk.Frame(frame)
        list_frame.pack(fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set, font=("Courier", 10))
        listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=listbox.yview)
        
        # Add files to listbox with metadata
        file_info = []
        for csv_file in csv_files:
            stat = csv_file.stat()
            size_mb = stat.st_size / (1024 * 1024)
            modified = pd.Timestamp(stat.st_mtime, unit='s').strftime('%Y-%m-%d %H:%M')
            
            display_text = f"{csv_file.name:<40} {size_mb:>6.1f}MB  {modified}"
            listbox.insert(tk.END, display_text)
            file_info.append(csv_file)
        
        # Select first item by default
        if file_info:
            listbox.selection_set(0)
        
        # Buttons
        button_frame = ttk.Frame(frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        
        def on_select():
            selection = listbox.curselection()
            if selection:
                selected_file = file_info[selection[0]]
                self.file_var.set(str(selected_file))
                dialog.destroy()
            else:
                messagebox.showwarning("No Selection", "Please select a file.")
        
        def on_cancel():
            dialog.destroy()
        
        ttk.Button(button_frame, text="Select", command=on_select).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(button_frame, text="Cancel", command=on_cancel).pack(side=tk.LEFT)
        
        # Double-click to select
        listbox.bind('<Double-Button-1>', lambda e: on_select())
        
        # Center dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")
    
    def get_results_dir(self):
        """Get the results directory path"""
        return Path(os.getcwd()) / "results"
    
    def load_and_visualize(self):
        """Load CSV data and create visualization"""
        filename = self.file_var.get().strip()
        
        if not filename:
            messagebox.showwarning("No File Selected", "Please select a CSV file first.")
            return
        
        if not os.path.exists(filename):
            messagebox.showerror("File Not Found", f"File not found: {filename}")
            return
        
        try:
            # Load CSV data
            self.data = pd.read_csv(filename)
            self.csv_filename = os.path.basename(filename)
            
            # Extract star name from filename if possible
            if "_photometry_" in self.csv_filename:
                self.star_name = self.csv_filename.split("_photometry_")[0]
            else:
                self.star_name = os.path.splitext(self.csv_filename)[0]
            
            # Validate data
            if len(self.data) == 0:
                messagebox.showwarning("Empty File", "The selected CSV file contains no data.")
                return
            
            # Update info
            has_rgb = any(col.startswith(('r_', 'g_', 'b_')) for col in self.data.columns)
            self.info_var.set(f"Loaded: {self.csv_filename} | {len(self.data)} records | "
                            f"{'RGB + Grayscale' if has_rgb else 'Grayscale only'}")
            
            # Create visualization
            self.create_visualization_tabs()
            
        except Exception as e:
            messagebox.showerror("Error Loading Data", f"Failed to load CSV file:\n{str(e)}")
    
    def create_visualization_tabs(self):
        """Create the visualization tabs"""
        # Clear existing visualization
        for widget in self.viz_frame.winfo_children():
            widget.destroy()
        
        # Create notebook for multiple tabs
        notebook = ttk.Notebook(self.viz_frame)
        notebook.pack(fill=tk.BOTH, expand=True)
        
        # Create tabs
        self.setup_lightcurve_tab(notebook)
        self.setup_rgb_comparison_tab(notebook)
        self.setup_quality_metrics_tab(notebook)
        self.setup_tracking_tab(notebook)
        
        # Update all plots
        self.update_all_plots()
    
    def setup_lightcurve_tab(self, parent):
        """Setup the light curve visualization tab"""
        frame = ttk.Frame(parent)
        parent.add(frame, text="Light Curves")
        
        # Create matplotlib figure with proper spacing
        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(16, 12))
        fig.suptitle(f'Star Light Curves Analysis - {self.star_name}', fontsize=16, fontweight='bold')
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
        fig.suptitle(f'RGB Channel Analysis - {self.star_name}', fontsize=16, fontweight='bold')
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
        fig.suptitle(f'Data Quality Analysis - {self.star_name}', fontsize=16, fontweight='bold')
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
        fig.suptitle(f'Star Tracking Analysis - {self.star_name}', fontsize=16, fontweight='bold')
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
        if self.data is None or not hasattr(self, 'viz_figures'):
            return
        
        try:
            self.update_lightcurve_plots()
            self.update_rgb_plots()
            self.update_quality_plots()
            self.update_tracking_plots()
            
            # Refresh all canvases
            for fig in self.viz_figures.values():
                fig.canvas.draw()
            
            self.info_var.set(f"Loaded: {self.csv_filename} | {len(self.data)} records | Plots updated")
            
        except Exception as e:
            messagebox.showerror("Plot Update Error", f"Error updating plots: {str(e)}")
    
    def update_lightcurve_plots(self):
        """Update light curve plots"""
        if 'image_index' not in self.data.columns:
            indices = list(range(len(self.data)))
        else:
            indices = self.data['image_index'].values
        
        # Determine if we have RGB data
        has_rgb = any(col.startswith(('r_flux_corrected', 'g_flux_corrected', 'b_flux_corrected')) 
                     for col in self.data.columns)
        
        axes = self.viz_axes['lightcurve']
        
        # Clear all axes
        for ax in axes.values():
            ax.clear()
        
        if has_rgb:
            # RGB + Grayscale combined plot
            r_flux = self.data.get('r_flux_corrected', pd.Series([0] * len(self.data)))
            g_flux = self.data.get('g_flux_corrected', pd.Series([0] * len(self.data)))
            b_flux = self.data.get('b_flux_corrected', pd.Series([0] * len(self.data)))
            gray_flux = self.data.get('gray_flux_corrected', pd.Series([0] * len(self.data)))
            
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
            raw_flux = self.data.get('gray_star_flux_raw', gray_flux)
            axes['raw_vs_corrected'].plot(indices, raw_flux, 'r-', label='Raw Flux', linewidth=2, alpha=0.7)
            axes['raw_vs_corrected'].plot(indices, gray_flux, 'b-', label='Sky-Corrected Flux', linewidth=2)
            axes['raw_vs_corrected'].set_title('Raw vs Sky-Corrected Flux')
            axes['raw_vs_corrected'].set_xlabel('Image Index')
            axes['raw_vs_corrected'].set_ylabel('Flux (ADU)')
            axes['raw_vs_corrected'].legend()
            axes['raw_vs_corrected'].grid(True, alpha=0.3)
            
            # Signal-to-Noise Ratios
            r_noise = self.data.get('r_poisson_noise', pd.Series([1] * len(self.data)))
            g_noise = self.data.get('g_poisson_noise', pd.Series([1] * len(self.data)))
            b_noise = self.data.get('b_poisson_noise', pd.Series([1] * len(self.data)))
            
            r_snr = r_flux / np.maximum(r_noise, 1)
            g_snr = g_flux / np.maximum(g_noise, 1)
            b_snr = b_flux / np.maximum(b_noise, 1)
            
            axes['snr'].plot(indices, r_snr, 'r-', label='Red S/N', linewidth=2)
            axes['snr'].plot(indices, g_snr, 'g-', label='Green S/N', linewidth=2)
            axes['snr'].plot(indices, b_snr, 'b-', label='Blue S/N', linewidth=2)
            
        else:
            # Grayscale only
            gray_flux = self.data.get('gray_flux_corrected', 
                                    self.data.get('flux_corrected', 
                                                pd.Series([0] * len(self.data))))
            raw_flux = self.data.get('gray_star_flux_raw',
                                   self.data.get('star_flux_raw', gray_flux))
            
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
            noise = self.data.get('gray_poisson_noise',
                                self.data.get('poisson_noise', pd.Series([1] * len(self.data))))
            snr = gray_flux / np.maximum(noise, 1)
            axes['snr'].plot(indices, snr, 'k-', linewidth=3, label='S/N Ratio')
            
            # Show RGB plot as "No RGB data"
            axes['rgb_separate'].text(0.5, 0.5, 'No RGB Data Available\\n(Grayscale only)',
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
        has_rgb = any(col.startswith(('r_flux_corrected', 'g_flux_corrected', 'b_flux_corrected')) 
                     for col in self.data.columns)
        
        axes = self.viz_axes['rgb']
        
        # Clear all axes
        for ax in axes.values():
            ax.clear()
        
        if not has_rgb:
            # Show "No RGB data" message on all plots
            for ax_name, ax in axes.items():
                ax.text(0.5, 0.5, 'No RGB Data Available\\n(Grayscale images only)',
                       transform=ax.transAxes, ha='center', va='center',
                       fontsize=16, alpha=0.5)
                ax.set_title(f'{ax_name.replace("_", " ").title()} (RGB Not Available)')
            return
        
        indices = self.data.get('image_index', pd.Series(range(len(self.data))))
        r_flux = self.data.get('r_flux_corrected', pd.Series([0] * len(self.data)))
        g_flux = self.data.get('g_flux_corrected', pd.Series([0] * len(self.data)))
        b_flux = self.data.get('b_flux_corrected', pd.Series([0] * len(self.data)))
        
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
        r_g_ratio = r_flux / np.maximum(g_flux, 1)
        b_g_ratio = b_flux / np.maximum(g_flux, 1)
        r_b_ratio = r_flux / np.maximum(b_flux, 1)
        
        axes['ratios'].plot(indices, r_g_ratio, 'orange', label='Red/Green', linewidth=2)
        axes['ratios'].plot(indices, b_g_ratio, 'purple', label='Blue/Green', linewidth=2)
        axes['ratios'].plot(indices, r_b_ratio, 'brown', label='Red/Blue', linewidth=2)
        axes['ratios'].set_title('Color Ratios Over Time')
        axes['ratios'].set_xlabel('Image Index')
        axes['ratios'].set_ylabel('Flux Ratio')
        axes['ratios'].legend()
        axes['ratios'].grid(True, alpha=0.3)
        
        # Color index (astronomical)
        b_v_index = -2.5 * np.log10(np.maximum(b_flux, 1) / np.maximum(g_flux, 1))
        v_r_index = -2.5 * np.log10(np.maximum(g_flux, 1) / np.maximum(r_flux, 1))
        
        axes['color_index'].plot(indices, b_v_index, 'cyan', label='B-V Index', linewidth=2)
        axes['color_index'].plot(indices, v_r_index, 'magenta', label='V-R Index', linewidth=2)
        axes['color_index'].set_title('Astronomical Color Indices')
        axes['color_index'].set_xlabel('Image Index')
        axes['color_index'].set_ylabel('Color Index (mag)')
        axes['color_index'].legend()
        axes['color_index'].grid(True, alpha=0.3)
        
        # Channel noise comparison
        r_noise = self.data.get('r_poisson_noise', pd.Series([0] * len(self.data)))
        g_noise = self.data.get('g_poisson_noise', pd.Series([0] * len(self.data)))
        b_noise = self.data.get('b_poisson_noise', pd.Series([0] * len(self.data)))
        
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
        indices = self.data.get('image_index', pd.Series(range(len(self.data))))
        
        axes = self.viz_axes['quality']
        
        # Clear all axes
        for ax in axes.values():
            ax.clear()
        
        # Sky background levels
        has_rgb = any(col.startswith(('r_sky_per_pixel', 'g_sky_per_pixel', 'b_sky_per_pixel')) 
                     for col in self.data.columns)
        
        if has_rgb:
            r_sky = self.data.get('r_sky_per_pixel', pd.Series([0] * len(self.data)))
            g_sky = self.data.get('g_sky_per_pixel', pd.Series([0] * len(self.data)))
            b_sky = self.data.get('b_sky_per_pixel', pd.Series([0] * len(self.data)))
            gray_sky = self.data.get('gray_sky_per_pixel', pd.Series([0] * len(self.data)))
            
            axes['sky_background'].plot(indices, r_sky, 'r-', label='Red Sky', linewidth=2, alpha=0.7)
            axes['sky_background'].plot(indices, g_sky, 'g-', label='Green Sky', linewidth=2, alpha=0.7)
            axes['sky_background'].plot(indices, b_sky, 'b-', label='Blue Sky', linewidth=2, alpha=0.7)
            axes['sky_background'].plot(indices, gray_sky, 'k-', label='Grayscale Sky', linewidth=2)
        else:
            gray_sky = self.data.get('gray_sky_per_pixel',
                                   self.data.get('sky_per_pixel', pd.Series([0] * len(self.data))))
            axes['sky_background'].plot(indices, gray_sky, 'k-', linewidth=3, label='Sky Background')
        
        axes['sky_background'].set_title('Sky Background Variation')
        axes['sky_background'].set_xlabel('Image Index')
        axes['sky_background'].set_ylabel('Sky Level (ADU/pixel)')
        axes['sky_background'].legend()
        axes['sky_background'].grid(True, alpha=0.3)
        
        # Sky noise (standard deviation)
        if has_rgb:
            r_sky_std = self.data.get('r_sky_std', pd.Series([0] * len(self.data)))
            g_sky_std = self.data.get('g_sky_std', pd.Series([0] * len(self.data)))
            b_sky_std = self.data.get('b_sky_std', pd.Series([0] * len(self.data)))
            gray_sky_std = self.data.get('gray_sky_std', pd.Series([0] * len(self.data)))
            
            axes['sky_noise'].plot(indices, r_sky_std, 'r-', label='Red Sky σ', linewidth=2, alpha=0.7)
            axes['sky_noise'].plot(indices, g_sky_std, 'g-', label='Green Sky σ', linewidth=2, alpha=0.7)
            axes['sky_noise'].plot(indices, b_sky_std, 'b-', label='Blue Sky σ', linewidth=2, alpha=0.7)
            axes['sky_noise'].plot(indices, gray_sky_std, 'k-', label='Gray Sky σ', linewidth=2)
        else:
            gray_sky_std = self.data.get('gray_sky_std',
                                       self.data.get('sky_std', pd.Series([0] * len(self.data))))
            axes['sky_noise'].plot(indices, gray_sky_std, 'k-', linewidth=3, label='Sky Noise')
        
        axes['sky_noise'].set_title('Sky Background Noise (σ)')
        axes['sky_noise'].set_xlabel('Image Index')
        axes['sky_noise'].set_ylabel('Sky Standard Deviation (ADU)')
        axes['sky_noise'].legend()
        axes['sky_noise'].grid(True, alpha=0.3)
        
        # Poisson noise
        if has_rgb:
            r_poisson = self.data.get('r_poisson_noise', pd.Series([0] * len(self.data)))
            g_poisson = self.data.get('g_poisson_noise', pd.Series([0] * len(self.data)))
            b_poisson = self.data.get('b_poisson_noise', pd.Series([0] * len(self.data)))
            
            axes['poisson_noise'].plot(indices, r_poisson, 'r-', label='Red Poisson', linewidth=2, alpha=0.7)
            axes['poisson_noise'].plot(indices, g_poisson, 'g-', label='Green Poisson', linewidth=2, alpha=0.7)
            axes['poisson_noise'].plot(indices, b_poisson, 'b-', label='Blue Poisson', linewidth=2, alpha=0.7)
        
        gray_poisson = self.data.get('gray_poisson_noise',
                                   self.data.get('poisson_noise', pd.Series([0] * len(self.data))))
        axes['poisson_noise'].plot(indices, gray_poisson, 'k-', linewidth=3, alpha=0.8, label='Grayscale Poisson')
        axes['poisson_noise'].set_title('Poisson Noise (√N)')
        axes['poisson_noise'].set_xlabel('Image Index')
        axes['poisson_noise'].set_ylabel('Poisson Noise (ADU)')
        axes['poisson_noise'].legend()
        axes['poisson_noise'].grid(True, alpha=0.3)
        
        # Total Signal-to-Noise Ratio
        if has_rgb:
            r_flux = self.data.get('r_flux_corrected', pd.Series([0] * len(self.data)))
            g_flux = self.data.get('g_flux_corrected', pd.Series([0] * len(self.data)))
            b_flux = self.data.get('b_flux_corrected', pd.Series([0] * len(self.data)))
            r_noise = self.data.get('r_poisson_noise', pd.Series([1] * len(self.data)))
            g_noise = self.data.get('g_poisson_noise', pd.Series([1] * len(self.data)))
            b_noise = self.data.get('b_poisson_noise', pd.Series([1] * len(self.data)))
            
            r_snr = r_flux / np.maximum(r_noise, 1)
            g_snr = g_flux / np.maximum(g_noise, 1)
            b_snr = b_flux / np.maximum(b_noise, 1)
            
            axes['total_snr'].plot(indices, r_snr, 'r-', label='Red S/N', linewidth=2)
            axes['total_snr'].plot(indices, g_snr, 'g-', label='Green S/N', linewidth=2)
            axes['total_snr'].plot(indices, b_snr, 'b-', label='Blue S/N', linewidth=2)
            
            gray_flux = self.data.get('gray_flux_corrected', pd.Series([0] * len(self.data)))
            gray_noise = self.data.get('gray_poisson_noise', pd.Series([1] * len(self.data)))
            gray_snr = gray_flux / np.maximum(gray_noise, 1)
            axes['total_snr'].plot(indices, gray_snr, 'k-', label='Grayscale S/N', linewidth=2, alpha=0.8)
        else:
            gray_flux = self.data.get('gray_flux_corrected',
                                    self.data.get('flux_corrected', pd.Series([0] * len(self.data))))
            gray_noise = self.data.get('gray_poisson_noise',
                                     self.data.get('poisson_noise', pd.Series([1] * len(self.data))))
            gray_snr = gray_flux / np.maximum(gray_noise, 1)
            axes['total_snr'].plot(indices, gray_snr, 'k-', linewidth=3, label='S/N Ratio')
        
        axes['total_snr'].set_title('Signal-to-Noise Ratio')
        axes['total_snr'].set_xlabel('Image Index')
        axes['total_snr'].set_ylabel('S/N Ratio')
        axes['total_snr'].legend()
        axes['total_snr'].grid(True, alpha=0.3)
    
    def update_tracking_plots(self):
        """Update star tracking analysis plots"""
        indices = self.data.get('image_index', pd.Series(range(len(self.data))))
        
        axes = self.viz_axes['tracking']
        
        # Clear all axes
        for ax in axes.values():
            ax.clear()
        
        # Extract position data
        x_positions = self.data.get('x_position', pd.Series([0] * len(self.data)))
        y_positions = self.data.get('y_position', pd.Series([0] * len(self.data)))
        movements = self.data.get('movement_pixels', pd.Series([0] * len(self.data)))
        
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
            try:
                cbar = self.viz_figures['tracking'].colorbar(scatter, ax=axes['position_scatter'])
                cbar.set_label('Image Index')
            except:
                pass  # Skip colorbar if it fails
        
        axes['position_scatter'].set_title('Star Position Scatter Plot')
        axes['position_scatter'].set_xlabel('X Position (pixels)')
        axes['position_scatter'].set_ylabel('Y Position (pixels)')
        axes['position_scatter'].set_aspect('equal', adjustable='box')
        axes['position_scatter'].grid(True, alpha=0.3)
        
        # Drift statistics
        if len(x_positions) > 1:
            x_drift = x_positions.max() - x_positions.min()
            y_drift = y_positions.max() - y_positions.min()
            total_drift = np.sqrt(x_drift**2 + y_drift**2)
            mean_movement = movements.mean() if len(movements) > 1 else 0
            max_movement = movements.max()
            
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
        
        axes['drift_stats'].set_xlim(0, 1)
        axes['drift_stats'].set_ylim(0, 1)
        axes['drift_stats'].set_title('Tracking Statistics')
        axes['drift_stats'].axis('off')
    
    def export_plots(self):
        """Export all plots as image files"""
        if not hasattr(self, 'viz_figures') or not self.viz_figures:
            messagebox.showwarning("No Plots", "No plots to export. Please load data first.")
            return
        
        export_dir = filedialog.askdirectory(
            title="Select Export Directory",
            initialdir=self.get_results_dir()
        )
        
        if not export_dir:
            return
        
        try:
            base_name = f"{self.star_name}_plots"
            exported_files = []
            
            for plot_type, fig in self.viz_figures.items():
                filename = f"{base_name}_{plot_type}.png"
                filepath = os.path.join(export_dir, filename)
                fig.savefig(filepath, dpi=300, bbox_inches='tight')
                exported_files.append(filename)
            
            success_msg = f"Successfully exported {len(exported_files)} plot files:\\n\\n"
            success_msg += "\\n".join(exported_files)
            success_msg += f"\\n\\nLocation: {export_dir}"
            
            messagebox.showinfo("Export Complete", success_msg)
            
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export plots:\\n{str(e)}")

def main():
    """Main function to start the application"""
    # Check for required dependencies
    try:
        import pandas as pd
        import matplotlib.pyplot as plt
    except ImportError as e:
        error_msg = f"Missing required dependencies: {e}\\n\\nPlease install with:\\npip install pandas matplotlib"
        print(error_msg)
        if 'tkinter' in str(e):
            print("Note: tkinter should be included with Python")
        return
    
    # Create and run the application
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
    
    app = PhotometryVisualizer(root)
    
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