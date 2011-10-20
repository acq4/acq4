# -*- coding: utf-8 -*-
"""
IVCurve: acq4 analysis module that analyzes current-voltage and firing
relationships from current clamp data.

"""
from PyQt4 import QtGui, QtCore
from lib.analysis.AnalysisModule import AnalysisModule
from advancedTypes import OrderedDict
import pyqtgraph as pg
from metaarray import MetaArray
import numpy, scipy.signal

import lib.analysis.tools.Utility as Utility # pbm's utilities...
import lib.analysis.tools.Fitting as Fitting # pbm's fitting stuff... 

import ctrlTemplate

class IVCurve(AnalysisModule):
    def __init__(self, host):
        AnalysisModule.__init__(self, host)
        
        self.ctrlWidget = QtGui.QWidget()
        self.ctrl = ctrlTemplate.Ui_Form()
        self.ctrl.setupUi(self.ctrlWidget)
        # Setup basic GUI
        self._elements_ = OrderedDict([
            ('File Loader', {'type': 'fileInput', 'size': (100, 300), 'host': self}),
            ('Parameters', {'type': 'ctrl', 'object': self.ctrlWidget, 'host': self, 'size': (100,300)}),
            ('Data Plot', {'type': 'plot', 'pos': ('right', 'File Loader'), 'size': (400, 300)}),
            ('IV Plot', {'type': 'plot', 'pos': ('right', 'Data Plot'), 'size': (400, 300)}),
            ('FI Plot', {'type': 'plot', 'pos': ('right', 'Parameters'), 'size': (400, 300)}),
            ('FSL/FISI Plot', {'type': 'plot', 'pos': ('right', 'FI Plot'), 'size': (400, 300)}),
        ])
        self.initializeElements()
        # grab input form the "Ctrl" window
        self.ctrl.IVCurve_Update.clicked.connect(self.updateAnalysis)
