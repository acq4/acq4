from __future__ import print_function
from acq4.modules.Module import Module
from acq4.util import Qt
from acq4.pyqtgraph import DataTreeWidget

class TaskMonitor(Module):
    """Simple module that displays information about tasks submitted to the manager
    and the results they generate.

    Useful for debugging issues in task generation and execution.
    """
    moduleDisplayName = "Task Monitor"
    moduleCategory = "Utilities"

    def __init__(self, manager, name, config):
        Module.__init__(self, manager, name, config) 
        self.man = manager
        self.win = Qt.QMainWindow()
        self.cw = Qt.QSplitter()
        self.taskTree = DataTreeWidget()
        self.resultTree = DataTreeWidget()
        self.win.setCentralWidget(self.cw)
        self.cw.addWidget(self.taskTree)
        self.cw.addWidget(self.resultTree)
        self.win.show()
        self.win.setWindowTitle('Task Monitor')
        self.man.sigTaskCreated.connect(self.showTask)
        self.taskTimer = Qt.QTimer()
        self.taskTimer.timeout.connect(self.checkResult)
        
    def showTask(self, cmd, task):
        self._lastTask = task
        self.taskTree.setData(cmd)
        self.resultTree.clear()
        self.taskTimer.start(100)

    def checkResult(self):
        try:
            if self._lastTask.isDone():
                result = self._lastTask.getResult()
                self.resultTree.setData(result)
                self.taskTimer.stop()
        except Exception:
            self.resultTree.setData("Task failed.")
            self.taskTimer.stop()
    


