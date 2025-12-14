#!/usr/bin/env python3
"""
Setup script for AnimeManager development package.
This enables 'pip install -e .' for development mode.
"""

import os

from setuptools import find_packages, setup


# Read requirements
def read_requirements():
    requirements_path = os.path.join(os.path.dirname(__file__), "requirements.txt")
    with open(requirements_path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip() and not line.startswith("#")]


# Read README for long description
def read_readme():
    readme_path = os.path.join(os.path.dirname(__file__), "README.md")
    try:
        with open(readme_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "AnimeManager - A comprehensive anime management application"


setup(
    name="AnimeManager",
    version="1.0.0",
    description="A comprehensive anime management application with torrent integration and media playback",
    long_description=read_readme(),
    long_description_content_type="text/markdown",
    author="WiredMind2",
    python_requires=">=3.8",
    # Package discovery
    packages=find_packages(exclude=["tests*", "build*", "dist*"]),
    # Include package data
    include_package_data=True,
    package_data={
        "AnimeManager": [
            "icons/**/*",
            "lib/*",
            "tutorial.html",
            "tutorial.css",
            "settings.json",
        ],
    },
    # Dependencies
    install_requires=read_requirements(),
    # Entry points
    entry_points={
        "console_scripts": [
            "animemanager=AnimeManager.__main__:main",
        ],
    },
    # Classification
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Multimedia :: Video",
        "Topic :: Internet :: File Transfer Protocol (FTP)",
    ],
    # Additional metadata
    keywords="anime manga torrent media player download manager",
    project_urls={
        "Bug Reports": "https://github.com/WiredMind2/AnimeManager/issues",
        "Source": "https://github.com/WiredMind2/AnimeManager",
    },
)
