# -*- coding: utf-8 -*-
"""
IVCurve: Analysis module that analyzes current-voltage and firing
relationships from current clamp data.
This is part of Acq4

Paul B. Manis, Ph.D.
2011-2013.

Pep8 compliant (via pep8.py) 10/25/2013

"""

from PyQt4 import QtGui, QtCore
from acq4.analysis.AnalysisModule import AnalysisModule
from collections import OrderedDict
import acq4.pyqtgraph as pg
from acq4.util.metaarray import MetaArray
import numpy
import scipy.signal
import os
import re
import os.path
import itertools
import matplotlib as MP
from matplotlib.ticker import FormatStrFormatter

MP.use('TKAgg')
# Do not modify the following code
# sets up matplotlib with sans-serif plotting...
import matplotlib.gridspec as GS

stdFont = 'Arial'

import matplotlib.pyplot as pylab
import matplotlib.gridspec as gridspec

pylab.rcParams['text.usetex'] = True
pylab.rcParams['interactive'] = False
pylab.rcParams['font.family'] = 'sans-serif'
pylab.rcParams['font.sans-serif'] = 'Arial'
pylab.rcParams['mathtext.default'] = 'sf'
pylab.rcParams['figure.facecolor'] = 'white'
# next setting allows pdf font to be readable in Adobe Illustrator
pylab.rcParams['pdf.fonttype'] = 42
pylab.rcParams['text.dvipnghack'] = True
# to here (matplotlib stuff - touchy!)

import acq4.analysis.tools.Utility as Utility   # pbm's utilities...
import acq4.analysis.tools.Fitting as Fitting   # pbm's fitting stuff...
import ctrlTemplate
import acq4.util.debug as debug


