"""
Base test framework classes for AnimeManager testing.

This module provides base classes for different types of tests:
- BaseE2ETest: For end-to-end tests
- BaseGUITest: For GUI tests
- BasePerformanceTest: For performance tests
"""

import unittest
import time
import psutil
import os
from typing import Dict, Any, Optional


class BaseE2ETest(unittest.TestCase):
    """Base class for end-to-end tests."""

    def setUp(self):
        """Set up test environment."""
        super().setUp()
        # Add any common E2E setup here
        self.start_time = time.time()

    def tearDown(self):
        """Clean up test environment."""
        super().tearDown()
        # Add any common E2E cleanup here
        end_time = time.time()
        duration = end_time - self.start_time
        print(f"E2E Test {self._testMethodName} took {duration:.2f} seconds")


class BaseGUITest(unittest.TestCase):
    """Base class for GUI tests."""

    def setUp(self):
        """Set up GUI test environment."""
        super().setUp()
        # GUI setup would go here if needed
        self.start_time = time.time()

    def tearDown(self):
        """Clean up GUI test environment."""
        super().tearDown()
        # GUI cleanup would go here
        end_time = time.time()
        duration = end_time - self.start_time
        print(f"GUI Test {self._testMethodName} took {duration:.2f} seconds")


class BasePerformanceTest(unittest.TestCase):
    """Base class for performance tests."""

    def setUp(self):
        """Set up performance test environment."""
        super().setUp()
        self.start_time = time.time()
        self.initial_memory = psutil.Process(os.getpid()).memory_info().rss

    def tearDown(self):
        """Clean up performance test environment."""
        super().tearDown()
        end_time = time.time()
        final_memory = psutil.Process(os.getpid()).memory_info().rss

        duration = end_time - self.start_time
        memory_used = final_memory - self.initial_memory

        print(f"Performance Test {self._testMethodName}:")
        print(f"  Duration: {duration:.2f} seconds")
        print(f"  Memory used: {memory_used / 1024 / 1024:.2f} MB")

    def measure_performance(self, operation, iterations: int = 1) -> Dict[str, Any]:
        """Measure performance of an operation."""
        times = []

        for _ in range(iterations):
            start = time.time()
            result = operation()
            end = time.time()
            times.append(end - start)

        return {
            'result': result,
            'times': times,
            'min': min(times),
            'max': max(times),
            'avg': sum(times) / len(times),
            'iterations': iterations
        }