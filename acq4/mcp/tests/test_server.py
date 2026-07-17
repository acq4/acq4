"""Tests for acq4.mcp.server's pure helpers.

Importing this module must not require the optional `mcp` SDK; the SDK import is
deferred into build_server(). These tests cover the result formatter only -- the thin
FastMCP tool wiring is verified live against a running ACQ4.
"""

from acq4.mcp.server import _format_execute


def test_format_includes_result_repr():
    text = _format_execute(
        {"stdout": "", "stderr": "", "result": "42", "traceback": None}
    )
    assert "42" in text


def test_format_includes_stdout():
    text = _format_execute(
        {"stdout": "hello\n", "stderr": "", "result": None, "traceback": None}
    )
    assert "hello" in text


def test_format_includes_stderr():
    text = _format_execute(
        {"stdout": "", "stderr": "a warning\n", "result": None, "traceback": None}
    )
    assert "a warning" in text


def test_format_includes_traceback():
    text = _format_execute(
        {"stdout": "", "stderr": "", "result": None, "traceback": "ValueError: boom"}
    )
    assert "ValueError: boom" in text


def test_format_empty_result_reports_no_output():
    text = _format_execute(
        {"stdout": "", "stderr": "", "result": None, "traceback": None}
    )
    assert "no output" in text.lower()
