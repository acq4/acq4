from __future__ import print_function

import importlib
import os
import sys

walk_dir = "acq4"
file_count = 0
fail_count = 0

for folder, subs, filenames in os.walk(walk_dir):
    import_path = folder.replace(os.path.sep, ".")
    if folder == "acq4" or "pyqtgraph" in folder:
        continue
    for filename in filenames:
        if filename[-2:] != 'py':
            continue
        if filename in ["__main__.py"]:
            continue
        elif filename == "__init__.py":
            file_path = import_path
        else:
            file_path = '.'.join([import_path, filename[:-3]])
        try:
            print("attempting to import", file_path)
            importlib.import_module(file_path)
        except:
            # import ipdb; ipdb.set_trace()
            fail_count += 1
            print(filename, "failed to import {} : {}".format(file_path, sys.exc_info()[1]))
            sys.excepthook(*sys.exc_info())
        else:
            file_count += 1

print(file_count, "good files found")
print(fail_count, "bad files found (search logs for 'failed to import ' to see which)")
