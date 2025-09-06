# ABOUTME: Profiled QApplication subclass for collecting Qt event loop performance statistics
# ABOUTME: Provides low-overhead event timing data collection without slowing the event loop
import time
import weakref
from collections import defaultdict, deque
from ..util.Qt import QApplication, QEvent, QTimer, QObject


def _build_event_name_map():
    """Build mapping from event type integers to human-readable names."""
    mapping = {}
    
    # Try iterating QEvent attributes to get event type names
    for attr in dir(QEvent):
        if not attr or not attr[0].isupper():
            continue
        try:
            v = getattr(QEvent, attr)
            # Convert to int (works for both PyQt5 ints and PyQt6 enums)
            iv = int(v)
            mapping[iv] = attr
        except Exception:
            continue
    
    return mapping


# Global event name mapping - built once at import
EVENT_NAMES = _build_event_name_map()


def event_name(event):
    """Get human-readable name for an event."""
    t = int(event.type())
    return EVENT_NAMES.get(t, f"Type({t})")


class QApplicationProfile(QObject):
    """Handles statistics collection for a specific profiling session.
    
    This class collects Qt event loop performance data over a defined time period.
    Multiple QApplicationProfile instances can be active simultaneously to collect
    overlapping statistics for different analysis purposes.
    """
    
    def __init__(self, name="profile", slow_threshold_ms=5.0, max_slow_samples=1000):
        super().__init__()
        self.name = name
        self._slow_threshold = slow_threshold_ms / 1000.0
        self._max_slow_samples = max_slow_samples
        
        # Timing state
        self._start_time = time.perf_counter()
        self._total_active_time = 0.0  # seconds spent inside notify()
        
        # Event statistics - using simple data structures for speed
        self._event_stats = defaultdict(lambda: [0.0, 0])  # [total_time, count] by event type
        
        # Slow event tracking
        self._slow_samples = deque(maxlen=max_slow_samples)
        
        # Safety counters
        self._total_events = 0
        self._exceptions = 0
        self._active = True
    
    def record_event(self, duration, event_type, receiver_name=None):
        """Record statistics for a single event. Called by ProfiledQApplication."""
        if not self._active:
            return
            
        self._total_active_time += duration
        self._total_events += 1
        
        # Update event type statistics
        stats = self._event_stats[event_type]
        stats[0] += duration  # total time
        stats[1] += 1         # count
        
        # Track slow events
        if duration >= self._slow_threshold:
            self._slow_samples.append((duration, event_type, receiver_name or "<unknown>"))
    
    def record_exception(self):
        """Record an exception during event processing."""
        if self._active:
            self._exceptions += 1
    
    def stop(self):
        """Stop collecting statistics for this profile."""
        self._active = False
    
    def is_active(self):
        """Check if this profile is still collecting data."""
        return self._active
    
    def get_statistics(self):
        """Get current profiling statistics.
        
        Returns dict with keys:
        - name: profile name
        - wall_time: total elapsed time since start
        - active_time: time spent processing events  
        - idle_time: time spent waiting for events
        - active_fraction: fraction of time spent processing events
        - total_events: total number of events processed
        - exceptions: number of exceptions during event processing
        - event_stats: dict mapping event_type_int -> {'time': float, 'count': int, 'name': str}
        - slow_events: list of (duration, event_type_name, receiver_class) tuples
        """
        current_time = time.perf_counter()
        wall_time = current_time - self._start_time
        active_time = self._total_active_time
        idle_time = wall_time - active_time
        active_fraction = active_time / wall_time if wall_time > 0 else 0.0
        
        # Convert event stats to more usable format
        event_stats = {}
        for event_type, (total_time, count) in self._event_stats.items():
            event_stats[event_type] = {
                'time': total_time,
                'count': count,
                'name': EVENT_NAMES.get(event_type, f"Type({event_type})")
            }
        
        # Convert slow events to include event names
        slow_events = []
        for duration, event_type, receiver_name in self._slow_samples:
            event_type_name = EVENT_NAMES.get(event_type, f"Type({event_type})")
            slow_events.append((duration, event_type_name, receiver_name))
        
        return {
            'name': self.name,
            'wall_time': wall_time,
            'active_time': active_time,
            'idle_time': idle_time,
            'active_fraction': active_fraction,
            'total_events': self._total_events,
            'exceptions': self._exceptions,
            'event_stats': event_stats,
            'slow_events': slow_events
        }
    
    def print_summary_report(self, top_events=10, slow_events=10):
        """Print a human-readable summary of profiling statistics."""
        stats = self.get_statistics()
        
        print(f"\n=== Qt Event Loop Profile Report: {stats['name']} ===")
        print(f"Wall time: {stats['wall_time']:.3f}s")
        print(f"Active time: {stats['active_time']:.3f}s ({stats['active_fraction']:.1%})")
        print(f"Idle time: {stats['idle_time']:.3f}s")
        print(f"Total events: {stats['total_events']:,}")
        
        if stats['exceptions'] > 0:
            print(f"Exceptions: {stats['exceptions']}")
        
        # Top events by total time
        if stats['event_stats']:
            print(f"\nTop {top_events} event types by total time:")
            sorted_events = sorted(
                stats['event_stats'].items(),
                key=lambda x: x[1]['time'],
                reverse=True
            )[:top_events]
            
            for event_type, data in sorted_events:
                avg_ms = (data['time'] / data['count'] * 1000) if data['count'] else 0
                print(f"  {data['name']:<20} {data['time']:7.3f}s ({data['count']:>6,} events, {avg_ms:5.2f}ms avg)")
        
        # Slowest individual events
        if stats['slow_events']:
            print(f"\nSlowest {slow_events} individual events (≥{self._slow_threshold*1000:.1f}ms):")
            sorted_slow = sorted(stats['slow_events'], reverse=True)[:slow_events]
            for duration, event_name, receiver in sorted_slow:
                print(f"  {event_name:<20} {duration*1000:7.2f}ms (receiver: {receiver})")
    
    def get_event_breakdown_by_type(self):
        """Get event processing time breakdown by event type.
        
        Returns list of tuples: (event_name, total_time, count, avg_time, percentage)
        sorted by total time descending.
        """
        stats = self.get_statistics()
        if not stats['event_stats']:
            return []
        
        total_time = stats['active_time']
        breakdown = []
        
        for event_type, data in stats['event_stats'].items():
            avg_time = data['time'] / data['count'] if data['count'] else 0
            percentage = (data['time'] / total_time * 100) if total_time else 0
            breakdown.append((
                data['name'],
                data['time'],
                data['count'], 
                avg_time,
                percentage
            ))
        
        return sorted(breakdown, key=lambda x: x[1], reverse=True)


