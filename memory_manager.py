import gc
import psutil
import time
import tracemalloc
import weakref
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional

try:
    from .logger import log
except ImportError:
    from logger import log


class MemoryManager:
    """Comprehensive memory management system for the application"""

    def __init__(self, memory_limit_gb=4.0, enable_tracemalloc=True):
        self.memory_limit_bytes = int(memory_limit_gb * 1024 * 1024 * 1024)
        self.process = psutil.Process()
        self.monitoring_active = False
        self.monitor_thread = None
        self.alert_callbacks = []

        # Memory monitoring
        self.memory_history = []
        self.gc_stats = {'collections': 0, 'freed_objects': 0, 'peak_memory': 0}
        self.memory_levels = {
            'low': 0.7,      # < 70% of limit
            'medium': 0.85,  # 70-85% of limit
            'high': 0.95,    # 85-95% of limit
            'critical': 1.0  # > 95% of limit
        }

        # Object pooling
        self.object_pools = defaultdict(list)
        self.pool_limits = {
            'anime': 100,
            'character': 50,
            'search_result': 200,
            'thumbnail': 50,
            'image': 100
        }

        # Weak references for leak detection
        self.weak_refs = weakref.WeakSet()
        self.tracked_objects = {}
        self.leak_threshold_hours = 1.0

        # Performance monitoring
        self.performance_stats = {
            'memory_checks': 0,
            'alerts_triggered': 0,
            'objects_pooled': 0,
            'leaks_detected': 0
        }

        # Enable tracemalloc for detailed memory tracking
        if enable_tracemalloc:
            tracemalloc.start()
            self.tracemalloc_enabled = True
        else:
            self.tracemalloc_enabled = False

    def start_monitoring(self, interval_seconds=30.0):
        """Start background memory monitoring"""
        if self.monitoring_active:
            return

        self.monitoring_active = True
        import threading
        self.monitor_thread = threading.Thread(
            target=self._monitor_loop,
            args=(interval_seconds,),
            daemon=True,
            name="MemoryMonitor"
        )
        self.monitor_thread.start()
        print(f"Memory monitoring started (limit: {self.memory_limit_bytes / (1024**3):.1f}GB)")

    def stop_monitoring(self):
        """Stop memory monitoring"""
        self.monitoring_active = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5.0)
        print("Memory monitoring stopped")

    def _monitor_loop(self, interval_seconds):
        """Background monitoring loop"""
        while self.monitoring_active:
            try:
                stats = self.get_memory_stats()
                self.memory_history.append((time.time(), stats))

                # Keep only recent history (last 60 minutes)
                cutoff_time = time.time() - 3600
                self.memory_history = [
                    (t, s) for t, s in self.memory_history if t > cutoff_time
                ]

                # Check memory pressure and take action
                self._handle_memory_pressure(stats)

                # Update performance stats
                self.performance_stats['memory_checks'] += 1

                time.sleep(interval_seconds)

            except Exception as e:
                print(f"Memory monitoring error: {e}")
                time.sleep(interval_seconds)

    def get_memory_stats(self) -> Dict[str, Any]:
        """Get comprehensive memory statistics"""
        try:
            memory_info = self.process.memory_info()
            current_mb = memory_info.rss / (1024 * 1024)

            # Get memory level
            usage_ratio = current_mb / (self.memory_limit_bytes / (1024 * 1024))
            memory_level = 'low'
            for level, threshold in self.memory_levels.items():
                if usage_ratio >= threshold:
                    memory_level = level
                else:
                    break

            # Update peak memory
            if current_mb > self.gc_stats['peak_memory']:
                self.gc_stats['peak_memory'] = current_mb

            # Get GC stats
            gc_stats = gc.get_stats()

            # Get tracemalloc stats if enabled
            tracemalloc_stats = None
            if self.tracemalloc_enabled:
                try:
                    current, peak = tracemalloc.get_traced_memory()
                    tracemalloc_stats = {
                        'current_mb': current / (1024 * 1024),
                        'peak_mb': peak / (1024 * 1024)
                    }
                except:
                    pass

            return {
                'current_mb': current_mb,
                'peak_mb': self.gc_stats['peak_memory'],
                'usage_ratio': usage_ratio,
                'memory_level': memory_level,
                'available_mb': psutil.virtual_memory().available / (1024 * 1024),
                'gc_collections': sum(stat['collections'] for stat in gc_stats),
                'object_counts': gc.get_count(),
                'tracemalloc': tracemalloc_stats,
                'pool_sizes': {k: len(v) for k, v in self.object_pools.items()},
                'tracked_objects': len(self.tracked_objects)
            }

        except Exception as e:
            print(f"Error getting memory stats: {e}")
            return {
                'current_mb': 0,
                'peak_mb': 0,
                'usage_ratio': 0,
                'memory_level': 'unknown',
                'available_mb': 0,
                'gc_collections': 0,
                'object_counts': (0, 0, 0),
                'tracemalloc': None,
                'pool_sizes': {},
                'tracked_objects': 0
            }

    def _handle_memory_pressure(self, stats: Dict[str, Any]):
        """Handle memory pressure based on current level"""
        level = stats['memory_level']

        if level == 'high':
            print(f"High memory usage detected ({stats['current_mb']:.1f}MB)")
            self._cleanup_non_essential()
            self.force_garbage_collection()

        elif level == 'critical':
            print(f"Critical memory usage detected ({stats['current_mb']:.1f}MB)")
            self._aggressive_cleanup()
            self.force_garbage_collection()
            self._trigger_alerts('critical_memory', stats)

    def force_garbage_collection(self):
        """Force garbage collection with statistics"""
        before_stats = self.get_memory_stats()

        # Run garbage collection
        collected = gc.collect()

        after_stats = self.get_memory_stats()

        freed_mb = before_stats['current_mb'] - after_stats['current_mb']
        self.gc_stats['collections'] += 1
        self.gc_stats['freed_objects'] += collected

        print(f"GC: Collected {collected} objects, freed {freed_mb:.2f}MB")

    def get_object_from_pool(self, object_type: str) -> Any:
        """Get object from pool or create new one"""
        if object_type in self.object_pools and self.object_pools[object_type]:
            obj = self.object_pools[object_type].pop()
            self.performance_stats['objects_pooled'] += 1
            return obj

        # Create new object based on type
        return self._create_object(object_type)

    def return_object_to_pool(self, object_type: str, obj: Any):
        """Return object to pool for reuse"""
        if object_type in self.object_pools:
            # Clear object state before pooling
            self._clear_object_state(obj)

            # Add to pool if under limit
            if len(self.object_pools[object_type]) < self.pool_limits.get(object_type, 50):
                self.object_pools[object_type].append(obj)

    def track_object(self, obj: Any, name: str = None, metadata: Dict[str, Any] = None):
        """Track object for memory leak detection"""
        if name is None:
            name = f"object_{id(obj)}"

        # Create weak reference to avoid circular dependencies
        weak_ref = weakref.ref(obj, lambda ref: self._object_collected(name))
        self.weak_refs.add(weak_ref)

        self.tracked_objects[name] = {
            'weak_ref': weak_ref,
            'created_at': time.time(),
            'type': type(obj).__name__,
            'metadata': metadata or {}
        }

    def _object_collected(self, name: str):
        """Callback when tracked object is garbage collected"""
        if name in self.tracked_objects:
            del self.tracked_objects[name]

    def detect_memory_leaks(self) -> List[Dict[str, Any]]:
        """Detect potential memory leaks"""
        leaks = []
        current_time = time.time()

        for name, info in self.tracked_objects.items():
            weak_ref = info['weak_ref']

            # Check if object is still alive after threshold time
            if weak_ref() is not None:
                age_hours = (current_time - info['created_at']) / 3600
                if age_hours > self.leak_threshold_hours:
                    leaks.append({
                        'name': name,
                        'type': info['type'],
                        'age_hours': age_hours,
                        'metadata': info['metadata'],
                        'still_alive': True
                    })

        self.performance_stats['leaks_detected'] = len(leaks)
        return leaks

    def add_alert_callback(self, callback: Callable):
        """Add callback for memory alerts"""
        self.alert_callbacks.append(callback)

    def _trigger_alerts(self, alert_type: str, data: Dict[str, Any]):
        """Trigger memory alerts"""
        self.performance_stats['alerts_triggered'] += 1

        for callback in self.alert_callbacks:
            try:
                callback(alert_type, data)
            except Exception as e:
                print(f"Alert callback error: {e}")

    def optimize_memory_usage(self):
        """Comprehensive memory optimization"""
        print("Starting comprehensive memory optimization...")

        # 1. Force garbage collection
        print("Running garbage collection...")
        self.force_garbage_collection()

        # 2. Clear object pools
        print("Clearing object pools...")
        total_cleared = 0
        for pool_type, pool in self.object_pools.items():
            total_cleared += len(pool)
            pool.clear()
        print(f"Cleared {total_cleared} objects from pools")

        # 3. Clear tracked objects (force cleanup)
        print("Cleaning up tracked objects...")
        leaks_before = len(self.detect_memory_leaks())
        self.tracked_objects.clear()
        self.weak_refs.clear()
        print(f"Cleaned up tracking data (was tracking {leaks_before} potential leaks)")

        # 4. Run final garbage collection
        print("Final garbage collection...")
        self.force_garbage_collection()

        # Show results
        final_stats = self.get_memory_stats()
        print(f"Memory optimization complete. Current usage: {final_stats['current_mb']:.2f}MB")

        return final_stats

    def get_performance_report(self) -> Dict[str, Any]:
        """Get comprehensive memory performance report"""
        current_stats = self.get_memory_stats()
        leaks = self.detect_memory_leaks()

        # Calculate memory efficiency metrics
        memory_efficiency = 1.0 - (current_stats['usage_ratio'])
        pool_utilization = sum(len(pool) for pool in self.object_pools.values()) / sum(self.pool_limits.values()) if self.pool_limits else 0

        return {
            'current_memory_mb': current_stats['current_mb'],
            'peak_memory_mb': current_stats['peak_mb'],
            'memory_limit_gb': self.memory_limit_bytes / (1024**3),
            'usage_percentage': current_stats['usage_ratio'] * 100,
            'memory_level': current_stats['memory_level'],
            'memory_efficiency': memory_efficiency,
            'pool_utilization': pool_utilization,
            'gc_collections': self.gc_stats['collections'],
            'objects_freed': self.gc_stats['freed_objects'],
            'tracked_objects': len(self.tracked_objects),
            'potential_leaks': len(leaks),
            'pool_sizes': current_stats['pool_sizes'],
            'performance_stats': self.performance_stats.copy(),
            'memory_history_points': len(self.memory_history),
            'leak_details': leaks[:10],  # First 10 leaks for brevity
            'tracemalloc_enabled': self.tracemalloc_enabled,
            'tracemalloc_stats': current_stats['tracemalloc']
        }

    def _create_object(self, object_type: str) -> Any:
        """Create new object of specified type"""
        # This would be implemented based on actual object types used
        if object_type == 'anime':
            return {'type': 'anime', 'data': {}}
        elif object_type == 'character':
            return {'type': 'character', 'data': {}}
        elif object_type == 'search_result':
            return {'type': 'search_result', 'data': {}}
        else:
            return {'type': object_type, 'data': {}}

    def _clear_object_state(self, obj: Any):
        """Clear object state for pooling"""
        if isinstance(obj, dict):
            # Clear dict contents but keep structure
            keys_to_remove = [k for k in obj.keys() if k != 'type']
            for key in keys_to_remove:
                del obj[key]
            if 'data' in obj:
                obj['data'].clear()

    def _cleanup_non_essential(self):
        """Clean up non-essential memory usage"""
        # Clear any caches that can be rebuilt
        # This would be implemented based on application-specific caches
        pass

    def _aggressive_cleanup(self):
        """Perform aggressive memory cleanup"""
        # Clear all pools
        for pool in self.object_pools.values():
            pool.clear()

        # Force multiple GC cycles
        for _ in range(3):
            gc.collect()

        # Clear weak references
        self.weak_refs.clear()

        print("Aggressive memory cleanup completed")


# Global memory manager instance
_memory_manager = None

def get_memory_manager() -> MemoryManager:
    """Get the global memory manager instance"""
    global _memory_manager
    if _memory_manager is None:
        _memory_manager = MemoryManager()
    return _memory_manager

def track_memory_object(obj: Any, name: str = None, metadata: Dict[str, Any] = None):
    """Convenience function to track an object for memory leak detection"""
    get_memory_manager().track_object(obj, name, metadata)

def get_object_from_pool(object_type: str) -> Any:
    """Convenience function to get object from pool"""
    return get_memory_manager().get_object_from_pool(object_type)

def return_object_to_pool(object_type: str, obj: Any):
    """Convenience function to return object to pool"""
    get_memory_manager().return_object_to_pool(object_type, obj)