#        self.ctrl.IVCurve_ssTStart.valueChanged.connect(self.readParameters)
#        self.ctrl.IVCurve_ssTStop.valueChanged.connect(self.readParameters)
#        self.ctrl.IVCurve_pkTStart.valueChanged.connect(self.readParameters)
#        self.ctrl.IVCurve_pkTStop.valueChanged.connect(self.readParameters)
        
        self.Rin = 0.0
        self.tau = 0.0
        self.traces = None
        self.nospk = []
        self.spk=[]
        self.icmd=[]
        self.data_plot = self.getElement('Data Plot', create=True)
        self.IV_plot = self.getElement('IV Plot', create=True)
        self.fiPlot = self.getElement('FI Plot', create=True)
        self.fslPlot = self.getElement('FSL/FISI Plot', create = True)
        self.IVScatterPlot_ss = pg.ScatterPlotItem(size=6, pen=pg.mkPen('w'), brush=pg.mkBrush(255, 255, 255, 255), identical=True)
        self.IVScatterPlot_pk = pg.ScatterPlotItem(size=6, pen=pg.mkPen('r'), brush=pg.mkBrush(255, 0, 0, 255), identical=True)

        self.lrss = pg.LinearRegionItem(self.data_plot, 'vertical', [0, 1])
        self.lrpk = pg.LinearRegionItem(self.data_plot, 'vertical', [0, 1])
        self.data_plot.addItem(self.lrss)
        self.data_plot.addItem(self.lrpk)
        self.ctrl.IVCurve_ssTStart.setSuffix(' ms')
        self.ctrl.IVCurve_ssTStop.setSuffix(' ms')
        self.ctrl.IVCurve_pkTStart.setSuffix(' ms')
        self.ctrl.IVCurve_pkTStop.setSuffix(' ms')

        # Add a color scale
        # removed for now--seems to be causing crashes :(
        self.colorScale = pg.ColorScaleBar(self.data_plot, (20, 150), (-10, -10))
        self.data_plot.scene().addItem(self.colorScale)

        # Plots are updated when the selected region changes
        self.lrss.sigRegionChanged.connect(self.update_ssAnalysis)
        self.lrpk.sigRegionChanged.connect(self.update_pkAnalysis)

    def loadFileRequested(self, dh):
        """Called by file loader when a file load is requested."""
        if len(dh) != 1:
            raise Exception("Can only load one file at a time.")
        dh = dh[0]
        self.data_plot.clearPlots()
        dirs = dh.subDirs()
        c = 0
        traces = []
        self.values = []
        seq = self.dataModel.listSequenceParams(dh)
        maxplotpts = 1024
        # Iterate over sequence
        for d in dirs:
            d = dh[d]
            try:
                data = self.dataModel.getClampFile(d).read()
            except:
                continue  ## If something goes wrong here, we'll just carry on

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
            self.data_plot.plot(data, pen=pg.intColor(c, len(dirs), maxValue=200), decimate=decimate_factor)
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
            cmdtimes = numpy.argwhere(cmd[1:]-cmd[:-1] != 0)
            self.tstart = cmd.xvals('Time')[cmdtimes[0]]
            self.tend = cmd.xvals('Time')[cmdtimes[1]]
            self.tdur = self.tend - self.tstart

            tr =  numpy.reshape(self.traces, (len(dirs),-1))
            fsl = numpy.zeros(len(dirs))
            fisi = numpy.zeros(len(dirs))
            misi = numpy.zeros(len(dirs))
            ar = numpy.zeros(len(dirs))
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
                spike = Utility.findspikes(cmd.xvals('Time'), tr[i], 
                    0, t0=self.tstart, t1=self.tend, dt=sampInterval,
                    mode = 'peak', interpolate=True)
                if len(spike) > 0:
                    self.spikecount[i] = len(spike)
                    fsl[i] = spike[0]-self.tstart
                if len(spike) > 1:
                    fisi[i] = spike[1]-spike[0]
                if len(spike) >= minspk: # for Adaptation ratio analysis
                    misi = numpy.mean(numpy.diff(spike[-3:]))
                    ar[i] = misi/fisi[i]
            iAR = numpy.where(ar > 0)
            ARmean = numpy.mean(ar[iAR]) # only where we made the measurement
            self.ctrl.IVCurve_AR.setText(u'%7.3f' % (ARmean))
            
            fisi = fisi*1.0e3
            fsl = fsl*1.0e3
            current = numpy.array(self.values)
            iscale = 1.0e12 # convert to pA
            self.nospk = numpy.where(self.spikecount == 0)
            self.spk = numpy.where(self.spikecount > 0)
            self.icmd = current[self.nospk]
            self.spcmd = current[self.spk]
            # plot with lines and symbols:
            self.fiScatterPlot = pg.ScatterPlotItem(size=10, pen=pg.mkPen('b'), brush=pg.mkBrush(0, 0, 255, 200), 
                style='s', identical=True)
            self.fslScatterPlot = pg.ScatterPlotItem(size=6, pen=pg.mkPen('g'), brush=pg.mkBrush(0, 255, 0, 200), 
                style = '*', identical=True)
            self.fisiScatterPlot = pg.ScatterPlotItem(size=6, pen=pg.mkPen('y'), brush=pg.mkBrush(255, 255, 0, 200),
                style = 's', identical=True)
            self.fiPlot.plot(x=current*1e12, y = self.spikecount, clear=True)
            #self.fiPlot.setXRange(-0.5, 0.5)
            self.fiScatterPlot.addPoints(x=current*iscale, y=self.spikecount )# plot the spike counts
            self.fslPlot.plot(x=self.spcmd*iscale, y = fsl[self.spk], clear=True)
            self.fslPlot.plot(x=self.spcmd*iscale, y = fisi[self.spk])
            self.fslScatterPlot.addPoints(x=self.spcmd*iscale, y=fsl[self.spk])# plot the spike counts
            self.fisiScatterPlot.addPoints(x=self.spcmd*iscale, y=fisi[self.spk])# plot the spike counts
            self.fiPlot.addItem(self.fiScatterPlot)
            self.fslPlot.addItem(self.fslScatterPlot)
            self.fslPlot.addItem(self.fisiScatterPlot)
            self.fslPlot.setXRange(0.0, numpy.max(self.spcmd*iscale))
            self.lrss.setRegion([(self.tend-(self.tdur/2.0)), self.tend]) # steady-state
            self.lrpk.setRegion([self.tstart, self.tstart+(self.tdur/5.0)]) # "peak" during hyperpolarization
            
        return True

    def updateAnalysis(self):
        self.readParameters(clearFlag = True, pw = True)
