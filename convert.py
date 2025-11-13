import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import rawpy
from astropy.io import fits
import numpy as np
import threading
import time
import json
import copy

def C2F(inputDir, outputDir, progress_callback=None, stop_event=None):
    if not os.path.exists(outputDir):
        os.makedirs(outputDir)
    filesToProcess = [f for f in os.listdir(inputDir) if f.lower().endswith('.cr3')]
    total_files = len(filesToProcess)
    if not filesToProcess:
        messagebox.showinfo("Info", "No CR3 files found in the input directory.")
        return
    for i, filename in enumerate(filesToProcess):
        if stop_event and stop_event.is_set():
            break
        if progress_callback:
            progress_callback(i, total_files, f"Converting {filename}")
        inputPath = os.path.join(inputDir, filename)
        outputFilename = os.path.splitext(filename)[0] + '.fits'
        outputPath = os.path.join(outputDir, outputFilename)
        try:
            with rawpy.imread(inputPath) as raw:
                rawImage = np.flipud(raw.raw_image.copy())
            hdu = fits.PrimaryHDU(rawImage)
            hdul = fits.HDUList([hdu])
            hdul.writeto(outputPath, overwrite=True)
        except Exception as e:
            messagebox.showerror("Error", f"Could not convert {inputPath}: {e}")
    if progress_callback:
        progress_callback(total_files, total_files, "Conversion completed")

def C2F_RGB(inputDir, outputDir, progress_callback=None, stop_event=None):
    if not os.path.exists(outputDir):
        os.makedirs(outputDir)
    filesToProcess = [f for f in os.listdir(inputDir) if f.lower().endswith('.cr3')]
    total_files = len(filesToProcess)
    for i, filename in enumerate(filesToProcess):
        if stop_event and stop_event.is_set():
            break
        if progress_callback:
            progress_callback(i, total_files, f"Converting {filename} to RGB")
        inputPath = os.path.join(inputDir, filename)
        outputFilename = os.path.splitext(filename)[0] + '_rgb.fits'
        outputPath = os.path.join(outputDir, outputFilename)
        try:
            with rawpy.imread(inputPath) as raw:
                rgb = raw.postprocess(output_bps=16)
            rgb_flipped = np.flipud(rgb) # Apply vertical flip for consistency
            rgb_transposed = np.transpose(rgb_flipped, (2, 0, 1)).astype(np.uint16)
            hdu = fits.PrimaryHDU(rgb_transposed)
            hdul = fits.HDUList([hdu])
            hdul.writeto(outputPath, overwrite=True)
        except Exception as e:
            messagebox.showerror("Error", f"Error converting {filename}: {e}")
    if progress_callback:
        progress_callback(total_files, total_files, "RGB conversion completed")

def F_RGB2F_Gray(inputDir, outputDir, progress_callback=None, stop_event=None):
    if not os.path.exists(outputDir):
        os.makedirs(outputDir)
    fitsFiles = [f for f in os.listdir(inputDir) if f.lower().endswith(('.fits', '.fit', '.fts'))]
    total_files = len(fitsFiles)
    if not fitsFiles:
        messagebox.showinfo("Info", "No FITS files found in the input directory.")
        return

    converted_count = 0
    for i, fitsFile in enumerate(fitsFiles):
        if stop_event and stop_event.is_set():
            break
        if progress_callback:
            progress_callback(i, total_files, f"Converting {fitsFile} to grayscale")
        fitsPath = os.path.join(inputDir, fitsFile)
        try:
            with fits.open(fitsPath) as hdul:
                data = hdul[0].data
                if data.ndim == 3 and data.shape[0] == 3:
                    # Apply weighted conversion for RGB to grayscale
                    # Weights are common luminance perception values
                    R, G, B = data[0, :, :], data[1, :, :], data[2, :, :]
                    gray_data = 0.2989 * R + 0.5870 * G + 0.1140 * B
                    grayFilename = fitsFile.replace('_rgb', '')
                    grayPath = os.path.join(outputDir, grayFilename)
                    hdu = fits.PrimaryHDU(gray_data.astype(np.float32))
                    hdu.writeto(grayPath, overwrite=True)
                    converted_count += 1
                else:
                    print(f"Skipping {fitsFile}: Not a 3-channel color FITS file.")
                    continue
        except Exception as e:
            messagebox.showerror("Error", f"Error converting {fitsFile}: {e}")

    if converted_count == 0:
        messagebox.showinfo("Info", "No color FITS files were found to convert.")
    elif progress_callback:
        progress_callback(total_files, total_files, f"Grayscale conversion completed - {converted_count} files")

