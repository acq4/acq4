import functools
import os
import sys
import threading
import queue
import time
import weakref


class Profile:
    def __init__(self, max_duration=None, finish_callback=None):
        # list of (timestamp, thread_id, frame, event, arg, calling_lineno, current_lineno)
        # calling_lineno is the line number of the _caller_ at the time of each event
        # current_lineno is the line number of the current frame at the time of each event
        self._events = []
        self._thread_names = {}
        self.start_time = None
        self.stop_time = None
        self._max_duration = max_duration
        self._finish_callback = finish_callback

    def start(self):
        self.start_time = time.perf_counter()
        threading.setprofile_all_threads(self.profile)

    def stop(self):
        self.stop_time = time.perf_counter()
        threading.setprofile_all_threads(None)
        if self._finish_callback:
            self._finish_callback(self)

    def profile(self, frame, event, arg):
        """Profile function called on each event. 
        Must be as inexpensive as possible.
        """
        thread_id = threading.get_ident()
        now = time.perf_counter()
        if self._max_duration is not None and (now - self.start_time) > self._max_duration:
            self.stop()
            return

        # initial setup for new threads (rare; ok to be a little more expensive)
        if thread_id not in self._thread_names:
            self._new_thread(thread_id, frame, now)

        # note: we have to store lineno explicitly because they will probably
        # change before we process the event later
        calling_lineno = frame.f_back.f_lineno if frame.f_back else None
        self._events.append((now, thread_id, frame, event, arg, calling_lineno, frame.f_lineno))

    def _new_thread(self, thread_id, frame, now):
        """Record initial stack for a new thread."""
        self._thread_names[thread_id] = threading.current_thread().name
        f = frame
        stack = []
        while f:
            stack.append(f)
            f = f.f_back
        for f in reversed(stack):
            calling_lineno = f.f_back.f_lineno if f.f_back else None
            self._events.append((now, thread_id, f, 'initial', None, calling_lineno, f.f_lineno))

    def get_events(self):
        """Return a structure detailing all events.

        Returns
        -------
            dict: {thread_id: [calls]}
        """
        # first group events by thread
        events_by_thread = {}
        for event in self._events:
            tid = event[1]
            events_by_thread.setdefault(tid, []).append(event)

        # now process each thread's events into a call tree
        result = {}
        for tid, events in events_by_thread.items():
            root_calls = []
            stack = []
            for event in events:
                if event[3] in ('call', 'initial', 'c_call'):
                    call_rec = CallRecord(event)
                    if len(stack) == 0:
                        call_rec.set_parent(None)
                        root_calls.append(call_rec)
                    else:
                        call_rec.set_parent(stack[-1])
                        stack[-1].children.append(call_rec)
                    stack.append(call_rec)

                elif event[3] in ('return', 'c_return', 'c_exception'):
                    if event[3] in ('c_return', 'c_exception') and stack[-1].event_type == 'initial':
                        # ignore unmatched C returns at the top level -- these don't appear in the initial stack
                        continue

                    while True:
                        last_call = stack.pop()  # if stack is empty here, something went wrong
                        if last_call.try_return(event):
                            break
                        else:
                            print("stack:")
                            print(last_call)
                            for c in stack:
                                print(c)
                            print("-------")
                else:
                    raise ValueError(f"Unknown event type: {event[3]}")
            # set the end time for any calls that didn't return
            end_time = self.stop_time
            for call in stack:
                call.duration = end_time - call.timestamp
            result[tid] = root_calls

        return result

    def print_call_tree(self):
        """Print the call tree for all threads."""
        events = self.get_events()
        for tid, calls in events.items():
            thread_name = self._thread_names[tid]
            print(f"Thread {thread_name} ({tid}):")
            self._print_calls(calls)
            print("")

    def _print_calls(self, calls, depth=0):
        for call in calls:
            indent_str = '|  ' * depth
            print(f'{indent_str}{str(call)}')
            self._print_calls(call.children, depth + 1)




