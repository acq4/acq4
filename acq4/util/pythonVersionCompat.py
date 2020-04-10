import sys

if sys.version_info[0] >= 3:
    buffer = memoryview
else:
    import __builtin__
    buffer = __builtin__.buffer
