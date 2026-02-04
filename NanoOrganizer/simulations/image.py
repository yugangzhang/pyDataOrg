#!/usr/bin/env python3
"""Synthetic microscopy image series: particle growth on SEM / TEM."""

import numpy as np
from pathlib import Path
from typing import Tuple, List


def create_fake_image_series(
    output_dir: Path,
    n_images: int = 5,
    time_points: List[float] = None,
    size: Tuple[int, int] = (512, 512),
    pattern: str = "sem",
    particle_growth: bool = True,
) -> List[Path]:
    """
    Generate a series of synthetic microscopy images showing particle growth.

    Parameters
    ----------
    output_dir : Path
        Where to save PNGs.
    n_images : int
        Number of images in the series.
    time_points : list
        Time stamps (used in filenames).
    size : tuple
        (width, height) in pixels.
    pattern : str
        ``"sem"`` or ``"tem"`` – controls particle count / size.
    particle_growth : bool
        If True, particle size and contrast evolve with time.

    Returns
    -------
    list of Path
        Paths to the created PNG files.
    """
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print("Pillow not available – cannot create images.")
        return []

    if time_points is None:
        time_points = [0, 30, 60, 120, 180, 300, 600][:n_images]

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    image_paths: List[Path] = []

    for idx, t in enumerate(time_points[:n_images]):
        img  = Image.new('L', size, 255)
        draw = ImageDraw.Draw(img)

        if particle_growth:
            growth_fraction = 1 - np.exp(-t / 300)

            if pattern == "sem":
                n_particles         = int(20 + 30 * growth_fraction)
                particle_size_range = (5 + 10 * growth_fraction,
                                       10 + 20 * growth_fraction)
            else:   # tem
                n_particles         = int(10 + 20 * growth_fraction)
                particle_size_range = (10 + 15 * growth_fraction,
                                       20 + 30 * growth_fraction)

            contrast   = 50 + 80 * growth_fraction
            gray_value = int(255 - contrast)

            for _ in range(n_particles):
                x = np.random.randint(0, size[0])
                y = np.random.randint(0, size[1])
                r = np.random.uniform(*particle_size_range)
                draw.ellipse(
                    [(x - r, y - r), (x + r, y + r)],
                    fill=gray_value,
                    outline=max(0, gray_value - 30),
                )

        # Add subtle noise
        pixels = img.load()
        for i in range(0, size[0], 2):
            for j in range(0, size[1], 2):
                noise   = int(np.random.normal(0, 10))
                current = pixels[i, j]
                pixels[i, j] = max(0, min(255, current + noise))

        filename = f"{pattern}_t{int(t):04d}s_{idx + 1:02d}.png"
        img_path = output_dir / filename
        img.save(img_path)
        image_paths.append(img_path)
        print(f"  ✓ Created {pattern.upper()} image at t={t}s: {filename}")

    return image_paths
