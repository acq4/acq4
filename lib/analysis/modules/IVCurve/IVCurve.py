# -*- coding: utf-8 -*-
"""
IVCurve: acq4 analysis module that analyzes current-voltage and firing
relationships from current clamp data.

"""
from PyQt4 import QtGui, QtCore
from lib.analysis.AnalysisModule import AnalysisModule
from collections import OrderedDict
import pyqtgraph as pg
from metaarray import MetaArray
import numpy, scipy.signal
import os

import lib.analysis.tools.Utility as Utility # pbm's utilities...
import lib.analysis.tools.Fitting as Fitting # pbm's fitting stuff... 

import ctrlTemplate
import debug

class IVCurve(AnalysisModule):
    def __init__(self, host):
        AnalysisModule.__init__(self, host)
        
        self.ctrlWidget = QtGui.QWidget()
        self.ctrl = ctrlTemplate.Ui_Form()
        self.ctrl.setupUi(self.ctrlWidget)
        self.main_layout =  pg.GraphicsView()
        
        # make fixed widget for the module output
        self.widget = QtGui.QWidget()
        self.gridLayout = QtGui.QGridLayout()
        self.widget.setLayout(self.gridLayout)
        self.gridLayout.setContentsMargins(0,0,0,0)
        self.gridLayout.setSpacing(1)
        # Setup basic GUI
        self._elements_ = OrderedDict([
            ('File Loader', {'type': 'fileInput', 'size': (100, 300), 'host': self}),
            ('Parameters', {'type': 'ctrl', 'object': self.ctrlWidget, 'host': self, 'size': (100,300)}),
            ('Plots', {'type': 'ctrl', 'object': self.widget, 'pos': ('right',), 'size': (800, 600)}),
#            ('Plots', {'type': 'graphicsLayout', 'pos': ('right',), 'size': (800, 600)}),
#            ('Data Plot', {'type': 'plot', 'pos': ('right', 'File Loader'), 'size': (400, 300)}),
#            ('IV Plot', {'type': 'plot', 'pos': ('right', 'Data Plot'), 'size': (400, 300)}),
#            ('FI Plot', {'type': 'plot', 'pos': ('right', 'Parameters'), 'size': (400, 300)}),
#            ('FSL/FISI Plot', {'type': 'plot', 'pos': ('right', 'FI Plot'), 'size': (400, 300)}),
        ])
        self.initializeElements()
        # grab input form the "Ctrl" window
        self.ctrl.IVCurve_Update.clicked.connect(self.updateAnalysis)
        self.ctrl.IVCurve_PrintResults.clicked.connect(self.printAnalysis)
#        self.ctrl.IVCurve_ssTStart.valueChanged.connect(self.readParameters)
#        self.ctrl.IVCurve_ssTStop.valueChanged.connect(self.readParameters)
#        self.ctrl.IVCurve_pkTStart.valueChanged.connect(self.readParameters)
#        self.ctrl.IVCurve_pkTStop.valueChanged.connect(self.readParameters)
        self.clearResults()
        self.layout = self.getElement('Plots', create=True)
#        print dir(self.plotView)
#        mainLayout = pg.GraphicsLayout(border=pg.mkPen(0, 0, 255))
        #print dir(mainLayout)
#        self.data_plot = self.getElement('Data Plot', create=True)
 
        self.data_plot = pg.PlotWidget()
        self.gridLayout.addWidget(self.data_plot, 0, 0)# (row=0, col=0) # self.getElement('Data Plot', create=True)
        self.labelUp(self.data_plot, 'T (ms)', 'V (mV)', 'Data')
        self.IV_plot = pg.PlotWidget()
        self.gridLayout.addWidget(self.IV_plot, 0, 1) # self.getElement('IV Plot', create=True)
        self.labelUp(self.IV_plot, 'I (nA)', 'V (mV)', 'I-V')
        self.fiPlot = pg.PlotWidget()
        self.gridLayout.addWidget(self.fiPlot, 1, 0) # self.getElement('FI Plot', create=True)
        self.labelUp(self.fiPlot, 'I (nA)', 'Spikes (#)', 'F-I')
        self.fslPlot =  pg.PlotWidget()
        self.gridLayout.addWidget(self.fslPlot, 1, 1) # self.getElement('FSL/FISI Plot', create = True)
        self.labelUp(self.fslPlot, 'I (nA)', 'Fsl/Fisi (ms)', 'FSL/FISI')
