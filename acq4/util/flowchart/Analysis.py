# -*- coding: utf-8 -*-
from __future__ import print_function

from acq4.pyqtgraph.flowchart.library.common import *
import acq4.util.functions as functions
import numpy as np
import scipy
#from acq4.pyqtgraph import graphicsItems
import acq4.pyqtgraph as pg
import acq4.util.metaarray as metaarray
#import acq4.pyqtgraph.CheckTable as CheckTable
from collections import OrderedDict
from acq4.analysis.tools.Fitting import Fitting

class EventFitter(CtrlNode):
    """Takes a waveform and event list as input, returns extra information about each event.
    Optionally performs an exponential reconvolution before measuring each event.
    Plots fits of reconstructed events if the plot output is connected."""
    nodeName = "EventFitter"
    uiTemplate = [
        ('multiFit', 'check', {'value': False}),
        #('parallel', 'check', {'value': False}),
        #('nProcesses', 'spin', {'value': 1, 'min': 1, 'int': True}),
        ('plotFits', 'check', {'value': True}),
        ('plotGuess', 'check', {'value': False}),
        ('plotEvents', 'check', {'value': False}),
    ]
    
    
    def __init__(self, name):
        CtrlNode.__init__(self, name, terminals={
            'waveform': {'io': 'in'},
            'events': {'io': 'in'},
            'output': {'io': 'out'},
            'plot':  {'io': 'out'}
        })
        self.plotItems = []
        self.selectedFit = None
        self.deletedFits = []
        self.pool = None  ## multiprocessing pool
        self.poolSize = 0
        #self.ctrls['parallel'].toggled.connect(self.setupPool)
        #self.ctrls['nProcesses'].valueChanged.connect(self.setupPool)
    
    #def setupPool(self):
        #import multiprocessing as mp
        #if self.ctrls['parallel'].isChecked():
            #nProc = self.ctrls['nProcesses'].value()
            #if self.pool is not None and self.poolSize != nProc:
                #self.pool.terminate()
                #self.pool = None
            #if self.pool is None:
                #self.pool = mp.Pool(processes=nProc)
                #self.poolSize = nProc
        #else:
            #if self.pool is not None:
                #self.pool.terminate()
                #self.pool = None
    
    def process(self, waveform, events, display=True):
        self.deletedFits = []
        for item in self.plotItems:
            try:
                item.sigClicked.disconnect(self.fitClicked)
            except:
                pass
        self.plotItems = []
        
        tau = waveform.infoCopy(-1).get('expDeconvolveTau', None)
        dt = waveform.xvals(0)[1] - waveform.xvals(0)[0]
        opts = {
            'dt': dt, 'tau': tau, 'multiFit': self.ctrls['multiFit'].isChecked(),
            'waveform': waveform.view(np.ndarray),
            'tvals': waveform.xvals('Time'),
        }
        
        
        #if not self.ctrls['parallel'].isChecked():
        output = processEventFits(events, startEvent=0, stopEvent=len(events), opts=opts)
        guesses = output['guesses']
        eventData = output['eventData']
        indexes = output['indexes']
        xVals = output['xVals']
        yVals = output['yVals']
        output = output['output']
        #else:
            #print "parallel:", self.pool, self.poolSize
            #results = []
            #nProcesses = self.ctrls['nProcesses'].value()
            #evPerProcess = int(len(events) / nProcesses)
            #start = 0
            #for i in range(nProcesses):
                #stop = start + evPerProcess
                #if stop > len(events):
                    #stop = len(events)
                #args = (events, start, stop, opts)
                #results.append(self.pool.apply_async(processEventFits, args))
                #print "started process", start, stop
                #start = stop
            #data = []
            #guesses = []
            #eventData = []
            #indexes = []
            #xVals = []
            #yVals = []
            #for res in results:  ## reconstruct results here
                #print "getting result", res
                #output = res.get(10)
                #data.append(output['output'])
                #guesses.extend(output['guesses'])
                #eventData.extend(output['eventData'])
                #indexes.extend(output['indexes'])
                #xVals.extend(output['xVals'])
                #yVals.extend(output['yVals'])
            #output = np.concatenate(data)
            
        for i in range(len(indexes)):            
            if display and self['plot'].isConnected():
                if self.ctrls['plotFits'].isChecked():
                    item = pg.PlotDataItem(x=xVals[i], y=yVals[i], pen=(0, 0, 255), clickable=True)
                    item.setZValue(100)
                    self.plotItems.append(item)
                    item.eventIndex = indexes[i]
                    item.sigClicked.connect(self.fitClicked)
                    item.deleted = False
                if self.ctrls['plotGuess'].isChecked():
                    item2 = pg.PlotDataItem(x=xVals[i], y=functions.pspFunc(guesses[i], xVals[i]), pen=(255, 0, 0))
                    item2.setZValue(100)
                    self.plotItems.append(item2)
                if self.ctrls['plotEvents'].isChecked():
                    item2 = pg.PlotDataItem(x=xVals[i], y=eventData[i], pen=(0, 255, 0))
                    item2.setZValue(100)
                    self.plotItems.append(item2)
                #plot = list(self.plot.connections().keys())[0].node().getPlot()
                #plot.addItem(item)
            
        self.outputData = output
        return {'output': output, 'plot': self.plotItems}

    def deleteSelected(self):
        item = self.selectedFit
        d = not item.deleted
        if d:
            self.deletedFits.append(item.eventIndex)
            self.selectedFit.setPen((100, 0, 0))
        else:
            self.deletedFits.remove(item.eventIndex)
            self.selectedFit.setPen((0, 0, 255))
        item.deleted = d
            
        inds = np.ones(len(self.outputData), dtype=bool)
        inds[self.deletedFits] = False
        self.setOutput(output=self.outputData[inds], plot=self.plotItems)
        


    ## Intercept keypresses on any plot that is connected.
    def connected(self, local, remote):
        if local is self['plot']:
            self.filterPlot(remote.node())
            remote.node().sigPlotChanged.connect(self.filterPlot)
        CtrlNode.connected(self, local, remote)
        
    def disconnected(self, local, remote):
        if local is self['plot']:
            self.filterPlot(remote.node(), install=False)
            try:
                remote.node().sigPlotChanged.disconnect(self.filterPlot)
            except:
                pass
        CtrlNode.disconnected(self, local, remote)

    ## install event filter on remote plot (for detecting del key press)
    def filterPlot(self, node, install=True):
        plot = node.getPlot()
        if plot is None:
            return
        if install:
            plot.installEventFilter(self)
        else:
            plot.removeEventFilter(self)

    def fitClicked(self, curve):
        if self.selectedFit is not None:
            if self.selectedFit.deleted:
                self.selectedFit.setPen((100,0,0))
            else:
                self.selectedFit.setPen((0,0,255))
            
        self.selectedFit = curve
        curve.setPen((255,255,255))

    def eventFilter(self, obj, event):
        if self.selectedFit is None:
            return False
        if event.type() == Qt.QEvent.KeyPress and event.key() == Qt.Qt.Key_Delete:
            self.deleteSelected()
            return True
        return False

        
