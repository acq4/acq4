from lib.modules.ProtocolRunner.analysisModules import AnalysisModule
import lib.Manager as Manager
from PyQt4 import QtCore, QtGui
from UncagingTemplate import Ui_Form
from lib.util.qtgraph.graphicsItems import ImageItem
from numpy import *
from scipy.ndimage.filters import gaussian_filter

class UncagingModule(AnalysisModule):
    def __init__(self, *args):
        AnalysisModule.__init__(self, *args)
        self.ui = Ui_Form()
        self.ui.setupUi(self)
        self.postGuiInit()
        self.man = Manager.getManager()
        mods = self.man.listModules()
        devs = self.man.listDevices()
        for m in mods:
            self.ui.cameraModCombo.addItem(m)
        for d in devs:
            self.ui.cameraDevCombo.addItem(d)
            self.ui.clampDevCombo.addItem(d)
        self.prots = {}
        self.currentProt = None
        QtCore.QObject.connect(self.ui.deleteBtn, QtCore.SIGNAL('clicked()'), self.deleteSelected)
        QtCore.QObject.connect(self.stateGroup, QtCore.SIGNAL('changed'), self.stateChanged)
        QtCore.QObject.connect(self.ui.protList, QtCore.SIGNAL('currentItemChanged(QListWidgetItem*, QListWidgetItem*)'), self.itemSelected)
        
        
    def protocolStarted(self, *args):
        #print "start:",args
        #self.newProt()
        pass
    
    def protocolFinished(self):
        self.currentProt = None
        
    def newFrame(self, frame):
        if not self.ui.enabledCheck.isChecked():
            return
        if self.currentProt is None:
            self.newProt()
        self.currentProt.addFrame(frame)

    def newProt(self):
        n = self.pr.currentProtocol.name()
        i = 0
        while True:
            name = n + ("_%03d" % i)
            if name not in self.prots:
                break
            i += 1
        p = Prot(name, self)
        self.currentProt = p
        self.prots[name] = p
        self.ui.protList.addItem(name)

    def deleteSelected(self):
        row = self.ui.protList.currentRow()
        if row == -1:
            return
        item = self.ui.protList.takeItem(row)
        name = str(item.text())
        del self.prots[name]
        if self.currentProt is not None and self.currentProt.name == name:
            self.currentProt = None
    
    def selectedProt(self):
        row = self.ui.protList.currentRow()
        if row == -1:
            return None
        item = self.ui.protList.item(row)
        name = str(item.text())
        return self.prots[name]
        
    
    def stateChanged(self, *args):
        sp = self.selectedProt()
        if sp is not None:
            sp.updateParams(*args)
            
    def itemSelected(self, *args):
        sp = self.selectedProt()
        if sp is not None:
            self.stateGroup.setState(sp.getState())
        
class Prot:
    z = 1000
    params = ['alphaSlider', 'frameSpin', 'clampBaseStartSpin', 'clampBaseStopSpin', 'clampTestStartSpin', 'clampTestStopSpin', 'pspToleranceSpin', 'spotToleranceSpin']
    
    def __init__(self, name, ui):
        self.name = name
        self.ui = ui
        self.frames = []
        self.imgItem = ImageItem()
        self.img = None
        self.updateParams()
        self.z = Prot.z
        Prot.z += 1
        
    def addFrame(self, frame):
        camDev = str(self.ui.ui.cameraDevCombo.currentText())
        clampDev = str(self.ui.ui.clampDevCombo.currentText())
        camFrame = self.state['frameSpin']
        data = {
            'cam': frame['result'][camDev]['frames'][camFrame],
            'clamp': frame['result'][clampDev]['scaled']
        }
        #print "New frame:", data['clamp'].shape, data['clamp'].xvals('Time').shape
        self.frames.append(data)
        self.recalculate()
        
    def updateParams(self, param=None, val=None):
        state = self.ui.stateGroup.state().copy()
        self.state = {}
        for k in Prot.params:
            self.state[k] = state[k]
        if param == 'alphaSlider':
            self.updateImage()
            #self.imgItem.setAlpha(state['alphaSlider'])
        else:
            self.recalculate(allFrames=True)
        
    def recalculate(self, allFrames=False):
        if len(self.frames) < 1:
            return
            
        ## calculate image
        if allFrames:
            self.img = None
            frames = self.frames
        else:
            frames = self.frames[-1:]
        
        if self.img is None:
            self.img = zeros(frames[0]['cam'].shape + (4,), dtype=uint8)
        
        for f in frames:
            alpha = gaussian_filter((f['cam'] - f['cam'].min()).astype(float32), (5, 5))
            alpha /= alpha.max()
            tol = self.state['spotToleranceSpin']
            alpha = ((clip(alpha-tol, 0, 1) / (1.0-tol)) * 256).astype(uint8)
            
            (r, g, b) = self.evaluateTrace(f['clamp'])
            #print "New frame analysis:", r, g, b, alpha.max(), alpha.min()
            newImg = empty(frames[0]['cam'].shape + (4,), dtype=uint8)
            newImg[..., 0] = b * alpha
            newImg[..., 1] = g * alpha
            newImg[..., 2] = r * alpha
            newImg[..., 3] = alpha
            self.img += newImg
            #self.img = (newImg.copy() * 256).astype(uint8) 
            #self.img[..., 3] = 255
            
        self.updateImage()
        #self.imgItem.setAlpha(float(self.state['alphaSlider']) / self.ui.ui.alphaSlider.maximum())
        
        ## Set correct scene
        cModName = str(self.ui.ui.cameraModCombo.currentText())
        camMod = self.ui.man.getModule(cModName)
        scene = camMod.ui.scene
        if self.imgItem.scene is not scene:
            info = self.frames[-1]['cam'].infoCopy()[-1]
            s = info['pixelSize']
            p = info['imagePosition']
            camMod.ui.addImage(self.imgItem, p, s, self.z)
            #scene.addItem(self.imgItem)

    def updateImage(self):
        aImg = self.img.copy()
        aImg[..., 3] *= float(self.state['alphaSlider']) / self.ui.ui.alphaSlider.maximum()
        self.imgItem.updateImage(aImg)

    def evaluateTrace(self, data):
        bstart = self.state['clampBaseStartSpin'] * 1e-3
        bstop = self.state['clampBaseStopSpin'] * 1e-3
        tstart = self.state['clampTestStartSpin'] * 1e-3
        tstop = self.state['clampTestStopSpin'] * 1e-3
        base = data['Time': bstart:bstop].view(ndarray)
        test = data['Time': tstart:tstop].view(ndarray)
        med = median(base)
        std = base.std()
        test = test - med
        r = 0.0
        tol = self.state['pspToleranceSpin']
        g = clip(test.max() / (tol*std), 0.0, 1.0)
        b = clip(-test.min() / (tol*std), 0.0, 1.0)
        return (r, g, b)
        
        
    def __del__(self):
        ## Remove images from scene
        if self.imgItem is not None:
            self.imgItem.scene().removeItem(self.imgItem)
    
    def getState(self):
        return self.state