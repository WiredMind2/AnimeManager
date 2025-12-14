"""
GUI Testing Framework for Tkinter Components

This module provides comprehensive GUI testing capabilities including:
- Automated screenshot comparison
- Accessibility testing
- Component interaction testing
- Visual regression testing
- Performance testing for GUI responsiveness
"""

import os
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch
import pytest
import tkinter as tk
from PIL import Image, ImageChops, ImageDraw
import io
import base64

try:
    from ..base_test_framework import BaseGUITest
except ImportError:
    from tests.base_test_framework import BaseGUITest


class GUITestFramework:
    """Framework for GUI testing with screenshot comparison and accessibility checks."""

    def __init__(self, root=None):
        self.root = root or tk.Tk()
        self.screenshot_dir = os.path.join(os.path.dirname(__file__), 'screenshots')
        self.baseline_dir = os.path.join(self.screenshot_dir, 'baseline')
        self.current_dir = os.path.join(self.screenshot_dir, 'current')
        self.diff_dir = os.path.join(self.screenshot_dir, 'diff')

        # Create directories
        for directory in [self.screenshot_dir, self.baseline_dir, self.current_dir, self.diff_dir]:
            os.makedirs(directory, exist_ok=True)

    def take_screenshot(self, widget=None, filename=None):
        """Take a screenshot of a widget or the entire root window."""
        target = widget or self.root

        # Get widget geometry
        x = target.winfo_rootx()
        y = target.winfo_rooty()
        width = target.winfo_width()
        height = target.winfo_height()

        if width <= 1 or height <= 1:
            # Widget not fully initialized
            return None

        # Use PIL to capture screenshot
        try:
            from PIL import ImageGrab
            screenshot = ImageGrab.grab(bbox=(x, y, x + width, y + height))
            return screenshot
        except ImportError:
            # Fallback for systems without ImageGrab
            return self._create_placeholder_image(width, height)

    def _create_placeholder_image(self, width, height):
        """Create a placeholder image for testing."""
        img = Image.new('RGB', (width, height), color='white')
        draw = ImageDraw.Draw(img)
        draw.text((10, 10), f"Placeholder {width}x{height}", fill='black')
        return img

    def save_screenshot(self, screenshot, filename, directory=None):
        """Save screenshot to specified directory."""
        if screenshot is None:
            return None

        directory = directory or self.current_dir
        filepath = os.path.join(directory, filename)
        screenshot.save(filepath)
        return filepath

    def compare_screenshots(self, baseline_path, current_path, diff_path=None, threshold=0.01):
        """Compare two screenshots and return similarity score."""
        if not os.path.exists(baseline_path) or not os.path.exists(current_path):
            return 0.0

        baseline = Image.open(baseline_path)
        current = Image.open(current_path)

        # Resize images to same size if needed
        if baseline.size != current.size:
            current = current.resize(baseline.size)

        # Calculate difference
        diff = ImageChops.difference(baseline, current)

        # Calculate RMS difference
        diff_data = list(diff.getdata())
        rms = sum((r**2 + g**2 + b**2) for r, g, b in diff_data) / len(diff_data)
        rms = (rms / 3) ** 0.5  # Average across RGB channels

        # Normalize to 0-1 scale
        max_rms = 255
        similarity = 1 - (rms / max_rms)

        # Save diff image if path provided
        if diff_path and similarity < (1 - threshold):
            diff.save(diff_path)

        return similarity

    def assert_screenshot_match(self, widget, test_name, threshold=0.99):
        """Assert that current screenshot matches baseline."""
        # Take current screenshot
        screenshot = self.take_screenshot(widget)
        if screenshot is None:
            pytest.skip("Widget not visible or initialized")

        # Save current screenshot
        current_path = self.save_screenshot(screenshot, f"{test_name}_current.png")

        # Check for baseline
        baseline_path = os.path.join(self.baseline_dir, f"{test_name}_baseline.png")

        if not os.path.exists(baseline_path):
            # Create baseline if it doesn't exist
            self.save_screenshot(screenshot, f"{test_name}_baseline.png", self.baseline_dir)
            pytest.skip(f"Created baseline screenshot for {test_name}")

        # Compare screenshots
        diff_path = os.path.join(self.diff_dir, f"{test_name}_diff.png")
        similarity = self.compare_screenshots(baseline_path, current_path, diff_path)

        assert similarity >= threshold, (
            f"Screenshot mismatch for {test_name}. "
            f"Similarity: {similarity:.3f}, Threshold: {threshold}. "
            f"Diff saved to {diff_path}"
        )


