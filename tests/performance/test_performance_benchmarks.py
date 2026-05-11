"""
Performance Testing and Benchmarking Suite

This module provides comprehensive performance testing including:
- Automated performance benchmarks
- Memory leak detection
- Load testing for concurrent operations
- Database query performance tests
- API response time benchmarks
"""

import time
import psutil
import tracemalloc
import threading
import concurrent.futures
from functools import wraps
import pytest
import statistics
import unittest
from unittest.mock import MagicMock, patch

try:
    from ..base_test_framework import BasePerformanceTest
except ImportError:
    from tests.base_test_framework import BasePerformanceTest


class PerformanceMonitor:
    """Monitor system performance metrics during tests."""

    def __init__(self):
        self.process = psutil.Process()
        self.start_time = None
        self.start_memory = None
        self.start_cpu = None

    def start_monitoring(self):
        """Start performance monitoring."""
        self.start_time = time.time()
        self.start_memory = self.process.memory_info().rss
        self.start_cpu = self.process.cpu_percent(interval=None)

    def get_metrics(self):
        """Get current performance metrics."""
        if self.start_time is None:
            return {}

        current_time = time.time()
        current_memory = self.process.memory_info().rss
        current_cpu = self.process.cpu_percent(interval=None)

        return {
            'elapsed_time': current_time - self.start_time,
            'memory_usage': current_memory,
            'memory_delta': current_memory - self.start_memory,
            'cpu_percent': current_cpu,
            'cpu_delta': current_cpu - self.start_cpu
        }


def benchmark(iterations=100, warmup=5):
    """Decorator for benchmarking functions."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Warmup runs
            for _ in range(warmup):
                func(*args, **kwargs)

            # Benchmark runs
            times = []
            for _ in range(iterations):
                start = time.perf_counter()
                result = func(*args, **kwargs)
                end = time.perf_counter()
                times.append(end - start)

            # Calculate statistics
            stats = {
                'iterations': iterations,
                'min': min(times),
                'max': max(times),
                'mean': statistics.mean(times),
                'median': statistics.median(times),
                'stdev': statistics.stdev(times) if len(times) > 1 else 0,
                'total': sum(times)
            }

            # Store results for later retrieval
            wrapper.benchmark_results = stats
            return result

        return wrapper
    return decorator


class MemoryLeakDetector:
    """Detect memory leaks in functions."""

    def __init__(self, threshold_mb=10):
        self.threshold_bytes = threshold_mb * 1024 * 1024

    def check_for_leaks(self, func, *args, **kwargs):
        """Check if function has memory leaks."""
        tracemalloc.start()

        # Get initial memory
        initial_snapshot = tracemalloc.take_snapshot()

        # Run function
        result = func(*args, **kwargs)

        # Get final memory
        final_snapshot = tracemalloc.take_snapshot()
        tracemalloc.stop()

        # Compare snapshots
        stats = final_snapshot.compare_to(initial_snapshot, 'lineno')

        total_growth = sum(stat.size_diff for stat in stats if stat.size_diff > 0)

        return {
            'memory_growth': total_growth,
            'has_leak': total_growth > self.threshold_bytes,
            'top_allocators': stats[:10] if stats else []
        }


class LoadTester:
    """Load testing for concurrent operations."""

    def __init__(self, max_workers=10):
        self.max_workers = max_workers

    def run_concurrent_operations(self, operation, num_operations=100, *args, **kwargs):
        """Run operations concurrently and measure performance."""
        start_time = time.time()

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all operations
            futures = [executor.submit(operation, *args, **kwargs)
                      for _ in range(num_operations)]

            # Wait for completion and collect results
            results = []
            for future in concurrent.futures.as_completed(futures):
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    results.append({'error': str(e)})

        end_time = time.time()

        return {
            'total_time': end_time - start_time,
            'operations_per_second': num_operations / (end_time - start_time),
            'successful_operations': len([r for r in results if 'error' not in r]),
            'failed_operations': len([r for r in results if 'error' in r]),
            'results': results
        }


class DatabasePerformanceTester:
    """Performance testing for database operations."""

    def __init__(self, db_instance=None):
        self.db = db_instance

    def benchmark_query(self, query_func, iterations=50, *args, **kwargs):
        """Benchmark database query performance."""
        times = []

        for _ in range(iterations):
            start = time.perf_counter()
            result = query_func(*args, **kwargs)
            end = time.perf_counter()
            times.append(end - start)

        return {
            'iterations': iterations,
            'times': times,
            'min': min(times),
            'max': max(times),
            'avg': statistics.mean(times),
            'median': statistics.median(times),
            'stdev': statistics.stdev(times) if len(times) > 1 else 0
        }

    def test_connection_pooling(self, num_connections=20):
        """Test database connection pooling performance."""
        # This would test connection pooling if implemented
        pass


class APIResponseTester:
    """Test API response times and performance."""

    def __init__(self, api_client=None):
        self.api_client = api_client

    def benchmark_api_call(self, api_method, iterations=20, *args, **kwargs):
        """Benchmark API call performance."""
        times = []
        success_count = 0

        for _ in range(iterations):
            start = time.perf_counter()
            try:
                result = api_method(*args, **kwargs)
                success_count += 1
            except Exception:
                result = None
            end = time.perf_counter()
            times.append(end - start)

        return {
            'iterations': iterations,
            'successful_calls': success_count,
            'success_rate': success_count / iterations,
            'response_times': times,
            'avg_response_time': statistics.mean(times),
            'min_response_time': min(times),
            'max_response_time': max(times),
            'p95_response_time': statistics.quantiles(times, n=20)[18] if len(times) >= 20 else max(times)
        }


class BasePerformanceTest(unittest.TestCase):
    """Base class for performance tests."""

    def setUp(self):
        """Set up performance testing environment."""
        self.monitor = PerformanceMonitor()
        self.memory_detector = MemoryLeakDetector()
        self.load_tester = LoadTester()

    def assert_performance_threshold(self, actual_time, max_time, operation_name="operation"):
        """Assert that operation completes within time threshold."""
        self.assertLessEqual(actual_time, max_time,
                           f"{operation_name} took {actual_time:.3f}s, exceeding limit of {max_time:.3f}s")

    def assert_no_memory_leak(self, func, *args, **kwargs):
        """Assert that function doesn't have memory leaks."""
        result = self.memory_detector.check_for_leaks(func, *args, **kwargs)
        self.assertFalse(result['has_leak'],
                        f"Memory leak detected: {result['memory_growth']} bytes growth")

    def assert_load_performance(self, operation, num_operations=50, max_total_time=10.0):
        """Assert load testing performance."""
        result = self.load_tester.run_concurrent_operations(operation, num_operations)
        self.assertLessEqual(result['total_time'], max_total_time,
                           f"Load test took {result['total_time']:.3f}s for {num_operations} operations")


