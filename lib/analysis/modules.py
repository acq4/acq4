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
from PyQt4 import QtCore, QtGui
from functions import *
from SpinBox import *
from debug import *
from DictView import DictView
from scipy import stats
from numpy import log

class UncagingSpot(QtGui.QGraphicsEllipseItem):
    def __init__(self, source): #source is directory handle
        QtGui.QGraphicsEllipseItem.__init__(self, 0, 0, 1, 1)
        self.source = source
        self.record = None
        self.position = None
        self.size = None
        self.laserTime = None
        

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
        self.thresholdSpin.setValue(10.0)
        self.ctrlLayout.addRow("Low pass", self.lowPassSpin)
        self.ctrlLayout.addRow("Decay const.", self.tauSpin)
        self.ctrlLayout.addRow("Threshold", self.thresholdSpin)
        
        QtCore.QObject.connect(self.tauSpin, QtCore.SIGNAL('valueChanged(double)'), self.tauChanged)
        QtCore.QObject.connect(self.lowPassSpin, QtCore.SIGNAL('valueChanged(double)'), self.lowPassChanged)
        QtCore.QObject.connect(self.thresholdSpin, QtCore.SIGNAL('valueChanged(double)'), self.thresholdChanged)
        
        self.analysisEnabled = True
        self.events = []
        self.data = []
        
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
        
    def setData(self, data):
        self.data = data
        self.recalculate()
        
    def recalculate(self):
        self.events = self.processData(self.data, display=True)
        self.emit(QtCore.SIGNAL('outputChanged'), self)
        print "Events:", self.events
        ##display events
        
    def getEvents(self):
        return self.events
        
    def processData(self, data, display=False):
        """Returns a list of record arrays - each record array contains the events detected in one trace.
                Arguments:
                    data - a list of traces"""
        if display:
            self.analysisPlot.clear()
            self.dataPlot.clear()
            self.templatePlot.clear()
            self.tickGroups = []
        events = []
        
        for i in range(len(data)):
            if display:
                color = float(i)/(len(data))*0.7
                pen = mkPen(hsv=[color, 0.8, 0.7])
                self.dataPlot.plot(data[i], pen=pen)
                
        if not self.analysisEnabled:
            return []
        
        for i in range(len(data)):
            #p.mark('start trace %d' % i)
            d = data[i]
            #print "lowpass:", d
            d1 = lowPass(d, self.lowPassSpin.value())
            #p.mark('lowpass')
            d2 = d1.view(ndarray) - measureBaseline(d1)
            #p.mark('subtract baseline')
            dt = d.xvals('Time')[1] - d.xvals('Time')[0]
            #p.mark('dt')
            d3 = diff(d2) * self.tauSpin.value() / dt + d2[:-1]
            #p.mark('deconvolve')
            d4 = removeBaseline(d3, dt=dt)
            #p.mark('remove baseline')
            #d4 = d3
                
            #stdev = measureNoise(d3)
            #print "noise:", stdev
            #thresh = stdev * self.thresholdSpin.value()
            #absd = abs(d3)
            #eventList = argwhere((absd[1:] > thresh) * (absd[:-1] <= thresh))[:, 0] + 1
            
            eventList = findEvents(d4, noiseThreshold=self.thresholdSpin.value())
            #p.mark('find events')
            events.append(eventList)
            if display:
                color = float(i)/(len(data))*0.7
                pen = mkPen(hsv=[color, 0.8, 0.7])
                
                self.analysisPlot.plot(d4, x=d.xvals('Time')[:-1], pen=pen)
                tg = VTickGroup(view=self.analysisPlot)
                tg.setPen(pen)
                tg.setYRange([0.8, 1.0], relative=True)
                tg.setXVals(d.xvals('Time')[eventList['start']])
                self.tickGroups.append(tg)
                self.analysisPlot.addItem(tg)
                
                ## generate triggered stacks for plotting
                stack = triggerStack(d, eventList['start'], window=[-100, 200])
                negPen = mkPen([0, 0, 200])
                posPen = mkPen([200, 0, 0])
                for j in range(stack.shape[0]):
                    base = median(stack[j, 80:100])
                    
                    if eventList[j]['sum'] > 0:
                        scale = stack[j, 100:100+eventList[j]['len']].max() - base
                        pen = posPen
                        params = {'sign': 1}
                    else:
                        scale = base - stack[j, 100:100+eventList[j]['len']].min()
                        pen = negPen
                        params = {'sign': -1}
                    self.templatePlot.plot((stack[j]-base) / scale, pen=pen, params=params)
        
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
        QtCore.QObject.connect(self.canvas.view, QtCore.SIGNAL('mouseReleased'), self.mouseClicked)
        self.ctrl = Ui_UncagingControlWidget()
        self.ctrlWidget = QtGui.QWidget()
        bwtop.addWidget(self.ctrlWidget)
        self.ctrl.setupUi(self.ctrlWidget)
        bwtop.addWidget(self.canvas)
        QtCore.QObject.connect(self.ctrl.recolorBtn, QtCore.SIGNAL('clicked()'), self.recolor)
        self.ctrl.directTimeSpin.setValue(4.0)
        self.ctrl.poststimTimeSpin.setRange(1.0, 1000.0)
        self.ctrl.poststimTimeSpin.setValue(150.0)
        self.ctrl.eventFindRadio.setChecked(True)
        self.ctrl.useSpontActCheck.setChecked(True)
        self.ctrl.rgbRadio.setChecked(True)
        self.ctrl.absoluteRadio.setChecked(True)
        
        
        #self.plot = PlotWidget()
        self.plot = EventMatchWidget()
        self.cw.addWidget(self.plot)
        
        self.z = 0
        self.resize(1000, 600)
        self.show()
        self.scanItems = []
        self.imageItems = []
        self.currentTraces = []
        self.noiseThreshold = 2.0
        self.eventTimes = []
        self.analysisCache = empty(len(self.scanItems),
            {'names': ('spotID', 'eventsValid', 'eventList', 'preEvents', 'dirEvents', 'postEvents', 'stdev', 'preChargePos', 'preChargeNeg', 'dirCharge', 'postChargePos', 'postChargeNeg'),
             'formats':(object, object, object, object, object, object, float, float, float, float, float, float)})
        
        
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
        self.analysisCache.resize(appendIndex + len(dirs))
        for d in dirs: #d is a directory handle
            #d = dh[d]
            if 'Scanner' in d.info() and 'position' in d.info()['Scanner']:
                pos = d.info()['Scanner']['position']
                if 'spotSize' in d.info()['Scanner']:
                    size = d.info()['Scanner']['spotSize']
                else:
                    size = self.defaultSize
                item = UncagingSpot(d)
                item.record = self.analysisCache[appendIndex]
                item.record['eventsValid'] = False
                appendIndex += 1
                item.position = pos
                item.size = size
                item.setBrush(QtGui.QBrush(QtGui.QColor(100,100,200)))                 
                self.canvas.addItem(item, [pos[0] - size*0.5, pos[1] - size*0.5], scale=[size,size], z = self.z, name=[dh.shortName(), d.shortName()])
                self.scanItems.append(item)
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
        self.scanItems = []
        self.currentTraces = []
        self.eventTimes = []
    
    def recolor(self):
        for i in self.scanItems:
            if i.record['eventsValid'] == False:
                events, pre, direct, post, q, stdev = self.getEventLists(i.source)
                i.record['eventList'] = events
                i.record['preEvents'] = pre
                i.record['dirEvents'] = direct
                i.record['postEvents'] = post
                i.record['stdev'] = stdev
                i.record['eventsValid'] = True
                i.laserTime = q
            self.analyzeEvents(i)
        for i in self.scanItems:
            color = self.spotColor(i)
            i.setBrush(QtGui.QBrush(color))
            
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
            
        data['Channel':'primary'] = denoise(data['Channel':'primary'])
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
        
    def getEventLists(self, dh):
        #if not self.plot.analysisEnabled:
        #    return QtGui.QColor(100,100,200)
        data = self.getClampData(dh)['Channel':'primary']
        events = self.plot.processData([data])[0]
        
        times = data.xvals('Time')
        self.eventTimes.extend(times[events['start']])
        q = self.getLaserTime(dh)
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
        
        stdev = data.std() / dt
        
        return events, pre, direct, post, q, stdev
        
    def analyzeEvents(self, item):
        pre = item.record['preEvents']
        post = item.record['postEvents']
        direct = item.record['dirEvents']
        stimTime = item.laserTime - 0.001
        dirTime = item.laserTime + self.ctrl.directTimeSpin.value()/1000
        endTime = item.laserTime + self.ctrl.poststimTimeSpin.value()/1000
        
        if self.ctrl.useSpontActCheck.isChecked():
            pos = (post[post['sum'] > 0]['sum'].sum() / (endTime-dirTime)) - (pre[pre['sum'] > 0]['sum'].sum() / stimTime)
            neg = ((post[post['sum'] < 0]['sum'].sum() / (endTime-dirTime)) - (pre[pre['sum'] < 0]['sum'].sum() / stimTime))
            dir = (abs(direct['sum']).sum() / (dirTime-stimTime)) - (abs(pre['sum']).sum() / stimTime)
            item.record['postChargePos'] = pos
            item.record['postChargeNeg'] = neg
            item.record['dirCharge'] = dir
        else:
            pos = (post[post['sum'] > 0]['sum'].sum() / (endTime-dirTime))
            neg = (post[post['sum'] < 0]['sum'].sum() / (endTime-dirTime))
            prePos = pre[pre['sum'] > 0]['sum'].sum() / stimTime
            preNeg = (pre[pre['sum'] < 0]['sum'].sum() / stimTime)
            item.record['postChargePos'] = pos
            item.record['postChargeNeg'] = neg
            item.record['preChargePos'] = prePos
            item.record['preChargeNeg'] = preNeg
            item.record['dirCharge'] = 0
            
    def spotColor(self, item):
        if self.ctrl.rgbRadio.isChecked():
            red = clip(log(max(1.0, (item.record['postChargePos']/item.record['stdev'])+1))*255, 0, 255) 
            blue = clip(log(max(1.0, (-item.record['postChargeNeg']/item.record['stdev'])+1))*255, 0, 255)
            green = clip(log(max(1.0, (item.record['dirCharge']/item.record['stdev'])+1))*255, 0, 255)
            return QtGui.QColor(red, green, blue, max(red, green, blue))
            
        if self.ctrl.rainbowRadio.isChecked():
            maxcharge = stats.scoreatpercentile(self.analysisCache['postChargeNeg'], per = 5)
            #hue = 255 - (log(1+1000*(item.record['postChargeNeg'] / self.analysisCache['postChargeNeg'].min())))*255/log(1001)
            #maxcharge = a.max()
            hue = 255 - (-item.record['postChargeNeg']/maxcharge)*255
            #print "max charge:", maxcharge, "charge: ", item.record['postChargeNeg'], "hue: ", hue
            sat = 255
            if hue < 0:
                hue = 0
                val = 180
            if item.record['postChargeNeg'] == 0:
                alpha = 0
            else:
                alpha = 255
            if len(item.record['dirEvents']) > 0:
                val = 0
            else:
                val = 255
            print "Type hue", type(hue), "Type sat", type(sat)
            return QtGui.QColor.fromHsv(hue, sat, val, alpha)
        
   
    def mouseClicked(self, ev):
        ###should probably make mouseClicked faster by using cached data instead of calling processData in eventFinderWidget each time
        """Makes self.currentTraces a list of data corresponding to items on a canvas under a mouse click. Each list item is a tuple where the first element
           is an array of clamp data, and the second is the directory handle for the Clamp.ma file."""
        spots = self.canvas.view.items(ev.pos())
        self.currentTraces = []
        for i in spots:
            d = self.loadTrace(i)
            if d is not None:
                self.currentTraces.append(d)
        self.plot.setData([i[0]['Channel':'primary'] for i in self.currentTraces])

        
    def loadTrace(self, item):
        """Returns a tuple where the first element is a clamp.ma, and the second is its directory handle."""
        if not hasattr(item, 'source'):
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
        self.LTPplot = PlotWidget()
        self.latencies = {}
        self.dictView = DictView(self.latencies)
        bwtop.addWidget(self.canvas)
        bwtop.addWidget(self.LTPplot)
        bwtop.addWidget(self.dictView)
        self.plot.enableAnalysis(False)
        
    def mouseClicked(self, ev):
        UncagingWindow.mouseClicked(self, ev)
        epspStats = zeros([len(self.currentTraces)], {'names':('unixtime', 'slope', 'amp', 'flux', 'epsptime', 'time', 'normSlope', 'normAmp', 'normFlux'), 'formats': ((float,)*9)})
        #print 'lenspots:', len(self.currentTraces)
        flag = 0
        condtime = None
        spiketime = []
        for i in range(len(self.currentTraces)):
            if self.currentTraces[i][0]['Channel':'Command'].max() < 0.1e-09:
                t,s,a,f,e = self.EPSPstats(self.currentTraces[i])
                #print 'i:', i, 't:', t, 's:', s, 'a:', a, 'f:', f, 'e:', e
                if s != None:
                    epspStats[i]['unixtime'] = t
                    epspStats[i]['slope'] = s
                    epspStats[i]['amp'] = a
                    epspStats[i]['flux'] = f
                    epspStats[i]['epsptime'] = e
            elif self.currentTraces[i][0]['Channel':'Command'].max() >= 0.1e-09:
                a = argwhere(self.currentTraces[i][0]['Channel':'primary'] == self.currentTraces[i][0]['Channel':'primary'].max())
                #print i, a
                if len(a) > 0:
                    spikeindex = a[0]
                    spike = self.currentTraces[i][0]['Channel':'primary'].xvals('Time')[spikeindex]
                    #print i, spike
                    spiketime.append(spike)
                if flag != 1:
                    condtime = self.currentTraces[i][0]['Channel':'primary'].infoCopy()[-1]['startTime']
                    flag = 1
        #print 'spiketime', spiketime
       # print "epspStats before sort:", epspStats, '\n'
        epspStats.sort(order = 'unixtime') 
       # print "sortedStats after sort:", epspStats
        startBase = argwhere(epspStats['unixtime'] > 0)[0]
        epspStats = epspStats[startBase:]
        try:
            endbase = argwhere(epspStats['unixtime'] > condtime)[0]
        except IndexError:
            if condtime != None:
                endbase = -1
            else: raise
            
        for x in range(len(epspStats)):
            epspStats[x]['time'] =(epspStats[x]['unixtime']-(epspStats[0]['unixtime']))/60
            epspStats[x]['normSlope'] = (epspStats['slope'][x])/(mean(epspStats[:endbase]['slope']))
            epspStats[x]['normAmp'] = (epspStats['amp'][x])/(mean(epspStats[:endbase]['amp']))
            epspStats[x]['normFlux'] = (epspStats['flux'][x])/(mean(epspStats[:endbase]['flux']))
        #print 'epspSlope', epspStats[:endbase]['slope']
        #print 'meanSlope', mean(epspStats[:endbase]['slope'])
        
        self.latencies['Average EPSP time:'] = mean(epspStats[:endbase]['epsptime']*1000)
        #print 'spiketime:', spiketime
        #print 'mean:', mean(spiketime)
        self.latencies['Average 1st Spike time:'] = mean(spiketime)*1000
        self.latencies['PSP-Spike Delay:']= self.latencies['Average 1st Spike time:']-self.latencies['Average EPSP time:']
        self.latencies['Change in slope(red):'] = mean(epspStats[(endbase+1):]['normSlope'])
        self.latencies['Change in amp(blue):'] = mean(epspStats[(endbase+1):]['normAmp'])
        self.latencies['Change in flux(green):'] = mean(epspStats[(endbase+1):]['normFlux'])
        self.dictView.setData(self.latencies)
        
        self.LTPplot.clear()
        self.LTPplot.plot(data = epspStats['normSlope'], x = epspStats['time'], pen=mkPen([255, 0, 0]))
        self.LTPplot.plot(data = epspStats['normFlux'], x = epspStats['time'], pen=mkPen([0, 255, 0]))
        self.LTPplot.plot(data = epspStats['normAmp'], x = epspStats['time'], pen = mkPen([0, 0, 255]))
        
    def EPSPstats(self, data):
        """Returns a five-item list with the unixtime of the trace, and the slope, the amplitude and the integral of the epsp, and the time of the epsp.
                Arguments:
                    data - a tuple with a 'Clamp.ma' array as the first item and the directory handle of the 'Clamp.ma' file as the second."""
        d = data[0]['Channel':'primary']            
        time = d.infoCopy()[-1]['startTime']
        q = self.getLaserTime(data[1])
        base = d['Time': 0.0:(q - 0.01)]
        pspRgn = d['Time': q:(q+0.2)]
        flux = pspRgn.sum() - (base.mean()*pspRgn.shape[0])
        amp = pspRgn.max() - base.mean()
        a = argwhere(pspRgn > base.mean()+4*base.std())
        if len(a) > 0:
            epspindex = a[0,0]
            epsptime = pspRgn.xvals('Time')[epspindex]
            slope = (d['Time': (epsptime+0.0015):(epsptime+0.0025)].mean() - d['Time': (epsptime-0.0005):(epsptime+0.0005)].mean())/ 2
            return [time, slope, amp, flux, epsptime]
        else:
            return [time, None, amp, flux, None]
        
    #def EPSPflux(self, data):
    #    """Returns a tuple with the unixtime of the trace and the integral of the EPSP.
    #            Arguments:
    #                data - a tuple with a 'Clamp.ma' array as the first item and the directory handle of the 'Clamp.ma' file as the second. """
    #    time = data[0].infoCopy()[-1]['startTime']
    #    q = self.getLaserTime(data[1])
    #    base = data[0]['Time': 0.0:(q - 0.01)]
    #    pspRgn = data[0]['Time': q:(q+0.2)]
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
    #    pspRgn = data[0]['Time': q:(q+0.2)]
    #    amp = pspRgn.max() - base.mean()
    #    return time, amp
        
class IVWindow(QtGui.QMainWindow):
    def __init__(self):
        QtGui.QMainWindow.__init__(self)
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
        self.plot = PlotWidget()
        self.cw.addWidget(self.plot)
        self.resize(800, 800)
        self.show()

    def loadIV(self):
        self.plot.clear()
        dh = getManager().currentFile
        dirs = dh.subDirs()
        c = 0.0
        for d in dirs:
            d = dh[d]
            try:
                data = d['Clamp1.ma'].read()['Channel': 'primary']
            except:
                data = d['Clamp2.ma'].read()['Channel': 'primary']
            self.plot.plot(data, pen=mkPen(hsv=[c, 0.7]))
            c += 1.0 / len(dirs)


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