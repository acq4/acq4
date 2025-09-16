import math
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
        self.start_time = time.perf_counter()
        self.end_time = None  # Set when profiling stops
        
        # Raw event data - analysis deferred
        self._events = []  # Store raw (duration, event_type, receiver, event) tuples

        # Safety counters
        self._exceptions = 0
        self._active = True
    
    def record_event(self, rec):
        """Record raw event data for later analysis. Called by ProfiledQApplication."""
        if not self._active:
            return
        self._events.append(rec)

    def stop(self):
        """Stop collecting statistics for this profile."""
        self._active = False
        self.end_time = time.perf_counter()
    
    def is_active(self):
        """Check if this profile is still collecting data."""
        return self._active
    
    def get_statistics(self, group_by='type'):
        """Get profiling statistics as uniform row data for UI display.
        
        Args:
            group_by: 'type' to group by event type, 'type_receiver' to group by (type, receiver)
        
        Returns list of dicts with uniform statistics for each row (global + grouped):
        [{'description': 'All Events', 'count': 1000, 'total_time': 2.5, 'avg_time': 0.0025, 'percentage': 100.0}, ...]
        """
        # Sort events into lists: first list contains all events, subsequent lists contain grouped events
        event_lists = []
        
        # Global list - all events
        event_lists.append(("All Events", self._events))
        
        # Group events based on group_by parameter
        events_by_group = defaultdict(list)
        
        for event_data in self._events:
            event_type = event_data['event_type']
            receiver_ref = event_data['receiver']
            description = event_data['description']
            
            if group_by == 'type':
                group_key = event_type
            elif group_by == 'type_receiver':
                receiver = receiver_ref()
                if receiver is None:
                    # Use the captured description for dead receivers
                    group_key = (event_type, f"{description} <deleted>")
                else:
                    group_key = (event_type, receiver)
            else:
                raise ValueError(f"Invalid group_by value: {group_by}")
            
            events_by_group[group_key].append(event_data)
        
        # Add grouped lists, sorted by total time descending
        group_totals = []
        for group_key, events in events_by_group.items():
            total_time = sum(event['duration'] for event in events)
            
            if group_by == 'type':
                event_type = group_key
                description = EVENT_NAMES.get(event_type, f"Type({event_type})")
            elif group_by == 'type_receiver':
                event_type, receiver = group_key
                # Create receiver description
                try:
                    if isinstance(receiver, str):
                        # receiver is already a description string (like "QWidget(mainWindow) <deleted>")
                        receiver_desc = receiver
                    else:
                        class_name = type(receiver).__name__
                        object_name = getattr(receiver, 'objectName', lambda: '')()
                        if object_name:
                            receiver_desc = f"{class_name}({object_name})"
                        else:
                            receiver_desc = class_name
                except Exception:
                    receiver_desc = "<unknown>"
                event_type_name = EVENT_NAMES.get(event_type, f"Type({event_type})")
                description = f"{event_type_name} → {receiver_desc}"
            
            group_totals.append((total_time, description, events))
        
        group_totals.sort(reverse=True)
        for total_time, description, events in group_totals:
            event_lists.append((description, events))
        
        # Calculate statistics uniformly for each row/list
        row_stats = []
        wall_time = self.end_time - self.start_time
        
        for description, events in event_lists:
            count = len(events)
            total_time = sum(event['duration'] for event in events)
            avg_time = total_time / count if count > 0 else 0
            percentage = (total_time / wall_time * 100) if wall_time > 0 else 0
            
            row_data = {
                'description': description,
                'count': count,
                'total_time': total_time,
                'avg_time': avg_time,
                'percentage': percentage
            }
            
            # For type_receiver grouping, also store the receiver object
            if group_by == 'type_receiver' and description != "All Events":
                # Extract receiver from the group key
                for group_key, group_events in events_by_group.items():
                    if group_events == events:
                        if isinstance(group_key, tuple) and len(group_key) == 2:
                            receiver = group_key[1]
                            # Only store if it's not a placeholder string
                            if receiver != "<garbage collected>":
                                row_data['receiver'] = receiver
                        break
            
            row_stats.append(row_data)
        
        return row_stats
    

class ProfiledQApplication(QApplication):
    """QApplication subclass that manages multiple Qt event loop profiling sessions.
    
    This class acts as a dispatcher that sends event timing information to
    multiple active QApplicationProfile instances. This allows for targeted
    profiling over specific time periods and overlapping profile sessions.
    """
    
    def __init__(self, *args):
        super().__init__(*args)

        # Cache of receiver descriptions to avoid repeated introspection
        # {qobject: (description_str, [(parent_name, parent_type), (grandparent_name, grandparent_type), ...])}
        self.receiver_descriptions = weakref.WeakKeyDictionary()

        # Active profiles
        self._active_profiles: list[QApplicationProfile] = []
        
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
        try:
            # Get receiver description (cached) before receiver is potentially deleted
            desc, parent_chain = self.receiver_description(receiver)
        
            # Dispatch raw data to all active profiles (minimal work)
            start_time = time.perf_counter()
            try:
                return super().notify(receiver, event)
            finally:
                duration = time.perf_counter() - start_time
                rec = {
                    'event': event,
                    'receiver': weakref.ref(receiver),
                    'duration': duration,
                    'description': desc,
                    'parent_chain': parent_chain,
                    'event_type': int(event.type()),
                }
                for profile in self._active_profiles:
                    profile.record_event(rec)
                
                # Update exponential averaging for activity fraction
                self._update_activity_average(duration)

        finally:
            self._in_notify = False

    def receiver_description(self, receiver):
        """Return a description of the given receiver object
        """
        if receiver in self.receiver_descriptions:
            return self.receiver_descriptions[receiver]
        
        # string description from class/qobject name
        try:
            class_name = type(receiver).__name__
            object_name = getattr(receiver, 'objectName', lambda: '')()
            if object_name:
                desc = f"{class_name}({object_name})"
            else:
                desc = class_name
        except RuntimeError:
            # Qt object has been deleted - use generic description
            desc = f"<deleted {type(receiver).__name__}>"

        # parent chain description
        parent_chain = []
        try:
            obj = receiver
            while obj is not None:
                name = obj.objectName()
                parent_chain.append((name, type(obj)))
                obj = obj.parent()
        except RuntimeError:
            # Qt object has been deleted during traversal
            parent_chain.append(("<deleted>", type(None)))

        self.receiver_descriptions[receiver] = (desc, parent_chain)
        return self.receiver_descriptions[receiver]            
    
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