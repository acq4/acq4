from acq4.devices.Device import TaskGui
from acq4.logging_config import get_logger
from pyqtgraph.WidgetGroup import WidgetGroup
from acq4.util import Qt

logger = get_logger(__name__)
Ui_Form = Qt.importTemplate('.TaskTemplate')


class NiDAQTask(TaskGui):
    
    sigChanged = Qt.Signal(object)
    
    def __init__(self, dev, taskRunner):
        TaskGui.__init__(self, dev, taskRunner)
        self.ui = Ui_Form()
        self.ui.setupUi(self)
        self.nPts = 0
        self.ignorePeriod = False
        self.ignoreRate = False
        self.rate = 40e3

        self._block_update = False # use to block signal emission during bulk updates

        self.updateNPts()
        self.updateDevList()
        self.ui.rateSpin.setOpts(dec=True, step=0.5, minStep=10, bounds=[1,None], siPrefix=True, suffix='Hz')
        self.ui.periodSpin.setOpts(dec=True, step=0.5, minStep=1e-6, bounds=[1e-6,None], siPrefix=True, suffix='s')
        
        ## important to create widget group before connecting anything else.
        self.stateGroup = WidgetGroup([
            (self.ui.rateSpin, 'rate'),
            (self.ui.downsampleSpin, 'downsample'),
            (self.ui.triggerDevList, 'triggerDevice'),
        ])
        
        self.ui.periodSpin.sigValueChanging.connect(self.updateRateSpin)
        self.ui.rateSpin.sigValueChanging.connect(self.updatePeriodSpin)
        self.taskRunner.sigTaskChanged.connect(self.taskChanged)
        self.ui.rateSpin.setValue(self.rate)
        self.stateGroup.sigChanged.connect(self.stateChanged)

    def quit(self):
        self.taskRunner.sigTaskChanged.disconnect(self.taskChanged)
        TaskGui.quit(self)
        
    def saveState(self):
        return self.stateGroup.state()
        
    def restoreState(self, state):
        """Restore a saveState() state; keys for removed controls (e.g. old filter settings) are ignored."""
        block = self._block_update
        try:
            self._block_update = True
            self.stateGroup.setState(state)
        except Exception:
            logger.exception("Error while loading DAQ task GUI configuration (proceeding with default configuration) :")
        finally:
            self._block_update = block
            self.stateChanged()
        
    def generateTask(self, params=None):
        return self.currentState()
        
    def currentState(self):
        self.updateNPts()
        state = self.stateGroup.state()
        ## make sure all of these are up to date:
        state['numPts'] = self.nPts
        state['rate'] = self.rate
        state['downsample'] = self.ui.downsampleSpin.value()
        if self.ui.triggerDevList.currentIndex() > 0:
            state['triggerDevice'] = str(self.ui.triggerDevList.currentText())
        else:
            del state['triggerDevice']
        
        return state
        
    def updatePeriodSpin(self):
        if self.ignoreRate:
            return
        period = 1. / self.ui.rateSpin.value()
        
        self.ignorePeriod = True
        self.ui.periodSpin.setValue(period)
        self.ignorePeriod = False
        
    def updateRateSpin(self):
        if self.ignorePeriod:
            return
        period = self.ui.periodSpin.value()
        rate = 1.0 / period
        self.ignoreRate = True
        self.ui.rateSpin.setValue(rate)
        self.ignoreRate = False
        
    def stateChanged(self, name=None, val=None):
        if name == 'rate':
            self.rate = self.ui.rateSpin.value()
            self.updateNPts()
            
        if self._block_update:
            return
        state = self.currentState()
        self.sigChanged.emit(state)
        
    def taskChanged(self, n, v):
        if n == 'duration':
            self.updateNPts()
            self.sigChanged.emit(self.currentState())
        
    def updateNPts(self):
        dur = self.taskRunner.getParam('duration')
        nPts = int(dur * self.rate)
        if nPts != self.nPts:
            self.nPts = nPts
            self.ui.numPtsLabel.setText(str(self.nPts))
        
    def updateDevList(self):
        ## list all devices
        allDevNames = self.dev.dm.listDevices()
        ## convert device names into device handles
        allDevs = [self.dev.dm.getDevice(d) for d in allDevNames]
        ## select out devices which have trigger channel to this DAQ
        self.devs = [d.name() for d in allDevs if d.getTriggerChannels(self.dev.name())['input'] is not None]
            
        self.ui.triggerDevList.clear()
        self.ui.triggerDevList.addItem('No Trigger')
        
        for d in self.devs:
            self.ui.triggerDevList.addItem(d)
