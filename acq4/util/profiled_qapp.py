import math
import time
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


def extract_metacall_info(event):
    """Extract information from MetaCall events.
    
    Note: PyQt5 MetaCall events don't expose internal signal/slot details
    without private Qt headers, so we can only provide basic info.
    """
    event_type_int = int(event.type())
    if event_type_int != 43:  # MetaCall is type 43
        return None
    
    # MetaCall events in PyQt5 appear as generic QEvent objects
    # and don't expose sender/signal information publicly
    return "Signal/slot call (details not available in PyQt5)"


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
        self._end_time = None  # Set when profiling stops
        
        # Raw event data - analysis deferred
        self._events = []  # Store raw (duration, event_type, receiver, event) tuples
        
        # Safety counters
        self._exceptions = 0
        self._active = True
    
    def record_event(self, duration, event_type, receiver, event):
        """Record raw event data for later analysis. Called by ProfiledQApplication."""
        if not self._active:
            return
            
        # Store raw event data - analysis happens later
        self._events.append((duration, event_type, receiver, event))    
    
    def stop(self):
        """Stop collecting statistics for this profile."""
        self._active = False
        self._end_time = time.perf_counter()
    
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
        - slow_events: list of (duration, event_type_name, receiver_class, info) tuples
        """
        # Use end time if profiling has stopped, otherwise current time for active profiles
        end_time = self._end_time if self._end_time is not None else time.perf_counter()
        wall_time = end_time - self._start_time
        
        # Analyze raw event data and calculate totals
        event_stats = defaultdict(lambda: {'time': 0.0, 'count': 0, 'name': ''})
        slow_events = []
        total_active_time = 0.0
        total_events = 0
        
        for duration, event_type, receiver, event in self._events:
            total_active_time += duration
            total_events += 1
            # Update event type statistics
            stats = event_stats[event_type]
            stats['time'] += duration
            stats['count'] += 1
            stats['name'] = EVENT_NAMES.get(event_type, f"Type({event_type})")
            
            # Track slow events
            if duration >= self._slow_threshold:
                # Get receiver name
                try:
                    class_name = type(receiver).__name__
                    object_name = getattr(receiver, 'objectName', lambda: '')()
                    if object_name:
                        receiver_name = f"{class_name}({object_name})"
                    else:
                        receiver_name = class_name
                except Exception:
                    receiver_name = "<unknown>"
                
                # Get event info
                event_info = ""
                try:
                    event_type_name = EVENT_NAMES.get(event_type, f"Type({event_type})")
                    if event_type_name == 'MetaCall':
                        event_info = extract_metacall_info(event)
                    elif duration >= 0.005:  # For slow events, show the event type
                        event_info = f"Event: {event_type_name}"
                except Exception as e:
                    event_info = f"Error: {str(e)}"
                
                slow_events.append((duration, event_type_name, receiver_name, event_info))
        
        # Calculate derived statistics
        idle_time = wall_time - total_active_time
        active_fraction = total_active_time / wall_time if wall_time > 0 else 0.0
        
        # Sort slow events by duration descending
        slow_events.sort(reverse=True)
        if len(slow_events) > self._max_slow_samples:
            slow_events = slow_events[:self._max_slow_samples]
        
        return {
            'name': self.name,
            'wall_time': wall_time,
            'active_time': total_active_time,
            'idle_time': idle_time,
            'active_fraction': active_fraction,
            'total_events': total_events,
            'exceptions': self._exceptions,
            'event_stats': dict(event_stats),
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
        
        # Active profiles
        self._active_profiles = []
        
        # Guard against re-entrancy (should be rare but possible)
        self._in_notify = False
        
        # Exponential averaging for real-time activity fraction
        self.exp_avg_time_constant = 0.3  # seconds
        self._exp_avg_active_fraction = None  # Current exponentially averaged active fraction
        self._last_event_end = time.perf_counter()  # Time when previous event completed
        
    def start_profile(self, name="profile", slow_threshold_ms=5.0, max_slow_samples=1000):
        """Start a new profiling session.
        
        Returns:
            QApplicationProfile: Profile instance that will collect statistics
        """
        profile = QApplicationProfile(name, slow_threshold_ms, max_slow_samples)
        self._active_profiles.append(profile)
        return profile
    
    def notify(self, receiver, event):
        """Override notify to dispatch timing information to active profiles."""
        if self._in_notify:
            # Rare re-entrancy case - just pass through
            return super().notify(receiver, event)
        
        self._in_notify = True
        start_time = time.perf_counter()
        exception_occurred = False
        
        try:
            return super().notify(receiver, event)
        except Exception:
            exception_occurred = True
            raise
        finally:
            self._in_notify = False

            # Timing collection - keep this as fast as possible
            duration = time.perf_counter() - start_time
            event_type = int(event.type())
            
            # Update exponential averaging for activity fraction
            self._update_activity_average(duration)
            
            # Dispatch raw data to all active profiles (minimal work)
            for profile in self._active_profiles:
                if profile.is_active():
                    profile.record_event(duration, event_type, receiver, event)
                    if exception_occurred:
                        profile._exceptions += 1
    
    def get_active_profiles(self):
        """Get list of currently active profile instances."""
        return [p for p in self._active_profiles if p.is_active()]
    
    def get_profile_count(self):
        """Get the number of active profiles."""
        return len([p for p in self._active_profiles if p.is_active()])
    
    def stop_all_profiles(self):
        """Stop all currently active profiles."""
        for profile in self._active_profiles:
            if profile.is_active():
                profile.stop()
    
    def _update_activity_average(self, event_duration):
        """Update the exponentially averaged activity fraction."""
        current_time = time.perf_counter()
        total_interval = current_time - self._last_event_end
        
        if total_interval > 0:
            # Calculate activity fraction for this interval
            activity_fraction = event_duration / total_interval
            
            # For exponential averaging with time-based weighting:
            alpha = 1.0 - math.exp(-total_interval / self.exp_avg_time_constant)
            
            if self._exp_avg_active_fraction is None:
                # First measurement
                self._exp_avg_active_fraction = activity_fraction
            else:
                # Exponential smoothing with proper time weighting
                self._exp_avg_active_fraction = (
                    alpha * activity_fraction + 
                    (1.0 - alpha) * self._exp_avg_active_fraction
                )
        
        self._last_event_end = current_time
    
    @property
    def activity_fraction(self):
        """Get the current exponentially averaged activity fraction.
        
        Returns:
            float: Fraction of real time spent processing events (0.0 to 1.0)
        """
        return self._exp_avg_active_fraction