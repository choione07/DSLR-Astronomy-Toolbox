# DSLR Telescope Astronomy Toolbox - Complete Technical Documentation

## System Overview

The DSLR Telescope Astronomy Toolbox is a comprehensive Python-based solution for astronomical image processing and photometry analysis, specifically designed for DSLR telescope photography. The system provides a complete workflow from raw CR3 image conversion to professional aperture photometry analysis with scientific data visualization and export capabilities.

### Project Purpose
- Process DSLR telescope images from raw format to calibrated FITS files
- Perform professional aperture photometry on variable stars and celestial objects
- Track stellar brightness changes over time with scientific accuracy
- Export publication-quality data for astronomical research and analysis
- Provide an integrated workflow for amateur and professional astronomers

### Target Applications
- Variable star photometry and monitoring
- Exoplanet transit photometry  
- Asteroid brightness measurements
- Stellar color analysis and photometric studies
- Time-series astronomical data collection
- DSLR telescope image calibration and processing

## System Components

### 1. Main Launcher (`main.py`)
**Purpose**: Unified control center serving as the main entry point for all astronomy processing tools.

**Key Features**:
- Central dashboard for all astronomy tools
- Step-by-step workflow guidance from CR3 to photometry
- Individual tool launching capabilities
- System dependency checking and validation
- Quick access to results folders and documentation

**Complete Workflow**:
1. **Convert Raw Files**: CR3 → FITS conversion
2. **Calibrate Images**: Bias/Dark/Flat correction
3. **Photometry Analysis**: Star measurement & tracking

### 2. Format Converter (`convert.py`)
**Purpose**: Converts Canon CR3 raw files to FITS format suitable for astronomical analysis.

**Main Functions**:
- **CR3 to Grayscale FITS**: Extracts raw sensor data, applies vertical flip
- **CR3 to RGB FITS**: Creates 3-channel RGB FITS with 16-bit output depth
- **RGB to Grayscale Conversion**: Weighted luminance using CIE standard coefficients
- **Interactive GUI Converter**: User-friendly batch processing interface

**Technical Specifications**:
- Input Formats: Canon CR3 raw files, RGB FITS files
- Output Formats: Grayscale FITS, RGB FITS (3-channel)
- Data Types: 16-bit integer for maximum dynamic range
- Processing Speed: ~5-15 seconds per CR3 file

### 3. Image Calibration System (`calibration_gui.py`, `calibration.py`)
**Purpose**: Professional astronomical image calibration following DeepSkyStacker methodology.

**Main Functions**:
- **Master Frame Creation**: Combines bias, dark, and flat frames using median stacking
- **Light Frame Calibration**: Applies bias, dark, and flat field corrections
- **Interactive Calibration GUI**: Real-time preview and progress monitoring
- **Quality Control**: Automatic detection of problematic frames

**Calibration Workflow** (Standard CCD Reduction):
1. Load bias frames → Create master bias (median combine)
2. Load dark frames → Create master dark (median combine, no correction needed)
3. Load flat frames → Bias/dark correct each flat → Create master flat (median combine)
4. Load light frames → Apply full calibration: (Light - Bias - Dark × scale) / Flat_normalized
5. Output calibrated FITS files ready for photometry

**Calibration Formula**:
```
Calibrated = (Raw - MasterBias - MasterDark × OptimizationFactor) / MasterFlat_normalized
```

Where:
- MasterFlat_normalized = (MasterFlat - Bias - Dark) / mean(MasterFlat)
- OptimizationFactor: Optional exposure time scaling (default: 1.0)

**Color Balance in Flat Fields**:
- Each RGB channel normalized to maintain proper color balance
- Uses minimum channel mean as reference to avoid noise amplification
- Prevents systematic color biases in calibrated images

### 4. FITS Image Viewer (`viewer.py`)
**Purpose**: Professional FITS image display tool for astronomical data visualization.

**Features**:
- Automatic format detection (grayscale vs RGB)
- Proper astronomical orientation
- Percentile-based contrast stretching (0.5-99.5%)
- Interactive features with zoom/pan
- Scientific visualization principles

### 5. Aperture Photometry Suite (`photometry.py`)
**Purpose**: Professional aperture photometry analysis system implementing scientific methodology.

## Scientific Methodology

### Aperture Photometry Implementation
The system implements professional aperture photometry following astronomical best practices:

1. **Robust Sky Background Calculation**:
   - Uses **sigma-clipped median** from sky annulus pixels (σ=3.0, maxiters=10)
   - Automatically rejects cosmic rays, hot pixels, and outliers
   - Implemented via `photutils.ApertureStats` with `SigmaClip`
   - More robust than simple median or mean methods

2. **Star Flux Measurement**:
   - Circular aperture photometry with precise background subtraction
   - Sky background: median × aperture_area
   - Corrected flux: raw_flux - sky_background

