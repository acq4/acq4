# -*- coding: utf-8 -*-
from acq4.modules.TaskRunner.analysisModules import AnalysisModule
from acq4.Manager import getManager
from PyQt4 import QtCore, QtGui
from PhotostimTemplate import Ui_Form
#from acq4.pyqtgraph import ImageItem
from numpy import *
from scipy.ndimage.filters import gaussian_filter
from acq4.util.metaarray import MetaArray
from acq4.util.debug import *

class PhotostimModule(AnalysisModule):
    def __init__(self, *args):
        AnalysisModule.__init__(self, *args)
        self.ui = Ui_Form()
        self.ui.setupUi(self)
        self.postGuiInit()
        self.man = getManager()

        self.ui.scannerDevCombo.setTypes('scanner')
        self.ui.clampDevCombo.setTypes('clamp')
        self.ui.cameraModCombo.setTypes('cameraModule')
        
        self.ui.clampBaseStartSpin.setOpts(suffix='s', siPrefix=True, bounds=[0, None], step=1e-3)
        self.ui.clampBaseStopSpin.setOpts(suffix='s', siPrefix=True, bounds=[0, None], step=1e-3)
        self.ui.clampTestStartSpin.setOpts(suffix='s', siPrefix=True, bounds=[0, None], step=1e-3)
        self.ui.clampTestStopSpin.setOpts(suffix='s', siPrefix=True, bounds=[0, None], step=1e-3)
        self.ui.spikeThresholdSpin.setOpts(suffix='V', siPrefix=True, bounds=[None, None], dec=True, minStep=0.05)
        self.ui.colorMapper.setFields([('maxPeak', {'mode': 'range', 'units': 'V'}),
                                       ('minPeak', {'mode': 'range', 'units': 'V'}),
                                       ('maxZScore', {'mode': 'range'}),
                                       ('minZScore', {'mode': 'range'}),
                                       ('nSpikes', {'mode': 'range'}),
                                       ])

        self.tasks = {}
        self.currentTask = None
        self.ui.deleteBtn.clicked.connect(self.deleteSelected)
        self.stateGroup.sigChanged.connect(self.stateChanged)
        self.ui.taskList.currentItemChanged.connect(self.itemSelected)
        self.ui.taskList.itemClicked.connect(self.itemClicked)
        self.ui.recomputeBtn.clicked.connect(self.recompute)
        
    def quit(self):
        AnalysisModule.quit(self)
        for k in self.tasks:
            self.tasks[k].close()
        self.tasks.clear()
        self.currentTask = None
        
    def taskSequenceStarted(self, *args):
        pass
    
    def taskFinished(self):
        self.currentTask = None
        
    def newFrame(self, frame):
        if not self.ui.enabledCheck.isChecked():
            return
        if self.currentTask is None:
            self.newTask()
        self.currentTask.addFrame(frame)

    def newTask(self):
        n = self.pr.currentTask.name()
        if n is None:
            n = 'protocol'
       
        i = 0
        while True:
            name = n + ("_%03d" % i)
            if name not in self.tasks:
                break
            i += 1
        p = Task(name, self)
        self.currentTask = p
        self.tasks[name] = p
        item = QtGui.QListWidgetItem(name)
        item.setCheckState(QtCore.Qt.Checked)
        self.ui.taskList.addItem(item)
        self.ui.taskList.setCurrentItem(item)

    def deleteSelected(self):
        row = self.ui.taskList.currentRow()
        if row == -1:
            return
        item = self.ui.taskList.takeItem(row)
        name = str(item.text())
        self.tasks[name].close()
        del self.tasks[name]
        if self.currentTask is not None and self.currentTask.name == name:
            self.currentTask = None
    
    def selectedTask(self):
        row = self.ui.taskList.currentRow()
        if row == -1:
            return None
        item = self.ui.taskList.item(row)
        name = str(item.text())
        return self.tasks[name]
    
    def stateChanged(self, *args):
        sp = self.selectedTask()
        if sp is not None:
            sp.updateParams(*args)
            
    def itemSelected(self, *args):
        sp = self.selectedTask()
        if sp is not None:
            self.stateGroup.setState(sp.getState())
            
    def itemClicked(self, item):
        task = self.tasks[str(item.text())]
        if item.checkState() == QtCore.Qt.Checked:
            task.show()
        else:
            task.hide()

    def recompute(self):
        sp = self.selectedTask()
        if sp is not None:
            sp.recalculate(allFrames=True)

    def quit(self):
        AnalysisModule.quit(self)
        for p in self.tasks.values():
            p.close()
            
    def cameraModule(self):
        return self.ui.cameraModCombo.getSelectedObj()
        
    def cameraDevice(self):
        camMod = self.cameraModule()
        if 'camDev' in camMod.config:
            return camMod.config['camDev']
        else:
            return None

    def clampDevice(self):
        return str(self.ui.clampDevCombo.currentText())
        
    def scannerDevice(self):
        return str(self.ui.scannerDevCombo.currentText())
        
        
