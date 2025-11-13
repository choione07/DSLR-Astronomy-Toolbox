# DSLR Telescope Astronomy Toolbox

A complete Python-based astronomy image processing pipeline for DSLR telescope photography, from raw CR3 files to professional photometry analysis.

## Overview

This toolbox provides a comprehensive workflow for processing telescope images captured with DSLR cameras:
- **Convert** Canon CR3 raw files to FITS format
- **Calibrate** images with bias/dark/flat corrections
- **Analyze** stellar brightness through aperture photometry
- **Visualize** results with publication-quality plots

Perfect for variable star studies, exoplanet transit photometry, and astronomical research.

## Quick Start

### Installation

1. **Install Python dependencies:**
   ```bash
   pip install astropy photutils matplotlib numpy scipy rawpy
   ```

2. **Launch the application:**
   ```bash
   python main.py
   ```

### Basic Workflow

1. **Convert Raw Images** → Launch `convert.py` to convert CR3 files to FITS
2. **Calibrate Images** → Use `calibration_gui.py` for bias/dark/flat corrections  
3. **Perform Photometry** → Run `photometry.py` for star tracking and measurements

## Features

- **Complete Workflow**: CR3 → FITS → Calibration → Photometry
- **User-Friendly GUIs**: Intuitive interfaces for all processing steps
- **RGB & Grayscale Support**: Handles both color and monochrome images
- **Automatic Star Tracking**: Centroid-based tracking across image sequences
- **Manual Sequential Mode**: Frame-by-frame analysis for precise control
- **Professional Photometry**: Sigma-clipped sky background estimation with robust outlier rejection
- **Correct Noise Calculation**: Physically accurate Poisson noise from raw photon counts
- **Standard CCD Calibration**: Proper bias/dark correction of flat frames following best practices
- **Advanced Dark Optimization**: Improved dark frame scaling using robust statistical methods
- **Data Visualization**: Comprehensive analysis with light curves, color analysis, and quality metrics
- **Scientific Output**: CSV export compatible with analysis software

## Recent Improvements (v1.1)

**Critical Algorithm Fixes:**
- ✓ Fixed RGB photometry to use sigma-clipped statistics (robust against cosmic rays and hot pixels)
- ✓ Corrected Poisson noise calculation to use raw counts (physically accurate uncertainty estimation)
- ✓ Improved dark frame optimization using median-based robust statistics
- ✓ Fixed flat field calibration to properly subtract bias/dark from flat frames (standard CCD procedure)

These fixes significantly improve photometric accuracy and follow professional astronomical calibration standards.

## System Requirements

- **Python**: 3.8+ with tkinter support
- **Operating System**: Windows, macOS, or Linux
- **Memory**: 4GB+ RAM recommended
- **Display**: 1400×900 minimum resolution

## Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `astropy` | ≥ 5.0 | FITS file handling, astronomical calculations |
| `photutils` | ≥ 1.5.0 | Aperture photometry, star detection |
| `matplotlib` | ≥ 3.5.0 | Visualization, GUI integration |
| `numpy` | ≥ 1.21 | Array operations, mathematical functions |
| `scipy` | ≥ 1.7 | Statistical functions, image processing |
| `rawpy` | latest | Canon CR3 raw file processing |

## Usage Guide

### 1. Image Conversion
Convert Canon CR3 files to FITS format:
```bash
python convert.py
```
- Select input folder with CR3 files
- Choose output format (RGB FITS or Grayscale FITS)
- Process entire directories automatically

### 2. Image Calibration
Apply bias, dark, and flat field corrections:
```bash
python calibration_gui.py
```
- Load calibration frames (bias, dark, flat)
- Create master frames with median stacking
- Apply corrections to light frames
- Output calibrated FITS files

### 3. Aperture Photometry
Measure stellar brightness with professional accuracy:
```bash
python photometry.py
```

**Basic Steps:**
1. Select folder containing calibrated FITS files
2. Enter star name for identification
3. Click on target star in the first image
4. Adjust aperture radii using sliders:
   - **Star Aperture**: Inner circle for star flux (typically 3-8 pixels)
   - **Inner Sky**: Start of background annulus (typically 12-20 pixels)
   - **Outer Sky**: End of background annulus (typically 20-30 pixels)
5. Choose processing mode:
   - **Automatic**: Tracks star automatically across sequence
   - **Manual Sequential**: Click star position in each frame
6. Start photometry analysis
7. Save results as CSV file

### 4. Data Analysis
View comprehensive analysis:
- **Light Curves**: Brightness variations over time
- **RGB Analysis**: Multi-channel color photometry
- **Quality Metrics**: Background stability and noise analysis
- **Tracking Analysis**: Position drift and movement quality

## Output Data

Results are saved as CSV files in the `./results/` directory containing:
- **Position Data**: x, y coordinates and tracking information
- **Photometry**: Raw flux, sky-corrected flux, background levels
- **Uncertainty**: Poisson noise and sky standard deviation
- **Metadata**: FITS headers, timestamps, processing parameters

For RGB images, separate measurements are provided for Red, Green, Blue, and Grayscale channels.

## Scientific Applications

- **Variable Star Studies**: Monitor brightness changes in Cepheids, RR Lyrae, etc.
- **Exoplanet Photometry**: Detect planetary transits and measure light curves
- **Asteroid Research**: Determine rotation periods and brightness variations
- **Color Photometry**: Multi-channel stellar color analysis
- **Educational Projects**: University astronomy labs and student research

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "No star detected" | Adjust sensitivity slider to lower values (0.5σ-1.0σ) |
| "Lost tracking" | Reduce aperture size or switch to manual mode |
| "Import errors" | Install missing dependencies with pip |
| "Memory issues" | Process smaller batches of images |

## Documentation

- **README.md** (this file): Quick start guide and basic usage
- **DOCUMENTATION.md**: Complete technical documentation
- **requirements.txt**: Exact dependency versions

## Contributing

This toolbox implements professional astronomical methodology following international standards. The system is designed for both amateur astronomers and research applications.

For detailed technical information, algorithm descriptions, and advanced usage, see [DOCUMENTATION.md](DOCUMENTATION.md).

## License

Open source astronomy software for educational and research use.

---

*A complete solution for DSLR telescope photometry - from raw images to scientific results.*