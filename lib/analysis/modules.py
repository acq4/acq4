# -*- coding: utf-8 -*-
from lib.Manager import getManager
from metaarray import *
from pyqtgraph.ImageView import *
from pyqtgraph.GraphicsView import *
from pyqtgraph.graphicsItems import *
from pyqtgraph.graphicsWindows import *
from pyqtgraph.PlotWidget import *
from pyqtgraph.functions import *
from Canvas import Canvas
from UncagingControlTemplate import *
from StdpCtrlTemplate import *
from PyQt4 import QtCore, QtGui
from functions import *
from SpinBox import *
from debug import *
#from DictView import DictView
from scipy import stats, signal, ndimage
from numpy import log
from WidgetGroup import *
from advancedTypes import OrderedDict

class UncagingSpot(QtGui.QGraphicsEllipseItem):
    def __init__(self, source=None): #source is directory handle for single-stimulus spots
        QtGui.QGraphicsEllipseItem.__init__(self, 0, 0, 1, 1)
        self.source = source
        self.index = None
        self.position = None
        self.size = None
        self.laserTime = None
        self.sourceItems = []   ## points to source spots if this is an average
        

        

from EventDetectionCtrlTemplate import *

class EventMatchWidget(QtGui.QSplitter):
    def __init__(self):
        QtGui.QSplitter.__init__(self)
        
        ## set up GUI
        self.setOrientation(QtCore.Qt.Horizontal)
        
        self.vsplitter = QtGui.QSplitter()
        self.vsplitter.setOrientation(QtCore.Qt.Vertical)
        
        self.ctrlWidget = QtGui.QWidget()
        self.ctrl = Ui_EventDetectionCtrlForm()
        self.ctrl.setupUi(self.ctrlWidget)
        self.addWidget(self.ctrlWidget)        
        self.addWidget(self.vsplitter)
        
        self.dataPlot = PlotWidget(name='UncagingData')
        self.vsplitter.addWidget(self.dataPlot)
        
        self.analysisPlot = PlotWidget(name='UncagingAnalysis')
        self.vsplitter.addWidget(self.analysisPlot)
        
        self.analysisPlot.setXLink('UncagingData')
        
        self.templatePlot = PlotWidget()
        #self.vsplitter.addWidget(self.templatePlot)
        
        self.ctrl.preFilterList.addFilter('Denoise')
        self.ctrl.preFilterList.addFilter('Bessel', cutoff=1000, order=4, band='lowpass')
        self.ctrl.preFilterList.addFilter('ExpDeconvolve')
        self.ctrl.preFilterList.addFilter('AdaptiveDetrend', threshold=2.0)
        
        self.ctrl.zcSumAbsThresholdSpin.setOpts(value=0, step=1, minStep=1e-12, bounds=[0,None], dec=True)
        self.ctrl.zcAmpAbsThresholdSpin.setOpts(value=0, step=1, minStep=1e-12, bounds=[0,None], dec=True)
        
        QtCore.QObject.connect(self.ctrl.detectMethodCombo, QtCore.SIGNAL('currentIndexChanged(int)'), self.ctrl.detectMethodStack.setCurrentIndex)
        self.analysisEnabled = True
        self.events = []
        self.data = []
        
        self.stateGroup = WidgetGroup(self)
        
        QtCore.QObject.connect(self.stateGroup, QtCore.SIGNAL('changed'), self.recalculate)        


    def widgetGroupInterface(self):
        return (None, None, None, True) ## Just tells self.stateGroup to automatically add all children
        
    #def stateChanged(self):
        #self.emit(QtCore.SIGNAL('stateChanged'))
        #self.recompute()
        
    def enableAnalysis(self, b):
        if b == self.analysisEnabled:
            return
        self.analysisEnabled = b
        
        if b:
            self.recalculate()
            self.templatePlot.show()
            self.analysisPlot.show()
            self.ctrlWidget.show()
        else:
            self.templatePlot.hide()
            self.analysisPlot.hide()
            self.ctrlWidget.hide()
        
    def setData(self, data, analyze=True):
        self.data = data
        if (type(data) is list and isinstance(data[0], ndarray)) or (isinstance(data, ndarray) and data.ndim >= 2):
            self.recalculate(analyze=analyze)
        else:
            raise Exception("Data for event match widget must be a list of arrays or an array with ndim >= 2.")
        
    def recalculate(self, analyze=True):
        self.events = self.processData(self.data, display=True, analyze=analyze)
        self.emit(QtCore.SIGNAL('outputChanged'), self)
        #print "Events:", self.events
        ##display events
        
    def getEvents(self):
        return self.events
        
    def preprocess(self, data):
        """Run all selected preprocessing steps on data, return the resulting array"""
        return self.ctrl.preFilterList.processData(data)
        
        
        #orig = data
        #dt = data.xvals('Time')[1] - data.xvals('Time')[0]
        
        #if self.ctrl.denoiseCheck.isChecked():
            #data = denoise(data)
            
        #if self.ctrl.lowPassCheck.isChecked():
            #data = lowPass(data, self.ctrl.lowPassSpin.value(), dt=dt)
        #if self.ctrl.highPassCheck.isChecked():
            #data = highPass(data, self.ctrl.highPassSpin.value(), dt=dt)
            
        #if self.ctrl.expDeconvolveCheck.isChecked():
            #data = diff(data) * self.ctrl.expDeconvolveSpin.value() / dt + data[:-1]
        
        #if self.ctrl.detrendCheck.isChecked():
            #if self.ctrl.detrendMethodCombo.currentText() == 'Linear':
                #data = signal.detrend(data)
            #elif self.ctrl.detrendMethodCombo.currentText() == 'Adaptive':
                #data = removeBaseline(data, dt=dt)
            #else:
                #raise Exception("detrend method not yet implemented.")
        ##data = MetaArray(data, info=orig.infoCopy())
        
        #return data
                
        
        
    def findEvents(self, data):
        """Locate events in the data based on GUI settings selected. Generally only for internal use."""
        #dt = data.xvals('Time')[1] - data.xvals('Time')[0]
        if self.ctrl.detectMethodCombo.currentText() == 'Stdev. Threshold':
            events = stdevThresholdEvents(data, self.ctrl.stThresholdSpin.value())
            #stdev = data.std()
            #mask = abs(data) > stdev * self.ctrl.stThresholdSpin.value()
            #starts = argwhere(mask[1:] * (1-mask[:-1]))[:,0]
            #ends = argwhere((1-mask[1:]) * mask[:-1])[:,0]
            #if len(ends) > 0 and len(starts) > 0:
                #if ends[0] < starts[0]:
                    #ends = ends[1:]
                #if starts[-1] > ends[-1]:
                    #starts = starts[:-1]
                
                
            #lengths = ends-starts
            #events = empty(starts.shape, dtype=[('start',int), ('len',float), ('sum',float), ('peak',float)])
            #events['start'] = starts
            #events['len'] = lengths
            
            #if len(starts) == 0 or len(ends) == 0:
                #return events
            
            #for i in range(len(starts)):
                #d = data[starts[i]:ends[i]]
                #events['sum'][i] = d.sum()
                #if events['sum'][i] > 0:
                    #peak = d.max()
                #else:
                    #peak = d.min()
                #events['peak'][i] = peak
            
        elif self.ctrl.detectMethodCombo.currentText() == 'Zero-crossing':
            minLen = self.ctrl.zcLenAbsThresholdSpin.value()
            minPeak = self.ctrl.zcAmpAbsThresholdSpin.value()
            minSum = self.ctrl.zcSumAbsThresholdSpin.value()
            noiseThresh = self.ctrl.zcSumRelThresholdSpin.value()
            events = findEvents(data, minLength=minLen, minPeak=minPeak, minSum=minSum, noiseThreshold=noiseThresh)
        elif self.ctrl.detectMethodCombo.currentText() == 'Clements-Bekkers':
            rise = self.ctrl.cbRiseTauSpin.value()
            decay = self.ctrl.cbFallTauSpin.value()
            template = expTemplate(dt, rise, decay, rise*2, (rise+decay)*4)
            events = cbTemplateMatch(data, template, self.ctrl.cbThresholdSpin.value())
        else:
            raise Exception("Event detection method not implemented yet.")
        return events
        
    def processData(self, data, display=False, analyze=True):
        """Returns a list of record arrays - each record array contains the events detected in one trace.
                Arguments:
                    data - a list of traces"""
                    
        ## Clear plots
        if display:
            self.analysisPlot.clear()
            self.dataPlot.clear()
            self.templatePlot.clear()
            self.tickGroups = []
        events = []

        ## Plot raw data
        for i in range(len(data)):
            if display:
                color = float(i)/(len(data))*0.7
                pen = mkPen(hsv=[color, 0.8, 0.7])
                self.dataPlot.plot(data[i], pen=pen)
        
        if not (analyze and self.analysisEnabled):
            return []
            
        ## Find events in all traces
        for i in range(len(data)):
            #p.mark('start trace %d' % i)
            d = data[i]
            if len(d) < 2:
                raise Exception("Data appears to be invalid for event detection: %s" % str(data))
            
            ## Preprocess this trace
            ppd = self.preprocess(d)
            timeVals = d.xvals('Time')[:len(ppd)]  ## preprocess may have shortened array, make sure time matches
            
            ## Find events
            eventList = self.findEvents(ppd)
            if len(eventList) > 200:
                print "Warning--detected %d events; only showing first 200." % len(eventList)
            eventList = eventList[:200]   ## Only take first 200 events to avoid overload
            events.append(eventList)
            
            ## Plot filtered data, stacked events
            if display:
                color = float(i)/(len(data))*0.7
                pen = mkPen(hsv=[color, 0.8, 0.7])
                
                self.analysisPlot.plot(ppd, x=timeVals, pen=pen)
                tg = VTickGroup(view=self.analysisPlot)
                tg.setPen(pen)
                tg.setYRange([0.8, 1.0], relative=True)
                tg.setXVals(d.xvals('Time')[eventList['start']])
                #print "set tick locations:", timeVals[eventList['start']]
                self.tickGroups.append(tg)
                self.analysisPlot.addItem(tg)
                
                ## generate triggered stacks for plotting
                #stack = triggerStack(d, eventList['start'], window=[-100, 200])
                #negPen = mkPen([0, 0, 200])
                #posPen = mkPen([200, 0, 0])
                #print stack.shape
                #for j in range(stack.shape[0]):
                    #base = median(stack[j, 80:100])
                    
                    #if eventList[j]['sum'] > 0:
                        #scale = stack[j, 100:100+eventList[j]['len']].max() - base
                        #pen = posPen
                        #params = {'sign': 1}
                    #else:
                        #length = eventList[j]['len']
                        #if length < 1:
                            #length = 1
                        #scale = base - stack[j, 100:100+length].min()
                        #pen = negPen
                        #params = {'sign': -1}
                    #self.templatePlot.plot((stack[j]-base) / scale, pen=pen, params=params)
        
        return events
        
        
    #def tauChanged(self):
    #    self.recalculate()
    #    
    #def lowPassChanged(self):
    #    self.recalculate()
    #    
    #def thresholdChanged(self):
    #    self.recalculate()
    #    
    #def setTau(self, val):
    #    self.tauSpin.setValue(val)
    #    
    #def setLowPass(self, val):
    #    self.lowPassSpin.setValue(val)
    #    
    #def setThreshold(self, val):
    #    self.thresholdSpin.setValue(val)
        
    def clear(self):
        self.analysisPlot.clear()
        self.templatePlot.clear()
        self.dataPlot.clear()
        self.events = []
        self.data = []
        

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
        bwtop = QtGui.QSplitter()
        bwtop.setOrientation(QtCore.Qt.Horizontal)
        self.cw.insertWidget(1, bwtop)
        self.canvas = Canvas()
        QtCore.QObject.connect(self.canvas.view, QtCore.SIGNAL('mouseReleased'), self.canvasClicked)
        self.ctrl = Ui_UncagingControlWidget()
        self.ctrlWidget = QtGui.QWidget()
        bwtop.addWidget(self.ctrlWidget)
        self.ctrl.setupUi(self.ctrlWidget)
        bwtop.addWidget(self.canvas)
        self.scaleBar = ScaleBar(self.canvas.view, 1e-3, width = -5)
        self.scaleBar.setZValue(1000000)
        self.canvas.view.scene().addItem(self.scaleBar)
        self.colorScaleBar = ColorScaleBar(self.canvas.view, [10,150], [-10,-10])
        self.colorScaleBar.setZValue(1000000)
        self.canvas.view.scene().addItem(self.colorScaleBar)
        QtCore.QObject.connect(self.ctrl.recolorBtn, QtCore.SIGNAL('clicked()'), self.recolor)
        self.ctrl.directTimeSpin.setValue(4.0)
        self.ctrl.poststimTimeSpin.setRange(1.0, 1000.0)
        self.ctrl.colorSpin1.setValue(8.0)
        self.ctrl.colorSpin3.setValue(99)
        self.ctrl.poststimTimeSpin.setValue(300.0)
        self.ctrl.eventFindRadio.setChecked(True)
        self.ctrl.useSpontActCheck.setChecked(False)
        self.ctrl.gradientRadio.setChecked(True)
        self.ctrl.medianCheck.setChecked(True)
        
        
        
        #self.plot = PlotWidget()
        self.plot = EventMatchWidget()
        self.cw.addWidget(self.plot)
        
        self.cw.setStretchFactor(0, 1)
        self.cw.setStretchFactor(1, 5)
        self.cw.setStretchFactor(2, 20)
        
        QtCore.QObject.connect(self.plot.stateGroup, QtCore.SIGNAL('changed'), self.resetAnalysisCache)
        
        self.z = 0
        self.resize(1000, 600)
        self.show()
        self.scanItems = []
        self.scanAvgItems = []
        self.imageItems = []
        self.currentTraces = []
        self.noiseThreshold = 2.0
        self.eventTimes = []
        self.analysisCache = empty(len(self.scanItems),
            {'names': ('eventsValid', 'eventList', 'preEvents', 'dirEvents', 'postEvents', 'stdev', 'preChargePos', 'preChargeNeg', 'dirCharge', 'postChargePos', 'postChargeNeg'),
             'formats':(object, object, object, object, object, float, float, float, float, float, float)})
        
        
    def addImage(self, img=None, fd=None):
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
            
        img = img.view(ndarray)
        if img.ndim == 3:
            img = img.max(axis=0)
        #print pos, ps, img.shape, img.dtype, img.max(), img.min()
        item = ImageItem(img)
        self.canvas.addItem(item, pos, scale=ps, z=self.z, name=fd.shortName())
        self.z += 1
        self.imageItems.append(item)

    def addScan(self):
        dh = getManager().currentFile
        if len(dh.info()['protocol']['params']) > 0:
            dirs = [dh[d] for d in dh.subDirs()]
        else:
            dirs = [dh]
        appendIndex = self.analysisCache.size
        a = empty(len(self.scanItems) + len(dirs), dtype = self.analysisCache.dtype)
        a[:appendIndex] = self.analysisCache
        self.analysisCache = a
        for d in dirs: #d is a directory handle
            #d = dh[d]
            if 'Scanner' in d.info() and 'position' in d.info()['Scanner']:
                pos = d.info()['Scanner']['position']
                if 'spotSize' in d.info()['Scanner']:
                    size = d.info()['Scanner']['spotSize']
                else:
                    size = self.defaultSize
                item = UncagingSpot(d)
                item.index = appendIndex
                self.analysisCache['eventsValid'][appendIndex] = False
                appendIndex += 1
                item.position = pos
                item.size = size
                item.setBrush(QtGui.QBrush(QtGui.QColor(100,100,200,0)))                 
                self.canvas.addItem(item, [pos[0] - size*0.5, pos[1] - size*0.5], scale=[size,size], z = self.z, name=[dh.shortName(), d.shortName()])
                self.scanItems.append(item)
                
                ## Find out if this spot is the "same" as any existing average spots
                avgSpot = None
                for s in self.scanAvgItems:
                    if s.size == size and abs(s.position[0] - pos[0]) < size/10. and abs(s.position[1] - pos[1]) < size/10.:
                        avgSpot = s
                        break
                    
                if avgSpot is None: 
                    ## If not, create a new average spot 
                    avgSpot = UncagingSpot()
                    avgSpot.position = pos
                    avgSpot.size = size
                    avgSpot.setBrush(QtGui.QBrush(QtGui.QColor(100,100,200, 100)))                 
                    self.canvas.addItem(avgSpot, [pos[0] - size*0.5, pos[1] - size*0.5], scale=[size,size], z = self.z+10000, name=["Averages", "spot%03d"%len(self.scanAvgItems)])
                    self.scanAvgItems.append(avgSpot)
                
                avgSpot.sourceItems.append(item)
                
            else:
                print "Skipping directory %s" %d.name()
        self.analysisCache = self.analysisCache[:appendIndex]    
        self.z += 1
        
    def clearImage(self):
        for item in self.imageItems:
            self.canvas.removeItem(item)
        self.imageItems = []
        
        
    def clearScan(self):
        for item in self.scanItems:
            self.canvas.removeItem(item)
        for item in self.scanAvgItems:
            self.canvas.removeItem(item)
        self.scanItems = []
        self.scanAvgItems = []
        self.currentTraces = []
        self.eventTimes = []
        self.analysisCache = empty(len(self.scanItems),
            {'names': ('eventsValid', 'eventList', 'preEvents', 'dirEvents', 'postEvents', 'stdev', 'preChargePos', 'preChargeNeg', 'dirCharge', 'postChargePos', 'postChargeNeg'),
             'formats':(object, object, object, object, object, float, float, float, float, float, float)})
        
    def resetAnalysisCache(self):
        self.analysisCache['eventsValid'] = False
        
    def recolor(self):
        #for i in self.scanItems:
            #color = self.spotColor(i)
            #i.setBrush(QtGui.QBrush(color))
        progressDlg = QtGui.QProgressDialog("Detecting events in all traces...", "Cancel", 0, 100)
        progressDlg.setWindowModality(QtCore.Qt.WindowModal)
        #self.progressDlg.setMinimumDuration(0)
        for n in range(len(self.scanItems)):
            i = self.scanItems[n]
            events, pre, direct, post, q, stdev = self.getEventLists(i)
            self.analysisCache[i.index]['eventList'] = events
            self.analysisCache[i.index]['eventsValid'] = True
            self.analysisCache[i.index]['preEvents'] = pre
            self.analysisCache[i.index]['dirEvents'] = direct
            self.analysisCache[i.index]['postEvents'] = post
            self.analysisCache[i.index]['stdev'] = stdev
            i.laserTime = q
            self.analyzeEvents(i)
            progressDlg.setValue(100.*float(n)/len(self.scanItems))
            QtGui.QApplication.instance().processEvents()
            if progressDlg.wasCanceled():
                progressDlg.setValue(100)
                return
        progressDlg.setValue(100)
        self.colorSpots()

            
    def getClampData(self, dh):
        """Returns a clamp.ma
                Arguments:
                    dh - a directory handle"""
        try:
            data = dh['Clamp1.ma'].read()
            #print "Loaded", dh['Clamp1.ma'].name()
        except:
            data = dh['Clamp2.ma'].read()
            #print "Loaded", dh['Clamp2.ma'].name()
        #if data.hasColumn('Channel', 'primary'):
        #    data = data['Channel': 'primary']
        #elif data.hasColumn('Channel', 'scaled'):
        #    data = data['Channel': 'scaled']
        if data._info[0]['name'] == 'Channel':   ### Stupid. Rename column to support some older files.
            cols = data._info[0]['cols']
            for i in range(len(cols)):
                if cols[i]['name'] == 'scaled':
                    cols[i]['name'] = 'primary'
            
        data['Channel':'primary'] = denoise(data['Channel':'primary'], threshold = 5)
        #data = removeBaseline(data)
        #data = lowPass(data, 2000)
        return data
        
        
    #def findEvents(self, data):
        #return findEvents(data, noiseThreshold=self.noiseThreshold)
    def getLaserTime(self, d):
        """Returns the time of laser stimulation in seconds.
                Arguments:
                    d - a directory handle"""
        q = d.getFile('Laser-UV.ma').read()['QSwitch']
        return argmax(q)/q.infoCopy()[-1]['rate']
        
    def getEventLists(self, i):
        #if not self.plot.analysisEnabled:
        #    return QtGui.QColor(100,100,200)
        data = self.getClampData(i.source)['Channel':'primary']
        if self.analysisCache[i.index]['eventsValid'] == False:
            #print "Recomputing events...."
            a = self.plot.processData([data])[0] #events is an array
            events = a[a['len'] > 2] #trying to filter out noise
        else:
            events = self.analysisCache[i.index]['eventList']
        #for i in range(len(events)):
        #    if events[i]['peak'] > (events[i]['sum'])/10:
        #        events= delete(events, events[i])
        #
        times = data.xvals('Time')
        self.eventTimes.extend(times[events['start']])
        q = self.getLaserTime(i.source)
        stimTime = q - 0.001
        dirTime = q + self.ctrl.directTimeSpin.value()/1000
        endTime = q + self.ctrl.poststimTimeSpin.value()/1000
        stimInd = argwhere((times[:-1] <= stimTime) * (times[1:] > stimTime))[0,0]
        dirInd = argwhere((times[:-1] <= dirTime) * (times[1:] > dirTime))[0,0]
        endInd = argwhere((times[:-1] <= endTime) * (times[1:] > endTime))[0,0]
        dt = times[1]-times[0]
        
        times = events['start']
        pre = events[times < stimInd]
        direct = events[(times > stimInd) * (times < dirInd)]
        post = events[(times > dirInd) * (times < endInd)]
        
        #pos = (post[post['sum'] > 0]['sum'].sum() / (endTime-dirTime)) - (pre[pre['sum'] > 0]['sum'].sum() / stimTime)
        #neg = -(post[post['sum'] < 0]['sum'].sum() / (endTime-dirTime)) - (pre[pre['sum'] < 0]['sum'].sum() / stimTime)
        
        #dir = (abs(direct['sum']).sum() / (dirTime-stimTime)) - (abs(pre['sum']).sum() / stimTime)
        
        stdev = data.std() / dt
        
        return events, pre, direct, post, q, stdev
        
    def analyzeEvents(self, item):
        pre = self.analysisCache[item.index]['preEvents']
        post = self.analysisCache[item.index]['postEvents']
        direct = self.analysisCache[item.index]['dirEvents']
        stimTime = item.laserTime - 0.001
        dirTime = item.laserTime + self.ctrl.directTimeSpin.value()/1000
        endTime = item.laserTime + self.ctrl.poststimTimeSpin.value()/1000
        
        if self.ctrl.useSpontActCheck.isChecked():
            pos = (post[post['sum'] > 0]['sum'].sum() / (endTime-dirTime)) - (pre[pre['sum'] > 0]['sum'].sum() / stimTime)
            neg = ((post[post['sum'] < 0]['sum'].sum() / (endTime-dirTime)) - (pre[pre['sum'] < 0]['sum'].sum() / stimTime))
            dir = (abs(direct['sum']).sum() / (dirTime-stimTime)) - (abs(pre['sum']).sum() / stimTime)
            self.analysisCache[item.index]['postChargePos'] = pos
            self.analysisCache[item.index]['postChargeNeg'] = neg
            self.analysisCache[item.index]['dirCharge'] = dir
        else:
            pos = (post[post['sum'] > 0]['sum'].sum() / (endTime-dirTime))
            neg = (post[post['sum'] < 0]['sum'].sum() / (endTime-dirTime))
            prePos = pre[pre['sum'] > 0]['sum'].sum() / stimTime
            preNeg = (pre[pre['sum'] < 0]['sum'].sum() / stimTime)
            self.analysisCache[item.index]['postChargePos'] = pos
            self.analysisCache[item.index]['postChargeNeg'] = neg
            self.analysisCache[item.index]['preChargePos'] = prePos
            self.analysisCache[item.index]['preChargeNeg'] = preNeg
            self.analysisCache[item.index]['dirCharge'] = 0
            
    def colorSpots(self):
        if self.ctrl.gradientRadio.isChecked():
            maxcharge = stats.scoreatpercentile(self.analysisCache['postChargeNeg'], per = self.ctrl.colorSpin1.value())
            spont = self.analysisCache['preChargeNeg'].mean()
            #print "spont activity:", spont
            for item in self.scanAvgItems:
                if item.source is not None:  ## this is a single item
                    negCharge = self.analysisCache[item.index]['postChargeNeg']
                    numDirectEvents = len(self.analysisCache[item.index]['dirEvents'])
                    if numDirectEvents == 0:
                        directeventsflag = True
                    else:
                        directeventsflag = False
                else:    ## this is an average item
                    negCharges = array([self.analysisCache[i.index]['postChargeNeg'] for i in item.sourceItems])
                    numDirectEventses = array([len(self.analysisCache[i.index]['dirEvents']) for i in item.sourceItems])
                    if self.ctrl.medianCheck.isChecked():
                        if len(negCharges[negCharges < 0]) > len(negCharges)/2.0: ###Errs on side of false negatives, but averages all non-zero charges
                            negCharge = mean(negCharges[negCharges<0])
                            #numDirectEvents = median(numDirectEventses)
                        else:
                            negCharge = 0
                            #numDirectEvents = mean(numDirectEventses)
                    if len(numDirectEventses[numDirectEventses > 0]) > len(numDirectEventses)/2:
                        directeventsflag = True
                    else:
                        directeventsflag = False
                
                ## Set color based on strength of negative events
                color = self.ctrl.gradientWidget.getColor(clip(negCharge/maxcharge, 0, 1))
                if negCharge > spont:
                    color.setAlpha(100)
                

                ## Traces with no events are transparent
                if abs(negCharge) < 1e-16:
                    color = QtGui.QColor(0,0,0,0)
                
                

                ## Traces with events below threshold are transparent
                if negCharge >= stats.scoreatpercentile(self.analysisCache['postChargeNeg'][self.analysisCache['postChargeNeg'] < 0], self.ctrl.colorSpin3.value()):
                    color = QtGui.QColor(0,0,0,0)
                
                ## Direct events have white outlines
                if directeventsflag == True:
                    pen = mkPen(color = QtGui.QColor(0,0,0,200), width = 2)
                    if abs(negCharge) < 1e-16: 
                        color = QtGui.QColor(0,0,0,200)
                else:
                    pen = QtGui.QPen()

                item.setBrush(QtGui.QBrush(color))
                item.setPen(pen)

                #print "Color set."
            self.colorScaleBar.show()

            self.colorScaleBar.setGradient(self.ctrl.gradientWidget.getGradient())
            self.colorScaleBar.setLabels({str(maxcharge):1,
                                          str(stats.scoreatpercentile(self.analysisCache['postChargeNeg'][self.analysisCache['postChargeNeg'] < 0], self.ctrl.colorSpin3.value())):0,
                                          "--spont":spont/(maxcharge - stats.scoreatpercentile(self.analysisCache['postChargeNeg'][self.analysisCache['postChargeNeg'] < 0], self.ctrl.colorSpin3.value()))})

        else:
            self.colorScaleBar.hide()
            for item in self.scanAvgItems:
                if item.source is not None:  ## this is a single item
                    items = [item]
                else:    ## this is an average item
                    items = item.sourceItems
                    #negCharges = array([self.analysisCache[i.index]['postChargeNeg'] for i in item.sourceItems]) 
                    #numDirectEventses = [len(self.analysisCache[i.index]['dirEvents']) for i in item.sourceItems]
                    
                postZPos = [self.analysisCache[i.index]['postChargePos'] / self.analysisCache[i.index]['stdev'] for i in items]
                postZNeg = [-self.analysisCache[i.index]['postChargeNeg'] / self.analysisCache[i.index]['stdev'] for i in items]
                dirZ = [self.analysisCache[i.index]['dirCharge']/self.analysisCache[i.index]['stdev'] for i in items]
                    
                red = clip(log(max(1.0, median(postZPos)+1))*255, 0, 255) 
                blue = clip(log(max(1.0, median(postZNeg)+1))*255, 0, 255)
                green = clip(log(max(1.0, min(dirZ)+1))*255, 0, 255)
                color = QtGui.QColor(red, green, blue, max(red, green, blue))
            
                item.setBrush(QtGui.QBrush(color))
                #item.setPen(pen)
            
            

   
    def canvasClicked(self, ev, analyze=True):
        ###should probably make mouseClicked faster by using cached data instead of calling processData in eventFinderWidget each time
        """Makes self.currentTraces a list of data corresponding to items on a canvas under a mouse click. Each list item is a tuple where the first element
           is an array of clamp data, and the second is the directory handle for the Clamp.ma file."""
        if ev.button() != QtCore.Qt.LeftButton:
            return []
           
        spots = self.canvas.view.items(ev.pos())
        spots = [s for s in spots if isinstance(s, UncagingSpot)]
        if len(spots) == 0:
            return []
        self.currentTraces = []
        for s in spots:
            d = self.loadTrace(s)
            if d is not None:
                self.currentTraces.append(d)
            #if hasattr(i, 'source') and i.source is not None:
                #print 'postEvents:', self.analysisCache[i.index]['postEvents']
                #print 'postChargeNeg:', self.analysisCache[i.index]['postChargeNeg']
        self.plot.setData([i[0]['Channel':'primary'] for i in self.currentTraces], analyze=analyze)
        return spots
        

        
    def loadTrace(self, item):
        """Returns a tuple where the first element is a clamp.ma, and the second is its directory handle."""
        if not hasattr(item, 'source') or item.source is None:
            return
        dh = item.source
        data = self.getClampData(dh)
        return data, dh
        