class Task:
    z = 500
    params = ['clampBaseStartSpin', 'clampBaseStopSpin', 'clampTestStartSpin', 'clampTestStopSpin', 'spikeThresholdSpin', 'spikeThresholdAbsRatio']
    
    def __init__(self, name, ui):
        self.scatter = pg.ScatterPlotItem()
        self.name = name
        self.ui = weakref.ref(ui)
        self.frames = []
        self.spots = {'pos': [], 'size': [], 'color': []}
        self.updateParams()
        self.z = Task.z
        Task.z += 1
        
    def addFrame(self, frame):
        camDev = self.ui().cameraDevice()
        if camDev is None:
            print "Warning: No camera module selected in uncaging analysis dock."
            return  
        clampDev = self.ui().clampDevice()
        scannerDev = self.ui().scannerDevice()
        data = {
            'clamp': frame['result'][clampDev]['primary'],
            'scanner': frame['result'][scannerDev],
        }
        self.frames.append(data)
        self.recalculate()
        
    def updateParams(self, param=None, val=None):
        state = self.ui().stateGroup.state().copy()
        self.state = {}
        for k in Task.params:
            self.state[k] = state[k]

    def recalculate(self, allFrames=False):
        if len(self.frames) < 1:
            return
        #print "recalc", allFrames
        #print self.state
        ## calculate image
        if allFrames:
            ## Clear out old displays
            # for (i, p, s) in self.items:
            #     s = i.scene()
            #     if s is not None:
            #         s.removeItem(i)
            # self.items = []
            
            ## Compute for all frames
            self.spots = {'pos': [], 'size': [], 'color': []}
            frames = self.frames
        else:
            frames = self.frames[-1:]
        
        for f in frames:
            color = self.evaluateTrace(f['clamp'])

            # spot = QtGui.QGraphicsEllipseItem(QtCore.QRectF(-0.5, -0.5, 1, 1))
            # spot.setBrush(QtGui.QBrush(QtGui.QColor(r*255, g*255, b*255, alpha)))
            # spot.setPen(QtGui.QPen(QtCore.Qt.NoPen))
            p = f['scanner']['position']
            s = f['scanner']['spotSize']
            self.spots.append((color, p, s))
            # self.items.append([spot, p, [s, s]])
            
        # self.hide()  ## Make sure only correct items are displayed
        # self.show()
        self.scatter.setData(pos=self.spots['pos'], size=self.spots['size'], brush=self.spots['color'])

        ## Set correct scene
        camMod = self.ui().ui.cameraModCombo.getSelectedObj()
        scene = camMod.ui.view.scene()
        if self.scatter.scene() is not scene:
            camMod.ui.addItem(self.scatter)
        # for i in self.items:
        #     (item, p, s) = i
        #     if item.scene() is not scene:
        #         camMod.ui.addItem(item, p, s, self.z)

    def evaluateTrace(self, data):
        bstart = self.state['clampBaseStartSpin']
        bstop = self.state['clampBaseStopSpin']
        tstart = self.state['clampTestStartSpin']
        tstop = self.state['clampTestStopSpin']
        base = data['Time': bstart:bstop].view(ndarray)
        test = data['Time': tstart:tstop].view(ndarray)
        if len(test) == 0:
            raise Exception("Uncaging analysis: No clamp data to evaluate. Check start/stop values?")
        time = data.xvals('Time')
        dt = time[1] - time[0]
        med = median(base)
        std = base.std()
        testDetrend = test - med
        testBlur = gaussian_filter(testDetrend, (1e-3 / dt))
        # g = 0.0
        # tol = self.state['pspToleranceSpin']
        # r = clip(testBlur.max() / (tol*std), 0.0, 1.0)
        # b = clip(-testBlur.min() / (tol*std), 0.0, 1.0)
        
        ## Only check first 10ms after stim
        # testLen = 10e-3
        # sec = abs(testBlur[:int(testLen/dt)])
        # secMax = max(abs(testBlur.max()), abs(testBlur.min()))
        # if sec.max() < secMax:
        #     g = 0
        # else:
        #     sec = sec * (sec < (secMax * 0.5))
        #     halfTime = argwhere(sec==sec.max())[0,0] * dt
        #     g = (testLen-halfTime) / testLen
        #     g = clip(g, 0.0, 1.0)
        # g = g * max(r, b)
        # return (r, g, b)

        # Compute size of positive / negative peaks
        mx = testDetrend.max()
        mn = testDetrend.min()
        results = {
            'maxPeak': mx,
            'minPeak': mn,
            'maxZScore': mx / std,
            'minZScore': mn / std,
            }

        # do spike detection
        thresh = self.state['spikeThresholdSpin']
        if self.state['spikeThresholdAbsRadio'] is False:
            thresh -= med
        mask = test > thresh
        spikes = np.argwhere(np.diff(mask) == 1)
        results['nSpikes'] = len(spikes)

        # generate spot color from analysis
        color = self.colorMapper.map(results)

        return color
        
        
    def __del__(self):
        self.close()
    
    def getState(self):
        return self.state
        
    def show(self):
        self.scatter.setVisible(True)
        # for (i, p, s) in self.items:
        #     i.show()
        
    def hide(self):
        self.scatter.setVisible(False)
        # for (i, p, s) in self.items:
        #     i.hide()
        
    def close(self):
        ## Remove items from scene
        # if self.items is None:
        #     return
        # for (item, p, s) in self.items:
        #     try:
        #         scene = item.scene()
        #         if scene is not None:
        #             scene.removeItem(item)
        #     except:
        #         printExc("Error while cleaning up uncaging analysis:")
                
        self.frames = None
        self.spots = None
        if self.scatter.scene() is not None:
            self.scatter.scene().removeItem(self.scatter)
        # self.items = None
        