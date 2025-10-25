#!/usr/bin/env python3
"""
Realistic time-series data simulations for nanoparticle synthesis experiments.

These functions simulate how experimental data evolves during synthesis:
- UV-Vis: Plasmon peak shifts and grows as particles form
- SAXS: Particle size increases over time
- WAXS: Crystallinity develops during reaction
- Microscopy: Particle morphology evolves
"""

import numpy as np
from pathlib import Path
from typing import Tuple, List


def simulate_uvvis_time_series_data(
    wavelength_range: Tuple[float, float] = (200, 800),
    n_wavelengths: int = 300,
    time_points: List[float] = None,
    initial_peak: float = 480,
    final_peak: float = 530,
    growth_rate: float = 1.0,
) -> Tuple[List[float], List[float], List[float]]:
    """
    Simulate realistic UV-Vis time-series data showing nanoparticle growth.
    
    Models a typical synthesis where:
    - Initially: Small/no particles, low absorbance
    - During: Peak grows and shifts red as particles get larger
    - Final: Stable peak at final particle size
    
    Parameters
    ----------
    wavelength_range : tuple
        (min, max) wavelength in nm
    n_wavelengths : int
        Number of wavelength points per spectrum
    time_points : list
        Time points in seconds (default: [0, 30, 60, 120, 180, 300, 600])
    initial_peak : float
        Starting peak position (nm) for small particles
    final_peak : float
        Final peak position (nm) for grown particles
    growth_rate : float
        How fast particles grow (higher = faster saturation)
    
    Returns
    -------
    times : list
        Repeated time values for each wavelength
    wavelengths : list
        Wavelength values (repeated for each time)
    absorbance : list
        Absorbance values
    """
    if time_points is None:
        time_points = [0, 30, 60, 120, 180, 300, 600]  # seconds
    
    wavelengths = np.linspace(wavelength_range[0], wavelength_range[1], n_wavelengths)
    
    times_out = []
    wavelengths_out = []
    absorbance_out = []
    
    for t in time_points:
        # Particle growth follows exponential saturation
        growth_fraction = 1 - np.exp(-growth_rate * t / 300)
        
        # Peak position shifts from initial to final
        peak_center = initial_peak + (final_peak - initial_peak) * growth_fraction
        
        # Peak intensity grows with particle concentration
        peak_height = 1.5 * growth_fraction
        
        # Peak width (smaller particles = broader peak)
        peak_width = 50 + 30 * (1 - growth_fraction)
        
        # Calculate spectrum at this time
        baseline = 0.05 + 0.05 * growth_fraction
        absorbance = baseline + peak_height * np.exp(
            -((wavelengths - peak_center) ** 2) / (2 * peak_width ** 2)
        )
        
        # Add realistic noise (decreases with signal)
        noise_level = 0.02 * (1 + 0.5 / (growth_fraction + 0.1))
        absorbance += np.random.normal(0, noise_level, n_wavelengths)
        absorbance = np.maximum(absorbance, 0)  # Physical constraint: no negative absorbance
        
        # Store in long format (each row is one measurement)
        for wl, abs_val in zip(wavelengths, absorbance):
            times_out.append(t)
            wavelengths_out.append(wl)
            absorbance_out.append(abs_val)
    
    return times_out, wavelengths_out, absorbance_out