#        self.update_Tau(printWindow = True)

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
        if printWindow:
            print 'Mean tau: %8.1f' % (meantau*1e3)
        
    def update_ssAnalysis(self, clear=True):
        if self.traces is None:
            return
        rgnss = self.lrss.getRegion()
        self.ctrl.IVCurve_ssTStart.setValue(rgnss[0]*1.0e3)
        self.ctrl.IVCurve_ssTStop.setValue(rgnss[1]*1.0e3)
        data1 = self.traces['Time': rgnss[0]:rgnss[1]]
        if len(self.nospk) >= 1:
            # Steady-state IV where there are no spikes
            self.ivss = data1.mean(axis=1)[self.nospk]
            # compute Rin from the SS IV:
            if len(self.icmd) > 0 and len(self.ivss) > 0:
                self.Rin = numpy.max(numpy.diff(self.ivss)/numpy.diff(self.icmd))
                self.ctrl.IVCurve_Rin.setText(u'%9.3f M\u03A9' % (self.Rin*1.0e-6))
            else:
                self.ctrl.IVCurve_Rin.setText(u'No valid points')
            self.update_IVPlot()
        else:
            print ' no spikes found?'

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
        self.update_Tau(printWindow = pw)
        self.update_IVPlot()

    def update_IVPlot(self):
        self.IV_plot.plot(self.ivss, clear=True)
        self.IVScatterPlot_ss.setPoints(x=self.icmd, y = self.ivss)
        self.IV_plot.addItem(self.IVScatterPlot_ss)
        self.IV_plot.plot(self.ivpk, clear=False)
        self.IVScatterPlot_pk.setPoints(x=self.icmd, y = self.ivpk)
        self.IV_plot.addItem(self.IVScatterPlot_pk)
        
        
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
        
#-----------------------------
# the rest of this file has the code originally from PyDatac3 for CCIV analysis
#

