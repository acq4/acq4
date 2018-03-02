from __future__ import print_function
from acq4.util import Qt
from .debug import enableFaulthandler

class Thread(Qt.QThread):
    """ Simple wrapper around QThread that allows customization of behavior for all threads
    across ACQ4.

    Currently, this class only modifies the run() method to enable fault handling for
    the new thread.
    """
    def __init__(self, *args, **kwds):
        Qt.QThread.__init__(self, *args, **kwds)

        # sneaky trick: force all subclasses to use our run wrapper
        self.__subclass_run = self.run
        self.run = self.__run_wrapper

    def __run_wrapper(self):
        # for every new thread, re-enable faulthandler to ensure the new
        # thread is properly handled
        enableFaulthandler()

        self.__subclass_run()
