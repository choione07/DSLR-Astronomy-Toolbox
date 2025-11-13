#!/usr/bin/env python3
"""
Astronomy Toolbox - Main Launcher GUI
A unified home page for all your astronomy image processing tools
Created: 2025-08-27
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import subprocess
import sys
import os
from pathlib import Path
import threading

class AstronomyToolbox:
    def __init__(self, root):
        self.root = root
        self.root.title("Astronomy Toolbox")
        self.root.geometry("800x800")

        # Create main interface
        self.create_header()
        self.create_workflow_section()
        self.create_tools_section()
        self.create_actions_section()
        self.create_status_section()

    def create_header(self):
        """Create the main header section"""
        header_frame = tk.Frame(self.root)
        header_frame.pack(fill=tk.X, padx=20, pady=20)

        # Main title
        title_label = tk.Label(header_frame, text="DSLR Telescope Astronomy Toolbox",
                              font=('Arial', 24, 'bold'))
        title_label.pack()

        # Subtitle
        subtitle_label = tk.Label(header_frame,
                                 text="Workflow: CR3 to FITS Conversion → Calibration → Aperture Photometry",
                                 font=('Arial', 14))
        subtitle_label.pack(pady=(5, 0))

        # Separator
        separator = ttk.Separator(header_frame, orient='horizontal')
        separator.pack(fill=tk.X, pady=(15, 0))

    def create_workflow_section(self):
        """Create the main workflow section"""
        workflow_frame = tk.Frame(self.root)
        workflow_frame.pack(fill=tk.X, padx=20, pady=(10, 20))

        # Section title
        tk.Label(workflow_frame, text="Workflow",
                font=('Arial', 18, 'bold')).pack(anchor=tk.W)

        # Workflow buttons frame
        buttons_frame = tk.Frame(workflow_frame)
        buttons_frame.pack(fill=tk.X, pady=10)

        # Workflow steps
        workflow_steps = [
            ("1. Convert Raw Files", "CR3 to FITS conversion", "convert.py"),
            ("2. Calibrate Images", "Bias/Dark/Flat correction", "calibration_gui.py"),
            ("3. Photometry Analysis", "Star measurement & tracking", "photometry.py")
        ]

        for i, (title, desc, filename) in enumerate(workflow_steps):
            step_frame = tk.Frame(buttons_frame, relief=tk.RIDGE, bd=2)
            step_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)

            # Title
            tk.Label(step_frame, text=title, font=('Arial', 14, 'bold')).pack(pady=(15, 5))

            # Description
            tk.Label(step_frame, text=desc, font=('Arial', 12),
                    wraplength=250, height=2).pack(pady=(0, 15))

            # Launch button
            tk.Button(step_frame, text="Launch", font=('Arial', 14),
                     command=lambda f=filename: self.launch_tool(f),
                     width=14).pack(pady=(0, 15))

    def create_tools_section(self):
        """Create individual tools section"""
        tools_frame = tk.Frame(self.root)
        tools_frame.pack(fill=tk.X, padx=20, pady=(0, 20))

        # Section title
        tk.Label(tools_frame, text="Individual Tools",
                font=('Arial', 18, 'bold')).pack(anchor=tk.W)

        # Tools grid
        tools_grid = tk.Frame(tools_frame)
        tools_grid.pack(fill=tk.X, pady=10)

        tools = [
            ("FITS Viewer", "View FITS images", "viewer.py"),
            ("Data Visualizer", "Visualize photometry CSV results", "visualize.py"),
            ("Magnitude Analyzer", "Fourier analysis & magnitude conversion", "analyze.py")
        ]

        # Create compact tool display
        for i, (name, desc, filename) in enumerate(tools):
            tool_frame = tk.Frame(tools_grid, relief=tk.RIDGE, bd=1)
            tool_frame.pack(fill=tk.X, pady=2)

            # Create horizontal layout for compact display
            content_frame = tk.Frame(tool_frame)
            content_frame.pack(fill=tk.X, padx=8, pady=6)

            # Tool info on left
            info_frame = tk.Frame(content_frame)
            info_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)

            # Tool name
            tk.Label(info_frame, text=name, font=('Arial', 14, 'bold')).pack(anchor=tk.W)

            # Tool description
            tk.Label(info_frame, text=desc, font=('Arial', 12)).pack(anchor=tk.W, pady=(2, 0))

            # Launch button on right
            tk.Button(content_frame, text="Launch", font=('Arial', 14),
                     command=lambda f=filename: self.launch_tool(f),
                     width=12).pack(side=tk.RIGHT, padx=(10, 0))

    def create_actions_section(self):
        """Create quick action buttons"""
        actions_frame = tk.Frame(self.root)
        actions_frame.pack(fill=tk.X, padx=20, pady=(0, 10))

        # Section title
        tk.Label(actions_frame, text="Quick Actions",
                font=('Arial', 18, 'bold')).pack(anchor=tk.W)

        # Buttons frame
        buttons_frame = tk.Frame(actions_frame)
        buttons_frame.pack(fill=tk.X, pady=10)

        # Action buttons
        actions = [
            ("Open Results Folder", self.open_results_folder),
            ("Show Documentation", self.show_documentation),
            ("Check Dependencies", self.check_dependencies),
            ("Exit", self.root.quit)
        ]

        for text, command in actions:
            tk.Button(buttons_frame, text=text, command=command, font=('Arial', 12),
                     width=18).pack(side=tk.LEFT, padx=5)

    def create_status_section(self):
        """Create status section"""
        status_frame = tk.Frame(self.root, relief=tk.SUNKEN, bd=1)
        status_frame.pack(fill=tk.X, side=tk.BOTTOM)

        self.status_var = tk.StringVar(value="Ready - All tools available")
        status_label = tk.Label(status_frame, textvariable=self.status_var,
                               font=('Arial', 10))
        status_label.pack(side=tk.LEFT, padx=10, pady=5)

        # Version info
        version_label = tk.Label(status_frame, text="Astronomy Toolbox v1.0",
                                font=('Arial', 10), fg='gray')
        version_label.pack(side=tk.RIGHT, padx=10, pady=5)

    def launch_tool(self, filename):
        """Launch a specific tool"""
        try:
            self.status_var.set(f"Launching {filename}...")
            self.root.update()

            # Get the directory where main.py is located
            script_dir = os.path.dirname(os.path.abspath(__file__))
            tool_path = os.path.join(script_dir, filename)

            # Check if file exists in the same directory as main.py
            if not os.path.exists(tool_path):
                # Fallback: check current working directory
                if os.path.exists(filename):
                    tool_path = filename
                else:
                    messagebox.showerror("Error", f"File not found: {filename}\nSearched in:\n- {tool_path}\n- {os.path.abspath(filename)}")
                    self.status_var.set("Launch failed - File not found")
                    return

            # Launch in separate process
            def launch_process():
                try:
                    subprocess.Popen([sys.executable, tool_path])
                    self.root.after(2000, lambda: self.status_var.set("Ready - All tools available"))
                except Exception as e:
                    self.root.after(0, lambda: messagebox.showerror("Launch Error", f"Failed to launch {filename}:\n{str(e)}"))
                    self.root.after(0, lambda: self.status_var.set("Launch failed"))

            threading.Thread(target=launch_process, daemon=True).start()

        except Exception as e:
            messagebox.showerror("Launch Error", f"Failed to launch {filename}:\n{str(e)}")
            self.status_var.set("Launch failed")

    def open_results_folder(self):
        """Open the results folder"""
        results_path = Path("results")
        if results_path.exists():
            if sys.platform == "darwin":  # macOS
                subprocess.run(["open", str(results_path)])
            elif sys.platform == "win32":  # Windows
                subprocess.run(["explorer", str(results_path)])
            else:  # Linux
                subprocess.run(["xdg-open", str(results_path)])
            self.status_var.set("Results folder opened")
        else:
            messagebox.showinfo("Results Folder", "Results folder doesn't exist yet.\nRun photometry analysis to create it.")

    def show_documentation(self):
        """Show documentation information"""
        doc_text = """ASTRONOMY TOOLBOX DOCUMENTATION

