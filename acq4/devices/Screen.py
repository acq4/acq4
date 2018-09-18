from __future__ import print_function
from acq4.devices.Device import *
from acq4.util import Qt

class Screen(Device):
    """
    Device used for screen output. 
    
    Currently, this is only used to blank the screen temporarily to avoid 
    contaminating sensitive imaging operations. In the future, this device may
    be extended to provide visual stimulation (perhaps via psychopy)    
    """
    sigBlankScreen = Qt.Signal(object, object)  # bool blank/unblank, QWaitCondition
    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)
        dm.declareInterface(name, ['screen'], self)
        self.blanker = ScreenBlanker()
        self.sigBlankScreen.connect(self.blankRequested, Qt.Qt.QueuedConnection)

    def taskInterface(self, taskRunner):
        return ScreenTaskGui(self, taskRunner)

    def createTask(self, cmd, parentTask):
        return ScreenTask(self, cmd, parentTask)

    def blankScreen(self, blank=True, timeout=10.):
        isGuiThread = Qt.QThread.currentThread() == Qt.QCoreApplication.instance().thread()
        if isGuiThread:
            if blank:
                self.blanker.blank()
            else:
                self.blanker.unBlank()
        else:
            mutex = Qt.QMutex()
            mutex.lock()
            waitCond = Qt.QWaitCondition()
            self.sigBlankScreen.emit(blank, waitCond)
            if not waitCond.wait(mutex, int(timeout*1000)):
                raise Exception("Screen blanker threaded request timed out.")
            
        
    def unBlankScreen(self):
        self.blankScreen(False)

    def blankRequested(self, blank, waitCond):
        try:
            if blank:
                self.blankScreen()
            else:
                self.unBlankScreen()
        finally:
            waitCond.wakeAll()


class Black(Qt.QWidget):
    """ make a black rectangle to fill screen when "blanking" """
    def paintEvent(self, event):
        p = Qt.QPainter(self)
        brush = Qt.QBrush(Qt.QColor(0,0,0))
        p.fillRect(self.rect(), brush)
        p.end()
     

class ScreenBlanker:
    """
    Perform the blanking on ALL screens that we can detect.
    This is so that extraneous light does not leak into the 
    detector during acquisition.
    """
    def __init__(self):
        self.widgets = []
    
    def blank(self):
        d = Qt.QApplication.desktop()
        for i in range(d.screenCount()): # look for all screens
            w = Black()
            self.widgets.append(w) # make a black widget
            sg = d.screenGeometry(i) # get the screen size
            w.move(sg.x(), sg.y()) # put the widget there
            w.showFullScreen() # duh
        Qt.QApplication.processEvents() # make it so
        
    def __exit__(self, *args):
        pass
    #for w in self.widgets:
            #w.hide() # just take them away
        #self.widgets = []
    
    def unBlank(self):
        for w in self.widgets:
            w.hide() # just take them away
        self.widgets = []
        


class ScreenTask(DeviceTask):
    
    def __init__(self, dev, cmd, parentTask):
        DeviceTask.__init__(self, dev, cmd, parentTask)
        self.cmd = cmd

    def configure(self):
        pass
        
    def start(self):
        ## possibly nothing required here, DAQ will start recording.
        if self.cmd['blank']:
            self.dev.blankScreen()
        
    def stop(self, abort=False):
        self.dev.unBlankScreen()
        
        
class ScreenTaskGui(TaskGui):
    
    def __init__(self, dev, taskRunner):
        TaskGui.__init__(self, dev, taskRunner)
        self.layout = Qt.QGridLayout()
        self.setLayout(self.layout)
        self.blankCheck = Qt.QCheckBox("Blank Screen")
        
        self.layout.addWidget(self.blankCheck)
        
    def saveState(self):
        return {'blank': self.blankCheck.isChecked()}
        
    def restoreState(self, state):
        self.blankCheck.setChecked(state['blank'])
        
    def listSequence(self):
        return []
        
    def generateTask(self, params=None):
        return self.saveState()
        