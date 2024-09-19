import sys

if sys.version_info[0] >= 3:
    buffer = memoryview
else:
    
    buffer = builtins.buffer
