"""Tests for set_log_file migration behavior in acq4.logging_config."""
import logging
import os

import pytest

import acq4.logging_config as lc


@pytest.fixture
def clean_log_handler():
    """Save and restore the module-level file handler so tests don't pollute the root logger."""
    saved = lc.log_file_handler
    lc.log_file_handler = None
    yield
    root_logger = logging.getLogger()
    if lc.log_file_handler is not None:
        root_logger.removeHandler(lc.log_file_handler)
        lc.log_file_handler.close()
    lc.log_file_handler = saved


def test_temp_log_deleted_after_migration(tmp_path, clean_log_handler):
    """Switching away from a temp log copies its contents to the new file and deletes the temp file."""
    temp_log = tmp_path / "temp_log.json"
    new_log = tmp_path / "subdir" / "log.json"
    new_log.parent.mkdir()

    # establish a temporary log file and write a record into it
    lc.set_log_file(str(temp_log), is_temp_file=True)
    logging.getLogger("acq4").error("hello from temp")
    assert temp_log.exists()
    temp_contents = temp_log.read_bytes()
    assert b"hello from temp" in temp_contents

    # switch to the requested log directory
    lc.set_log_file(str(new_log))

    # the temp file is gone and its records were migrated
    assert not temp_log.exists()
    assert new_log.exists()
    assert b"hello from temp" in new_log.read_bytes()


def test_non_temp_log_not_deleted(tmp_path, clean_log_handler):
    """A non-temporary log file is left in place when the log file is changed."""
    first_log = tmp_path / "log.json"
    second_log = tmp_path / "log2.json"

    lc.set_log_file(str(first_log), is_temp_file=False)
    logging.getLogger("acq4").error("persistent record")
    assert first_log.exists()

    lc.set_log_file(str(second_log))

    # the original (non-temp) file is preserved and not migrated
    assert first_log.exists()
    assert second_log.exists()
    assert b"persistent record" not in second_log.read_bytes()
