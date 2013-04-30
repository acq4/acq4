from lib.devices.Device import *
from PyQt4 import QtGui

class Screen(Device):
    
    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)
        dm.declareInterface(name, ['screen'], self)

    def protocolInterface(self, prot):
        return ScreenProtoGui(self, prot)

    def createTask(self, cmd):
        return ScreenTask(self, cmd)



class Black(QtGui.QWidget):
    """ make a black rectangle to fill screen when "blanking" """
    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        brush = QtGui.QBrush(QtGui.QColor(0,0,0))
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
        d = QtGui.QApplication.desktop()
        for i in range(d.screenCount()): # look for all screens
            w = Black()
            self.widgets.append(w) # make a black widget
            sg = d.screenGeometry(i) # get the screen size
            w.move(sg.x(), sg.y()) # put the widget there
            w.showFullScreen() # duh
        QtGui.QApplication.processEvents() # make it so
        
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
    
    def __init__(self, dev, cmd):
        DeviceTask.__init__(self, dev, cmd)
        self.cmd = cmd
        self.blanker = ScreenBlanker()

    def configure(self, tasks, startOrder):
        pass
        
    def start(self):
        ## possibly nothing required here, DAQ will start recording.
        if self.cmd['blank']:
            self.blanker.blank()
        
    def stop(self, abort=False):
        self.blanker.unBlank()
        
        
class ScreenProtoGui(ProtocolGui):
    
    def __init__(self, dev, prot):
        ProtocolGui.__init__(self, dev, prot)
        self.layout = QtGui.QGridLayout()
        self.setLayout(self.layout)
        self.blankCheck = QtGui.QCheckBox("Blank Screen")
        
        self.layout.addWidget(self.blankCheck)
        
    def saveState(self):
        return {'blank': self.blankCheck.isChecked()}
        
    def restoreState(self, state):
        self.blankCheck.setChecked(state['blank'])
        
    def listSequence(self):
        return []
        
    def generateProtocol(self, params=None):
        return self.saveState()
        