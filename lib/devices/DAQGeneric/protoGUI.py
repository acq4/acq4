# -*- coding: utf-8 -*-
from PyQt4 import QtCore, QtGui
import sys
from ProtocolTemplate import *
from DaqChannelGui import *
from lib.devices.Device import ProtocolGui
from lib.util.SequenceRunner import *
from lib.util.WidgetGroup import *
#from PyQt4 import Qwt5 as Qwt
from lib.util.qtgraph.PlotWidget import PlotWidget
import numpy
import weakref
from lib.util.debug import *

class DAQGenericProtoGui(ProtocolGui):
    def __init__(self, dev, prot, ownUi=True):
        ProtocolGui.__init__(self, dev, prot)
        
        if ownUi:
            self.ui = Ui_Form()
            self.ui.setupUi(self)
            self.stateGroup = WidgetGroup([
                (self.ui.topSplitter, 'splitter1'),
                (self.ui.controlSplitter, 'splitter2'),
                (self.ui.plotSplitter, 'splitter3'),
            ])
            self.createChannelWidgets(self.ui.controlSplitter, self.ui.plotSplitter)
            self.ui.topSplitter.setStretchFactor(0, 0)
            self.ui.topSplitter.setStretchFactor(1, 1)
            
        else:
            ## If ownUi is False, then the UI is created elsewhere and createChannelWidgets must be called from there too.
            self.stateGroup = None
        
    def createChannelWidgets(self, ctrlParent, plotParent):
        self.plots = weakref.WeakValueDictionary()
        self.channels = {}
        
        ## Create plots and control widgets
        for ch in self.dev.config:
            conf = self.dev.config[ch]
            p = PlotWidget(plotParent)
            
            units = ''
            if 'units' in conf:
                units = ' (%s)' % conf['units']
                
            #p.setAxisTitle(PlotWidget.yLeft, ch+units)
            p.setLabel('left', ch+units)
            self.plots[ch] = p
            
            p.registerPlot(self.dev.name + '.' + ch)
            
            if conf['type'] in ['ao', 'do']:
                w = OutputChannelGui(ctrlParent, ch, conf, p, self.dev, self.prot)
                QtCore.QObject.connect(w, QtCore.SIGNAL('sequenceChanged'), self.sequenceChanged)
            elif conf['type'] in ['ai', 'di']:
                w = InputChannelGui(ctrlParent, ch, conf, p, self.dev, self.prot)
            else:
                raise Exception("Unrecognized device type '%s'" % conf['type'])
            w.ui.groupBox.setTitle(ch + units)
            self.channels[ch] = w
        

    def saveState(self):
        if self.stateGroup is not None:
            state = self.stateGroup.state().copy()
        else:
            state = {}
        state['channels'] = {}
        for ch in self.channels:
            state['channels'][ch] = self.channels[ch].saveState()
        return state

    def restoreState(self, state):
        try:
            if self.stateGroup is not None:
                self.stateGroup.setState(state)
            for ch in state['channels']:
                self.channels[ch].restoreState(state['channels'][ch])
        except:
            printExc('Error while restoring GUI state:')
            #sys.excepthook(*sys.exc_info())
        #self.ui.waveGeneratorWidget.update()
            
        
    def listSequence(self):
        ## returns sequence parameter names and lengths
        l = {}
        for ch in self.channels:
            chl = self.channels[ch].listSequence()
            for k in chl:
                l[ch+'.'+k] = chl[k]
        return l
        
    def sequenceChanged(self):
        self.emit(QtCore.SIGNAL('sequenceChanged'), self.dev.name)
        
    def taskStarted(self, params):  ## automatically invoked from ProtocolGui
        ## Pull out parameters for this device
        params = dict([(p[1], params[p]) for p in params if p[0] == self.dev.name])
        
        for ch in self.channels:
            ## Extract just the parameters the channel will need
            chParams = {}
            search = ch + '.'
            for k in params:
                if k[:len(search)] == search:
                    chParams[k[len(search):]] = params[k]
            self.channels[ch].taskStarted(chParams)
            
    def protocolStarted(self):  ## automatically invoked from ProtocolGui
        for ch in self.channels:
            self.channels[ch].protocolStarted()
        
        
    def generateProtocol(self, params=None):
        #print "generating protocol with:", params
        if params is None:
            params = {}
        p = {}
        for ch in self.channels:
            ## Extract just the parameters the channel will need
            chParams = {}
            search = ch + '.'
            for k in params:
                if k[:len(search)] == search:
                    chParams[k[len(search):]] = params[k]
            ## request the protocol from the channel
            #print "  requesting %s protocol with params:"%ch, chParams
            p[ch] = self.channels[ch].generateProtocol(chParams)
        #print p
        return p
        
    def handleResult(self, result, params):
        #print "handling result:", result
        if result is None:
            return
        for ch in self.channels:
            #print "\nhandle result for", ch
            #print 'result:', type(result)
            #print result
            #print "--------\n"
            #if ch not in result:
                #print "  no result"
                #continue
            #print result.infoCopy()
            if result.hasColumn(0, ch):
                self.channels[ch].handleResult(result[ch], params)
            
            
    def quit(self):
        ProtocolGui.quit(self)
        for ch in self.channels:
            self.channels[ch].quit()
        