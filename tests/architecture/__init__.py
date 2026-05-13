"""Architecture tests.

These tests encode the layer boundaries and inheritance rules
documented in ADRs 0003, 0005 and 0006. They scan the source tree
statically -- they do not execute application code -- so they are
fast enough to run as part of the default suite.

Run only this suite::

    python -m pytest -m architecture
"""