class STDPWindow(UncagingWindow):
    ###NEED:  add labels to LTP plot?, figure out how to get/display avg epsp time and avg spike time, 
    def __init__(self):
        UncagingWindow.__init__(self)
        bwtop = QtGui.QSplitter()
        bwtop.setOrientation(QtCore.Qt.Horizontal)
        self.cw.insertWidget(1, bwtop)
        self.plotBox = QtGui.QTabWidget()
        self.LTPplot = PlotWidget()
        self.line = InfiniteLine(self.LTPplot, 1.0, movable = True)
        self.finalTimeRgn = LinearRegionItem(self.LTPplot, orientation='vertical', vals=[30, 50])
        self.LTPplot.addItem(self.finalTimeRgn)
        self.LTPplot.addItem(self.line)
        self.plotBox.addTab(self.LTPplot, 'LTP')
        self.avgPlot = PlotWidget()
        self.plotBox.addTab(self.avgPlot, 'Averages')
        self.results = {}
        #self.dictView = DictView(self.results)
        self.resultsTable = QtGui.QTableWidget()
        bwtop.addWidget(self.canvas)
        bwtop.addWidget(self.plotBox)
        #bwtop.addWidget(self.dictView)
        bwtop.addWidget(self.resultsTable)
        bwbottom = QtGui.QSplitter()
        bwbottom.setOrientation(QtCore.Qt.Horizontal)
        self.cw.insertWidget(2, bwbottom)
        self.stdpCtrl = Ui_StdpCtrlWidget()
        self.stdpCtrlWidget = QtGui.QWidget()
        bwbottom.addWidget(self.stdpCtrlWidget)
        self.stdpCtrl.setupUi(self.stdpCtrlWidget)
        self.stdpCtrl.thresholdSpin.setValue(4.0)
        self.stdpCtrl.durationSpin.setRange(0,1000)
        self.stdpCtrl.durationSpin.setValue(200)
        self.stdpCtrl.apthresholdSpin.setRange(-100, 100)
        self.stdpCtrl.apthresholdSpin.setValue(0)
        self.stdpCtrl.apExclusionCheck.setChecked(True)
        self.stdpCtrl.slopeWidthSpin.setValue(2.0)
        bwbottom.addWidget(self.plot)
        self.plot.enableAnalysis(True)
        self.ctrlWidget.hide()
        self.colorScaleBar.hide()
        self.epspStats = None

        self.slopeMark1 = QtGui.QGraphicsLineItem()
        self.slopeMark1.setPen(QtGui.QPen(QtGui.QColor(255,255,255)))
        self.slopeMark2 = QtGui.QGraphicsLineItem()
        self.slopeMark2.setPen(QtGui.QPen(QtGui.QColor(255,255,255)))
        self.slopeMark3a = QtGui.QGraphicsLineItem()
        self.slopeMark3a.setPen(QtGui.QPen(QtGui.QColor(0,255,0)))
        self.slopeMark4a = QtGui.QGraphicsLineItem()
        self.slopeMark4a.setPen(QtGui.QPen(QtGui.QColor(0,0,255)))
        self.slopeMark3b = QtGui.QGraphicsLineItem()
        self.slopeMark3b.setPen(QtGui.QPen(QtGui.QColor(0,255,0)))
        self.slopeMark4b = QtGui.QGraphicsLineItem()
        self.slopeMark4b.setPen(QtGui.QPen(QtGui.QColor(0,0,255)))
        self.stdpCtrl.slopeWidthSpin.setOpts(value=2e-3, dec=True, step=1, minStep=1e-4, bounds=[1e-4, None], suffix='s', siPrefix=True)
        
        self.plot.analysisPlot.show()

        self.line.connect(QtCore.SIGNAL('positionChanged'), self.lineMoved)
        bwtop.setStretchFactor(0, 2)
        bwtop.setStretchFactor(1, 5)
        bwtop.setStretchFactor(0, 5)

        
        
        
    def canvasClicked(self, ev):
        if ev.button() != QtCore.Qt.LeftButton:
            return
        spots = UncagingWindow.canvasClicked(self, ev)
        if len(spots) == 0:
            return
        
        self.epspStats = zeros(len(self.currentTraces), dtype=[
            ('currentTracesIndex', int), 
            ('pspMask', bool), 
            ('preMask', bool), 
            ('postMask', bool), 
            ('finalMask', bool),
            ('conditioningMask', bool), 
            ('unixtime', float), 
            ('slope', float), 
            #('derslope', float), 
            #('derslopetime', float), 
            ('amp', float), 
            ('flux', float), 
            ('epsptime', float), 
            #('derepsptime', float), 
            ('time', float), 
            ('normSlope', float), 
            #('normDerSlope', float), 
            ('normAmp', float), 
            ('normFlux', float), 
            ('spikeTime', float),
        ])
            #{'names':('currentTracesIndex', 'pspMask', 'conditioningMask', 'unixtime', 'slope', 'derslope','derslopetime', 'amp', 'flux', 'epsptime', 'derepsptime', 'time', 'normSlope', 'normDerSlope','normAmp', 'normFlux', 'spikeTime'),
             #'formats': (int, bool, bool, float, float, float, float, float, float, float, float, float, float, float, float, float, float)})
             
    
        ## Initialize PSP stats array
        for i in range(len(self.currentTraces)):
            self.epspStats[i]['currentTracesIndex'] = i
            self.epspStats[i]['pspMask']            = False
            self.epspStats[i]['conditioningMask']   = False
            self.epspStats[i]['unixtime']           = self.getUnixTime(self.currentTraces[i])
            
            if self.currentTraces[i][0]['Channel':'Command'].max() >= 0.1e-09:
                self.epspStats[i]['conditioningMask'] = True
                cmdChannel = self.currentTraces[i][0]['Channel':'Command']
                priChannel = self.currentTraces[i][0]['Channel':'primary']
                stimtime = argwhere(cmdChannel == cmdChannel.max())
                first    = argwhere(priChannel == priChannel[stimtime[0]:stimtime[0]+90].max())
                if len(first) > 0:
                    firstspikeindex = first[0]
                    firstspike = priChannel.xvals('Time')[firstspikeindex]
                    self.epspStats[i]['spikeTime'] = firstspike
        
        ## Sort all trace analysis records. 
        ##   Note that indexes in epspStats and currentTraces will no longer match.
        self.epspStats.sort(order = 'unixtime') 
        
        ## compute normalized time in minutes past start
        mintime = self.epspStats['unixtime'].min()
        self.epspStats['time'] = (self.epspStats['unixtime'] - mintime) / 60
            
        
        
        
        ## Sort data into pre- and post- regions
        condtime = (
            self.epspStats[self.epspStats['conditioningMask']]['unixtime'].min(), 
            self.epspStats[self.epspStats['conditioningMask']]['unixtime'].max()
        )
        self.epspStats['preMask']  = self.epspStats['unixtime'] < condtime[0]
        self.epspStats['postMask'] = self.epspStats['unixtime'] > condtime[1]
        finalRange = self.finalTimeRgn.getRegion()
        self.epspStats['finalMask'] = self.epspStats['postMask'] * (self.epspStats['time'] > finalRange[0]) * (self.epspStats['time'] < finalRange[1])
        preIndexes  = self.epspStats[self.epspStats['preMask' ]]['currentTracesIndex']
        postIndexes = self.epspStats[self.epspStats['postMask']]['currentTracesIndex']
        
        
        ## determine likely times for first response after stim.
        preEvents  = self.getEvents(self.epspStats['preMask'])
        postEvents = self.getEvents(self.epspStats['postMask'])
        finalEvents = self.getEvents(self.epspStats['finalMask'])
        
        preSearchStart  = self.getEpspSearchStart(preEvents)
        postSearchStart = self.getEpspSearchStart(postEvents)
        
        
        ## Analyze pre and post traces for events
        if preSearchStart is None or postSearchStart is None:
            print "Could not determine start time for PSP search; will not calculate stats.", preSearchStart, postSearchStart
        else:
            for j in range(len(self.epspStats)):
                i = self.epspStats[j]['currentTracesIndex']
                if i in preIndexes:
                    t,s,a,f,e = self.EPSPstats(self.currentTraces[i], preSearchStart)
                elif i in postIndexes:
                    t,s,a,f,e = self.EPSPstats(self.currentTraces[i], postSearchStart)
                self.epspStats[j]['amp'] = a
                self.epspStats[j]['flux'] = f
                #self.epspStats[i]['derslope'] = ds
                #self.epspStats[i]['derepsptime'] = de
                #self.epspStats[i]['derslopetime'] = dst
                if s != None:
                    #print "Setting pspMask index %i to True" %i
                    self.epspStats[j]['pspMask']  = True
                    self.epspStats[j]['slope']    = s
                    self.epspStats[j]['epsptime'] = e
                if self.stdpCtrl.apExclusionCheck.isChecked():
                    if self.currentTraces[i][0]['Channel':'primary'].max() > self.stdpCtrl.apthresholdSpin.value()/1000:  ##exclude traces with action potentials from plot
                        #print "Setting pspMask index %i to False" %i
                        self.epspStats[j]['pspMask'] = False
                    
            
        ## mask for all traces in the base region with no APs
        prePspMask    = self.epspStats['preMask']  * self.epspStats['pspMask']  
        postPspMask   = self.epspStats['postMask'] * self.epspStats['pspMask']  
        finalPspMask  = self.epspStats['finalMask'] * self.epspStats['pspMask']  
        prePspStats   = self.epspStats[prePspMask]
        postPspStats  = self.epspStats[postPspMask]
        finalPspStats = self.epspStats[finalPspMask]
        
        ## Times (indexes) of first event selected from each trace
        preEpspTimes  = self.epspStats[prePspMask]['epsptime']
        postEpspTimes = self.epspStats[postPspMask]['epsptime']
        finalEpspTimes = self.epspStats[finalPspMask]['epsptime']
        
        ## Times of all events within search region in pre and post traces
        dt = 1e-4  ## FIXME
        #allPreEventTimes  = self.getEventTimes('pre')
        allPreEventTimes  = preEvents['start'][preEvents['start']>preSearchStart] * dt
        #allPostEventTimes = self.getEventTimes('post')
        allPostEventTimes = postEvents['start'][postEvents['start']>postSearchStart] * dt
        allFinalEventTimes = finalEvents['start'][finalEvents['start']>postSearchStart] * dt
        
        ## Compute normalized values
        for x in range(len(self.epspStats)):
            #self.epspStats[x]['time'] = (self.epspStats[x]['unixtime'] - self.epspStats['unixtime'].min()) / 60
            if self.epspStats[x]['pspMask'] == True:
                self.epspStats[x]['normSlope'] = self.epspStats[x]['slope'] / prePspStats['slope'].mean()
                self.epspStats[x]['normAmp']   = self.epspStats[x]['amp']   / prePspStats['amp'].mean()
                self.epspStats[x]['normFlux']  = self.epspStats[x]['flux']  / prePspStats['flux'].mean()
                #self.epspStats[x]['normDerSlope'] = (self.epspStats['derslope'][x])/(mean(self.epspStats[(self.epspStats['pspMask'])*baseStats]['derslope']))

        
        self.results = OrderedDict()
        statSet = [
            ('1st EPSP Time (pre)',  preEpspTimes),
            ('1st EPSP Time (post)', postEpspTimes),
            ('1st EPSP Time (final)',finalEpspTimes),
            ('EPSP Time (pre)',      allPreEventTimes),
            ('EPSP Time (post)',     allPostEventTimes),
            ('EPSP Time (final)',    allFinalEventTimes),
            ('Flux (pre)',           prePspStats['flux']),
            ('Flux (post)',          postPspStats['flux']),
            ('Flux (final)',         finalPspStats['flux']),
            ('Slope (pre)',          prePspStats['slope']),
            ('Slope (post)',         postPspStats['slope']),
            ('Slope (final)',        finalPspStats['slope']),
        ]
        for name, vals in statSet:
            self.results['Median '+name] = median(vals)
            self.results['Mean '  +name] = mean(vals)
            self.results['Stdev ' +name] = std(vals)
        #self.results['Average 1st EPSP time (pre):'] = (preEpspTimes.mean()*1000, preEpspTimes.std()*1000) 
        #self.results['Average 1st EPSP time (post):'] = (postEpspTimes.mean()*1000, postEpspTimes.std()*1000)
        #self.results['Median 1st EPSP time (pre):'] = median(preEpspTimes)*1000 
        #self.results['Median 1st EPSP time (post):'] = median(postEpspTimes)*1000
        
        #self.results['Average EPSP time (pre):'] = (allPreEventTimes.mean()*1000, allPreEventTimes.std()*1000)
        #self.results['Average EPSP time (post):'] = (allPostEventTimes.mean()*1000, allPostEventTimes.std()*1000)
        #self.results['Median EPSP time (pre):'] = median(allPreEventTimes)*1000
        #self.results['Median EPSP time (post):'] = median(allPostEventTimes)*1000
        
        #self.results['Average derEPSP time:'] = mean(self.epspStats[self.epspStats['unixtime']< endbase]['derepsptime']*1000)
        #print 'spiketime:', spiketime
        #print 'mean:', mean(spiketime)
        
        
        #self.results['Average flux (pre)'] = (prePspStats['flux'].mean(), prePspStats['flux'].std())
        #self.results['Average flux (post)'] = (postPspStats['flux'].mean(), postPspStats['flux'].std())
        #self.results['Average slope (pre)'] = (prePspStats['slope'].mean(), prePspStats['slope'].std())
        #self.results['Average slope (post)'] = (postPspStats['slope'].mean(), postPspStats['slope'].std())
        
        self.results['Number of Pre Traces']   = sum(self.epspStats['preMask'])
        self.results['Number of Post Traces']  = sum(self.epspStats['postMask'])
        self.results['Number of Final Traces'] = sum(self.epspStats['finalMask'])
        self.results['Final Period Start']     = finalRange[0]
        self.results['Final Period End']       = finalRange[1]
        
        self.results['Average 1st Spike time:'] = mean(self.epspStats[self.epspStats['conditioningMask']]['spikeTime'])*1000
        
        #self.results['Average last Spike time:'] = mean(lastspiketime)*1000
        #self.results['PSP-Spike Delay:'] = self.results['Average 1st Spike time:']-self.results['Median EPSP Time (pre):']
        #self.results['derPSP-Spike Delay:']= self.results['Average 1st Spike time:']-self.results['Average derEPSP time:']
        self.results['Change in slope(red):']      = mean(finalPspStats['normSlope'])
        self.results['Change in amp(blue):']       = mean(finalPspStats['normAmp'])
        self.results['Change in flux(green):']     = mean(finalPspStats['normFlux'])
        self.results['Change in latency(purple):'] = mean(finalPspStats['epsptime']) / mean(prePspStats['epsptime'])
        #self.results['Change in derslope(purple):'] = mean(self.epspStats[(self.epspStats['unixtime']> endbase)*(self.epspStats['pspMask'])]['normDerSlope'])
        self.setResultsTable(self.results)
        #self.dictView.setData(self.results)
        
        self.LTPplot.clearPlots()
        #self.LTPplot.addItem(self.line)
        
        pspStats = self.epspStats[self.epspStats['pspMask']]
        
        ## plot flux
        self.LTPplot.plot(data = pspStats['normFlux'], x=pspStats['time'], pen=mkPen([0, 255, 0]))
        
        ## plot amplitude
        self.LTPplot.plot(data = pspStats['normAmp'], x=pspStats['time'], pen=mkPen([0, 0, 255]))
        #self.LTPplot.plot(data = self.epspStats[self.epspStats['pspMask']]['normDerSlope'], x = self.epspStats[self.epspStats['pspMask']]['time'], pen = mkPen([255, 0, 255]))
        
        ## plot slope
        self.LTPplot.plot(data = pspStats['normSlope'], x=pspStats['time'], pen=mkPen([255, 0, 0]))
        
        ## plot latency
        self.LTPplot.plot(data = pspStats['epsptime'] / preEpspTimes.mean(), x=pspStats['time'], pen=mkPen([255, 0, 255]))
        
        self.showAveragePlots()
        

    def setResultsTable(self, data):
        t = self.resultsTable
        t.setColumnCount(3)
        t.setRowCount(len(data))
        for i in range(len(data)):
            k = data.keys()[i]
            v = data[k]
            i1 = QtGui.QTableWidgetItem(k)
            t.setItem(i, 0, i1)
            if type(v) is tuple:
                i2 = [QtGui.QTableWidgetItem("%0.04g" % x) for x in v]
                for j in range(len(i2)):
                    t.setItem(i, j+1, i2[j])
            else:
                i2 = QtGui.QTableWidgetItem("%0.04g" % v)
                t.setItem(i, 1, i2)
        self.copyResultsTable()
                
    def copyResultsTable(self):
        """Copy results table to clipboard."""
        s = ''
        t = self.resultsTable
        for r in range(t.rowCount()):
            row = []
            for c in range(t.columnCount()):
                item = t.item(r, c)
                if item is not None:
                    row.append(str(item.text()))
                else:
                    row.append('')
            s += ('\t'.join(row) + '\n')
        QtGui.QApplication.clipboard().setText(s)

    def showAveragePlots(self):
        stats = self.epspStats
        masks = [
            (stats['preMask'],                     mkPen((0, 0, 255))),
            (stats['preMask'] * stats['pspMask'],  mkPen((0, 150, 255))),
            (stats['conditioningMask'],            mkPen((255, 0, 255))),
            (stats['postMask'],                    mkPen((255, 0, 0))),
            (stats['postMask'] * stats['pspMask'], mkPen((255, 150, 0))),
            (stats['finalMask'],                    mkPen((0, 255, 0))),
            (stats['finalMask'] * stats['pspMask'], mkPen((150, 255, 0))),
        ]
        self.avgPlot.clear()
        for mask, pen in masks:
            inds = stats[mask]['currentTracesIndex']
            traces = [self.currentTraces[i][0]['Channel': 'primary'] for i in inds]
            avg = vstack(traces).mean(axis=0)
            ma = MetaArray(avg, info=traces[0].infoCopy())
            self.avgPlot.plot(ma, pen=pen)
        
    

    def getUnixTime(self, data):
        time = data[0]['Channel':'primary'].infoCopy()[-1]['startTime']
        return time
    
    def getBaselineRgn(self, data, q=None):
        if q == None:
            q = self.getLaserTime(data[1])
        base = data[0]['Channel':'primary']['Time': 0.001:q]
        return base
    
    def getPspRgn(self, data, cutoff, q=None):
        if q == None:
            q = self.getLaserTime(data[1])
        pspRgn = data[0]['Channel':'primary']['Time': q:(q + cutoff)]
        return pspRgn
    
    def getPspFlux(self, data, pspRgn=None, base=None):
        if pspRgn == None:
            pspRgn = self.getPspRgn(data, self.stdpCtrl.durationSpin.value()/1000.0)
        if base == None:
            base = self.getBaselineRgn(data)
        flux = pspRgn.sum() -(base.mean()*pspRgn.shape[0])
        return flux
    
    def getPspAmp(self, data, pspRgn=None, base=None):
        amp = 0
        if pspRgn == None:
            pspRgn = self.getPspRgn(data, self.stdpCtrl.durationSpin.value()/1000.0)
        if base == None:
            base = self.getBaselineRgn(data)
        max = pspRgn.max() - base.mean()
        min = pspRgn.min() - base.mean()
        if abs(max) > abs(min): ### returns EPSP amplitude
            amp = max
        elif abs(max) < abs(min): ## returns IPSP amplitude
            amp = min
        return amp
    
    def getPspSlope(self, data, pspStart, base=None):
        """Return the slope of the first PSP after pspStart"""
        data = data[0]['Channel': 'primary']
        dt = data.xvals('Time')[1] - data.xvals('Time')[0]
        #if pspStart == None:
            #pspStart = self.getEpspSearchStart()
            #if pspStart == None:
                #return None, None
        e = self.plot.processData(data=[data], display=False, analyze=True)[0]
        e = e[e['peak'] > 0]  ## select only positive events
        starts = e['start']
        pspTimes = starts[starts > pspStart]
        if len(pspTimes) < 1:
            return None, None
        pspTime = pspTimes[0]
        width = self.stdpCtrl.slopeWidthSpin.value() / dt
        slopeRgn = gaussian_filter(data[pspTime : pspTime + 2*width].view(ndarray), 2)  ## slide forward to point of max slope
        peak = argmax(slopeRgn[1:]-slopeRgn[:-1])
        pspTime += peak
        
        pspRgn = data[pspTime-(width/2) : pspTime+(width/2)]
        slope = stats.linregress(pspRgn.xvals('Time'), pspRgn)[0]
        return slope, pspTime*dt
    
    #def getDerSlope(self, data):
        #d = data[0]['Channel':'primary']
        ##pspRgn = self.getPspRgn(data, self.stdpCtrl.durationSpin.value()/1000.0+0.1)
        #q = self.getLaserTime(data[1])*d.infoCopy()[-1]['rate']
        ##base = self.getBaselineRgn(data)
        #lp = lowPass(d, 200)
        #der = diff(lp)
        #pspRgn = der[q:q+self.stdpCtrl.durationSpin.value()*d.infoCopy()[-1]['rate']/1000]
        #base = der[:q]
        #slope = pspRgn.max()
        #a = argwhere(der == pspRgn.max())[0,0]
        #slopetime = d.xvals('Time')[a]
        ##rgnPsp = pspRgn[0:a][::-1]
        ##b = argwhere(rgnPsp < base.mean()+base.std())
        ##if len(b>0):
        ##    epsptime= pspRgn.xvals('Time')[a-b[0,0]]
        ##else:
        ##    epsptime = pspRgn.xvals('Time')[0]
        #n=0
        #a = []
        #while len(a) == 0 and n<2*self.stdpCtrl.thresholdSpin.value()-1:
            #a = argwhere(pspRgn > base.mean()+(self.stdpCtrl.thresholdSpin.value()*2-n)*base.std())
            #n+=1
        #if len(a)>0:
            #rgnPsp = pspRgn[0:a[0,0]][::-1]
            #n=0
            #b=[]
            #while len(b)==0 and n<self.stdpCtrl.thresholdSpin.value():
                #b = argwhere(rgnPsp < base.mean()+n*base.std())
                #n+=1
            #if len(b) > 0:
                #index= a[0,0]-b[0,0]
            #else:
                #index = 0
        #else:
            #index = 0
        #epsptime = self.getPspRgn(data,self.stdpCtrl.durationSpin.value()/1000.0).xvals('Time')[index]
        #return slope, slopetime, epsptime
        
    def getPspIndex(self, data, pspRgn=None, base=None):
        if pspRgn == None:
            pspRgn = self.getPspRgn(data, self.stdpCtrl.durationSpin.value()/1000.0)
        if base == None:
            base = self.getBaselineRgn(data)
        a = argwhere(pspRgn > max(base[-100:].mean()+self.stdpCtrl.thresholdSpin.value()*base.std(), base[-100:].mean()+0.0005))
        if len(a) > 0:
            rgnPsp = pspRgn[0:a[0,0]][::-1]
            b = argwhere(rgnPsp < base[-100:].mean()+base.std())
            if len(b) > 0:
                return a[0,0]-b[0,0]
            else:
                return 0
    
    def getPspTime(self, data, pspRgn=None, base=None):
        if pspRgn == None:
            pspRgn = self.getPspRgn(data, self.stdpCtrl.durationSpin.value()/1000.0)
        if base == None:
            base = self.getBaselineRgn(data)
        index = self.getPspIndex(data, pspRgn, base)
        if index != None:
            time = pspRgn.xvals('Time')[index]
            return time
    
    def EPSPstats(self, data, start):
        """Returns a five-item list with the unixtime of the trace, and the slope, the amplitude and the integral of the epsp, and the time of the epsp.
                Arguments:
                    data - a tuple with a 'Clamp.ma' array as the first item and the directory handle of the 'Clamp.ma' file as the second."""
        d = data[0]['Channel':'primary']
        #p = Profiler('EPSPStats')
        time = self.getUnixTime(data)
        #p.mark('1')
        base = self.getBaselineRgn(data)
        #p.mark('2')
        pspRgn = self.getPspRgn(data, self.stdpCtrl.durationSpin.value()/1000.0)
        #p.mark('3')
        flux = self.getPspFlux(data, pspRgn=pspRgn, base=base)
        #p.mark('4')
        amp = self.getPspAmp(data, pspRgn=pspRgn, base=base)
        #p.mark('5')
        #p.mark('6')
        slope, epsptime = self.getPspSlope(data, pspStart=start)
        #p.mark('7')
        #epsptime = self.getPspTime(data, pspRgn, base)
        #ds, dst, det = self.getDerSlope(data)
        #p.mark('8')
        return [time, slope, amp, flux, epsptime]
    
    def getEvents(self, mask, crop=True):
        """Return a list of event times for all traces within mask"""
        events = []
        #condStats = self.epspStats[self.epspStats['conditioningMask']]
        #if len(condStats) < 1:
            #raise Exception("No conditioning data found.")
        
        #if period == 'pre':
            #condtime = condStats['unixtime'].min()
            #indexes = self.epspStats[self.epspStats['unixtime'] < condtime]['currentTracesIndex']
        #elif period == 'post':
            #condtime = condStats['unixtime'].max()
            #indexes = self.epspStats[self.epspStats['unixtime'] > condtime]['currentTracesIndex']
        indexes = self.epspStats[mask]['currentTracesIndex']
        for i in indexes:
            #data = self.currentTraces[i][0]['Channel':'primary']
            #self.plot.setData([data])
            #for x in range(len(self.plot.events[i])):
            events.append(self.plot.events[i])
        if len(events) == 0:
            events = array([], dtype=[('start', int), ('sum', float), ('peak', float), ('len', int)])
        else:
            events = hstack(events)
            if crop:
                #FIXME
                stopInd = 500 + self.stdpCtrl.durationSpin.value()*10
                events = events[(events['start']>500)*(events['start']<stopInd)]
        
        return events
    
    def getEpspSearchStart(self, events):
        """Return index of earliest expected PSP. 
        -events is a list of event times (indexes) from which to search"""
        #e = self.getEventTimes(period)
        #print 'got event list'
        if len(events) > 0:
            #print 'finding event start'
            h = histogram(events['start'], weights=events['sum'], bins=100, range=(0,2000))
            g = ndimage.gaussian_filter(h[0].astype(float32), 2)
            i = argwhere(g > g.max()/3)
            if len(i) < 1:
                print "Coundn't find %s search start." % period
                print "Event times:", events
                print "histogram:", g
                return None
            i = i[0,0]
            start = h[1][i]
            return start
    
            
        
    def lineMoved(self, line):
        if self.epspStats != None:
            pos = line.getXPos()
            d = argmin(abs(self.epspStats['time'] - pos))
            dataindex = int(self.epspStats[d]['currentTracesIndex'])
            data = self.currentTraces[dataindex][0]['Channel':'primary']
            self.plot.setData([data])
            #self.plot.dataPlot.addItem(self.slopeMark3a)
            #self.plot.dataPlot.addItem(self.slopeMark4a)
            #x3 = self.epspStats[d]['derepsptime']
            #y3a = data[int(x3*data.infoCopy()[-1]['rate'])]
            #x4 = self.epspStats[d]['derslopetime']
            #y4a = data[int(x4*data.infoCopy()[-1]['rate'])]
            #self.slopeMark3a.setLine(x3, y3a-0.001, x3, y3a+0.001)
            #self.slopeMark4a.setLine(x4, y4a-0.001, x4, y4a+0.001)
            #der = diff(lowPass(data,200))
            #self.plot.analysisPlot.plot(der, x = data.xvals('Time')[:-1], clear=True)
            #y3b = der[int(x3*data.infoCopy()[-1]['rate'])]
            #y4b = der[int(x4*data.infoCopy()[-1]['rate'])]
            #self.plot.analysisPlot.addItem(self.slopeMark3b)
            #self.plot.analysisPlot.addItem(self.slopeMark4b)
            #self.slopeMark3b.setLine(x3, y3b-0.001, x3, y3b+0.001)
            #self.slopeMark4b.setLine(x4, y4b-0.001, x4, y4b+0.001)
            
            if self.epspStats[d]['pspMask']:
                self.plot.dataPlot.addItem(self.slopeMark1)
                self.plot.dataPlot.addItem(self.slopeMark2)
                x1 = self.epspStats[d]['epsptime']
                x2 = x1 + self.stdpCtrl.slopeWidthSpin.value()
                y1 = data[int(x1*data.infoCopy()[-1]['rate'])]
                y2 = data[int(x2*data.infoCopy()[-1]['rate'])]
                self.slopeMark1.setLine(x1, y1-0.001, x1, y1+0.001)
                self.slopeMark2.setLine(x2, y2-0.001, x2, y2+0.001)
        
    #def EPSPflux(self, data):
    #    """Returns a tuple with the unixtime of the trace and the integral of the EPSP.
    #            Arguments:
    #                data - a tuple with a 'Clamp.ma' array as the first item and the directory handle of the 'Clamp.ma' file as the second. """
    #    time = data[0].infoCopy()[-1]['startTime']
    #    q = self.getLaserTime(data[1])
    #    base = data[0]['Time': 0.0:(q - 0.01)]
    #    pspRgn = data[0]['Time': q:(q+self.stdpCtrl.durationSpin.value()/1000.0)]
    #    flux = pspRgn.sum() - (base.mean()*pspRgn.shape[0])
    #    return time, flux
    #
    #def EPSPamp(self, data):
    #    """Returns a tuple with the unixtime of the trace and the amplitude of the EPSP.
    #            Arguments:
    #                data - a tuple with a 'Clamp.ma' array as the first item and the directory handle of the 'Clamp.ma' file as the second. """
    #    time = data[0].infoCopy()[-1]['startTime']
    #    q = self.getLaserTime(data[1])
    #    base = data[0]['Time': 0.0:(q - 0.01)]
    #    pspRgn = data[0]['Time': q:(q+self.stdpCtrl.durationSpin.value()/1000.0)]
    #    amp = pspRgn.max() - base.mean()
    #    return time, amp
        
