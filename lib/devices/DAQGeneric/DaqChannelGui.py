# -*- coding: utf-8 -*-

from PyQt4 import QtGui, QtCore
#from PyQt4 import Qwt5 as Qwt
import AOChannelTemplate, DOChannelTemplate, InputChannelTemplate
from lib.util.SequenceRunner import *
from lib.util.WidgetGroup import *
#from lib.util.pyqtgraph.PlotWidget import PlotCurveItem
import numpy
import sip

class DaqChannelGui(QtGui.QWidget):
    def __init__(self, parent, name, config, plot, dev, prot):
        QtGui.QWidget.__init__(self, parent)
        
        ## Name of this channel
        self.name = name
        
        ## Configuration for this channel defined in the device configuration file
        self.config = config
        
        if 'scale' in config:
            self.scale = config['scale']
        else:
            self.scale = 1.0
        #print "device %s scale=%f" % (name, self.scale)
        
        ## The device handle for this channel's DAQGeneric device
        self.dev = dev
        
        ## The protocol GUI window which contains this object
        self.prot = prot
        
        ## Make sure protocol interface includes our DAQ device
        self.daqDev = self.dev.getDAQName(self.name)
        self.daqUI = self.prot.getDevice(self.daqDev)
        
        ## plot widget
        self.plot = plot
        #plot.setCanvasBackground(QtGui.QColor(0,0,0))
        #plot.replot()
        
        ## Curves displayed in self.plot
        #self.plots = []
        
            
    def postUiInit(self):
        ## Automatically locate all read/writable widgets and group them together for easy 
        ## save/restore operations
        self.stateGroup = WidgetGroup(self)
        
        self.displayCheckChanged()
        QtCore.QObject.connect(self.ui.displayCheck, QtCore.SIGNAL('stateChanged(int)'), self.displayCheckChanged)
        QtCore.QObject.connect(self.ui.groupBox, QtCore.SIGNAL('toggled(bool)'), self.groupBoxClicked)
            
    def groupBoxClicked(self, b):
        self.setChildrenVisible(self.ui.groupBox, b)
        if b:
            self.ui.groupBox.setTitle(unicode(self.ui.groupBox.title())[4:])
        else:
            self.ui.groupBox.setTitle("[+] " + unicode(self.ui.groupBox.title()))
            
    def setChildrenVisible(self, obj, vis):
        for c in obj.children():
            if isinstance(c, QtGui.QWidget):
                c.setVisible(vis)
            else:
                self.setChildrenVisible(c, vis)
            
    def saveState(self):
        return self.stateGroup.state()
    
    def restoreState(self, state):
        self.stateGroup.setState(state)
        if hasattr(self.ui, 'waveGeneratorWidget'):
            self.ui.waveGeneratorWidget.update()

    def clearPlots(self):
        #for i in self.plots:
            #i.detach()
        #self.plots = []
        self.plot.clear()
        self.currentPlot = None

    def displayCheckChanged(self):
        if self.stateGroup.state()['displayCheck']:
            self.plot.show()
        else:
            self.plot.hide()
            
    def taskStarted(self, params):
        pass
    
    def protocolStarted(self):
        pass
    
    def quit(self):
        pass
        
