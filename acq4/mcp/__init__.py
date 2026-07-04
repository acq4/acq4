"""MCP integration for ACQ4: execute code and inspect a running instance over teleprox.

This package must import cleanly on every ACQ4 install; the optional `mcp` SDK is
only imported by `acq4.mcp.server` (the stdio MCP process), never at package import.
"""