class CallRecord:
    def __init__(self, event):
        self.timestamp, self.thread_id, self.frame, self.event_type, self.arg, self._calling_lineno, self._current_lineno = event
        self.parent = None
        self.children = []
        self.duration = None
        self.depth = None

    def set_parent(self, parent):
        self.parent = parent
        if parent is None:
            self.depth = 0
        else:
            self.depth = parent.depth + 1

    def try_return(self, event):
        """Check if the given return event matches this call record.

        If it matches, set the duration and return True.
        """
        timestamp, thread_id, frame, ev_type, arg, _, _ = event
        matched_func_return = (
            self.event_type in ('initial', 'call') and 
            ev_type == 'return' and 
            self.frame is frame
        )
        matched_c_return = (
            self.event_type == 'c_call' and 
            ev_type in ('c_return', 'c_exception') and 
            self.frame is frame and 
            self.arg == arg
        )
        if matched_func_return or matched_c_return:
            self.duration = timestamp - self.timestamp
            return True
        
        print(f"Unmatched return event:\n  {self.event_type}:{ev_type}\n  {self.frame}:{frame} {self.frame is frame}\n  {self.arg}:{arg} {self.arg is arg}")
        return False

    @property
    def funcname(self):
        """Return the name of the called function."""
        return self.frame.f_code.co_qualname
    
    @property
    def filename(self):
        """Return the filename where the called function was defined."""
        return self.frame.f_code.co_filename

    @property
    def lineno(self):
        """Return the line number where at the time of this event.
        
        For 'call' events, this is the line where the called function is _defined_.
        For 'c_call' events, this is the line where the C function was _called_."""
        return self._current_lineno

    @property
    def calling_location(self):
        """Return the location (filename, lineno) where this function was called from,
        or None if this is a top-level function.
        """
        if self.event_type == 'c_call':
            return (self.frame.f_code.co_filename, self._current_lineno)        
        if self.event_type in ('call', 'initial') and self.frame.f_back is not None:
            return (self.frame.f_back.f_code.co_filename, self._calling_lineno)
        else:
            return None

    @property
    def module(self):
        return module_from_file(self.filename)

    @property
    def display_name(self):
        """Get formatted function name, handling C functions and class methods"""
        if self.event_type == 'c_call':
            return f"C:{self.arg.__qualname__}"
        else:
            return f"{self.funcname}"

    @property
    def function_key(self):
        """Get unique function key as tuple that uniquely identifies the function"""
        if self.event_type == 'c_call':
            # For C calls, use the C function object itself as the unique identifier
            return ('c_call', self.arg.__qualname__, self.arg.__module__)
        else:
            # For Python calls, use filename, line number, and function name
            return (self.filename, self.lineno, self.display_name)

    def __str__(self):
        dur_str = f" [{self.duration*1000:.6f}ms]" if self.duration is not None else ""
        if self.event_type == 'c_call':
            func = self.arg.__name__ + " (C)"
        else:
            func = self.funcname
        return f"{func} ({self.filename}:{self.lineno}){dur_str}"


@functools.cache
def module_from_file(path):
    """Convert a filesystem path to a Python module name, if possible.

    If the path does not correspond to a module, the original path is returned.
    """
    full_path = path = os.path.realpath(os.path.abspath(path))
    if not os.path.exists(path):
        return full_path
    real_syspath = [os.path.realpath(os.path.abspath(p)) for p in sys.path]
    parts = []
    while True:        
        if os.path.isfile(path):
            path, mod_file = os.path.split(path)
            if mod_file != '__init__.py':
                parts.insert(0, os.path.splitext(mod_file)[0])
        if os.path.isdir(path):
            if path in real_syspath:
                break
            if not os.path.isfile(os.path.join(path, '__init__.py')):
                break
            parent_path, mod_dir = os.path.split(path)
            parts.insert(0, mod_dir)
            if path == parent_path:
                return full_path
            path = parent_path
    if parts:
        return '.'.join(parts)
    else:
        return full_path