def convert_rgb_to_gray_data(rgb_data):
    """
    Converts a 3-channel RGB FITS data array to a grayscale data array
    using weighted luminance conversion.
    Assumes input rgb_data has shape (3, H, W).
    """
    if rgb_data.ndim == 3 and rgb_data.shape[0] == 3:
        R, G, B = rgb_data[0, :, :], rgb_data[1, :, :], rgb_data[2, :, :]
        gray_data = 0.2989 * R + 0.5870 * G + 0.1140 * B
        return gray_data
    else:
        raise ValueError("Input data must be a 3-channel RGB array (shape: 3, H, W).")

class ConverterApp:
    def __init__(self, master):
        self.master = master
        master.title("FITS Format Converter")
        master.geometry("600x400")

        self.inputDir = tk.StringVar()
        self.outputDir = tk.StringVar()
        self.inputFormat = tk.StringVar()
        self.outputFormat = tk.StringVar()
        
        # Conversion state
        self.is_converting = False
        self.conversion_thread = None
        self.stop_event = threading.Event()

        # Input folder
        tk.Label(master, text="Input Folder:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        tk.Entry(master, textvariable=self.inputDir, width=50).grid(row=0, column=1, padx=5, pady=5)
        tk.Button(master, text="Browse...", command=self.browseInput).grid(row=0, column=2, padx=5, pady=5)

        # Output folder
        tk.Label(master, text="Output Folder:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        tk.Entry(master, textvariable=self.outputDir, width=50).grid(row=1, column=1, padx=5, pady=5)
        tk.Button(master, text="Browse...", command=self.browseOutput).grid(row=1, column=2, padx=5, pady=5)

        # Input format
        tk.Label(master, text="Input Format:").grid(row=2, column=0, sticky="w", padx=5, pady=5)
        inputFormats = ["CR3", "FITS (Color)"]
        self.inputFormat.set(inputFormats[0])
        ttk.Combobox(master, textvariable=self.inputFormat, values=inputFormats, state="readonly").grid(row=2, column=1, sticky="ew", padx=5, pady=5)

        # Output format
        tk.Label(master, text="Output Format:").grid(row=3, column=0, sticky="w", padx=5, pady=5)
        outputFormats = ["FITS (Grayscale)", "FITS (Color)"]
        self.outputFormat.set(outputFormats[1])  # Default to FITS (Color)
        ttk.Combobox(master, textvariable=self.outputFormat, values=outputFormats, state="readonly").grid(row=3, column=1, sticky="ew", padx=5, pady=5)

        # Control buttons
        button_frame = tk.Frame(master)
        button_frame.grid(row=4, column=0, columnspan=3, pady=10)
        
        self.convert_btn = tk.Button(button_frame, text="Convert", command=self.convert)
        self.convert_btn.pack(side=tk.LEFT, padx=5)
        
        self.stop_btn = tk.Button(button_frame, text="Stop", command=self.stop_conversion, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)

        # Progress section
        progress_frame = tk.Frame(master)
        progress_frame.grid(row=5, column=0, columnspan=3, sticky="ew", padx=10, pady=10)
        
        self.progress_label = tk.Label(progress_frame, text="Ready")
        self.progress_label.pack()
        
        self.progress_bar = ttk.Progressbar(progress_frame, mode='determinate')
        self.progress_bar.pack(fill=tk.X, pady=5)
        
        # Log output section
        log_frame = tk.LabelFrame(master, text="Conversion Log")
        log_frame.grid(row=6, column=0, columnspan=3, sticky="nsew", padx=10, pady=10)
        
        self.log_text = tk.Text(log_frame, height=8, width=70)
        scrollbar = tk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Display any pending log messages from initialization
        if hasattr(self, '_pending_log_messages'):
            for message in self._pending_log_messages:
                self.log_text.insert(tk.END, message)
            delattr(self, '_pending_log_messages')
            self.log_text.see(tk.END)
        
        # Configure grid weights
        master.grid_rowconfigure(6, weight=1)
        master.grid_columnconfigure(1, weight=1)
        
        # Load last used options if remember feature is enabled
        




    def browseInput(self):
        self.inputDir.set(filedialog.askdirectory())

    def browseOutput(self):
        self.outputDir.set(filedialog.askdirectory())

    def log_message(self, message):
        """Add message to log output"""
        # Handle case where log_text hasn't been created yet (during initialization)
        if hasattr(self, 'log_text'):
            self.log_text.insert(tk.END, f"{time.strftime('%H:%M:%S')} - {message}\n")
            self.log_text.see(tk.END)
            self.master.update()
        else:
            # Store messages for later when log_text is available
            if not hasattr(self, '_pending_log_messages'):
                self._pending_log_messages = []
            self._pending_log_messages.append(f"{time.strftime('%H:%M:%S')} - {message}\n")
    
    def update_progress(self, current, total, message):
        """Update progress bar and label"""
        if total > 0:
            progress_percent = (current / total) * 100
            self.progress_bar["value"] = progress_percent
        self.progress_label.config(text=f"{message} ({current}/{total})")
        self.master.update()
    
    def convert(self):
        if self.is_converting:
            return
            
        inputDir = self.inputDir.get()
        outputDir = self.outputDir.get()
        inputFormat = self.inputFormat.get()
        outputFormat = self.outputFormat.get()

        if not inputDir or not outputDir:
            messagebox.showerror("Error", "Please select both input and output directories.")
            return

        if inputFormat == outputFormat:
            messagebox.showerror("Error", "Input and output formats cannot be the same.")
            return
        
        # Clear log and reset progress
        self.log_text.delete(1.0, tk.END)
        self.progress_bar["value"] = 0
        self.stop_event.clear()
        
        # Update UI state
        self.is_converting = True
        self.convert_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        
        self.log_message(f"Starting conversion: {inputFormat} → {outputFormat}")
        self.log_message(f"Input folder: {inputDir}")
        self.log_message(f"Output folder: {outputDir}")
        
        # Start conversion in separate thread
        self.conversion_thread = threading.Thread(target=self.run_conversion, 
                                                args=(inputDir, outputDir, inputFormat, outputFormat),
                                                daemon=True)
        self.conversion_thread.start()
    
    def run_conversion(self, inputDir, outputDir, inputFormat, outputFormat):
        """Run conversion in separate thread"""
        try:
            if inputFormat == "CR3" and outputFormat == "FITS (Grayscale)":
                C2F(inputDir, outputDir, self.update_progress, self.stop_event)
            elif inputFormat == "CR3" and outputFormat == "FITS (Color)":
                C2F_RGB(inputDir, outputDir, self.update_progress, self.stop_event)
            elif inputFormat == "FITS (Color)" and outputFormat == "FITS (Grayscale)":
                F_RGB2F_Gray(inputDir, outputDir, self.update_progress, self.stop_event)
            else:
                self.master.after(0, lambda: messagebox.showerror("Error", 
                    f"Conversion from {inputFormat} to {outputFormat} is not supported."))
                return
            
            if self.stop_event.is_set():
                self.master.after(0, lambda: self.log_message("Conversion stopped by user"))
            else:
                self.master.after(0, lambda: self.log_message("Conversion completed successfully!"))
                self.master.after(0, lambda: messagebox.showinfo("Success", "Conversion complete."))
                
        except Exception as e:
            self.master.after(0, lambda: self.log_message(f"Error: {str(e)}"))
            self.master.after(0, lambda: messagebox.showerror("Error", f"An error occurred: {e}"))
        finally:
            # Reset UI state
            self.master.after(0, self.conversion_finished)
    
    def stop_conversion(self):
        """Stop the conversion process"""
        self.stop_event.set()
        self.log_message("Stop requested...")
        self.stop_btn.config(state=tk.DISABLED)
    
    def conversion_finished(self):
        """Clean up after conversion is finished"""
        self.is_converting = False
        self.convert_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)

if __name__ == "__main__":
    root = tk.Tk()
    app = ConverterApp(root)
    root.mainloop()