def processEventFits(events, startEvent, stopEvent, opts):
    ## This function does all the processing work for EventFitter.
    dt = opts['dt']
    origTau = opts['tau']
    multiFit = opts['multiFit']
    waveform = opts['waveform']
    tvals = opts['tvals']
    
    nFields = len(events.dtype.fields)
    
    dtype = [(n, events[n].dtype) for n in events.dtype.names]
    output = np.empty(len(events), dtype=dtype + [
        ('fitAmplitude', float), 
        ('fitTime', float),
        ('fitRiseTau', float), 
        ('fitDecayTau', float), 
        ('fitTimeToPeak', float),
        ('fitError', float),
        ('fitFractionalError', float),
        ('fitLengthOverDecay', float),
    ])
    
    offset = 0 ## not all input events will produce output events; offset keeps track of the difference.

    outputState = {
        'guesses': [],
        'eventData': [], 
        'indexes': [], 
        'xVals': [],
        'yVals': []
    }
    
    for i in range(startEvent, stopEvent):
        start = events[i]['time']
        #sliceLen = 50e-3
        sliceLen = dt*300. ## Ca2+ events are much longer than 50ms
        if i+1 < len(events):
            nextStart = events[i+1]['time']
            sliceLen = min(sliceLen, nextStart-start)
                
        guessLen = events[i]['len']*dt
        tau = origTau
        if tau is not None:
            guessLen += tau*2.
        #print i, guessLen, tau, events[i]['len']*dt

        #sliceLen = 50e-3
        sliceLen = guessLen
        if i+1 < len(events):  ## cut slice back if there is another event coming up
            nextStart = events[i+1]['time']
            sliceLen = min(sliceLen, nextStart-start)
        
        
        ## Figure out from where to pull waveform data that will be fitted
        startIndex = np.argwhere(tvals>=start)[0][0]
        stopIndex = startIndex + int(sliceLen/dt)
        eventData = waveform[startIndex:stopIndex]
        times = tvals[startIndex:stopIndex]
        #print i, startIndex, stopIndex, dt
        if len(times) < 4:  ## PSP fit requires at least 4 points; skip this one
            offset += 1
            continue
        
        ## reconvolve this chunk of the signal if it was previously deconvolved
        if tau is not None:
            eventData = functions.expReconvolve(eventData, tau=tau, dt=dt)
        #print i, len(eventData)
        ## Make guesses as to the shape of the event
        mx = eventData.max()
        mn = eventData.min()
        if mx > -mn:
            peakVal = mx
        else:
            peakVal = mn
        guessAmp = peakVal * 2  ## fit converges more reliably if we start too large
        guessRise = guessLen/4.
        guessDecay = guessLen/2.
        guessStart = times[0]
        
        zc = functions.zeroCrossingEvents(eventData - (peakVal/3.))
        ## eliminate events going the wrong direction
        if len(zc) > 0:
            if guessAmp > 0:
                zc = zc[zc['peak']>0]
            else:
                zc = zc[zc['peak']<0]
        #print zc    
        ## measure properties for the largest event within 10ms of start
        zc = zc[zc['index'] < 10e-3/dt]
        if len(zc) > 0:
            if guessAmp > 0:
                zcInd = np.argmax(zc['sum']) ## the largest event in this clip
            else:
                zcInd = np.argmin(zc['sum']) ## the largest event in this clip
            zcEv = zc[zcInd]
            #guessLen = dt*zc[zcInd]['len']
            guessRise = .1e-3 #dt*zcEv['len'] * 0.2
            guessDecay = dt*zcEv['len'] * 0.8 
            guessStart = times[0] + dt*zcEv['index'] - guessRise*3.
            
            ## cull down the data set if possible
            cullLen = zcEv['index'] + zcEv['len']*3
            if len(eventData) > cullLen:
                eventData = eventData[:cullLen]
                times = times[:cullLen]
                
            
        ## fitting to exponential rise * decay
        ## parameters are [amplitude, x-offset, rise tau, fall tau]
        guess = [guessAmp, guessStart, guessRise, guessDecay]
        #guess = [amp, times[0], guessLen/4., guessLen/2.]  ## careful! 
        bounds = [
            sorted((guessAmp * 0.1, guessAmp)),
            sorted((guessStart-min(guessRise, 0.01), guessStart+guessRise*2)), 
            sorted((dt*0.5, guessDecay)),
            sorted((dt*0.5, guessDecay * 50.))
        ]
        yVals = eventData.view(np.ndarray)
        
        fit = functions.fitPsp(times, yVals, guess=guess, bounds=bounds, multiFit=multiFit)
        
        computed = functions.pspFunc(fit, times)
        peakTime = functions.pspMaxTime(fit[2], fit[3])
        diff = (yVals - computed)
        err = (diff**2).sum()
        fracError = diff.std() / computed.std()
        lengthOverDecay = (times[-1] - fit[1]) / fit[3]  # ratio of (length of data that was fit : decay constant)
        output[i-offset] = tuple(events[i]) + tuple(fit) + (peakTime, err, fracError, lengthOverDecay)
        #output['fitTime'] += output['time']
            
        #print fit
        #self.events.append(eventData)
        
        outputState['guesses'].append(guess)
        outputState['eventData'].append(eventData)
        outputState['indexes'].append(i)
        outputState['xVals'].append(times)
        outputState['yVals'].append(computed)
        

    if offset > 0:
        output = output[:-offset]
        
    outputState['output'] = output
        
    return outputState