# Example performance tests
class TestPerformanceBenchmarks(BasePerformanceTest):
    """Performance benchmark tests."""

    def setUp(self):
        super().setUp()
        # Mock database for testing
        self.mock_db = MagicMock()

    @benchmark(iterations=50, warmup=5)
    def benchmark_string_concatenation(self):
        """Benchmark string concatenation performance."""
        result = ""
        for i in range(1000):
            result += str(i)
        return result

    def test_string_concatenation_performance(self):
        """Test string concatenation performance."""
        self.benchmark_string_concatenation()
        stats = self.benchmark_string_concatenation.benchmark_results

        # Assert reasonable performance
        self.assertLess(stats['mean'], 0.01, "String concatenation should be fast")
        print(f"String concatenation benchmark: {stats}")

    def test_memory_leak_detection(self):
        """Test memory leak detection."""
        def memory_intensive_function():
            # Create some objects
            data = [i for i in range(10000)]
            return sum(data)

        # Should not detect leaks for normal operations
        self.assert_no_memory_leak(memory_intensive_function)

    def test_load_testing(self):
        """Test concurrent load performance."""
        def simple_operation():
            time.sleep(0.01)  # Simulate some work
            return "done"

        result = self.load_tester.run_concurrent_operations(simple_operation, 20)

        # Assert reasonable performance
        self.assertGreater(result['operations_per_second'], 50,
                          f"Low throughput: {result['operations_per_second']} ops/sec")
        print(f"Load test results: {result}")

    @pytest.mark.performance
    def test_database_query_performance(self):
        """Test database query performance (mocked)."""
        db_tester = DatabasePerformanceTester(self.mock_db)

        def mock_query():
            time.sleep(0.001)  # Simulate query time
            return [{'id': 1, 'name': 'test'}]

        result = db_tester.benchmark_query(mock_query, iterations=20)

        # Assert query performance
        self.assertLess(result['avg'], 0.02, "Database queries should be fast")
        print(f"Database query benchmark: {result}")

    @pytest.mark.performance
    def test_api_response_performance(self):
        """Test API response performance (mocked)."""
        api_tester = APIResponseTester()

        def mock_api_call():
            time.sleep(0.005)  # Simulate API call
            return {'status': 'success', 'data': []}

        result = api_tester.benchmark_api_call(mock_api_call, iterations=10)

        # Assert API performance
        self.assertLess(result['avg_response_time'], 0.1, "API calls should be responsive")
        self.assertEqual(result['success_rate'], 1.0, "All API calls should succeed")
        print(f"API response benchmark: {result}")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])