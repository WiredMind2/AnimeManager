"""Characterization tests for the inheritance-to-composition migration.

Each module pins the public behavior of one inheritance hotspot
(``AnimeAPI``, ``APIUtils``) so that decomposing
those classes (ADR 0005, Phase 2) cannot silently change behavior.
"""