#        self.IVScatterPlot_ss = pg.ScatterPlotItem(size=6, pen=pg.mkPen('w'), brush=pg.mkBrush(255, 255, 255, 255), identical=True)
#        self.IVScatterPlot_pk = pg.ScatterPlotItem(size=6, pen=pg.mkPen('r'), brush=pg.mkBrush(255, 0, 0, 255), identical=True)

        self.lrss = pg.LinearRegionItem([0, 1])
        self.lrpk = pg.LinearRegionItem([0, 1])
        self.data_plot.addItem(self.lrss)
        self.data_plot.addItem(self.lrpk)
        self.ctrl.IVCurve_ssTStart.setSuffix(' ms')
        self.ctrl.IVCurve_ssTStop.setSuffix(' ms')
        self.ctrl.IVCurve_pkTStart.setSuffix(' ms')
        self.ctrl.IVCurve_pkTStop.setSuffix(' ms')

        # Add a color scale
        # removed for now--seems to be causing crashes :(
        self.colorScale = pg.GradientLegend(self.data_plot, (20, 150), (-10, -10))
        self.data_plot.scene().addItem(self.colorScale)

        # Plots are updated when the selected region changes
        self.lrss.sigRegionChanged.connect(self.update_ssAnalysis)
        self.lrpk.sigRegionChanged.connect(self.update_pkAnalysis)

    def clearResults(self):
        """
        Make sure that all the result variables are cleared with each new file load
        """
        self.filename = ''
        self.Rin = 0.0
        self.tau = 0.0
        self.AdaptRatio = 0.0
        self.traces = None
        self.nospk = []
        self.spk=[]
        self.icmd=[]
        self.Sequence = ''
        self.ivss = []
        self.ivpk = []
        self.traces=[]
        
        
    def loadFileRequested(self, dh):
        """Called by file loader when a file load is requested."""
        if len(dh) == 0:
            raise Exception("Select an IV protocol directory.")
        if len(dh) != 1:
            raise Exception("Can only load one file at a time.")
        self.clearResults()
        dh = dh[0]
        self.data_plot.clearPlots()
        self.filename = dh.name()
        dirs = dh.subDirs()
        c = 0
        traces = []
        self.values = []
        self.Sequence = self.dataModel.listSequenceParams(dh)
        maxplotpts = 1024
        # Iterate over sequence
        for dirName in dirs:
            d = dh[dirName]
            try:
                data = self.dataModel.getClampFile(d).read()
            except:
                debug.printExc("Error loading data for protocol %s:" % d.name() )
                continue  ## If something goes wrong here, we'll just try to carry on
            cmd = self.dataModel.getClampCommand(data)
            data = self.dataModel.getClampPrimary(data)
            shdat = data.shape
            if shdat[0] > 2*maxplotpts:
                decimate_factor = int(numpy.floor(shdat[0]/maxplotpts))
                if decimate_factor < 2:
                    decimate_factor = 2
            else:
                pass
                # store primary channel data and read command amplitude
            traces.append(data)
            self.data_plot.plot(data, pen=pg.intColor(c, len(dirs), maxValue=200)) # , decimate=decimate_factor)
            self.values.append(cmd[len(cmd)/2])
            #c += 1.0 / len(dirs)
            c += 1
        self.colorScale.setIntColorScale(0, len(dirs), maxValue=200)
        self.colorScale.setLabels({'%0.2g'%self.values[0]:0, '%0.2g'%self.values[-1]:1}) 
        
        # set up the selection region correctly, prepare IV curves and find spikes
        if len(dirs) > 0:
            info = [
                {'name': 'Command', 'units': cmd.axisUnits(-1), 'values': numpy.array(self.values)},
                data.infoCopy('Time'), 
                data.infoCopy(-1)]
            self.traces = MetaArray(traces, info=info)
            cmddata = cmd.asarray()
            cmdtimes = numpy.argwhere(cmddata[1:]-cmddata[:-1] != 0)[:,0]
            self.tstart = cmd.xvals('Time')[cmdtimes[0]]
            self.tend = cmd.xvals('Time')[cmdtimes[1]]
            self.tdur = self.tend - self.tstart

            tr =  numpy.reshape(self.traces.asarray(), (len(dirs),-1))
            fsl = numpy.zeros(len(dirs))
            fisi = numpy.zeros(len(dirs))
            misi = numpy.zeros(len(dirs))
            ar = numpy.zeros(len(dirs))
            rmp = numpy.zeros(len(dirs))
            
            self.spikecount = numpy.zeros(len(dirs))
            # for adaptation ratio:
            minspk = 4
            maxspk = 10 # range of spike counts

            info1 = self.traces.infoCopy()
            sfreq = info1[2]['DAQ']['primary']['rate']
            sampInterval = 1.0/sfreq
            self.tstart += sampInterval
            self.tend += sampInterval
            tmax = cmd.xvals('Time')[-1]
            #self.lr.setRegion([end *0.5, end * 0.6])

            for i in range(len(dirs)):
                (spike, spk) = Utility.findspikes(cmd.xvals('Time'), tr[i], 
                    0, t0=self.tstart, t1=self.tend, dt=sampInterval,
                    mode = 'peak', interpolate=True)
                if len(spike) > 0:
                    self.spikecount[i] = len(spike)
                    fsl[i] = spike[0]-self.tstart
                if len(spike) > 1:
                    fisi[i] = spike[1]-spike[0]
                if len(spike) >= minspk and len(spike) <= maxspk: # for Adaptation ratio analysis
                    misi = numpy.mean(numpy.diff(spike[-3:]))
                    ar[i] = misi/fisi[i]
                (rmp[i], r2) = Utility.measure('mean', cmd.xvals('Time'), tr[i], 0.0, self.tstart)
            iAR = numpy.where(ar > 0)
            ARmean = numpy.mean(ar[iAR]) # only where we made the measurement
            self.AdaptRatio = ARmean
            self.Rmp = numpy.mean(rmp) # rmp is taken from the mean of all the baselines in the traces
            self.ctrl.IVCurve_AR.setText(u'%7.3f' % (ARmean))
            
            fisi = fisi*1.0e3
            fsl = fsl*1.0e3
            current = numpy.array(self.values)
            iscale = 1.0e12 # convert to pA
            self.nospk = numpy.where(self.spikecount == 0)
            self.spk = numpy.where(self.spikecount > 0)
            self.icmd = current[self.nospk]
            self.spcmd = current[self.spk]
            ### plot with lines and symbols:
            #self.fiScatterPlot = pg.ScatterPlotItem(size=10, pen=pg.mkPen('b'), brush=pg.mkBrush(0, 0, 255, 200), symbol='s', identical=True)
            #self.fiScatterPlot = pg.PlotDataItem(x=current*iscale, y=self.spikecount, pen='w', symbolSize=10, symbolPen='b', symbolBrush=pg.mkBrush(0, 0, 255, 200), symbol='s', identical=True)
            #self.fiScatterPlot.addPoints(x=current*iscale, y=self.spikecount )# plot the spike counts
            #self.fiPlot.plot(x=current*1e12, y = self.spikecount, clear=True)
            #self.fiPlot.setXRange(-0.5, 0.5)   
            #self.fiPlot.addItem(self.fiScatterPlot)
            self.fiPlot.plot(x=current*iscale, y=self.spikecount, clear=True, pen='w', symbolSize=10, symbolPen='b', symbolBrush=(0, 0, 255, 200), symbol='s')
            
            self.fslPlot.plot(x=self.spcmd*iscale, y=fsl[self.spk], pen='w', clear=True, symbolSize=6, symbolPen='g', symbolBrush=(0, 255, 0, 200), symbol='t')
            #self.fslScatterPlot = pg.ScatterPlotItem(size=6, pen=pg.mkPen('g'), brush=pg.mkBrush(0, 255, 0, 200), symbol = 't', identical=True)
            
            #self.fslPlot.plot(x=self.spcmd*iscale, y = fsl[self.spk], clear=True)
            self.fslPlot.plot(x=self.spcmd*iscale, y=fisi[self.spk], pen='w', symbolSize=6, symbolPen='y', symbolBrush=(255, 255, 0, 200), symbol='s')
            #self.fslScatterPlot.addPoints(x=self.spcmd*iscale, y=fsl[self.spk])# plot the spike counts            
            
            
            #self.fisiScatterPlot = pg.ScatterPlotItem(size=6, pen=pg.mkPen('y'), brush=pg.mkBrush(255, 255, 0, 200),symbol = 's', identical=True)
            #self.fisiScatterPlot.addPoints(x=self.spcmd*iscale, y=fisi[self.spk])# plot the spike counts
            
            #self.fslPlot.addItem(self.fslScatterPlot)
            #self.fslPlot.addItem(self.fisiScatterPlot)
            if len(self.spcmd) > 0:
                self.fslPlot.setXRange(0.0, numpy.max(self.spcmd*iscale))
            self.lrss.setRegion([(self.tend-(self.tdur/2.0)), self.tend]) # steady-state
            self.lrpk.setRegion([self.tstart, self.tstart+(self.tdur/5.0)]) # "peak" during hyperpolarization
            
        return True

    def updateAnalysis(self):
        self.readParameters(clearFlag = True, pw = True)
