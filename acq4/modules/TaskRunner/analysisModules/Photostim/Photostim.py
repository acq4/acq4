# -*- coding: utf-8 -*-
from __future__ import print_function
from acq4.modules.TaskRunner.analysisModules import AnalysisModule
from acq4.Manager import getManager
from acq4.util import Qt
from .PhotostimTemplate import Ui_Form
import numpy as np
import scipy.ndimage
from acq4.util.metaarray import MetaArray
from acq4.util.debug import *
import acq4.pyqtgraph as pg

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
        item = Qt.QListWidgetItem(name)
        item.setCheckState(Qt.Qt.Checked)
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
        if item.checkState() == Qt.Qt.Checked:
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
        
    def clampDevice(self):
        return str(self.ui.clampDevCombo.currentText())
        
    def scannerDevice(self):
        return str(self.ui.scannerDevCombo.currentText())

    def saveState(self):
        state = AnalysisModule.saveState(self)

        # remove some unnecessary information
        state['colorMapper'].pop('fields', None)

        return state
        
        
class Task:
    z = 500
    params = ['clampBaseStartSpin', 'clampBaseStopSpin', 'clampTestStartSpin', 'clampTestStopSpin', 'spikeThresholdSpin', 'spikeThresholdAbsRadio']
    
    def __init__(self, name, ui):
        self.scatter = pg.ScatterPlotItem(pxMode=False)
        self.name = name
        self.ui = weakref.ref(ui)
        self.frames = []
        self.spots = {'pos': [], 'size': [], 'color': []}
        self.updateParams()
        self.z = Task.z
        Task.z += 1
        
    def addFrame(self, frame):
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
        if allFrames:
            ## Compute for all frames
            self.spots = {'pos': [], 'size': [], 'color': []}
            frames = self.frames
        else:
            frames = self.frames[-1:]
        
        for f in frames:
            color = self.evaluateTrace(f['clamp'])

            p = f['scanner']['position']
            s = f['scanner']['spotSize']
            self.spots['pos'].append(p)
            self.spots['size'].append(s)
            self.spots['color'].append(color)
            
        x = [p[0] for p in self.spots['pos']]
        y = [p[1] for p in self.spots['pos']]
        self.scatter.setData(x, y, size=self.spots['size'], brush=self.spots['color'])

        ## Set correct scene
        camMod = self.ui().ui.cameraModCombo.getSelectedObj()
        scene = camMod.ui.view.scene()
        if self.scatter.scene() is not scene:
            camMod.ui.addItem(self.scatter)

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
        med = np.median(base)
        std = base.std()
        testDetrend = test - med
        testBlur = scipy.ndimage.gaussian_filter(testDetrend, (1e-3 / dt))

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
            thresh += med
        if thresh > med:
            mask = test > thresh
        else:
            mask = test < thresh

        spikes = np.argwhere(np.diff(mask.astype(np.int8)) == 1)
        results['nSpikes'] = len(spikes)
        # generate spot color from analysis
        color = self.ui().ui.colorMapper.map(results)

        return Qt.QColor(*color[0])
        
        
    def __del__(self):
        self.close()
    
    def getState(self):
        return self.state
        
    def show(self):
        self.scatter.setVisible(True)
        
    def hide(self):
        self.scatter.setVisible(False)
        
    def close(self):
        ## Remove items from scene
        self.frames = None
        self.spots = None
        if self.scatter.scene() is not None:
            self.scatter.scene().removeItem(self.scatter)
        