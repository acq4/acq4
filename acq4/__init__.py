import os
import sys
from .util import pg_setup

__version__ = '0.9.3'

# If we are running from a git repo, generate a more descriptive version number
from .util.gitversion import getGitVersion

try:
    gitv = getGitVersion('acq4', os.path.join(os.path.dirname(__file__), '..'))
    if gitv is not None:
        __version__ = gitv
except Exception:
    pass

# Set up a list of paths to search for configuration files
# (used if no config is explicitly specified)

# First we check the parent directory of the current module.
# This path is used when running directly from a source checkout
modpath = os.path.dirname(os.path.abspath(__file__))
CONFIGPATH = [
    os.path.normpath(os.path.join(modpath, '..', 'config')),
]

# Next check for standard system install locations
if 'linux' in sys.platform or sys.platform == 'darwin':
    CONFIGPATH.append('/etc/acq4')

# Finally, look for an example config..
CONFIGPATH.extend([
    os.path.normpath(os.path.join(modpath, '..', 'config', 'example')),
    os.path.normpath(os.path.join(modpath, 'config', 'example')),
])


from .Manager import getManager