#        self.update_Tau(printWindow = True)

    def fileCellProtocol(self):
        """
        break the current filename down and return a tuple: (date, cell, protocol)
        last argument returned is the rest of the path... """
        (p0, proto) = os.path.split(self.filename)
        (p1, cell) = os.path.split(p0)
        (p2, date) = os.path.split(p1)
        return(date, cell, proto, p2)
        
    def printAnalysis(self):
        """
        Print the CCIV summary information (Cell, protocol, etc) 
        """
        (date, cell, proto, p2) = self.fileCellProtocol()
        smin = numpy.amin(self.Sequence.values())
        smax = numpy.amax(self.Sequence.values())
        sstep = numpy.mean(numpy.diff(self.Sequence.values()))
        seq = '%g;%g/%g' % (smin, smax, sstep)
        print '='*80
        print "%14s,%14s,%16s,%20s,%9s,%9s,%10s,%9s" % ("Date", "Cell", "Protocol",
            "Sequence", "RMP(mV)", " Rin(Mohm)",  "tau(ms)",  "ARatio")
        print "%14s,%14s,%16s,%20s,%8.1f,%8.1f,%8.2f,%8.3f" % (date, cell, proto,
            seq, self.Rmp*1000., self.Rin*1e-6,
            self.tau*1000., self.AdaptRatio)
        print '-'*80

    def update_Tau(self, printWindow = True):
        """ compute tau (single exponential) from the onset of the response
            using lrpk window, and only the smallest 3 steps...
        """
        rgnpk= self.lrpk.getRegion()
        Func = 'exp1' # single exponential fit.
        Fits = Fitting.Fitting()
        fitx = []
        fity = []
        initpars = [-60.0*1e-3, -5.0*1e-3, 10.0*1e-3]
        icmdneg = numpy.where(self.icmd < 0)
        maxcmd = numpy.min(self.icmd)
        ineg = numpy.where(self.icmd[icmdneg] >= maxcmd/3)
        whichdata = ineg[0]
        itaucmd = self.icmd[ineg]
        whichaxis = 0
        (fpar, xf, yf, names) = Fits.FitRegion(whichdata, whichaxis, 
                self.traces.xvals('Time'), self.traces.view(numpy.ndarray), 
                dataType = '2d', t0=rgnpk[0], t1=rgnpk[1],
                fitFunc = Func, fitPars = initpars)
        if fpar == []:
            print 'fitting failed - see log'
            return
        outstr = ""
        s = numpy.shape(fpar)
        taus = []
        for j in range(0, s[0]):
            outstr = ""
            taus.append(fpar[j][2])
            for i in range(0, len(names[j])):
                outstr = outstr + ('%s = %f, ' % (names[j][i], fpar[j][i]))
            if printWindow:
                print( "FIT(%d, %.1f pA): %s " % (whichdata[j], itaucmd[j]*1e12, outstr) )
        meantau = numpy.mean(taus)
        self.ctrl.IVCurve_Tau.setText(u'%12.2f ms' % (meantau*1.e3))
        self.tau = meantau
        if printWindow:
            print 'Mean tau: %8.1f' % (meantau*1e3)
        
    def update_ssAnalysis(self, clear=True):
        if self.traces is None:
            return
        rgnss = self.lrss.getRegion()
        self.ctrl.IVCurve_ssTStart.setValue(rgnss[0]*1.0e3)
        self.ctrl.IVCurve_ssTStop.setValue(rgnss[1]*1.0e3)
        data1 = self.traces['Time': rgnss[0]:rgnss[1]]
        self.ivss=[]
        if len(self.nospk) >= 1:
            # Steady-state IV where there are no spikes
            self.ivss = data1.mean(axis=1)[self.nospk]
            # compute Rin from the SS IV:
            if len(self.icmd) > 0 and len(self.ivss) > 0:
                self.Rin = numpy.max(numpy.diff(self.ivss)/numpy.diff(self.icmd))
                self.ctrl.IVCurve_Rin.setText(u'%9.3f M\u03A9' % (self.Rin*1.0e-6))
            else:
                self.ctrl.IVCurve_Rin.setText(u'No valid points')
        else:
            self.ivss = data1.mean(axis=1) # all traces
        self.update_IVPlot()

    def update_pkAnalysis(self, clear=False, pw = False):
        if self.traces is None:
            return
        rgnpk= self.lrpk.getRegion()
        self.ctrl.IVCurve_pkTStart.setValue(rgnpk[0]*1.0e3)
        self.ctrl.IVCurve_pkTStop.setValue(rgnpk[1]*1.0e3)
        data2 = self.traces['Time': rgnpk[0]:rgnpk[1]]
        if len(self.nospk) >= 1:
            # Peak (minimum voltage) IV where there are no spikes
            self.ivpk = data2.min(axis=1)[self.nospk]
        else:
            self.ivpk = data2.min(axis=1)
        self.update_Tau(printWindow = pw)
        self.update_IVPlot()

    def update_IVPlot(self):
        self.IV_plot.clear()
        if len(self.ivss) > 0:
            self.IV_plot.plot(self.ivss, symbolSize=6, symbolPen='w', symbolBrush='w')
            #self.IVScatterPlot_ss.setPoints(x=self.icmd, y = self.ivss)
            #self.IV_plot.addItem(self.IVScatterPlot_ss)
        if len(self.ivpk) > 0:
            self.IV_plot.plot(self.ivpk, symbolSize=6, symbolPen='w', symbolBrush='r')
            #self.IVScatterPlot_pk.setPoints(x=self.icmd, y = self.ivpk)
            #self.IV_plot.addItem(self.IVScatterPlot_pk)
        
        
    def readParameters(self, clearFlag=False, pw=False):
        """
        Read the parameter window entries, set the lr regions, and do an update on the analysis
        """
        rgnx1 = self.ctrl.IVCurve_ssTStart.value()/1.0e3
        rgnx2 = self.ctrl.IVCurve_ssTStop.value()/1.0e3
        self.lrss.setRegion([rgnx1, rgnx2])
        self.update_ssAnalysis(clear=clearFlag)

        rgnx1 = self.ctrl.IVCurve_pkTStart.value()/1.0e3
        rgnx2 = self.ctrl.IVCurve_pkTStop.value()/1.0e3
        self.lrpk.setRegion([rgnx1, rgnx2])
        self.update_pkAnalysis(clear=False, pw = pw)


#---- Helpers ---
# Some of these would normally live in a pyqtgraph-related module, but are just stuck here to get the job done.
    def labelUp(self, plot, xtext, ytext, title):
        """helper to label up the plot"""
        plot.setLabel('bottom', xtext)
        plot.setLabel('left', ytext)
        plot.setTitle(title)


