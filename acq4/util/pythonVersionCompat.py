import sys

if sys.version_info[0] >= 3:
    buffer = memoryview
else:
    from six.moves import builtins
    buffer = builtins.buffer
