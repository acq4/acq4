from __future__ import print_function
import os, sys

def pycRename(startDir):
    printed = False
    startDir = os.path.abspath(startDir)
    for path, dirs, files in os.walk(startDir):
        for f in files:
            fileName = os.path.join(path, f)
            base, ext = os.path.splitext(fileName)
            py = base + ".py"
            if ext == '.pyc' and not os.path.isfile(py):
                if not printed:
                    print("NOTE: Renaming orphaned .pyc files:")
                    printed = True
                n = 1
                while True:
                    name2 = fileName + ".renamed%d" % n
                    if not os.path.exists(name2):
                        break
                    n += 1
                print("  " + fileName + "  ==>")
                print("  " + name2)
                os.rename(fileName, name2)