class ProfiledQApplication(QApplication):
    """QApplication subclass that manages multiple Qt event loop profiling sessions.
    
    This class acts as a dispatcher that sends event timing information to
    multiple active QApplicationProfile instances. This allows for targeted
    profiling over specific time periods and overlapping profile sessions.
    """
    
    def __init__(self, *args):
        super().__init__(*args)
        
        # Active profiles - using WeakSet to avoid holding references
        self._active_profiles = weakref.WeakSet()
        
        # Guard against re-entrancy (should be rare but possible)
        self._in_notify = False
        
    def start_profile(self, name="profile", slow_threshold_ms=5.0, max_slow_samples=1000):
        """Start a new profiling session.
        
        Returns:
            QApplicationProfile: Profile instance that will collect statistics
        """
        profile = QApplicationProfile(name, slow_threshold_ms, max_slow_samples)
        self._active_profiles.add(profile)
        return profile
    
    def notify(self, receiver, event):
        """Override notify to dispatch timing information to active profiles."""
        if self._in_notify:
            # Rare re-entrancy case - just pass through
            return super().notify(receiver, event)
        
        # Quick exit if no active profiles to avoid any overhead
        if not self._active_profiles:
            return super().notify(receiver, event)
        
        self._in_notify = True
        start_time = time.perf_counter()
        exception_occurred = False
        
        try:
            result = super().notify(receiver, event)
            return result
        except Exception:
            exception_occurred = True
            raise
        finally:
            # Timing collection - keep this as fast as possible
            duration = time.perf_counter() - start_time
            event_type = int(event.type())
            
            # Get receiver name once for all profiles
            receiver_name = None
            if self._active_profiles:
                try:
                    receiver_name = type(receiver).__name__
                except Exception:
                    receiver_name = "<unknown>"
            
            # Dispatch to all active profiles
            for profile in list(self._active_profiles):  # Copy to avoid modification during iteration
                if profile.is_active():
                    profile.record_event(duration, event_type, receiver_name)
                    if exception_occurred:
                        profile.record_exception()
            
            self._in_notify = False
    
    def get_active_profiles(self):
        """Get list of currently active profile instances."""
        return [p for p in self._active_profiles if p.is_active()]
    
    def get_profile_count(self):
        """Get the number of active profiles."""
        return len([p for p in self._active_profiles if p.is_active()])
    
    def stop_all_profiles(self):
        """Stop all currently active profiles."""
        for profile in list(self._active_profiles):
            if profile.is_active():
                profile.stop()