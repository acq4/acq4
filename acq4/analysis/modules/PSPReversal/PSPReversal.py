# -*- coding: utf-8 -*-
"""
PSPReversal: Analysis module that analyzes the current-voltage relationships
relationships of PSPs from voltage clamp data.
This is part of Acq4
Based on IVCurve (as of 5/2014)
Paul B. Manis, Ph.D.
2014.

Pep8 compliant (via pep8.py) 10/25/2013

"""

from collections import OrderedDict
import os
import re
import os.path
import itertools
import functools

from PyQt4 import QtGui, QtCore
import numpy as np
import numpy.ma as ma

from acq4.analysis.AnalysisModule import AnalysisModule
import acq4.pyqtgraph as pg
from acq4.util.metaarray import MetaArray


stdFont = 'Arial'

import acq4.analysis.tools.Utility as Utility  # pbm's utilities...
import acq4.analysis.tools.Fitting as Fitting  # pbm's fitting stuff...
import ctrlTemplate
import resultsTemplate


class PSPReversal(AnalysisModule):
    """
    PSPReversal is an Analysis Module for Acq4.

    PSPReversal performs analyses of current-voltage relationships in
    electrophysiology experiments. The module is interactive, and is primarily
    designed to allow a preliminary examination of data collected in current clamp and voltage clamp.
    Results analyzed include:
    RMP/Holding current as a function of time through the protocol
    Reversal potential determined from difference of two windows (or interpolation) with various measurements
    Prints reversal potential, IV curve (subtracted), and ancillary information
    
    """

    def __init__(self, host):
        AnalysisModule.__init__(self, host)
        # Note that self.dataModel is set by the host.
        # This module assumes that the dataModel is PatchEPhys

        #-------------data elements---------------
        self.current_dirhandle = None
        self.data_loaded = None  #
        self.lrwin1_flag = True  # show is default
        self.lrwin2_flag = True
        self.rmp_flag = True
        self.lrtau_flag = False
        self.measure = {'rmp': [], 'rmpcmd': [],
                        'leak': [],
                        'win1': [], 'win1cmd': [], 'win1off': [], 'win1on': [], 'winaltcmd': [],
                        'win2': [], 'win2cmd': [], 'win2off': [], 'win2on': [], 'winaltcmd': [],
        }
        self.cmd = None
        self.junction = 0.0  # junction potential (user adjustable)
        self.holding = 0.0  # holding potential (read from commands)
        self.regionsExist = False  #
        self.regions = {}
        self.fit_curve = None
        self.fitted_data = None
        self.tx = None
        self.keepAnalysisCount = 0
        self.spikesCounted = False
        self.alternation = False  # data collected with "alternation" protocols
        self.dataMode = 'IC'  # analysis depends on the type of data we have.
        self.ICModes = ['IC', 'CC', 'IClamp']  # list of CC modes
        self.VCModes = ['VC', 'VClamp']  # list of VC modes

        #--------------graphical elements-----------------
        self._sizeHint = (1280, 900)   # try to establish size of window
        self.ctrlWidget = QtGui.QWidget()
        self.ctrl = ctrlTemplate.Ui_Form()
        self.ctrl.setupUi(self.ctrlWidget)
        self.results = resultsTemplate.Ui_Dialog()
        self.resultsWidget = QtGui.QWidget()
        self.results.setupUi(self.resultsWidget)
        self.main_layout = pg.GraphicsView()  # instead of GraphicsScene?
        # make fixed widget for the module output
        self.widget = QtGui.QWidget()
        self.gridLayout = QtGui.QGridLayout()
        self.widget.setLayout(self.gridLayout)
        self.gridLayout.setContentsMargins(4, 4, 4, 4)
        self.gridLayout.setSpacing(1)
        # Setup basic GUI
        self._elements_ = OrderedDict([
            ('File Loader',
             {'type': 'fileInput', 'size': (150, 50), 'host': self}),
            ('Parameters',
             {'type': 'ctrl', 'object': self.ctrlWidget, 'host': self,
              'size': (150, 700)}),
            ('Results',
             {'type': 'ctrl', 'object': self.resultsWidget, 'host': self,
              'size': (150, 700)}),
            ('Plots',
             {'type': 'ctrl', 'object': self.widget, 'pos': ('right',),
              'size': (400, 700)}),
        ])
        self.initializeElements()
        self.fileLoaderInstance = self.getElement('File Loader', create=True)
        # grab input form the "Ctrl" window
        self.ctrl.PSPReversal_Update.clicked.connect(self.update_allAnalysis)
        self.ctrl.PSPReversal_PrintResults.clicked.connect(self.printAnalysis)
        self.ctrl.PSPReversal_KeepAnalysis.clicked.connect(self.resetKeepAnalysis)
        self.ctrl.PSPReversal_getFileInfo.clicked.connect(self.getFileInfo)
        self.ctrl.PSPReversal_Alternation.clicked.connect(self.getAlternation)
        [self.ctrl.PSPReversal_RMPMode.currentIndexChanged.connect(x)
         for x in [self.update_rmpAnalysis, self.count_spikes]]
        self.ctrl.PSPReversal_Junction.valueChanged.connect(self.set_junction)
        self.ctrl.dbStoreBtn.clicked.connect(self.dbstore_clicked)
        self.clearResults()
        self.layout = self.getElement('Plots', create=True)

        # instantiate the graphs using a gridLayout
        self.data_plot = pg.PlotWidget()
        self.gridLayout.addWidget(self.data_plot, 0, 0, 3, 1)
        self.label_up(self.data_plot, 'T (s)', 'V (V)', 'Data')

        self.cmd_plot = pg.PlotWidget()
        self.gridLayout.addWidget(self.cmd_plot, 3, 0, 1, 1)
        self.label_up(self.cmd_plot, 'T (s)', 'I (A)', 'Command')

        self.RMP_plot = pg.PlotWidget()
        self.gridLayout.addWidget(self.RMP_plot, 1, 1, 1, 1)
        self.label_up(self.RMP_plot, 'T (s)', 'V (mV)', 'RMP')

        self.unusedPlot = pg.PlotWidget()
        self.gridLayout.addWidget(self.unusedPlot, 2, 1, 1, 1)
        #self.label_up(self.unusedPlot, 'I (pA)', 'Fsl/Fisi (ms)', 'FSL/FISI')

        self.cmdPlot = pg.PlotWidget()
        self.gridLayout.addWidget(self.cmdPlot, 3, 1, 1, 1)
        self.label_up(self.cmdPlot, 'T (s)', 'V (mV)', 'Commands(T)')

        self.IV_plot = pg.PlotWidget()
        self.gridLayout.addWidget(self.IV_plot, 0, 1, 1, 1)
        self.label_up(self.IV_plot, 'I (pA)', 'V (V)', 'I-V')
        for row, s in enumerate([20, 10, 10, 10]):
            self.gridLayout.setRowStretch(row, s)

            #    self.tailPlot = pg.PlotWidget()
            #    self.gridLayout.addWidget(self.fslPlot, 3, 1, 1, 1)
            #    self.label_up(self.tailPlot, 'V (V)', 'I (A)', 'Tail Current')

        # Add color scales and some definitions
        self.colors = ['w', 'g', 'b', 'r', 'y', 'c']
        self.symbols = ['o', 's', 't', 'd', '+']
        self.colorList = itertools.cycle(self.colors)
        self.symbolList = itertools.cycle(self.symbols)
        self.colorScale = pg.GradientLegend((20, 150), (-10, -10))
        self.data_plot.scene().addItem(self.colorScale)

    def clearResults(self):
        """
        clearResults resets variables.

        This is typically needed everytime a new data set is loaded.
        """
        self.filename = ''
        self.Rin = 0.0
        self.tau = 0.0
        self.AdaptRatio = 0.0
        self.traces = None
        self.spikesCounted = False
        self.nospk = []
        self.spk = []
        self.cmd = []
        self.Sequence = ''
        for m in self.measure.keys():
            self.measure[m] = []
        self.rmp = []  # resting membrane potential during sequence

    def resetKeepAnalysis(self):
        self.keepAnalysisCount = 0  # reset counter.

    def getAlternation(self):
        self.alternation = self.ctrl.PSPReversal_Alternation.isChecked()

    def set_junction(self):
        self.junction = self.ctrl.PSPReversal_Junction.value()

    def initialize_Regions(self):
        """
        initialize_Regions sets the linear regions on the displayed data

        Here we create the analysis regions in the plot. However, this should
        NOT happen until the plot has been created
        Note the the information about each region is held in a dictionary,
        which for each region has a dictionary that accesses the UI and class methodss for
        that region. This later simplifies the code and reduces repetitive sections.
        """
        # hold all the linear regions in a dictionary
        if not self.regionsExist:
            self.regions['lrwin1'] = {'name': 'win1',
                                      'region': pg.LinearRegionItem([0, 1],
                                                                    brush=pg.mkBrush(0, 255, 0, 50.)),
                                      'plot': self.data_plot,
                                      'state': self.ctrl.PSPReversal_showHide_lrwin1,
                                      'shstate': True,  # keep internal copy of the state
                                      'mode': self.ctrl.PSPReversal_win1mode,
                                      'start': self.ctrl.PSPReversal_win1TStart,
                                      'stop': self.ctrl.PSPReversal_win1TStop,
                                      'updater': self.update_winAnalysis,
                                      'units': 'ms'}
            self.ctrl.PSPReversal_showHide_lrwin1.region = self.regions['lrwin1']['region']  # save region with checkbox
            self.regions['lrwin2'] = {'name': 'win2',
                                      'region': pg.LinearRegionItem([0, 1],
                                                                    brush=pg.mkBrush(0, 0, 255, 50.)),
                                      'plot': self.data_plot,
                                      'state': self.ctrl.PSPReversal_showHide_lrwin2,
                                      'shstate': True,  # keep internal copy of the state
                                      'mode': self.ctrl.PSPReversal_win2mode,
                                      'start': self.ctrl.PSPReversal_win2TStart,
                                      'stop': self.ctrl.PSPReversal_win2TStop,
                                      'updater': self.update_winAnalysis,
                                      'units': 'ms'}
            self.ctrl.PSPReversal_showHide_lrwin2.region = self.regions['lrwin2']['region']  # save region with checkbox
            # self.lrtau = pg.LinearRegionItem([0, 1],
            #                                  brush=pg.mkBrush(255, 0, 0, 50.))
            self.regions['lrrmp'] = {'name': 'rmp',
                                     'region': pg.LinearRegionItem([0, 1],
                                                                   brush=pg.mkBrush
                                                                   (255, 255, 0, 25.)),
                                     'plot': self.data_plot,
                                     'state': self.ctrl.PSPReversal_showHide_lrrmp,
                                     'shstate': True,  # keep internal copy of the state
                                     'mode': None,
                                     'start': self.ctrl.PSPReversal_rmpTStart,
                                     'stop': self.ctrl.PSPReversal_rmpTStop,
                                     'updater': self.update_rmpAnalysis,
                                     'units': 'ms'}
            self.ctrl.PSPReversal_showHide_lrrmp.region = self.regions['lrrmp']['region']  # save region with checkbox
            self.regions['lrleak'] = {'name': 'leak',
                                      'region': pg.LinearRegionItem([0, 1],
                                                                    brush=pg.mkBrush
                                                                    (255, 0, 255, 25.)),
                                      'plot': self.IV_plot,
                                      'shstate': True,  # keep internal copy of the state
                                      'state': self.ctrl.PSPReversal_subLeak,
                                      'mode': None,
                                      'start': self.ctrl.PSPReversal_leakTStart,
                                      'stop': self.ctrl.PSPReversal_leakTStop,
                                      'updater': self.update_allAnalysis,
                                      'units': 'mV'}
            self.ctrl.PSPReversal_subLeak.region = self.regions['lrleak']['region']  # save region with checkbox
            for reg in self.regions.keys():
                self.regions[reg]['plot'].addItem(self.regions[reg]['region'])
                self.regions[reg]['state'].clicked.connect(functools.partial(self.showhide,
                                                                             lrregion=reg))  #self.regions[reg]['state'].clicked.connect(self.showhide)   #lambda: self.showHide(region=reg))
                self.regions[reg]['region'].sigRegionChangeFinished.connect(
                    functools.partial(self.regions[reg]['updater'], region=self.regions[reg]['name']))
                if self.regions[reg]['mode'] is not None:
                    self.regions[reg]['mode'].currentIndexChanged.connect(self.update_allAnalysis)
            self.regionsExist = True
        for reg in self.regions.keys():
            for s in ['start', 'stop']:
                self.regions[reg][s].setSuffix(' ' + self.regions[reg]['units'])

                ######
                # The next set of short routines control showing and hiding of regions
                # in the plot of the raw data (traces)
                ######

    def showhide(self, lrregion=None):
        if lrregion is None:
            print('PSPReversal:showhide:: lrregion is None')
            return
        region = self.regions[lrregion]
        if not region['shstate']:
            region['region'].show()
            region['state'].setCheckState(QtCore.Qt.Checked)
            region['shstate'] = True
        else:
            region['region'].hide()
            region['state'].setCheckState(QtCore.Qt.Unchecked)
            region['shstate'] = False

    def uniq(self, inlist):
        # order preserving detection of unique values in a list
        uniques = []
        for item in inlist:
            if item not in uniques:
                uniques.append(item)
        return uniques

    def getFileInfo(self):
        """
        getFileInfo reads the sequence information from the
        currently selected data file

        Two-dimensional sequences are supported.

        """
        dh = self.fileLoaderInstance.selectedFiles()
        dh = dh[0]  # only the first file
        dirs = dh.subDirs()
        self.Sequence = self.dataModel.listSequenceParams(dh)
        keys = self.Sequence.keys()
        leftseq = [str(x) for x in self.Sequence[keys[0]]]
        if len(keys) > 1:
            rightseq = [str(x) for x in self.Sequence[keys[1]]]
        else:
            rightseq = []
        leftseq.insert(0, 'All')
        rightseq.insert(0, 'All')
        self.ctrl.PSPReversal_Sequence1.clear()
        self.ctrl.PSPReversal_Sequence2.clear()
        self.ctrl.PSPReversal_Sequence1.addItems(leftseq)
        self.ctrl.PSPReversal_Sequence2.addItems(rightseq)
        #        self.dirsSet = dh  # not sure we need this anymore...

    def cell_summary(self, dh):
        # other info into a dictionary
        self.CellSummary = {}
        self.CellSummary['Day'] = self.dataModel.getDayInfo(dh)
        self.CellSummary['Slice'] = self.dataModel.getSliceInfo(dh)
        self.CellSummary['Cell'] = self.dataModel.getCellInfo(dh)
        self.CellSummary['ACSF'] = self.dataModel.getACSF(dh)
        self.CellSummary['Internal'] = self.dataModel.getInternalSoln(dh)
        self.CellSummary['Temp'] = self.dataModel.getTemp(dh)
        self.CellSummary['Cell'] = self.dataModel.getCellType(dh)
        #print self.CellSummary

    def loadFileRequested(self, dh):
        """
        loadFileRequested is called by file loader when a file is requested.
        dh is the handle to the currently selected directory (or directories)

        Loads all of the successive records from the specified protocol.
        Stores ancillary information from the protocol in class variables.
        Extracts information about the commands, sometimes using a rather
        simplified set of assumptions.
        modifies: plots, sequence, data arrays, data mode, etc.
        """
        if len(dh) == 0:
            raise Exception("PSPReversal::loadFileRequested: " +
                            "Select an IV protocol directory.")
        if len(dh) != 1:
            raise Exception("PSPReversal::loadFileRequested: " +
                            "Can only load one file at a time.")
        self.clearResults()
        dh = dh[0]
        if self.current_dirhandle != dh:  # is this the current file/directory?
            self.getFileInfo()  # No, get info frommost recent file requested
            self.current_dirhandle = dh  # this is critical!
        self.cell_summary(dh)  # get other info as needed