class FunctionAnalysis:
    """Analysis results for a specific function across all its invocations in a profile"""

    def __init__(self, function_key, function_calls, callers, subcalls, profile_duration):
        self.function_key = function_key
        self.function_calls = function_calls  # List of CallRecord instances
        self.callers = callers  # Dict: caller_function_key -> list of CallRecord instances
        self.subcalls = subcalls  # Dict: subcall_function_key -> list of CallRecord instances
        self.profile_duration = profile_duration

        # Calculate totals
        self.total_calls = len(function_calls)
        valid_durations = [call.duration for call in function_calls if call.duration is not None]

        if valid_durations:
            self.total_duration = sum(valid_durations)
            self.avg_duration = self.total_duration / len(valid_durations)
            self.min_duration = min(valid_durations)
            self.max_duration = max(valid_durations)
        else:
            self.total_duration = self.avg_duration = self.min_duration = self.max_duration = 0

        # Calculate percentage relative to total profile time
        self.profile_percentage = (self.total_duration / profile_duration * 100) if profile_duration > 0 else 0

    def get_caller_stats(self, caller_function_key):
        """Get statistics for calls from a specific caller"""
        calls = self.callers.get(caller_function_key, [])
        return self._calculate_call_stats(calls)

    def get_subcall_stats(self, subcall_function_key):
        """Get statistics for calls to a specific subcall function"""
        calls = self.subcalls.get(subcall_function_key, [])
        return self._calculate_call_stats(calls)

    def get_caller_percentage(self, caller_function_key):
        """Get percentage of caller's total time spent calling this function"""
        calls = self.callers.get(caller_function_key, [])
        if not calls:
            return 0.0

        # Calculate total time spent in this function when called by this caller
        total_time_in_function = sum(call.duration for call in calls if call.duration is not None)

        # Get total time of the caller across all its invocations
        caller_analysis = self._get_caller_total_time(caller_function_key)
        if not caller_analysis or caller_analysis == 0:
            return 0.0

        return (total_time_in_function / caller_analysis) * 100

    def get_subcall_percentage(self, subcall_function_key):
        """Get percentage of this function's time spent in subcall"""
        calls = self.subcalls.get(subcall_function_key, [])
        if not calls:
            return 0.0

        subcall_total_time = sum(call.duration for call in calls if call.duration is not None)
        if self.total_duration == 0:
            return 0.0

        return (subcall_total_time / self.total_duration) * 100

    def get_parent_relative_percentage(self, parent_duration):
        """Get percentage relative to a specific parent duration (for tree display)"""
        if parent_duration == 0 or self.total_duration == 0:
            return 0.0
        return (self.total_duration / parent_duration) * 100

    def get_callers_with_percentages(self):
        """Get all callers with statistics and percentages"""
        result = {}
        for caller_key, calls in self.callers.items():
            stats = self._calculate_call_stats(calls)
            if stats:
                percentage = self.get_caller_percentage(caller_key)
                stats['percentage'] = percentage
                result[caller_key] = stats
        return result

    def get_subcalls_with_percentages(self):
        """Get all subcalls with statistics and percentages"""
        result = {}
        for subcall_key, calls in self.subcalls.items():
            stats = self._calculate_call_stats(calls)
            if stats:
                percentage = self.get_subcall_percentage(subcall_key)
                stats['percentage'] = percentage
                result[subcall_key] = stats
        return result

    def _get_caller_total_time(self, caller_function_key):
        """Get total time spent in caller function across all its invocations

        This requires access to the ProfileAnalyzer to get caller's total time.
        For now, we'll calculate it from the calls we have.
        """
        # This is a simplified approach - in a full implementation,
        # we'd want the ProfileAnalyzer to provide this information
        calls = self.callers.get(caller_function_key, [])
        if not calls:
            return 0.0

        # Get the parent duration from one of the calls (they should all have same parent)
        sample_call = calls[0]
        if hasattr(sample_call, 'parent') and sample_call.parent and sample_call.parent.duration:
            return sample_call.parent.duration
        return 0.0

    def _calculate_call_stats(self, calls):
        """Calculate statistics for a list of calls"""
        if not calls:
            return None

        valid_durations = [call.duration for call in calls if call.duration is not None]
        if not valid_durations:
            return None

        return {
            'n_calls': len(valid_durations),
            'total_duration': sum(valid_durations),
            'avg_duration': sum(valid_durations) / len(valid_durations),
            'min_duration': min(valid_durations),
            'max_duration': max(valid_durations)
        }


