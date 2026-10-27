"""Tests for light and dark mode theme switching in app.py."""

from __future__ import annotations

from app import CSS_ENTERPRISE, CSS_LIGHT


def test_theme_css_definitions():
    """Verify both dark (CSS_ENTERPRISE) and light (CSS_LIGHT) CSS blocks exist and have valid structure."""
    assert CSS_ENTERPRISE is not None
    assert len(CSS_ENTERPRISE) > 500
    assert "background:#070B14" in CSS_ENTERPRISE or ".stApp{background:#070B14" in CSS_ENTERPRISE

    assert CSS_LIGHT is not None
    assert len(CSS_LIGHT) > 500
    assert "background:#F8FAFC" in CSS_LIGHT or ".stApp{background:#F8FAFC" in CSS_LIGHT


def test_light_mode_color_contrast():
    """Verify light theme specifies white surfaces and dark text."""
    assert "#FFFFFF" in CSS_LIGHT
    assert "#0F172A" in CSS_LIGHT  # Slate-900 high contrast text
    assert "#E2E8F0" in CSS_LIGHT  # Crisp border
    assert "#4F46E5" in CSS_LIGHT  # Primary accent