3. **Physically Correct Poisson Noise Calculation**:
   - Uses **raw photon counts** before background subtraction: √N_raw
   - Physically accurate representation of photon counting statistics
   - Critical for proper error propagation in scientific analysis

4. **Multi-channel RGB Processing**:
   - Individual R, G, B + grayscale photometry
   - Each channel processed with identical robust algorithms
   - Consistent sigma-clipping across all channels

### Algorithm Improvements (v1.1)

**Critical Fixes Applied:**

1. **RGB Photometry Sigma Clipping** (photometry.py:2160-2163)
   - **Before**: Used simple `np.median()` on sky pixels
   - **After**: Uses `ApertureStats` with sigma clipping (σ=3.0)
   - **Impact**: Robust against cosmic rays and hot pixels

2. **Poisson Noise Calculation** (photometry.py:2118, 2174, 2198)
   - **Before**: `√(corrected_flux)` - mathematically incorrect
   - **After**: `√(raw_flux)` - physically correct
   - **Impact**: Proper uncertainty estimation for scientific analysis

3. **Dark Frame Optimization** (calibration.py:213-260)
   - **Before**: Used only hot pixels for scaling factor
   - **After**: Uses broader pixel selection with sigma-clipped median
   - **Impact**: More stable and reliable dark subtraction

4. **Flat Field Calibration** (calibration.py:580-632)
   - **Before**: Master flat created from raw flat frames
   - **After**: Each flat frame bias/dark corrected before combining
   - **Impact**: Follows standard CCD calibration procedures - critical fix

### Processing Modes

**Mode 1: Automatic Tracking**
- User selects star on first image
- System automatically tracks star centroid in subsequent images
- Uses centroid refinement with brightness validation
- Background threading prevents GUI freezing

**Mode 2: Manual Sequential (PASCO Capstone Style)**
- Frame-by-frame manual star selection
- Automatic frame advancement after each click
- Auto-centering on previous star position
- Zoom persistence maintained throughout sequence

### Data Visualization System

The system includes a comprehensive analysis window (1600×1200 pixels) with four main tabs:

**Tab 1: Light Curves Analysis**
- Combined RGB + Grayscale flux trends
- RGB channels comparison with color coding
- Raw vs sky-corrected comparison
- Signal-to-noise ratio trends

**Tab 2: RGB Analysis**
- RGB channel flux comparison
- Color ratios (R/G, B/G, R/B) over time
- Astronomical color indices (B-V, V-R)
- Channel noise comparison

**Tab 3: Quality Metrics**
- Sky background variation over time
- Sky noise (σ) standard deviation
- Poisson noise (√N) analysis
- Total S/N ratios for all channels

**Tab 4: Tracking Analysis**
- Position drift (X,Y coordinates over time)
- Movement per frame analysis
- 2D position scatter plot with time progression
- Tracking quality assessment

## Technical Specifications

### System Requirements
- **Python**: 3.8+ with tkinter support
- **Operating Systems**: Windows, macOS, Linux
- **Memory**: 4GB+ RAM recommended for large image sequences
- **Display**: 1400×900 minimum resolution for optimal GUI experience

### Required Dependencies
```
astropy >= 5.0          # FITS handling, astronomical calculations
photutils >= 1.5.0      # Aperture photometry, star detection
matplotlib >= 3.5.0     # Visualization, GUI integration
numpy >= 1.21           # Array operations, mathematical functions
scipy >= 1.7            # Statistical functions, image processing
rawpy                   # Canon CR3 raw file processing
```

### Performance Characteristics
- **Processing Speed**: ~1-5 seconds per image
- **Memory Usage**: ~50-100MB baseline + image data
- **Threading**: Non-blocking GUI with background processing
- **Display**: Hardware-accelerated matplotlib rendering

### Aperture Parameters
- **Star Aperture**: 1-20 pixels (typically 3-8 for DSLR images)
- **Inner Sky Radius**: 1-20 pixels (typically 12-20)
- **Outer Sky Radius**: 1-20 pixels (typically 20-30)
- **Detection Sensitivity**: 0.5σ to 3.0σ above background
- **Tracking Tolerance**: 12 pixel maximum movement per frame

## Data Output

### CSV Export Format
**Location**: `./results/star_name_photometry_Nimages.csv`

**Basic Columns (All Images)**:
- `filename`, `image_index`, `star_name`, `is_rgb`
- `x_position`, `y_position`, `tracked_position`, `movement_pixels`
- `aperture_area`, `sky_annulus_area`

**RGB Images (Additional Columns)**:
- R, G, B channels: `*_star_flux_raw`, `*_flux_corrected`, `*_sky_background_total`, `*_sky_per_pixel`, `*_sky_std`, `*_poisson_noise`
- Grayscale: `gray_*` measurements with same structure

**FITS Metadata (When Available)**:
- `fits_date-obs`, `fits_exptime`, `fits_filter`, `fits_telescop`
- `fits_instrume`, `fits_observer`, `fits_xpixsz`, `fits_ypixsz`

