# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- sys.path setup ----------------------------------------------------------
# AnimeManager's repo root IS the package root (the directory is named
# "AnimeManager" and contains __init__.py). Keep both the repo root and
# its parent on sys.path so canonical imports resolve in local/docs builds.

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, os.pardir))
_PARENT_OF_REPO = os.path.abspath(os.path.join(_REPO_ROOT, os.pardir))

for _p in (_PARENT_OF_REPO, _REPO_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = 'AnimeManager'
copyright = '2025, AnimeManager Team'
author = 'AnimeManager Team'
release = '1.0.0'

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.viewcode',
    'sphinx.ext.napoleon',
    'sphinx.ext.intersphinx',
]

templates_path = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

# Avoid duplicate-object warnings in large autodoc builds.
suppress_warnings = [
    'autodoc.import_object',
    'misc.highlighting_failure',
    'app.add_directive',
    'duplicate_object_description',
    'ref.python',
]

# Tolerate optional dependencies that may be absent in CI.
autodoc_mock_imports = [
    'mpv', 'vlc', 'libtorrent',
    'PIL', 'PIL.Image', 'PIL.ImageTk',
    'uvicorn', 'fastapi',
    'tkinter',
]

language = 'en'

# Autodoc settings
autodoc_default_options = {
    'members': True,
    'undoc-members': True,
    'show-inheritance': True,
}

# Napoleon settings for Google/NumPy style docstrings
napoleon_google_docstring = True
napoleon_numpy_docstring = True
napoleon_include_init_with_doc = False
napoleon_include_private_with_doc = False
napoleon_include_special_with_doc = True
napoleon_use_admonition_for_examples = False
napoleon_use_admonition_for_notes = False
napoleon_use_admonition_for_references = False
napoleon_use_ivar = False
napoleon_use_param = True
napoleon_use_rtype = True
napoleon_preprocess_types = False
napoleon_type_aliases = None
napoleon_attr_annotations = True

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'sphinx_rtd_theme'
html_static_path = ['_static']

# Intersphinx mapping
intersphinx_mapping = {
    'python': ('https://docs.python.org/3', None),
}
