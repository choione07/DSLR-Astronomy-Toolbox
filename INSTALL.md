# DSLR Telescope Astronomy Toolbox - Installation Guide

## Quick Start

### 1. Install Python Dependencies

```bash
pip install -r requirements.txt
```

**Note:** If you get an error about `tkinter`, don't worry! `tkinter` is included with Python by default and doesn't need to be installed separately.

### 2. Run the Application

```bash
python main.py
```

This will launch the main toolbox interface where you can access all tools.

## Alternative: Run Individual Tools

You can also run any tool directly:

```bash
python convert.py          # CR3 to FITS converter
python calibration_gui.py  # Image calibration
python photometry.py       # Photometry analysis
python viewer.py           # FITS image viewer
python visualize.py        # Data visualization
```

## Troubleshooting

### Common Installation Issues

**Problem: "tkinter not found" error during pip install**
- **Solution**: Remove or ignore this error. tkinter comes with Python by default.

**Problem: "No module named 'astropy'" when running tools**
- **Solution**: Install dependencies with `pip install -r requirements.txt`

**Problem: "File not found" errors when launching from main.py**
- **Solution**: Make sure all `.py` files are in the same directory as `main.py`

### Dependencies

Required packages (auto-installed with requirements.txt):
- `astropy >= 5.0` - FITS file handling and astronomical calculations
- `photutils >= 1.5.0` - Professional aperture photometry tools
- `numpy >= 1.21.0` - Numerical computing and array operations
- `scipy >= 1.7.0` - Statistical functions and image processing
- `matplotlib >= 3.5.0` - Plotting, visualization, and GUI integration
- `rawpy >= 0.17.0` - Canon CR3 raw file processing
- `Pillow >= 9.0.0` - Image processing utilities

**Note:** tkinter is included with Python and does not need separate installation

### System Requirements

- **Python**: 3.8 or newer
- **Operating System**: Windows, macOS, or Linux
- **Memory**: 4GB RAM minimum (8GB recommended for large images)
- **Storage**: 100MB for software + space for your FITS images

## File Structure

When you download the toolbox, make sure these files are all in the same directory:

```
astronomy-toolbox/
├── main.py              # Main launcher (START HERE)
├── convert.py           # CR3 to FITS converter
├── calibration_gui.py   # Calibration interface
├── calibration.py       # Calibration engine
├── photometry.py        # Photometry analysis
├── viewer.py            # FITS image viewer
├── visualize.py         # Data visualization
├── progress.py          # Progress tracking utility
├── requirements.txt     # Python dependencies
└── INSTALL.md          # This installation guide
```

## Getting Started

1. **Install dependencies**: `pip install -r requirements.txt`
2. **Launch the toolbox**: `python main.py`
3. **Check dependencies**: Click "Check Dependencies" in the main window
4. **Follow the workflow**: Convert → Calibrate → Analyze

## Support

If you encounter issues:

1. **Check dependencies**: Use the "Check Dependencies" button in main.py
2. **Verify file structure**: Make sure all .py files are in the same directory
3. **Update Python**: Ensure you're using Python 3.8 or newer
4. **Reinstall packages**: Try `pip install --upgrade -r requirements.txt`

For the complete workflow documentation, click "Show Documentation" in the main application window.