class CaEventFitter(EventFitter):
    nodeName="CaEventFitter"
    uiTemplate = [
            ('multiFit', 'check', {'value': False}),
            ('plotFits', 'check', {'value': True}),
            ('plotGuess', 'check', {'value': False}),
            ('plotEvents', 'check', {'value': False}),        
            ('Amplitude_UpperBound', 'spin', {'value':0.2, 'step':0.1, 'minStep':1e-4, 'dec':True, 'bounds':[0, None]}),
            ('RiseTau_UpperBound', 'spin', {'value':0.3, 'step':0.1, 'minStep':1e-6, 'dec':True, 'bounds':[0, None], 'siPrefix':True, 'suffix':'s'}),
            ('DecayTau_UpperBound', 'spin', {'value':2, 'step':0.1, 'minStep':1e-6, 'dec':True, 'bounds':[0, None], 'siPrefix':True, 'suffix':'s'})
        ]    
    
    def process(self, waveform, events, display=True):
        self.deletedFits = []
        for item in self.plotItems:
            try:
                item.sigClicked.disconnect(self.fitClicked)
            except:
                pass
        self.plotItems = []       
        
        tau = waveform.infoCopy(-1).get('expDeconvolveTau', None)
        dt = (waveform.xvals(0)[1:] - waveform.xvals(0)[:-1]).mean()
        
        opts = {
            'dt': dt, 
            'tau': tau, 
            'multiFit': self.ctrls['multiFit'].isChecked(),
            'waveform': waveform.view(np.ndarray),
            'tvals': waveform.xvals('Time'),
            'ampMax':self.ctrls['Amplitude_UpperBound'].value(),
            'riseTauMax':self.ctrls['RiseTau_UpperBound'].value(),
            'decayTauMax':self.ctrls['DecayTau_UpperBound'].value()
        }       
        
        
        output = self.fitEvents(events, startEvent=0, stopEvent=len(events), opts=opts)
        guesses = output['guesses']
        eventData = output['eventData']
        indexes = output['indexes']
        xVals = output['xVals']
        yVals = output['yVals']
        output = output['output'] 
        
        for i in range(len(indexes)):            
            if display and self['plot'].isConnected():
                if self.ctrls['plotFits'].isChecked():
                    item = pg.PlotDataItem(x=xVals[i], y=yVals[i], pen=(0, 0, 255), clickable=True)
                    item.setZValue(100)
                    self.plotItems.append(item)
                    item.eventIndex = indexes[i]
                    item.sigClicked.connect(self.fitClicked)
                    item.deleted = False
                if self.ctrls['plotGuess'].isChecked():
                    item2 = pg.PlotDataItem(x=xVals[i], y=functions.expPulse(guesses[i], xVals[i]), pen=(255, 0, 0))
                    item2.setZValue(100)
                    self.plotItems.append(item2)
                if self.ctrls['plotEvents'].isChecked():
                    item2 = pg.PlotDataItem(x=xVals[i], y=eventData[i], pen=(0, 255, 0))
                    item2.setZValue(100)
                    self.plotItems.append(item2)
                #plot = list(self.plot.connections().keys())[0].node().getPlot()
                #plot.addItem(item)
            
        self.outputData = output
        return {'output': output, 'plot': self.plotItems}

    @staticmethod
    def fitEvents(events, startEvent, stopEvent, opts):
        dt = opts['dt']
        origTau = opts['tau']
        multiFit = opts['multiFit']
        waveform = opts['waveform']
        tvals = opts['tvals']        
 
        dtype = [(n, events[n].dtype) for n in events.dtype.names]
        output = np.empty(len(events), dtype=dtype + [
            ('fitAmplitude', float), 
            ('fitTime', float),
            ('fitRiseTau', float), 
            ('fitDecayTau', float), 
            ('fitWidth', float),
            ('fitError', float),
            ('fitFractionalError', float)
        ]) 
        
        offset = 0 ## not all input events will produce output events; offset keeps track of the difference.
        
        outputState = {
                'guesses': [],
                'eventData': [], 
                'indexes': [], 
                'xVals': [],
                'yVals': []
            }        
        #print "=========="
        for i in range(startEvent, stopEvent):
            start = events[i]['time']
            sliceLen = events[i]['len']*dt +100.*dt ## Ca2+ events are much longer than 50ms
            if i+1 < len(events):
                nextStart = events[i+1]['time']
                #nextStart = events[i+1]['index']*dt
                #print "    picking between:", sliceLen, nextStart, '-', start, '=', nextStart-start
                sliceLen = min(sliceLen, nextStart-start)
            #print "   chose:", sliceLen
                
                
            guessLen = events[i]['len']*dt
            #guessLen = sliceLen
                    
            tau = origTau
            if tau is not None:
                guessLen += tau*2.              
            
            #print "   picking between:", guessLen*3, sliceLen
            #sliceLen = min(guessLen*3., sliceLen)
            
            ## Figure out from where to pull waveform data that will be fitted
            startIndex = np.argwhere(tvals>=start)[0][0]
            stopIndex = startIndex + int(sliceLen/dt)
            startIndex -= 10 ## pull baseline data from before the event starts
            #print "    data to fit: indices:", startIndex, stopIndex, 'dt:', dt, "times:", startIndex*dt, stopIndex*dt
            eventData = waveform[startIndex:stopIndex]
            times = tvals[startIndex:stopIndex]
            
            if len(times) < 4:  ## PSP fit requires at least 4 points; skip this one
                offset += 1
                continue
            
            ## reconvolve this chunk of the signal if it was previously deconvolved
            if tau is not None:
                eventData = functions.expReconvolve(eventData, tau=tau, dt=dt)                
    
            ## Make guesses as to the shape of the event
            mx = eventData.max()
            mn = eventData.min()

            guessAmp = (mx-mn)*2     ## fit converges more reliably if we start too large
            guessRise = guessLen/4.
            guessDecay = guessLen/4.
            guessStart = times[10]
            guessWidth = guessLen*0.75
            guessYOffset = eventData[0]
            
            ## fitting to exponential rise * decay
            ## parameters are [amplitude, x-offset, rise tau, fall tau]
            guess = [guessStart, guessYOffset, guessRise, guessDecay, guessAmp, guessWidth]
            guessFit = [guessYOffset, guessStart, guessRise, guessDecay, guessAmp, guessWidth]
            #guess = [amp, times[0], guessLen/4., guessLen/2.]  ## careful! 
            #bounds = [
                #sorted((guessAmp * 0.1, guessAmp)),
                #sorted((guessStart-guessRise*2, guessStart+guessRise*2)), 
                #sorted((dt*0.5, guessDecay)),
                #sorted((dt*0.5, guessDecay * 50.))
            #]
            yVals = eventData.view(np.ndarray)
            
            ## Set bounds for parameters -
            ## exppulse parameter order: yOffset, t0, tau1, tau2, amp, width
            #yOffset, t0, tau1, tau2, amp, width
            bounds=[(-10, 10), ## no bounds on yOffset
                    (float(events[i]['time']-10*dt), float(events[i]['time']+5*dt)), ## t0 must be near the startpoint found by eventDetection
                    (0.010, float(opts['riseTauMax'])), ## riseTau must be greater than 10 ms
                    (0.010, float(opts['decayTauMax'])), ## ditto for decayTau
                    (0., float(opts['ampMax'])), ## amp must be greater than 0
                    (0, float(events[i]['len']*dt*2))] ## width
            
            #print "Bounds", bounds
            #print "times", times.min(), times.max()
            
            ## Use Paul's fitting algorithm so that we can put bounds/constraints on the fit params
            #print "event:", i, 'amp bounds:', bounds[4]
            fitter = Fitting()
            fitResults = fitter.FitRegion([1], 0, times, yVals, fitPars=guessFit, fitFunc='exppulse', bounds=bounds, method='SLSQP', dataType='xy')
            fitParams, xPts, yPts, names = fitResults
            #print "fitParams:", fitParams
            #print "names", names
            #fitResult = functions.fit(functions.expPulse, times, yVals, guess, generateResult=True, resultXVals=times)                
            #fitParams, val, computed, err = fitResult
            #print '  fitParams:', fitParams[0]
            yOffset, t0, tau1, tau2, amp, width = fitParams[0]
            #print "fitResult", fitResult
            #computed = fitResult[-2]
            computed = fitter.expPulse(fitParams[0], times)
            diff = (yVals - computed)
            err = (diff**2).sum()
            fracError = diff.std() / computed.std()
            
            output[i-offset] = tuple(events[i]) + (amp, t0, tau1, tau2, width) + (err, fracError)
            #print "amp:", amp
            #print "output:", output[i-offset]
            
            outputState['guesses'].append(guess)
            outputState['eventData'].append(eventData)
            outputState['indexes'].append(i)
            outputState['xVals'].append(times)
            outputState['yVals'].append(computed)  
                
        if offset > 0:
            output = output[:-offset]
            
        outputState['output'] = output
            
        return outputState                
                
