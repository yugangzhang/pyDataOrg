"""
Nanoorganizer – modular data organizer for nanoparticle synthesis.
"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="Nanoorganizer",
    version="1.0.0",
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
            # MAIN APP - All tools in one (port 8501) - RECOMMENDED!
            'nanoorganizer=NanoOrganizer.web_app.app_cli:main',
            # Restricted user mode - folder browser locked to CWD
            'nanoorganizer_user=NanoOrganizer.web_app.app_cli:main_user',

            # Legacy individual tools (still available)
            'nanoorganizer-hub=NanoOrganizer.web.hub_cli:main',
            'nanoorganizer-viz=NanoOrganizer.web.cli:main',
            'nanoorganizer-csv=NanoOrganizer.web.csv_plotter_cli:main',
            'nanoorganizer-csv-enhanced=NanoOrganizer.web.csv_enhanced_cli:main',
            'nanoorganizer-manage=NanoOrganizer.web.data_manager_cli:main',
            'nanoorganizer-3d=NanoOrganizer.web.plotter_3d_cli:main',
            'nanoorganizer-img=NanoOrganizer.web.image_viewer_cli:main',
            'nanoorganizer-multi=NanoOrganizer.web.multi_axes_cli:main',
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
