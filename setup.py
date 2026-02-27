"""
Nanoorganizer – modular data organizer for nanoparticle synthesis.
"""

import re
from pathlib import Path
from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()


def read_version():
    """Read version from NanoOrganizer/version.py without importing package."""
    version_path = Path(__file__).resolve().parent / "NanoOrganizer" / "version.py"
    text = version_path.read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not match:
        raise RuntimeError("Unable to find __version__ in NanoOrganizer/version.py")
    return match.group(1)


setup(
    name="Nanoorganizer",
    version=read_version(),
    author='Brookhaven National Laboratory_YugangZhang@CFN',
    author_email="yuzhang@bnl.gov",
    description="A clean, modular, extensible framework for nano-synthesis data organizer",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yugangzhang/Nanoorganizer",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Science/Research",
        "Topic :: Scientific/Engineering :: Physics",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.8",
    install_requires=[
        "numpy>=1.20.0",
        "scipy>=1.7.0",
        "matplotlib>=3.3.0",
        "pandas>=1.3.0",
        "plotly>=6.1.1",
        "seaborn>=0.11.0",
    ],
    entry_points={
        'console_scripts': [
            # Secure mode with custom port + password
            'viz=NanoOrganizer.web_app.app_cli:main_secure',
        ],
    },
    extras_require={
        "image": [
            "Pillow>=8.0.0",
        ],
        "hdf5": [
            "h5py>=3.0.0",
        ],
        "web": [
            "streamlit>=1.20.0",
            "pandas>=1.3.0",
            "plotly>=6.1.1",
            "seaborn>=0.11.0",
            "kaleido>=0.2.1",  # For plotly image export (compatible with plotly 6+)
        ],
        "dev": [
            "pytest>=6.0",
            "pytest-cov",
            "Pillow>=8.0.0",
        ],
    },
)
