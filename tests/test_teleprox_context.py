# End-to-end tests for task_stack propagation across teleprox remote processes.
# Verifies that log records emitted in a remote process carry the caller's task context.
import logging
import sys
import time

import pytest

from acq4.util.future import task_stack, setup_teleprox_context_propagation


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _start_acq4_child(name, log_addr):
    """Start a teleprox child process with the acq4 path and log forwarding."""
    import teleprox
    # Use WARNING level so teleprox internal debug logs don't pollute the recorder.
    proc = teleprox.start_process(name=name, log_addr=log_addr, log_level=logging.WARNING)
    proc.client._import('sys').path.insert(0, sys.path[0])
    # Set up context propagation in the remote process
    proc.client._import('acq4.util.future').setup_teleprox_context_propagation()
    return proc


def _find_app_record(recorder, msg):
    """Return the first record whose msg is exactly *msg* (not a substring of a debug trace)."""
    return recorder.find_message(f'^{msg}$')


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_task_stack_in_remote_log_records():
    """Log records from a remote process carry the caller's task_stack."""
    import teleprox
    from teleprox.tests.util import RemoteLogRecorder

    with RemoteLogRecorder('test_remote_task_stack') as recorder:
        proc = _start_acq4_child('test_child', recorder.address)
        try:
            remote_logging = proc.client._import('logging')

            with task_stack.push('Approach'):
                with task_stack.push('moveToGlobal'):
                    remote_logging.getLogger('acq4').warning('remote_msg_in_context')

            remote_logging.getLogger('acq4').warning('remote_msg_no_context')
        finally:
            proc.stop()

    rec_with = _find_app_record(recorder, 'remote_msg_in_context')
    rec_without = _find_app_record(recorder, 'remote_msg_no_context')

    assert rec_with is not None, "message with context not received"
    assert rec_without is not None, "message without context not received"

    assert getattr(rec_with, 'task_stack', None) == 'Approach > moveToGlobal'
    assert getattr(rec_without, 'task_stack', None) == ''


def test_remote_queue_worker_captures_propagated_stack():
    """A queue-worker pattern captures the propagated task_stack from the RPC caller."""
    import teleprox
    from teleprox.tests.util import RemoteLogRecorder

    with RemoteLogRecorder('test_remote_queue_worker') as recorder:
        proc = _start_acq4_child('test_queue_child', recorder.address)
        try:
            # Install a simple queue-worker module in the remote process.
            proc.client._import('sys').path.insert(0, sys.path[0])
            remote_worker = proc.client._import('tests.teleprox_queue_worker_helper')
            remote_worker.start()

            with task_stack.push('PatchPipette'):
                with task_stack.push('approach'):
                    # The worker captures task_stack.get() inside the RPC call,
                    # which has been set to ('PatchPipette', 'approach') by the hook.
                    remote_worker.enqueue('queued_work_msg')
        finally:
            time.sleep(0.4)
            proc.stop()

    rec = _find_app_record(recorder, 'queued_work_msg')
    assert rec is not None, "queued message not received"
    assert getattr(rec, 'task_stack', '') == 'PatchPipette > approach'


def test_main_process_log_records_have_task_stack(tmp_path):
    """Log records written to the JSON log file by the main process include task_stack."""
    import json
    from acq4.logging_config import setup_logging

    log_file = str(tmp_path / 'test.log')
    setup_logging(log_file, gui=False)

    logger = logging.getLogger('acq4.test_task_stack_field')
    with task_stack.push('TestOp'):
        logger.warning('main_process_in_context')
    logger.warning('main_process_no_context')

    records = []
    with open(log_file) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    in_ctx = next((r for r in records if 'main_process_in_context' in r.get('message', '') + r.get('msg', '')), None)
    no_ctx = next((r for r in records if 'main_process_no_context' in r.get('message', '') + r.get('msg', '')), None)

    assert in_ctx is not None
    assert no_ctx is not None
    assert in_ctx.get('task_stack') == 'TestOp'
    assert no_ctx.get('task_stack') == ''
