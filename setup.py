"""NanoOrganizer — sample-centric organisation, visualisation and analysis of
experimental data.
"""

import re
from pathlib import Path

from setuptools import find_packages, setup

HERE = Path(__file__).resolve().parent


def read_version():
    """Read the version without importing the package."""
    text = (HERE / "NanoOrganizer" / "version.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not match:
        raise RuntimeError("Unable to find __version__ in NanoOrganizer/version.py")
    return match.group(1)


setup(
    name="nanoorganizer",
    version=read_version(),
    author="Yugang Zhang, Center for Functional Nanomaterials, "
           "Brookhaven National Laboratory",
    author_email="yuzhang@bnl.gov",
    description=(
        "Organise experimental metadata, visualise any measurement, "
        "analyse in batch, and compare across samples"
    ),
    long_description=(HERE / "README.md").read_text(encoding="utf-8"),
    long_description_content_type="text/markdown",
    url="https://github.com/yugangzhang/Nanoorganizer",
    license="MIT",
    packages=find_packages(exclude=("tests", "tests.*")),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: MIT License",
        "Topic :: Scientific/Engineering :: Physics",
        "Topic :: Scientific/Engineering :: Chemistry",
        "Topic :: Scientific/Engineering :: Visualization",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    python_requires=">=3.9",
    # Deliberately small, and all of it on PyPI: the package must install and
    # run with nothing private or site-specific.
    install_requires=[
        "numpy>=1.20.0",
        "scipy>=1.7.0",
        "matplotlib>=3.3.0",
        "pandas>=1.3.0",
    ],
    extras_require={
        # Reading micrographs and sizing particles.
        "image": ["Pillow>=8.0.0", "scikit-image>=0.19.0"],
        "hdf5": ["h5py>=3.0.0"],
        "web": [
            "streamlit>=1.36.0",     # st.navigation with sections
            "Pillow>=8.0.0",
            "scikit-image>=0.19.0",
            "plotly>=5.0.0",
            "seaborn>=0.11.0",
        ],
        "dev": [
            "pytest>=6.0",
            "pytest-cov",
            "Pillow>=8.0.0",
            "scikit-image>=0.19.0",
            "streamlit>=1.36.0",
            "nbclient>=0.7",
            "nbformat>=5.0",
        ],
    },
    entry_points={
        "console_scripts": [
            # Launch the web app with a password and an allowed-roots fence.
            "viz=NanoOrganizer.web_app.app_cli:main_secure",
            # Add or update an account in the multi-user store.
            "viz-adduser=NanoOrganizer.web_app.app_cli:main_adduser",
        ],
    },
    include_package_data=True,
    zip_safe=False,
)