class IVWindow(QtGui.QMainWindow):
    def __init__(self):
        QtGui.QMainWindow.__init__(self)
        self.traces = None
        self.cw = QtGui.QSplitter()
        self.cw.setOrientation(QtCore.Qt.Vertical)
        self.setCentralWidget(self.cw)
        bw = QtGui.QWidget()
        bwl = QtGui.QHBoxLayout()
        bw.setLayout(bwl)
        self.cw.addWidget(bw)
        self.loadIVBtn = QtGui.QPushButton('Load I/V')
        bwl.addWidget(self.loadIVBtn)
        QtCore.QObject.connect(self.loadIVBtn, QtCore.SIGNAL('clicked()'), self.loadIV)
        self.plot1 = PlotWidget()
        self.cw.addWidget(self.plot1)
        self.plot2 = PlotWidget()
        self.cw.addWidget(self.plot2)
        self.resize(800, 800)
        self.show()
        self.lr = LinearRegionItem(self.plot1, 'vertical', [0, 1])
        self.plot1.addItem(self.lr)
        QtCore.QObject.connect(self.lr, QtCore.SIGNAL('regionChanged'), self.updateAnalysis)
        

    def loadIV(self):
        self.plot1.clearPlots()
        dh = getManager().currentFile
        dirs = dh.subDirs()
        c = 0.0
        traces = []
        values = []
        for d in dirs:
            d = dh[d]
            try:
                data = d['Clamp1.ma'].read()
            except:
                data = d['Clamp2.ma'].read()
            cmd = data['Channel': 'Command']
            if data.hasColumn('Channel', 'primary'):
                data = data['Channel': 'primary']
            else:
                data = data['Channel': 'scaled']
            traces.append(data)
            self.plot1.plot(data, pen=mkPen(hsv=[c, 0.7]))
            values.append(cmd[len(cmd)/2])
            c += 1.0 / len(dirs)
            
        if len(dirs) > 0:
            end = cmd.xvals('Time')[-1]
            self.lr.setRegion([end *0.5, end * 0.6])
            self.updateAnalysis()
            info = [
                {'name': 'Command', 'units': cmd.axisUnits(-1), 'values': array(values)},
                data.infoCopy('Time'), 
                data.infoCopy(-1)]
            self.traces = MetaArray(vstack(traces), info=info)
        
    def updateAnalysis(self):
        if self.traces is None:
            return
        rgn = self.lr.getRegion()
        data = self.traces['Time': rgn[0]:rgn[1]]
        self.plot2.plot(data.mean(axis=1), clear=True)
        self.plot2.plot(data.max(axis=1))
        self.plot2.plot(data.min(axis=1))
        
        

