#!/usr/bin/env python
"""Test script for daemon functionality - runs for a specified time and logs to a file."""

import argparse
import time
import os
from datetime import datetime


def main():
    parser = argparse.ArgumentParser(description='Test daemon script that runs for a specified duration')
    parser.add_argument('--duration', type=int, default=10, help='Duration to run in seconds')
    parser.add_argument('--output', type=str, default='/tmp/claude/daemon_test.log', help='Output log file')
    parser.add_argument('--message', type=str, default='Test daemon', help='Message to log')

    args = parser.parse_args()

    # Ensure output directory exists
    os.makedirs(os.path.dirname(args.output), exist_ok=True)

    # Log start
    with open(args.output, 'a') as f:
        f.write(f"[{datetime.now()}] {args.message} started, running for {args.duration} seconds\n")
        f.flush()

    # Run for specified duration, logging every second
    for i in range(args.duration):
        time.sleep(1)
        with open(args.output, 'a') as f:
            f.write(f"[{datetime.now()}] {args.message} - tick {i+1}/{args.duration}\n")
            f.flush()

    # Log completion
    with open(args.output, 'a') as f:
        f.write(f"[{datetime.now()}] {args.message} completed\n")
        f.flush()


if __name__ == '__main__':
    main()