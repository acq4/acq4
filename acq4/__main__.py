# -*- coding: utf-8 -*-
from __future__ import print_function
"""
Main ACQ4 invocation script
Copyright 2010  Luke Campagnola
Distributed under MIT/X11 license. See license.txt for more infomation.
"""

print("Loading ACQ4...")
import os, sys
if __package__ is None:
    import acq4
    __package__ = 'acq4'

from .util import Qt
from .Manager import Manager
from .util.debug import installExceptionHandler


# Pull some args out
if "--profile" in sys.argv:
    profile = True
    sys.argv.pop(sys.argv.index('--profile'))
else:
    profile = False
if "--callgraph" in sys.argv:
    callgraph = True
    sys.argv.pop(sys.argv.index('--callgraph'))
else:
    callgraph = False


## Enable stack trace output when a crash is detected
from .util.debug import enableFaulthandler
enableFaulthandler()


## Prevent Windows 7 from grouping ACQ4 windows under a single generic python icon in the taskbar
if sys.platform == 'win32':
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('ACQ4')


# Enable exception handling
installExceptionHandler()


## Initialize Qt
app = Qt.pg.mkQApp()


## Disable garbage collector to improve stability. 
## (see pyqtgraph.util.garbage_collector for more information)
from acq4.pyqtgraph.util.garbage_collector import GarbageCollector
gc = GarbageCollector(interval=1.0, debug=False)

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
    mbox = Qt.QMessageBox()
    mbox.setText(message)
    mbox.setStandardButtons(mbox.Ok)
    mbox.exec_()


## Run python code periodically to allow interactive debuggers to interrupt the qt event loop
timer = Qt.QTimer()
def donothing(*args):
    #print "-- beat --"
    x = 0
    for i in range(0, 100):
        x += i
timer.timeout.connect(donothing)
timer.start(1000)


## Start Qt event loop unless running in interactive mode.
from . import pyqtgraph as pg
interactive = (sys.flags.interactive == 1) and not pg.Qt.USE_PYSIDE
if interactive:
    print("Interactive mode; not starting event loop.")
    
    ## import some things useful on the command line
    from .util.debug import *
    from .util import functions as fn
    import numpy as np

    ### Use CLI history and tab completion
    import atexit
    import os
    historyPath = os.path.expanduser("~/.pyhistory")
    try:
        import readline
    except ImportError:
        print("Module readline not available.")
    else:
        import rlcompleter
        readline.parse_and_bind("tab: complete")
        if os.path.exists(historyPath):
            readline.read_history_file(historyPath)
    def save_history(historyPath=historyPath):
        try:
            import readline
        except ImportError:
            print("Module readline not available.")
        else:
            readline.write_history_file(historyPath)
    atexit.register(save_history)
else:
    if profile:
        import cProfile
        cProfile.run('app.exec_()', sort='cumulative')    
        pg.exit()  # pg.exit() causes python to exit before Qt has a chance to clean up. 
                   # this avoids otherwise irritating exit crashes.
    elif callgraph:
        from pycallgraph import PyCallGraph
        from pycallgraph.output import GraphvizOutput
        with PyCallGraph(output=GraphvizOutput()):
            app.exec_()
    else:
        app.exec_()
        pg.exit()  # pg.exit() causes python to exit before Qt has a chance to clean up. 
                   # this avoids otherwise irritating exit crashes.
