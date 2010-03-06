from lib.Manager import getManager
from metaarray import *
from pyqtgraph.ImageView import *
from pyqtgraph.GraphicsView import *
from pyqtgraph.graphicsItems import *
from pyqtgraph.graphicsWindows import *
from pyqtgraph.PlotWidget import *
from pyqtgraph.functions import *
from Canvas import Canvas
from PyQt4 import QtCore, QtGui
from functions import *
from SpinBox import *

class EventMatchWidget(QtGui.QSplitter):
    def __init__(self):
        QtGui.QSplitter.__init__(self)
        
        ## set up GUI
        self.hsplitter = QtGui.QSplitter()
        self.addWidget(self.hsplitter)
        self.setOrientation(QtCore.Qt.Vertical)
        self.hsplitter.setOrientation(QtCore.Qt.Horizontal)
        self.analysisPlot = PlotWidget()
        self.addWidget(self.analysisPlot)
        self.dataPlot = PlotWidget()
        self.addWidget(self.dataPlot)
        
        self.analysisPlot.registerPlot('UncagingAnalysis')
        self.dataPlot.registerPlot('UncagingData')
        self.analysisPlot.setXLink('UncagingData')
        
        self.ctrlWidget = QtGui.QWidget()
        self.hsplitter.addWidget(self.ctrlWidget)
        self.templatePlot = PlotWidget()
        self.hsplitter.addWidget(self.templatePlot)
        
        self.ctrlLayout = QtGui.QFormLayout()
        self.ctrlWidget.setLayout(self.ctrlLayout)
        self.tauSpin = SpinBox(log=True, step=0.1, bounds=[0, None], suffix='s', siPrefix=True)
        self.tauSpin.setValue(0.01)
        self.lowPassSpin = SpinBox(log=True, step=0.1, bounds=[0, None], suffix='Hz', siPrefix=True)
        self.lowPassSpin.setValue(200.0)
        self.thresholdSpin = SpinBox(log=True, step=0.1, bounds=[0, None])
        self.thresholdSpin.setValue(2.0)
        self.ctrlLayout.addRow("Low pass", self.lowPassSpin)
        self.ctrlLayout.addRow("Decay const.", self.tauSpin)
        self.ctrlLayout.addRow("Threshold", self.thresholdSpin)
        
        QtCore.QObject.connect(self.tauSpin, QtCore.SIGNAL('valueChanged(double)'), self.tauChanged)
        QtCore.QObject.connect(self.lowPassSpin, QtCore.SIGNAL('valueChanged(double)'), self.lowPassChanged)
        QtCore.QObject.connect(self.thresholdSpin, QtCore.SIGNAL('valueChanged(double)'), self.thresholdChanged)
        
        
        self.events = []
        self.data = []
        
    def setData(self, data):
        self.data = data
        self.dataPlot.clear()
        for d in data:
            d1 = lowPass(d, self.lowPassSpin.value())
            self.dataPlot.plot(d1)
        self.recalculate()
        
    def recalculate(self):
        self.events = self.processData(self.data, display=True)
        self.emit(QtCore.SIGNAL('outputChanged'), self)
        ##display events
        
    def getEvents(self):
        return self.events
        
    def processData(self, data, display=False):
        if display:
            self.analysisPlot.clear()
            self.tickGroups = []
        events = []
        for i in range(len(data)):
            d = data[i]
            #print "lowpass:", d
            d1 = lowPass(d, self.lowPassSpin.value())
            d2 = d1.view(ndarray) - measureBaseline(d1)
            dt = d.xvals('Time')[1] - d.xvals('Time')[0]
            d3 = diff(d2) * self.tauSpin.value() / dt + d2[:-1]
            d4 = removeBaseline(d3)
            if display:
                color = i/(len(data))*0.7
                pen = mkPen(hsv=[color, 0.7, 1.0])
                self.analysisPlot.plot(d4, x=d.xvals('Time')[:-1], pen=pen)
                tg = VTickGroup(view=self.analysisPlot)
                tg.setPen(pen)
                tg.setYRange([0.8, 1.0], relative=True)
                self.tickGroups.append(tg)
                self.analysisPlot.addItem(tg)
                
            #stdev = measureNoise(d3)
            #print "noise:", stdev
            #thresh = stdev * self.thresholdSpin.value()
            #absd = abs(d3)
            #eventList = argwhere((absd[1:] > thresh) * (absd[:-1] <= thresh))[:, 0] + 1
            
            eventList = findEvents(d4, noiseThreshold=self.thresholdSpin.value())['start']
            events.append(eventList)
            if display:
                for t in self.tickGroups:
                    t.setXVals(d.xvals('Time')[eventList])
            #print eventList
        
        return events
        
        
    def tauChanged(self):
        self.recalculate()
        
    def lowPassChanged(self):
        self.recalculate()
        
    def thresholdChanged(self):
        self.recalculate()
        
    def setTau(self, val):
        self.tauSpin.setValue(val)
        
    def setLowPass(self, val):
        self.lowPassSpin.setValue(val)
        
    def setThreshold(self, val):
        self.thresholdSpin.setValue(val)
        