#     def IVFitting(self, Func='exp1'):
#         Func = str(self.ui.Fit_comboBox.currentText())
#         (xm, ym, pl) = MP.getCoordinates(last = 1) # use last clicked plot
#         if xm == None or xm[0] == xm[1]:
#             # print xm
#             print 'PyDatac: No times Window set for fit'
#             return
#         t0 = min(xm)
#         t1 = max(xm)
#         fitx = []
#         fity = []
#         initpars = self.getFitPars() # read fitting parameters from the gui
#         for cu in pl.itemList():
#             if isinstance(cu, Qwt.QwtPlotCurve) and cu.selected and cu.dataID != None:
#                 fitx.append(cu.dataX)
#                 fity.append(cu.dataY)
#         whichdata = [1]
#         whichaxis = 0
#         if len(whichdata) > 0:
#             (fpar, xf, yf, names) = Fits.FitRegion(whichdata, whichaxis, fitx, fity, t0=t0, t1=t1,
#                                             FitPlot = pl, FitFunc = Func, FitPars = initpars,
#                                             plotInstance = MP)
#             outstr = ""
#             s = shape(fpar)
#             for j in range(0, s[0]):
#                 outstr = ""
#                 for i in range(0, len(names[j])):
#                     outstr = outstr + ('%s = %f, ' % (names[j][i], fpar[j][i]))
#             self.Status( "FIT(%d): %s" % (j, outstr) )
#         for i in range(0, len(names[0])):
#             val = 'self.ui.Fit_Result_%d' % (i)
#             eval('%s.setText(\'%f\')' % (val, fpar[0][i]))
# 
#     def ClearFits(self):
#         (xm, ym, pl) = MP.getCoordinates(last = 1) # use the last window clicked...
#         for cu in pl.itemList():
#             if isinstance(cu, Qwt.QwtPlotCurve) and cu.dataID == None:
#                 cu.detach()
#         pl.replot()
# 
#     def selectedTraces(self, records = None):
#         """ find the list of selected traces on the display and reconcile it with
#         the list in self.dat. Returns a list with the selections
#         """
#         if records is None:
#             seltr = MP.getSelectedTraces(self.ui.Main_Plot_Top) # linear list from displayed data
#         selected = []
#         available = []
#         st = 0
#         for i in range(0, len(self.dat)):
#             if records is not None:
#                 seltr = range(0, shape(self.dat[i])[0]) # selection is "all"
#             nrec = range(st, shape(self.dat[i])[0]+st)
#             sel=sorted(set.intersection(set(seltr), set(nrec)))
#             selected.append([x-st for x in sel])
#             st = st + len(nrec)
#         return(selected)
# 
#     def CCIVAnalysis(self, Record = None):
#         """ Perform analysis of IV plots in current clamp. Includes peak and mean
#         current-voltage relationships, spike counts with current level,
#         interspike interval versus time, and possibly first spike latency
#         and numeric calcuation of input resistance and time constant
#         This is a reduced version of the analysis in MATLAB datac program.
#         """
#         # 1. read all the GUI controls that we need
#         if not self.grabData(record = Record):
#             return
#         select = self.selectedTraces(records = Record)
#         spike_thresh = self.ui.CCIV_SpikeThreshold.value()
#         (vaxis, iaxis, leftlabel, botlabel, leftunits, botunits) = self.getAxes(self.dmode[0])
#         self.tabPages.setTab(self.ui.GraphTabs, 'IV')
#         tdel = self.ui.CCIV_Delay.value()
#         predel = self.ui.CCIV_preDelay.value()
#         tdur = self.ui.CCIV_Duration.value()
#         vpreFlag = self.ui.CCIV_PreVFlag.isChecked()
#         minISI = self.ui.CCIV_minISI.value()
#         # 2. prepare plots
#         MP.PlotReset(self.PlotGroup, self.ui.CCIV_Plot_V, xlabel = 'T', unitsX='ms',
#                          ylabel = 'V', unitsY='mV', textName='CCIV V',
#                          yExtent = '-10000.0', yMinorTicks=0)
#         MP.PlotReset(self.PlotGroup, self.ui.CCIV_Plot_I, xlabel = 'T', unitsX='ms',
#                           ylabel = 'I', unitsY='pA', textName='CCIV I',
#                           yExtent = '-10000.0', yMinorTicks=0)
#         MP.PlotReset(self.PlotGroup, self.ui.CCIV_Plot_IV, xlabel = 'I', unitsX='pA',
#                         ylabel = 'V', unitsY='mV', textName='CCIV IV',
#                         yExtent = '-10000.0', yMinorTicks=0)
#         MP.PlotReset(self.PlotGroup, self.ui.CCIV_Plot_FI, xlabel='I', unitsX='pA',
#                          ylabel='Spike Count', unitsY='N', textName='CCIV Spikes',
#                          yExtent = '-10000.0', yMinorTicks=0)
#         if vpreFlag:
#             MP.PlotReset(self.PlotGroup, self.ui.CCIV_Plot_Latency, xlabel='V', unitsX= 'mV',
#                      ylabel='Latency', unitsY= 'ms', textName='CCIV FSL FISI',
#                      yExtent = '-10000.0', yMinorTicks=0)
#         else:
#             MP.PlotReset(self.PlotGroup, self.ui.CCIV_Plot_Latency, xlabel='I', unitsX= 'pA',
#                      ylabel='Latency', unitsY= 'ms', textName='CCIV FSL FISI',
#                      yExtent = '-10000.0', yMinorTicks=0)
# 
#         MP.PlotReset(self.PlotGroup, self.ui.CCIV_Plot_ISI, xlabel='S(i) Lat', unitsX= 'ms',
#                          ylabel='S(i+1)', unitsY= 'ms', textName='CCIV ISI',
#                          yExtent = '-10000.0', yMinorTicks=0)
# 
#         # 3. make the measurements
#         self.vmin = Utils.measureTrace(self.tdat, self.dat, t0=tdel + predel,
#                     t1=tdel+predel+0.5*tdur, thisaxis=vaxis, mode='min', selection = select) # min voltage at start of trace
#         if predel > 0:
#             self.vpre = Utils.measureTrace(self.tdat, self.dat, t0=tdel + predel*0.8,
#                         t1=tdel+predel, thisaxis=vaxis, mode='mean', selection = select)
#             self.ipre = Utils.measureTrace(self.tdat, self.dat, t0=tdel+ predel*0.8,
#                         t1=tdel+predel, thisaxis=iaxis, mode='mean', selection = select)
#         else:
#             self.vpre = numpy.array([])
#         self.im = Utils.measureTrace(self.tdat, self.dat, t0=tdel + predel,
#                     t1=tdel+predel+tdur, thisaxis=iaxis, mode='mean', selection = select) # mean current
#         self.vss = Utils.measureTrace(self.tdat, self.dat, t0= tdel + predel + 0.5*tdur,
#                     t1=tdel+predel+tdur, thisaxis=vaxis, mode='mean', selection = select) # mean voltage at end of trace
#         u = numpy.where(numpy.array(self.im) < 0)[0].tolist() # only for currents < 0 and half of max negative current
#         whichdata = [x for x in u if self.im[x] > 0.5*min(self.im)] # ok, figure that out.
#         #
#         # exp fit to hyperpolarizing steps, single exp. fpar[0] is the DC, 2 is the ampltiude, 3 is the tau
#         (fpar, xf, yf, yn) = Fits.FitRegion(whichdata, vaxis, self.tdat, self.dat,
#                     t0=tdel+predel, t1=tdel + predel + 0.5*tdur, fitFunc = 'exp1',
#                     fitPlot = None, plotInstance = None,
#                     dataType = 'blocks') # we plot the fit later, so fitplot is none
#         # 3B: Get spike times
#         self.SpikesDetect('IV', tdel + predel, tdel + predel + tdur, spike_thresh,
#                           i_thresh = 100, plotTarget = self.ui.CCIV_Plot_V,
#                           Record = None, refractory=minISI)
#         # 3C: isi versus time (useful to gauge cell type)
#         # and get spike latency vs prepulse level
#         self.fsl = numpy.array([])
#         self.fisi = numpy.array([])
#         if len(self.vpre) > 0:
#             if vpreFlag:
#                 xd = self.vpre
#             else:
#                 xd = self.ipre
#             for block in self.allspikes: # each block is a tuple
#                 if len(block[0]) == 0:
#                     continue
#                 spdata = block[0] # spike data for v is in element 0 of the tuple
#                 for spr in spdata.keys(): # each record is a key in spike data
#                     spt = spdata[spr] # spike times are held in a numpy array as the value of the dict element
#                     if len(spt) > 0:
#                         self.fsl = numpy.append(self.fsl, spt[0]-(tdel+predel))
#                     if len(block[spl]) > 1:
#                         self.fisi = numpy.append(self.fisi, spt[1]-spt[0])
#         else:
#             xd = self.im[select]        # calculate an adaptation ratio: mean isi of last 2 spikes divided by first isi
#         # for traces with 4-8 spikes (averaged)
#         adapt_ratio = numpy.array([])
#         for spdata in self.allspikes:
# #            spdata = block[0]
#             for spr in spdata.keys():
#                 spt = spdata[spr]
#                 if len(spt) < 4 :
#                     continue    # need at least 4 spikes
#                 isis = numpy.diff(spt)
#                 ssisi = numpy.mean(isis[-2:-1]) # get "steady state" isi, in msec from last 2 isis
#                 if ssisi >= 20.0 and ssisi <= 100.0: # only get adaptation in finite firing range of 10 to 50 Hz
#                     adapt_ratio = numpy.append(adapt_ratio, (numpy.mean(isis[-2:-1])/isis[0]))
#         if len(adapt_ratio) > 0:
#             adapt_ratio = numpy.mean(adapt_ratio)
#         else:
#             adapt_ratio = 0.0
#         infostring = self.getBasicInfo()
#         # calculate input resistance and average of Tau and resting membrane potential
#         summary = [0.0, 0.0, 0.0]
#         summary =  numpy.mean(fpar, axis=0)
# 
#         # 4A: Plot  the raw traces
#         self.plotTraces(self.ui.CCIV_Plot_V,self.ui.CCIV_Plot_I)
#         Fits.FitPlot(xFit = xf, yFit = yf, fitFunc = 'exp1', fitPars = fpar,
#                      fitPlot = self.ui.CCIV_Plot_V, plotInstance = MP)
#         # 4B: Plot IV results
#         MP.PlotLine(self.ui.CCIV_Plot_IV, self.im, self.vmin,
#                         color = 'g', symbol='o', symbolsize = 5, dataID='CCIV_IVmin')
#         MP.PlotLine(self.ui.CCIV_Plot_IV, self.im, self.vss,
#                         color = 'k', symbol='s', symbolsize = 5, dataID='CCIV_IVss')
#         (ppar, xpf, ypf, yn) = Fits.FitRegion([1], 0, self.im, self.vmin, t0=-1000.0, t1=0,
#                             fitPlot = self.ui.CCIV_Plot_IV, fitFunc = 'poly3',
#                             plotInstance=MP, dataType = 'xy')
#         # 4C: Plot spike count
#         for vsplist in self.allspikes: # for each block selected
#             stn = []
#             for isp in vsplist.keys():
#                 stn.append(len(vsplist[isp])) # compute spike count
#             MP.PlotLine(self.ui.CCIV_Plot_FI, self.im, stn,
#                             color = 'k', symbol='o', symbolsize = 5, dataID='CCIV_FI')
#             # 4D: plot isi versus time (useful to gauge cell type)
#             sc = False
#             for spl in vsplist.keys(): # for each record
#                 if len(vsplist[spl]) > 1:
#                     if sc is False:
#                         self.next_color(init=True, ncolors=len(vsplist.keys()), startColor = spl)
#                         sc = True
#                     isis = numpy.diff(vsplist[spl]) # compute isis
#                     MP.PlotLine(self.ui.CCIV_Plot_ISI, vsplist[spl][:-1], isis,
#                             color = self.next_color(startColor = spl), symbol='o', symbolsize = 5, dataID='CCIV_ISI')
#         if vpreFlag:
#             MP.PlotLine(self.ui.CCIV_Plot_Latency, xd, self.fsl, color = 'k',
#                        symbol = 'o', symbolsize = 5, dataID = 'CCIV_FSL',
#                        linestyle = None)
#             MP.PlotLine(self.ui.CCIV_Plot_Latency, xd, self.fisi, color = 'r',
#                         symbol = 's', symbolsize = 5, dataID = 'CCIV_FISI',
#                         linestyle = None)
#         else:
#             MP.PlotLine(self.ui.CCIV_Plot_Latency, xd, self.fsl, color = 'k',
#                        symbol = 'o', symbolsize = 5, dataID = 'CCIV_FSL',
#                        linestyle = None)
#             MP.PlotLine(self.ui.CCIV_Plot_Latency, xd, self.fisi, color = 'r',
#                         symbol = 's', symbolsize = 5, dataID = 'CCIV_FISI',
#                         linestyle = None)
#         maxRin = 0.0
#         if ppar:
#             a = ppar[0]
#             Rinx = 3.0*a[0]*(self.im**2.0) + 2.0*a[1]*self.im + a[2]
#             if len(Rinx[u]) > 0:
#                 maxRin = max(Rinx[u])
#             infostring = infostring + ('Vm (avg) = %7.2f   Rin (max) = %7.2f  Tau (avg) = %7.2f\n AR: %7.2f' %
#                 (summary[0], maxRin, summary[2], adapt_ratio))
#         MP.fillTextBox(self.ui.CCIV_Text, infostring)
#         self.ui.GraphTabs.update()
#         # now save result off to data table
# #        print 'summary: ', summary
# #        print 'self.s: ', self.s
# #        print 'self.s[name]: ', self.s['Name']
#         results = {'Method': self.s['Method'], 'Name': self.s['Name'], 'Sequence': self.s['Sequence'],
#             'Rin': maxRin, 'Rmp': summary[0], 'tau1' : summary[2],
#             'adaptratio': adapt_ratio, 'protocol': self.s['Name']}
#         # the next set are all numpy arrays
#         results['IV_im'] = self.im
#         results['IV_vss'] = self.vss
#         results['IV_vmin'] = self.vmin # comes out as 3 arrays, all same length
#         results['FSL_vpre'] = self.vpre
#         results['FSL_fsl'] = self.fsl
#         results['FSL_fisi'] = self.fisi # fsl and fisi may be empty
#         # convert allspikes to a [2, n], where the first dimension holds the record number
#         # and the second index holds the spike latency. Substitue NaN's for empty arrays
#         slist = []
#         for thisblock in self.allspikes:
#             for k in thisblock.keys():
#                 npts = len(thisblock[k])
#                 if npts == 0:
#                     x = numpy.nan
#                     indx = numpy.array([int(k)])
#                 else:
#                     x = thisblock[k]
#                     indx = numpy.array([int(k)]*npts)
#                 slist.append([indx, x])
#         slist = Utils.flatten(slist)
#         sl = numpy.vstack([numpy.hstack(slist[0::2]), numpy.hstack(slist[1::2])])
#         results['Spikes'] = sl
#         self.results = results
#         return(results)
# 
#     def CCIVPrintResults(self):
#         """
#         Print the CCIV summary information (Cell, protocol, etc 
#         """
#         (date, cell, proto, p2) = self.fileCellProtocol()
#         print '='*80
#         print "Date\tCell\tMethod\tName\tSequence\tRMP(mV) \tRin(Mohm)\t  tau (ms)\t ARatio"
#         print "%s\t%s\t%s\t%s\t%s\t%7.1f\t%7.1f\t%7.2f\t%7.3f" % (date, cell, self.results['Method'],
#             self.results['Name'], self.results['Sequence'], self.results['Rmp'], self.results['Rin']*1000.0,
#             self.results['tau1'], self.results['adaptratio'])
#         print '-'*80
        