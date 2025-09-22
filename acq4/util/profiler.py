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