class IVCurve(AnalysisModule):
    """
    IVCurve is an Analysis Module for Acq4.

    IVCurve performs analyses of current-voltage relationships in
    electrophysiology experiments. The module is interactive, and is primarily
    designed to examine data collected in current clamp. Results analyzed
    include:
    Resting potential (average RMP through the episodes in the protocol).
    Input resistance (maximum slope if IV relationship below Vrest)
    Cell time constant (single exponential fit)
    Ih Sag amplitude and tau
    Spike rate as a function of injected current
    Interspike interval as a function of time for each current level
    RMP as a function of time through the protocol

    """
    def __init__(self, host):
        AnalysisModule.__init__(self, host)
        self.ctrlWidget = QtGui.QWidget()
        self.ctrl = ctrlTemplate.Ui_Form()
        self.ctrl.setupUi(self.ctrlWidget)
        self.loaded = None
        self.main_layout = pg.GraphicsView()   # instead of GraphicsScene?
        self.dirsSet = None
        self.lrss_flag = True   # show is default
        self.lrpk_flag = True
        self.rmp_flag = True
        self.lrtau_flag = False
        self.regionsExist = False
        self.fit_curve = None
        self.fitted_data = None
        self.keepAnalysisCount = 0
        self.colors = ['w', 'g', 'b', 'r', 'y', 'c']
        self.symbols = ['o', 's', 't', 'd', '+']
        self.colorList = itertools.cycle(self.colors)
        self.symbolList = itertools.cycle(self.symbols)
        self.dataMode = 'IC'  # analysis depends on the type of data we have.
        self.ICModes = ['IC', 'CC', 'IClamp']  # list of CC modes
        self.VCModes = ['VC', 'VClamp']  # list of VC modes
         # make fixed widget for the module output
        self.widget = QtGui.QWidget()
        self.gridLayout = QtGui.QGridLayout()
        self.widget.setLayout(self.gridLayout)
        self.gridLayout.setContentsMargins(4, 4, 4, 4)
        self.gridLayout.setSpacing(1)
         # Setup basic GUI
        self._elements_ = OrderedDict([
            ('File Loader',
             {'type': 'fileInput', 'size': (100, 300), 'host': self}),
            ('Parameters',
             {'type': 'ctrl', 'object': self.ctrlWidget, 'host': self,
              'size': (100, 300)}),
            ('Plots',
             {'type': 'ctrl', 'object': self.widget, 'pos': ('right',),
              'size': (800, 600)}),
        ])
        self.initializeElements()
        self.fileLoaderInstance = self.getElement('File Loader', create=True)
         # grab input form the "Ctrl" window
        self.ctrl.IVCurve_Update.clicked.connect(self.updateAnalysis)
        self.ctrl.IVCurve_PrintResults.clicked.connect(self.printAnalysis)
        self.ctrl.IVCurve_MPLExport.clicked.connect(self.matplotlibExport)
        self.ctrl.IVCurve_KeepAnalysis.clicked.connect(self.resetKeepAnalysis)
        self.ctrl.IVCurve_getFileInfo.clicked.connect(self.getFileInfo)
        [self.ctrl.IVCurve_RMPMode.currentIndexChanged.connect(x)
         for x in [self.update_rmpAnalysis, self.countSpikes]]
        self.ctrl.dbStoreBtn.clicked.connect(self.dbStoreClicked)
        self.clearResults()
        self.layout = self.getElement('Plots', create=True)

         # instantiate the graphs using a gridLayout
        self.data_plot = pg.PlotWidget()
        self.gridLayout.addWidget(self.data_plot, 0, 0, 3, 1)
        self.labelUp(self.data_plot, 'T (s)', 'V (V)', 'Data')

        self.cmd_plot = pg.PlotWidget()
        self.gridLayout.addWidget(self.cmd_plot, 3, 0, 1, 1)
        self.labelUp(self.cmd_plot, 'T (s)', 'I (A)', 'Command')

        self.RMP_plot = pg.PlotWidget()
        self.gridLayout.addWidget(self.RMP_plot, 1, 1, 1, 1)
        self.labelUp(self.RMP_plot, 'T (s)', 'V (mV)', 'RMP')

        self.fiPlot = pg.PlotWidget()
        self.gridLayout.addWidget(self.fiPlot, 2, 1, 1, 1)
        self.labelUp(self.fiPlot, 'I (pA)', 'Spikes (#)', 'F-I')

        self.fslPlot = pg.PlotWidget()
        self.gridLayout.addWidget(self.fslPlot, 3, 1, 1, 1)
        self.labelUp(self.fslPlot, 'I (pA)', 'Fsl/Fisi (ms)', 'FSL/FISI')

        self.IV_plot = pg.PlotWidget()
        self.gridLayout.addWidget(self.IV_plot, 0, 1, 1, 1)
        self.labelUp(self.IV_plot, 'I (pA)', 'V (V)', 'I-V')
        for row, s in enumerate([20, 10, 10, 10]):
            self.gridLayout.setRowStretch(row, s)

     #    self.tailPlot = pg.PlotWidget()
     #    self.gridLayout.addWidget(self.fslPlot, 3, 1, 1, 1)
     #    self.labelUp(self.tailPlot, 'V (V)', 'I (A)', 'Tail Current')

         # Add a color scale
        self.colorScale = pg.GradientLegend((20, 150), (-10, -10))
        self.data_plot.scene().addItem(self.colorScale)

    def clearResults(self):
        """
        clearResults resets variables.

        This is typically needed for each new file that is loaded.
        """
        self.filename = ''
        self.Rin = 0.0
        self.tau = 0.0
        self.AdaptRatio = 0.0
        self.traces = None
        self.tx = None
        self.nospk = []
        self.spk = []
        self.cmd = []
        self.Sequence = ''
        self.ivss = []  # steady-state IV (window 2)
        self.ivpk = []  # peak IV (window 1)
        self.traces = []
        self.fsl = []  # first spike latency
        self.fisi = []  # first isi
        self.ar = []  # adaptation ratio
        self.rmp = []  # resting membrane potential during sequence

    def resetKeepAnalysis(self):
        self.keepAnalysisCount = 0  # reset counter.

    def initialize_Regions(self):
        """
        initialize_Regions sets the linear regions on the displayed data

        Here we create the analysis regions in the plot. However, this should
        NOT happen until the plot has been created
        """
        if not self.regionsExist:
            self.lrss = pg.LinearRegionItem([0, 1],
                                            brush=pg.mkBrush(0, 255, 0, 50.))
            self.lrpk = pg.LinearRegionItem([0, 1],
                                            brush=pg.mkBrush(0, 0, 255, 50.))
            self.lrtau = pg.LinearRegionItem([0, 1],
                                             brush=pg.mkBrush(255, 0, 0, 50.))
            self.lrrmp = pg.LinearRegionItem([0, 1],
                                             brush=pg.mkBrush
                                             (255, 255, 0, 25.))
            self.lrleak = pg.LinearRegionItem([0, 1],
                                              brush=pg.mkBrush
                                              (255, 0, 255, 25.))
            self.data_plot.addItem(self.lrss)
            self.data_plot.addItem(self.lrpk)
            self.data_plot.addItem(self.lrtau)
            self.data_plot.addItem(self.lrrmp)
            self.IV_plot.addItem(self.lrleak)
            self.ctrl.IVCurve_showHide_lrss.\
                clicked.connect(self.showhide_lrss)
            self.ctrl.IVCurve_showHide_lrpk.\
                clicked.connect(self.showhide_lrpk)
            self.ctrl.IVCurve_showHide_lrtau.\
                clicked.connect(self.showhide_lrtau)
            self.ctrl.IVCurve_showHide_lrrmp.\
                clicked.connect(self.showhide_lrrmp)
            self.ctrl.IVCurve_subLeak.clicked.connect(self.showhide_leak)
             # Plots are updated when the selected region changes
            self.lrrmp.sigRegionChangeFinished.connect(self.update_rmpAnalysis)
            self.lrss.sigRegionChangeFinished.connect(self.update_ssAnalysis)
            self.lrpk.sigRegionChangeFinished.connect(self.update_pkAnalysis)
            self.lrleak.sigRegionChangeFinished.connect(self.updateAnalysis)
            self.lrtau.sigRegionChangeFinished.connect(self.update_Tauh)
            self.regionsExist = True
            self.ctrl.IVCurve_tauh_Commands.\
                currentIndexChanged.connect(self.updateAnalysis)
        self.showhide_lrrmp(True)  # always...
        self.showhide_lrtau(False)
        self.ctrl.IVCurve_ssTStart.setSuffix(' ms')
        self.ctrl.IVCurve_ssTStop.setSuffix(' ms')
        self.ctrl.IVCurve_pkTStart.setSuffix(' ms')
        self.ctrl.IVCurve_pkTStop.setSuffix(' ms')
        self.ctrl.IVCurve_tau2TStart.setSuffix(' ms')
        self.ctrl.IVCurve_tau2TStop.setSuffix(' ms')
        self.ctrl.IVCurve_LeakMin.setSuffix(' mV')
        self.ctrl.IVCurve_LeakMax.setSuffix(' mV')

     ######
     # The next set of short routines control showing and hiding of regions
     # in the plot of the raw data (traces)
     ######
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
            self.ctrl.IVCurve_showHide_lrtau.\
                setCheckState(QtCore.Qt.Unchecked)

    def showhide_lrrmp(self, flagvalue):
        if flagvalue:
            self.lrrmp.show()
            self.ctrl.IVCurve_showHide_lrrmp.setCheckState(QtCore.Qt.Checked)
        else:
            self.lrrmp.hide()
            self.ctrl.IVCurve_showHide_lrrmp.\
                setCheckState(QtCore.Qt.Unchecked)

    def showhide_leak(self, flagvalue):
        if flagvalue:
            self.lrleak.show()
            self.ctrl.IVCurve_subLeak.setCheckState(QtCore.Qt.Checked)
        else:
            self.lrleak.hide()
            self.ctrl.IVCurve_subLeak.setCheckState(QtCore.Qt.Unchecked)

    def uniq(self, inlist):
         # order preserving detection of unique values in a list
        uniques = []
        for item in inlist:
            if item not in uniques:
                uniques.append(item)
        return uniques

    def getFileInfo(self):
        """
        getFileInfo reads the sequence information from the data file

        Two-dimensional sequences are supported.

        """
        dh = self.fileLoaderInstance.selectedFiles()
        dh = dh[0]
        dirs = dh.subDirs()
         # w=None
         # ndir  = len(dirs)
         # for j, d in enumerate(dirs):
         #     z = d.split('_')
         #     if w is None:
         #         nseq = len(z)
         #         w = [[0 for x in range(ndir)] for y in range(nseq)]
         #     for i, p in enumerate(z):
         #         w[i][j]=p
         #  # w now contains the pairings, but split up
         # print 'w: ', w
         # leftseq = self.uniq(w[0])
         # leftseq.insert(0, 'None')
         # if nseq > 1:
         #     rightseq = self.uniq(w[1])
         #     rightseq.insert(0, 'None')

        self.Sequence = self.dataModel.listSequenceParams(dh)
        keys = self.Sequence.keys()
        leftseq = [str(x) for x in self.Sequence[keys[0]]]
        if len(keys) > 1:
            rightseq = [str(x) for x in self.Sequence[keys[1]]]
        else:
            rightseq = []
        leftseq.insert(0, 'All')
        rightseq.insert(0, 'All')
        self.ctrl.IVCurve_Sequence1.clear()
        self.ctrl.IVCurve_Sequence2.clear()
        self.ctrl.IVCurve_Sequence1.addItems(leftseq)
        self.ctrl.IVCurve_Sequence2.addItems(rightseq)
        self.dirsSet = dh  # not sure we need this anymore...
        self.loaded = dh  # this is critical!

    def loadFileRequested(self, dh):
        """
        loadFileRequested is called by file loader when a file is requested.

        Loads all of the successive records from the specified protocol.
        Stores ancillary information from the protocol in class variables.
        Extracts information about the commands, sometimes using a rather
        simplified set of assumptions.
        input: dh, the file handle
        modifies: plots, sequence, data arrays, data mode,
        """
        if len(dh) == 0:
            raise Exception("IVCurve::loadFileRequested: " +
                            "Select an IV protocol directory.")
        if len(dh) != 1:
            raise Exception("IVCurve::loadFileRequested: " +
                            "Can only load one file at a time.")
        self.clearResults()
        dh = dh[0]
        if self.loaded != dh:
            self.getFileInfo()  # get info frommost recent file requested
        self.loaded = dh
        self.protocol = ''
        self.data_plot.clearPlots()
        self.cmd_plot.clearPlots()
        self.filename = dh.name()
        dirs = dh.subDirs()
        tail = ''
        fn = self.filename
        self.protocol = ''
         # this is WAY too specific, but needed it to get the overall name...
         # maybe count levels back up from protocol instead?
         # make a new list of directories... subsetted if need be
        if dh != self.dirsSet:
            self.ctrl.IVCurve_Sequence1.clear()
            self.ctrl.IVCurve_Sequence2.clear()

        # day directory format, like '2013.01.01'
        # mre = re.compile('(\d{4})\.(\d{2}).(\d{2})')
        # print 'fn: ', fn
        # while fn is not '/' and re.match(mre, tail) is None:
        #     (head, tail) = os.path.split(fn)
        #     fn = head
        #     #print 'fn, tail: ', fn, tail
        #     if re.match(mre, tail) is not None:
        #         self.protocol = os.path.join(tail, self.protocol)
        (head, tail) = os.path.split(fn)
        self.protocol = tail
        subs = re.compile('[\/]')
        self.protocol = re.sub(subs, '-', self.protocol)
        self.protocol = self.protocol[:-1] + '.pdf'
        self.commonPrefix = os.path.join(fn, 'Ruili')
        traces = []
        cmd_wave = []
        self.values = []
        self.Sequence = self.dataModel.listSequenceParams(dh)
        self.traceTimes = numpy.zeros(0)
        maxplotpts = 1024
         # Iterate over sequence
        if ('Clamp1', 'Pulse_amplitude') in self.Sequence.keys():
            sequenceValues = self.Sequence[('Clamp1', 'Pulse_amplitude')]
        else:
            sequenceValues = []  # print self.Sequence.keys()
        # if sequence has repeats, build pattern

        if 'repetitions' in self.Sequence:
            reps = self.Sequence[('protocol', 'repetitions')]
            sequenceValues = [x for y in range(len(dirs))
                              for x in sequenceValues]
         # select subset of data by overriding the directory sequence...
        if self.dirsSet is not None:
            ld = [self.ctrl.IVCurve_Sequence1.currentIndex()-1]
            rd = [self.ctrl.IVCurve_Sequence2.currentIndex()-1]
            if ld[0] == -1 and rd[0] == -1:
                pass
            else:
                if ld[0] == -1:  # 'All'
                    ld = range(self.ctrl.IVCurve_Sequence1.count()-1)
                if rd[0] == -1:  # 'All'
                    rd = range(self.ctrl.IVCurve_Sequence2.count()-1)
                dirs = []
                for i in ld:
                    for j in rd:
                        dirs.append('%03d_%03d' % (i, j))

        i = 0  # sometimes, the elements are not right...
        for i, dirName in enumerate(dirs):
            d = dh[dirName]
            try:
                dataF = self.dataModel.getClampFile(d)
                # Check if no clamp file for this iteration of the protocol
                # (probably the protocol was stopped early)
                if dataF is None:
                    print ('IVCurve::loadFileRequested: ',
                           'Missing data in %s, element: %d' % (dirName, i))
                    continue
            except:
                debug.printExc("Error loading data for protocol %s:"
                               % d.name())
                continue   # If something goes wrong here, we just carry on
            dataF = dataF.read()
            cmd = self.dataModel.getClampCommand(dataF)
            data = self.dataModel.getClampPrimary(dataF)
            self.dataMode = self.dataModel.getClampMode(data)
            if self.dataMode == 'IC' or self.dataMode == 'CC':
                sf = 1.0
            else:
                sf = 1e3
            # only accept data in a particular range
            if self.ctrl.IVCurve_IVLimits.isChecked():
                cval = sf*sequenceValues[i]
                cmin = self.ctrl.IVCurve_IVLimitMin.value()
                cmax = self.ctrl.IVCurve_IVLimitMax.value()
                if cval < cmin or cval > cmax:
                    continue  # skip adding the data to the arrays
            shdat = data.shape
            if shdat[0] > 2*maxplotpts:
                decimate_factor = int(numpy.floor(shdat[0]/maxplotpts))
                if decimate_factor < 2:
                    decimate_factor = 2
            else:
                pass
             # store primary channel data and read command amplitude
            info1 = data.infoCopy()
            self.traceTimes = numpy.append(self.traceTimes,
                                        info1[1]['startTime'])
            traces.append(data.view(numpy.ndarray))
            cmd_wave.append(cmd.view(numpy.ndarray))
            self.data_plot.plot(data,
                                pen=pg.intColor(i, len(dirs), maxValue=200))
            if self.dataMode in ['IC', 'CC']:
                self.data_plot.plotItem.setLabel('left', None, None, 'mV')
            self.cmd_plot.plot(cmd,
                               pen=pg.intColor(i, len(dirs), maxValue=200))
            if len(sequenceValues) > 0:
                    self.values.append(sequenceValues[i])
            else:
                self.values.append(cmd[len(cmd)/2])
            i += 1
        print 'IVCurve::loadFileRequested: Done loading files'
        if traces is None or len(traces) == 0:
            print "IVCurve::loadFileRequested: No data found in this run..."
            return False
        # put relative to the start
        self.traceTimes = self.traceTimes - self.traceTimes[0]
        traces = numpy.vstack(traces)
        cmd_wave = numpy.vstack(cmd_wave)
        self.cmd_wave = cmd_wave
        self.colorScale.setIntColorScale(0, i, maxValue=200)
        # set up the selection region correctly and
        # prepare IV curves and find spikes
        info = [
            {'name': 'Command', 'units': cmd.axisUnits(-1),
             'values': numpy.array(self.values)},
            data.infoCopy('Time'),
            data.infoCopy(-1)]
        traces = traces[:len(self.values)]
        self.traces = MetaArray(traces, info=info)
        sfreq = self.dataModel.getSampleRate(data)
        self.dataMode = self.dataModel.getClampMode(data)
        if self.dataMode is None:
            self.dataMode = 'CC' # set a default mode
        self.ctrl.IVCurve_dataMode.setText(self.dataMode)

        if self.ctrl.IVCurve_KeepAnalysis.isChecked():
            self.keepAnalysisCount += 1
        else:
            self.keepAnalysisCount = 0  # always make sure is reset
             # this is the only way to reset iterators.
            self.colorList = itertools.cycle(self.colors)
            self.symbolList = itertools.cycle(self.symbols)
        self.makeMapSymbols()

        if self.dataMode == 'IC':
            cmdUnits = 'pA'
            scaleFactor = 1e12
            self.labelUp(self.data_plot, 'T (s)', 'V (V)', 'Data')
        else:
            cmdUnits = 'mV'
            scaleFactor = 1e3
            self.labelUp(self.data_plot, 'T (s)', 'I (A)', 'Data')
        cmddata = cmd.view(numpy.ndarray)
        cmddiff = numpy.abs(cmddata[1:] - cmddata[:-1])
        if self.dataMode in self.ICModes:
            mindiff = 1e-12
        else:
            mindiff = 1e-4
        cmdtimes1 = numpy.argwhere(cmddiff >= mindiff)[:, 0]
        cmddiff2 = cmdtimes1[1:] - cmdtimes1[:-1]
        cmdtimes2 = numpy.argwhere(cmddiff2 > 1)[:, 0]
        if len(cmdtimes1) > 0 and len(cmdtimes2) > 0:
            cmdtimes = numpy.append(cmdtimes1[0], cmddiff2[cmdtimes2])
        else:  # just fake it
            cmdtimes = numpy.array([0.01, 0.1])
        if self.ctrl.IVCurve_KeepT.isChecked() is False:
            self.tstart = cmd.xvals('Time')[cmdtimes[0]]
            self.tend = cmd.xvals('Time')[cmdtimes[1]] + self.tstart
            self.tdur = self.tend - self.tstart

         # build the list of command values that are used for the fitting
        cmdList = []
        for i in range(len(self.values)):
            cmdList.append('%8.3f %s' %
                           (scaleFactor*self.values[i], cmdUnits))
        self.ctrl.IVCurve_tauh_Commands.clear()
        self.ctrl.IVCurve_tauh_Commands.addItems(cmdList)
        self.sampInterval = 1.0/sfreq
        if self.ctrl.IVCurve_KeepT.isChecked() is False:
            self.tstart += self.sampInterval
            self.tend += self.sampInterval
        tmax = cmd.xvals('Time')[-1]
        self.tx = cmd.xvals('Time').view(numpy.ndarray)
        commands = numpy.array(self.values)

        self.initialize_Regions()  # now create the analysis regions
        if self.ctrl.IVCurve_KeepT.isChecked() is False:
            self.lrss.setRegion([(self.tend-(self.tdur/5.0)),
                                self.tend-0.001])  # steady-state
            # "peak" during hyperpolarization
            self.lrpk.setRegion([self.tstart,
                                self.tstart+(self.tdur/5.0)])
            self.lrtau.setRegion([self.tstart+(self.tdur/5.0)+0.005,
                                 self.tend])
            self.lrrmp.setRegion([1.e-4, self.tstart*0.9])  # rmp window
        self.lrleak.setRegion([self.ctrl.IVCurve_LeakMin.value(),
                              self.ctrl.IVCurve_LeakMax.value()])

        if self.dataMode in self.ICModes:
            # for adaptation ratio:
            self.updateAnalysis()
        if self.dataMode in self.VCModes:
            self.cmd = commands
            self.spikecount = numpy.zeros(len(numpy.array(self.values)))
        return True

    def updateAnalysis(self):
        """updateAnalysis re-reads the time parameters and counts the spikes"""
        self.readParameters(clearFlag=True, pw=True)
        self.countSpikes()

    def countSpikes(self):
        """
        countSpikes: Using the threshold set in the control panel, count the
        number of spikes in the stimulation window (self.tstart, self.tend)
        Updates the spike plot(s).

        The following variables are set:
        self.spikecount: a 1-D numpy array of spike counts, aligned with the
            current (command)
        self.AdaptRatio: the adaptation ratio of the spike train
        self.fsl: a numpy array of first spike latency for each command level
        self.fisi: a numpy array of first interspike intervals for each
            command level
        self.nospk: the indices of command levels where no spike was detected
        self.spk: the indices of command levels were at least one spike
            was detected
        """
        if self.keepAnalysisCount == 0:
            clearFlag = True
        else:
            clearFlag = False
        if self.dataMode not in self.ICModes or self.tx is None:
            print ('IVCurve::countSpikes: Cannot count spikes, ' +
                   'and dataMode is ', self.dataMode)
            self.spikecount = []
            self.fiPlot.plot(x=[], y=[], clear=clearFlag, pen='w',
                             symbolSize=6, symbolPen='b',
                             symbolBrush=(0, 0, 255, 200), symbol='s')
            self.fslPlot.plot(x=[], y=[], pen='w', clear=clearFlag,
                              symbolSize=6, symbolPen='g',
                              symbolBrush=(0, 255, 0, 200), symbol='t')
            self.fslPlot.plot(x=[], y=[], pen='w', symbolSize=6,
                              symbolPen='y',
                              symbolBrush=(255, 255, 0, 200), symbol='s')
            return
        minspk = 4
        maxspk = 10  # range of spike counts
        threshold = self.ctrl.IVCurve_SpikeThreshold.value() * 1e-3
        ntr = len(self.traces)
        self.spikecount = numpy.zeros(ntr)
        fsl = numpy.zeros(ntr)
        fisi = numpy.zeros(ntr)
        ar = numpy.zeros(ntr)
        rmp = numpy.zeros(ntr)
        # rmp is taken from the mean of all the baselines in the traces
        self.Rmp = numpy.mean(rmp)

        for i in range(ntr):
            (spike, spk) = Utility.findspikes(self.tx, self.traces[i],
                                              threshold, t0=self.tstart,
                                              t1=self.tend,
                                              dt=self.sampInterval,
                                              mode='schmitt',
                                              interpolate=False,
                                              debug=False)
            if len(spike) == 0:
                continue
            self.spikecount[i] = len(spike)
            fsl[i] = spike[0]-self.tstart
            if len(spike) > 1:
                fisi[i] = spike[1]-spike[0]
             # for Adaptation ratio analysis
            if len(spike) >= minspk and len(spike) <= maxspk:
                misi = numpy.mean(numpy.diff(spike[-3:]))
                ar[i] = misi/fisi[i]
            (rmp[i], r2) = Utility.measure('mean', self.tx, self.traces[i],
                                           0.0, self.tstart)
        iAR = numpy.where(ar > 0)
        ARmean = numpy.mean(ar[iAR])  # only where we made the measurement
        self.AdaptRatio = ARmean
        self.ctrl.IVCurve_AR.setText(u'%7.3f' % (ARmean))
        fisi = fisi*1.0e3
        fsl = fsl*1.0e3
        self.fsl = fsl
        self.fisi = fisi
        self.nospk = numpy.where(self.spikecount == 0)
        self.spk = numpy.where(self.spikecount > 0)
        self.update_SpikePlots()

    def fileCellProtocol(self):
        """
        fileCellProtocol breaks the current filename down and returns a
        tuple: (date, cell, protocol)

        last argument returned is the rest of the path...
        """
        (p0, proto) = os.path.split(self.filename)
        (p1, cell) = os.path.split(p0)
        (p2, date) = os.path.split(p1)
        return(date, cell, proto, p2)

    def printAnalysis(self):
        """
        Print the CCIV summary information (Cell, protocol, etc)
        Printing goes to the terminal, where the data can be copied
        to another program like a spreadsheet.
        """
        (date, cell, proto, p2) = self.fileCellProtocol()
        smin = numpy.amin(self.Sequence.values())
        smax = numpy.amax(self.Sequence.values())
        sstep = numpy.mean(numpy.diff(self.Sequence.values()))
        seq = '%g;%g/%g' % (smin, smax, sstep)
        print '='*80
        print ("%14s,%14s,%16s,%20s,%9s,%9s,%10s,%9s,%10s" %
               ("Date", "Cell", "Protocol",
                "Sequence", "RMP(mV)", " Rin(Mohm)",  "tau(ms)",
                "ARatio", "tau2(ms)"))
        print ("%14s,%14s,%16s,%20s,%8.1f,%8.1f,%8.2f,%8.3f,%8.2f" %
               (date, cell, proto, seq, self.Rmp*1000., self.Rin*1e-6,
                self.tau*1000., self.AdaptRatio, self.tau2*1000))
        print '-'*80

    def update_Tau(self, printWindow=True, whichTau=1):
        """
        Compute time constant (single exponential) from the
        onset of the response
        using lrpk window, and only the smallest 3 steps...
        """
        if self.cmd == []:  # probably not ready yet to do the update.
            return
        if self.dataMode == 'VC':  # don't try this in voltage clamp mode
            return
        rgnpk = self.lrpk.getRegion()
        Func = 'exp1'  # single exponential fit.
        Fits = Fitting.Fitting()
        initpars = [-60.0*1e-3, -5.0*1e-3, 10.0*1e-3]
        icmdneg = numpy.where(self.cmd < 0)
        maxcmd = numpy.min(self.cmd)
        ineg = numpy.where(self.cmd[icmdneg] >= maxcmd/3)
        whichdata = ineg[0]
        itaucmd = self.cmd[ineg]
        whichaxis = 0

        (fpar, xf, yf, names) = Fits.FitRegion(whichdata, whichaxis,
                                               self.traces.xvals('Time'),
                                               self.traces.view(numpy.ndarray),
                                               dataType='xy',
                                               t0=rgnpk[0], t1=rgnpk[1],
                                               fitFunc=Func,
                                               fitPars=initpars)
        if fpar == []:
            print 'IVCurve::update_Tau: Charging tau fitting failed - see log'
            return
        # outstr = ""
        s = numpy.shape(fpar)
        taus = []
        for j in range(0, s[0]):
            outstr = ""
            taus.append(fpar[j][2])
            for i in range(0, len(names[j])):
                outstr = outstr + ('%s = %f, ' % (names[j][i], fpar[j][i]))
            if printWindow:
                print("FIT(%d, %.1f pA): %s " %
                      (whichdata[j], itaucmd[j]*1e12, outstr))
        meantau = numpy.mean(taus)
        self.ctrl.IVCurve_Tau.setText(u'%18.1f ms' % (meantau*1.e3))
        self.tau = meantau
        tautext = 'Mean Tau: %8.1f'
        if printWindow:
            print tautext % (meantau*1e3)

    def update_Tauh(self, printWindow=False):
        """ compute tau (single exponential) from the onset of the markers
            using lrtau window, and only for the step closest to the selected
            current level in the GUI window.

            Also compute the ratio of the sag from the peak (marker1) to the
            end of the trace (marker 2).
            Based on analysis in Fujino and Oertel, J. Neuroscience 2001,
            to type cells based on different Ih kinetics and magnitude.
        """
        if self.ctrl.IVCurve_showHide_lrtau.isChecked() is not True:
            return
        bovera = 0.0
        rgn = self.lrtau.getRegion()
        Func = 'exp1'  # single exponential fit to the whole region
        Fits = Fitting.Fitting()
        fitx = []
        fity = []
        initpars = [-80.0*1e-3, -10.0*1e-3, 50.0*1e-3]

         # find the current level that is closest to the target current
        s_target = self.ctrl.IVCurve_tauh_Commands.currentIndex()
        itarget = self.values[s_target]  # retrive actual value from commands
        self.neg_cmd = itarget
        idiff = numpy.abs(numpy.array(self.cmd) - itarget)
        amin = numpy.argmin(idiff)   # amin appears to be the same as s_target
         # target trace (as selected in cmd drop-down list):
        target = self.traces[amin]
         # get Vrmp -  # rmp approximation.
        vrmp = numpy.median(target['Time': 0.0:self.tstart-0.005])*1000.
        self.ctrl.IVCurve_vrmp.setText('%8.2f' % (vrmp))
        self.neg_vrmp = vrmp
         # get peak and steady-state voltages
        pkRgn = self.lrpk.getRegion()
        ssRgn = self.lrss.getRegion()
        vpk = target['Time': pkRgn[0]:pkRgn[1]].min() * 1000
         #vpk = numpy.mean(dpk[amin])*1000.
        self.neg_pk = (vpk-vrmp) / 1000.
         #dss = self.traces['Time' : rgn[1]-0.010:rgn[1]]
         #vss = numpy.mean(dss[amin])*1000.
        vss = numpy.median(target['Time': ssRgn[0]:ssRgn[1]]) * 1000
        self.neg_ss = (vss-vrmp) / 1000.
        whichdata = [int(amin)]
        itaucmd = [self.cmd[amin]]
        rgnss = self.lrss.getRegion()
        self.ctrl.IVCurve_tau2TStart.setValue(rgn[0]*1.0e3)
        self.ctrl.IVCurve_tau2TStop.setValue(rgn[1]*1.0e3)
        fd = self.traces['Time': rgn[0]:rgn[1]][whichdata][0]
        if self.fitted_data is None:  # first time through..
            self.fitted_data = self.data_plot.plot(fd, pen=pg.mkPen('w'))
        else:
            self.fitted_data.clear()
            self.fitted_data = self.data_plot.plot(fd, pen=pg.mkPen('w'))
            self.fitted_data.update()

         # now do the fit
        whichaxis = 0
        (fpar, xf, yf, names) = Fits.FitRegion(whichdata, whichaxis,
                                               self.traces.xvals('Time'),
                                               self.traces.view(numpy.ndarray),
                                               dataType='2d',
                                               t0=rgn[0], t1=rgn[1],
                                               fitFunc=Func,
                                               fitPars=initpars)
        if fpar == []:
            print 'IVCurve::update_Tauh: tau_h fitting failed - see log'
            return
        redpen = pg.mkPen('r', width=1.5, style=QtCore.Qt.DashLine)
        if self.fit_curve is None:
            self.fit_curve = self.data_plot.plot(xf[0], yf[0],
                                                 pen=redpen)
        else:
            self.fit_curve.clear()
            self.fit_curve = self.data_plot.plot(xf[0], yf[0],
                                                 pen=redpen)
            self.fit_curve.update()

        outstr = ""
        s = numpy.shape(fpar)
        taus = []
        for j in range(0, s[0]):
            outstr = ""
            taus.append(fpar[j][2])
            for i in range(0, len(names[j])):
                outstr = outstr + ('%s = %f, ' %
                                   (names[j][i], fpar[j][i]*1000.))
            if printWindow:
                print("Ih FIT(%d, %.1f pA): %s " %
                      (whichdata[j], itaucmd[j]*1e12, outstr))
        meantau = numpy.mean(taus)
        self.ctrl.IVCurve_Tauh.setText(u'%8.1f ms' % (meantau*1.e3))
        self.tau2 = meantau
        tautext = 'Mean Tauh: %8.1f'
        bovera = (vss-vrmp)/(vpk-vrmp)
        self.ctrl.IVCurve_Ih_ba.setText('%8.1f' % (bovera*100.))
        self.ctrl.IVCurve_ssAmp.setText('%8.2f' % (vss-vrmp))
        self.ctrl.IVCurve_pkAmp.setText('%8.2f' % (vpk-vrmp))
        if bovera < 0.55 and self.tau2 < 0.015:  #
            self.ctrl.IVCurve_FOType.setText('D Stellate')
        else:
            self.ctrl.IVCurve_FOType.setText('T Stellate')

         # estimate of Gh:
        Gpk = itarget / self.neg_pk
        Gss = itarget / self.neg_ss
        self.Gh = Gss-Gpk
        self.ctrl.IVCurve_Gh.setText('%8.2f nS' % (self.Gh*1e9))

    def update_ssAnalysis(self, clear=True):
        """
        Compute the steady-state IV from the selected time window

        Input parameters:
            clear: a boolean flag that originally allowed accumulation of plots
                    presently, ignored.
        returns:
            nothing.
        modifies:
            ivss, yleak, ivss_cmd, cmd.

        The IV curve is only valid when there are no spikes detected in
            the window. The values in the curve are taken as the mean of the
            current and the voltage in the time window, at each command step.
        We also compute the input resistance.
        For voltage clamp data, we can optionally remove the "leak" current.
        The resulting curve is plotted.
        """
        if self.traces is None:
            return
        rgnss = self.lrss.getRegion()
        self.ctrl.IVCurve_ssTStart.setValue(rgnss[0]*1.0e3)
        self.ctrl.IVCurve_ssTStop.setValue(rgnss[1]*1.0e3)
        data1 = self.traces['Time': rgnss[0]:rgnss[1]]
        self.ivss = []
        commands = numpy.array(self.values)

         # check out whether there are spikes in the window that is selected
        threshold = self.ctrl.IVCurve_SpikeThreshold.value() * 1e-3
        ntr = len(self.traces)
        spikecount = numpy.zeros(ntr)
        for i in range(ntr):
            (spike, spk) = Utility.findspikes(self.tx, self.traces[i],
                                              threshold,
                                              t0=rgnss[0], t1=rgnss[1],
                                              dt=self.sampInterval,
                                              mode='schmitt',
                                              interpolate=False,
                                              debug=False)
            if len(spike) == 0:
                continue
            spikecount[i] = len(spike)
        nospk = numpy.where(spikecount == 0)
        if data1.shape[1] == 0 or data1.shape[0] == 1:
            return  # skip it

        self.ivss = data1.mean(axis=1)  # all traces
        if self.ctrl.IVCurve_SubRMP.isChecked():
            self.ivss = self.ivss - self.ivrmp

        if len(nospk) >= 1:
             # Steady-state IV where there are no spikes
            self.ivss = self.ivss[nospk]
            self.ivss_cmd = commands[nospk]
            self.cmd = commands[nospk]
             # compute Rin from the SS IV:
            if len(self.cmd) > 0 and len(self.ivss) > 0:
                self.Rin = numpy.max(numpy.diff
                                     (self.ivss)/numpy.diff(self.cmd))
                self.ctrl.IVCurve_Rin.setText(u'%9.1f M\u03A9'
                                              % (self.Rin*1.0e-6))
            else:
                self.ctrl.IVCurve_Rin.setText(u'No valid points')
        # self.ivss = self.ivss.view(numpy.ndarray)
        self.yleak = numpy.zeros(len(self.ivss))
        if self.ctrl.IVCurve_subLeak.isChecked():
            (x, y) = Utility.clipdata(self.ivss, self.ivss_cmd,
                                      self.ctrl.IVCurve_LeakMin.value()*1e-3,
                                      self.ctrl.IVCurve_LeakMax.value()*1e-3)
            p = numpy.polyfit(x, y, 1)  # linear fit
            self.yleak = numpy.polyval(p, self.ivss_cmd)
            self.ivss = self.ivss - self.yleak
        self.update_IVPlot()

    def update_pkAnalysis(self, clear=False, pw=False):
        """
            Compute the peak IV (minimum) from the selected window
        """
        if self.traces is None:
            return
        rgnpk = self.lrpk.getRegion()
        self.ctrl.IVCurve_pkTStart.setValue(rgnpk[0]*1.0e3)
        self.ctrl.IVCurve_pkTStop.setValue(rgnpk[1]*1.0e3)
        data2 = self.traces['Time': rgnpk[0]:rgnpk[1]]
        commands = numpy.array(self.values)
         # check out whether there are spikes in the window that is selected
        threshold = self.ctrl.IVCurve_SpikeThreshold.value() * 1e-3
        ntr = len(self.traces)
        spikecount = numpy.zeros(ntr)
        for i in range(ntr):
            (spike, spk) = Utility.findspikes(self.tx, self.traces[i],
                                              threshold,
                                              t0=rgnpk[0], t1=rgnpk[1],
                                              dt=self.sampInterval,
                                              mode='schmitt',
                                              interpolate=False, debug=False)
            if len(spike) == 0:
                continue
            spikecount[i] = len(spike)
        nospk = numpy.where(spikecount == 0)
        if data2.shape[1] == 0:
            return  # skip it
        self.ivpk = data2.min(axis=1)
        if self.ctrl.IVCurve_SubRMP.isChecked():
            self.ivpk = self.ivpk - self.ivrmp

        if len(nospk) >= 1:
             # Peak (minimum voltage) IV where there are no spikes
            self.ivpk = self.ivpk[nospk]
            self.ivpk_cmd = commands[nospk]
            self.cmd = commands[nospk]
        self.ivpk = self.ivpk.view(numpy.ndarray)
        self.update_Tau(printWindow=pw)
        if self.ctrl.IVCurve_subLeak.isChecked():
            self.ivpk = self.ivpk - self.yleak
        self.update_IVPlot()

    def update_rmpAnalysis(self, clear=True, pw=False):
        """
            Compute the RMP over time/commands from the selected window
        """
        if self.traces is None:
            return
        rgnrmp = self.lrrmp.getRegion()
        self.ctrl.IVCurve_rmpTStart.setValue(rgnrmp[0]*1.0e3)
        self.ctrl.IVCurve_rmpTStop.setValue(rgnrmp[1]*1.0e3)
        data1 = self.traces['Time': rgnrmp[0]:rgnrmp[1]]
        data1 = data1.view(numpy.ndarray)
        self.ivrmp = []
        commands = numpy.array(self.values)
        self.ivrmp = data1.mean(axis=1)  # all traces
        self.ivrmp_cmd = commands
        self.cmd = commands
        self.averageRMP = numpy.mean(self.ivrmp)
        self.update_RMPPlot()

    def makeMapSymbols(self):
        """
        Given the current state of things, (keep analysis count, for example),
        return a tuple of pen, fill color, empty color, a symbol from
        our lists, and a clearflag. Used to overplot different data.
        """
        n = self.keepAnalysisCount
        pen = self.colorList.next()
        filledbrush = pen
        emptybrush = None
        symbol = self.symbolList.next()
        if n == 0:
            clearFlag = True
        else:
            clearFlag = False
        self.currentSymDict = {'pen': pen, 'filledbrush': filledbrush,
                               'emptybrush': emptybrush, 'symbol': symbol,
                               'n': n, 'clearFlag': clearFlag}

    def mapSymbol(self):
        cd = self.currentSymDict
        if cd['filledbrush'] == 'w':
            cd['filledbrush'] = pg.mkBrush((128, 128, 128))
        if cd['pen'] == 'w':
            cd['pen'] = pg.mkPen((128, 128, 128))
        self.lastSymbol = (cd['pen'], cd['filledbrush'],
                           cd['emptybrush'], cd['symbol'],
                           cd['n'], cd['clearFlag'])
        return(self.lastSymbol)

    def update_IVPlot(self):
        """
            Draw the peak and steady-sate IV to the I-V window
            Note: x axis is always I or V, y axis V or I
        """
        if self.ctrl.IVCurve_KeepAnalysis.isChecked() is False:
            self.IV_plot.clear()
        (pen, filledbrush, emptybrush, symbol, n, clearFlag) =\
            self.mapSymbol()
        if self.dataMode in self.ICModes:
            if (len(self.ivss) > 0 and
                    self.ctrl.IVCurve_showHide_lrss.isChecked()):
                self.IV_plot.plot(self.ivss_cmd*1e12, self.ivss*1e3,
                                  symbol=symbol, pen=pen,
                                  symbolSize=6, symbolPen=pen,
                                  symbolBrush=filledbrush)
            if (len(self.ivpk) > 0 and
                    self.ctrl.IVCurve_showHide_lrpk.isChecked()):
                self.IV_plot.plot(self.ivpk_cmd*1e12, self.ivpk*1e3,
                                  symbol=symbol, pen=pen,
                                  symbolSize=6, symbolPen=pen,
                                  symbolBrush=emptybrush)
            self.labelUp(self.IV_plot, 'I (pA)', 'V (mV)', 'I-V (CC)')
        if self.dataMode in self.VCModes:
            if (len(self.ivss) > 0 and
                    self.ctrl.IVCurve_showHide_lrss.isChecked()):
                self.IV_plot.plot(self.ivss_cmd*1e3, self.ivss*1e9,
                                  symbol=symbol, pen=pen,
                                  symbolSize=6, symbolPen=pen,
                                  symbolBrush=filledbrush)
            if (len(self.ivpk) > 0 and
                    self.ctrl.IVCurve_showHide_lrpk.isChecked()):
                self.IV_plot.plot(self.ivpk_cmd*1e3, self.ivpk*1e9,
                                  symbol=symbol, pen=pen,
                                  symbolSize=6, symbolPen=pen,
                                  symbolBrush=emptybrush)
            self.labelUp(self.IV_plot, 'V (mV)', 'I (nA)', 'I-V (VC)')

    def update_RMPPlot(self):
        """
            Draw the RMP to the I-V window
            Note: x axis can be I, T, or  # spikes
        """
        if self.ctrl.IVCurve_KeepAnalysis.isChecked() is False:
            self.RMP_plot.clear()
        if len(self.ivrmp) > 0:
            (pen, filledbrush, emptybrush, symbol, n, clearFlag) =\
                self.mapSymbol()
            mode = self.ctrl.IVCurve_RMPMode.currentIndex()
            if self.dataMode in self.ICModes:
                sf = 1e3
                self.RMP_plot.setLabel('left', 'V mV')
            else:
                sf = 1e12
                self.RMP_plot.setLabel('left', 'I (pA)')
            if mode == 0:
                self.RMP_plot.plot(self.traceTimes, sf*numpy.array(self.ivrmp),
                                   symbol=symbol, pen=pen,
                                   symbolSize=6, symbolPen=pen,
                                   symbolBrush=filledbrush)
                self.RMP_plot.setLabel('bottom', 'T (s)')
            elif mode == 1:
                self.RMP_plot.plot(self.cmd,
                                   1.e3*numpy.array(self.ivrmp), symbolSize=6,
                                   symbol=symbol, pen=pen,
                                   symbolPen=pen, symbolBrush=filledbrush)
                self.RMP_plot.setLabel('bottom', 'I (pA)')
            elif mode == 2:
                self.RMP_plot.plot(self.spikecount,
                                   1.e3*numpy.array(self.ivrmp), symbolSize=6,
                                   symbol=symbol, pen=pen,
                                   symbolPen=pen, symbolBrush=emptybrush)
                self.RMP_plot.setLabel('bottom', 'Spikes')
            else:
                pass

    def update_SpikePlots(self):
        """
            Draw the spike counts to the FI and FSL windows
            Note: x axis can be I, T, or  # spikes
        """
        if self.dataMode in self.VCModes:
            self.fiPlot.clear()  # no plots of spikes in VC
            self.fslPlot.clear()
            return
        (pen, filledbrush, emptybrush, symbol, n, clearFlag) = self.mapSymbol()
        mode = self.ctrl.IVCurve_RMPMode.currentIndex()  # get x axis mode
        commands = numpy.array(self.values)
        self.cmd = commands[self.nospk]
        self.spcmd = commands[self.spk]
        iscale = 1.0e12  # convert to pA
        yfslsc = 1.0  # convert to msec
        if mode == 0:  # plot with time as x axis
            xfi = self.traceTimes
            xfsl = self.traceTimes
            select = range(len(self.traceTimes))
            xlabel = 'T (s)'
        elif mode == 1:  # plot with current as x
            select = self.spk
            xfi = commands*iscale
            xfsl = self.spcmd*iscale
            xlabel = 'I (pA)'
        elif mode == 2:  # plot with spike counts as x
            xfi = self.spikecount
            xfsl = self.spikecount
            select = range(len(self.spikecount))
            xlabel = 'Spikes (N)'
        else:
            return  # mode not in available list
        self.fiPlot.plot(x=xfi, y=self.spikecount, clear=clearFlag,
                         symbolSize=6,
                         symbol=symbol, pen=pen,
                         symbolPen=pen, symbolBrush=filledbrush)
        self.fslPlot.plot(x=xfsl, y=self.fsl[select]*yfslsc, clear=clearFlag,
                          symbolSize=6,
                          symbol=symbol, pen=pen,
                          symbolPen=pen, symbolBrush=filledbrush)
        self.fslPlot.plot(x=xfsl, y=self.fisi[select]*yfslsc, symbolSize=6,
                          symbol=symbol, pen=pen,
                          symbolPen=pen, symbolBrush=emptybrush)
        if len(xfsl) > 0:
            self.fslPlot.setXRange(0.0, numpy.max(xfsl))
        self.fiPlot.setLabel('bottom', xlabel)
        self.fslPlot.setLabel('bottom', xlabel)

    def readParameters(self, clearFlag=False, pw=False):
        """
        Read the parameter window entries, set the lr regions, and do an
        update on the analysis
        """
        (pen, filledbrush, emptybrush, symbol, n, clearFlag) = self.mapSymbol()
        # update RMP first as we might use it for the others.
        if self.ctrl.IVCurve_showHide_lrrmp.isChecked():
            rgnx1 = self.ctrl.IVCurve_rmpTStart.value()/1.0e3
            rgnx2 = self.ctrl.IVCurve_rmpTStop.value()/1.0e3
            self.lrrmp.setRegion([rgnx1, rgnx2])
            self.update_rmpAnalysis(clear=clearFlag, pw=pw)

        if self.ctrl.IVCurve_showHide_lrss.isChecked():
            rgnx1 = self.ctrl.IVCurve_ssTStart.value()/1.0e3
            rgnx2 = self.ctrl.IVCurve_ssTStop.value()/1.0e3
            self.lrss.setRegion([rgnx1, rgnx2])
            self.update_ssAnalysis(clear=clearFlag)

        if self.ctrl.IVCurve_showHide_lrpk.isChecked():
            rgnx1 = self.ctrl.IVCurve_pkTStart.value()/1.0e3
            rgnx2 = self.ctrl.IVCurve_pkTStop.value()/1.0e3
            self.lrpk.setRegion([rgnx1, rgnx2])
            self.update_pkAnalysis(clear=clearFlag, pw=pw)

        if self.ctrl.IVCurve_subLeak.isChecked():
            rgnx1 = self.ctrl.IVCurve_LeakMin.value()/1e3
            rgnx2 = self.ctrl.IVCurve_LeakMax.value()/1e3
            self.lrleak.setRegion([rgnx1, rgnx2])
            self.update_ssAnalysis()
            self.update_pkAnalysis()

        if self.ctrl.IVCurve_showHide_lrtau.isChecked():
            # include tau in the list... if the tool is selected
            self.update_Tauh()

    def update_RMPPlot_MP(self):
        """
            Draw the RMP to the I-V window using matplotlib
            Note: x axis can be I, T, or  # spikes
        """
        if self.ctrl.IVCurve_KeepAnalysis.isChecked() is False:
            self.mplax['RMP'].clear()
        if len(self.ivrmp) > 0:
            mode = self.ctrl.IVCurve_RMPMode.currentIndex()
            ax = self.mplax['RMP']
            ax.set_title('RMP', verticalalignment='top', size=11)
            if self.dataMode in self.ICModes:
                sf = 1e12
                isf = 1e3
                ax.set_ylabel('V (mV)', size=9)
            else:
                sf = 1e3
                isf = 1e12
                ax.set_ylabel('I (pA)', size=9)
            if mode == 0:
                ax.plot(self.traceTimes, isf*numpy.array(self.ivrmp),
                        'k-s', markersize=2)
                ax.set_xlabel('T (s)', size=9)
            elif mode == 1:
                ax.plot(numpy.array
                        (self.values)*sf, isf*numpy.array(self.ivrmp),
                        'k-s', markersize=2)
                if self.dataMode in self.ICModes:
                    ax.set_xlabel('I (pA)', size=9)
                else:
                    ax.set_xlabel('V (mV)', size=9)
            elif mode == 2:
                ax.plot(self.spikecount, isf*numpy.array(self.ivrmp),
                        'k-s', markersize=2)
                ax.set_xlabel('Spikes', size=9)
            else:
                pass

    def update_IVPlot_MP(self):
        """
            Draw the IV o the I-V window using matplotlib
            Note: x axis can be I, T, or  # spikes
        """
        if self.ctrl.IVCurve_KeepAnalysis.isChecked() is False:
            self.mplax['IV'].clear()
        ax = self.mplax['IV']
        n = self.keepAnalysisCount
        if self.dataMode in self.ICModes:
            if (len(self.ivss) > 0 and
                    self.ctrl.IVCurve_showHide_lrss.isChecked()):
                ax.plot(self.ivss_cmd*1e12, self.ivss*1e3, 'k-s', markersize=3)
            if (len(self.ivpk) > 0 and
                    self.ctrl.IVCurve_showHide_lrpk.isChecked()):
                ax.plot(self.ivpk_cmd*1e12, self.ivpk*1e3, 'r-o', markersize=3)
            ax.set_xlabel('I (pA)', size=9)
            ax.set_ylabel('V (mV)', size=9)
            ax.set_title('I-V (CC)', verticalalignment='top', size=11)
        if self.dataMode in self.VCModes:
            if (len(self.ivss) > 0 and
                    self.ctrl.IVCurve_showHide_lrss.isChecked()):
                ax.plot(self.ivss_cmd*1e3, self.ivss*1e9, 'k-s', markersize=3)
            if (len(self.ivpk) > 0 and
                    self.ctrl.IVCurve_showHide_lrpk.isChecked()):
                ax.plot(self.ivpk_cmd*1e3, self.ivpk*1e9, 'r-o', markersize=3)
            ax.set_xlabel('V (mV)', size=9)
            ax.set_ylabel('I (nA)', size=9)
            ax.set_title('I-V (VC)', verticalalignment='top', size=11)

    def update_SpikePlots_MP(self):
        """
            Draw the spike count data the I-V window using matplotlib
            Note: x axis can be I, T, or  # spikes
        """
        if self.ctrl.IVCurve_KeepAnalysis.isChecked() is False:
            axfi = self.mplax['FI']
            axfi.clear()
            axfsl = self.mplax['FSL']
            axfsl.clear()
        if self.dataMode in self.VCModes:
            return
        mode = self.ctrl.IVCurve_RMPMode.currentIndex()  # get x axis mode
        commands = numpy.array(self.values)
        self.cmd = commands[self.nospk]
        self.spcmd = commands[self.spk]
        iscale = 1.0e12  # convert to pA
        yfslsc = 1.0  # convert to msec
        if mode == 0:  # plot with time as x axis
            xfi = self.traceTimes
            xfsl = self.traceTimes
            select = range(len(self.traceTimes))
            xlabel = 'T (s)'
        elif mode == 1:  # plot with current as x
            select = self.spk
            xfi = commands*iscale
            xfsl = self.spcmd*iscale
            xlabel = 'I (pA)'
        elif mode == 2:  # plot with spike counts as x
            xfi = self.spikecount
            xfsl = self.spikecount
            select = range(len(self.spikecount))
            xlabel = 'Spikes (N)'
        else:
            return  # mode not in available list
        axfi.plot(xfi, self.spikecount, 'b-s', markersize=3)
        axfsl.plot(xfsl, self.fsl[select]*yfslsc, 'g-^', markersize=3)
        axfsl.plot(xfsl, self.fisi[select]*yfslsc, 'y-s', markersize=3)
        if len(self.spcmd) > 0:
            axfsl.set_xlim([0.0, numpy.max(xfsl)])
        axfi.set_xlabel(xlabel, size=9)
        axfi.set_ylabel('\# spikes', size=9)
        axfi.set_title('F-I', verticalalignment='top', size=11)
        axfsl.set_xlabel(xlabel, size=9)
        axfsl.set_ylabel('FSL/FISI', size=9)
        axfsl.set_title('FSL/FISI', verticalalignment='top', size=11)

    def cleanRepl(self, matchobj):
        """
            Clean up a directory name so that it can be written to a
            matplotlib title without encountering LaTeX escape sequences
            Replace backslashes with forward slashes
            replace underscores (subscript) with escaped underscores
        """
        if matchobj.group(0) == '\\':
            return '/'
        if matchobj.group(0) == '_':
            return '\_'
        if matchobj.group(0) == '/':
            return '/'
        else:
            return ''

    def matplotlibExport(self):
        """
        Make a matplotlib window that shows the current data in the same
        format as the pyqtgraph window
        Probably you would use this for publication purposes.
        """
        fig = pylab.figure(1)
         # escape filename information so it can be rendered by removing
         # common characters that trip up latex...:
        escs = re.compile('[\\\/_]')
        tiname = '%r' % self.filename
        tiname = re.sub(escs, self.cleanRepl, tiname)
         #print tiname
        fig.suptitle(r''+tiname[1:-1])
        pylab.autoscale(enable=True, axis='both', tight=None)
        if self.dataMode not in self.ICModes or self.tx is None:
            iscale = 1e3
        else:
            iscale = 1e12
        self.mplax = {}
        gs = gridspec.GridSpec(4, 2)
        self.mplax['data'] = pylab.subplot(gs[0:3, 0])
        self.mplax['cmd'] = pylab.subplot(gs[3, 0])
        self.mplax['IV'] = pylab.subplot(gs[0, 1])
        self.mplax['RMP'] = pylab.subplot(gs[1, 1])
        self.mplax['FI'] = pylab.subplot(gs[2, 1])
        self.mplax['FSL'] = pylab.subplot(gs[3, 1])
        gs.update(wspace=0.25, hspace=0.5)
        self.mplax['data'].set_title('Data', verticalalignment='top', size=11)

        for i in range(len(self.traces)):
            self.mplax['data'].plot(self.tx, self.traces[i]*1e3, 'k')
            self.mplax['cmd'].plot(self.tx, self.cmd_wave[i]*iscale, 'k')
        self.mplax['data'].set_ylabel('mV', size=9)
        self.mplax['data'].set_xlabel('T (s)', size=9)
        self.mplax['cmd'].set_ylabel('pA', size=9)
        self.mplax['cmd'].set_xlabel('T (s)', size=9)
        self.update_IVPlot_MP()
        self.update_RMPPlot_MP()
        self.update_SpikePlots_MP()

        for ax in self.mplax:
            self.cleanAxes(self.mplax[ax])
        for a in ['data', 'IV', 'FI', 'FSL', 'RMP', 'cmd']:
            self.formatTicks(self.mplax[a], 'y', '%d')
        for a in ['FI', 'IV', 'RMP', 'FSL']:
            self.formatTicks(self.mplax[a], 'x', '%d')
        pylab.draw()
        pylab.savefig(os.path.join(self.commonPrefix,
                      'PlotPDFs', self.protocol))
        pylab.show()

    def dbStoreClicked(self):
        """
        Store data into the current database for further analysis
        """
        self.updateAnalysis()
        db = self._host_.dm.currentDatabase()
        table = 'DirTable_Cell'
        columns = OrderedDict([
            ('IVCurve_rmp', 'real'),
            ('IVCurve_rinp', 'real'),
            ('IVCurve_taum', 'real'),
            ('IVCurve_neg_cmd', 'real'),
            ('IVCurve_neg_pk', 'real'),
            ('IVCurve_neg_ss', 'real'),
            ('IVCurve_h_tau', 'real'),
            ('IVCurve_h_g', 'real'),
        ])

        rec = {
            'IVCurve_rmp': self.neg_vrmp/1000.,
            'IVCurve_rinp': self.Rin,
            'IVCurve_taum': self.tau,
            'IVCurve_neg_cmd': self.neg_cmd,
            'IVCurve_neg_pk': self.neg_pk,
            'IVCurve_neg_ss': self.neg_ss,
            'IVCurve_h_tau': self.tau2,
            'IVCurve_h_g': self.Gh,
        }

        with db.transaction():
             # Add columns if needed
            if 'IVCurve_rmp' not in db.tableSchema(table):
                for col, typ in columns.items():
                    db.addColumn(table, col, typ)

            db.update(table, rec, where={'Dir': self.loaded.parent()})
        print "updated record for ", self.loaded.name()

