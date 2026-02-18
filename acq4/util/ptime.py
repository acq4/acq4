"""
Defines a high-resolution time() function that works across platforms.

- Like time.time(), but high resolution even on windows
- Like ptime.time(), but returns unix timestamp

"""

import sys
from time import perf_counter as clock
from time import time as system_time

START_TIME = None
time = None


def winTime():
    """Return the current time in seconds with high precision (windows version, use ptime.time() to stay platform independent)."""
    return clock() + START_TIME


def unixTime():
    """Return the current time in seconds with high precision (unix version, use ptime.time() to stay platform independent)."""
    return system_time()


if sys.platform.startswith("win"):
    cstart = clock()  ### Required to start the clock in windows
    START_TIME = system_time() - cstart

    time = winTime
else:
    time = unixTime


def loop(duration=None, end_time=None):
    """Generator that yields the current time in a loop until the specified duration has elapsed or
    end_time is reached."""
    if duration is None and end_time is None:
        raise ValueError("Must specify either duration or end_time")
    if end_time is None:
        end_time = time() + duration
    while (now := time()) < end_time:
        yield now
