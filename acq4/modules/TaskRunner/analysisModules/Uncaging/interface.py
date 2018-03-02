# -*- coding: utf-8 -*-
from __future__ import print_function
from acq4.modules.TaskRunner.analysisModules import AnalysisModule
from acq4.Manager import getManager
from acq4.util import Qt
from .UncagingTemplate import Ui_Form
#from acq4.pyqtgraph import ImageItem
from numpy import *
from scipy.ndimage.filters import gaussian_filter
from acq4.util.metaarray import MetaArray
from acq4.util.debug import *

class UncagingModule(AnalysisModule):
    def __init__(self, *args):
        AnalysisModule.__init__(self, *args)
        self.ui = Ui_Form()
        self.ui.setupUi(self)
        self.postGuiInit()
        self.man = getManager()
        #devs = self.man.listDevices()
        #for d in devs:
            #self.ui.scannerDevCombo.addItem(d)
            #self.ui.clampDevCombo.addItem(d)
            
        #self.fillModuleList()
        self.ui.scannerDevCombo.setTypes('scanner')
        self.ui.clampDevCombo.setTypes('clamp')
        self.ui.cameraModCombo.setTypes('cameraModule')
        
        
        self.tasks = {}
        self.currentTask = None
        self.ui.deleteBtn.clicked.connect(self.deleteSelected)
        self.stateGroup.sigChanged.connect(self.stateChanged)
        self.ui.taskList.currentItemChanged.connect(self.itemSelected)
        self.ui.taskList.itemClicked.connect(self.itemClicked)
        self.ui.recomputeBtn.clicked.connect(self.recompute)
        #self.man.sigModulesChanged.connect(self.fillModuleList)
        
    def quit(self):
        AnalysisModule.quit(self)
        for k in self.tasks:
            self.tasks[k].close()
        self.tasks.clear()
        self.currentTask = None
        
        
    #def fillModuleList(self):
        #mods = self.man.listModules()
        #self.ui.cameraModCombo.clear()
        #for m in mods:
            #self.ui.cameraModCombo.addItem(m)
        
    def taskSequenceStarted(self, *args):
        #print "start:",args
        #self.newTask()
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
        #Qt.QObject.disconnect(getManager(), Qt.SIGNAL('modulesChanged'), self.fillModuleList)
        #getManager().sigModulesChanged.disconnect(self.fillModuleList)
        AnalysisModule.quit(self)
        for p in self.tasks.values():
            p.close()
            
    def cameraModule(self):
        return self.ui.cameraModCombo.getSelectedObj()
        #return str(self.ui.cameraModCombo.currentText())
        
    def cameraDevice(self):
        camMod = self.cameraModule()
        #mod = self.man.getModule(camMod)
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
    #params = ['alphaSlider', 'frame1Spin', 'frame2Spin', 'clampBaseStartSpin', 'clampBaseStopSpin', 'clampTestStartSpin', 'clampTestStopSpin', 'pspToleranceSpin', 'spotToleranceSpin', 'displayImageCheck']
    params = ['alphaSlider', 'clampBaseStartSpin', 'clampBaseStopSpin', 'clampTestStartSpin', 'clampTestStopSpin', 'pspToleranceSpin']
    
    def __init__(self, name, ui):
        self.name = name
        self.ui = weakref.ref(ui)
        self.frames = []
        #self.imgItem = ImageItem()
        self.items = [] #[self.imgItem, [0,0], [1,1]]]
        #self.img = None
        self.updateParams()
        self.z = Task.z
        Task.z += 1
        
        
    def addFrame(self, frame):
        camDev = self.ui().cameraDevice()
        if camDev is None:
            print("Warning: No camera module selected in uncaging analysis dock.")
            return  
        clampDev = self.ui().clampDevice()
        scannerDev = self.ui().scannerDevice()
        
        scanUi = self.ui().pr.getDevice(scannerDev)
        if not hasattr(scanUi, 'pointSize'):
            printExc('The device "%s" does not appear to be a scanner; skipping analysis.' % scannerDev)
        pointSize = scanUi.pointSize()
        
        #if self.state['displayImageCheck']:
            #camFrame1 = frame['result'][camDev]['frames'][self.state['frame1Spin']]
            #camFrame2 = frame['result'][camDev]['frames'][self.state['frame2Spin']]
            #camInfo = camFrame1.infoCopy()
            #camFrame = MetaArray(camFrame2.astype(float32) - camFrame1.astype(float32), info=camInfo)
        #else:
            ##camInfo = frame['result'][camDev]['frames'][self.state['frame1Spin']].infoCopy()
            #camInfo = None
            #camFrame = None
            
        data = {
            #'cam': camFrame,
            'clamp': frame['result'][clampDev]['primary'],
            'scanner': frame['result'][scannerDev],
            #'camInfo': camInfo
        }
        data['scanner']['spot'] = pointSize
        #print "============\n", data
        #print "New frame:", data['clamp'].shape, data['clamp'].xvals('Time').shape
        self.frames.append(data)
        self.recalculate()
        
    def updateParams(self, param=None, val=None):
        state = self.ui().stateGroup.state().copy()
        self.state = {}
        for k in Task.params:
            self.state[k] = state[k]
        if param == 'alphaSlider':
            self.updateAlpha()
            #self.imgItem.setAlpha(state['alphaSlider'])
        #else:
            #self.recalculate(allFrames=True)

    def updateAlpha(self):
        #if self.state['displayImageCheck']:
            #self.updateImage()
        #else:
        for (i, p, s) in self.items[1:]:
            c = i.brush().color()
            c.setAlpha(self.state['alphaSlider'])
            i.setBrush(Qt.QBrush(c))
            

    def recalculate(self, allFrames=False):
        if len(self.frames) < 1:
            return
        #print "recalc", allFrames
        #print self.state
        ## calculate image
        if allFrames:
            ## Clear out old displays
            #self.img = None
            for (i, p, s) in self.items:
                s = i.scene()
                if s is not None:
                    s.removeItem(i)
            self.items = []
            
            ## Compute for all frames
            frames = self.frames
        else:
            frames = self.frames[-1:]
        
        
        #if self.state['displayImageCheck'] and frames[0]['cam'] is not None:
            #if self.img is None:
                #self.img = zeros(frames[0]['cam'].shape + (4,), dtype=float32)
        
        for f in frames:
            (r, g, b) = self.evaluateTrace(f['clamp'])
            
            #if self.state['displayImageCheck'] and f['cam'] is not None and self.img is not None and f['cam'].shape == self.img.shape:
                #alpha = gaussian_filter((f['cam'] - f['cam'].min()), (5, 5))
                #tol = self.state['spotToleranceSpin']
                #alpha = clip(alpha-tol, 0, 2**32)
                #alpha *= 256. / alpha.max()
                #newImg = empty(frames[0]['cam'].shape + (4,), dtype=uint16)
                #newImg[..., 0] = b * alpha
                #newImg[..., 1] = g * alpha
                #newImg[..., 2] = r * alpha
                #newImg[..., 3] = alpha
                
                #self.img = clip(self.img + (newImg.astype(uint16)), 0, 255)
            #else:
            alpha = self.state['alphaSlider']
            spot = Qt.QGraphicsEllipseItem(Qt.QRectF(-0.5, -0.5, 1, 1))
            spot.setBrush(Qt.QBrush(Qt.QColor(r*255, g*255, b*255, alpha)))
            spot.setPen(Qt.QPen(Qt.Qt.NoPen))
            p = f['scanner']['position']
            s = f['scanner']['spotSize']
            self.items.append([spot, p, [s, s]])
            
        self.hide()  ## Make sure only correct items are displayed
        self.show()
        
        #if self.state['displayImageCheck']:
            #self.updateImage()

            ## update location of image
            #info = frames[-1]['camInfo'][-1]
            #s = info['pixelSize']
            #p = info['imagePosition']
            #self.items[0][1] = p
            #self.items[0][2] = s
        
        ## Set correct scene
        #cModName = str(self.ui().ui.cameraModCombo.currentText())
        #camMod = self.ui().man.getModule(cModName)
        camMod = self.ui().ui.cameraModCombo.getSelectedObj()
        scene = camMod.ui.view.scene()
        for i in self.items:
            (item, p, s) = i
            if item.scene() is not scene:
                camMod.ui.addItem(item, p, s, self.z)


    #def updateImage(self):
        ##print "updateImage", self.img.shape, self.img.max(axis=0).max(axis=0), self.img.min(axis=0).min(axis=0)
        ##print "scene:", self.imgItem.scene(), "z", self.imgItem.zValue(), 'visible', self.imgItem.isVisible()
        #aImg = self.img.astype(uint8)
        #aImg[..., 3] *= float(self.state['alphaSlider']) / self.ui().ui.alphaSlider.maximum()
        #self.imgItem.updateImage(aImg)

    def evaluateTrace(self, data):
        bstart = self.state['clampBaseStartSpin'] * 1e-3
        bstop = self.state['clampBaseStopSpin'] * 1e-3
        tstart = self.state['clampTestStartSpin'] * 1e-3
        tstop = self.state['clampTestStopSpin'] * 1e-3
        base = data['Time': bstart:bstop].view(ndarray)
        test = data['Time': tstart:tstop].view(ndarray)
        if len(test) == 0:
            raise Exception("Uncaging analysis: No clamp data to evaluate. Check start/stop values?")
        time = data.xvals('Time')
        dt = time[1] - time[0]
        med = median(base)
        std = base.std()
        test = test - med
        testBlur = gaussian_filter(test, (1e-3 / dt))
        g = 0.0
        tol = self.state['pspToleranceSpin']
        r = clip(testBlur.max() / (tol*std), 0.0, 1.0)
        b = clip(-testBlur.min() / (tol*std), 0.0, 1.0)
        
        ## measure latency 
        
        #for i in range(5):
            #t = i * 1e-3
            ##sec = data['Time': tstart+t:tstart+t+1e-3].view(ndarray)
            #sec = testBlur[int(t / dt):int((t+1e-3) / dt)]
            #if (abs(sec.max()-med) > tol*std) or (abs(sec.min()-med) > tol*std):
                #g = (5-i) * 0.2
                #break
                
        ## Only check first 10ms after stim
        testLen = 10e-3
        sec = abs(testBlur[:int(testLen/dt)])
        secMax = max(abs(testBlur.max()), abs(testBlur.min()))
        if sec.max() < secMax:
            g = 0
        else:
            sec = sec * (sec < (secMax * 0.5))
            halfTime = argwhere(sec==sec.max())[0,0] * dt
            g = (testLen-halfTime) / testLen
            g = clip(g, 0.0, 1.0)
        g = g * max(r, b)
        return (r, g, b)
        
        
    def __del__(self):
        self.close()
    
    def getState(self):
        return self.state
        
    def show(self):
        #self.visible = True
        #if self.state['displayImageCheck']:
            #self.imgItem.show()
        #else:
        for (i, p, s) in self.items:
            i.show()
        
    def hide(self):
        #self.visible = False
        for (i, p, s) in self.items:
            i.hide()
        
    def close(self):
        ## Remove items from scene
        if self.items is None:
            return
        for (item, p, s) in self.items:
            try:
                scene = item.scene()
                if scene is not None:
                    scene.removeItem(item)
            except:
                printExc("Error while cleaning up uncaging analysis:")
                
        #del self.imgItem
        #del self.frames
        #del self.img
        #del self.items
        self.imgItem = None
        self.frames = None
        self.img = None
        self.items = None
        