def simulate_saxs_time_series_data(
    q_range: Tuple[float, float] = (0.01, 0.5),
    n_points: int = 200,
    time_points: List[float] = None,
    initial_size_nm: float = 2.0,
    final_size_nm: float = 10.0,
    growth_rate: float = 1.0,
) -> Tuple[List[float], List[float], List[float]]:
    """
    Simulate SAXS time-series data showing particle growth.
    
    Models particle size evolution:
    - Initially: Small particles, form factor peaks at high q
    - During: Particles grow, features shift to lower q
    - Final: Large particles, strong small-angle scattering
    
    Parameters
    ----------
    q_range : tuple
        (min, max) q values in 1/Angstrom
    n_points : int
        Number of q points
    time_points : list
        Time points in seconds
    initial_size_nm : float
        Starting particle size
    final_size_nm : float
        Final particle size
    growth_rate : float
        Growth rate parameter
    
    Returns
    -------
    times : list
        Time values
    q_values : list
        q values (1/Angstrom)
    intensities : list
        Scattering intensities
    """
    if time_points is None:
        time_points = [0, 30, 60, 120, 180, 300, 600]
    
    q = np.linspace(q_range[0], q_range[1], n_points)
    
    times_out = []
    q_out = []
    intensity_out = []
    
    for t in time_points:
        # Particle size grows
        growth_fraction = 1 - np.exp(-growth_rate * t / 300)
        radius_nm = initial_size_nm + (final_size_nm - initial_size_nm) * growth_fraction
        radius_A = radius_nm * 10 / 2  # Convert nm to Angstrom (radius)
        
        # Spherical form factor
        qr = q * radius_A
        # Avoid division by zero
        form_factor = np.where(
            qr > 0.01,
            (3 * (np.sin(qr) - qr * np.cos(qr)) / qr**3) ** 2,
            1.0
        )
        
        # Intensity scales with particle volume and concentration
        # Assume concentration increases with growth
        particle_volume = (4/3) * np.pi * radius_A**3
        concentration_factor = 1 + 2 * growth_fraction
        scale_factor = 1000 * particle_volume * concentration_factor
        
        intensity = scale_factor * form_factor
        
        # Add Poisson noise (realistic for X-ray counting)
        noise = np.random.normal(0, 0.05 * np.sqrt(intensity + 1), n_points)
        intensity = intensity + noise
        intensity = np.maximum(intensity, 0.1)  # Floor value
        
        for q_val, I_val in zip(q, intensity):
            times_out.append(t)
            q_out.append(q_val)
            intensity_out.append(I_val)
    
    return times_out, q_out, intensity_out


def simulate_waxs_time_series_data(
    two_theta_range: Tuple[float, float] = (10, 80),
    n_points: int = 500,
    time_points: List[float] = None,
    peaks: List[Tuple[float, float]] = None,
    crystallization_rate: float = 1.0,
) -> Tuple[List[float], List[float], List[float]]:
    """
    Simulate WAXS time-series data showing crystallization.
    
    Models crystallinity development:
    - Initially: Amorphous (broad background)
    - During: Peaks emerge and sharpen
    - Final: Well-defined crystalline peaks
    
    Parameters
    ----------
    two_theta_range : tuple
        (min, max) 2θ values in degrees
    n_points : int
        Number of 2θ points
    time_points : list
        Time points in seconds
    peaks : list of tuples
        [(position, max_height), ...] for crystalline peaks
    crystallization_rate : float
        How fast crystallinity develops
    
    Returns
    -------
    times : list
        Time values
    two_theta : list
        2θ values (degrees)
    intensities : list
        Diffraction intensities
    """
    if time_points is None:
        time_points = [0, 30, 60, 120, 180, 300, 600]
    
    if peaks is None:
        # Default: Cu2O peaks
        peaks = [(30.0, 100), (35.0, 80), (62.0, 60)]
    
    two_theta = np.linspace(two_theta_range[0], two_theta_range[1], n_points)
    
    times_out = []
    two_theta_out = []
    intensity_out = []
    
    for t in time_points:
        # Crystallinity develops
        cryst_fraction = 1 - np.exp(-crystallization_rate * t / 300)
        
        # Start with amorphous background
        amorphous_intensity = 20 * (1 - 0.7 * cryst_fraction)
        intensity = np.ones(n_points) * amorphous_intensity
        
        # Add crystalline peaks that grow and sharpen
        for peak_pos, peak_max_height in peaks:
            # Peak grows in height
            peak_height = peak_max_height * cryst_fraction
            
            # Peak sharpens (width decreases) as crystallinity improves
            peak_width = 3.0 - 1.5 * cryst_fraction  # From 3° to 1.5°
            
            # Gaussian peak
            peak_contribution = peak_height * np.exp(
                -((two_theta - peak_pos) ** 2) / (2 * peak_width ** 2)
            )
            intensity += peak_contribution
        
        # Add noise
        noise = np.random.normal(0, 2 + 0.5 * np.sqrt(intensity), n_points)
        intensity = intensity + noise
        intensity = np.maximum(intensity, 0)
        
        for tt, I_val in zip(two_theta, intensity):
            times_out.append(t)
            two_theta_out.append(tt)
            intensity_out.append(I_val)
    
    return times_out, two_theta_out, intensity_out


