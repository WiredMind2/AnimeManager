"""
Tests for torrent manager implementations.
"""

import os
import sys
import unittest

# Add project root to path
PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Import base test classes
from .base_torrent_manager_tests import (BaseTorrentManagerTestBase,
                                         TorrentManagerIntegrationTestBase,
                                         TorrentManagerPerformanceTestBase)

# Note: Specific torrent manager tests (qBittorrent, Deluge, etc.) can be added here


def create_torrent_manager_test_suite():
    """Create a comprehensive test suite for all torrent managers."""
    suite = unittest.TestSuite()

    # Note: Add specific torrent manager tests here when created
    # Example:
    # if TestQBittorrentManager:
    #     suite.addTest(unittest.TestLoader().loadTestsFromTestCase(TestQBittorrentManager))

    return suite


def run_torrent_manager_tests():
    """Run all torrent manager tests."""
    print("Running Torrent Manager Tests...")
    print("=" * 50)

    # Create test suite
    suite = create_torrent_manager_test_suite()

    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Print summary
    print("\n" + "=" * 50)
    print(f"Torrent Manager Tests Summary:")
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Skipped: {len(result.skipped) if hasattr(result, 'skipped') else 0}")

    if result.failures:
        print(f"\nFailures:")
        for test, traceback in result.failures:
            print(
                f"  - {test}: {traceback.split(chr(10))[-2] if chr(10) in traceback else traceback}"
            )

    if result.errors:
        print(f"\nErrors:")
        for test, traceback in result.errors:
            print(
                f"  - {test}: {traceback.split(chr(10))[-2] if chr(10) in traceback else traceback}"
            )

    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_torrent_manager_tests()
    sys.exit(0 if success else 1)