class AccessibilityTester:
    """Accessibility testing utilities for GUI components."""

    def __init__(self, root=None):
        self.root = root

    def check_widget_accessibility(self, widget):
        """Check accessibility properties of a widget."""
        issues = []

        # Check for text alternatives
        if hasattr(widget, 'cget'):
            text = widget.cget('text') if 'text' in widget.configure() else ""
            if not text and hasattr(widget, 'get'):
                try:
                    text = widget.get()
                except:
                    pass

            if not text:
                issues.append("Missing text content for screen readers")

        # Check color contrast (simplified)
        if hasattr(widget, 'cget'):
            bg = widget.cget('bg') if 'bg' in widget.configure() else ""
            fg = widget.cget('fg') if 'fg' in widget.configure() else ""

            if bg and fg:
                # Basic contrast check
                if bg.lower() == fg.lower():
                    issues.append("Poor color contrast between background and foreground")

        # Check keyboard navigation
        if not hasattr(widget, 'focus_set'):
            issues.append("Widget may not support keyboard navigation")

        return issues

    def check_window_accessibility(self, window):
        """Check accessibility of an entire window."""
        issues = []

        def check_children(parent):
            for child in parent.winfo_children():
                issues.extend(self.check_widget_accessibility(child))
                check_children(child)

        check_children(window)
        return issues


class PerformanceTester:
    """Performance testing for GUI responsiveness."""

    def __init__(self, root=None):
        self.root = root

    def measure_render_time(self, widget_creation_func, iterations=10):
        """Measure time taken to create and render widgets."""
        times = []

        for _ in range(iterations):
            start_time = time.time()

            widget = widget_creation_func()
            if hasattr(widget, 'update'):
                widget.update()

            end_time = time.time()
            times.append(end_time - start_time)

            # Clean up
            if hasattr(widget, 'destroy'):
                widget.destroy()

        return {
            'min': min(times),
            'max': max(times),
            'avg': sum(times) / len(times),
            'median': sorted(times)[len(times) // 2]
        }

    def measure_event_response_time(self, widget, event_func, iterations=10):
        """Measure response time for GUI events."""
        times = []

        for _ in range(iterations):
            start_time = time.time()
            event_func()
            if hasattr(widget, 'update'):
                widget.update()
            end_time = time.time()
            times.append(end_time - start_time)

        return {
            'min': min(times),
            'max': max(times),
            'avg': sum(times) / len(times),
            'median': sorted(times)[len(times) // 2]
        }


class BaseGUITest(unittest.TestCase):
    """Base class for GUI tests with common setup and teardown."""

    def setUp(self):
        """Set up test environment."""
        self.root = tk.Tk()
        self.root.withdraw()  # Hide window during testing
        self.gui_framework = GUITestFramework(self.root)
        self.accessibility_tester = AccessibilityTester(self.root)
        self.performance_tester = PerformanceTester(self.root)

    def tearDown(self):
        """Clean up test environment."""
        if hasattr(self, 'root') and self.root:
            self.root.destroy()

    def assert_accessible(self, widget, max_issues=0):
        """Assert that a widget meets accessibility standards."""
        issues = self.accessibility_tester.check_widget_accessibility(widget)
        self.assertLessEqual(len(issues), max_issues,
                           f"Accessibility issues found: {issues}")

    def assert_screenshot_match(self, widget, test_name, threshold=0.99):
        """Assert screenshot matches baseline."""
        self.gui_framework.assert_screenshot_match(widget, test_name, threshold)

    def assert_performance(self, operation, max_time=1.0):
        """Assert operation completes within time limit."""
        start_time = time.time()
        result = operation()
        end_time = time.time()

        duration = end_time - start_time
        self.assertLessEqual(duration, max_time,
                           f"Operation took {duration:.3f}s, max allowed: {max_time}s")

        return result


# Example GUI test
class TestGUIComponents(BaseGUITest):
    """Example tests for GUI components."""

    def test_button_creation_performance(self):
        """Test button creation performance."""
        def create_button():
            button = tk.Button(self.root, text="Test Button")
            button.pack()
            return button

        metrics = self.performance_tester.measure_render_time(create_button, 5)

        # Assert reasonable performance
        self.assertLess(metrics['avg'], 0.1, "Button creation should be fast")
        print(f"Button creation performance: {metrics}")

    def test_button_accessibility(self):
        """Test button accessibility."""
        button = tk.Button(self.root, text="Accessible Button")
        button.pack()

        # Force update to ensure widget is realized
        self.root.update()

        issues = self.accessibility_tester.check_widget_accessibility(button)
        self.assertEqual(len(issues), 0, f"Accessibility issues: {issues}")

    @pytest.mark.skipif(os.name != 'nt', reason="Screenshot tests require Windows")
    def test_button_screenshot(self):
        """Test button screenshot comparison."""
        button = tk.Button(self.root, text="Screenshot Test", width=20, height=2)
        button.pack()

        # Force update and small delay for rendering
        self.root.update()
        time.sleep(0.1)

        # This will create baseline on first run, then compare
        self.assert_screenshot_match(button, "test_button")


if __name__ == '__main__':
    unittest.main()