class Histogram(CtrlNode):
    """Converts a list of values into a histogram."""
    nodeName = 'Histogram'
    uiTemplate = [
        ('numBins', 'intSpin', {'value': 100, 'min': 3, 'max': 100000})
    ]
    
    def processData(self, In):
        data = In.view(np.ndarray)
        units = None
        if (hasattr(In, 'implements') and In.implements('MetaArray')):
            units = In.axisUnits(1)
        y,x = np.histogram(data, bins=self.ctrls['numBins'].value())
        x = (x[1:] + x[:-1]) * 0.5
        return metaarray.MetaArray(y, info=[{'name': 'bins', 'values': x, 'units': units}])
        



class StatsCalculator(Node):
    """Calculates avg, sum, median, min, max, and stdev from input."""
    nodeName = "StatsCalculator"
    
    def __init__(self, name):
        Node.__init__(self, name, terminals={
            'data': {'io': 'in'},
            'regions': {'io': 'in', 'multi': True},
            'stats': {'io': 'out'}
        })
        self.funcs = OrderedDict([
            ('sum', np.sum),
            ('avg', np.mean),
            ('med', np.median),
            ('min', np.min),
            ('max', np.max),
            ('std', np.std)
        ])
        
        self.ui = pg.CheckTable(list(self.funcs.keys()))
        #Qt.QObject.connect(self.ui, Qt.SIGNAL('stateChanged'), self.update)
        self.ui.sigStateChanged.connect(self.update)
        
    def ctrlWidget(self):
        return self.ui
        
    def process(self, data, regions=None, display=True):
        keys = list(data.dtype.fields.keys())
        if len(keys) == 0:
            return {'stats': None}  ## Avoid trashing the UI and its state if possible..
        self.ui.updateRows(keys)
        state = self.ui.saveState()
        stats = OrderedDict()
        cols = state['cols']
        if regions is None:
            regions = {}
        
        dataRegions = {'all': data}
        #print "regions:"
        items = list(regions.items())
        for name, r in items:
            #print "  ", term, r
            if isinstance(r, dict):
                items.extend(list(r.items()))
                continue
            try:
                mask = (data['fitTime'] > r[0]) * (data['fitTime'] < r[1])
            except:
                mask = (data['time'] > r[0]) * (data['time'] < r[1])
            dataRegions[name] = data[mask]
        
        for row in state['rows']:  ## iterate over variables in data
            name = row[0]
            flags = row[1:]
            for i in range(len(flags)):  ## iterate over stats operations
                if flags[i]:
                    for rgnName, rgnData in dataRegions.items():  ## iterate over regions
                        v = rgnData[name]
                        fn = self.funcs[cols[i]]
                        if len(v) > 0:
                            result = fn(v)
                        else:
                            result = 0.0
                        stats[name+'_'+rgnName+'_'+cols[i]] = result
        return {'stats': stats}
        
    def saveState(self):
        state = Node.saveState(self)
        state['ui'] = self.ui.saveState()
        return state
        
    def restoreState(self, state):
        Node.restoreState(self, state)
        self.defaultState = state
        self.ui.restoreState(state['ui'])
        
        