#        self.current_dirhandle = dh  # save as our current one.
        self.protocolfile = ''
        self.data_plot.clearPlots()
        self.cmd_plot.clearPlots()
        self.filename = dh.name()
        dirs = dh.subDirs()
        # if dh != self.dirsSet:  # done in "getFile Info
        #     self.ctrl.PSPReversal_Sequence1.clear()
        #     self.ctrl.PSPReversal_Sequence2.clear()
        (head, tail) = os.path.split(self.filename)
        self.protocolfile = tail
        subs = re.compile('[\/]')
        self.protocolfile = re.sub(subs, '-', self.protocolfile)
        self.protocolfile = self.protocolfile + '.pdf'
        self.commonPrefix = self.filename
        traces = []
        cmd_wave = []
        self.tx = None
        self.values = []
        self.Sequence = self.dataModel.listSequenceParams(dh)  # already done in 'getfileinfo'
        self.traceTimes = np.zeros(0)
        maxplotpts = 1024

        # builidng command voltages - get amplitudes to clamp
        clamp = ('Clamp1', 'Pulse_amplitude')
        reps = ('protocol', 'repetitions')
        led = ('LED-Blue', 'Command.PulseTrain_amplitude')
        # repeat patterns for LED on/off
        if led in self.Sequence:  # first in alternation
            self.ledseq = self.Sequence[led]
            self.nledseq = len(self.ledseq)
            sequenceValues = [x for x in range(self.nledseq)]

        if clamp in self.Sequence:
            self.clampValues = self.Sequence[clamp]
            self.nclamp = len(self.clampValues)
            sequenceValues = [x for x in self.clampValues for y in sequenceValues]
        else:
            sequenceValues = []
            nclamp = 0

        # if sequence has repeats, build pattern
        if reps in self.Sequence:
            self.repc = self.Sequence[reps]
            self.nrepc = len(self.repc)
            sequenceValues = [x for y in range(self.nrepc) for x in sequenceValues]

        # select subset of data by overriding the directory sequence...
        if self.current_dirhandle is not None:
            ld = [self.ctrl.PSPReversal_Sequence1.currentIndex() - 1]
            rd = [self.ctrl.PSPReversal_Sequence2.currentIndex() - 1]
            if ld[0] == -1 and rd[0] == -1:
                pass
            else:
                if ld[0] == -1:  # 'All'
                    ld = range(self.ctrl.PSPReversal_Sequence1.count() - 1)
                if rd[0] == -1:  # 'All'
                    rd = range(self.ctrl.PSPReversal_Sequence2.count() - 1)
                dirs = []
                for i in ld:
                    for j in rd:
                        dirs.append('%03d_%03d' % (i, j))

        i = 0  # sometimes, the elements are not right...
        for i, dirName in enumerate(dirs):
            dataDirHandle = dh[dirName]
            try:
                dataFileHandle = self.dataModel.getClampFile(dataDirHandle)
                # Check if no clamp file for this iteration of the protocol
                # (probably the protocol was stopped early)
                if dataFileHandle is None:
                    print ('PSPReversal::loadFileRequested: ',
                           'Missing data in %s, element: %d' % (dirName, i))
                    continue
            except:
                print("Error loading data for protocol %s:"
                      % dirName)
                continue  # If something goes wrong here, we just carry on
            dataFile = dataFileHandle.read()
            self.devicesUsed = self.dataModel.getDevices(dataDirHandle)
            #print self.devicesUsed
            cmd = self.dataModel.getClampCommand(dataFile)
            data = self.dataModel.getClampPrimary(dataFile)
            self.dataMode = self.dataModel.getClampMode(data)
            self.holding = self.dataModel.getClampHoldingLevel(dataFileHandle)
            if 'LED-Blue' in self.devicesUsed.keys():
                LED_pulseTrainCommand = dataDirHandle.parent().info()['devices']['LED-Blue']['channels']['Command']
                LED_pulseTrainInfo = LED_pulseTrainCommand['waveGeneratorWidget']['stimuli']['PulseTrain']
                self.LEDInfo = {}
                for k in LED_pulseTrainInfo.keys():
                    if k in ['type']:
                        self.LEDInfo[k] = LED_pulseTrainInfo[k]
                    else:
                        self.LEDInfo[k] = LED_pulseTrainInfo[k]['value']
            if self.dataMode is None:
                self.dataMode = self.ICModes[0]  # set a default mode
            self.ctrl.PSPReversal_dataMode.setText(self.dataMode)
            # Assign scale factors for the different modes to display data rationally
            if self.dataMode in self.ICModes:
                self.cmdscaleFactor = 1e12
                self.cmdUnits = 'pA'
            elif self.dataMode in self.VCModes:
                self.cmdUnits = 'mV'
                self.cmdscaleFactor = 1e3
            else:  # data mode not known; plot as voltage
                self.cmdUnits = 'V'
                self.cmdscaleFactor = 1.0

            # only accept data in a particular range
            if self.ctrl.PSPReversal_IVLimits.isChecked():
                cval = self.cmdscaleFactor * sequenceValues[i]
                cmin = self.ctrl.PSPReversal_IVLimitMin.value()
                cmax = self.ctrl.PSPReversal_IVLimitMax.value()
                if cval < cmin or cval > cmax:
                    continue  # skip adding the data to the arrays
            # store primary channel data and read command amplitude
            info1 = data.infoCopy()
            self.traceTimes = np.append(self.traceTimes,
                                        info1[1]['startTime'])
            traces.append(data.view(np.ndarray))
            cmd_wave.append(cmd.view(np.ndarray))

            if len(sequenceValues) > 0:
                self.values.append(sequenceValues[i])
            else:
                self.values.append(cmd[len(cmd) / 2])
            i += 1
        print 'PSPReversal::loadFileRequested: Done loading files'
        self.ctrl.PSPReversal_Holding.setText('%.1f mV' % (float(self.holding) * 1e3))
        if traces is None or len(traces) == 0:
            print "PSPReversal::loadFileRequested: No data found in this run..."
            return False
        # put relative to the start
        self.traceTimes = self.traceTimes - self.traceTimes[0]
        traces = np.vstack(traces)
        cmd_wave = np.vstack(cmd_wave)
        self.cmd_wave = cmd_wave
        self.tx = np.array(cmd.xvals('Time'))
        commands = np.array(self.values)
        self.colorScale.setIntColorScale(0, i, maxValue=200)
        # set up the selection region correctly and
        # prepare IV curves and find spikes
        info = [
            {'name': 'Command', 'units': cmd.axisUnits(-1),
             'values': np.array(self.values)},
            data.infoCopy('Time'),
            data.infoCopy(-1)]
        traces = traces[:len(self.values)]
        self.traces = MetaArray(traces, info=info)
        sfreq = self.dataModel.getSampleRate(data)

        cmddata = cmd.view(np.ndarray)
        cmddiff = np.abs(cmddata[1:] - cmddata[:-1])
        if self.dataMode in self.ICModes:
            mindiff = 1e-12
        else:
            mindiff = 1e-4
        cmdtimes1 = np.argwhere(cmddiff >= mindiff)[:, 0]
        cmddiff2 = cmdtimes1[1:] - cmdtimes1[:-1]
        cmdtimes2 = np.argwhere(cmddiff2 > 1)[:, 0]
        if len(cmdtimes1) > 0 and len(cmdtimes2) > 0:
            cmdtimes = np.append(cmdtimes1[0], cmddiff2[cmdtimes2])
        else:  # just fake it
            cmdtimes = np.array([0.01, 0.1])
        if self.ctrl.PSPReversal_KeepT.isChecked() is False:
            self.tstart = cmd.xvals('Time')[cmdtimes[0]]
            self.tend = cmd.xvals('Time')[cmdtimes[1]] + self.tstart
            self.tdur = self.tend - self.tstart

            # build the list of command values that are used for the fitting
        cmdList = []
        for i in range(len(self.values)):
            cmdList.append('%8.3f %s' %
                           (self.cmdscaleFactor * self.values[i], self.cmdUnits))
        self.ctrl.PSPReversal_tauh_Commands.clear()
        self.ctrl.PSPReversal_tauh_Commands.addItems(cmdList)
        self.sampInterval = 1.0 / sfreq
        if self.ctrl.PSPReversal_KeepT.isChecked() is False:
            self.tstart += self.sampInterval
            self.tend += self.sampInterval
        if self.dataMode in self.ICModes:
            # for adaptation ratio:
            self.update_allAnalysis()
        if self.dataMode in self.VCModes:
            self.cmd = commands
            self.spikecount = np.zeros(len(np.array(self.values)))

        # and also plot
        self.plottraces()
        return True

    def fileInformation(self, dh):
        pass

    def fileCellProtocol(self):
        """
        fileCellProtocol breaks the current filename down and returns a
        tuple: (date, cell, protocol)

        last argument returned is the rest of the path...
        """
        (p0, proto) = os.path.split(self.filename)
        (p1, cell) = os.path.split(p0)
        (p2, slice) = os.path.split(p1)
        (p3, date) = os.path.split(p2)
        return (date, slice, cell, proto, p3)

    def plottraces(self):
        if self.ctrl.PSPReversal_KeepAnalysis.isChecked():
            self.keepAnalysisCount += 1
        else:
            self.keepAnalysisCount = 0  # always make sure is reset
            # this is the only way to reset iterators.
            self.colorList = itertools.cycle(self.colors)
            self.symbolList = itertools.cycle(self.symbols)
        self.makemap_symbols()

        ntr = self.traces.shape[0]
        self.data_plot.setDownsampling(auto=True, mode='mean')
        self.data_plot.setClipToView(True)
        for i in range(ntr):
            self.data_plot.plot(self.tx, self.traces[i],
                                pen=pg.intColor(i, ntr, maxValue=200),
            )
            self.cmd_plot.plot(self.tx, self.cmd_wave[i],
                               pen=pg.intColor(i, ntr, maxValue=200),
                               autoDownsample=True, downsampleMethod='mean')

        if self.dataMode in self.ICModes:
            self.label_up(self.data_plot, 'T (s)', 'V (V)', 'Data')
            self.label_up(self.cmd_plot, 'T (s)', 'I (%s)' % self.cmdUnits, 'Data')
        elif self.dataMode in self.VCModes:  # voltage clamp
            self.label_up(self.data_plot, 'T (s)', 'I (A)', 'Data')
            self.label_up(self.cmd_plot, 'T (s)', 'V (%s)' % self.cmdUnits, 'Data')
        else:  # mode is not known: plot both as V
            self.label_up(self.data_plot, 'T (s)', 'V (V)', 'Data')
            self.label_up(self.cmd_plot, 'T (s)', 'V (%s)' % self.cmdUnits, 'Data')

        self.setupRegions()

    def setupRegions(self):
        self.initialize_Regions()  # now create the analysis regions
        if self.ctrl.PSPReversal_KeepT.isChecked() is False:
            if 'LED-Blue' in self.devicesUsed:
                tdur1 = 0.1
                tstart1 = self.LEDInfo['start'] - tdur1
                tdur2 = self.LEDInfo['length'] * 5.  # go 5 times the duration.
                tstart2 = self.LEDInfo['start']
                if tstart2 + tdur2 > self.tend:
                    tdur2 = self.tend - tstart2  # restrict duration to end of the trace
            else:
                tstart1 = self.tstart
                tdur1 = self.tstart / 5.0
                tdur2 = self.tdur / 2.0
                tstart2 = self.tend - tdur2

            tend = self.tend - 0.001
            #
            self.regions['lrwin1']['region'].setRegion([tstart1,
                                                        tstart1 + tdur1])
            # steady state:
            self.regions['lrwin2']['region'].setRegion([tstart2,
                                                        tstart2 + tdur2])
            # self.lrtau.setRegion([self.tstart+(self.tdur/5.0)+0.005,
            #                      self.tend])
            self.regions['lrrmp']['region'].setRegion([1.e-4, self.tstart * 0.9])  # rmp window

        # leak is on voltage (or current), not times
        self.regions['lrleak']['region'].setRegion(
            [self.regions['lrleak']['start'].value(),  # self.ctrl.PSPReversal_LeakMin.value(),
             self.regions['lrleak']['stop'].value()])  #self.ctrl.PSPReversal_LeakMax.value()])
        for r in ['lrwin1', 'lrwin2', 'lrrmp']:
            self.regions[r]['region'].setBounds([0., np.max(self.tx)]) # limit regions to data

    def update_allAnalysis(self, region=None):
        """ update_allAnalysis re-reads the time parameters and counts the spikes
            and forces an update of all the analysis inthe process...
        """
        self.read_parameters(clear_flag=True, pw=True)
        self.count_spikes()

    def count_spikes(self):
        """
        count_spikes: Using the threshold set in the control panel, count the
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
        if self.spikesCounted:  # only do once for each set of traces
            return
        if self.keepAnalysisCount == 0:
            clear_flag = True
        else:
            clear_flag = False
        ntr = len(self.traces)
        self.spikecount = np.zeros(ntr)
        self.fsl = np.zeros(ntr)
        self.fisi = np.zeros(ntr)
        self.ar = np.zeros(ntr)
        self.nospk = range(0, len(self.traces))
        self.spk = np.zeros(ntr)
        if self.dataMode not in self.ICModes or self.tx is None:
            #print ('PSPReversal::count_spikes: Cannot count spikes, ' +
            #       'and dataMode is ', self.dataMode, 'and ICModes are: ', self.ICModes, 'tx is: ', self.tx)
            self.spikecount = []
            # self.fiPlot.plot(x=[], y=[], clear=clear_flag, pen='w',
            #                  symbolSize=6, symbolPen='b',
            #                  symbolBrush=(0, 0, 255, 200), symbol='s')
            # self.fslPlot.plot(x=[], y=[], pen='w', clear=clear_flag,
            #                   symbolSize=6, symbolPen='g',
            #                   symbolBrush=(0, 255, 0, 200), symbol='t')
            # self.fslPlot.plot(x=[], y=[], pen='w', symbolSize=6,
            #                   symbolPen='y',
            #                   symbolBrush=(255, 255, 0, 200), symbol='s')
            # self.ctrl.PSPReversal_AR.setText(u'%7.3f' % (ARmean))
            return
        minspk = 4
        maxspk = 10  # range of spike counts
        threshold = self.ctrl.PSPReversal_SpikeThreshold.value() * 1e-3
        # rmp = np.zeros(ntr)
        # # rmp is taken from the mean of all the baselines in the traces
        # self.Rmp = np.mean(rmp)

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
            self.fsl[i] = spike[0] - self.tstart
            if len(spike) > 1:
                self.fisi[i] = spike[1] - spike[0]
                # for Adaptation ratio analysis
            if len(spike) >= minspk and len(spike) <= maxspk:
                misi = np.mean(np.diff(spike[-3:]))
                self.ar[i] = misi / self.isi[i]
            (self.rmp[i], r2) = Utility.measure('mean', self.tx, self.traces[i],
                                                0.0, self.tstart)
        # iAR = np.where(ar > 0)
        # ARmean = np.mean(ar[iAR])  # only where we made the measurement
        # self.AdaptRatio = ARmean
        #self.ctrl.PSPReversal_AR.setText(u'%7.3f' % (ARmean))
        self.fisi = self.fisi * 1.0e3
        self.fsl = self.fsl * 1.0e3
        self.nospk = np.where(self.spikecount == 0)
        self.spk = np.where(self.spikecount > 0)
        self.update_SpikePlots()

    def printAnalysis(self):
        """
        Print the CCIV summary information (Cell, protocol, etc)
        Printing goes to the results window, where the data can be copied
        to another program like a spreadsheet.
        """
        (date, slice, cell, proto, p2) = self.fileCellProtocol()
        self.cell_summary(self.current_dirhandle)
        # The day summary may be missing elements, so we need to create dummies (dict is read-only)
        day={}
        for x in ['age', 'weight', 'sex']:  # check to see if these are filled out
            if x not in self.CellSummary.keys():
                day[x] = 'unknown'
            else:
                day[x] = self.CellSummary['Day'][x]
        for cond in ['ACSF', 'Internal', 'Temp']:
            if self.CellSummary[cond] == '':
                self.CellSummary[cond] = 'unknown'

        # format output in html
        rtxt = '<font face="monospace, courier">'  # use a monospaced font.
        rtxt += '<div style="white-space: pre;">'  # css to force repsect of spaces in text
        rtxt += ("{:^14s}\t{:^14s}\t{:^14s}<br>" .format
               ("Date", "Slice", "Cell"))
        rtxt += ("<b>{:^14s}\t{:^14s}\t{:^14s}</b><br>".format
               (date, slice, cell))
        rtxt += ('{:^8s}\t{:^8s}\t{:^8s}\t{:^8s}<br>'.format
               ('Temp', 'Age', 'Weight', 'Sex'))
        rtxt += ('{:^8s}\t{:^8s}\t{:^8s}\t{:^8s}<br>'.format
               ( self.CellSummary['Temp'], day['age'], day['weight'], day['sex']))
        rtxt += ('{:<8s}: {:<32s}<br>'.format('ACSF', self.CellSummary['ACSF']))
        rtxt += ('{:<8s}: {:<32s}<br>'.format('Internal', self.CellSummary['Internal']))
        rtxt += ('{:<8s}: <b>{:<32s}</b><br>'.format('Protocol', proto))
        rtxt += ('{:<8s}: [{:5.1f}-{:5.1f}{:2s}] mode: {:<12s}<br>'.format(
                'Win 1', self.regions['lrwin1']['start'].value(), self.regions['lrwin1']['stop'].value(),
               self.regions['lrwin1']['units'], self.regions['lrwin1']['mode'].currentText()))
        rtxt += ('{:<8s}: [{:5.1f}-{:5.1f}{:2s}] mode: {:<12s}<br>'.format(
                'Win 2', self.regions['lrwin2']['start'].value(), self.regions['lrwin2']['stop'].value(),
                self.regions['lrwin2']['units'], self.regions['lrwin2']['mode'].currentText(),
               ))
        vc = self.win2IV[0]
        im = self.win2IV[1]
        imsd = self.win2IV[2]
        p = np.polyfit(vc, im, 2)  # 2nd order polynomial
        jp = self.junction
        ho = float(self.holding) * 1e3
        rtxt += 'HP: {:5.1f} mV  JP: {:5.1f} mV<br>'.format(ho, jp)
        # find the roots
        a = p[0]
        b = p[1]
        c = p[2]
        r = np.sqrt(b ** 2 - 4 * a * c)
        reversal = {}
        reversal[0] = {'value': (-b + r) / (2 * a), 'valid': False}
        reversal[1] = {'value': (-b - r) / (2 * a), 'valid': False}
        rtxt += '<b>Erev: '
        anyrev = False
        for i in range(0, 2):  # print only the valid reversal values
            if -100. < reversal[i]['value'] < 40.:
                reversal[i]['valid'] = True
                rtxt += '{:12.1f} '.format(reversal[i]['value'] + jp + ho)
                anyrev = True
        if not anyrev:
            rtxt += '</b>None found (roots, no correction: {12.1f}<br>'.format(reversal[i]['value'])
        else:
            rtxt += ' mV</b><br>'
        rtxt += ('-' * 40) + '<br>'
        rtxt += '<b>IV</b><br>'
        rtxt += '<i>{:>8s} \t{:>9s} \t{:>9s}</i><br>'.format('mV', 'nA', 'SD')
        for i in range(len(vc)):
            rtxt += ('{:>9.1f} \t{:>9.3f} \t{:>9.3f}<br>'.format((vc[i] + jp + ho), im[i], imsd[i]))
        rtxt += ('-' * 40) + '<br></div></font>'
        #print (rtxt)
        self.results.resultsPSPReversal_text.setText(rtxt)


    def update_Tau(self, printWindow=True, whichTau=1):
        """
        Compute time constant (single exponential) from the
        onset of the response
        using lrwin2 window, and only the smallest 3 steps...
        """
        if not self.cmd:  # probably not ready yet to do the update.
            return
        if self.dataMode not in self.ICModes:  # only permit in IC
            return
        rgnpk = self.lrwin2.getRegion()
        Func = 'exp1'  # single exponential fit.
        Fits = Fitting.Fitting()
        initpars = [-60.0 * 1e-3, -5.0 * 1e-3, 10.0 * 1e-3]
        icmdneg = np.where(self.cmd < 0)
        maxcmd = np.min(self.cmd)
        ineg = np.where(self.cmd[icmdneg] >= maxcmd / 3)
        whichdata = ineg[0]
        itaucmd = self.cmd[ineg]
        whichaxis = 0

        (fpar, xf, yf, names) = Fits.FitRegion(whichdata, whichaxis,
                                               #self.traces.xvals('Time'),
                                               #self.traces.view(np.ndarray),
                                               self.tx,
                                               self.traces,
                                               dataType='xy',
                                               t0=rgnpk[0], t1=rgnpk[1],
                                               fitFunc=Func,
                                               fitPars=initpars,
                                               method='simplex')
        if fpar == []:
            print 'PSPReversal::update_Tau: Charging tau fitting failed - see log'
            return
        taus = []
        for j in range(0, fpar.shape[0]):
            outstr = ""
            taus.append(fpar[j][2])
            for i in range(0, len(names[j])):
                outstr = outstr + ('%s = %f, ' % (names[j][i], fpar[j][i]))
            if printWindow:
                print("FIT(%d, %.1f pA): %s " %
                      (whichdata[j], itaucmd[j] * 1e12, outstr))
        meantau = np.mean(taus)
        self.ctrl.PSPReversal_Tau.setText(u'%18.1f ms' % (meantau * 1.e3))
        self.tau = meantau
        tautext = 'Mean Tau: %8.1f'
        if printWindow:
            print tautext % (meantau * 1e3)

    def update_Tauh(self, printWindow=False):
        """ compute tau (single exponential) from the onset of the markers
            using lrtau window, and only for the step closest to the selected
            current level in the GUI window.

            Also compute the ratio of the sag from the peak (marker1) to the
            end of the trace (marker 2).
            Based on analysis in Fujino and Oertel, J. Neuroscience 2001,
            to type cells based on different Ih kinetics and magnitude.
        """
        return
        if self.ctrl.PSPReversal_showHide_lrtau.isChecked() is not True:
            return
        bovera = 0.0
        rgn = self.lrtau.getRegion()
        Func = 'exp1'  # single exponential fit to the whole region
        Fits = Fitting.Fitting()
        fitx = []
        fity = []
        initpars = [-80.0 * 1e-3, -10.0 * 1e-3, 50.0 * 1e-3]

        # find the current level that is closest to the target current
        s_target = self.ctrl.PSPReversal_tauh_Commands.currentIndex()
        itarget = self.values[s_target]  # retrive actual value from commands
        self.neg_cmd = itarget
        idiff = np.abs(np.array(self.cmd) - itarget)
        amin = np.argmin(idiff)  # amin appears to be the same as s_target
        # target trace (as selected in cmd drop-down list):
        target = self.traces[amin]
        # get Vrmp -  # rmp approximation.
        vrmp = np.median(target['Time': 0.0:self.tstart - 0.005]) * 1000.
        self.ctrl.PSPReversal_vrmp.setText('%8.2f' % (vrmp))
        self.neg_vrmp = vrmp
        # get peak and steady-state voltages
        pkRgn = self.lrwin2.getRegion()
        ssRgn = self.lrwin1.getRegion()
        vpk = target['Time': pkRgn[0]:pkRgn[1]].min() * 1000
        self.neg_pk = (vpk - vrmp) / 1000.
        vss = np.median(target['Time': ssRgn[0]:ssRgn[1]]) * 1000
        self.neg_ss = (vss - vrmp) / 1000.
        whichdata = [int(amin)]
        itaucmd = [self.cmd[amin]]
        rgnss = self.lrwin1.getRegion()
        self.ctrl.PSPReversal_tau2TStart.setValue(rgn[0] * 1.0e3)
        self.ctrl.PSPReversal_tau2TStop.setValue(rgn[1] * 1.0e3)
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
                                               self.traces.view(np.ndarray),
                                               dataType='2d',
                                               t0=rgn[0], t1=rgn[1],
                                               fitFunc=Func,
                                               fitPars=initpars)
        if fpar == []:
            print 'PSPReversal::update_Tauh: tau_h fitting failed - see log'
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
        s = np.shape(fpar)
        taus = []
        for j in range(0, s[0]):
            outstr = ""
            taus.append(fpar[j][2])
            for i in range(0, len(names[j])):
                outstr = outstr + ('%s = %f, ' %
                                   (names[j][i], fpar[j][i] * 1000.))
            if printWindow:
                print("Ih FIT(%d, %.1f pA): %s " %
                      (whichdata[j], itaucmd[j] * 1e12, outstr))
        meantau = np.mean(taus)
        self.ctrl.PSPReversal_Tauh.setText(u'%8.1f ms' % (meantau * 1.e3))
        self.tau2 = meantau
        tautext = 'Mean Tauh: %8.1f'
        bovera = (vss - vrmp) / (vpk - vrmp)
        self.ctrl.PSPReversal_Ih_ba.setText('%8.1f' % (bovera * 100.))
        self.ctrl.PSPReversal_win2Amp.setText('%8.2f' % (vss - vrmp))
        self.ctrl.PSPReversal_win1Amp.setText('%8.2f' % (vpk - vrmp))
        if bovera < 0.55 and self.tau2 < 0.015:  #
            self.ctrl.PSPReversal_FOType.setText('D Stellate')
        else:
            self.ctrl.PSPReversal_FOType.setText('T Stellate')
            # estimate of Gh:
        Gpk = itarget / self.neg_pk
        Gss = itarget / self.neg_ss
        self.Gh = Gss - Gpk
        self.ctrl.PSPReversal_Gh.setText('%8.2f nS' % (self.Gh * 1e9))

    def update_winAnalysis(self, region=None, clear=True, pw=False):
        """
        Compute the a current-voltage relationship from the selected time window

        Input parameters:
            region: which region of the linearRegion elements are used for
            the time window.

            clear: a boolean flag that originally allowed accumulation of plots
                    presently, ignored.
            pw: printwindow flag = current ignored.
        returns:
            nothing.
        modifies:
            ivss, yleak, ivss_cmd, cmd.

        The IV curve is only valid when there are no spikes detected in
            the window. In voltage-clamp mode, this is assumed to always
            be true.
            In current clamp mode, the results of the spike detection (count_spikes)
            are used to remove traces with spikes in them.
        The values in the curve are taken according to the "mode" of the window
            as selected in the gui. This can be mean, min, max, sum, or the largest of the
             abs(min) and max (as -abs(min)).
        Subtraction of one window from another is also possible - this currently only
            works in one direction: win1 can be subtracted from win2; if win1 has not been
            analyzed, then the subtraction will not be done.
        Alternation: if the data have been collected in an alternation mode,
            then the data is split into "on" and "off" groups, and the current-voltage
            relationship is computed for each group.
        We can also compute the input resistance (although this does not always make sense)
        For voltage clamp data, we can optionally remove the "leak" current.
        The resulting IV curve is plotted at the end of the analysis.
        """
        window = region
        region = 'lr' + window
        wincmd = window + 'cmd'
        winoff = window + 'off'
        winon = window + 'on'
        windowsd = window + 'std'
        winaltcmd = window + 'altcmd'
        winunordered = window + '_unordered'
        winlinfit = window + '_linfit'

        if region is None:
            return
        if self.traces is None:
            return

        # these will always be filled
        self.measure[window] = []
        self.measure[wincmd] = []
        # The next ones will only be set if the alt flag is on
        self.measure[winoff] = []
        self.measure[winon] = []
        self.measure[winaltcmd] = []
        self.measure[winunordered] = []
        self.measure[windowsd] = []


        mode = self.regions[region]['mode'].currentText()
        rgninfo = self.regions[region]['region'].getRegion()
        self.regions[region]['start'].setValue(rgninfo[0] * 1.0e3)  # report values to screen
        self.regions[region]['stop'].setValue(rgninfo[1] * 1.0e3)
        data1 = self.traces['Time': rgninfo[0]:rgninfo[1]]  # extract analysis region
        tx1 = ma.compressed(ma.masked_outside(self.tx, rgninfo[0], rgninfo[1]))  # time to match data1
        if window == 'win1': # check if win1 overlaps with win2, and select data
            r1 = rgninfo
            r2 = self.regions['lrwin2']['region'].getRegion()
            tx = ma.masked_inside(tx1, r2[0], r2[1])  #
            n_unmasked = ma.count(tx)
            if n_unmasked == 0:  # handle case where win1 is entirely inside win2
                print 'update_winAnalysis: Window 1 is inside Window 2: No analysis possible'
                return
            data1 = ma.array(data1, mask=ma.resize(ma.getmask(tx), data1.shape))
            self.txm = ma.compressed(tx)  # now compress tx as well

        if data1.shape[1] == 0 or data1.shape[0] == 1:
            print 'no data to analyze?'
            return  # skip it
        commands = np.array(self.values)  # get command levels
        print 'analyzing %s with mode %s' % (region, mode)
        if self.dataMode in self.ICModes:
            self.count_spikes()
        if mode in ['Mean-Win1', 'Sum-Win1']:
            if 'win1_unordered' not in self.measure.keys() or len(
                    self.measure['win1_unordered']) == 0:  # Window not analyzed yet, but needed: do it
                self.update_winAnalysis(region='win1')
        if mode == 'Min':
            self.measure[window] = data1.min(axis=1)
        elif mode == 'Max':
            self.measure[window] = data1.max(axis=1)
        elif mode == 'Mean' or mode is None:
            self.measure[window] = data1.mean(axis=1)
            self.measure[windowsd] = data1.std(axis=1)
        elif mode == 'Mean-Win1' and len(self.measure['win1_unordered']) == data1.shape[0]:
            self.measure[window] = data1.mean(axis=1) - self.measure[
                'win1_unordered']
            self.measure[windowsd] = data1.std(axis=1) - self.measure[
                'win1_unordered']
        elif mode in ['Mean-Linear', 'Mean-Poly2'] and window == 'win2':  # and self.txm.shape[0] == data1.shape[0]:
            fits = np.zeros(data1.shape)
            for j in range(data1.shape[0]):  # polyval only does 1d
                fits[j,:] = np.polyval(self.win1fits[:,j], tx1)
            self.measure[window] = np.mean(data1-fits, axis=1)
            self.measure[windowsd] = np.std(data1-fits, axis=1)

        elif mode == 'Sum':
            self.measure[window] = np.sum(data1, axis=1)
        elif mode == 'Sum-Win1' and len(self.measure['win1_unordered']) == data1.shape[0]:
            u = self.measure['win1_unordered']._data
            self.measure[window] = np.sum(data1 - u[:, np.newaxis], axis=1)
        elif mode == 'Abs':  # find largest regardless of the sign ('minormax')
            x1 = data1.min(axis=1)
            x2 = data1.max(axis=1)
            self.measure[window] = np.zeros(data1.shape[0])
            for i in range(data1.shape[0]):
                if -x1[i] > x2[i]:
                    self.measure[window][i] = x1[i]
                else:
                    self.measure[window][i] = x2[i]
        elif mode == 'Linear' and window == 'win1' :
            ntr = data1.shape[0]
            d1 = np.resize(data1.compressed(), (ntr, self.txm.shape[0]))
            p = np.polyfit(self.txm, d1.T, 1)
            self.win1fits = p
            self.measure[window] = data1.mean(axis=1)
            # fits = np.zeros((data1.shape[0], tx.shape[0]))
            # for j in range(data1.shape[0]):
            #     fits[j,:] = np.polyval(p[:,j], tx)
            #     if j == 0:
            #         fpl=pg.plot(tx1, data1[j,:])
            #     else:
            #         fpl.plot(tx1, data1[j,:])
            #     fpl.plot(tx, fits[j,:], pen=pg.mkPen({'color': "F00", 'width': 1}))

        elif mode == 'Poly2' and window == 'win1' :
            ntr = data1.shape[0]
            d1 = np.resize(data1.compressed(), (ntr, self.txm.shape[0]))
            p = np.polyfit(self.txm, d1.T, 2)
            self.win1fits = p
            self.measure[window] = data1.mean(axis=1)
            # fits = np.zeros((data1.shape[0], tx.shape[0]))
            # for j in range(data1.shape[0]):
            #     fits[j,:] = np.polyval(p[:,j], tx)
            #     if j == 0:
            #         fpl=pg.plot(tx1, data1[j,:])
            #     else:
            #         fpl.plot(tx1, data1[j,:])
            #     fpl.plot(tx, fits[j,:], pen=pg.mkPen({'color': "F00", 'width': 1}))

        else:
            print 'update_winAnalysis: Mode %s is not recognized' % mode
            return
            #self.measure['win1'] = np.array([np.max(x1[i], x2[i]) for i in range(data2.shape[0]])
            #self.measure['win1'] = np.maximum(np.fabs(data2.min(axis=1)), data2.max(axis=1))
        if self.ctrl.PSPReversal_SubBaseline.isChecked():
            self.measure[window] = self.measure[window] - self.measure['rmp']
        if len(self.nospk) >= 1 and self.dataMode in self.ICModes:
            # Steady-state IV where there are no spikes
            print 'update_winAnalysis: Removing traces with spikes from analysis'
            self.measure[window] = self.measure[window][self.nospk]
            if len(self.measure[windowsd]) > 0:
                self.measure[windowsd] = self.measure[windowsd][self.nsopk]
            self.measure[wincmd] = commands[self.nospk]
            self.cmd = commands[self.nospk]
            # compute Rin from the SS IV:
            if len(self.cmd) > 0 and len(self.measure[window]) > 0:
                self.Rin = np.max(np.diff
                                  (self.measure[window]) / np.diff(self.cmd))
                self.ctrl.PSPReversal_Rin.setText(u'%9.1f M\u03A9'
                                                  % (self.Rin * 1.0e-6))
            else:
                self.ctrl.PSPReversal_Rin.setText(u'No valid points')
        else:
            self.measure[wincmd] = commands
            self.cmd = commands
            self.measure['leak'] = np.zeros(len(self.measure[window]))
        self.measure[winunordered] = self.measure[window]

        # now separate the data into alternation groups, then sort by command level
        if self.alternation and window == 'win2':
            print 'in alternation'
            nm = len(self.measure[window])  # get the number of measurements
            xoff = range(0, nm, 2)  # really should get this from loadrequestedfile
            xon = range(1, nm, 2)
            measure_voff = self.measure[wincmd][xoff]  # onset same as the other
            measure_von = self.measure[wincmd][xon]
            measure_off = self.measure[window][xoff]
            measure_on = self.measure[window][xon]
            vcs_on = np.argsort(measure_von)
            vcs_off = np.argsort(measure_voff)
            measure_von = measure_von[vcs_on]
            measure_off = measure_off[vcs_off]
            measure_on = measure_on[vcs_on]
            self.measure[winon] = np.array(measure_on)
            self.measure[winoff] = np.array(measure_off)
            self.measure[winaltcmd] = np.array(measure_von)
            # if len(self.measure[windowsd]) > 0:
            #     measure_on_sd = self.measure[windowsd][xon]
            #     measure_on_sd = measure_on_sd[vcs_on]
            #     self.measure[winonsd] = np.array(measure_on_sd)
        else:
            isort = np.argsort(self.measure[wincmd])  # get sort order for commands
            self.measure[wincmd] = self.measure[wincmd][isort]  # sort the command values
            self.measure[window] = self.measure[window][isort]  # sort the data in the window
            # if len(self.measure[windowsd]) > 0:
            #     self.measure[windowsd] = self.measure[windowsd][isort]
            self.update_IVPlot()
        self.update_cmdTimePlot(wincmd)

    def regions_exclusive(self):
        """
        Find the areas in win1 that are exclusive of win 2.
        If there is no overlap, returns win2
        """

    def update_cmdTimePlot(self, wincmd):
        (pen, filledbrush, emptybrush, symbol, n, clear_flag) = self.map_symbol()

        self.cmdPlot.plot(x=self.traceTimes, y=self.cmd, clear=clear_flag,
                          symbolSize=6,
                          symbol=symbol, pen=pen,
                          symbolPen=pen, symbolBrush=filledbrush)


    def update_rmpAnalysis(self, region=None, clear=True, pw=False):
        """
            Compute the RMP over time/commands from the selected window
        """
        if self.traces is None:
            return
        rgnrmp = self.regions['lrrmp']['region'].getRegion()
        self.regions['lrrmp']['start'].setValue(rgnrmp[0] * 1.0e3)
        self.regions['lrrmp']['stop'].setValue(rgnrmp[1] * 1.0e3)
        data1 = self.traces['Time': rgnrmp[0]:rgnrmp[1]]
        data1 = data1.view(np.ndarray)
        self.measure['rmp'] = []
        commands = np.array(self.values)
        self.measure['rmp'] = data1.mean(axis=1)  # all traces
        self.measure['rmpcmd'] = commands
        self.cmd = commands
        self.averageRMP = np.mean(self.measure['rmp'])
        self.update_RMPPlot()

    def makemap_symbols(self):
        """
        Given the current state of things, (keep analysis count, for example),
        return a tuple of pen, fill color, empty color, a symbol from
        our lists, and a clear_flag. Used to overplot different data.
        """
        n = self.keepAnalysisCount
        pen = self.colorList.next()
        filledbrush = pen
        emptybrush = None
        symbol = self.symbolList.next()
        if n == 0:
            clear_flag = True
        else:
            clear_flag = False
        self.currentSymDict = {'pen': pen, 'filledbrush': filledbrush,
                               'emptybrush': emptybrush, 'symbol': symbol,
                               'n': n, 'clear_flag': clear_flag}

    def map_symbol(self):
        cd = self.currentSymDict
        if cd['filledbrush'] == 'w':
            cd['filledbrush'] = pg.mkBrush((128, 128, 128))
        if cd['pen'] == 'w':
            cd['pen'] = pg.mkPen((128, 128, 128))
        self.lastSymbol = (cd['pen'], cd['filledbrush'],
                           cd['emptybrush'], cd['symbol'],
                           cd['n'], cd['clear_flag'])
        return self.lastSymbol

    def update_IVPlot(self):
        """
            Draw the peak and steady-sate IV to the I-V window
            Note: x axis is always I or V, y axis V or I
        """
        if self.ctrl.PSPReversal_KeepAnalysis.isChecked() is False:
            self.IV_plot.clear()
        (pen, filledbrush, emptybrush, symbol, n, clear_flag) = \
            self.map_symbol()
        if self.dataMode in self.ICModes:
            self.label_up(self.IV_plot, 'I (pA)', 'V (mV)', 'I-V (CC)')
            if (len(self.measure['win1']) > 0 and
                    self.regions['lrwin1']['state'].isChecked()):
                self.IV_plot.plot(self.measure['win1cmd'] * 1e12, self.measure['win1'] * 1e3,
                                  symbol=symbol, pen=pen,
                                  symbolSize=6, symbolPen=pen,
                                  symbolBrush=emptybrush)
            if (len(self.measure['win2']) > 0 and
                    self.regions['lrwin2']['state'].isChecked()):
                self.IV_plot.plot(self.measure['win2cmd'] * 1e12, self.measure['win2'] * 1e3,
                                  symbol=symbol, pen=pen,
                                  symbolSize=6, symbolPen=pen,
                                  symbolBrush=filledbrush)
        if self.dataMode in self.VCModes:
            self.label_up(self.IV_plot, 'V (mV)', 'I (nA)', 'I-V (VC)')
            if (len(self.measure['win1']) > 0 and
                    self.regions['lrwin1']['state'].isChecked()):
                self.IV_plot.plot(self.measure['win1cmd'] * 1e3, self.measure['win1'] * 1e9,
                                  symbol=symbol, pen=pen,
                                  symbolSize=6, symbolPen=pen,
                                  symbolBrush=emptybrush)
            if (len(self.measure['win2']) > 0 and
                    self.regions['lrwin2']['state'].isChecked()):
                if not self.alternation:
                    self.IV_plot.plot(self.measure['win2cmd'] * 1e3, self.measure['win2'] * 1e9,
                                      symbol=symbol, pen=pen,
                                      symbolSize=6, symbolPen=pen,
                                      symbolBrush=filledbrush)
                else:
                    if len(self.measure['win2altcmd']) > 0:
                        self.IV_plot.plot(self.measure['win2altcmd'] * 1e3, self.measure['win2on'] * 1e9,
                                          symbol=symbol, pen=pen,
                                          symbolSize=6, symbolPen=pen,
                                          symbolBrush=filledbrush)
                        # plot mean
                        m = self.measure['win2altcmd']
                        print 'nrepc: ', self.nrepc
                        calt = m.reshape(m.shape[0] / self.nrepc, self.nrepc)
                        vc = calt.mean(axis=1)
                        m2 = self.measure['win2on']
                        ialt = m2.reshape(m2.shape[0] / self.nrepc, self.nrepc)
                        im = ialt.mean(axis=1)
                        imsd = ialt.std(axis=1)
                        avPen = pg.mkPen({'color': "F00", 'width': 2})
                        self.IV_plot.plot(vc * 1e3, im * 1e9,
                                          symbol='s', pen=avPen,
                                          symbolSize=6, symbolPen=avPen,
                                          symbolBrush=filledbrush)
                        self.win2IV = [vc * 1e3, im * 1e9, imsd*1e9]



    def update_RMPPlot(self):
        """
            Draw the RMP to the I-V window
            Note: x axis can be I, T, or  # spikes
        """
        if self.ctrl.PSPReversal_KeepAnalysis.isChecked() is False:
            self.RMP_plot.clear()
        if len(self.measure['rmp']) > 0:
            (pen, filledbrush, emptybrush, symbol, n, clear_flag) = \
                self.map_symbol()
            mode = self.ctrl.PSPReversal_RMPMode.currentText()
            if self.dataMode in self.ICModes:
                sf = 1e3
                self.RMP_plot.setLabel('left', 'V mV')
            else:
                sf = 1e12
                self.RMP_plot.setLabel('left', 'I (pA)')
            if mode == 'T (s)':
                self.RMP_plot.plot(self.traceTimes, sf * np.array(self.measure['rmp']),
                                   symbol=symbol, pen=pen,
                                   symbolSize=6, symbolPen=pen,
                                   symbolBrush=filledbrush)
                self.RMP_plot.setLabel('bottom', 'T (s)')
            elif mode == 'I (pA)':
                self.RMP_plot.plot(self.cmd,
                                   1.e3 * np.array(self.measure['rmp']), symbolSize=6,
                                   symbol=symbol, pen=pen,
                                   symbolPen=pen, symbolBrush=filledbrush)
                self.RMP_plot.setLabel('bottom', 'I (pA)')
            elif mode == 'Sp (#/s)':
                self.RMP_plot.plot(self.spikecount,
                                   1.e3 * np.array(self.measure['rmp']), symbolSize=6,
                                   symbol=symbol, pen=pen,
                                   symbolPen=pen, symbolBrush=emptybrush)
                self.RMP_plot.setLabel('bottom', 'Spikes')
            else:
                print 'Selected RMP x axis mode not known: %s' % mode

    def update_SpikePlots(self):
        """
            Draw the spike counts to the FI and FSL windows
            Note: x axis can be I, T, or  # spikes
        """
        if self.dataMode in self.VCModes:
            #self.cmdPlot.clear()  # no plots of spikes in VC
            #self.fslPlot.clear()
            return
        (pen, filledbrush, emptybrush, symbol, n, clear_flag) = self.map_symbol()
        mode = self.ctrl.PSPReversal_RMPMode.currentIndex()  # get x axis mode
        commands = np.array(self.values)
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
            xfi = commands * iscale
            xfsl = self.spcmd * iscale
            xlabel = 'I (pA)'
        elif mode == 2:  # plot with spike counts as x
            xfi = self.spikecount
            xfsl = self.spikecount
            select = range(len(self.spikecount))
            xlabel = 'Spikes (N)'
        else:
            return  # mode not in available list
            # self.fiPlot.plot(x=xfi, y=self.spikecount, clear=clear_flag,
            #                  symbolSize=6,
            #                  symbol=symbol, pen=pen,
            #                  symbolPen=pen, symbolBrush=filledbrush)
            # self.fslPlot.plot(x=xfsl, y=self.fsl[select]*yfslsc, clear=clear_flag,
            #                   symbolSize=6,
            #                   symbol=symbol, pen=pen,
            #                   symbolPen=pen, symbolBrush=filledbrush)
            # self.fslPlot.plot(x=xfsl, y=self.fisi[select]*yfslsc, symbolSize=6,
            #                   symbol=symbol, pen=pen,
            #                   symbolPen=pen, symbolBrush=emptybrush)
            # if len(xfsl) > 0:
            #     self.fslPlot.setXRange(0.0, np.max(xfsl))
            # # self.fiPlot.setLabel('bottom', xlabel)
            # self.fslPlot.setLabel('bottom', xlabel)

    def read_parameters(self, clear_flag=False, pw=False):
        """
        Read the parameter window entries, set the lr regions, and do an
        update on the analysis
        """
        (pen, filledbrush, emptybrush, symbol, n, clear_flag) = self.map_symbol()
        # update RMP first as we might use it for the others.
        if self.regions['lrrmp']['state'].isChecked():
            rgnx1 = self.regions['lrrmp']['start'].value() / 1.0e3
            rgnx2 = self.regions['lrrmp']['start'].value() / 1.0e3
            self.regions['lrrmp']['region'].setRegion([rgnx1, rgnx2])
            self.update_rmpAnalysis(clear=clear_flag, pw=pw)

        if self.regions['lrwin1']['state'].isChecked():
            rgnx1 = self.regions['lrwin1']['start'].value() / 1.0e3
            rgnx2 = self.regions['lrwin1']['stop'].value() / 1.0e3
            self.regions['lrwin1']['region'].setRegion([rgnx1, rgnx2])
            self.update_winAnalysis(region='win1', clear=clear_flag, pw=pw)

        if self.regions['lrwin2']['state'].isChecked():
            rgnx1 = self.regions['lrwin2']['start'].value() / 1.0e3
            rgnx2 = self.regions['lrwin2']['stop'].value() / 1.0e3
            self.regions['lrwin2']['region'].setRegion([rgnx1, rgnx2])
            self.update_winAnalysis(region='win2', clear=clear_flag, pw=pw)

        if self.regions['lrleak']['state'].isChecked():
            rgnx1 = self.regions['lrleak']['start'].value() / 1.0e3
            rgnx2 = self.regions['lrleak']['stop'].value() / 1.0e3
            self.regions['lrleak']['region'].setRegion([rgnx1, rgnx2])
            self.update_winAnalysis(region='win1')
            self.update_winAnalysis(region='win2')

        # if self.ctrl.PSPReversal_showHide_lrtau.isChecked():
        #     # include tau in the list... if the tool is selected
        #     self.update_Tauh()

        if self.regions['lrwin1']['mode'].currentIndexChanged:
            self.update_winAnalysis(region='win1')

        if self.regions['lrwin2']['mode'].currentIndexChanged:
            self.update_winAnalysis(region='win2')

    def dbstore_clicked(self):
        """
        Store data into the current database for further analysis
        """
        self.update_allAnalysis()
        db = self._host_.dm.currentDatabase()
        table = 'DirTable_Cell'
        columns = OrderedDict([
            ('PSPReversal_rmp', 'real'),
            ('PSPReversal_rinp', 'real'),
            ('PSPReversal_taum', 'real'),
            ('PSPReversal_neg_cmd', 'real'),
            ('PSPReversal_neg_pk', 'real'),
            ('PSPReversal_neg_ss', 'real'),
            ('PSPReversal_h_tau', 'real'),
            ('PSPReversal_h_g', 'real'),
        ])

        rec = {
            'PSPReversal_rmp': self.neg_vrmp / 1000.,
            'PSPReversal_rinp': self.Rin,
            'PSPReversal_taum': self.tau,
            'PSPReversal_neg_cmd': self.neg_cmd,
            'PSPReversal_neg_pk': self.neg_pk,
            'PSPReversal_neg_ss': self.neg_ss,
            'PSPReversal_h_tau': self.tau2,
            'PSPReversal_h_g': self.Gh,
        }

        with db.transaction():
            # Add columns if needed
            if 'PSPReversal_rmp' not in db.tableSchema(table):
                for col, typ in columns.items():
                    db.addColumn(table, col, typ)

            db.update(table, rec, where={'Dir': self.current_dirhandle.parent()})
        print "updated record for ", self.current_dirhandle.name()

    #---- Helpers ----
    # Some of these would normally live in a pyqtgraph-related module, but are
    # just stuck here to get the job done.
    #
    def label_up(self, plot, xtext, ytext, title):
        """helper to label up the plot"""
        plot.setLabel('bottom', xtext)
        plot.setLabel('left', ytext)
        plot.setTitle(title)

