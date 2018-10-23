from __future__ import print_function
import re, os, sys

version = sys.argv[1]

replace = [
    ("acq4/__init__.py", r"__version__ = .*", "__version__ = '%s'" % version),
    #("setup.py", r"    version=.*,", "    version='%s'," % version),  # setup.py automatically detects version
    ("documentation/source/conf.py", r"version = .*", "version = '%s'" % version),
    ("documentation/source/conf.py", r"release = .*", "release = '%s'" % version),
    #("tools/debian/control", r"^Version: .*", "Version: %s" % version),
    ("tools/innosetup.iss", r'#define AppVersion .*', '#define AppVersion "%s"' % version),
    ]

path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')

for filename, search, sub in replace:
    filename = os.path.join(path, filename)
    if not os.path.isfile(filename):
        print("skipping: %s; does not exist" % filename)
        continue
    data = open(filename, 'r').read()
    if re.search(search, data) is None:
        print('Error: Search expression "%s" not found in file %s.' % (search, filename))
        os._exit(1)
    open(filename, 'w').write(re.sub(search, sub, data))
    
print("Updated version strings to %s" % version)



