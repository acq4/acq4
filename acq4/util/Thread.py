import threading

from acq4.util import Qt
from acq4.util.debug import log_and_ignore_exception
from pyqtgraph.debug import enableFaulthandler


class Thread(Qt.QThread):
    """Wrapper around QThread that implements debugging tools:

    - handles thread naming for debugging
    - modifies the run() method to enable fault handling for the new thread
    """
    def __init__(self, *args, **kwds):
        name = kwds.pop('name', None)
        self._threadname = name
        Qt.QThread.__init__(self, *args, **kwds)
        if not hasattr(Qt.QThread, '_names'):
            Qt.QThread._names = {}

        if name is not None:
            self.setObjectName(name)
        
        # sneaky trick: force all subclasses to use our run wrapper
        self.__subclass_run = self.run
        self.run = self.__run_wrapper

    def __run_wrapper(self):
        Qt.QThread._names[threading.current_thread().ident] = self._threadname

        # for every new thread, re-enable faulthandler to ensure the new
        # thread is properly handled. It needs sys.stderr.fileno(), which fails
        # whenever something has swapped sys.stderr for a capture buffer; a
        # debugging aid must not take the thread's actual work down with it.
        with log_and_ignore_exception(
            Exception, "Could not enable faulthandler for thread %r", self._threadname
        ):
            enableFaulthandler()

        self.__subclass_run()