class PSPWindow(QtGui.QMainWindow):
    def __init__(self):
        QtGui.QMainWindow.__init__(self)
        self.cw = QtGui.QSplitter()
        self.cw.setOrientation(QtCore.Qt.Vertical)
        self.setCentralWidget(self.cw)
        bw = QtGui.QWidget()
        bwl = QtGui.QHBoxLayout()
        bw.setLayout(bwl)
        self.cw.addWidget(bw)
        self.loadTraceBtn = QtGui.QPushButton('Load Trace')
        bwl.addWidget(self.loadTraceBtn)
        QtCore.QObject.connect(self.loadTraceBtn, QtCore.SIGNAL('clicked()'), self.loadTrace)
        self.plot = PlotWidget()
        self.cw.addWidget(self.plot)
        self.resize(800, 800)
        self.show()

    def loadTrace(self):
        self.plot.clear()
        fh = getManager().currentFile
        try:
            data = d['Clamp1.ma'].read()['Channel': 'primary']
        except:
            data = d['Clamp2.ma'].read()['Channel': 'primary']
        self.plot.plot(data)
        
class CellHealthWindow(QtGui.QMainWindow):
    def __init__(self):
        QtGui.QMainWindow.__init__(self)
        self.cw = QtGui.QSplitter()
        self.cw.setOrientation(QtCore.Qt.Vertical)
        self.setCentralWidget(self.cw)
        bw = QtGui.QWidget()
        bwl = QtGui.QHBoxLayout()
        bw.setLayout(bwl)
        self.cw.addWidget(bw)
        self.loadDataBtn = QtGui.QPushButton('Load Data')
        bwl.addWidget(self.loadDataBtn)
        QtCore.QObject.connect(self.loadDataBtn, QtCore.SIGNAL('clicked()'), self.loadData)
        self.riPlot = PlotWidget()
        self.raPlot = PlotWidget()
        self.vmPlot = PlotWidget()
        self.iPlot = PlotWidget()
        self.cw.addWidget(self.riPlot)
        self.cw.addWidget(self.raPlot)
        self.cw.addWidget(self.vmPlot)
        self.cw.addWidget(self.iPlot)
        self.resize(600,600)
        self.show()
        
    def loadData(self):
        self.clear()
        d = getManager().currentFile.read()
        self.riPlot.plot(d['Value':'inputResistance'])
        self.riPlot.setYRange(0, 1e9)
        self.raPlot.plot(d['Value':'accessResistance'])
        self.raPlot.setYRange(0, 0.1e9)
        self.vmPlot.plot(d['Value':'restingPotential'])
        self.iPlot.plot(d['Value':'restingCurrent'])
        self.iPlot.setYRange(-500e-12, 0)
        
    def clear(self):
        self.riPlot.clear()
        self.raPlot.clear()
        self.vmPlot.clear()
        self.iPlot.clear()