def create_fake_image_series(
    output_dir: Path,
    n_images: int = 5,
    time_points: List[float] = None,
    size: Tuple[int, int] = (512, 512),
    pattern: str = "sem",
    particle_growth: bool = True
) -> List[Path]:
    """
    Create a series of fake microscopy images showing particle evolution.
    
    Models morphology changes:
    - Initially: Small particles, low contrast
    - During: Particles grow, aggregate
    - Final: Large, well-defined particles
    
    Parameters
    ----------
    output_dir : Path
        Where to save images
    n_images : int
        Number of images in series
    time_points : list
        Time points (for filenames)
    size : tuple
        Image size (width, height)
    pattern : str
        'sem' or 'tem'
    particle_growth : bool
        Whether to show particle growth
    
    Returns
    -------
    image_paths : list
        Paths to created images
    """
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print("PIL not available, cannot create images")
        return []
    
    if time_points is None:
        time_points = [0, 30, 60, 120, 180, 300, 600][:n_images]
    
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    image_paths = []
    
    for idx, t in enumerate(time_points[:n_images]):
        img = Image.new('L', size, 255)  # Start with white
        draw = ImageDraw.Draw(img)
        
        if particle_growth:
            # Particle parameters evolve with time
            growth_fraction = 1 - np.exp(-t / 300)
            
            # Number and size of particles
            if pattern == "sem":
                # SEM: Many small particles at surface
                n_particles = int(20 + 30 * growth_fraction)
                particle_size_range = (5 + 10 * growth_fraction, 10 + 20 * growth_fraction)
            else:  # TEM
                # TEM: Fewer, well-defined particles
                n_particles = int(10 + 20 * growth_fraction)
                particle_size_range = (10 + 15 * growth_fraction, 20 + 30 * growth_fraction)
            
            # Draw particles
            for _ in range(n_particles):
                x = np.random.randint(0, size[0])
                y = np.random.randint(0, size[1])
                r = np.random.uniform(*particle_size_range)
                
                # Contrast increases with time (better crystallinity)
                contrast = 50 + 80 * growth_fraction
                gray_value = int(255 - contrast)
                
                # Draw circle (particle)
                draw.ellipse(
                    [(x - r, y - r), (x + r, y + r)],
                    fill=gray_value,
                    outline=max(0, gray_value - 30)
                )
        
        # Add texture/noise
        pixels = img.load()
        for i in range(0, size[0], 2):
            for j in range(0, size[1], 2):
                noise = int(np.random.normal(0, 10))
                current = pixels[i, j]
                pixels[i, j] = max(0, min(255, current + noise))
        
        # Save image
        filename = f"{pattern}_t{int(t):04d}s_{idx+1:02d}.png"
        img_path = output_dir / filename
        img.save(img_path)
        image_paths.append(img_path)
        print(f"  ✓ Created {pattern.upper()} image at t={t}s: {filename}")
    
    return image_paths


# Additional utility function for realistic data
def add_baseline_drift(
    values: np.ndarray,
    drift_rate: float = 0.001
) -> np.ndarray:
    """Add realistic baseline drift to data (common in long measurements)."""
    n = len(values)
    drift = np.linspace(0, drift_rate * n, n)
    return values + drift


def add_instrument_noise(
    values: np.ndarray,
    noise_type: str = "gaussian",
    noise_level: float = 0.02
) -> np.ndarray:
    """Add realistic instrument noise."""
    n = len(values)
    if noise_type == "gaussian":
        noise = np.random.normal(0, noise_level, n)
    elif noise_type == "poisson":
        # Poisson noise (counting statistics)
        noise = np.random.normal(0, noise_level * np.sqrt(np.abs(values) + 1), n)
    else:
        noise = np.zeros(n)
    return values + noise


if __name__ == "__main__":
    """Quick test of time-series simulation functions."""
    print("Testing time-series simulation functions...")
    
    # UV-Vis
    print("\n1. UV-Vis time series:")
    times, wls, absorb = simulate_uvvis_time_series_data()
    n_times = len(set(times))
    n_wls_per_time = len(wls) // n_times
    print(f"   Generated {n_times} time points, {n_wls_per_time} wavelengths each")
    print(f"   Total data points: {len(times)}")
    
    # SAXS
    print("\n2. SAXS time series:")
    times, qs, Is = simulate_saxs_time_series_data()
    n_times = len(set(times))
    n_q_per_time = len(qs) // n_times
    print(f"   Generated {n_times} time points, {n_q_per_time} q-points each")
    print(f"   Total data points: {len(times)}")
    
    # WAXS
    print("\n3. WAXS time series:")
    times, tts, Is = simulate_waxs_time_series_data()
    n_times = len(set(times))
    n_tt_per_time = len(tts) // n_times
    print(f"   Generated {n_times} time points, {n_tt_per_time} 2θ-points each")
    print(f"   Total data points: {len(times)}")
    
    # Images
    print("\n4. Image series:")
    img_dir = Path("/tmp/test_images")
    paths = create_fake_image_series(img_dir, n_images=5, pattern="sem")
    print(f"   Generated {len(paths)} images")
    
    print("\n✓ All tests passed!")