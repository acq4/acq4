from __future__ import print_function
import os, sys

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


# Initialize Qt
from .util import Qt


# Import pyqtgraph, get QApplication instance
from . import pyqtgraph as pg
pg.setConfigOptions(useWeave=False)
app = pg.mkQApp()


## rename any orphaned .pyc files -- these are probably leftover from 
## a module being moved and may interfere with expected operation.
modDir = os.path.abspath(os.path.split(__file__)[0])
pg.renamePyc(modDir)


## Install a simple message handler for Qt errors:
def messageHandler(*args):
    if len(args) == 2:  # Qt4
        msgType, msg = args
    else:               # Qt5
        msgType, context, msg = args
    # ignore harmless ibus messages on linux
    if 'ibus-daemon' in msg:
        return
    import traceback
    print("Qt Error: (traceback follows)")
    print(msg)
    traceback.print_stack()
    try:
        logf = "crash.log"
            
        fh = open(logf, 'a')
        fh.write(msg+'\n')
        fh.write('\n'.join(traceback.format_stack()))
        fh.close()
    except:
        print("Failed to write crash log:")
        traceback.print_exc()
        
    
    if msgType == pg.QtCore.QtFatalMsg:
        try:
            print("Fatal error occurred; asking manager to quit.")
            global man, app
            man.quit()
            app.processEvents()
        except:
            pass

try:
    pg.QtCore.qInstallMsgHandler(messageHandler)
except AttributeError:
    pg.QtCore.qInstallMessageHandler(messageHandler)

from .Manager import getManager

