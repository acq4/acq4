import os
import sys
from typing import TYPE_CHECKING

__version__ = '0.10.41'

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


if TYPE_CHECKING:
    from .Manager import Manager


def getManager() -> "Manager":
    """Return the currently running Manager instance.

    ``acq4.Manager`` is imported lazily here so that ``import acq4`` stays cheap;
    importing the manager drags in Qt, the device package, and much of the rest
    of acq4.
    """
    from .Manager import getManager as _getManager
    return _getManager()