## Error Handling and Troubleshooting

### Common Issues and Solutions

1. **"No star detected"**
   - Adjust sensitivity slider to lower values (0.5σ - 1.0σ)
   - Use "Adjust Aperture Position" mode for manual placement
   - Check image quality and contrast

2. **"Lost tracking at image N"**
   - Reduce aperture size if star is faint
   - Check for cosmic rays or image artifacts
   - Use manual sequential mode instead

3. **"Image not displaying"**
   - Use "Refresh Display" button
   - Check FITS file format and integrity
   - Restart application if display system fails

4. **"Processing stops early"**
   - Check individual image quality
   - Look for corrupted FITS files in sequence
   - Verify sufficient disk space and memory

### Debugging Features
- Comprehensive logging to status window
- Timestamped debug messages for all operations
- Progress tracking with image-by-image updates
- Error messages with specific failure descriptions
- Processing continuation after recoverable errors

## Scientific Applications

### Research Applications
- **Variable Star Research**: Cepheid variables, Delta Scuti, RR Lyrae studies
- **Exoplanet Studies**: Planetary transit photometry and timing variations
- **Solar System Astronomy**: Asteroid rotation periods, comet brightness monitoring
- **Stellar Photometry**: Multi-color analysis, color-magnitude diagrams
- **Educational Applications**: University lab exercises, amateur astronomy projects

### Professional Research
- Publication-quality data for peer-reviewed journals
- Long-term monitoring programs
- Survey astronomy and data mining
- Ground-based support for space telescope observations

## Quality Assurance

### Scientific Accuracy Features
- **Methodology Compliance**: Exact implementation of Korean astronomy text methods
- **Statistical Robustness**: Median combination and sigma-clipped statistics
- **Multi-method Detection**: Fallback algorithms for robust star detection
- **Brightness Validation**: Ensures measurements are on actual stars
- **Error Propagation**: Proper uncertainty calculation and reporting

### Validation Capabilities
- Signal-to-noise monitoring
- Background stability tracking
- Tracking quality metrics
- Color consistency validation

## Code Architecture

### Design Principles
- **Modular Architecture**: Well-separated GUI and processing logic
- **Thread Safety**: Background processing without GUI blocking
- **Error Resilience**: Graceful handling of individual failures
- **Extensible Design**: Easy addition of new analysis features
- **Professional Standards**: Production-quality error handling and logging

### Key Components
- **GUI Management**: tkinter with matplotlib integration
- **Image Processing**: astropy and photutils integration
- **Data Visualization**: matplotlib with scientific formatting
- **File Management**: Robust I/O with error recovery
- **Threading System**: Background processing with progress updates

## Future Enhancement Possibilities

### Potential Improvements
- **Multi-star Photometry**: Process multiple targets simultaneously
- **PSF Photometry**: Point spread function fitting for crowded fields
- **Automated Calibration**: Integrated calibration frame processing
- **Reference Star Selection**: Automated comparison star identification
- **Light Curve Modeling**: Built-in period analysis and curve fitting

### Analysis Enhancements
- Statistical analysis and trend detection
- Color-magnitude diagram generation
- Variability detection and classification
- Period analysis with Fourier transforms
- Atmospheric extinction correction

## Conclusion

The DSLR Telescope Astronomy Toolbox represents a complete, professional-grade solution for astronomical photometry analysis. It combines rigorous scientific methodology with intuitive user interface design to provide researchers and amateur astronomers with publication-quality results.

**Key Strengths**:
- **Scientific Accuracy**: Implements proper aperture photometry methodology
- **Professional Interface**: Clean, intuitive design without unnecessary complexity
- **Comprehensive Analysis**: Complete workflow from image loading to data visualization
- **Robust Performance**: Handles real-world challenges in astronomical data
- **Extensible Design**: Ready for future enhancements and customizations

The application successfully bridges the gap between complex astronomical software and user-friendly analysis tools, making precise photometry accessible to a broader community while maintaining the rigor required for scientific research.

## Version History

### v1.1 (November 2025) - Critical Algorithm Fixes
**Aperture Photometry Improvements:**
- Fixed RGB photometry to use sigma-clipped background statistics
- Corrected Poisson noise calculation (now uses raw counts)
- Both fixes ensure scientific accuracy and robustness

**Calibration System Improvements:**
- Fixed flat field creation to include proper bias/dark correction
- Improved dark frame optimization algorithm with robust statistics
- Follows standard CCD calibration procedures

**Impact:** These fixes are critical for accurate photometric measurements and should be applied to all existing installations.

### v1.0 (September 2024) - Initial Release
- Complete CR3 to FITS conversion pipeline
- Full image calibration system
- Professional aperture photometry with tracking
- Comprehensive data visualization
- Multi-channel RGB and grayscale support

---
*Documentation Version: Complete Technical Reference v1.1*
*Last Updated: November 2025*
*Total System: 14 Python files, ~5500+ lines of code*