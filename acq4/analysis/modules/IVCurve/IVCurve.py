# -*- coding: utf-8 -*-
"""
IVCurve: Analysis module that analyzes current-voltage and firing
relationships from current clamp data.
This is part of Acq4

Paul B. Manis, Ph.D.
2011-2013.

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

from acq4.analysis.AnalysisModule import AnalysisModule
import acq4.pyqtgraph as pg
from acq4.util.metaarray import MetaArray
import acq4.util.matplotlibexporter as matplotlibexporter
import acq4.analysis.tools.Utility as Utility  # pbm's utilities...
import acq4.analysis.tools.Fitting as Fitting  # pbm's fitting stuff...
import ctrlTemplate


# noinspection PyPep8
class IVCurve(AnalysisModule):
    """
    IVCurve is an Analysis Module for Acq4.

    IVCurve performs analyses of current-voltage relationships in
    electrophysiology experiments. The module is interactive, and is primarily
    designed to allow a preliminary examination of data collected in current clamp and voltage clamp.
    Results analyzed include:
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

        self.loaded = None
        self.filename = None
        self.dirsSet = None
        self.lrss_flag = True  # show is default
        self.lrpk_flag = True
        self.rmp_flag = True
        self.lrtau_flag = False
        self.regions_exist = False
        self.fit_curve = None
        self.fitted_data = None
        self.regions_exist = False
        self.regions = {}
        self.tx = None
        self.keep_analysis_count = 0
        self.colors = ['w', 'g', 'b', 'r', 'y', 'c']
        self.symbols = ['o', 's', 't', 'd', '+']
        self.color_list = itertools.cycle(self.colors)
        self.symbol_list = itertools.cycle(self.symbols)
        self.script_header = False
        self.data_mode = 'IC'  # analysis depends on the type of data we have.
        self.ic_modes = ['IC', 'CC', 'IClamp', 'ic', 'I-Clamp Fast', 'I-Clamp Slow']
        self.vc_modes = ['VC', 'VClamp', 'vc']  # list of VC modes

        # --------------graphical elements-----------------
        self._sizeHint = (1280, 900)  # try to establish size of window
        self.ctrlWidget = QtGui.QWidget()
        self.ctrl = ctrlTemplate.Ui_Form()
        self.ctrl.setupUi(self.ctrlWidget)
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
             {'type': 'fileInput', 'size': (170, 50), 'host': self}),
            ('Parameters',
             {'type': 'ctrl', 'object': self.ctrlWidget, 'host': self,
              'size': (160, 700)}),
            ('Plots',
             {'type': 'ctrl', 'object': self.widget, 'pos': ('right',),
              'size': (400, 700)}),
        ])
        self.initializeElements()
        self.file_loader_instance = self.getElement('File Loader', create=True)
        # grab input form the "Ctrl" window
        self.ctrl.IVCurve_Update.clicked.connect(self.updateAnalysis)
        self.ctrl.IVCurve_PrintResults.clicked.connect(self.printAnalysis)
        if not matplotlibexporter.HAVE_MPL:
            self.ctrl.IVCurve_MPLExport.setEnabled = False  # make button inactive
        #        self.ctrl.IVCurve_MPLExport.clicked.connect(self.matplotlibExport)
        else:
            self.ctrl.IVCurve_MPLExport.clicked.connect(
                functools.partial(matplotlibexporter.matplotlibExport, gridlayout=self.gridLayout,
                                  title=self.filename))
        self.ctrl.IVCurve_KeepAnalysis.clicked.connect(self.resetKeepAnalysis)
        self.ctrl.IVCurve_getFileInfo.clicked.connect(self.get_file_information)
        [self.ctrl.IVCurve_RMPMode.currentIndexChanged.connect(x)
         for x in [self.update_rmpAnalysis, self.countSpikes]]
        self.ctrl.dbStoreBtn.clicked.connect(self.dbStoreClicked)
        self.clear_results()
        self.layout = self.getElement('Plots', create=True)

        # instantiate the graphs using a gridLayout (also facilitates matplotlib export; see export routine below)
        self.data_plot = pg.PlotWidget()
        self.gridLayout.addWidget(self.data_plot, 0, 0, 3, 1)
        self.label_up(self.data_plot, 'T (s)', 'V (V)', 'Data')

        self.cmd_plot = pg.PlotWidget()
        self.gridLayout.addWidget(self.cmd_plot, 3, 0, 1, 1)
        self.label_up(self.cmd_plot, 'T (s)', 'I (A)', 'Command')

        self.RMP_plot = pg.PlotWidget()
        self.gridLayout.addWidget(self.RMP_plot, 1, 1, 1, 1)
        self.label_up(self.RMP_plot, 'T (s)', 'V (mV)', 'RMP')

        self.fiPlot = pg.PlotWidget()
        self.gridLayout.addWidget(self.fiPlot, 2, 1, 1, 1)
        self.label_up(self.fiPlot, 'I (pA)', 'Spikes (#)', 'F-I')

        self.fslPlot = pg.PlotWidget()
        self.gridLayout.addWidget(self.fslPlot, 3, 1, 1, 1)
        self.label_up(self.fslPlot, 'I (pA)', 'Fsl/Fisi (ms)', 'FSL/FISI')

        self.IV_plot = pg.PlotWidget()
        self.gridLayout.addWidget(self.IV_plot, 0, 1, 1, 1)
        self.label_up(self.IV_plot, 'I (pA)', 'V (V)', 'I-V')
        for row, s in enumerate([20, 10, 10, 10]):
            self.gridLayout.setRowStretch(row, s)

            #    self.tailPlot = pg.PlotWidget()
            #    self.gridLayout.addWidget(self.fslPlot, 3, 1, 1, 1)
            #    self.label_up(self.tailPlot, 'V (V)', 'I (A)', 'Tail Current')

            # Add a color scale
        self.color_scale = pg.GradientLegend((20, 150), (-10, -10))
        self.data_plot.scene().addItem(self.color_scale)
        self.ctrl.pushButton.clicked.connect(functools.partial(self.initialize_regions,
                                                               reset=True))

    def clear_results(self):
        """
        clear results resets variables.

        This is typically needed every time a new data set is loaded.
        """
        self.filename = ''
        self.r_in = 0.0
        self.tau = 0.0
        self.adapt_ratio = 0.0
        self.traces = None
        self.spikes_counted = False
        self.nospk = []
        self.spk = []
        self.cmd = []
        self.Sequence = ''
        self.ivss = []  # steady-state IV (window 2)
        self.ivpk = []  # peak IV (window 1)
        self.traces = []
        self.fsl = []  # first spike latency
        self.fisi = []  # first isi
        self.rmp = []  # resting membrane potential during sequence
        self.analysis_summary = {}
        self.script_header = True

    def resetKeepAnalysis(self):
        self.keep_analysis_count = 0  # reset counter.

    def show_or_hide(self, lrregion=None, forcestate=None):
        """
        Show or hide specific regions in the display
        :param lrregion: name of the region ('lrwin0', etc)
        :param forcestate: set True to force the show status
        :return:
        """
        if lrregion is None:
            print('PSPReversal:show_or_hide:: lrregion is {:<s}'.format(lrregion))
            return
        region = self.regions[lrregion]
        if forcestate is not None:
            if forcestate:
                region['region'].show()
                region['state'].setChecked(QtCore.Qt.Checked)
                region['shstate'] = True
            else:
                region['region'].hide()
                region['state'].setChecked(QtCore.Qt.Unchecked)
                region['shstate'] = False
        else:
            if not region['shstate']:
                region['region'].show()
                region['state'].setChecked(QtCore.Qt.Checked)
                region['shstate'] = True
            else:
                region['region'].hide()
                region['state'].setChecked(QtCore.Qt.Unchecked)
                region['shstate'] = False

    def initialize_regions(self, reset=False):
        """
        initialize_regions sets the linear regions on the displayed data

        Here we create the analysis regions in the plot. However, this should
        NOT happen until the plot has been created
        Note the the information about each region is held in a dictionary,
        which for each region has a dictionary that accesses the UI and class
        methods for that region. This later simplifies the code and reduces
        repetitive sections.
        """
        # hold all the linear regions in a dictionary
        if not self.regions_exist:
            print 'initializing regions'
            self.regions['lrleak'] = {'name': 'leak',  # use a "leak" window
                                      'region': pg.LinearRegionItem([0, 1],
                                                                    brush=pg.mkBrush(255, 255, 0, 50.)),
                                      'plot': self.IV_plot,
                                      'state': self.ctrl.IVCurve_subLeak,
                                      'shstate': False,  # keep internal copy of the state
                                      'mode': self.ctrl.IVCurve_subLeak,
                                      'start': self.ctrl.IVCurve_LeakMin,
                                      'stop': self.ctrl.IVCurve_LeakMax,
                                      'updater': self.updateAnalysis,
                                      'units': 'pA'}
            self.ctrl.IVCurve_subLeak.region = self.regions['lrleak']['region']  # save region with checkbox
            self.regions['lrwin0'] = {'name': 'win0',  # peak window
                                      'region': pg.LinearRegionItem([0, 1],
                                                                    brush=pg.mkBrush(0, 255, 0, 50.)),
                                      'plot': self.data_plot,
                                      'state': self.ctrl.IVCurve_showHide_lrpk,
                                      'shstate': True,  # keep internal copy of the state
                                      'mode': None,
                                      'start': self.ctrl.IVCurve_pkTStart,
                                      'stop': self.ctrl.IVCurve_pkTStop,
                                      'updater': self.updateAnalysis,
                                      'units': 'ms'}
            self.ctrl.IVCurve_showHide_lrpk.region = self.regions['lrwin0']['region']  # save region with checkbox
            self.regions['lrwin1'] = {'name': 'win2',  # ss window
                                      'region': pg.LinearRegionItem([0, 1],
                                                                    brush=pg.mkBrush(0, 0, 255, 50.)),
                                      'plot': self.data_plot,
                                      'state': self.ctrl.IVCurve_showHide_lrss,
                                      'shstate': True,  # keep internal copy of the state
                                      'mode': None,
                                      'start': self.ctrl.IVCurve_ssTStart,
                                      'stop': self.ctrl.IVCurve_ssTStop,
                                      'updater': self.updateAnalysis,
                                      'units': 'ms'}
            self.ctrl.IVCurve_showHide_lrss.region = self.regions['lrwin1']['region']  # save region with checkbox
            # self.lrtau = pg.LinearRegionItem([0, 1],
            # brush=pg.mkBrush(255, 0, 0, 50.))
            self.regions['lrrmp'] = {'name': 'rmp',
                                     'region': pg.LinearRegionItem([0, 1],
                                                                   brush=pg.mkBrush
                                                                   (255, 255, 0, 25.)),
                                     'plot': self.data_plot,
                                     'state': self.ctrl.IVCurve_showHide_lrrmp,
                                     'shstate': True,  # keep internal copy of the state
                                     'mode': None,
                                     'start': self.ctrl.IVCurve_rmpTStart,
                                     'stop': self.ctrl.IVCurve_rmpTStop,
                                     'updater': self.update_rmpAnalysis,
                                     'units': 'ms'}
            self.ctrl.IVCurve_showHide_lrrmp.region = self.regions['lrrmp']['region']  # save region with checkbox
            # establish that measurement is on top, exclusion is next, and reference is on bottom
            self.regions['lrtau'] = {'name': 'tau',
                                     'region': pg.LinearRegionItem([0, 1],
                                                                   brush=pg.mkBrush
                                                                   (255, 255, 0, 25.)),
                                     'plot': self.data_plot,
                                     'state': self.ctrl.IVCurve_showHide_lrtau,
                                     'shstate': False,  # keep internal copy of the state
                                     'mode': None,
                                     'start': self.ctrl.IVCurve_tau2TStart,
                                     'stop': self.ctrl.IVCurve_tau2TStop,
                                     'updater': self.update_Tauh(),
                                     'units': 'ms'}
            self.ctrl.IVCurve_showHide_lrtau.region = self.regions['lrtau']['region']  # save region with checkbox

            self.regions['lrwin0']['region'].setZValue(500)
            self.regions['lrwin1']['region'].setZValue(100)
            self.regions['lrtau']['region'].setZValue(1000)
            self.regions['lrrmp']['region'].setZValue(1000)
            self.regions['lrleak']['region'].setZValue(1000)

            for regkey, reg in self.regions.items():  # initialize region states
                self.show_or_hide(lrregion=regkey, forcestate=reg['shstate'])

            for regkey, reg in self.regions.items():
                reg['plot'].addItem(reg['region'])
                reg['state'].clicked.connect(functools.partial(self.show_or_hide,
                                                               lrregion=regkey))
                if reg['updater'] is not None:
                    reg['region'].sigRegionChangeFinished.connect(
                        functools.partial(reg['updater'], region=reg['name']))
                    # if self.regions[reg]['mode'] is not None:
                    #     self.regions[reg]['mode'].currentIndexChanged.connect(self.interactive_analysis)
        if reset:
            for regkey, reg in self.regions.items():  # initialize region states
                self.show_or_hide(lrregion=regkey, forcestate=reg['shstate'])
        for reg in self.regions.itervalues():
            for s in ['start', 'stop']:
                reg[s].setSuffix(' ' + reg['units'])
        self.regions_exist = True

    def get_file_information(self, default_dh=None):
        """
        get_file_information reads the sequence information from the
        currently selected data file

        Two-dimensional sequences are supported.
        :return nothing:
        """
        dh = self.file_loader_instance.selectedFiles()
        if len(dh) == 0:  # when using scripts, the fileloader may not know...
            if default_dh is not None:
                dh = default_dh
            else:
                return
        dh = dh[0]  # only the first file
        self.sequence = self.dataModel.listSequenceParams(dh)
        keys = self.sequence.keys()
        leftseq = [str(x) for x in self.sequence[keys[0]]]
        if len(keys) > 1:
            rightseq = [str(x) for x in self.sequence[keys[1]]]
        else:
            rightseq = []
        leftseq.insert(0, 'All')
        rightseq.insert(0, 'All')
        self.ctrl.IVCurve_Sequence1.clear()
        self.ctrl.IVCurve_Sequence2.clear()
        self.ctrl.IVCurve_Sequence1.addItems(leftseq)
        self.ctrl.IVCurve_Sequence2.addItems(rightseq)

    def cell_summary(self, dh):
        """
        cell_summary generates a dictionary of information about the cell
        for the selected directory handle (usually a protocol; could be a file)
        :param dh: the directory handle for the data, as passed to loadFileRequested
        :return nothing:
        """
        # other info into a dictionary
        self.analysis_summary['Day'] = self.dataModel.getDayInfo(dh)
        self.analysis_summary['Slice'] = self.dataModel.getSliceInfo(dh)
        self.analysis_summary['Cell'] = self.dataModel.getCellInfo(dh)
        self.analysis_summary['ACSF'] = self.dataModel.getACSF(dh)
        self.analysis_summary['Internal'] = self.dataModel.getInternalSoln(dh)
        self.analysis_summary['Temperature'] = self.dataModel.getTemp(dh)
        self.analysis_summary['CellType'] = self.dataModel.getCellType(dh)
        today = self.analysis_summary['Day']
        print today.keys()
        if 'species' in today.keys():
          self.analysis_summary['Species'] = today['species']
        if 'age' in today.keys():
          self.analysis_summary['Age'] = today['age']
        if 'sex' in today.keys():
          self.analysis_summary['Sex'] = today['sex']
        if 'weight' in today.keys():
          self.analysis_summary['Weight'] = today['weight']
        if 'temperature' in today.keys():
          self.analysis_summary['Temperature'] = today['temperature']
        self.analysis_summary['Description'] = today['description']

        if self.analysis_summary['Cell'] is not None:
            ct = self.analysis_summary['Cell']['__timestamp__']
        else:
            ct = 0.
        pt = dh.info()['__timestamp__']
        self.analysis_summary['ElapsedTime'] = pt - ct  # save elapsed time between cell opening and protocol start
        (date, sliceid, cell, proto, p3) = self.file_cell_protocol()
        self.analysis_summary['CellID'] = os.path.join(date, sliceid, cell)  # use this as the ID for the cell later on
        self.analysis_summary['Protocol'] = proto

    def loadFileRequested(self, dh):
        """
        loadFileRequested is called by "file loader" when a file is requested.
            FileLoader is provided by the AnalysisModule class
            dh is the handle to the currently selected directory (or directories)

        This function loads all of the successive records from the specified protocol.
        Ancillary information from the protocol is stored in class variables.
        Extracts information about the commands, sometimes using a rather
        simplified set of assumptions.
        :param dh: the directory handle (or list of handles) representing the selected
        entitites from the FileLoader in the Analysis Module
        :modifies: plots, sequence, data arrays, data mode, etc.
        :return: True if successful; otherwise raises an exception
        """
        # print 'loadfilerequested dh: ', dh

        if len(dh) == 0:
            raise Exception("IVCurve::loadFileRequested: " +
                            "Select an IV protocol directory.")
        if len(dh) != 1:
            raise Exception("IVCURVE::loadFileRequested: " +
                            "Can only load one file at a time.")
        self.clear_results()
        #        if self.current_dirhandle != dh[0]:  # is this the current file/directory?
        self.get_file_information(default_dh=dh)  # No, get info from most recent file requested
        data_file_handle = None
        data_dir_handle = None
        self.current_dirhandle = dh[0]  # this is critical!
        dh = dh[0]  # just get the first one
        self.data_plot.clearPlots()
        self.cmd_plot.clearPlots()
        self.filename = dh.name()
        self.cell_summary(dh)  # get other info as needed for the protocol
        dirs = dh.subDirs()
        traces = []
        cmd = []
        cmd_wave = []
        data = []
        self.time_base = None
        self.values = []
        #        self.sequence = self.dataModel.listSequenceParams(dh)  # already done in 'getfileinfo'
        self.trace_times = np.zeros(0)
        sequence_values = None
        # building command voltages - get amplitudes to clamp
        clamp = ('Clamp1', 'Pulse_amplitude')
        reps = ('protocol', 'repetitions')

        # the sequence was retrieved from the data file by get_file_information
        if clamp in self.sequence:
            self.clampValues = self.sequence[clamp]
            self.nclamp = len(self.clampValues)
            if sequence_values is not None:
                # noinspection PyUnusedLocal
                sequence_values = [x for x in self.clampValues for y in sequence_values]
            else:
                sequence_values = [x for x in self.clampValues]
        else:
            sequence_values = []
