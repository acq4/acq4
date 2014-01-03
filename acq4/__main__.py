# -*- coding: utf-8 -*-
"""
Main ACQ4 invocation script
Copyright 2010  Luke Campagnola
Distributed under MIT/X11 license. See license.txt for more infomation.
"""

print("Loading ACQ4...")

from .pyqtgraph.Qt import QtGui, QtCore

from .Manager import *
from numpy import *

## Initialize Qt
app = pg.mkQApp()


## Create Manager. This configures devices and creates the main manager window.
man = Manager(argv=sys.argv[1:])

# If example config was loaded, offer more help to the user.
message = """\
<center><b>Demo mode:</b><br>\
ACQ4 is running from an example configuration file at:<br><pre>%s</pre><br>\
This configuration defines several simulated devices that allow you to test the capabilities of ACQ4.<br>\
See the <a href="http://acq4.org/documentation/userGuide/configuration.html">ACQ4 documentation</a> \
for more information.</center>
""" % man.configFile
if man.configFile.endswith(os.path.join('example', 'default.cfg')):
    mbox = QtGui.QMessageBox()
    mbox.setText(message)
    mbox.setStandardButtons(mbox.Ok)
    mbox.exec_()


## for debugging with pdb
#QtCore.pyqtRemoveInputHook()

## Start Qt event loop unless running in interactive mode.
interactive = (sys.flags.interactive == 1) and not pyqtgraph.Qt.USE_PYSIDE

## Run python code periodically to allow interactive debuggers to interrupt the qt event loop
timer = QtCore.QTimer()
def donothing(*args):
    #print "-- beat --"
    x = 0
    for i in range(0, 100):
        x += i
timer.timeout.connect(donothing)
timer.start(1000)


if interactive:
    print "Interactive mode; not starting event loop."
    
    ## import some things useful on the command line
    from .util.debug import *
    from . import pyqtgraph as pg
    from .util import functions as fn
    import numpy as np

    ### Use CLI history and tab completion
    import atexit
    import os
    historyPath = os.path.expanduser("~/.pyhistory")
    try:
        import readline
    except ImportError:
        print "Module readline not available."
    else:
        import rlcompleter
        readline.parse_and_bind("tab: complete")
        if os.path.exists(historyPath):
            readline.read_history_file(historyPath)
    def save_history(historyPath=historyPath):
        try:
            import readline
        except ImportError:
            print "Module readline not available."
        else:
            readline.write_history_file(historyPath)
    atexit.register(save_history)
else:
    app.exec_()
    pg.exit() ## force exit without garbage collection
    
    