class PointCombiner(Node):
    """Takes a list of spot properties and combines all of the overlapping spots."""
    nodeName = "CombinePoints"
    
    def __init__(self, name):
        Node.__init__(self, name, terminals={
            'input': {'io': 'in'},
            'output': {'io': 'out'}
        })
        
    def process(self, input, display=True):
        points = []
        for rec in input:
            x = rec['posX']
            y = rec['posY']
            size = rec['spotSize']
            threshold = size*0.2
            matched = False
            for p in points:
                if abs(p['posX']-x) < threshold and abs(p['posY']-y) < threshold:
                    #print "matched point"
                    p['recs'][rec['file']] = rec
                    matched = True
                    break
            if not matched:
                #print "point did not match:", x, y, rec['file']
                points.append({'posX': x, 'posY': y, 'recs': {rec['file']: rec}})
        
        output = []
        i = 0
        for pt in points:
            rec = {}
            keys = list(pt['recs'].keys())
            names = list(pt['recs'][keys[0]].keys())
            for name in names:
                vals = [pt['recs'][k][name] for k in keys] 
                try:
                    if len(vals) > 2:
                        val = np.median(vals)
                    else:
                        val = np.mean(vals)
                    rec[name] = val
                except:
                    pass
                    #print "Error processing vals: ", vals
                    #raise
            rec['sources'] = keys
            rec['posX'] = pt['posX']
            rec['posY'] = pt['posY']
            output.append(rec)
        return {'output': output}
        
        
        
class RegionLabeler(Node):
    """Adds a column to an event list which labels each event with the region it appears in (if any)."""
    nodeName = "LabelRegions"
    
    def __init__(self, name):
        Node.__init__(self, name, terminals={
            'events': {'io': 'in'},
            'regions': {'io': 'in', 'multi': True},
            'output': {'io': 'out', 'bypass': 'events'}
        })

    def process(self, events, regions, display=True):
        terms = list(regions.keys())
        names = [term.node().name() for term in terms]
        maxLen = max(list(map(len, names)))
        dtype = [(n, events[n].dtype) for n in events.dtype.names]
        output = np.empty(len(events), dtype=dtype + [('region', '|S%d'%maxLen)])
        
        starts = np.empty((len(regions), 1))
        stops = np.empty((len(regions), 1))
        for i in range(len(regions)):
            rgn = regions[terms[i]]
            starts[i,0] = rgn[0]
            stops[i,0] = rgn[1]
            
        try:
            times = events['fitTime'][np.newaxis,:]
        except:
            times = events['time'][np.newaxis,:]
            
        match = (times >= starts) * (times <= stops)
        
        for i in range(len(events)):
            m = np.argwhere(match[:,i])
            if len(m) == 0:
                rgn = ''
            else:
                rgn = names[int(m[0])]
            output[i] = tuple(events[i]) + (rgn,)
        
        return {'output': output}


class EventMasker(CtrlNode):
    """Removes events from a list which occur within masking regions (used for removing noise)
    Accepts a list of regions or a list of times (use padding to give width to each time point)"""
    nodeName = "EventMasker"
    uiTemplate = [
        ('prePadding', 'spin', {'value': -2e-3, 'step': 1e-3, 'bounds': [None, 0], 'siPrefix': True, 'suffix': 's'}),
        ('postPadding', 'spin', {'value': 1e-3, 'step': 1e-3, 'bounds': [0, None], 'siPrefix': True, 'suffix': 's'}),
        #('prePadding', 'intSpin', {'min': 0, 'max': 1e9}),
        #('postPadding', 'intSpin', {'min': 0, 'max': 1e9}),
    ]
    
    def __init__(self, name):
        CtrlNode.__init__(self, name, terminals={
            'events': {'io': 'in'},
            'regions': {'io': 'in'},
            'output': {'io': 'out', 'bypass': 'events'}
        })
    
    def process(self, events, regions, display=True):
        ##print "From masker:", events
        ###events = events.copy()
        
        #prep = self.ctrls['prePadding'].value()
        #postp = self.ctrls['postPadding'].value()
        
        #starts = (regions['index']-prep)[:,np.newaxis]
        #stops = (regions['index']+prep)[:,np.newaxis]
        
        #times = events['index'][np.newaxis, :]
        #mask = ((times >= starts) * (times <= stops)).sum(axis=0) == 0
        
        prep = self.ctrls['prePadding'].value()
        postp = self.ctrls['postPadding'].value()
        
        starts = (regions['time']+prep)[:,np.newaxis]
        stops = (regions['time']+postp)[:,np.newaxis]
        
        times = events['fitTime'][np.newaxis, :]
        mask = ((times >= starts) * (times <= stops)).sum(axis=0) == 0
        return {'output': events[mask]}
        

