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
    ],
    extras_require={
        "image": [
            "Pillow>=8.0.0",
        ],
        "hdf5": [
            "h5py>=3.0.0",
        ],
        "web": [
            "streamlit>=1.20.0",
        ],
        "dev": [
            "pytest>=6.0",
            "pytest-cov",
            "Pillow>=8.0.0",
        ],
    },
)
