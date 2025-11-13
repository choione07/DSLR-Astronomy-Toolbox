#!/usr/bin/env python3
"""
FITS Image Calibration Tool
Robust Python program for calibrating FITS light images using bias, dark, and flat frames
Based on DeepSkyStacker methodology for 3D RGB FITS files

Author: Generated for astronomical image processing
Usage: python fits_calibration.py --input-folder <path> --output-folder <path>
"""

import os
import sys
import argparse
import logging
import numpy as np
from pathlib import Path
from typing import List, Optional, Tuple, Union
import warnings

try:
    from astropy.io import fits
    from astropy import stats
except ImportError:
    print("Error: astropy is required. Install with: pip install astropy")
    sys.exit(1)

try:
    from scipy import ndimage
except ImportError:
    print("Error: scipy is required. Install with: pip install scipy")
    sys.exit(1)

# sigma_clipped_stats is from astropy, not scipy
from astropy.stats import sigma_clipped_stats

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('fits_calibration.log'),
        logging.StreamHandler()
    ]
)

class FITSCalibrationError(Exception):
    """Custom exception for FITS calibration errors"""
    pass

class FITSImage:
    """Class to handle both 2D grayscale and 3D RGB FITS images"""
    
    def __init__(self, data: np.ndarray, header: fits.Header = None):
        if len(data.shape) == 2:
            # Grayscale image - convert to shape (1, height, width) for unified processing
            self.data = data.astype(np.float64)[np.newaxis, ...]
            self.is_rgb = False
            self.num_channels = 1
        elif len(data.shape) == 3 and data.shape[0] == 3:
            # RGB image with shape (3, height, width)
            self.data = data.astype(np.float64)
            self.is_rgb = True
            self.num_channels = 3
        else:
            raise FITSCalibrationError(f"Expected 2D grayscale or 3D RGB data, got shape {data.shape}")
        
        self.header = header or fits.Header()
        self.shape = self.data.shape
        self.original_shape = data.shape
        
    @classmethod
    def from_file(cls, filepath: Path) -> 'FITSImage':
        """Load FITS file (supports both grayscale and RGB)"""
        try:
            with fits.open(filepath) as hdul:
                data = hdul[0].data
                header = hdul[0].header
                
                if data is None:
                    raise FITSCalibrationError(f"No data found in {filepath}")
                
                return cls(data, header)
                
        except Exception as e:
            raise FITSCalibrationError(f"Failed to load {filepath}: {str(e)}")
    
    def save_to_file(self, filepath: Path, overwrite: bool = True):
        """Save FITS image to file"""
        try:
            # Convert back to original format for saving
            if self.is_rgb:
                output_data = self.data.astype(np.float32)
            else:
                # Convert back to 2D for grayscale
                output_data = self.data[0].astype(np.float32)
            
            # Create HDU
            hdu = fits.PrimaryHDU(data=output_data, header=self.header)
            
            # Save file
            hdu.writeto(filepath, overwrite=overwrite)
            logging.info(f"Saved calibrated image: {filepath}")
            
        except Exception as e:
            raise FITSCalibrationError(f"Failed to save {filepath}: {str(e)}")
    
    def get_channel_statistics(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Get mean, median, and standard deviation for each channel"""
        means = np.array([np.mean(self.data[i]) for i in range(self.num_channels)])
        medians = np.array([np.median(self.data[i]) for i in range(self.num_channels)])
        stds = np.array([np.std(self.data[i]) for i in range(self.num_channels)])
        return means, medians, stds

class MasterFrameCreator:
    """Creates master calibration frames from multiple input frames"""
    
    def __init__(self, method: str = 'median', sigma_clip: float = 3.0):
        self.method = method.lower()
        self.sigma_clip = sigma_clip
        
        if self.method not in ['mean', 'median']:
            raise FITSCalibrationError(f"Invalid combination method: {method}")
    
    def create_master_frame(self, frame_paths: List[Path]) -> FITSImage:
        """Create master frame from multiple input frames"""
        if not frame_paths:
            raise FITSCalibrationError("No frames provided for master frame creation")
        
        logging.info(f"Creating master frame from {len(frame_paths)} frames using {self.method}")
        
        # Load all frames
        frames = []
        reference_shape = None
        
        for path in frame_paths:
            try:
                frame = FITSImage.from_file(path)
                if reference_shape is None:
                    reference_shape = frame.shape
                elif frame.shape != reference_shape:
                    raise FITSCalibrationError(f"Frame size mismatch: {path} has shape {frame.shape}, expected {reference_shape}")
                
                frames.append(frame.data)
                
            except Exception as e:
                logging.warning(f"Skipping frame {path}: {str(e)}")
                continue
        
        if not frames:
            raise FITSCalibrationError("No valid frames found")
        
        # Stack frames
        frame_stack = np.array(frames)  # Shape: (num_frames, 3, height, width)
        
        # Apply sigma clipping and combination
        if self.method == 'median':
            master_data = np.median(frame_stack, axis=0)
        else:  # mean
            if self.sigma_clip > 0:
                # Apply sigma clipping
                master_data = np.zeros_like(frame_stack[0])
                num_channels = reference_shape[0]  # Dynamic channel count
                for c in range(num_channels):  # For each channel
                    for y in range(reference_shape[1]):
                        for x in range(reference_shape[2]):
                            pixel_values = frame_stack[:, c, y, x]
                            clipped_mean, _, _ = sigma_clipped_stats(pixel_values, sigma=self.sigma_clip)
                            master_data[c, y, x] = clipped_mean
            else:
                master_data = np.mean(frame_stack, axis=0)
        
        # Create header with processing info
        header = fits.Header()
        header['HISTORY'] = f'Master frame created from {len(frames)} frames'
        header['HISTORY'] = f'Combination method: {self.method}'
        header['NFRAMES'] = len(frames)
        
        return FITSImage(master_data, header)

class BiasFrameProcessor:
    """Handles bias frame subtraction"""
    
    def __init__(self, master_bias: FITSImage):
        self.master_bias = master_bias
        logging.info(f"Bias processor initialized with master bias shape: {master_bias.shape}")
    
    def subtract_bias(self, image: FITSImage) -> FITSImage:
        """Subtract master bias from image"""
        if image.shape != self.master_bias.shape:
            raise FITSCalibrationError(f"Image shape {image.shape} doesn't match bias shape {self.master_bias.shape}")
        
        # Subtract bias from each channel
        calibrated_data = image.data - self.master_bias.data
        
        # Ensure non-negative values
        calibrated_data = np.maximum(calibrated_data, 0)
        
        # Update header
        new_header = image.header.copy()
        new_header['HISTORY'] = 'Bias subtraction applied'
        
        return FITSImage(calibrated_data, new_header)

class DarkFrameProcessor:
    """Handles dark frame subtraction with optimization"""
    
    def __init__(self, master_dark: FITSImage, optimize_factor: bool = True):
        self.master_dark = master_dark
        self.optimize_factor = optimize_factor
        self.dark_factors = np.ones(master_dark.num_channels)  # Scaling factors for all channels
        logging.info(f"Dark processor initialized with master dark shape: {master_dark.shape}")
    
    def _compute_optimal_dark_factor(self, image: FITSImage) -> np.ndarray:
        """Compute optimal dark scaling factor using improved methodology

        Uses a more robust approach that considers the entire dark frame statistics
        rather than just hot pixels, which can be unreliable.
        """
        factors = np.ones(image.num_channels)

        for c in range(image.num_channels):
            img_channel = image.data[c]
            dark_channel = self.master_dark.data[c]

            # Improved approach: Use median of entire frame for more stable estimate
            # First, get the median values of both frames
            img_median = np.median(img_channel)
            dark_median = np.median(dark_channel)

            # Compute per-pixel ratios for pixels above dark median
            # (to avoid division by very small values)
            mask = dark_channel > dark_median * 0.5

            if np.any(mask) and dark_median > 0:
                # Get corresponding pixels in both frames
                img_pixels = img_channel[mask]
                dark_pixels = dark_channel[mask]

                # Compute ratios only for valid pixels
                valid_mask = (dark_pixels > dark_median * 0.1) & (img_pixels > 0)
                if np.any(valid_mask):
                    ratios = img_pixels[valid_mask] / dark_pixels[valid_mask]

                    # Use sigma-clipped median for robust estimate (median is more stable than mean)
                    _, clipped_median, _ = sigma_clipped_stats(ratios, sigma=2.5, maxiters=5)
                    factors[c] = clipped_median if not np.isnan(clipped_median) else 1.0
                else:
                    # Fallback: use overall median ratio
                    if dark_median > 0:
                        factors[c] = img_median / dark_median
            else:
                # If dark frame is too dim, use default factor
                factors[c] = 1.0

            # Clamp factors to reasonable range to prevent over/under correction
            factors[c] = np.clip(factors[c], 0.1, 5.0)

            logging.debug(f"Channel {c}: computed dark factor = {factors[c]:.3f}")

        return factors
    
    def subtract_dark(self, image: FITSImage) -> FITSImage:
        """Subtract dark frame with optional optimization"""
        if image.shape != self.master_dark.shape:
            raise FITSCalibrationError(f"Image shape {image.shape} doesn't match dark shape {self.master_dark.shape}")
        
        # Compute optimization factors if enabled
        if self.optimize_factor:
            self.dark_factors = self._compute_optimal_dark_factor(image)
            logging.info(f"Dark optimization factors (RGB): {self.dark_factors}")
        
        # Apply dark subtraction with factors
        calibrated_data = image.data.copy()
        for c in range(image.num_channels):
            calibrated_data[c] -= self.master_dark.data[c] * self.dark_factors[c]
        
        # Ensure non-negative values
        calibrated_data = np.maximum(calibrated_data, 0)
        
        # Update header
        new_header = image.header.copy()
        if image.is_rgb:
            new_header['HISTORY'] = f'Dark subtraction applied with factors: R={self.dark_factors[0]:.3f} G={self.dark_factors[1]:.3f} B={self.dark_factors[2]:.3f}'
        else:
            new_header['HISTORY'] = f'Dark subtraction applied with factor: {self.dark_factors[0]:.3f}'
        
        return FITSImage(calibrated_data, new_header)

class FlatFrameProcessor:
    """Handles flat field correction with proper color balance - DSS style"""
    
    def __init__(self, master_flat: FITSImage):
        self.master_flat = master_flat
        self.balanced_flat = self._create_color_balanced_flat()
        self.normalization_factor = self._compute_normalization()
        logging.info(f"Flat processor initialized with shape: {master_flat.shape}")
        logging.info(f"Flat normalization factor: {self.normalization_factor}")
    
    def _create_color_balanced_flat(self) -> FITSImage:
        """Create color-balanced flat field by normalizing channels"""
        raw_means = np.zeros(self.master_flat.num_channels)
        
        # Compute mean for each channel
        for c in range(self.master_flat.num_channels):
            raw_means[c] = np.mean(self.master_flat.data[c])
        
        # Use the minimum mean as target to avoid amplifying noise
        target_mean = np.min(raw_means)
        
        # Create balanced flat by scaling each channel to the target mean
        balanced_data = np.zeros_like(self.master_flat.data)
        for c in range(self.master_flat.num_channels):
            scale_factor = target_mean / raw_means[c]
            balanced_data[c] = self.master_flat.data[c] * scale_factor
        
        if self.master_flat.is_rgb:
            logging.info(f"Original flat means (RGB): {raw_means}")
        else:
            logging.info(f"Original flat mean (grayscale): {raw_means[0]}")
        logging.info(f"Target mean for balance: {target_mean:.1f}")
        logging.info("Created balanced flat field")
        
        return FITSImage(balanced_data, self.master_flat.header)
    
    def _compute_normalization(self) -> float:
        """Compute single normalization factor for balanced flat"""
        # Use the first channel as reference (green for RGB, grayscale for mono)
        ref_channel = 1 if self.balanced_flat.is_rgb else 0
        return np.mean(self.balanced_flat.data[ref_channel])
    
    def apply_flat(self, image: FITSImage) -> FITSImage:
        """Apply flat field correction using balanced flat"""
        if image.shape != self.master_flat.shape:
            raise FITSCalibrationError(f"Image shape {image.shape} doesn't match flat shape {self.master_flat.shape}")
        
        calibrated_data = image.data.copy()
        
        # Apply flat correction using the balanced flat field
        for c in range(image.num_channels):
            flat_channel = self.balanced_flat.data[c]
            
            # Avoid division by very small values
            safe_flat = np.maximum(flat_channel, 1e-6)
            
            # Apply flat field correction with single normalization factor
            calibrated_data[c] = (calibrated_data[c] * self.normalization_factor) / safe_flat
        
        # Update header
        new_header = image.header.copy()
        correction_type = "Color-balanced" if image.is_rgb else "Flat field"
        new_header['HISTORY'] = f'{correction_type} flat field correction applied with normalization: {self.normalization_factor:.1f}'
        
        return FITSImage(calibrated_data, new_header)

class DarkFlatFrameProcessor:
    """Handles dark flat frame subtraction (optional)"""
    
    def __init__(self, master_darkflat: FITSImage):
        self.master_darkflat = master_darkflat
        logging.info(f"Dark flat processor initialized with master dark flat shape: {master_darkflat.shape}")
    
    def subtract_darkflat(self, image: FITSImage) -> FITSImage:
        """Subtract master dark flat from image"""
        if image.shape != self.master_darkflat.shape:
            raise FITSCalibrationError(f"Image shape {image.shape} doesn't match dark flat shape {self.master_darkflat.shape}")
        
        # Subtract dark flat from each channel
        calibrated_data = image.data - self.master_darkflat.data
        
        # Ensure non-negative values
        calibrated_data = np.maximum(calibrated_data, 0)
        
        # Update header
        new_header = image.header.copy()
        new_header['HISTORY'] = 'Dark flat subtraction applied'
        
        return FITSImage(calibrated_data, new_header)

class FITSCalibrator:
    """Main calibration class that orchestrates the entire process"""
    
    def __init__(self, 
                 bias_processor: Optional[BiasFrameProcessor] = None,
                 dark_processor: Optional[DarkFrameProcessor] = None, 
                 flat_processor: Optional[FlatFrameProcessor] = None,
                 darkflat_processor: Optional[DarkFlatFrameProcessor] = None):
        self.bias_processor = bias_processor
        self.dark_processor = dark_processor
        self.flat_processor = flat_processor
        self.darkflat_processor = darkflat_processor
        
        logging.info("FITS Calibrator initialized with processors:")
        logging.info(f"  - Bias: {'Yes' if bias_processor else 'No'}")
        logging.info(f"  - Dark: {'Yes' if dark_processor else 'No'}")
        logging.info(f"  - Flat: {'Yes' if flat_processor else 'No'}")
        logging.info(f"  - Dark Flat: {'Yes' if darkflat_processor else 'No'}")
    
    def calibrate_image(self, image: FITSImage) -> FITSImage:
        """Apply full calibration pipeline to an image"""
        calibrated = image
        
        # Apply calibrations in the correct order (following DSS methodology)
        # Order: Bias -> Dark -> Flat
        
        if self.bias_processor:
            logging.debug("Applying bias subtraction")
            calibrated = self.bias_processor.subtract_bias(calibrated)
        
        if self.dark_processor:
            logging.debug("Applying dark subtraction")
            calibrated = self.dark_processor.subtract_dark(calibrated)
        
        if self.flat_processor:
            logging.debug("Applying flat field correction")
            calibrated = self.flat_processor.apply_flat(calibrated)
        
        # Add final calibration info to header
        calibrated.header['HISTORY'] = 'Full calibration pipeline completed'
        calibrated.header['CALIBRAT'] = True
        
        return calibrated

def find_fits_files(directory: Path, pattern: str = "*.fits") -> List[Path]:
    """Find all FITS files in a directory"""
    fits_files = list(directory.glob(pattern))
    
    # Also check for common FITS extensions
    for ext in ["*.fit", "*.fts", "*.FIT", "*.FITS", "*.FTS"]:
        fits_files.extend(directory.glob(ext))
    
    # Remove duplicates and sort
    fits_files = sorted(list(set(fits_files)))
    
    logging.info(f"Found {len(fits_files)} FITS files in {directory}")
    return fits_files

def create_output_directory(output_path: Path) -> Path:
    """Create output directory structure"""
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Create subdirectories
    calibrated_dir = output_path / "calibrated"
    masters_dir = output_path / "masters"
    
    calibrated_dir.mkdir(exist_ok=True)
    masters_dir.mkdir(exist_ok=True)
    
    return output_path

def check_existing_master_frames(masters_dir: Path) -> dict:
    """Check for existing master frames and return paths if they exist"""
    masters = {
        'bias': masters_dir / "master_bias.fits",
        'dark': masters_dir / "master_dark.fits", 
        'flat': masters_dir / "master_flat.fits",
        'darkflat': masters_dir / "master_darkflat.fits"
    }
    
    existing_masters = {}
    for frame_type, path in masters.items():
        if path.exists():
            logging.info(f"Found existing master {frame_type}: {path}")
            existing_masters[frame_type] = path
        else:
            logging.info(f"No existing master {frame_type} found")
    
    return existing_masters

def auto_detect_output_folder(input_folder: Path) -> Path:
    """Automatically determine output folder based on input structure"""
    # Check if input folder contains frame type subfolders
    expected_folders = ['light', 'bias', 'dark', 'flat']
    has_subfolders = any((input_folder / folder).exists() for folder in expected_folders)
    
    if has_subfolders:
        # Use input folder as base (save directly in the input folder)
        output_folder = input_folder
    else:
        # Use parent directory of input folder
        output_folder = input_folder.parent / f"{input_folder.name}_calibrated"
    
    logging.info(f"Auto-selected output folder: {output_folder}")
    return output_folder

def main():
    parser = argparse.ArgumentParser(
        description="Calibrate FITS light images using bias, dark, and flat frames"
    )
    parser.add_argument("--input-folder", "-i", type=Path, required=True,
                       help="Input folder containing FITS files and subfolders")
    parser.add_argument("--output-folder", "-o", type=Path, required=False,
                       help="Output folder for calibrated images (auto-detected if not specified)")
    parser.add_argument("--bias-folder", type=Path,
                       help="Folder containing bias frames (default: input_folder/bias)")
    parser.add_argument("--dark-folder", type=Path,
                       help="Folder containing dark frames (default: input_folder/dark)")  
    parser.add_argument("--flat-folder", type=Path,
                       help="Folder containing flat frames (default: input_folder/flat)")
    parser.add_argument("--light-folder", type=Path,
                       help="Folder containing light frames (default: input_folder/light)")
    parser.add_argument("--master-method", choices=['mean', 'median'], default='median',
                       help="Method for combining master frames")
    parser.add_argument("--optimize-dark", action='store_true',
                       help="Enable dark frame optimization")
    parser.add_argument("--verbose", "-v", action='store_true',
                       help="Enable verbose logging")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Set default paths
    input_folder = args.input_folder
    bias_folder = args.bias_folder or input_folder / "bias"
    dark_folder = args.dark_folder or input_folder / "dark" 
    flat_folder = args.flat_folder or input_folder / "flat"
    darkflat_folder = input_folder / "darkflat"  # Optional darkflat folder
    light_folder = args.light_folder or input_folder / "light"
    
    # Validate input paths
    if not input_folder.exists():
        logging.error(f"Input folder does not exist: {input_folder}")
        return 1
    
    # Auto-detect output folder if not provided, or use provided one
    if args.output_folder:
        output_folder = create_output_directory(args.output_folder)
    else:
        output_folder = create_output_directory(auto_detect_output_folder(input_folder))
    
    try:
        # Check for existing master frames first
        masters_dir = output_folder / "masters"
        existing_masters = check_existing_master_frames(masters_dir)
        
        # Initialize master frame creator
        master_creator = MasterFrameCreator(method=args.master_method)
        
        # Initialize processors
        bias_processor = None
        dark_processor = None
        flat_processor = None
        darkflat_processor = None
        
        # Handle bias frames (check existing or create new)
        if 'bias' in existing_masters:
            logging.info("Using existing master bias frame")
            master_bias = FITSImage.from_file(existing_masters['bias'])
            bias_processor = BiasFrameProcessor(master_bias)
        elif bias_folder.exists():
            bias_files = find_fits_files(bias_folder)
            if bias_files:
                logging.info("Creating new master bias frame")
                master_bias = master_creator.create_master_frame(bias_files)
                master_bias.save_to_file(output_folder / "masters" / "master_bias.fits")
                bias_processor = BiasFrameProcessor(master_bias)
            else:
                logging.warning("No bias frames found")
        else:
            logging.info("No bias folder found - skipping bias correction")
        
        # Handle dark frames (check existing or create new)
        if 'dark' in existing_masters:
            logging.info("Using existing master dark frame")
            master_dark = FITSImage.from_file(existing_masters['dark'])
            dark_processor = DarkFrameProcessor(master_dark, optimize_factor=args.optimize_dark)
        elif dark_folder.exists():
            dark_files = find_fits_files(dark_folder)
            if dark_files:
                logging.info("Creating new master dark frame")
                master_dark = master_creator.create_master_frame(dark_files)
                master_dark.save_to_file(output_folder / "masters" / "master_dark.fits")
                dark_processor = DarkFrameProcessor(master_dark, optimize_factor=args.optimize_dark)
            else:
                logging.warning("No dark frames found")
        else:
            logging.info("No dark folder found - skipping dark correction")
        
        # Handle flat frames (check existing or create new)
        if 'flat' in existing_masters:
            logging.info("Using existing master flat frame")
            master_flat = FITSImage.from_file(existing_masters['flat'])
            flat_processor = FlatFrameProcessor(master_flat)
        elif flat_folder.exists():
            flat_files = find_fits_files(flat_folder)
            if flat_files:
                logging.info("Creating new master flat frame with proper calibration")

                # IMPORTANT: Flat frames must be bias and dark corrected before combining
                # This follows standard CCD calibration procedures
                if bias_processor or dark_processor:
                    logging.info("Calibrating individual flat frames before combining")
                    calibrated_flat_frames = []

                    for flat_file in flat_files:
                        flat_frame = FITSImage.from_file(flat_file)

                        # Apply bias correction if available
                        if bias_processor:
                            flat_frame = bias_processor.subtract_bias(flat_frame)

                        # Apply dark correction if available (no optimization for flats)
                        if dark_processor:
                            # Create a temporary dark processor without optimization for flats
                            flat_dark_processor = DarkFrameProcessor(dark_processor.master_dark, optimize_factor=False)
                            flat_frame = flat_dark_processor.subtract_dark(flat_frame)

                        calibrated_flat_frames.append(flat_frame.data)

                    # Combine calibrated flat frames
                    frame_stack = np.array(calibrated_flat_frames)
                    if master_creator.method == 'median':
                        master_flat_data = np.median(frame_stack, axis=0)
                    else:  # mean
                        master_flat_data = np.mean(frame_stack, axis=0)

                    master_flat = FITSImage(master_flat_data)
                    master_flat.header['HISTORY'] = f'Master flat created from {len(flat_files)} bias/dark corrected frames'
                    logging.info("Master flat created from calibrated flat frames")
                else:
                    # No bias/dark available - create master flat from raw frames
                    logging.warning("No bias/dark processors available - creating master flat from uncalibrated frames")
                    logging.warning("For best results, provide bias and dark frames")
                    master_flat = master_creator.create_master_frame(flat_files)

                master_flat.save_to_file(output_folder / "masters" / "master_flat.fits")
                flat_processor = FlatFrameProcessor(master_flat)
            else:
                logging.warning("No flat frames found")
        else:
            logging.info("No flat folder found - skipping flat correction")
        
        # Handle dark flat frames (optional - check existing or create new)
        if 'darkflat' in existing_masters:
            logging.info("Using existing master dark flat frame")
            master_darkflat = FITSImage.from_file(existing_masters['darkflat'])
            darkflat_processor = DarkFlatFrameProcessor(master_darkflat)
        elif darkflat_folder.exists():
            darkflat_files = find_fits_files(darkflat_folder)
            if darkflat_files:
                logging.info("Creating new master dark flat frame")
                master_darkflat = master_creator.create_master_frame(darkflat_files)
                master_darkflat.save_to_file(output_folder / "masters" / "master_darkflat.fits")
                darkflat_processor = DarkFlatFrameProcessor(master_darkflat)
            else:
                logging.warning("Dark flat folder exists but no dark flat frames found")
        else:
            logging.info("No dark flat folder found - skipping dark flat correction (optional)")
        
        # Initialize calibrator with all processors (including optional darkflat)
        calibrator = FITSCalibrator(bias_processor, dark_processor, flat_processor, darkflat_processor)
        
        # Process light frames
        if not light_folder.exists():
            logging.error(f"Light frames folder does not exist: {light_folder}")
            return 1
        
        light_files = find_fits_files(light_folder)
        if not light_files:
            logging.error("No light frames found")
            return 1
        
        logging.info(f"Processing {len(light_files)} light frames")
        
        # Process each light frame
        for i, light_file in enumerate(light_files):
            try:
                logging.info(f"Processing {i+1}/{len(light_files)}: {light_file.name}")
                
                # Load light frame
                light_image = FITSImage.from_file(light_file)
                
                # Apply calibration
                calibrated_image = calibrator.calibrate_image(light_image)
                
                # Save calibrated image
                output_filename = light_file.stem + "_calibrated.fits"
                output_path = output_folder / "calibrated" / output_filename
                calibrated_image.save_to_file(output_path)
                
            except Exception as e:
                logging.error(f"Failed to process {light_file}: {str(e)}")
                continue
        
        logging.info("Calibration completed successfully")
        return 0
        
    except Exception as e:
        logging.error(f"Calibration failed: {str(e)}")
        return 1

if __name__ == "__main__":
    sys.exit(main())