# Helper module imported by the remote teleprox process in test_teleprox_context.py.
# Simulates a queue-worker that captures task_stack at enqueue time (the SmartStage pattern).
import logging
import queue
import threading

from acq4.util.future import task_stack

_queue = queue.Queue()
_thread = None


def start():
    global _thread
    _thread = threading.Thread(target=_worker, daemon=True)
    _thread.start()


def enqueue(msg):
    """Called from RPC; captures the propagated task_stack as caller_stack."""
    _queue.put((task_stack.get(), msg))


def _worker():
    while True:
        item = _queue.get()
        if item is None:
            break
        caller_stack, msg = item
        with task_stack.push_full(caller_stack):
            logging.getLogger('acq4').warning(msg)
