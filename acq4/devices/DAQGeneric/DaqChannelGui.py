# -*- coding: utf-8 -*-

from PyQt4 import QtGui, QtCore
#from PyQt4 import Qwt5 as Qwt
import AOChannelTemplate, DOChannelTemplate, InputChannelTemplate
from acq4.util.SequenceRunner import *
#from acq4.pyqtgraph.WidgetGroup import WidgetGroup
#from acq4.pyqtgraph.PlotWidget import PlotCurveItem
import numpy
#import sip
import weakref
from acq4.pyqtgraph import siFormat, SpinBox, WidgetGroup
#from acq4.pyqtgraph.SpinBox import SpinBox

###### For task GUIs

class DaqChannelGui(QtGui.QWidget):
    def __init__(self, parent, name, config, plot, dev, prot, daqName=None):
        QtGui.QWidget.__init__(self, parent)
        
        ## Name of this channel
        self.name = name
        
        ## Parent taskGui object
        self.taskGui = weakref.ref(parent)
        
        ## Configuration for this channel defined in the device configuration file
        self.config = config
        
        self.scale = 1.0
        self.units = ''
        
        ## The device handle for this channel's DAQGeneric device
        self.dev = dev
        
        ## The task GUI window which contains this object
        self.prot = weakref.ref(prot)
        
        ## Make sure task interface includes our DAQ device
        if daqName is None:
            self.daqDev = self.dev.getDAQName(self.name)
        else:
            self.daqDev = daqName
        self.daqUI = self.prot().getDevice(self.daqDev)
        
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
        self.stateGroup.addWidget(self.plot, name='plot')
        
        self.displayCheckChanged()
        #QtCore.QObject.connect(self.ui.displayCheck, QtCore.SIGNAL('stateChanged(int)'), self.displayCheckChanged)
        self.ui.displayCheck.stateChanged.connect(self.displayCheckChanged)
        #QtCore.QObject.connect(self.ui.groupBox, QtCore.SIGNAL('toggled(bool)'), self.groupBoxClicked)
        self.ui.groupBox.toggled.connect(self.groupBoxClicked)
        
        #if 'userScale' in self.config:
            #self.setScale(self.config['userScale'])
        #else:
            #self.setScale(1.0)
        
        if 'units' in self.config:
            self.setUnits(self.config['units'])
        else:
            self.setUnits('')
            
    def updateTitle(self):
        if self.ui.groupBox.isChecked():
            plus = ""
        else:
            plus = "[+] "
        
        #units = " (x%s)" % siFormat(self.scale, suffix=self.units)
        
        
        self.ui.groupBox.setTitle(plus + self.name + " (%s)" %self.units)
    
    def setUnits(self, units):
        self.units = units
        for s in self.getSpins():
            if isinstance(s, SpinBox):
                s.setOpts(suffix=units)
        self.updateTitle()

    def getSpins(self):
        return []

    #def setScale(self, scale):
        #self.scale = scale
        #self.updateTitle()
	        
    def groupBoxClicked(self, b):
        self.setChildrenVisible(self.ui.groupBox, b)
        self.updateTitle()
        #if b:
        #    self.ui.groupBox.setTitle(unicode(self.ui.groupBox.title())[4:])
        #else:
        #    self.ui.groupBox.setTitle("[+] " + unicode(self.ui.groupBox.title()))
            
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
    
    def taskSequenceStarted(self):
        pass
    
    def quit(self):
        #print "quit DAQGeneric channel", self.name
        self.plot.close()
        
        