class CellHealthAnalyzer(CtrlNode):
    
    nodeName = 'CellHealthAnalyzer'
    uiTemplate = [
        ('start', 'spin', {'min':0, 'suffix': 's', 'siPrefix':True, 'step':0.1, 'minStep':0.0001, 'value':0.8}),
        ('stop', 'spin', {'min':0, 'suffix': 's', 'siPrefix':True, 'step':0.1, 'minStep':0.0001, 'value':1.0}),
        ('mode', 'combo', {'values':['VC', 'IC']}),
        ('SeriesResistance', 'check', {'value':True}),
        ('MembraneResistance', 'check', {'value':True}),
        ('HoldingCurrent', 'check', {'value': True}),
        ('RestingPotential', 'check', {'value':True}),
        ('Capacitance', 'check', {'value': True}),
        ('FitError', 'check', {'value': True})
        ]
        

    
    def __init__(self, name):
        CtrlNode.__init__(self, name, terminals={
            'data': {'io': 'in'},
            'stats': {'io': 'out'}
        })
        
    #def process(self, waveform):
        #print "CellHealthAnalyzer.process called."
        
    def process(self, data, display=None):
        cmd = data['command']['Time':self.ctrls['start'].value():self.ctrls['stop'].value()]
        #data = waveform['primary']['Time':self.ctrls['start'].value():self.ctrls['stop'].value()]
        
        pulseStart = cmd.axisValues('Time')[np.argwhere(cmd != cmd[0])[0][0]]
        pulseStop = cmd.axisValues('Time')[np.argwhere(cmd != cmd[0])[-1][0]]
        
        #print "\n\nAnalysis parameters:", params
        ## Extract specific time segments
        nudge = 0.1e-3
        base = data['Time': :(pulseStart-nudge)]
        pulse = data['Time': (pulseStart+nudge):(pulseStop-nudge)]
        pulseEnd = data['Time': pulseStart+((pulseStop-pulseStart)*2./3.):pulseStop-nudge]
        end = data['Time': (pulseStop+nudge): ]
        #print "time ranges:", pulse.xvals('Time').min(),pulse.xvals('Time').max(),end.xvals('Time').min(),end.xvals('Time').max()
        pulseAmp = pulse['command'].mean() - base['command'].mean()
        
        ### Exponential fit
        ##  v[0] is offset to start of exp
        ##  v[1] is amplitude of exp
        ##  v[2] is tau
        def expFn(v, t):
            return (v[0]-v[1]) + v[1] * np.exp(-t / v[2])
        
        ## predictions
        ar = 10e6
        ir = 200e6
        if self.ctrls['mode'].currentText() == 'VC':
            ari = pulseAmp / ar
            iri = pulseAmp / ir
            pred1 = [ari, ari-iri, 1e-3]
            pred2 = [iri-ari, iri-ari, 1e-3]
        else:
            #clamp = self.manager.getDevice(self.clampName)
            try:
                bridge = data._info[-1]['ClampState']['ClampParams']['BridgeBalResist']
                bridgeOn = data._info[-1]['ClampState']['ClampParams']['BridgeBalEnabled']
                #bridge = float(clamp.getParam('BridgeBalResist'))  ## pull this from the data instead.
                #bridgeOn = clamp.getParam('BridgeBalEnable')
                if not bridgeOn:
                    bridge = 0.0
            except:
                bridge = 0.0
            #print "bridge:", bridge
            arv = pulseAmp * ar - bridge
            irv = pulseAmp * ir
            pred1 = [arv, -irv, 10e-3]
            pred2 = [irv, irv, 50e-3]
            
        # Fit exponential to pulse and post-pulse traces
        tVals1 = pulse.xvals('Time')-pulse.xvals('Time').min()
        tVals2 = end.xvals('Time')-end.xvals('Time').min()
        
        baseMean = base['primary'].mean()
        fit1 = scipy.optimize.leastsq(
            lambda v, t, y: y - expFn(v, t), pred1, 
            args=(tVals1, pulse['primary'] - baseMean),
            maxfev=200, full_output=1)
        #fit2 = scipy.optimize.leastsq(
            #lambda v, t, y: y - expFn(v, t), pred2, 
            #args=(tVals2, end['primary'] - baseMean),
            #maxfev=200, full_output=1, warning=False)
            
        
        #err = max(abs(fit1[2]['fvec']).sum(), abs(fit2[2]['fvec']).sum())
        err = abs(fit1[2]['fvec']).sum()
        
        
        # Average fit1 with fit2 (needs massaging since fits have different starting points)
        #print fit1
        fit1 = fit1[0]
        #fit2 = fit2[0]
        #fitAvg = [   ## Let's just not do this.
            #0.5 * (fit1[0] - (fit2[0] - (fit1[0] - fit1[1]))),
            #0.5 * (fit1[1] - fit2[1]),
            #0.5 * (fit1[2] + fit2[2])            
        #]
        fitAvg = fit1

        (fitOffset, fitAmp, fitTau) = fit1
        #print fit1
        
        fitTrace = np.empty(len(data))
        
        ## Handle analysis differently depending on clamp mode
        if self.ctrls['mode'].currentText() == 'VC':
            iBase = base['Channel': 'primary']
            iPulse = pulse['Channel': 'primary'] 
            iPulseEnd = pulseEnd['Channel': 'primary'] 
            vBase = base['Channel': 'command']
            vPulse = pulse['Channel': 'command'] 
            vStep = vPulse.mean() - vBase.mean()
            sign = [-1, 1][vStep > 0]

            iStep = sign * max(1e-15, sign * (iPulseEnd.mean() - iBase.mean()))
            iRes = vStep / iStep
            
            ## From Santos-Sacchi 1993
            pTimes = pulse.xvals('Time')
            iCapEnd = pTimes[-1]
            iCap = iPulse['Time':pTimes[0]:iCapEnd] - iPulseEnd.mean()
            Q = sum(iCap) * (iCapEnd - pTimes[0]) / iCap.shape[0]
            Rin = iRes
            Vc = vStep
            Rs_denom = (Q * Rin + fitTau * Vc)
            if Rs_denom != 0.0:
                Rs = (Rin * fitTau * Vc) / Rs_denom
                Rm = Rin - Rs
                Cm = (Rin**2 * Q) / (Rm**2 * Vc)
            else:
                Rs = 0
                Rm = 0
                Cm = 0
                
            #aRes = Rs
            RsPeak = iPulse.min()
            aRes = vStep/(RsPeak-iBase.mean()) ## just using Ohm's law
            cap = Cm
            
        if self.ctrls['mode'].currentText() == 'IC':
            iBase = base['Channel': 'command']
            iPulse = pulse['Channel': 'command'] 
            vBase = base['Channel': 'primary']
            vPulse = pulse['Channel': 'primary'] 
            vPulseEnd = pulseEnd['Channel': 'primary'] 
            iStep = iPulse.mean() - iBase.mean()
            
            if iStep >= 0:
                vStep = max(1e-5, -fitAmp)
            else:
                vStep = min(-1e-5, -fitAmp)
           
            if iStep == 0:
                iStep = 1e-14
                
            iRes = (vStep / iStep)
            aRes = (fitOffset / iStep) + bridge
            cap = fitTau / iRes
            
            
        rmp = vBase.mean()
        rmps = vBase.std()
        rmc = iBase.mean()
        rmcs = iBase.std()
        #print rmp, rmc
        
        ## use ui to determine which stats to return
        stats = {}
        if self.ctrls['SeriesResistance'].isChecked():
            stats['SeriesResistance'] = aRes
        if self.ctrls['MembraneResistance'].isChecked():
            stats['MembraneResistance'] = iRes
        if self.ctrls['Capacitance'].isChecked():
            stats['Capacitance'] = cap
        if self.ctrls['HoldingCurrent'].isChecked():
            stats['HoldingCurrent'] = rmc
        if self.ctrls['FitError'].isChecked():
            stats['FitError'] = err
        if self.ctrls['RestingPotential'].isChecked():
            stats['RestingPotential'] = rmp
            
        #return {'stats':{
            #'inputResistance': iRes, 
            #'accessResistance': aRes,
            #'capacitance': cap,
            #'restingPotential': rmp, 'restingPotentialStd': rmps,
            #'restingCurrent': rmc, 'restingCurrentStd': rmcs,
            #'fitError': err,
            #'fitTrace': fitTrace
        #}}
        return {'stats': stats}
    
    #def saveState(self):
        #state = CtrlNode.saveState(self)
        #state['ui'] = self.ui.saveState()
        #return state
        
    #def restoreState(self, state):
        #CtrlNode.restoreState(self, state)
        #self.defaultState = state
        #self.ui.restoreState(state['ui'])
        
        
