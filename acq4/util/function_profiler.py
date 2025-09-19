# ABOUTME: Python profiler that records function enter/exit times across all threads
# ABOUTME: Tracks function calls with unique IDs and provides performance analysis data

import sys
import time
import threading
from typing import List, Tuple, Dict, Optional, Any


class Profile:
    """
    Profiler that records function enter/exit times across all threads.

    Each function invocation is assigned a unique ID and records:
    [ID, parent_ID, thread_id, start_time, end_time, func_qualified_name, file, line_no]
    """

    class Counter:
        def __init__(self):
            self.value = 0
            self.lock = threading.Lock()

        def __call__(self):
            with self.lock:
                v = self.value
                self.value += 1
                return v

    def __init__(self, max_depth=None):
        # Check Python version requirement
        if sys.version_info < (3, 12):
            raise RuntimeError(
                f"Profile class requires Python 3.12+ for threading.setprofile_all_threads() support. "
                f"Current version: {sys.version_info.major}.{sys.version_info.minor}"
            )

        # Check if threading.setprofile_all_threads is available
        if not hasattr(threading, 'setprofile_all_threads'):
            raise RuntimeError(
                "threading.setprofile_all_threads() is not available. "
                "This should not happen on Python 3.12+."
            )

        self._active = False
        self._records: Dict[int, Tuple[int, Optional[int], int, float, Optional[float], str, str, int]] = {}
        self._call_stack: Dict[int, List[int]] = {}  # thread_id -> list of call IDs
        self._next_id = self.Counter()
        self._lock = threading.Lock()
        self._max_depth = max_depth
        self._profile_start_time = None
        self._profile_end_time = None

    def start(self):
        """Start profiling all function calls across all threads."""
        if self._active:
            return

        self._profile_start_time = time.perf_counter()
        self._active = True

        # Use Python 3.12+ threading.setprofile_all_threads to install profiler on all threads
        threading.setprofile_all_threads(self._profile_function)

    def stop(self):
        """Stop profiling and return collected data."""
        if self._active:
            self._profile_end_time = time.perf_counter()
            self._active = False
            threading.setprofile_all_threads(None)  # Clear profiler from all threads

            # Close any unfinished calls by assigning them the profile end time
            self._close_unfinished_calls()

        return list(self._records.values())

    def _close_unfinished_calls(self):
        """Assign end times to any calls that were still in progress when profiling stopped."""
        profile_duration = self._profile_end_time - self._profile_start_time
        for call_id, record in self._records.items():
            if record[4] is None:  # end_time is None
                # Assign the profile duration as the end time (relative to profile start)
                self._records[call_id] = list(record)
                self._records[call_id][4] = profile_duration

    def _profile_function(self, frame, event, arg):
        """Profile function for capturing function calls across all threads."""
        if not self._active:
            return

        thread_id = threading.get_ident()

        # If this is the first time we see this thread, capture the full stack
        if thread_id not in self._call_stack:
            self._capture_full_stack(frame, thread_id)

        if event == 'call':
            self._handle_call(frame, thread_id)
        elif event == 'return':
            self._handle_return(frame, thread_id)

    def _capture_full_stack(self, frame, thread_id):
        """Capture the full call stack for a thread when first encountered."""
        # Build stack from bottom to top
        stack_frames = []
        current_frame = frame
        while current_frame is not None:
            stack_frames.append(current_frame)
            current_frame = current_frame.f_back

        # Reverse to get stack from top (oldest) to bottom (newest)
        stack_frames.reverse()

        # Initialize call stack for this thread
        self._call_stack[thread_id] = []

        # Create records for each frame in the stack using existing logic
        for stack_frame in stack_frames:
            self._handle_call(stack_frame, thread_id)

    def _handle_call(self, frame, thread_id):
        """Handle function call event."""
        call_id = self._next_id()

        # Get parent ID from call stack
        self._call_stack.setdefault(thread_id, [])

        parent_id = self._call_stack[thread_id][-1] if self._call_stack[thread_id] else None
        self._call_stack[thread_id].append(call_id)

        # Only record if within depth limit
        if self._max_depth is None or len(self._call_stack[thread_id]) <= self._max_depth:
            # Get function information
            func_name = frame.f_code.co_name
            filename = frame.f_code.co_filename
            line_no = frame.f_lineno

            # Build qualified name
            if 'self' in frame.f_locals:
                class_name = frame.f_locals['self'].__class__.__name__
                func_qualified_name = f"{class_name}.{func_name}"
            else:
                func_qualified_name = func_name

            # Store time relative to profile start
            start_time = time.perf_counter() - self._profile_start_time

            # Record: [ID, parent_ID, thread_id, start_time, end_time, func_qualified_name, file, line_no]
            record = [call_id, parent_id, thread_id, start_time, None, func_qualified_name, filename, line_no]
            self._records[call_id] = record

    def _handle_return(self, frame, thread_id):
        """Handle function return event."""
        if thread_id not in self._call_stack or not self._call_stack[thread_id]:
            return

        call_id = self._call_stack[thread_id].pop()

        # Only update end time if we recorded this call
        if call_id in self._records:
            # Store time relative to profile start
            self._records[call_id][4] = time.perf_counter() - self._profile_start_time

    def get_records(self):
        """Get all recorded function call data."""
        return list(self._records.values())

    def get_events_by_thread(self):
        """Group and return events by thread ID."""
        records = list(self._records.values())
        threads = {}
        for record in records:
            thread_id = record[2]
            if thread_id not in threads:
                threads[thread_id] = []
            threads[thread_id].append(record)

        # Sort each thread's records by start time
        for thread_id in threads:
            threads[thread_id].sort(key=lambda r: r[3])  # Sort by start_time

        return threads

    def get_hierarchical_structure(self):
        """
        Get hierarchical call structure for efficient tree widget display.

        Returns:
            dict: {
                thread_id: {
                    'thread_info': thread_info_dict,
                    'root_calls': [call_id1, call_id2, ...],
                    'children': {call_id: [child_call_id1, child_call_id2, ...]},
                    'records': {call_id: record}
                }
            }
        """
        threads = self.get_events_by_thread()
        result = {}

        for thread_id, thread_records in threads.items():
            # Build children mapping for this thread
            children = {}
            records_by_id = {}
            root_calls = []

            for record in thread_records:
                call_id, parent_id, _, start_time, end_time, func_name, filename, line_no = record
                records_by_id[call_id] = record

                if parent_id is None:
                    root_calls.append(call_id)
                else:
                    if parent_id not in children:
                        children[parent_id] = []
                    children[parent_id].append(call_id)

            # Sort root calls and children by start time
            root_calls.sort(key=lambda cid: records_by_id[cid][3])
            for parent_id in children:
                children[parent_id].sort(key=lambda cid: records_by_id[cid][3])

            # Get thread name
            import threading
            thread_name = "Unknown"
            for thread in threading.enumerate():
                if thread.ident == thread_id:
                    thread_name = thread.name
                    break

            # Calculate thread start time (earliest call) and duration (profile duration)
            thread_start_time = 0  # Thread starts when profiling starts
            thread_duration = self._profile_end_time - self._profile_start_time if self._profile_end_time else 0

            result[thread_id] = {
                'thread_info': {
                    'id': thread_id,
                    'name': thread_name,
                    'call_count': len(thread_records),
                    'total_time': thread_duration,  # Full profile duration
                    'start_time': thread_start_time
                },
                'root_calls': root_calls,
                'children': children,
                'records': records_by_id
            }

        return result

    def print_events_hierarchical(self, events):
        """Print events in chronological order with hierarchical indentation."""
        if not events:
            return

        # Sort by start time
        sorted_events = sorted(events, key=lambda r: r[3])

        # Track call stack for indentation
        call_stack = []

        for record in sorted_events:
            call_id, parent_id, thread_id, start_time, end_time, func_name, filename, line_no = record

            # Calculate duration
            duration = (end_time - start_time) if end_time else 0

            # Update call stack based on parent relationship
            while call_stack and call_stack[-1] != parent_id:
                call_stack.pop()

            # Add current call to stack
            if parent_id is not None:
                if not call_stack or call_stack[-1] != parent_id:
                    call_stack.append(parent_id)
            call_stack.append(call_id)

            # Calculate indentation level
            indent_level = len(call_stack) - 1
            indent = "  " * indent_level

            # Print the call
            short_filename = filename.split('/')[-1] if '/' in filename else filename
            print(f"{indent}{func_name}() [{duration:.6f}s] ({short_filename}:{line_no})")

    def print_thread_call_structures(self):
        """Print call structure for each thread."""
        threads = self.get_events_by_thread()

        print(f"Call structures across {len(threads)} threads:\n")

        for thread_id, events in threads.items():
            # Look up thread name
            thread_name = "Unknown"
            for thread in threading.enumerate():
                if thread.ident == thread_id:
                    thread_name = thread.name
                    break

            print(f"Thread {thread_id} ({thread_name}):")
            self.print_events_hierarchical(events)
            print()

    def print_summary(self):
        """Print a summary of profiling results."""
        records = list(self._records.values())
        print(f"Total function calls: {len(records)}")
        print(f"Threads involved: {len(set(r[2] for r in records))}")

        # Calculate total times by function
        func_times = {}
        for record in records:
            if record[4] is not None:  # Has end time
                func_name = record[5]
                duration = record[4] - record[3]
                if func_name not in func_times:
                    func_times[func_name] = []
                func_times[func_name].append(duration)

        print("\nTop functions by total time:")
        sorted_funcs = sorted(func_times.items(),
                            key=lambda x: sum(x[1]), reverse=True)[:10]

        for func_name, times in sorted_funcs:
            total_time = sum(times)
            call_count = len(times)
            avg_time = total_time / call_count
            print(f"  {func_name}: {total_time:.6f}s total, {call_count} calls, {avg_time:.6f}s avg")


def start_profile(max_depth=None):
    """Start profiling and return a Profile instance."""
    profile = Profile(max_depth=max_depth)
    profile.start()
    return profile


if __name__ == "__main__":
    # Example functions to profile
    def function1():
        time.sleep(0.01)
        function2() 
        function3()

    def function2():
        time.sleep(0.02)

    def function3():
        time.sleep(0.03)
        function4()

    def function4():
        time.sleep(0.04)

    def make_worker_threads():
        thread1 = threading.Thread(target=function1)
        thread2 = threading.Thread(target=function2)
        thread1.start()
        thread2.start()
        return [thread1, thread2]

    # Start profiling with depth limit of 3
    profiler = start_profile(max_depth=None)
    
    function1()

    for thread in make_worker_threads():
        thread.join()

    profiler.stop()

    profiler.print_thread_call_structures()
    profiler.print_summary()