#            nclamp = 0

        # if sequence has repeats, build pattern
        if reps in self.sequence:
            self.repc = self.sequence[reps]
            self.nrepc = len(self.repc)
            # noinspection PyUnusedLocal
            sequence_values = [x for y in range(self.nrepc) for x in sequence_values]

        # select subset of data by overriding the directory sequence...
        if self.current_dirhandle is not None:
            ld = [self.ctrl.IVCurve_Sequence1.currentIndex() - 1]
            rd = [self.ctrl.IVCurve_Sequence2.currentIndex() - 1]
            if ld[0] == -1 and rd[0] == -1:
                pass
            else:
                if ld[0] == -1:  # 'All'
                    ld = range(self.ctrl.IVCurve_Sequence1.count() - 1)
                if rd[0] == -1:  # 'All'
                    rd = range(self.ctrl.IVCurve_Sequence2.count() - 1)
                dirs = []
                for i in ld:
                    for j in rd:
                        dirs.append('%03d_%03d' % (i, j))

        for i, directory_name in enumerate(dirs):  # dirs has the names of the runs withing the protocol
            data_dir_handle = dh[directory_name]  # get the directory within the protocol
            try:
                data_file_handle = self.dataModel.getClampFile(data_dir_handle)  # get pointer to clamp data
                # Check if there is no clamp file for this iteration of the protocol
                # Usually this indicates that the protocol was stopped early.
                if data_file_handle is None:
                    print 'IVCurve.loadFileRequested: Missing data in %s, element: %d' % (directory_name, i)
                    #raise Exception('IVCurve.loadFileRequested: Missing data in %s, element: %d' % (directory_name, i))
                    continue
            except:
                raise Exception("Error loading data for protocol %s:"
                                % directory_name)
            data_file = data_file_handle.read()
            # only consider data in a particular range
            data = self.dataModel.getClampPrimary(data_file)
            self.data_mode = self.dataModel.getClampMode(data_file)
            if self.data_mode is None:
                self.data_mode = self.ic_modes[0]  # set a default mode
            if self.data_mode in ['model_ic', 'model_vc']:  # lower case means model was run
                self.modelmode = True
            self.ctrl.IVCurve_dataMode.setText(self.data_mode)
            # Assign scale factors for the different modes to display data rationally
            if self.data_mode in self.ic_modes:
                self.command_scale_factor = 1e12
                self.command_units = 'pA'
            elif self.data_mode in self.vc_modes:
                self.command_units = 'mV'
                self.command_scale_factor = 1e3
            else:  # data mode not known; plot as voltage
                self.command_units = 'V'
                self.command_scale_factor = 1.0
            if self.ctrl.IVCurve_IVLimits.isChecked():
                cval = self.command_scale_factor * sequence_values[i]
                cmin = self.ctrl.IVCurve_IVLimitMin.value()
                cmax = self.ctrl.IVCurve_IVLimitMax.value()
                if cval < cmin or cval > cmax:
                    continue  # skip adding the data to the arrays

            self.devicesUsed = self.dataModel.getDevices(data_dir_handle)
            self.clampDevices = self.dataModel.getClampDeviceNames(data_dir_handle)
            self.holding = self.dataModel.getClampHoldingLevel(data_file_handle)
            self.amp_settings = self.dataModel.getWCCompSettings(data_file_handle)
            self.clamp_state = self.dataModel.getClampState(data_file_handle)
            # print self.devicesUsed
            cmd = self.dataModel.getClampCommand(data_file)

            # store primary channel data and read command amplitude
            info1 = data.infoCopy()
            if 'startTime' in info1[0].keys():
                start_time = info1[0]['startTime']
            elif 'startTime' in info1[1]['DAQ']['command'].keys():
                start_time = info1[1]['DAQ']['command']['startTime']
            else:
                start_time = 0.0
            self.trace_times = np.append(self.trace_times, start_time)
            traces.append(data.view(np.ndarray))
            cmd_wave.append(cmd.view(np.ndarray))
            # pick up and save the sequence values
            if len(sequence_values) > 0:
                self.values.append(sequence_values[i])
            else:
                self.values.append(cmd[len(cmd) / 2])
        if traces is None or len(traces) == 0:
            print "IVCurve::loadFileRequested: No data found in this run..."
            return False
        self.r_uncomp = 0.
        if self.amp_settings['WCCompValid']:
            if self.amp_settings['WCEnabled'] and self.amp_settings['CompEnabled']:
                self.r_uncomp = self.amp_settings['WCResistance'] * (1.0 - self.amp_settings['CompCorrection'] / 100.)
            else:
                self.r_uncomp = 0.
        # self.ctrl.IVCurve_R_unCompensated.setValue(self.r_uncomp * 1e-6)  # convert to Mohm to display
        # self.ctrl.IVCurve_R_unCompensated.setSuffix(u" M\u2126")
        # self.ctrl.IVCurve_Holding.setText('%.1f mV' % (float(self.holding) * 1e3))

        # put relative to the start
        self.trace_times -= self.trace_times[0]
        traces = np.vstack(traces)
        self.cmd_wave = np.vstack(cmd_wave)
        self.time_base = np.array(cmd.xvals('Time'))
        self.cmd = np.array(self.values)
        # set up the selection region correctly and
        # prepare IV curves and find spikes
        info = [
            {'name': 'Command', 'units': cmd.axisUnits(-1),
             'values': np.array(self.values)},
            data.infoCopy('Time'),
            data.infoCopy(-1)]
        traces = traces[:len(self.values)]
        self.traces = MetaArray(traces, info=info)
        sfreq = self.dataModel.getSampleRate(data_file_handle)
        self.sample_interval = 1. / sfreq
        vc_command = data_dir_handle.parent().info()['devices'][self.clampDevices[0]]
        if 'waveGeneratorWidget' in vc_command:
            try:
                vc_info = vc_command['waveGeneratorWidget']['stimuli']['Pulse']
                pulsestart = vc_info['start']['value']
                pulsedur = vc_info['length']['value']
            except KeyError:
                pulsestart = 0.
                pulsedur = np.max(self.time_base)
        elif 'daqState' in vc_command:
            vc_state = vc_command['daqState']['channels']['command']['waveGeneratorWidget']
            func = vc_state['function']
            # regex parse the function string: pulse(100, 1000, amp)
            pulsereg = re.compile("(^pulse)\((\d*),\s*(\d*),\s*(\w*)\)")
            match = pulsereg.match(func)
            g = match.groups()
            if g is None:
                raise Exception('loadFileRequested (IVCurve) cannot parse waveGenerator function: %s' % func)
            pulsestart = float(g[1]) / 1000.  # values coming in are in ms, but need s
            pulsedur = float(g[2]) / 1000.
        else:
            raise Exception("loadFileRequested (IVCurve): cannot find pulse information")
        cmdtimes = np.array([pulsestart, pulsedur])
        if self.ctrl.IVCurve_KeepT.isChecked() is False:
            self.tstart = cmdtimes[0]  # cmd.xvals('Time')[cmdtimes[0]]
            self.tend = np.sum(cmdtimes)  # cmd.xvals('Time')[cmdtimes[1]] + self.tstart
            self.tdur = self.tend - self.tstart
            self.analysis_summary['PulseWindow'] = [self.tstart, self.tend, self.tdur]
        # if self.ctrl.IVCurve_KeepT.isChecked() is False:
        #     self.tstart += self.sample_interval
        #     self.tend += self.sample_interval

        # build the list of command values that are used for the fitting
        cmdList = []
        for i in range(len(self.values)):
            cmdList.append('%8.3f %s' %
                           (self.command_scale_factor * self.values[i], self.command_units))
        self.ctrl.IVCurve_tauh_Commands.clear()
        self.ctrl.IVCurve_tauh_Commands.addItems(cmdList)
        self.color_scale.setIntColorScale(0, len(dirs), maxValue=200)
        self.make_map_symbols()
        # if self.data_mode in self.ic_modes:
        #     # for adaptation ratio:
        #     self.update_all_analysis()
        if self.data_mode in self.vc_modes:
            self.spikecount = np.zeros(len(np.array(self.values)))

        # and also plot
        self.plot_traces()
        self.setup_regions()
        #self._host_.dockArea.findAll()[1]['Parameters'].raiseDock()  # parameters window to the top
        self.get_window_analysisPars()  # prepare the analysis parameters
        return True

    def file_cell_protocol(self):
        """
        file_cell_protocol breaks the current filename down and returns a
        tuple: (date, cell, protocol)
        last argument returned is the rest of the path...
        """
        (p0, proto) = os.path.split(self.filename)
        (p1, cell) = os.path.split(p0)
        (p2, sliceid) = os.path.split(p1)
        (p3, date) = os.path.split(p2)
        return date, sliceid, cell, proto, p3

    def plot_traces(self, multimode=False):
        """
        Plot the current data traces.
        :param multimode: try using "multiline plot routine" to speed up plots (no color though)
        :return: nothing
        """
        if self.ctrl.IVCurve_KeepAnalysis.isChecked():
            self.keep_analysis_count += 1
        else:
            self.keep_analysis_count = 0  # always make sure is reset
            # this is the only way to reset iterators.
            self.color_list = itertools.cycle(self.colors)
            self.symbol_list = itertools.cycle(self.symbols)
        self.make_map_symbols()
        self.data_plot.plotItem.clearPlots()
        self.cmd_plot.plotItem.clearPlots()
        ntr = self.traces.shape[0]
        self.data_plot.setDownsampling(auto=False, mode='mean')
        self.data_plot.setClipToView(True)
        self.cmd_plot.setDownsampling(auto=False, mode='mean')
        self.cmd_plot.setClipToView(True)
        self.data_plot.disableAutoRange()
        self.cmd_plot.disableAutoRange()
        cmdindxs = np.unique(self.cmd)  # find the unique voltages
        colindxs = [int(np.where(cmdindxs == self.cmd[i])[0]) for i in range(len(self.cmd))]  # make a list to use
        if multimode:
            pass
            # datalines = MultiLine(self.time_base, self.traces, downsample=10)
            # self.data_plot.addItem(datalines)
            # cmdlines = MultiLine(self.time_base, self.cmd_wave, downsample=10)
            # self.cmd_plot.addItem(cmdlines)
        else:
            for i in range(ntr):
                atrace = self.traces[i]
                acmdwave = self.cmd_wave[i]
                self.data_plot.plot(x=self.time_base, y=atrace, downSample=10, downSampleMethod='mean',
                                    pen=pg.intColor(colindxs[i], len(cmdindxs), maxValue=255))
                self.cmd_plot.plot(x=self.time_base, y=acmdwave, downSample=10, downSampleMethod='mean',
                                   pen=pg.intColor(colindxs[i], len(cmdindxs), maxValue=255))

        if self.data_mode in self.ic_modes:
            self.label_up(self.data_plot, 'T (s)', 'V (V)', 'Data')
            self.label_up(self.cmd_plot, 'T (s)', 'I (%s)' % self.command_units, 'Data')
        elif self.data_mode in self.vc_modes:  # voltage clamp
            self.label_up(self.data_plot, 'T (s)', 'I (A)', 'Data')
            self.label_up(self.cmd_plot, 'T (s)', 'V (%s)' % self.command_units, 'Data')
        else:  # mode is not known: plot both as V
            self.label_up(self.data_plot, 'T (s)', 'V (V)', 'Data')
            self.label_up(self.cmd_plot, 'T (s)', 'V (%s)' % self.command_units, 'Data')
        self.data_plot.autoRange()
        self.cmd_plot.autoRange()

    def setup_regions(self):
        """
        Initialize the positions of the lr regions on the display.
        We attempt to use a logical set of values based on the timing of command steps
        and stimulus events
        :return:
        """
        self.initialize_regions()  # now create the analysis regions, if not already existing
        if self.ctrl.IVCurve_KeepT.isChecked() is False:  # change regions; otherwise keep...
            tstart_pk = self.tstart
            tdur_pk = self.tdur * 0.4  # use first 40% of trace for peak
            tstart_ss = self.tstart + 0.75 * self.tdur
            tdur_ss = self.tdur * 0.25
            tstart_tau = self.tstart + 0.1 * self.tdur
            tdur_tau = 0.9 * self.tdur
            # tauh window
            self.regions['lrtau']['region'].setRegion([tstart_tau,
                                                       tstart_tau + tdur_tau])
            # peak voltage window
            self.regions['lrwin0']['region'].setRegion([tstart_pk,
                                                        tstart_pk + tdur_pk])
            # steady-state meausurement:
            self.regions['lrwin1']['region'].setRegion([tstart_ss,
                                                        tstart_ss + tdur_ss])
            # rmp measurement
            self.regions['lrrmp']['region'].setRegion([0., self.tstart * 0.9])  # rmp window
            print 'rmp window region: ', self.tstart * 0.9
        for r in ['lrtau', 'lrwin0', 'lrwin1', 'lrrmp']:
            self.regions[r]['region'].setBounds([0., np.max(self.time_base)])  # limit regions to data

    def get_window_analysisPars(self):
        """
        Retrieve the settings of the lr region windows, and some other general values
        in preparation for analysis
        :return:
        """
        self.analysis_parameters = {}  # start out empty so we are not fooled by priors
        for region in ['lrleak', 'lrwin0', 'lrwin1', 'lrrmp', 'lrtau']:
            rgninfo = self.regions[region]['region'].getRegion()  # from the display
            self.regions[region]['start'].setValue(rgninfo[0] * 1.0e3)  # report values to screen
            self.regions[region]['stop'].setValue(rgninfo[1] * 1.0e3)
            self.analysis_parameters[region] = {'times': rgninfo}
        # for region in ['lrwin0', 'lrwin1', 'lrwin2']:
        #            if self.regions[region]['mode'] is not None:
        #                self.analysis_parameters[region]['mode'] = self.regions[region]['mode'].currentText()
        #         self.get_alternation()  # get values into the analysisPars dictionary
        #         self.get_baseline()
        #         self.get_junction()

    def updateAnalysis(self, **kwargs):
        """updateAnalysis re-reads the time parameters and counts the spikes"""
        self.get_window_analysisPars()
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
        self.adapt_ratio: the adaptation ratio of the spike train
        self.fsl: a numpy array of first spike latency for each command level
        self.fisi: a numpy array of first interspike intervals for each
            command level
        self.nospk: the indices of command levels where no spike was detected
        self.spk: the indices of command levels were at least one spike
            was detected
        """
        if self.keep_analysis_count == 0:
            clearFlag = True
        else:
            clearFlag = False
        if self.data_mode not in self.ic_modes or self.time_base is None:
            # print ('IVCurve::countSpikes: Cannot count spikes, ' +
            #       'and dataMode is ', self.data_mode, 'and ICModes are: ', self.ic_modes, 'tx is: ', self.tx)
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
        twin = self.tend - self.tstart  # measurements window in seconds
        maxspkrate = 50  # max rate to count  in adaptation is 50 spikes/second
        minspk = 4
        maxspk = int(maxspkrate*twin)  # scale max dount by range of spike counts
        threshold = self.ctrl.IVCurve_SpikeThreshold.value() * 1e-3
        ntr = len(self.traces)
        self.spikecount = np.zeros(ntr)
        fsl = np.zeros(ntr)
        fisi = np.zeros(ntr)
        ar = np.zeros(ntr)
        rmp = np.zeros(ntr)
        # rmp is taken from the mean of all the baselines in the traces

        for i in range(ntr):
            (spike, spk) = Utility.findspikes(self.time_base, self.traces[i],
                                              threshold, t0=self.tstart,
                                              t1=self.tend,
                                              dt=self.sample_interval,
                                              mode='schmitt',
                                              interpolate=False,
                                              debug=False)
            if len(spike) == 0:
                continue
            self.spikecount[i] = len(spike)
            fsl[i] = spike[0] - self.tstart
            if len(spike) > 1:
                fisi[i] = spike[1] - spike[0]
                # for Adaptation ratio analysis
            if minspk <= len(spike) <= maxspk:
                misi = np.mean(np.diff(spike[-3:]))
                ar[i] = misi / fisi[i]
            (rmp[i], r2) = Utility.measure('mean', self.time_base, self.traces[i],
                                           0.0, self.tstart)
        iAR = np.where(ar > 0)

        self.adapt_ratio = np.mean(ar[iAR])  # only where we made the measurement
        self.analysis_summary['AdaptRatio'] = self.adapt_ratio
        self.ctrl.IVCurve_AR.setText(u'%7.3f' % self.adapt_ratio)
        fisi *= 1.0e3
        fsl *= 1.0e3
        self.fsl = fsl
        self.fisi = fisi
        self.nospk = np.where(self.spikecount == 0)
        self.spk = np.where(self.spikecount > 0)
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
        return date, cell, proto, p2

    def printAnalysis(self, script_header=True, copytoclipboard=False):
        """
        Print the CCIV summary information (Cell, protocol, etc)
        Print a nice formatted version of the analysis output to the terminal.
        The output can be copied to another program (excel, prism) for further analysis
        :param script_header:
        :return:
        """
        
        if self.data_mode in self.ic_modes:
          data_template = (
            OrderedDict([('Species', '{:>s}'), ('Age', '{:>5s}'), ('Sex', '{:>1s}'), ('Weight', '{:>5s}'),
                         ('Temperature', '{:>5s}'), ('ElapsedTime', '{:>8.2f}'), 
                         ('RMP', '{:>5.1f}'), ('Rin', '{:>5.1f}'),
                         ('tau', '{:>5.1f}'), ('AdaptRatio', '{:>7.3f}'),
                         ('tauh', '{:>5.1f}'), ('Gh', '{:>6.2f}'),
                        ]))
        else:
          data_template = (
            OrderedDict([('ElapsedTime', '{:>8.2f}'), ('HoldV', '{:>5.1f}'), ('JP', '{:>5.1f}'),
                         ('Rs', '{:>6.2f}'), ('Cm', '{:>6.1f}'), ('Ru', '{:>6.2f}'),
                         ('Erev', '{:>6.2f}'),
                         ('gsyn_Erev', '{:>9.2f}'), ('gsyn_60', '{:>7.2f}'), ('gsyn_13', '{:>7.2f}'),
                         # ('p0', '{:6.3e}'), ('p1', '{:6.3e}'), ('p2', '{:6.3e}'), ('p3', '{:6.3e}'),
                         ('I_ionic+', '{:>8.3f}'), ('I_ionic-', '{:>8.3f}'), ('ILeak', '{:>7.3f}'),
                         ('win1Start', '{:>9.3f}'), ('win1End', '{:>7.3f}'),
                         ('win2Start', '{:>9.3f}'), ('win2End', '{:>7.3f}'),
                         ('win0Start', '{:>9.3f}'), ('win0End', '{:>7.3f}'),
            ]))
        
        # summary table header is written anew for each cell
        if self.script_header:
            print('{:34s}\t{:24s}\t'.format("Cell", "Protocol")),
            for k in data_template.keys():
                print('{:<s}\t'.format(k)),
            print ''
            self.script_header = False
        ltxt = ''
        ltxt += ('{:34s}\t{:24s}\t'.format(self.analysis_summary['CellID'], self.analysis_summary['Protocol']))
          
        for a in data_template.keys():
            if a in self.analysis_summary.keys():
                ltxt += ((data_template[a] + '\t').format(self.analysis_summary[a]))
            else:
                ltxt += (('NaN\t'))
        print ltxt
        if copytoclipboard:
            clipb = QtGui.QApplication.clipboard()
            clipb.clear(mode=clipb.Clipboard)
            clipb.setText(ltxt, mode=clipb.Clipboard)

            #
            # (date, cell, proto, p2) = self.fileCellProtocol()
            # print 'sequence: ', self.values
            # smin = np.amin(self.values)*1e12
            # smax = np.amax(self.values)*1e12
            # sstep = np.mean(np.diff(self.values))*1e12
            # seq = '%g;%g/%g' % (smin, smax, sstep)
            # print '='*80
            # print ("%14s,%14s,%16s,%20s,%9s,%9s,%10s,%9s,%10s" %
            # ("Date", "Cell", "Protocol",
            #         "Sequence", "RMP(mV)", " Rin(Mohm)",  "tau(ms)",
            #         "ARatio", "tau2(ms)"))
            # print ("%14s,%14s,%16s,%20s,%8.1f,%8.1f,%8.2f,%8.3f,%8.2f" %
            #        (date, cell, proto, seq, self.Rmp*1000., self.r_in*1e-6,
            #         self.tau*1000., self.adapt_ratio, self.tau2*1000))
            # print '-'*80

    def update_Tau_membrane(self, peak_time=None, printWindow=False, whichTau=1):
        """
        Compute time constant (single exponential) from the
        onset of the response
        using lrpk window, and only the smallest 1/3 of the steps...
        """

        if len(self.cmd) == 0:  # probably not ready yet to do the update.
            return
        if self.data_mode not in self.ic_modes:  # only permit in IC
            return
        rgnpk = list(self.regions['lrwin0']['region'].getRegion())
        Func = 'exp1'  # single exponential fit with DC offset.
        Fits = Fitting.Fitting()
        initpars = [self.rmp*1e-3, 0.010, 0.01]
        peak_time=None
        icmdneg = np.where(self.cmd < 0)
        maxcmd = np.min(self.cmd)
        ineg = np.where(self.cmd[icmdneg] >= maxcmd / 3)
        if peak_time is not None and ineg != np.array([]):
            rgnpk[1] = np.max(peak_time[ineg[0]])
        whichdata = ineg[0]
        itaucmd = self.cmd[ineg]
        whichaxis = 0
        fpar = []
        names = []

        for j, k in enumerate(whichdata):
            self.data_plot.plot(self.time_base,  self.traces[k], pen=pg.mkPen('y'))
            (fparx, xf, yf, namesx) = Fits.FitRegion([k], whichaxis,
                                               self.time_base,
                                               self.traces,
                                               dataType='2d',
                                               t0=rgnpk[0], t1=rgnpk[1],
                                               fitFunc=Func,
                                               fitPars=initpars,
                                               method='SLSQP',
                                               bounds=[(-0.1, 0.1), (-0.1, 0.1), (0.005, 0.30)])
        
            if not fparx:
              raise Exception('IVCurve::update_Tau_membrane: Charging tau fitting failed - see log')
            #print 'j: ', j, len(fpar)
            fpar.append(fparx[0])
            names.append(namesx[0])
        self.taupars = fpar
        self.tauwin = rgnpk
        self.taufunc = Func
        self.whichdata = whichdata
        taus = []
        for j in range(len(fpar)):
            outstr = ""
            taus.append(fpar[j][2])
            for i in range(0, len(names[j])):
                outstr += '%s = %f, ' % (names[j][i], fpar[j][i])
            if printWindow:
                print("FIT(%d, %.1f pA): %s " %
                      (whichdata[j], itaucmd[j] * 1e12, outstr))
        meantau = np.mean(taus)
        self.ctrl.IVCurve_Tau.setText(u'%18.1f ms' % (meantau * 1.e3))
        self.tau = meantau
        self.analysis_summary['tau'] = self.tau*1.e3
        tautext = 'Mean Tau: %8.1f'
        if printWindow:
            print tautext % (meantau * 1e3)
        self.show_tau_plot()

    def show_tau_plot(self):
        Fits = Fitting.Fitting()
        fitPars = self.taupars
        xFit = np.zeros((len(self.taupars), 500))
        for i in range(len(self.taupars)):
          xFit[i,:] = np.arange(0, self.tauwin[1]-self.tauwin[0], (self.tauwin[1]-self.tauwin[0])/500.)
        yFit = np.zeros((len(fitPars), xFit.shape[1]))
        fitfunc = Fits.fitfuncmap[self.taufunc]
        for k, whichdata in enumerate(self.whichdata):
            yFit[k] = fitfunc[0](fitPars[k], xFit[k], C=None)  # +self.ivbaseline[whichdata]
            self.data_plot.plot(xFit[k]+self.tauwin[0], yFit[k], pen=pg.mkPen('w'))
        

    def update_Tauh(self, printWindow=False):
        """ compute tau (single exponential) from the onset of the markers
            using lrtau window, and only for the step closest to the selected
            current level in the GUI window.

            Also compute the ratio of the sag from the peak (marker1) to the
            end of the trace (marker 2).
            Based on analysis in Fujino and Oertel, J. Neuroscience 2001,
            to type cells based on different Ih kinetics and magnitude.
        """
        if not self.ctrl.IVCurve_showHide_lrtau.isChecked():
            return
        rgn = self.regions['lrtau']['region'].getRegion()
        Func = 'exp1'  # single exponential fit to the whole region
        Fits = Fitting.Fitting()

        initpars = [-80.0 * 1e-3, -10.0 * 1e-3, 50.0 * 1e-3]

        # find the current level that is closest to the target current
        s_target = self.ctrl.IVCurve_tauh_Commands.currentIndex()
        itarget = self.values[s_target]  # retrive actual value from commands
        self.neg_cmd = itarget
        idiff = np.abs(np.array(self.cmd) - itarget)
        amin = np.argmin(idiff)  # amin appears to be the same as s_target
        # target trace (as selected in cmd drop-down list):
        target = self.traces[amin]
        # get Vrmp -  # rmp approximation.
        vrmp = np.median(target['Time': 0.0:self.tstart - 0.005]) * 1000.
        self.neg_vrmp = vrmp
        # get peak and steady-state voltages
        pkRgn = self.regions['lrwin0']['region'].getRegion()
        ssRgn = self.regions['lrwin1']['region'].getRegion()
        vpk = target['Time': pkRgn[0]:pkRgn[1]].min() * 1000
        self.neg_pk = (vpk - vrmp) / 1000.
        vss = np.median(target['Time': ssRgn[0]:ssRgn[1]]) * 1000
        self.neg_ss = (vss - vrmp) / 1000.
        whichdata = [int(amin)]
        itaucmd = [self.cmd[amin]]
        self.ctrl.IVCurve_tau2TStart.setValue(rgn[0] * 1.0e3)
        self.ctrl.IVCurve_tau2TStop.setValue(rgn[1] * 1.0e3)
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
        if not fpar:
            raise Exception('IVCurve::update_Tauh: tau_h fitting failed - see log')
        redpen = pg.mkPen('r', width=1.5, style=QtCore.Qt.DashLine)
        if self.fit_curve is None:
            self.fit_curve = self.data_plot.plot(xf[0], yf[0], pen=redpen)
        else:
            self.fit_curve.clear()
            self.fit_curve = self.data_plot.plot(xf[0], yf[0], pen=redpen)
            self.fit_curve.update()
        s = np.shape(fpar)
        taus = []
        for j in range(0, s[0]):
            outstr = ""
            taus.append(fpar[j][2])
            for i in range(0, len(names[j])):
                outstr += '%s = %f, ' % (names[j][i], fpar[j][i])
            if printWindow:
                print("Ih FIT(%d, %.1f pA): %s " %
                      (whichdata[j], itaucmd[j] * 1e12, outstr))
        meantau = np.mean(taus)
        self.ctrl.IVCurve_Tauh.setText(u'%8.1f ms' % (meantau * 1.e3))
        self.tau2 = meantau
        bovera = (vss - vrmp) / (vpk - vrmp)
        self.ctrl.IVCurve_Ih_ba.setText('%8.1f' % (bovera * 100.))
        self.ctrl.IVCurve_ssAmp.setText('%8.2f' % (vss - vrmp))
        self.ctrl.IVCurve_pkAmp.setText('%8.2f' % (vpk - vrmp))
        if bovera < 0.55 and self.tau2 < 0.015:  #
            self.ctrl.IVCurve_FOType.setText('D Stellate')
        else:
            self.ctrl.IVCurve_FOType.setText('T Stellate')
            # estimate of Gh:
        Gpk = itarget / self.neg_pk
        Gss = itarget / self.neg_ss
        self.Gh = Gss - Gpk
        self.analysis_summary['tauh'] = self.tau2*1.e3
        self.analysis_summary['Gh'] = self.Gh

        self.ctrl.IVCurve_Gh.setText('%8.2f nS' % (self.Gh * 1e9))

    def update_ssAnalysis(self):
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
        rgnss = self.regions['lrwin1']['region'].getRegion()
        self.ctrl.IVCurve_ssTStart.setValue(rgnss[0] * 1.0e3)
        self.ctrl.IVCurve_ssTStop.setValue(rgnss[1] * 1.0e3)
        data1 = self.traces['Time': rgnss[0]:rgnss[1]]
        self.ivss = []
        commands = np.array(self.values)

        # check out whether there are spikes in the window that is selected
        threshold = self.ctrl.IVCurve_SpikeThreshold.value() * 1e-3
        ntr = len(self.traces)
        spikecount = np.zeros(ntr)
        for i in range(ntr):
            (spike, spk) = Utility.findspikes(self.time_base, self.traces[i],
                                              threshold,
                                              t0=rgnss[0], t1=rgnss[1],
                                              dt=self.sample_interval,
                                              mode='schmitt',
                                              interpolate=False,
                                              debug=False)
            if len(spike) > 0:
                spikecount[i] = len(spike)
        nospk = np.where(spikecount == 0)
        if data1.shape[1] == 0 or data1.shape[0] == 1:
            return  # skip it

        self.ivss = data1.mean(axis=1)  # all traces
        if self.ctrl.IVCurve_SubBaseline.isChecked():
            self.ivss = self.ivss - self.ivbaseline

        if len(nospk) >= 1:
            # Steady-state IV where there are no spikes
            self.ivss = self.ivss[nospk]
            self.ivss_cmd = commands[nospk]
            self.cmd = commands[nospk]
            # compute Rin from the SS IV:
            if len(self.cmd) > 0 and len(self.ivss) > 0:
                self.r_in = np.max(np.diff
                                   (self.ivss) / np.diff(self.cmd))
                self.ctrl.IVCurve_Rin.setText(u'%9.1f M\u03A9'
                                              % (self.r_in * 1.0e-6))
                self.analysis_summary['Rin'] = self.r_in*1.0e-6
            else:
                self.ctrl.IVCurve_Rin.setText(u'No valid points')
        self.yleak = np.zeros(len(self.ivss))
        if self.ctrl.IVCurve_subLeak.isChecked():
            (x, y) = Utility.clipdata(self.ivss, self.ivss_cmd,
                                      self.ctrl.IVCurve_LeakMin.value() * 1e-3,
                                      self.ctrl.IVCurve_LeakMax.value() * 1e-3)
            p = np.polyfit(x, y, 1)  # linear fit
            self.yleak = np.polyval(p, self.ivss_cmd)
            self.ivss = self.ivss - self.yleak
        isort = np.argsort(self.ivss_cmd)
        self.ivss_cmd = self.ivss_cmd[isort]
        self.ivss = self.ivss[isort]
        self.update_IVPlot()

    def update_pkAnalysis(self, clear=False, pw=False):
        """
            Compute the peak IV (minimum) from the selected window
            mode can be 'min', 'max', or 'abs'
        """
        if self.traces is None:
            return
        mode = self.ctrl.IVCurve_PeakMode.currentText()
        rgnpk = self.regions['lrwin0']['region'].getRegion()
        self.ctrl.IVCurve_pkTStart.setValue(rgnpk[0] * 1.0e3)
        self.ctrl.IVCurve_pkTStop.setValue(rgnpk[1] * 1.0e3)
        data2 = self.traces['Time': rgnpk[0]:rgnpk[1]]
        if data2.shape[1] == 0:
            return  # skip it - window missed the data
        commands = np.array(self.values)
        # check out whether there are spikes in the window that is selected
        # but only in current clamp
        nospk = []
        peak_pos = None
        if self.data_mode in self.ic_modes:
            threshold = self.ctrl.IVCurve_SpikeThreshold.value() * 1e-3
            ntr = len(self.traces)
            spikecount = np.zeros(ntr)
            for i in range(ntr):
                (spike, spk) = Utility.findspikes(self.time_base, self.traces[i],
                                                  threshold,
                                                  t0=rgnpk[0], t1=rgnpk[1],
                                                  dt=self.sample_interval,
                                                  mode='schmitt',
                                                  interpolate=False, debug=False)
                if len(spike) == 0:
                    continue
                spikecount[i] = len(spike)
            nospk = np.where(spikecount == 0)
            nospk = np.array(nospk)[0]
        if mode == 'Min':
            self.ivpk = data2.min(axis=1)
            peak_pos = np.argmin(data2, axis=1)
        elif mode == 'Max':
            self.ivpk = data2.max(axis=1)
            peak_pos = np.argmax(data2, axis=1)
        elif mode == 'Abs':  # find largest regardless of the sign ('minormax')
            x1 = data2.min(axis=1)
            peak_pos1 = np.argmin(data2, axis=1)
            x2 = data2.max(axis=1)
            peak_pos2 = np.argmax(data2, axis=1)
            self.ivpk = np.zeros(data2.shape[0])
            for i in range(data2.shape[0]):
                if -x1[i] > x2[i]:
                    self.ivpk[i] = x1[i]
                    peak_pos = peak_pos1
                else:
                    self.ivpk[i] = x2[i]
                    peak_pos = peak_pos2
                    # self.ivpk = np.array([np.max(x1[i], x2[i]) for i in range(data2.shape[0]])
                    #self.ivpk = np.maximum(np.fabs(data2.min(axis=1)), data2.max(axis=1))
        if self.ctrl.IVCurve_SubBaseline.isChecked():
            self.ivpk = self.ivpk - self.ivbaseline
        if len(nospk) >= 1:
            # Peak (min, max or absmax voltage) IV where there are no spikes
            self.ivpk = self.ivpk[nospk]
            self.ivpk_cmd = commands[nospk]
            self.cmd = commands[nospk]
        else:
            self.ivpk_cmd = commands
            self.cmd = commands
        self.ivpk = self.ivpk.view(np.ndarray)
        if self.ctrl.IVCurve_subLeak.isChecked():
            self.ivpk = self.ivpk - self.yleak
        # now sort data in ascending command levels
        isort = np.argsort(self.ivpk_cmd)
        self.ivpk_cmd = self.ivpk_cmd[isort]
        self.ivpk = self.ivpk[isort]
        self.update_IVPlot()
        peak_time = self.time_base[peak_pos]
        self.update_Tau_membrane(peak_time=peak_time, printWindow=pw)

    def update_rmpAnalysis(self, **kwargs):
        """
            Compute the RMP over time/commands from the selected window
        """
        if self.traces is None:
            return
        rgnrmp = self.regions['lrrmp']['region'].getRegion()
        self.ctrl.IVCurve_rmpTStart.setValue(rgnrmp[0] * 1.0e3)
        self.ctrl.IVCurve_rmpTStop.setValue(rgnrmp[1] * 1.0e3)
        data1 = self.traces['Time': rgnrmp[0]:rgnrmp[1]]
        data1 = data1.view(np.ndarray)
        self.ivbaseline = []
        commands = np.array(self.values)
        self.ivbaseline = data1.mean(axis=1)  # all traces
        self.ivbaseline_cmd = commands
        self.cmd = commands
        self.rmp = np.mean(self.ivbaseline) * 1e3  # convert to mV
        self.ctrl.IVCurve_vrmp.setText('%8.2f' % self.rmp)
        self.update_RMPPlot()
        self.analysis_summary['RMP'] = self.rmp

    def make_map_symbols(self):
        """
        Given the current state of things, (keep analysis count, for example),
        return a tuple of pen, fill color, empty color, a symbol from
        our lists, and a clearflag. Used to overplot different data.
        """
        n = self.keep_analysis_count
        pen = self.color_list.next()
        filledbrush = pen
        emptybrush = None
        symbol = self.symbol_list.next()
        if n == 0:
            clearFlag = True
        else:
            clearFlag = False
        self.currentSymDict = {'pen': pen, 'filledbrush': filledbrush,
                               'emptybrush': emptybrush, 'symbol': symbol,
                               'n': n, 'clearFlag': clearFlag}

    def map_symbol(self):
        cd = self.currentSymDict
        if cd['filledbrush'] == 'w':
            cd['filledbrush'] = pg.mkBrush((128, 128, 128))
        if cd['pen'] == 'w':
            cd['pen'] = pg.mkPen((128, 128, 128))
        self.lastSymbol = (cd['pen'], cd['filledbrush'],
                           cd['emptybrush'], cd['symbol'],
                           cd['n'], cd['clearFlag'])
        return self.lastSymbol

    def update_IVPlot(self):
        """
            Draw the peak and steady-sate IV to the I-V window
            Note: x axis is always I or V, y axis V or I
        """
        if self.ctrl.IVCurve_KeepAnalysis.isChecked() is False:
            self.IV_plot.clear()
        (pen, filledbrush, emptybrush, symbol, n, clearFlag) = \
            self.map_symbol()
        if self.data_mode in self.ic_modes:
            if (len(self.ivss) > 0 and
                    self.ctrl.IVCurve_showHide_lrss.isChecked()):
                self.IV_plot.plot(self.ivss_cmd * 1e12, self.ivss * 1e3,
                                  symbol=symbol, pen=pen,
                                  symbolSize=6, symbolPen=pen,
                                  symbolBrush=filledbrush)
            if (len(self.ivpk) > 0 and
                    self.ctrl.IVCurve_showHide_lrpk.isChecked()):
                self.IV_plot.plot(self.ivpk_cmd * 1e12, self.ivpk * 1e3,
                                  symbol=symbol, pen=pen,
                                  symbolSize=6, symbolPen=pen,
                                  symbolBrush=emptybrush)
            self.label_up(self.IV_plot, 'I (pA)', 'V (mV)', 'I-V (CC)')
        if self.data_mode in self.vc_modes:
            if (len(self.ivss) > 0 and
                    self.ctrl.IVCurve_showHide_lrss.isChecked()):
                self.IV_plot.plot(self.ivss_cmd * 1e3, self.ivss * 1e9,
                                  symbol=symbol, pen=pen,
                                  symbolSize=6, symbolPen=pen,
                                  symbolBrush=filledbrush)
            if (len(self.ivpk) > 0 and
                    self.ctrl.IVCurve_showHide_lrpk.isChecked()):
                self.IV_plot.plot(self.ivpk_cmd * 1e3, self.ivpk * 1e9,
                                  symbol=symbol, pen=pen,
                                  symbolSize=6, symbolPen=pen,
                                  symbolBrush=emptybrush)
            self.label_up(self.IV_plot, 'V (mV)', 'I (nA)', 'I-V (VC)')

    def update_RMPPlot(self):
        """
            Draw the RMP to the I-V window
            Note: x axis can be I, T, or  # spikes
        """
        if self.ctrl.IVCurve_KeepAnalysis.isChecked() is False:
            self.RMP_plot.clear()
        if len(self.ivbaseline) > 0:
            (pen, filledbrush, emptybrush, symbol, n, clearFlag) = \
                self.map_symbol()
            mode = self.ctrl.IVCurve_RMPMode.currentIndex()
            if self.data_mode in self.ic_modes:
                sf = 1e3
                self.RMP_plot.setLabel('left', 'V mV')
            else:
                sf = 1e12
                self.RMP_plot.setLabel('left', 'I (pA)')
            if mode == 0:
                self.RMP_plot.plot(self.trace_times, sf * np.array(self.ivbaseline),
                                   symbol=symbol, pen=pen,
                                   symbolSize=6, symbolPen=pen,
                                   symbolBrush=filledbrush)
                self.RMP_plot.setLabel('bottom', 'T (s)')
            elif mode == 1:
                self.RMP_plot.plot(self.cmd,
                                   1.e3 * np.array(self.ivbaseline), symbolSize=6,
                                   symbol=symbol, pen=pen,
                                   symbolPen=pen, symbolBrush=filledbrush)
                self.RMP_plot.setLabel('bottom', 'I (pA)')
            elif mode == 2:
                self.RMP_plot.plot(self.spikecount,
                                   1.e3 * np.array(self.ivbaseline), symbolSize=6,
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
        if self.data_mode in self.vc_modes:
            self.fiPlot.clear()  # no plots of spikes in VC
            self.fslPlot.clear()
            return
        (pen, filledbrush, emptybrush, symbol, n, clearFlag) = self.map_symbol()
        mode = self.ctrl.IVCurve_RMPMode.currentIndex()  # get x axis mode
        commands = np.array(self.values)
        self.cmd = commands[self.nospk]
        self.spcmd = commands[self.spk]
        iscale = 1.0e12  # convert to pA
        yfslsc = 1.0  # convert to msec
        if mode == 0:  # plot with time as x axis
            xfi = self.trace_times
            xfsl = self.trace_times
            select = range(len(self.trace_times))
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
        self.fiPlot.plot(x=xfi, y=self.spikecount, clear=clearFlag,
                         symbolSize=6,
                         symbol=symbol, pen=pen,
                         symbolPen=pen, symbolBrush=filledbrush)
        self.fslPlot.plot(x=xfsl, y=self.fsl[select] * yfslsc, clear=clearFlag,
                          symbolSize=6,
                          symbol=symbol, pen=pen,
                          symbolPen=pen, symbolBrush=filledbrush)
        self.fslPlot.plot(x=xfsl, y=self.fisi[select] * yfslsc, symbolSize=6,
                          symbol=symbol, pen=pen,
                          symbolPen=pen, symbolBrush=emptybrush)
        if len(xfsl) > 0:
            self.fslPlot.setXRange(0.0, np.max(xfsl))
        self.fiPlot.setLabel('bottom', xlabel)
        self.fslPlot.setLabel('bottom', xlabel)

    def readParameters(self, clearFlag=False, pw=False):
        """
        Read the parameter window entries, set the lr regions to the values
        in the window, and do an update on the analysis
        """
        (pen, filledbrush, emptybrush, symbol, n, clearFlag) = self.map_symbol()
        # update RMP first as we might need it for the others.
        if self.ctrl.IVCurve_showHide_lrrmp.isChecked():
            rgnx1 = self.ctrl.IVCurve_rmpTStart.value() / 1.0e3
            rgnx2 = self.ctrl.IVCurve_rmpTStop.value() / 1.0e3
            self.regions['lrrmp']['region'].setRegion([rgnx1, rgnx2])
            self.update_rmpAnalysis(clear=clearFlag, pw=pw)

        if self.ctrl.IVCurve_showHide_lrss.isChecked():
            rgnx1 = self.ctrl.IVCurve_ssTStart.value() / 1.0e3
            rgnx2 = self.ctrl.IVCurve_ssTStop.value() / 1.0e3
            self.regions['lrwin1']['region'].setRegion([rgnx1, rgnx2])
            self.update_ssAnalysis()

        if self.ctrl.IVCurve_showHide_lrpk.isChecked():
            rgnx1 = self.ctrl.IVCurve_pkTStart.value() / 1.0e3
            rgnx2 = self.ctrl.IVCurve_pkTStop.value() / 1.0e3
            self.regions['lrwin0']['region'].setRegion([rgnx1, rgnx2])
            self.update_pkAnalysis(clear=clearFlag, pw=pw)

        if self.ctrl.IVCurve_subLeak.isChecked():
            rgnx1 = self.ctrl.IVCurve_LeakMin.value() / 1e3
            rgnx2 = self.ctrl.IVCurve_LeakMax.value() / 1e3
            self.regions['lrleak']['region'].setRegion([rgnx1, rgnx2])
            self.update_ssAnalysis()
            self.update_pkAnalysis()

        if self.ctrl.IVCurve_showHide_lrtau.isChecked():
            # include tau in the list... if the tool is selected
            rgnx1 = self.ctrl.IVCurve_tau2TStart.value() / 1e3
            rgnx2 = self.ctrl.IVCurve_tau2TStop.value() / 1e3
            self.regions['lrtau']['region'].setRegion([rgnx1, rgnx2])
            self.update_Tauh()

        if self.ctrl.IVCurve_PeakMode.currentIndexChanged:
            self.peakmode = self.ctrl.IVCurve_PeakMode.currentText()
            self.update_pkAnalysis()

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
            'IVCurve_rmp': self.neg_vrmp / 1000.,
            'IVCurve_rinp': self.r_in,
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

    # ---- Helpers ----
    # Some of these would normally live in a pyqtgraph-related module, but are
    # just stuck here to get the job done.
    #
    @staticmethod
    def label_up(plot, xtext, ytext, title):
        """helper to label up the plot"""
        plot.setLabel('bottom', xtext)
        plot.setLabel('left', ytext)
        plot.setTitle(title)