class OutputChannelGui(DaqChannelGui):
    def __init__(self, *args):
        DaqChannelGui.__init__(self, *args)
        
        self.currentPlot = None
        if self.config['type'] == 'ao':
            self.ui = AOChannelTemplate.Ui_Form()
        elif self.config['type'] == 'do':
            self.ui = DOChannelTemplate.Ui_Form()
        else:
            raise Exception("Unrecognized channel type '%s'" % self.config['type'])
        #pdb.set_trace()
        self.ui.setupUi(self)
        self.postUiInit()
        self.ui.waveGeneratorWidget.setTimeScale(1e-3)
        
        self.daqChanged(self.daqUI.currentState())
        
            

        QtCore.QObject.connect(self.daqUI, QtCore.SIGNAL('changed'), self.daqChanged)
        QtCore.QObject.connect(self.ui.waveGeneratorWidget, QtCore.SIGNAL('changed'), self.updateWaves)

    def quit(self):
        DaqChannelGui.quit(self)
        if not sip.isdeleted(self.daqUI):
            QtCore.QObject.disconnect(self.daqUI, QtCore.SIGNAL('changed'), self.daqChanged)
    
    def daqChanged(self, state):
        self.rate = state['rate']
        self.numPts = state['numPts']
        self.timeVals = numpy.linspace(0, float(self.numPts)/self.rate, self.numPts)
        self.updateWaves()
        
    def listSequence(self):
        return self.ui.waveGeneratorWidget.listSequences()
    
    def generateProtocol(self, params=None):
        if params is None:
            params = {}
        prot = {}
        state = self.stateGroup.state()
        if state['preSetCheck']:
            prot['preset'] = state['preSetSpin']
        if state['holdingCheck']:
            prot['holding'] = state['holdingSpin']
        if state['functionCheck']:
            #prot['command'] = self.scale * self.getSingleWave(params)  ## scaling is handled by Device
            prot['command'] = self.getSingleWave(params)
            #if prot['command'] is not None:
                #print "===command==", prot['command'].min(), prot['command'].max()
                #print params
            
        #print prot
        return prot
    
    def handleResult(self, result, params):
        pass
    
    def updateWaves(self):
        self.clearPlots()
        
        ## display sequence waves
        params = {}
        ps = self.ui.waveGeneratorWidget.listSequences()
        for k in ps:
            params[k] = range(ps[k])
        waves = []
        runSequence(lambda p: waves.append(self.getSingleWave(p)), params, params.keys(), passHash=True)
        for w in waves:
            if w is not None:
                self.ui.functionCheck.setChecked(True)
                self.plotCurve(w, color=QtGui.QColor(100, 100, 100))
        
        ## display single-mode wave in red
        single = self.getSingleWave()
        if single is not None:
            self.ui.functionCheck.setChecked(True)
            self.plotCurve(single, color=QtGui.QColor(200, 100, 100))
            #print "===single==", single.min(), single.max()
        self.emit(QtCore.SIGNAL('sequenceChanged'), self.dev.name)
        
    def taskStarted(self, params):
        ## Draw green trace for current command waveform
        if not self.stateGroup.state()['displayCheck']:
            return
        if self.currentPlot is not None:
            #print "======================== DATCH %s ===========================" % self.currentPlot
            #import gc
            #print "REF BEFORE:\n", '\n'.join(["%s:\n%s\n" % (type(x), str(x)) for x in gc.get_referrers(self.currentPlot)[:10]])
            self.plot.removeItem(self.currentPlot)
            #self.currentPlot.detach()
        
            #refs = gc.get_referrers(self.currentPlot)[:10]
            #print "REF AFTER:\n", '\n'.join(["%s:\n%s\n" % (type(x), str(x)) for x in refs])
            #refs = gc.get_referrers(refs[1])[:10]
            #print "REF2 AFTER:\n", '\n'.join(["%s:\n%s\n" % (type(x), str(x)) for x in refs])
        #a = empty((107)); a = empty((7)); a = empty((10007))
        
        cur = self.getSingleWave(params)
        #cur = self.ui.waveGeneratorWidget.getSingle(self.rate, self.numPts, params)
        if cur is not None:
            self.currentPlot = self.plotCurve(cur, color=QtGui.QColor(100, 200, 100))
            self.currentPlot.setZValue(100)
            #print "==cur===", cur.min(), cur.max()
            #print params
        
    def plotCurve(self, data, color=QtGui.QColor(100, 100, 100), replot=True):
        plot = self.plot.plot(data, self.timeVals, pen=QtGui.QPen(color))
        #plot = PlotCurve('cell')
        #plot.setPen(QtGui.QPen(color))
        #plot.setData(self.timeVals, data)
        #plot.attach(self.plot)
        #self.plots.append(plot)
        #if replot:
            #self.plot.replot()
        return plot

    def getSingleWave(self, params=None):
        state = self.stateGroup.state()
        if state['holdingCheck']:
            h = state['holdingSpin']
        else:
            h = 0.0
            
        self.ui.waveGeneratorWidget.setOffset(h)
        
        wave = self.ui.waveGeneratorWidget.getSingle(self.rate, self.numPts, params)
        
        return wave
        
class InputChannelGui(DaqChannelGui):
    def __init__(self, *args):
        DaqChannelGui.__init__(self, *args)
        self.ui = InputChannelTemplate.Ui_Form()
        self.ui.setupUi(self)
        #QtCore.QObject.connect(self.prot, QtCore.SIGNAL('protocolStarted'), self.clearPlots)
        self.postUiInit()
        self.clearBeforeNextPlot = False
         
    def protocolStarted(self):
        self.clearBeforeNextPlot = True
        #self.clearPlots()
         
    def listSequence(self):
        return []
    
    def generateProtocol(self, params=None):
        if params is None:
            params = {}
        state = self.stateGroup.state()
        return {'record': state['recordCheck'], 'recordInit': state['recordInitCheck']}
    
    def handleResult(self, result, params):
        if self.stateGroup.state()['displayCheck']:
            if self.clearBeforeNextPlot:
                self.clearPlots()
                self.clearBeforeNextPlot = False

            plot = self.plot.plot(result.view(numpy.ndarray), result.xvals('Time'), pen=QtGui.QPen(QtGui.QColor(200, 200, 200)), params=params)
            #plot = PlotCurve('cell')
            #plot.setPen(QtGui.QPen(QtGui.QColor(200, 200, 200)))
            #plot.setData(result.xvals('Time'), result)
            #plot.attach(self.plot)
            #self.plots.append(plot)
            #self.plot.replot()
    