WORKFLOW OVERVIEW:
1. Convert CR3 files to FITS format using convert.py
2. Calibrate images (bias, dark, flat correction) using calibration_gui.py  
3. Perform photometry analysis using photometry.py

TOOL DESCRIPTIONS:

convert.py - CR3 to FITS Converter
• Converts Canon CR3 raw files to FITS format
• Supports both grayscale and RGB conversion
• Essential first step for telescope image processing

calibration_gui.py - Image Calibration
• Applies bias, dark, and flat field corrections
• Creates master calibration frames
• DeepSkyStacker-style methodology
• Prepares images for scientific analysis

photometry.py - Photometry Suite  
• Star tracking and aperture photometry
• Sequential and automatic tracking modes
• RGB and grayscale analysis support
• Exports results to CSV for further analysis

viewer.py - FITS Image Viewer
• Display FITS images with proper scaling
• Supports both grayscale and RGB FITS files
• Integrated into other tools for image preview

visualize.py - Data Visualizer
• Visualize photometry CSV results with professional graphs
• Load saved CSV files from results folder
• RGB analysis, quality metrics, and tracking plots
• Export publication-quality plots

analyze.py - Magnitude Analyzer
• Convert photometry data to absolute magnitudes
• Differential photometry using reference star
• Fourier transform analysis for period detection
• Phase-folded light curves and frequency analysis