class OutputChannelGui(DaqChannelGui):
    
    sigSequenceChanged = QtCore.Signal(object)
    sigDataChanged = QtCore.Signal(object)
    
    def __init__(self, *args):
        DaqChannelGui.__init__(self, *args)
        self.units = ''
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
        #self.ui.waveGeneratorWidget.setTimeScale(1e-3)
        
        self.daqChanged(self.daqUI.currentState())
        
        if self.config['type'] == 'ao':
            for s in self.getSpins():
                s.setOpts(dec=True, range=[None, None], step=1.0, minStep=1e-12, siPrefix=True)

        self.daqUI.sigChanged.connect(self.daqChanged)
        self.ui.waveGeneratorWidget.sigDataChanged.connect(self.updateWaves)
        self.ui.waveGeneratorWidget.sigFunctionChanged.connect(self.waveFunctionChanged)
        self.ui.waveGeneratorWidget.sigParametersChanged.connect(self.sequenceChanged)
        self.ui.holdingCheck.stateChanged.connect(self.holdingCheckChanged)
        self.ui.holdingSpin.valueChanged.connect(self.holdingSpinChanged)
        self.dev.sigHoldingChanged.connect(self.updateHolding)
        
        self.holdingCheckChanged()

    def getSpins(self):
        return (self.ui.preSetSpin, self.ui.holdingSpin)
    
    def setMeta(self, key, **kwargs):
        ## key is 'x' (time), 'y' (amp), or 'xy' (sum)
        self.ui.waveGeneratorWidget.setMeta(key, **kwargs)
        
    #def setScale(self, scale):
        #self.ui.waveGeneratorWidget.setScale(scale)
        #self.scale = scale
        #self.updateTitle()
        
    def setUnits(self, units, **kwargs):
        DaqChannelGui.setUnits(self, units)
        self.ui.waveGeneratorWidget.setMeta('y', units=units, siPrefix=True, **kwargs)
        
    def quit(self):
        DaqChannelGui.quit(self)
        
        #if not sip.isdeleted(self.daqUI):
        try:
            self.daqUI.sigChanged.disconnect(self.daqChanged)
        except TypeError:
            pass
        self.ui.waveGeneratorWidget.sigDataChanged.disconnect(self.updateWaves)
        self.ui.waveGeneratorWidget.sigFunctionChanged.disconnect(self.waveFunctionChanged)
        self.ui.waveGeneratorWidget.sigParametersChanged.disconnect(self.sequenceChanged)
        self.ui.holdingCheck.stateChanged.disconnect(self.holdingCheckChanged)
        self.ui.holdingSpin.valueChanged.disconnect(self.holdingSpinChanged)
        self.dev.sigHoldingChanged.disconnect(self.updateHolding)


    def daqChanged(self, state):
        self.rate = state['rate']
        self.numPts = state['numPts']
        self.timeVals = numpy.linspace(0, float(self.numPts)/self.rate, self.numPts)
        self.updateWaves()
        
    def listSequence(self):
        return self.ui.waveGeneratorWidget.listSequences()
    
    def sequenceChanged(self):
        #self.emit(QtCore.SIGNAL('sequenceChanged'), self.dev.name)
        self.sigSequenceChanged.emit(self.dev.name())
        
    
    def generateTask(self, params=None):
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
            params[k] = range(len(ps[k]))
        waves = []
        runSequence(lambda p: waves.append(self.getSingleWave(p)), params, params.keys()) ## appends waveforms for the entire parameter space to waves
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
        #self.emit(QtCore.SIGNAL('sequenceChanged'), self.dev.name)
        self.sigDataChanged.emit(self)
        
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
        plot = self.plot.plot(y=data, x=self.timeVals, pen=QtGui.QPen(color))
        return plot

    def getSingleWave(self, params=None):
        state = self.stateGroup.state()
        h = self.getHoldingValue()
        if h is not None:
            self.ui.waveGeneratorWidget.setOffset(h)
        
        wave = self.ui.waveGeneratorWidget.getSingle(self.rate, self.numPts, params)
        
        return wave
        
    def holdingCheckChanged(self, *v):
        self.ui.holdingSpin.setEnabled(self.ui.holdingCheck.isChecked())
        self.updateHolding()
        
    def holdingSpinChanged(self, *args):
        hv = self.getHoldingValue()
        if hv is not None:
            self.ui.waveGeneratorWidget.setOffset(hv)
        
        
    def updateHolding(self):
        hv = self.getHoldingValue()
        if hv is not None:
            if not self.ui.holdingCheck.isChecked():
                self.ui.holdingSpin.setValue(hv)
            self.ui.waveGeneratorWidget.setOffset(hv)
            
    def getHoldingValue(self):
        """Return the value for this channel that will be used when the task is run
        (by default, this is just the current holding value)"""
        if self.ui.holdingCheck.isChecked():
            return self.ui.holdingSpin.value()
        else:
            return self.taskGui().getChanHolding(self.name)
        
    def waveFunctionChanged(self):
        if self.ui.waveGeneratorWidget.functionString() != "":
            self.ui.functionCheck.setChecked(True)
        else:
            self.ui.functionCheck.setChecked(False)
        
class InputChannelGui(DaqChannelGui):
    def __init__(self, *args):
        DaqChannelGui.__init__(self, *args)
        self.ui = InputChannelTemplate.Ui_Form()
        self.ui.setupUi(self)
        #QtCore.QObject.connect(self.prot, QtCore.SIGNAL('taskStarted'), self.clearPlots)
        self.postUiInit()
        self.clearBeforeNextPlot = False
         
    def taskSequenceStarted(self):
        self.clearBeforeNextPlot = True
        #self.clearPlots()
         
    def listSequence(self):
        return []
    
    def generateTask(self, params=None):
        if params is None:
            params = {}
        state = self.stateGroup.state()
        return {'record': state['recordCheck'], 'recordInit': state['recordInitCheck']}
    
    def handleResult(self, result, params):
        if self.stateGroup.state()['displayCheck']:
            if self.clearBeforeNextPlot:
                self.clearPlots()
                self.clearBeforeNextPlot = False

            plot = self.plot.plot(y=result.view(numpy.ndarray), x=result.xvals('Time'), pen=QtGui.QPen(QtGui.QColor(200, 200, 200)), params=params)
            #plot = PlotCurve('cell')
            #plot.setPen(QtGui.QPen(QtGui.QColor(200, 200, 200)))
            #plot.setData(result.xvals('Time'), result)
            #plot.attach(self.plot)
            #self.plots.append(plot)
            #self.plot.replot()
    