#---- Helpers ----
# Some of these would normally live in a pyqtgraph-related module, but are
# just stuck here to get the job done.
#
    def labelUp(self, plot, xtext, ytext, title):
        """helper to label up the plot"""
        plot.setLabel('bottom', xtext)
        plot.setLabel('left', ytext)
        plot.setTitle(title)

# for matplotlib cleanup:
# These were borrowed from Manis' "PlotHelpers.py"
#
    def cleanAxes(self, axl):
        if type(axl) is not list:
            axl = [axl]
        for ax in axl:
            for loc, spine in ax.spines.iteritems():
                if loc in ['left', 'bottom']:
                    pass
                elif loc in ['right', 'top']:
                    spine.set_color('none')  # do not draw the spine
                else:
                    raise ValueError('Unknown spine location: %s' % loc)
                 # turn off ticks when there is no spine
                ax.xaxis.set_ticks_position('bottom')
                # stopped working in matplotlib 1.10
                ax.yaxis.set_ticks_position('left')
            self.update_font(ax)

    def update_font(self, axl, size=6, font=stdFont):
        if type(axl) is not list:
            axl = [axl]
        fontProperties = {'family': 'sans-serif', 'sans-serif': [font],
                          'weight': 'normal', 'size': size}
        for ax in axl:
            for tick in ax.xaxis.get_major_ticks():
                tick.label1.set_family('sans-serif')
                tick.label1.set_fontname(stdFont)
                tick.label1.set_size(size)

            for tick in ax.yaxis.get_major_ticks():
                tick.label1.set_family('sans-serif')
                tick.label1.set_fontname(stdFont)
                tick.label1.set_size(size)
            ax.set_xticklabels(ax.get_xticks(), fontProperties)
            ax.set_yticklabels(ax.get_yticks(), fontProperties)
            ax.xaxis.set_smart_bounds(True)
            ax.yaxis.set_smart_bounds(True)
            ax.tick_params(axis='both', labelsize=9)

    def formatTicks(self, axl, axis='xy', fmt='%d', font='Arial'):
        """
        Convert tick labels to intergers
        to do just one axis, set axis = 'x' or 'y'
        control the format with the formatting string
        """
        if type(axl) is not list:
            axl = [axl]
        majorFormatter = FormatStrFormatter(fmt)
        for ax in axl:
            if 'x' in axis:
                ax.xaxis.set_major_formatter(majorFormatter)
            if 'y' in axis:
                ax.yaxis.set_major_formatter(majorFormatter)