WORKFLOW TIPS:
• Always calibrate your images before photometry
• Use consistent aperture sizes for comparison
• Save results regularly during long processing runs
• Check image quality at each step

For technical support, check the individual tool documentation."""

        doc_window = tk.Toplevel(self.root)
        doc_window.title("Documentation")
        doc_window.geometry("600x500")

        text_widget = tk.Text(doc_window, font=('Courier', 10), wrap=tk.WORD)
        text_widget.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        text_widget.insert(tk.END, doc_text)
        text_widget.configure(state='disabled')

        # Add close button
        tk.Button(doc_window, text="Close", command=doc_window.destroy).pack(pady=10)

    def check_dependencies(self):
        """Check if all required dependencies are available"""
        dependencies = {
            'astropy': 'Astronomy library for FITS files',
            'numpy': 'Numerical computing',
            'matplotlib': 'Plotting and visualization',
            'tkinter': 'GUI framework',
            'photutils': 'Photometry tools',
            'rawpy': 'RAW image processing'
        }

        results = []
        all_good = True

        for dep, desc in dependencies.items():
            try:
                if dep == 'tkinter':
                    import tkinter
                else:
                    __import__(dep)
                results.append(f"OK: {dep} - {desc}")
            except ImportError:
                results.append(f"MISSING: {dep} - {desc}")
                all_good = False

        # Check tool files
        tool_files = [
            'convert.py', 'viewer.py', 'calibration_gui.py',
            'calibration.py', 'photometry.py', 'progress.py', 'visualize.py', 'analyze.py'
        ]

        results.append("\nTool Files:")
        script_dir = os.path.dirname(os.path.abspath(__file__))
        
        for tool in tool_files:
            tool_path = os.path.join(script_dir, tool)
            if os.path.exists(tool_path):
                results.append(f"OK: {tool}")
            elif os.path.exists(tool):  # Fallback to current directory
                results.append(f"OK: {tool} (in current directory)")
            else:
                results.append(f"MISSING: {tool}")
                all_good = False

        # Show results
        result_text = "\n".join(results)
        if all_good:
            result_text += "\n\nAll dependencies and tools are available!"
            status_msg = "All dependencies OK"
        else:
            result_text += "\n\nSome dependencies or tools are missing. Install missing packages with pip."
            status_msg = "Missing dependencies detected"

        messagebox.showinfo("Dependency Check", result_text)
        self.status_var.set(status_msg)

def main():
    """Main function to launch the astronomy toolbox"""
    root = tk.Tk()
    app = AstronomyToolbox(root)

    # Center the window
    root.update_idletasks()
    x = (root.winfo_screenwidth() // 2) - (root.winfo_width() // 2)
    y = (root.winfo_screenheight() // 2) - (root.winfo_height() // 2)
    root.geometry(f"+{x}+{y}")

    root.mainloop()

if __name__ == "__main__":
    main()