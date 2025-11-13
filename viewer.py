import tkinter as tk
from tkinter import filedialog, messagebox
import matplotlib
matplotlib.use('TkAgg')
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from astropy.io import fits
import numpy as np
import os
import json

class FitsViewer:
    def __init__(self, master, filename=None):
        self.master = master
        

        if filename:
            self.open_file(filename)
        else:
            self.open_file_dialog()
    

    def open_file_dialog(self):
        self.dialog = tk.Toplevel(self.master)
        self.dialog.title("Open FITS File")
        self.dialog.protocol("WM_DELETE_WINDOW", self.dialog.destroy) # Close only dialog, not main window

        tk.Label(self.dialog, text="Enter filename or browse:").pack(pady=10)
        self.entry = tk.Entry(self.dialog, width=50)

        self.entry.pack(pady=5, padx=10)

        browse_button = tk.Button(self.dialog, text="Browse", command=self.browse_file)
        browse_button.pack(pady=5)

        open_button = tk.Button(self.dialog, text="Open", command=self.handle_open_button)
        open_button.pack(pady=10)

    def browse_file(self):
        filename = filedialog.askopenfilename(
            title="Select a FITS file",
            filetypes=(("FITS files", "*.fits *.fts *.fit"), ("All files", "*.*"))
        )
        if filename:
            self.entry.delete(0, tk.END)
            self.entry.insert(0, filename)

    def handle_open_button(self):
        filename = self.entry.get()
        if not filename:
            messagebox.showerror("Error", "No file selected.")
            return
        
        self.open_file(filename)
        # Close the dialog after successful file opening
        if hasattr(self, 'dialog'):
            self.dialog.destroy()

    def open_file(self, filename):
        try:
            with fits.open(filename) as hdul:
                image_data = hdul[0].data
            self.show_fits_image(image_data, filename)
        except FileNotFoundError:
            messagebox.showerror("Error", f"File not found: {filename}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open or read FITS file: {e}")

    def show_fits_image(self, data, filename):
        display_window = tk.Toplevel(self.master)
        display_window.protocol("WM_DELETE_WINDOW", display_window.destroy) # Close only viewer window
        display_window.title(f"FITS Viewer - {os.path.basename(filename)}")
        
        # Make window resizable and set reasonable minimum size
        display_window.minsize(400, 400)
        
        # Don't make window modal - allow interaction with main window
        display_window.transient()  # Remove parent binding for better responsiveness

        fig = Figure(figsize=(6, 6))
        ax = fig.add_subplot(111)

        image_type = "Unsupported"
        data = data.astype(np.float32) # Work with a float copy

        # Handle Grayscale images
        if data.ndim == 2:
            image_type = "Grayscale"
            # Use percentile for robust contrast stretching
            vmin, vmax = np.percentile(data, [0.5, 99.5])
            img = ax.imshow(data, cmap='gray', origin='lower', vmin=vmin, vmax=vmax)
            fig.colorbar(img, ax=ax)  # Add colorbar for grayscale

        # Handle RGB images
        elif data.ndim == 3:
            display_data = None
            # Case 1: Color axis is FIRST (e.g., from rawpy conversion)
            if data.shape[0] in [3, 4]:
                image_type = "Colormap"
                # Transpose from (C, H, W) to (H, W, C) for matplotlib
                display_data = np.moveaxis(data, 0, -1)
            # Case 2: Color axis is LAST (e.g., from TIFF or other sources)
            elif data.shape[2] in [3, 4]:
                image_type = "Colormap"
                display_data = data
            
            if display_data is not None:
                # Normalize the data for display using percentile clipping
                vmin, vmax = np.percentile(display_data, [0.5, 99.5])
                display_data = np.clip(display_data, vmin, vmax)
                # Scale the data to the required [0, 1] range for imshow
                display_data = (display_data - vmin) / (vmax - vmin)
                img = ax.imshow(display_data, origin='lower')

        # If format is not supported, show error and close
        if image_type == "Unsupported":
            messagebox.showerror("Error", "Unsupported FITS data format (not 2D or 3D RGB).")
            display_window.destroy()
            return

        ax.set_title(os.path.basename(filename))

        canvas = FigureCanvasTkAgg(fig, master=display_window)
        canvas.draw()
        canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=1)

        status_label = tk.Label(display_window, text=f"Image Type: {image_type}", bd=1, relief=tk.SUNKEN, anchor=tk.W)
        status_label.pack(side=tk.BOTTOM, fill=tk.X)

if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()  # Hide the main window since we don't need it
    # To allow running from command line with a filename argument
    import sys
    if len(sys.argv) > 1:
        app = FitsViewer(root, filename=sys.argv[1])
    else:
        app = FitsViewer(root)
    root.mainloop()