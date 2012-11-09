# -*- coding: utf-8 -*-
"""
IVCurve: Analysis module that analyzes current-voltage and firing
relationships from current clamp data.
This is part of Acq4

PBManis 2011-2012.

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
        self.lrss_flag = True # show is default
        self.lrpk_flag = True
        self.lrtau_flag = True
        self.regionsExist = False
        
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
        ])
        self.initializeElements()
        # grab input form the "Ctrl" window
        self.ctrl.IVCurve_Update.clicked.connect(self.updateAnalysis)
        self.ctrl.IVCurve_PrintResults.clicked.connect(self.printAnalysis)
        self.clearResults()
        self.layout = self.getElement('Plots', create=True)
 
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

        # Add a color scale
        self.colorScale = pg.GradientLegend((20, 150), (-10, -10))
        self.data_plot.scene().addItem(self.colorScale)




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
        self.fsl=[]
        self.fisi=[]
        self.ar=[]


    def initialize_Regions(self):
        """
        Here we create the analysis regions in the plot. However, this should
        NOT happen until the plot has been created
        """
        if not self.regionsExist:
            self.lrss = pg.LinearRegionItem([0, 1], brush=pg.mkBrush(0, 255, 0, 50.))
            self.lrpk = pg.LinearRegionItem([0, 1], brush=pg.mkBrush(0, 0, 255, 50.))
            self.lrtau = pg.LinearRegionItem([0, 1], brush=pg.mkBrush(255, 0, 0, 50.))
            self.data_plot.addItem(self.lrss)
            self.data_plot.addItem(self.lrpk)
            self.data_plot.addItem(self.lrtau)
            self.ctrl.IVCurve_showHide_lrss.clicked.connect(self.showhide_lrss)
            self.ctrl.IVCurve_showHide_lrpk.clicked.connect(self.showhide_lrpk)
            self.ctrl.IVCurve_showHide_lrtau.clicked.connect(self.showhide_lrtau)
            # Plots are updated when the selected region changes
            self.lrss.sigRegionChangeFinished.connect(self.update_ssAnalysis)
            self.lrpk.sigRegionChangeFinished.connect(self.update_pkAnalysis)
            self.lrtau.sigRegionChangeFinished.connect(self.update_Tauh)
            self.regionsExist = True

        self.showhide_lrpk(True)
        self.showhide_lrss(True)
        self.showhide_lrtau(False)

        self.ctrl.IVCurve_ssTStart.setSuffix(' ms')
        self.ctrl.IVCurve_ssTStop.setSuffix(' ms')
        self.ctrl.IVCurve_pkTStart.setSuffix(' ms')
        self.ctrl.IVCurve_pkTStop.setSuffix(' ms')
        #self.ctrl.IVCurve_tauTStart.setSuffix(' ms')
        #self.ctrl.IVCurve_tauTStop.setSuffix(' ms')
        self.ctrl.IVCurve_tau2TStart.setSuffix(' ms')
        self.ctrl.IVCurve_tau2TStop.setSuffix(' ms')


    def showhide_lrss(self, flagvalue):
        if flagvalue:
            self.lrss.show()
            self.ctrl.IVCurve_showHide_lrss.setCheckState(QtCore.Qt.Checked)
        else:
            self.lrss.hide()
            self.ctrl.IVCurve_showHide_lrss.setCheckState(QtCore.Qt.Unchecked)


    def showhide_lrpk(self, flagvalue):
        if flagvalue:
            self.lrpk.show()
            self.ctrl.IVCurve_showHide_lrpk.setCheckState(QtCore.Qt.Checked)
        else:
            self.lrpk.hide()
            self.ctrl.IVCurve_showHide_lrpk.setCheckState(QtCore.Qt.Unchecked)


    def showhide_lrtau(self, flagvalue):
        if flagvalue:
            self.lrtau.show()
            self.ctrl.IVCurve_showHide_lrtau.setCheckState(QtCore.Qt.Checked)
        else:
            self.lrtau.hide()
            self.ctrl.IVCurve_showHide_lrtau.setCheckState(QtCore.Qt.Unchecked)


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
        traces = None
        self.values = []
        self.Sequence = self.dataModel.listSequenceParams(dh)
        maxplotpts = 1024
        # Iterate over sequence
        for dirName in dirs:
            d = dh[dirName]
            try:
                dataF = self.dataModel.getClampFile(d)
                if dataF is None:  ## No clamp file for this iteration of the protocol (probably the protocol was stopped early)
                    print 'Missing data...'
                    c += 1
                    continue
            except:
                debug.printExc("Error loading data for protocol %s:" % d.name() )
                c += 1
                continue  ## If something goes wrong here, we'll just try to carry on
            dataF = dataF.read()
            cmd = self.dataModel.getClampCommand(dataF)
            data = self.dataModel.getClampPrimary(dataF)
            shdat = data.shape
            if shdat[0] > 2*maxplotpts:
                decimate_factor = int(numpy.floor(shdat[0]/maxplotpts))
                if decimate_factor < 2:
                    decimate_factor = 2
            else:
                pass
                # store primary channel data and read command amplitude
            if traces is None:
                traces = numpy.zeros((len(dirs), len(data)))
            traces[c,:]  = data.view(numpy.ndarray) # .append(data)
            self.data_plot.plot(data, pen=pg.intColor(c, len(dirs), maxValue=200)) # , decimate=decimate_factor)
            self.values.append(cmd[len(cmd)/2])
            c += 1
        print 'Done loading files'
        if traces is None or len(traces) == 0:
            print "No data found in this run..."
            return False
        self.colorScale.setIntColorScale(0, c, maxValue=200)
       # self.colorScale.setLabels({'%0.2g'%self.values[0]:0, '%0.2g'%self.values[-1]:1}) 
        
        # set up the selection region correctly, prepare IV curves and find spikes
        info = [
            {'name': 'Command', 'units': cmd.axisUnits(-1), 'values': numpy.array(self.values)},
            data.infoCopy('Time'), 
            data.infoCopy(-1)]
        self.traces = MetaArray(traces, info=info)
        info1 = dataF.infoCopy()
        sfreq = self.dataModel.getSampleRate(data)
        cmddata = cmd.view(numpy.ndarray)
        cmdtimes = numpy.argwhere(cmddata[1:]-cmddata[:-1] != 0)[:,0]
        self.tstart = cmd.xvals('Time')[cmdtimes[0]]
        self.tend = cmd.xvals('Time')[cmdtimes[1]]
        self.tdur = self.tend - self.tstart
        tr = traces
        
        self.spikecount = numpy.zeros(len(traces))
        # for adaptation ratio:
        minspk = 4
        maxspk = 10 # range of spike counts
        sampInterval = 1.0/sfreq
        self.tstart += sampInterval
        self.tend += sampInterval
        tmax = cmd.xvals('Time')[-1]
        tx = cmd.xvals('Time').view(numpy.ndarray)
        threshold = self.ctrl.IVCurve_SpikeThreshold.value() * 0.001

        fsl = numpy.zeros(len(dirs))
        fisi = numpy.zeros(len(dirs))
        ar = numpy.zeros(len(dirs))
        rmp = numpy.zeros(len(dirs))
        for i in range(len(dirs)):
            (spike, spk) = Utility.findspikes(tx, tr[i], 
                threshold, t0=self.tstart, t1=self.tend, dt=sampInterval,
                mode = 'schmitt', interpolate=False, debug=False)
            if len(spike) == 0:
                continue
            self.spikecount[i] = len(spike)
            fsl[i] = spike[0]-self.tstart
            if len(spike) > 1:
                fisi[i] = spike[1]-spike[0]
            if len(spike) >= minspk and len(spike) <= maxspk: # for Adaptation ratio analysis
                misi = numpy.mean(numpy.diff(spike[-3:]))
                ar[i] = misi/fisi[i]
            (rmp[i], r2) = Utility.measure('mean', tx, tr[i], 0.0, self.tstart)
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
        self.fiPlot.plot(x=current*iscale, y=self.spikecount, clear=True, pen='w', symbolSize=10, symbolPen='b', symbolBrush=(0, 0, 255, 200), symbol='s')
        self.fslPlot.plot(x=self.spcmd*iscale, y=fsl[self.spk], pen='w', clear=True, symbolSize=6, symbolPen='g', symbolBrush=(0, 255, 0, 200), symbol='t')
        self.fslPlot.plot(x=self.spcmd*iscale, y=fisi[self.spk], pen='w', symbolSize=6, symbolPen='y', symbolBrush=(255, 255, 0, 200), symbol='s')
        if len(self.spcmd) > 0:
            self.fslPlot.setXRange(0.0, numpy.max(self.spcmd*iscale))
        self.initialize_Regions() # now create the analysis regions
        self.lrss.setRegion([(self.tend-(self.tdur/2.0)), self.tend]) # steady-state
        self.lrpk.setRegion([self.tstart, self.tstart+(self.tdur/5.0)]) # "peak" during hyperpolarization
        self.lrtau.setRegion([self.tstart+0.005, self.tend])
        
        return True


    def updateAnalysis(self):
        self.readParameters(clearFlag = True, pw = True)


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
        print "%14s,%14s,%16s,%20s,%9s,%9s,%10s,%9s,%10s" % ("Date", "Cell", "Protocol",
            "Sequence", "RMP(mV)", " Rin(Mohm)",  "tau(ms)",  "ARatio", "tau2(ms)")
        print "%14s,%14s,%16s,%20s,%8.1f,%8.1f,%8.2f,%8.3f,%8.2f" % (date, cell, proto,
            seq, self.Rmp*1000., self.Rin*1e-6,
            self.tau*1000., self.AdaptRatio, self.tau2*1000)
        print '-'*80


    def update_Tau(self, printWindow = True, whichTau = 1):
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
            print 'tau fitting failed - see log'
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
        self.ctrl.IVCurve_Tau.setText(u'%18.1f ms' % (meantau*1.e3))
        self.tau = meantau
        tautext = 'Mean Tau: %8.1f'
            
        if printWindow:
            print tautext % (meantau*1e3)


    def update_Tauh(self, printWindow = True):
        """ compute tau (single exponential) from the onset of the markers
            using lrtau window, and only for the step closest to the selected
            current level. 
            Also compute the ratio of the sag from the peak (marker1) to the
            end of the trace (marker 2). 
            Based on Fujino and Oertel, J. Neuroscience 2001 to identify
            cells based on different Ih kinetics and magnitude.
        """
        bovera = 0.0
        rgnpk = self.lrtau.getRegion()
        Func = 'exp1' # single exponential fit to the whole region
        Fits = Fitting.Fitting()
        fitx = []
        fity = []
        initpars = [-80.0*1e-3, -10.0*1e-3, 50.0*1e-3]
        # find the current level that is closest to the target current
        itarget = self.ctrl.IVCurve_Ih_current.value()
        idiff = numpy.abs(numpy.array(self.icmd) - itarget*1e-9)
        # print self.icmd
        # print itarget
        # print idiff
        amin = numpy.argmin(idiff)
#        print 'amin: ', amin
        vrmp = numpy.mean(self.traces[amin][0:10])*1000. # rmp approximation.
        dpk = self.traces['Time' : rgnpk[0]:rgnpk[0]+0.001]
        vpk = numpy.mean(dpk[amin])*1000.
        dss = self.traces['Time' : rgnpk[1]-0.010:rgnpk[1]]
        vss = numpy.mean(dss[amin])*1000.
        # print 'icmd: ', self.icmd[amin]
        # print 'rmp: %.1f  vpk: %.1f  vss: %.1f' % (vrmp, vpk, vss)
        whichdata = [int(amin)]
        itaucmd = [self.icmd[amin]]
        whichaxis = 0
        (fpar, xf, yf, names) = Fits.FitRegion(whichdata, whichaxis, 
                self.traces.xvals('Time'), self.traces.view(numpy.ndarray), 
                dataType = '2d', t0=rgnpk[0], t1=rgnpk[1],
                fitFunc = Func, fitPars = initpars)
        if fpar == []:
            print 'tau_h fitting failed - see log'
            return
        outstr = ""
        s = numpy.shape(fpar)
        taus = []
        for j in range(0, s[0]):
            outstr = ""
            taus.append(fpar[j][2])
            for i in range(0, len(names[j])):
                outstr = outstr + ('%s = %f, ' % (names[j][i], fpar[j][i]*1000.))
            if printWindow:
                print( "Ih FIT(%d, %.1f pA): %s " % (whichdata[j], itaucmd[j]*1e12, outstr) )
        meantau = numpy.mean(taus)
        self.ctrl.IVCurve_Tauh.setText(u'%8.1f ms' % (meantau*1.e3))
        self.tau2 = meantau
        tautext = 'Mean Tauh: %8.1f'
        bovera = (vss-vrmp)/(vpk-vrmp)
        self.ctrl.IVCurve_Ih_ba.setText('%8.1f' % (bovera*100.))
        if bovera < 0.55 and self.tau2 < 0.015: #
            self.ctrl.IVCurve_FOType.setText('D Stellate')
        else:
            self.ctrl.IVCurve_FOType.setText('T Stellate')
            
      #  if printWindow:
      #      print tautext % (meantau*1e3)

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
                self.ctrl.IVCurve_Rin.setText(u'%9.1f M\u03A9' % (self.Rin*1.0e-6))
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
        if len(self.ivpk) > 0:
            self.IV_plot.plot(self.ivpk, symbolSize=6, symbolPen='w', symbolBrush='r')


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