class PSPFitter(CtrlNode):
    """Fit data to a PSP template"""
    nodeName = "PSPFitter"
    uiTemplate = [
        #('prePadding', 'spin', {'value': 0, 'step': 1e-3, 'minStep': 1e-6, 'dec': True, 'range': [None, None], 'siPrefix': True, 'suffix': 's'}),
        #('postPadding', 'spin', {'value': 0.1, 'step': 1e-3, 'minStep': 1e-6, 'dec': True, 'range': [None, None], 'siPrefix': True, 'suffix': 's'}),
        ('computeWaveform', 'check', {'value': True}),
        ('risePower', 'spin', {'min': 0, 'max': 10}),
        ('guessAmp1', 'spin', {'min': None, 'max': None}),
        ('guessAmp2', 'spin', {'min': None, 'max': None}),
        ('guessTime', 'spin', {'min': 0, 'max': None, 'siPrefix': True, 'suffix': 's'}),
        ('guessRise', 'spin', {'min': 0, 'max': None, 'siPrefix': True, 'suffix': 's'}),
        ('guessDecay', 'spin', {'min': 0, 'max': None, 'siPrefix': True, 'suffix': 's'}),
        ('guessDecay2', 'spin', {'min': 0, 'max': None, 'siPrefix': True, 'suffix': 's'}),
        ('minAmp1', 'spin', {'min': None, 'max': None}),
        ('maxAmp1', 'spin', {'min': None, 'max': None}),
        ('minAmp2', 'spin', {'min': None, 'max': None}),
        ('maxAmp2', 'spin', {'min': None, 'max': None}),
        ('minTime', 'spin', {'min': 0, 'max': None, 'siPrefix': True, 'suffix': 's'}),
        ('maxTime', 'spin', {'min': 0, 'max': None, 'siPrefix': True, 'suffix': 's'}),
        ('minRise', 'spin', {'min': 0, 'max': None, 'siPrefix': True, 'suffix': 's'}),
        ('maxRise', 'spin', {'min': 0, 'max': None, 'siPrefix': True, 'suffix': 's'}),
        ('minDecay', 'spin', {'min': 0, 'max': None, 'siPrefix': True, 'suffix': 's'}),
        ('maxDecay', 'spin', {'min': 0, 'max': None, 'siPrefix': True, 'suffix': 's'}),
        ('minDecay2', 'spin', {'min': 0, 'max': None, 'siPrefix': True, 'suffix': 's'}),
        ('maxDecay2', 'spin', {'min': 0, 'max': None, 'siPrefix': True, 'suffix': 's'}),
    ]
    
    def __init__(self, name):
        CtrlNode.__init__(self, name, terminals={
            'data': {'io': 'in'},
            'fitParams': {'io': 'out'},
            'fitXData': {'io': 'out'},
            'fitYData': {'io': 'out'},
        })
    
    def process(self, data, display=True):
        params = ['Amp1', 'Amp2', 'Time', 'Rise', 'Decay', 'Decay2']
        guess = tuple([self.ctrls['guess' + name].value() for name in params])
        bounds = [(self.ctrls['min' + name].value(), self.ctrls['max' + name].value()) for name in params]
        rp = self.ctrls['risePower'].value()
        
        minTime = self.ctrls['minTime'].value()
        times = data.xvals('Time')
        fullTimes = times
        data = data.view(np.ndarray)
        
        startInd = np.argwhere(times>=minTime)[0]
        
        times = times[startInd:]
        data = data[startInd:]
        
        ## Ignore specified guess amplitude; make a better guess.
        mx = data.max()
        mn = data.min()
        if abs(mn) > abs(mx):
            amp = mn
        else:
            amp = mx
        params[0] = amp
        params[1] = amp
        
        
        
        fit = functions.fitDoublePsp(x=times, y=data, guess=guess, bounds=bounds, risePower=rp)
        
        if self.ctrls['computeWaveform'].isChecked():
            fitData = functions.doublePspFunc(fit, fullTimes, rp)
        else:
            fitData = None
        return {'fitParams': fit, 'fitYData': fitData, 'fitXData': fullTimes}



