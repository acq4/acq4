"""
Main ACQ4 invocation script
"""
print("Loading ACQ4...")
import os
import sys

if __package__ is None:
    import acq4  # noqa: F401

    __package__ = 'acq4'

from .util import pg_setup  # noqa: F401
from .Manager import Manager
from .util.debug import installExceptionHandler

control_arg_parser = Manager.makeArgParser()
control_arg_parser.add_argument("-profile", action="store_true", help="Run the program under the profiler")
control_arg_parser.add_argument("--callgraph", action="store_true", help="Run the program under the callgraph profiler")
control_arg_parser.add_argument("--threadtrace", action="store_true", help="Run a thread tracer in the background")
control_arg_parser.add_argument("--qt-profile", action="store_true", help="Use ProfiledQApplication to collect Qt event loop performance statistics")
# teleprox optional port number
control_arg_parser.add_argument("--teleprox", type=int, nargs='?', const=0, default=None,
                                help="Run a teleprox server in the background. If no port number is specified, a random port will be used.")
args = control_arg_parser.parse_args()

## Enable stack trace output when a crash is detected
from .util.debug import enableFaulthandler

enableFaulthandler()


# Initialize Qt
from .util import Qt

# Import pyqtgraph, get QApplication instance
import pyqtgraph as pg
if args.threadtrace:
    tt = pg.debug.ThreadTrace()

# Create QApplication - use ProfiledQApplication if --qt-profile flag is set
if args.qt_profile:
    from .util.profiled_qapp import ProfiledQApplication
    app = ProfiledQApplication(sys.argv)
    print("Qt profiling enabled. Use app.print_summary_report() to view statistics.")
else:
    app = pg.mkQApp()

if args.teleprox is not None:    
    from teleprox import RPCServer
    if args.teleprox == 0:
        addr = 'tcp://127.0.0.1:*'
    else:
        addr = f'tcp://127.0.0.1:{args.teleprox}'
    teleprox_debug_server = RPCServer(addr)
    teleprox_debug_server.run_in_thread()
    print(f"Teleprox server listening on {teleprox_debug_server.address}")

app = pg.mkQApp()


## Install a simple message handler for Qt errors:
def messageHandler(*args):
    if len(args) == 2:  # Qt4
        msgType, msg = args
    else:  # Qt5
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

        with open(logf, 'a') as fh:
            fh.write(msg + '\n')
            fh.write('\n'.join(traceback.format_stack()))
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


## Prevent Windows 7 from grouping ACQ4 windows under a single generic python icon in the taskbar
if sys.platform == 'win32':
    import ctypes

    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('ACQ4')

# Enable exception handling
installExceptionHandler()


## Disable garbage collector to improve stability.
## (see pyqtgraph.util.garbage_collector for more information)
from pyqtgraph.util.garbage_collector import GarbageCollector

gc = GarbageCollector(interval=1.0, debug=False)

## Create Manager. This configures devices and creates the main manager window.
man = Manager.runFromCommandLine(args)

# If example config was loaded, offer more help to the user.
message = f"""\
<center><b>Demo mode:</b><br>\
ACQ4 is running from an example configuration file at:<br><pre>{man.configFile}</pre><br>\
This configuration defines several simulated devices that allow you to test the capabilities of ACQ4.<br>\
See the <a href="http://acq4.org/documentation/userGuide/configuration.html">ACQ4 documentation</a> \
for more information.</center>
"""
if man.configFile.endswith(os.path.join('example', 'default.cfg')):
    mbox = Qt.QMessageBox()
    mbox.setText(message)
    mbox.setStandardButtons(mbox.Ok)
    mbox.exec_()

## Run python code periodically to allow interactive debuggers to interrupt the qt event loop
timer = Qt.QTimer()


def donothing(*args):
    # print "-- beat --"
    pass


timer.timeout.connect(donothing)
timer.start(1000)

## Start Qt event loop unless running in interactive mode.
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
    if args.profile:
        import cProfile

        cProfile.run('app.exec_()', sort='cumulative')
        pg.exit()  # pg.exit() causes python to exit before Qt has a chance to clean up. 
        # this avoids otherwise irritating exit crashes.
    elif args.callgraph:
        from pycallgraph import PyCallGraph
        from pycallgraph.output import GraphvizOutput

        with PyCallGraph(output=GraphvizOutput()):
            app.exec_()
    else:
        app.exec_()
        # pg.exit()  # pg.exit() causes python to exit before Qt has a chance to clean up.
        # this avoids otherwise irritating exit crashes.
