# -*- coding: utf-8 -*-

from pyqtgraph.flowchart.library.common import *
import functions
import numpy as np
import scipy
#from pyqtgraph import graphicsItems
import pyqtgraph as pg
import metaarray
#import pyqtgraph.CheckTable as CheckTable
from collections import OrderedDict

class EventFitter(CtrlNode):
    """Takes a waveform and event list as input, returns extra information about each event.
    Optionally performs an exponential reconvolution before measuring each event.
    Plots fits of reconstructed events if the plot output is connected."""
    nodeName = "EventFitter"
    uiTemplate = [
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
        
    def process(self, waveform, events, display=True):
        self.deletedFits = []
        for item in self.plotItems:
            try:
                item.sigClicked.disconnect(self.fitClicked)
            except:
                pass
        self.plotItems = []
        
        tau = waveform.infoCopy(-1).get('expDeconvolveTau', None)
        nFields = len(events.dtype.fields)
        
        dtype = [(n, events[n].dtype) for n in events.dtype.names]
        dt = waveform.xvals(0)[1] - waveform.xvals(0)[0]
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
        
        for i in range(len(events)):
            start = events[i]['time']
            sliceLen = 50e-3
            if i+1 < len(events):
                nextStart = events[i+1]['time']
                sliceLen = min(sliceLen, nextStart-start)
                    
            guessLen = events[i]['len']*dt
            
            if tau is None:
                tau = waveform._info[-1].get('expDeconvolveTau', None)
            if tau is not None:
                guessLen += tau*2.
            
            sliceLen = min(guessLen*3., sliceLen)
            
            eventData = waveform['Time':start:start+sliceLen]
            times = eventData.xvals(0)
            if len(times) < 4:  ## PSP fit requires at least 4 points; skip this one
                offset += 1
                continue
            
            ## reconvolve this chunk of the signal if it was previously deconvolved
            if tau is not None:
                eventData = functions.expReconvolve(eventData, tau=tau)

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
                
            ## guess how large the event is
            ## we're trying to measure the size of the event at 1/3 peak value
            
            #print "Event", i, times[0]
            #print "   amp:", guessAmp
            
            zc = functions.zeroCrossingEvents(eventData - (peakVal/3.))
            
            ## eliminate events going the wrong direction
            if len(zc) > 0:
                if guessAmp > 0:
                    zc = zc[zc['peak']>0]
                else:
                    zc = zc[zc['peak']<0]
            #print zc    
            ## measure properties for the largest event
            if len(zc) > 0:
                if guessAmp > 0:
                    zcInd = np.argmax(zc['sum']) ## the largest event in this clip
                else:
                    zcInd = np.argmin(zc['sum']) ## the largest event in this clip
                zcEv = zc[zcInd]
                #guessLen = dt*zc[zcInd]['len']
                guessRise = dt*zcEv['len'] * 0.2
                guessDecay = dt*zcEv['len'] * 0.8 
                guessStart = times[0] + dt*zcEv['index'] - guessRise
                
                ## cull down the data set if possible
                cullLen = zcEv['index'] + zcEv['len']*3
                if len(eventData) > cullLen:
                    eventData = eventData[:cullLen]
                    times = times[:cullLen]
                    
            #print "===== event %d: %f =====" % (i, events[i]['time'])
            #print zc
            #print "rise:", guessRise
            #print 'decay:', guessDecay
            #if len(zc) == 0:
                #print "  ---> no zero-crossing events:"
                #print "  guessAmp:", guessAmp
                #print eventData - (guessAmp/3.)
                
            ## fitting to exponential rise * decay
            ## parameters are [amplitude, x-offset, rise tau, fall tau]
            guess = [guessAmp, guessStart, guessRise, guessDecay]
            #guess = [amp, times[0], guessLen/4., guessLen/2.]  ## careful! 
            bounds = [
                sorted((guessAmp * 0.1, guessAmp)),
                sorted((guessStart-guessRise*2, guessStart+guessRise*2)), 
                sorted((dt*0.5, guessDecay)),
                sorted((dt*0.5, guessDecay * 50.))
            ]
            yVals = eventData.view(np.ndarray)
            
            fit = functions.fitPsp(times, yVals, guess=guess, bounds=bounds)
            
            computed = functions.pspFunc(fit, times)
            peakTime = functions.pspMaxTime(fit[2], fit[3])
            err = abs(yVals - computed).sum()
            fracError = err / abs(computed).sum()
            lengthOverDecay = (times[-1] - fit[1]) / fit[3]  # ratio of (length of data that was fit : decay constant)
            output[i-offset] = tuple(events[i]) + tuple(fit) + (peakTime, err, fracError, lengthOverDecay)
            #output['fitTime'] += output['time']
                
            #print fit
            #self.events.append(eventData)
            
            if display and self.plot.isConnected():
                if self.ctrls['plotFits'].isChecked():
                    item = pg.PlotCurveItem(computed, times, pen=(0, 0, 255), clickable=True)
                    item.setZValue(100)
                    self.plotItems.append(item)
                    item.eventIndex = i
                    item.sigClicked.connect(self.fitClicked)
                    item.deleted = False
                if self.ctrls['plotGuess'].isChecked():
                    item2 = pg.PlotCurveItem(functions.pspFunc(guess, times), times, pen=(255, 0, 0))
                    item2.setZValue(100)
                    self.plotItems.append(item2)
                if self.ctrls['plotEvents'].isChecked():
                    item2 = pg.PlotCurveItem(eventData, times, pen=(0, 255, 0))
                    item2.setZValue(100)
                    self.plotItems.append(item2)
                #plot = self.plot.connections().keys()[0].node().getPlot()
                #plot.addItem(item)
            
        if offset > 0:
            output = output[:-offset]
            
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
        if local is self.plot:
            self.filterPlot(remote.node())
            remote.node().sigPlotChanged.connect(self.filterPlot)
        CtrlNode.connected(self, local, remote)
        
    def disconnected(self, local, remote):
        if local is self.plot:
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
        if event.type() == QtCore.QEvent.KeyPress and event.key() == QtCore.Qt.Key_Delete:
            self.deleteSelected()
            return True
        return False


        
class Histogram(CtrlNode):
    """Converts a list of values into a histogram."""
    nodeName = 'Histogram'
    uiTemplate = [
        ('numBins', 'intSpin', {'value': 100, 'min': 3, 'max': 100000})
    ]
    
    def processData(self, In):
        data = In.view(np.ndarray)
        units = None
        if isinstance(In, metaarray.MetaArray):
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
        
        self.ui = pg.CheckTable(self.funcs.keys())
        #QtCore.QObject.connect(self.ui, QtCore.SIGNAL('stateChanged'), self.update)
        self.ui.sigStateChanged.connect(self.update)
        
    def ctrlWidget(self):
        return self.ui
        
    def process(self, data, regions=None, display=True):
        keys = data.dtype.fields.keys()
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
        items = regions.items()
        for term, r in items:
            #print "  ", term, r
            if isinstance(r, dict):
                items.extend(r.items())
                continue
            try:
                mask = (data['fitTime'] > r[0]) * (data['fitTime'] < r[1])
            except:
                mask = (data['time'] > r[0]) * (data['time'] < r[1])
            dataRegions[term.node().name()] = data[mask]
        
        for row in state['rows']:  ## iterate over variables in data
            name = row[0]
            flags = row[1:]
            for i in range(len(flags)):  ## iterate over stats operations
                if flags[i]:
                    for rgnName, rgnData in dataRegions.iteritems():  ## iterate over regions
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
            keys = pt['recs'].keys()
            names = pt['recs'][keys[0]].keys()
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
        terms = regions.keys()
        names = [term.node().name() for term in terms]
        maxLen = max(map(len, names))
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
                rgn = names[m[0]]
            output[i] = tuple(events[i]) + (rgn,)
        
        return {'output': output}


class EventMasker(CtrlNode):
    """Removes events from a list which occur within masking regions (used for removing noise)
    Accepts a list of regions or a list of times (use padding to give width to each time point)"""
    nodeName = "EventMasker"
    uiTemplate = [
        #('prePadding', 'spin', {'value': 0, 'step': 1e-3, 'minStep': 1e-6, 'dec': True, 'range': [None, None], 'siPrefix': True, 'suffix': 's'}),
        #('postPadding', 'spin', {'value': 0.1, 'step': 1e-3, 'minStep': 1e-6, 'dec': True, 'range': [None, None], 'siPrefix': True, 'suffix': 's'}),
        ('prePadding', 'intSpin', {'min': 0, 'max': 1e9}),
        ('postPadding', 'intSpin', {'min': 0, 'max': 1e9}),
    ]
    
    def __init__(self, name):
        CtrlNode.__init__(self, name, terminals={
            'events': {'io': 'in'},
            'regions': {'io': 'in'},
            'output': {'io': 'out', 'bypass': 'events'}
        })
    
    def process(self, events, regions, display=True):
        #print "From masker:", events
        #events = events.copy()
        prep = self.ctrls['prePadding'].value()
        postp = self.ctrls['postPadding'].value()
        
        starts = (regions['index']-prep)[:,np.newaxis]
        stops = (regions['index']+prep)[:,np.newaxis]
        
        times = events['index'][np.newaxis, :]
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