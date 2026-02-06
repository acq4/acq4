#!/usr/bin/env python3
"""
binreplace_tree.py: recursively replace a byte sequence in all regular files under PATH.

Usage:
  python3 binreplace_tree.py PATH SEARCH REPLACE

- SEARCH/REPLACE are taken as UTF-8 text and converted to bytes.
- Binary-safe: files are opened in 'rb'/'wb' and processed as bytes.
- Rewrites a file only if it actually changes (to avoid touching mtimes unnecessarily).
"""

from __future__ import annotations

import os
import sys
import tempfile


def iter_files(root: str):
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        for name in filenames:
            yield os.path.join(dirpath, name)


def atomic_write_replace(original_path: str, new_bytes: bytes, st: os.stat_result) -> None:
    d = os.path.dirname(original_path) or "."
    base = os.path.basename(original_path)
    fd, tmp_path = tempfile.mkstemp(prefix=f".{base}.", suffix=".tmp", dir=d)
    try:
        with os.fdopen(fd, "wb") as dst:
            dst.write(new_bytes)
        os.chmod(tmp_path, st.st_mode)
        os.replace(tmp_path, original_path)  # atomic replace (same filesystem)
    except Exception:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
        raise


def replace_in_file(path: str, needle: bytes, repl: bytes) -> bool:
    try:
        st = os.lstat(path)
        if not os.path.isfile(path):
            return False

        with open(path, "rb") as f:
            data = f.read()

        new_data = data.replace(needle, repl)
        if new_data == data:
            return False

        atomic_write_replace(path, new_data, st)
        return True

    except (FileNotFoundError, PermissionError, IsADirectoryError):
        return False


import argparse

parser = argparse.ArgumentParser(description="Rename a conda environment by replacing all occurrences of old_name with new_name in the environment's files. Also removes all .pyc files.")
parser.add_argument("env_path", help="Path to the conda environment")
parser.add_argument("old_name", help="Old environment name to replace")
parser.add_argument("new_name", help="New environment name to use")
args = parser.parse_args()

root = args.env_path
needle = args.old_name.encode("utf-8")
repl = args.new_name.encode("utf-8")

if len(repl) != len(needle):
    print("Error: old_name and new_name must have the same length", file=sys.stderr)
    sys.exit(1)

scanned = 0
modified = []
errors = []
removed = []

all_files = list(iter_files(root))
for i,f in enumerate(all_files):
    scanned += 1
    try:
        if f.endswith(".pyc"):
            try:
                os.remove(f)
                removed.append(f)
            except Exception as e:
                errors.append(f)
                print(f"Error removing {f}: {e}", file=sys.stderr)
            continue
        if replace_in_file(f, needle, repl):                
            modified.append(f)
    except Exception as e:
        errors.append(f)
        print(f"Error processing {f}: {e}", file=sys.stderr)
    if i % 100 == 0:
        print(f"Processed {i+1}/{len(all_files)} files")

if modified:
    print(f"Modified files:")
    for f in modified:
        print(f"  {f}")

if errors:
    print(f"Files with errors:")
    for f in errors:
        print(f"  {f}")

print(f"Scanned: {scanned}  Modified: {len(modified)}  Removed pyc files: {len(removed)}  Errors: {len(errors)}")
if errors:
    sys.exit(1)
else:
    sys.exit(0)