class UncagingWindow(QtGui.QMainWindow):
    def __init__(self):
        QtGui.QMainWindow.__init__(self)
        self.cw = QtGui.QSplitter()
        self.cw.setOrientation(QtCore.Qt.Vertical)
        self.setCentralWidget(self.cw)
        bw = QtGui.QWidget()
        bwl = QtGui.QHBoxLayout()
        bw.setLayout(bwl)
        self.cw.addWidget(bw)
        self.addImgBtn = QtGui.QPushButton('Add Image')
        self.addScanBtn = QtGui.QPushButton('Add Scan')
        self.clearImgBtn = QtGui.QPushButton('Clear Images')
        self.clearScanBtn = QtGui.QPushButton('Clear Scans')
        self.defaultSize = 150e-6
        bwl.addWidget(self.addImgBtn)
        bwl.addWidget(self.clearImgBtn)
        bwl.addWidget(self.addScanBtn)
        bwl.addWidget(self.clearScanBtn)
        QtCore.QObject.connect(self.addImgBtn, QtCore.SIGNAL('clicked()'), self.addImage)
        QtCore.QObject.connect(self.addScanBtn, QtCore.SIGNAL('clicked()'), self.addScan)
        QtCore.QObject.connect(self.clearImgBtn, QtCore.SIGNAL('clicked()'), self.clearImage)
        QtCore.QObject.connect(self.clearScanBtn, QtCore.SIGNAL('clicked()'), self.clearScan)
        #self.layout = QtGui.QVBoxLayout()
        #self.cw.setLayout(self.layout)
        self.canvas = Canvas()
        QtCore.QObject.connect(self.canvas.view, QtCore.SIGNAL('mouseReleased'), self.mouseClicked)
        self.cw.addWidget(self.canvas)
        
        #self.plot = PlotWidget()
        self.plot = EventMatchWidget()
        self.cw.addWidget(self.plot)
        
        self.z = 0
        self.resize(1000, 800)
        self.show()
        self.scanItems = []
        self.imageItems = []
        self.currentTraces = []
        self.noiseThreshold = 2.0
        
    def addImage(self, img=None):
        if img is None:
            fd = getManager().currentFile
            img = fd.read()
        if 'imagePosition' in fd.info():
            ps = fd.info()['pixelSize']
            pos = fd.info()['imagePosition']
        else:
            info = img.infoCopy()[-1]
            ps = info['pixelSize']
            pos = info['imagePosition']
            
        img = img.astype(ndarray)
        if img.ndim == 3:
            img = img.max(axis=0)
        #print pos, ps, img.shape, img.dtype, img.max(), img.min()
        item = ImageItem(img)
        self.canvas.addItem(item, pos, scale=ps, z=self.z)
        self.z += 1
        self.imageItems.append(item)

    def addScan(self):
        dh = getManager().currentFile
        if len(dh.info()['protocol']['params']) > 0:
            dirs = [dh[d] for d in dh.subDirs()]
        else:
            dirs = [dh]
        for d in dirs:
            #d = dh[d]
            if 'Scanner' in d.info() and 'position' in d.info()['Scanner']:
               pos = d.info()['Scanner']['position']
               if 'spotSize' in d.info()['Scanner']:
                  size = d.info()['Scanner']['spotSize']
               else:
                  size = self.defaultSize
               item = QtGui.QGraphicsEllipseItem(0, 0, 1, 1)
               item.setBrush(QtGui.QBrush(self.traceColor(d)))
               item.source = d
               self.canvas.addItem(item, [pos[0] - size*0.5, pos[1] - size*0.5], scale=[size,size], z = self.z)
               #item.connect(QtCore.SIGNAL('clicked'), self.loadTrace)
               #print pos, size
               #print item.mapRectToScene(item.boundingRect())
               self.scanItems.append(item)
            else:
               print "Skipping directory %s" %d.name()
        self.z += 1
        
    def clearImage(self):
        for item in self.imageItems:
            self.canvas.removeItem(item)
        self.imageItems = []
        
        
    def clearScan(self):
        for item in self.scanItems:
            self.canvas.removeItem(item)
        self.scanItems = []
        self.currentTraces = []
        
        
        
    def getClampData(self, dh):
        try:
            data = dh['Clamp1.ma'].read()
            #print "Loaded", dh['Clamp1.ma'].name()
        except:
            data = dh['Clamp2.ma'].read()
            #print "Loaded", dh['Clamp2.ma'].name()
        if data.hasColumn('Channel', 'primary'):
            data = data['Channel': 'primary']
        elif data.hasColumn('Channel', 'scaled'):
            data = data['Channel': 'scaled']
            
        data = denoise(data)
        #data = removeBaseline(data)
        #data = lowPass(data, 2000)
        return data
        
        
    #def findEvents(self, data):
        #return findEvents(data, noiseThreshold=self.noiseThreshold)
        
    def traceColor(self, dh):
        data = self.getClampData(dh)
        base = data['Time': 0.0:0.49]
        signal = data['Time': 0.5:0.6]
        mx = signal.max()
        mn = signal.min()
        mean = base.mean()
        std = base.std()
        red = clip((mx-mean) / std * 10, 0, 255)
        blue = clip((mean-mn) / std * 10, 0, 255)
        return QtGui.QColor(red, 0, blue, 150)
   
    def mouseClicked(self, ev):
        #self.plot.clear()
        spot = self.canvas.view.items(ev.pos())
        n=0.0
        self.currentTraces = []
        for i in spot:
            #n += 1.0
            #color = n/(len(spot))*0.7
            #colorObj = QtGui.QColor()
            #colorObj.setHsvF(color, 0.7, 1)
            #pen = QtGui.QPen(colorObj)
            d = self.loadTrace(i)
            if d is not None:
                self.currentTraces.append(d)
        self.plot.setData(self.currentTraces)
            
    def loadTrace(self, item):
        if not hasattr(item, 'source'):
            return
        dh = item.source
        data = self.getClampData(dh)
        #self.currentTraces.append(data)
        return data
        #self.plot.plot(data, pen=pen)
        
        #events = self.findEvents(diff(data))
        #tg = VTickGroup()
        #tg.setPen(pen)
        #tg.setYRange([data.max(), 2*data.max() - data.min()])
        #tg.setXVals(data.xvals('Time')[events['start']])
        #print "events:", events
        #self.plot.addItem(tg)
        