class TreeDisplayData:
    """Pre-calculated display data for UI tree items"""

    def __init__(self, call_record, parent_duration=None, profile_start_time=0):
        self.call_record = call_record
        self.function_name = call_record.display_name
        self.module = call_record.module
        self.location = self._get_location()

        # Calculate values
        self.duration_seconds = call_record.duration if call_record.duration else 0
        self.duration_ms = self.duration_seconds * 1000
        self.start_time_relative = (call_record.timestamp - profile_start_time) * 1000

        # Calculate parent-relative percentage
        if parent_duration and parent_duration > 0 and self.duration_seconds > 0:
            self.parent_percentage = (self.duration_seconds / parent_duration) * 100
        else:
            self.parent_percentage = 0.0

        # Formatted strings for display
        self.duration_text = self._format_duration(self.duration_seconds)
        self.start_time_text = f"{self.start_time_relative:.3f}"
        self.percentage_text = f"{self.parent_percentage:.1f}" if self.parent_percentage > 0 else "—"

        # Children display data (will be populated by ProfileAnalyzer)
        self.children_display_data = []

    def _get_location(self):
        """Get formatted location string"""
        calling_location = self.call_record.calling_location
        if calling_location:
            filename, lineno = calling_location
            return f"{filename}:{lineno}"
        else:
            # Top-level function - show function definition location as fallback
            return f"{self.call_record.filename}:{self.call_record.frame.f_code.co_firstlineno}"

    def _format_duration(self, duration_seconds):
        """Format duration in seconds to milliseconds text"""
        if duration_seconds is not None and duration_seconds > 0:
            return f"{duration_seconds * 1000:.3f}"
        else:
            return "—"


class ThreadDisplayData:
    """Pre-calculated display data for thread tree items"""

    def __init__(self, thread_id, thread_name, root_calls, profile_duration, profile_start_time):
        self.thread_id = thread_id
        self.thread_name = thread_name
        self.root_calls = root_calls
        self.profile_start_time = profile_start_time

        # Calculate thread totals
        self.total_duration = profile_duration
        self.total_duration_ms = self.total_duration * 1000

        # Formatted strings
        self.display_name = f"{thread_name} ({thread_id})"
        self.duration_text = f"{self.total_duration * 1000:.3f}"
        self.start_time_text = "0.000"  # Threads start at beginning
        self.percentage_text = "—"  # Threads have no parent

        # Call display data (will be populated by ProfileAnalyzer)
        self.call_display_data = []