class RemoveDirect(CtrlNode):
    """Remove direct stimulation from trace and report fit parameters."""
    nodeName = "RemoveDirect"
    uiTemplate = [
        #('prePadding', 'spin', {'value': 0, 'step': 1e-3, 'minStep': 1e-6, 'dec': True, 'range': [None, None], 'siPrefix': True, 'suffix': 's'}),
        #('postPadding', 'spin', {'value': 0.1, 'step': 1e-3, 'minStep': 1e-6, 'dec': True, 'range': [None, None], 'siPrefix': True, 'suffix': 's'}),
        ('stimulusTime', 'spin', {'min': 0, 'max': None, 'value': 0.5, 'siPrefix': True, 'suffix': 's'}),
        ('subtractDirect', 'check', {'value': True}),
        ('risePower', 'spin', {'min': 0, 'max': 10, 'value': 2.0}),
        ('plotColor', 'color'),
        ('minDirectDuration', 'spin', {'min': 0, 'max': None, 'value': 0.01, 'siPrefix': True, 'suffix': 's'}),
        #('guessTime', 'spin', {'min': 0, 'max': None, 'siPrefix': True, 'suffix': 's'}),
        #('guessRise', 'spin', {'min': 0, 'max': None, 'siPrefix': True, 'suffix': 's'}),
        #('guessDecay', 'spin', {'min': 0, 'max': None, 'siPrefix': True, 'suffix': 's'}),
        #('guessDecay2', 'spin', {'min': 0, 'max': None, 'siPrefix': True, 'suffix': 's'}),
        #('minAmp1', 'spin', {'min': None, 'max': None}),
        #('maxAmp1', 'spin', {'min': None, 'max': None}),
        #('minAmp2', 'spin', {'min': None, 'max': None}),
        #('maxAmp2', 'spin', {'min': None, 'max': None}),
        #('minTime', 'spin', {'min': 0, 'max': None, 'siPrefix': True, 'suffix': 's'}),
        #('maxTime', 'spin', {'min': 0, 'max': None, 'siPrefix': True, 'suffix': 's'}),
        #('minRise', 'spin', {'min': 0, 'max': None, 'siPrefix': True, 'suffix': 's'}),
        #('maxRise', 'spin', {'min': 0, 'max': None, 'siPrefix': True, 'suffix': 's'}),
        #('minDecay', 'spin', {'min': 0, 'max': None, 'siPrefix': True, 'suffix': 's'}),
        #('maxDecay', 'spin', {'min': 0, 'max': None, 'siPrefix': True, 'suffix': 's'}),
        #('minDecay2', 'spin', {'min': 0, 'max': None, 'siPrefix': True, 'suffix': 's'}),
        #('maxDecay2', 'spin', {'min': 0, 'max': None, 'siPrefix': True, 'suffix': 's'}),
    ]
    
    def __init__(self, name):
        CtrlNode.__init__(self, name, terminals={
            'data': {'io': 'in'},
            'fitParams': {'io': 'out'},
            'output': {'io': 'out', 'bypass': 'data'},
            'plot': {'io': 'out'},
        })
        self.plotItem = pg.PlotDataItem()
    
    def process(self, data, display=True):
        
        rp = self.ctrls['risePower'].value()
        stimTime = self.ctrls['stimulusTime'].value()
        times = data.xvals('Time')
        dt = times[1] - times[0]
        data1 = data.view(np.ndarray)
        if stimTime > times[-1]:
            raise Exception("stimulusTime is larger than length of input data.")
        stimInd = np.argwhere(times>=stimTime)[0][0]
        
        # 1. make sure offset is removed
        offset = np.median(data1[:stimInd])
        data2 = data1 - offset
        
        # 2. check for zero-crossing events within 4ms after stimulus
        cross = functions.zeroCrossingEvents(data2[stimInd:])
        maxInd = 4e-3 / dt
        minLength = self.ctrls['minDirectDuration'].value() / dt
        gotEvent = None
        for start, length, sum, peak in cross:
            if start > maxInd:
                break
            if length < minLength:
                continue
            if gotEvent is None or length > gotEvent[1]:
                gotEvent = (start+stimInd, length)
        #if len(cross) == 0: ## must be a single large event
            #gotEvent = (0, len(data2)-stimInd)
        
        fitParams = dict(
            directFitAmp1=0., directFitAmp2=0., directFitTime=0., 
            directFitRise=0., directFitDecay1=0., directFitDecay2=0.,
            directFitPeakTime=0., directFitPeak=0., directFitSubtracted=False,
            directFitValid=False,
            )
        
        # 3. if there is no large event near stimulus, return original data
        if gotEvent is None:
            if display:
                self.plotItem.clear()
            return {'output': data, 'fitParams': fitParams, 'plot': self.plotItem}
        
        #print "============"
        #print stimInd
        #print gotEvent
        #print cross[:20]
        
        # 4. guess amplitude, tau from detected event
        evStart = gotEvent[0]
        evEnd = evStart + gotEvent[1]
        evRgn = data2[evStart:evEnd]
        #pg.plot(evRgn)
        mx = evRgn.max()
        mn = evRgn.min()
        ampGuess = mx if abs(mx) > abs(mn) else mn
        tauGuess = gotEvent[1] * dt
        if ampGuess < 0:
            ampBound = [None, 0]
        else:
            ampBound = [0, None]
        
        # 5. fit
        guess = [ampGuess*2, ampGuess*2, stimTime, 1e-3, tauGuess*0.5, tauGuess*2]
        bounds = [
            ampBound, ampBound,
            [stimTime, stimTime+4e-3],
            [1e-4, 100e-3],
            [1e-3, 1],
            [5e-3, 10],
        ]
        #print guess
        #print bounds
        endInd = evStart + gotEvent[1] * 10
        fitYData = data2[stimInd:endInd]
        fitXData = times[stimInd:endInd]
        fit = functions.fitDoublePsp(x=fitXData, y=fitYData, guess=guess, bounds=bounds, risePower=rp)
        
        # 6. subtract fit from original data (offset included), return
        y = functions.doublePspFunc(fit, times, rp)
        
        if display:
            self.plotItem.setData(x=fitXData, y=y[stimInd:endInd], pen=self.ctrls['plotColor'].color())        
            
        ## prepare list of fit params for output
        (xMax, yMax) = functions.doublePspMax(fit)
        xMax -= fit[2]  ## really interested in time-to-peak, not the exact peak time.
        
        fitParams = dict(
            directFitAmp1=fit[0], directFitAmp2=fit[1], directFitTime=fit[2], 
            directFitRise=fit[3], directFitDecay1=fit[4], directFitDecay2=fit[5],
            directFitPeakTime=xMax, directFitPeak=yMax, directFitSubtracted=None, directFitValid=True,
            )
            
        if self.ctrls['subtractDirect'].isChecked():
            out = metaarray.MetaArray(data-y, info=data.infoCopy())
            fitParams['directFitSubtracted'] = True
        else:
            out = data
            fitParams['directFitSubtracted'] = False
            
            
        return {'fitParams': fitParams, 'output': out, 'plot': self.plotItem}