class ProfileAnalyzer:
    """Analyzes profile results to extract function statistics and relationships"""

    def __init__(self, profile_events, profile_duration):
        """
        Args:
            profile_events: Dict from Profile.get_events() - {thread_id: [root_calls]}
            profile_duration: Total profile duration in seconds
        """
        self.profile_events = profile_events
        self.profile_duration = profile_duration
        self._function_lookup = None

    def build_function_lookup(self):
        """Build lookup table of all function calls, callers, and subcalls"""
        if self._function_lookup is not None:
            return self._function_lookup

        function_lookup = {}

        def process_call(call, parent_call=None):
            """Recursively process calls to build function lookup"""
            function_key = call.function_key

            # Initialize function entry if not exists
            if function_key not in function_lookup:
                function_lookup[function_key] = {
                    'calls': [],
                    'callers': {},  # caller_key -> [calls]
                    'subcalls': {}  # subcall_key -> [calls]
                }

            # Add this call to the function's call list
            function_lookup[function_key]['calls'].append(call)

            # Record caller relationship
            if parent_call is not None:
                parent_key = parent_call.function_key
                callers = function_lookup[function_key]['callers']
                if parent_key not in callers:
                    callers[parent_key] = []
                callers[parent_key].append(call)

                # Record subcall relationship on parent
                parent_subcalls = function_lookup[parent_key]['subcalls']
                if function_key not in parent_subcalls:
                    parent_subcalls[function_key] = []
                parent_subcalls[function_key].append(call)

            # Process children
            for child_call in call.children:
                process_call(child_call, call)

        # Process all threads and root calls
        for thread_id, root_calls in self.profile_events.items():
            for root_call in root_calls:
                process_call(root_call)

        self._function_lookup = function_lookup
        return function_lookup

    def analyze_function(self, call_record):
        """Analyze a specific function across all its invocations

        Args:
            call_record: A CallRecord instance to identify the function

        Returns:
            FunctionAnalysis instance with complete statistics
        """
        function_lookup = self.build_function_lookup()
        function_key = call_record.function_key

        function_data = function_lookup.get(function_key)
        if not function_data:
            return None

        return FunctionAnalysis(
            function_key=function_key,
            function_calls=function_data['calls'],
            callers=function_data['callers'],
            subcalls=function_data['subcalls'],
            profile_duration=self.profile_duration
        )

    def get_tree_display_data(self, profile_start_time):
        """Get pre-calculated display data for the entire call tree

        Args:
            profile_start_time: Start time of the profile for relative time calculations

        Returns:
            Dict mapping thread_id to ThreadDisplayData with nested TreeDisplayData
        """
        result = {}

        for thread_id, root_calls in self.profile_events.items():
            # Get thread name (stored in CallRecord or use default)
            thread_name = "MainThread"  # Default
            if root_calls:
                thread_name = getattr(root_calls[0], '_thread_name', f"Thread-{thread_id}")

            # Create thread display data
            thread_data = ThreadDisplayData(
                thread_id=thread_id,
                thread_name=thread_name,
                root_calls=root_calls,
                profile_duration=self.profile_duration,
                profile_start_time=profile_start_time
            )

            # Add tree display data for each call in this thread
            thread_data.call_display_data = []
            for root_call in root_calls:
                call_data = self._build_call_display_tree(root_call, self.profile_duration, profile_start_time)
                thread_data.call_display_data.append(call_data)

            result[thread_id] = thread_data

        return result

    def _build_call_display_tree(self, call_record, parent_duration, profile_start_time):
        """Recursively build TreeDisplayData for a call and its children

        Args:
            call_record: CallRecord to build display data for
            parent_duration: Duration of parent call for percentage calculation
            profile_start_time: Profile start time for relative time calculation

        Returns:
            TreeDisplayData with nested children_display_data
        """
        # Create display data for this call
        display_data = TreeDisplayData(
            call_record=call_record,
            parent_duration=parent_duration,
            profile_start_time=profile_start_time
        )

        # Build display data for children
        display_data.children_display_data = []
        if call_record.children:
            call_duration = call_record.duration if call_record.duration else 0
            for child_call in call_record.children:
                child_data = self._build_call_display_tree(child_call, call_duration, profile_start_time)
                display_data.children_display_data.append(child_data)

        return display_data


if __name__ == '__main__':
    q = queue.Queue()

    def raise_exc():
        raise ValueError("Test exception")

    prof = Profile()
    prof.start()

    t = threading.Thread(target=lambda: q.get(timeout=0.5), name="TestThread")
    t.start()

    q.put(42)
    t.join()


    try:
        q.get(timeout=0.5)
    except queue.Empty:
        pass

    try:
        raise_exc()
    except:
        pass

    prof.stop()

    prof.print_call_tree()
