# -*- coding: utf-8 -*-
"""
PSPReversal: Analysis module that analyzes the current-voltage relationships
relationships of PSPs from voltage clamp data.
This is part of Acq4
Based on IVCurve (as of 5/2014)
Paul B. Manis, Ph.D.
2014.

Pep8 compliant (via pep8.py) 10/25/2013 and 6/2014

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
from acq4.pyqtgraph import configfile
from acq4.util.metaarray import MetaArray


stdFont = 'Arial'

import acq4.analysis.tools.Utility as Utility  # pbm's utilities...
import acq4.analysis.tools.Fitting as Fitting  # pbm's fitting stuff...
import ctrlTemplate
import resultsTemplate
import scriptTemplate


class PSPReversal(AnalysisModule):
    """
    PSPReversal is an Analysis Module for Acq4.

    PSPReversal performs analyses of current-voltage relationships in
    electrophysiology experiments. The module is interactive, and is primarily
    designed to allow a preliminary examination of data collected in current clamp
    and voltage clamp.
    Results analyzed include:
    RMP/Holding current as a function of time through the protocol
    Reversal potential determined from difference of two windows (or interpolation)
    with various measurements
    Prints reversal potential, IV curve (subtracted), and ancillary information

    """

    def __init__(self, host):
        AnalysisModule.__init__(self, host)
        # Note that self.dataModel  is set by the host.
        # This module assumes that the dataModel is PatchEPhys

        # -------------data elements---------------
        self.current_dirhandle = None
        self.data_loaded = None  #
        self.lrwin1_flag = True  # show is default
        self.lrwin2_flag = True
        self.rmp_flag = True
        self.lrtau_flag = False
        self.measure = {'rmp': [], 'rmpcmd': [],
                        'leak': [],
                        'win1': [], 'win1cmd': [], 'win1off': [], 'win1on': [],
                        'winaltcmd': [],
                        'win2': [], 'win2cmd': [], 'win2off': [], 'win2on': [],
                        'win2altcmd': [],
                        }
        self.cmd = None
        self.junction = 0.0  # junction potential (user adjustable)
        self.holding = 0.0  # holding potential (read from commands)
        self.regions_exist = False
        self.regions = {}
        self.fit_curve = None
        self.fitted_data = None
        self.tx = None
        self.keep_analysis_count = 0
        self.spikes_counted = False
        self.alternation = False  # data collected with "alternation" protocols
        self.baseline = False
        self.data_mode = 'IC'  # analysis depends on the type of data we have.
        # list of CC modes; lower case from simulations
        self.ic_modes = ['IC', 'CC', 'IClamp', 'ic']
        self.vc_modes = ['VC', 'VClamp', 'vc']  # list of VC modes
        self.modelmode = False
        self.clamp_state = None
        self.amp_settings = None
        self.trace_times = None
        self.cell_time = 0. # cell elapsed time

        self.cmd_wave = None
        self.traces = None
        self.trace_times = None
        self.tx = None

        # (some) results elements
        self.filename = ''
        self.r_in = 0.0
        self.tau = 0.0
        self.adapt_ratio = 0.0
        self.traces = None
        self.spikes_counted = False
        self.nospk = []
        self.spk = []
        ntr = 0
        self.spikecount = None
        self.fsl = None
        self.fisi = None
        self.ar = None
        self.diffFit = None
        self.IV_background = None

        self.cmd = []
        self.sequence = ''
        for m in self.measure.keys():
            self.measure[m] = []
        self.rmp = []  # resting membrane potential during sequence

        # -----scripting-------
        self.script = None
        self.script_name = None

        # --------------graphical elements-----------------
        self._sizeHint = (1280, 900)  # try to establish size of window
        self.ctrl_widget = QtGui.QWidget()
        self.ctrl = ctrlTemplate.Ui_Form()
        self.ctrl.setupUi(self.ctrl_widget)
        self.results_widget = QtGui.QWidget()
        self.results = resultsTemplate.Ui_ResultsDialogBox()
        self.results.setupUi(self.results_widget)
        self.scripts_widget = QtGui.QWidget()
        self.scripts_form = scriptTemplate.Ui_Form()
        self.scripts_form.setupUi(self.scripts_widget)
        self.main_layout = pg.GraphicsView()  # instead of GraphicsScene?
        # make fixed widget for the module output
        self.widget = QtGui.QWidget()
        self.grid_layout = QtGui.QGridLayout()
        self.widget.setLayout(self.grid_layout)
        self.grid_layout.setContentsMargins(4, 4, 4, 4)
        self.grid_layout.setSpacing(1)
        # Setup basic GUI
        self._elements_ = OrderedDict([
            ('File Loader',
             {'type': 'fileInput', 'size': (150, 50), 'host': self}),
            ('Scripts',
             {'type': 'ctrl', 'object': self.scripts_widget, 'host': self,
              'size': (160, 700)}),
            ('Results',
             {'type': 'ctrl', 'object': self.results_widget, 'pos': ('above', 'Scripts'),
              'size': (160, 700)}),
            ('Parameters',
             {'type': 'ctrl', 'object': self.ctrl_widget, 'pos': ('above', 'Results'),
              'size': (160, 700)}),
            ('Plots',
             {'type': 'ctrl', 'object': self.widget, 'pos': ('right',),
              'size': (400, 700)}),
        ])
        self.initializeElements()  # exists as part of analysishost.
        self.file_loader_instance = self.getElement('File Loader', create=True)
        # grab input form the "Ctrl" window
        self.ctrl.PSPReversal_Update.clicked.connect(self.update_all_analysis)
        self.ctrl.PSPReversal_PrintResults.clicked.connect(self.print_analysis)
        self.ctrl.PSPReversal_KeepAnalysis.clicked.connect(self.reset_keep_analysis)
        self.ctrl.PSPReversal_rePlotData.clicked.connect(self.plot_traces)
        # self.ctrl.get_file_information.clicked.connect(self.get_file_information)
        self.ctrl.PSPReversal_Alternation.setTristate(False)
        self.ctrl.PSPReversal_Alternation.stateChanged.connect(self.get_alternation)
        self.ctrl.PSPReversal_SubBaseline.stateChanged.connect(self.get_baseline)
        [self.ctrl.PSPReversal_RMPMode.currentIndexChanged.connect(x)
         for x in [self.update_rmp_analysis, self.count_spikes]]
        self.ctrl.PSPReversal_Junction.valueChanged.connect(self.set_junction)
        self.ctrl.dbStoreBtn.clicked.connect(self.dbstore_clicked)

        self.scripts_form.PSPReversal_ScriptFile_Btn.clicked.connect(self.read_script)
        self.scripts_form.PSPReversal_ScriptRerun_Btn.clicked.connect(self.rerun_script)
        self.scripts_form.PSPReversal_ScriptPrint_Btn.clicked.connect(self.print_script_output)
        self.scripts_form.PSPReversal_ScriptCopy_Btn.clicked.connect(self.copy_script_output)
        self.scripts_form.PSPReversal_ScriptAppend_Btn.clicked.connect(self.append_script_output)

        self.clear_results()
        self.layout = self.getElement('Plots', create=True)

        # instantiate the graphs using a gridLayout
        self.data_plot = pg.PlotWidget()
        self.grid_layout.addWidget(self.data_plot, 0, 0, 3, 1)
        self.label_up(self.data_plot, 'T (s)', 'V (V)', 'Data')

        self.cmd_plot = pg.PlotWidget()
        self.grid_layout.addWidget(self.cmd_plot, 3, 0, 1, 1)
        self.label_up(self.cmd_plot, 'T (s)', 'I (A)', 'Command')

        self.rmp_plot = pg.PlotWidget()
        self.grid_layout.addWidget(self.rmp_plot, 1, 1, 1, 1)
        self.label_up(self.rmp_plot, 'T (s)', 'V (mV)', 'Holding')

        self.unused_plot = pg.PlotWidget()
        self.grid_layout.addWidget(self.unused_plot, 2, 1, 1, 1)
        # self.label_up(self.unused_plot, 'I (pA)', 'Fsl/Fisi (ms)', 'FSL/FISI')

        self.command_plot = pg.PlotWidget()
        self.grid_layout.addWidget(self.command_plot, 3, 1, 1, 1)
        self.label_up(self.command_plot, 'T (s)', 'V (mV)', 'Commands (T)')

        self.iv_plot = pg.PlotWidget()
        self.grid_layout.addWidget(self.iv_plot, 0, 1, 1, 1)
        self.label_up(self.iv_plot, 'I (pA)', 'V (V)', 'I-V')
        for row, s in enumerate([20, 10, 10, 10]):
            self.grid_layout.setRowStretch(row, s)

            #    self.tailPlot = pg.PlotWidget()
            #    self.grid_layout.addWidget(self.fslPlot, 3, 1, 1, 1)
            #    self.label_up(self.tailPlot, 'V (V)', 'I (A)', 'Tail Current')

        # Add color scales and some definitions
        self.colors = ['w', 'g', 'b', 'r', 'y', 'c']
        self.symbols = ['o', 's', 't', 'd', '+']
        self.color_list = itertools.cycle(self.colors)
        self.symbol_list = itertools.cycle(self.symbols)
        self.color_scale = pg.GradientLegend((20, 150), (-10, -10))
        self.data_plot.scene().addItem(self.color_scale)

    def clear_results(self):
        """
        clearResults resets variables.

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
        self.sequence = ''
        for m in self.measure.keys():
            self.measure[m] = []
        self.rmp = []  # resting membrane potential during sequence
        self.CellSummary = {}
        self.win1fits = None

    def reset_keep_analysis(self):
        self.keep_analysis_count = 0  # reset counter.

    def get_alternation(self):
        self.alternation = self.ctrl.PSPReversal_Alternation.isChecked()

    def get_baseline(self):
        self.baseline = self.ctrl.PSPReversal_SubBaseline.isChecked()

    def set_junction(self):
        self.junction = self.ctrl.PSPReversal_Junction.value()

    def initialize_regions(self):
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
            self.regions['lrwin1'] = {'name': 'win1',
                                      'region': pg.LinearRegionItem([0, 1],
                                                                    brush=pg.mkBrush(0, 255, 0, 50.)),
                                      'plot': self.data_plot,
                                      'state': self.ctrl.PSPReversal_showHide_lrwin1,
                                      'shstate': True,  # keep internal copy of the state
                                      'mode': self.ctrl.PSPReversal_win1mode,
                                      'start': self.ctrl.PSPReversal_win1TStart,
                                      'stop': self.ctrl.PSPReversal_win1TStop,
                                      'updater': self.update_win_analysis,
                                      'units': 'ms'}
            self.regions['lrwin0'] = {'name': 'win0',
                                      'region': pg.LinearRegionItem([0, 1],
                                                                    brush=pg.mkBrush(255, 255, 0, 50.)),
                                      'plot': self.data_plot,
                                      'state': self.ctrl.PSPReversal_showHide_lrwin1,
                                      'shstate': True,  # keep internal copy of the state
                                      'mode': self.ctrl.PSPReversal_win1mode,
                                      'start': self.ctrl.PSPReversal_leakTStart,
                                      'stop': self.ctrl.PSPReversal_leakTStop,
                                      'updater': self.update_win_analysis,
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
                                      'updater': self.update_win_analysis,
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
                                     'updater': self.update_rmp_analysis,
                                     'units': 'ms'}
            self.ctrl.PSPReversal_showHide_lrrmp.region = self.regions['lrrmp']['region']  # save region with checkbox
            # self.regions['lrleak'] = {'name': 'leak',
            #                           'region': pg.LinearRegionItem([0, 1],
            #                                                         brush=pg.mkBrush
            #                                                         (255, 0, 255, 25.)),
            #                           'plot': self.iv_plot,
            #                           'shstate': True,  # keep internal copy of the state
            #                           'state': self.ctrl.PSPReversal_subLeak,
            #                           'mode': None,
            #                           'start': self.ctrl.PSPReversal_leakTStart,
            #                           'stop': self.ctrl.PSPReversal_leakTStop,
            #                           'updater': self.update_all_analysis,
            #                           'units': 'mV'}
            # self.ctrl.PSPReversal_subLeak.region = self.regions['lrleak']['region']  # save region with checkbox
            # establish that measurement is on top, exclusion is next, and reference is on bottom
            self.regions['lrwin0']['region'].setZValue(500)
            self.regions['lrwin1']['region'].setZValue(100)
            self.regions['lrwin2']['region'].setZValue(1000)
            for reg in self.regions.keys():
                self.regions[reg]['plot'].addItem(self.regions[reg]['region'])
                self.regions[reg]['state'].clicked.connect(functools.partial(self.show_or_hide,
                                                                             lrregion=reg))
                self.regions[reg]['region'].sigRegionChangeFinished.connect(
                    functools.partial(self.regions[reg]['updater'], region=self.regions[reg]['name']))
                if self.regions[reg]['mode'] is not None:
                    self.regions[reg]['mode'].currentIndexChanged.connect(self.update_all_analysis)
            self.regions_exist = True
        for reg in self.regions.keys():
            for s in ['start', 'stop']:
                self.regions[reg][s].setSuffix(' ' + self.regions[reg]['units'])

                ######
                # The next set of short routines control showing and hiding of regions
                # in the plot of the raw data (traces)
                ######

    def show_or_hide(self, lrregion=None, forcestate=None):
        if lrregion is None:
            print('PSPReversal:show_or_hide:: lrregion is None')
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

    def uniq(self, inlist):
        # order preserving detection of unique values in a list
        uniques = []
        for item in inlist:
            if item not in uniques:
                uniques.append(item)
        return uniques

    def get_file_information(self, default_dh=None):
        """
        get_file_information reads the sequence information from the
        currently selected data file

        Two-dimensional sequences are supported.

        """
        dh = self.file_loader_instance.selectedFiles()
        if len(dh) == 0:  # when using scripts, the fileloader may not know...
            if default_dh is not None:
                dh = default_dh
            else:
                return
#        print 'getfileinfo dh: ', dh
        dh = dh[0]  # only the first file
        dirs = dh.subDirs()
        self.sequence = self.dataModel.listSequenceParams(dh)
        keys = self.sequence.keys()
        leftseq = [str(x) for x in self.sequence[keys[0]]]
        if len(keys) > 1:
            rightseq = [str(x) for x in self.sequence[keys[1]]]
        else:
            rightseq = []
        leftseq.insert(0, 'All')
        rightseq.insert(0, 'All')
        self.ctrl.PSPReversal_Sequence1.clear()
        self.ctrl.PSPReversal_Sequence2.clear()
        self.ctrl.PSPReversal_Sequence1.addItems(leftseq)
        self.ctrl.PSPReversal_Sequence2.addItems(rightseq)
        self.dirsSet = dh  # not sure we need this anymore...

    def cell_summary(self, dh):
        # other info into a dictionary
        self.CellSummary['Day'] = self.dataModel.getDayInfo(dh)
        self.CellSummary['Slice'] = self.dataModel.getSliceInfo(dh)
        self.CellSummary['Cell'] = self.dataModel.getCellInfo(dh)
        self.CellSummary['ACSF'] = self.dataModel.getACSF(dh)
        self.CellSummary['Internal'] = self.dataModel.getInternalSoln(dh)
        self.CellSummary['Temp'] = self.dataModel.getTemp(dh)
        self.CellSummary['CellType'] = self.dataModel.getCellType(dh)
        # print self.CellSummary

    def loadFileRequested(self, dh):
        """
        loadFileRequested is called by file loader when a file is requested.
        dh is the handle to the currently selected directory (or directories)

        Loads all of the successive records from the specified protocol.
        Stores ancillary information from the protocol in class variables.
        Extracts information about the commands, sometimes using a rather
        simplified set of assumptions.
        modifies: plots, sequence, data arrays, data mode, etc.
        Returns: True if successful; otherwise raises an exception
        """
#        print 'loadfilerequested dh: ', dh
        if len(dh) == 0:
            raise Exception("PSPReversal::loadFileRequested: " +
                            "Select an IV protocol directory.")
        if len(dh) != 1:
            raise Exception("PSPReversal::loadFileRequested: " +
                            "Can only load one file at a time.")
        self.clear_results()
        if self.current_dirhandle != dh[0]:  # is this the current file/directory?
            self.get_file_information(default_dh=dh)  # No, get info from most recent file requested
            self.current_dirhandle = dh[0]  # this is critical!
        dh = dh[0]  # just get the first one
        self.cell_summary(dh)  # get other info as needed for the protocol
        ct = self.CellSummary['Cell']['__timestamp__']
        pt = dh.info()['__timestamp__']
        self.CellSummary['ElapsedTime'] = pt-ct  # save elapsed time between cell opening and protocol start
        #        self.current_dirhandle = dh  # save as our current one.
        self.protocolfile = ''
        self.data_plot.clearPlots()
        self.cmd_plot.clearPlots()
        self.filename = dh.name()
        dirs = dh.subDirs()
        (date, slice, cell, proto, p3) = self.file_cell_protocol()
        self.CellSummary['CellID'] = os.path.join(date, slice, cell)  # use this as the "ID" for the cell later on
        self.protocolfile = proto
        subs = re.compile('[\/]')
        self.protocolfile = re.sub(subs, '-', self.protocolfile)
        self.protocolfile = self.protocolfile + '.pdf'
        self.commonPrefix = self.filename
        traces = []
        cmd = []
        cmd_wave = []
        data = []
        self.tx = None
        self.values = []
        self.sequence = self.dataModel.listSequenceParams(dh)  # already done in 'getfileinfo'
        self.trace_times = np.zeros(0)

        # builidng command voltages - get amplitudes to clamp
        clamp = ('Clamp1', 'Pulse_amplitude')
        reps = ('protocol', 'repetitions')
        led = ('LED-Blue', 'Command.PulseTrain_amplitude')
        # repeat patterns for LED on/off
        if led in self.sequence:  # first in alternation
            self.ledseq = self.sequence[led]
            self.nledseq = len(self.ledseq)
            sequence_values = [x for x in range(self.nledseq)]

        if clamp in self.sequence:
            self.clampValues = self.sequence[clamp]
            self.nclamp = len(self.clampValues)
            sequence_values = [x for x in self.clampValues for y in sequence_values]
        else:
            sequence_values = []
            nclamp = 0

        # if sequence has repeats, build pattern
        if reps in self.sequence:
            self.repc = self.sequence[reps]
            self.nrepc = len(self.repc)
            sequence_values = [x for y in range(self.nrepc) for x in sequence_values]

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
        for i, directory_name in enumerate(dirs):
            data_dir_handle = dh[directory_name]
            try:
                data_file_handle = self.dataModel.getClampFile(data_dir_handle)
                # Check if no clamp file for this iteration of the protocol
                # (probably the protocol was stopped early)
                if data_file_handle is None:
                    print ('PSPReversal::loadFileRequested: ',
                           'Missing data in %s, element: %d' % (directory_name, i))
                    continue
            except:
                print("Error loading data for protocol %s:"
                      % directory_name)
                continue  # If something goes wrong here, we just carry on
            data_file = data_file_handle.read()
            self.devicesUsed = self.dataModel.getDevices(data_dir_handle)
            self.amp_settings = self.dataModel.getWCCompSettings(data_file)
            self.clamp_state = self.dataModel.getClampState(data_file)
            # print self.devicesUsed
            cmd = self.dataModel.getClampCommand(data_file)
            data = self.dataModel.getClampPrimary(data_file)
            self.data_mode = self.dataModel.getClampMode(data)
            if self.data_mode is None:
                self.data_mode = self.ic_modes[0]  # set a default mode
            if self.data_mode in ['ic', 'vc']:  # lower case means model was run
                self.modelmode = True
            self.ctrl.PSPReversal_dataMode.setText(self.data_mode)
            # Assign scale factors for the different modes to display data rationally
            if self.data_mode in self.ic_modes:
                self.cmdscaleFactor = 1e12
                self.cmdUnits = 'pA'
            elif self.data_mode in self.vc_modes:
                self.cmdUnits = 'mV'
                self.cmdscaleFactor = 1e3
            else:  # data mode not known; plot as voltage
                self.cmdUnits = 'V'
                self.cmdscaleFactor = 1.0
            self.holding = self.dataModel.getClampHoldingLevel(data_file_handle)

            if 'LED-Blue' in self.devicesUsed.keys():
                led_pulse_train_command = data_dir_handle.parent().info()['devices']['LED-Blue']['channels']['Command']
                led_pulse_train_info = led_pulse_train_command['waveGeneratorWidget']['stimuli']['PulseTrain']
                self.led_info = {}
                for k in led_pulse_train_info.keys():
                    if k in ['type']:
                        self.led_info[k] = led_pulse_train_info[k]
                    else:
                        self.led_info[k] = led_pulse_train_info[k]['value']

            # only accept data in a particular range
            if self.ctrl.PSPReversal_IVLimits.isChecked():
                cval = self.cmdscaleFactor * sequence_values[i]
                cmin = self.ctrl.PSPReversal_IVLimitMin.value()
                cmax = self.ctrl.PSPReversal_IVLimitMax.value()
                if cval < cmin or cval > cmax:
                    continue  # skip adding the data to the arrays
            # store primary channel data and read command amplitude
            info1 = data.infoCopy()
            start_time = 0.0
            if 'startTime' in info1[0].keys():
                start_time = info1[0]['startTime']
            elif 'startTime' in info1[1]['DAQ']['command'].keys():
                start_time = info1[1]['DAQ']['command']['startTime']
            else:
                pass

            self.trace_times = np.append(self.trace_times, start_time)

            traces.append(data.view(np.ndarray))
            cmd_wave.append(cmd.view(np.ndarray))

            if len(sequence_values) > 0:
                self.values.append(sequence_values[i])
            else:
                self.values.append(cmd[len(cmd) / 2])
            i += 1
        #print 'PSPReversal::loadFileRequested: Done loading files'
        self.ctrl.PSPReversal_Holding.setText('%.1f mV' % (float(self.holding) * 1e3))
        if traces is None or len(traces) == 0:
            print "PSPReversal::loadFileRequested: No data found in this run..."
            return False
        if self.amp_settings['WCCompValid']:
            if self.amp_settings['WCEnabled'] and self.amp_settings['CompEnabled']:
               # print 'wc resistance, Ohms: ', self.amp_settings['WCResistance']
               # print 'Correction %: ', self.amp_settings['CompCorrection']
                self.r_uncomp = self.amp_settings['WCResistance'] * (1.0 - self.amp_settings['CompCorrection'] / 100.)
            else:
                self.r_uncomp = 0.
        self.ctrl.PSPReversal_R_unCompensated.setValue(self.r_uncomp * 1e-6)  # convert to Mohm to display
        self.ctrl.PSPReversal_R_unCompensated.setSuffix(u" M\u2126")

        # put relative to the start
        self.trace_times -= self.trace_times[0]
        traces = np.vstack(traces)
        self.cmd_wave = np.vstack(cmd_wave)
        self.tx = np.array(cmd.xvals('Time'))
        commands = np.array(self.values)
        self.color_scale.setIntColorScale(0, i, maxValue=200)
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
        if self.data_mode in self.ic_modes:
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
        self.sample_interval = 1.0 / sfreq
        self.makemap_symbols()
        if self.ctrl.PSPReversal_KeepT.isChecked() is False:
            self.tstart += self.sample_interval
            self.tend += self.sample_interval
        if self.data_mode in self.ic_modes:
            # for adaptation ratio:
            self.update_all_analysis()
        if self.data_mode in self.vc_modes:
            self.cmd = commands
            self.spikecount = np.zeros(len(np.array(self.values)))

        # and also plot
        self.plot_traces()
        self._host_.dockArea.findAll()[1]['Parameters'].raiseDock()  # parameters to the top
        if self.ctrl.PSPReversal_KeepT.isChecked():  # times already set, so go forward with analysis
            self.update_all_analysis()  # run all current analyses
            self.print_analysis()
        return True

    def file_information(self, dh):
        pass

    def file_cell_protocol(self):
        """
        file_cell_protocol breaks the current filename down and returns a
        tuple: (date, cell, protocol)

        last argument returned is the rest of the path...
        """
        (p0, proto) = os.path.split(self.filename)
        (p1, cell) = os.path.split(p0)
        (p2, slice) = os.path.split(p1)
        (p3, date) = os.path.split(p2)
        return (date, slice, cell, proto, p3)

    def plot_traces(self):
        """
        Plot the current data traces.
        :return: nothing
        """
        if self.ctrl.PSPReversal_KeepAnalysis.isChecked():
            self.keep_analysis_count += 1
        else:
            self.keep_analysis_count = 0  # always make sure is reset
            # this is the only way to reset iterators.
            self.color_list = itertools.cycle(self.colors)
            self.symbol_list = itertools.cycle(self.symbols)
        self.makemap_symbols()

        ntr = self.traces.shape[0]
        self.data_plot.setDownsampling(auto=True, mode='mean')
        self.data_plot.setClipToView(True)
        self.cmd_plot.setDownsampling(auto=True, mode='mean')
        self.cmd_plot.setClipToView(True)
        cmdindxs = np.unique(self.cmd)  # find the unique voltages
        colindxs = [int(np.where(cmdindxs == self.cmd[i])[0]) for i in range(len(self.cmd))]  # make a list to use
        for i in range(ntr):
            self.data_plot.plot(self.tx, self.traces[i],
                                pen=pg.intColor(colindxs[i], len(cmdindxs), maxValue=255))
            self.cmd_plot.plot(self.tx, self.cmd_wave[i],
                               pen=pg.intColor(colindxs[i], len(cmdindxs), maxValue=255),
                               autoDownsample=True, downsampleMethod='mean')

        if self.data_mode in self.ic_modes:
            self.label_up(self.data_plot, 'T (s)', 'V (V)', 'Data')
            self.label_up(self.cmd_plot, 'T (s)', 'I (%s)' % self.cmdUnits, 'Data')
        elif self.data_mode in self.vc_modes:  # voltage clamp
            self.label_up(self.data_plot, 'T (s)', 'I (A)', 'Data')
            self.label_up(self.cmd_plot, 'T (s)', 'V (%s)' % self.cmdUnits, 'Data')
        else:  # mode is not known: plot both as V
            self.label_up(self.data_plot, 'T (s)', 'V (V)', 'Data')
            self.label_up(self.cmd_plot, 'T (s)', 'V (%s)' % self.cmdUnits, 'Data')

        self.setup_regions()

    def setup_regions(self):
        self.initialize_regions()  # now create the analysis regions
        if self.ctrl.PSPReversal_KeepT.isChecked() is False:
            if 'LED-Blue' in self.devicesUsed:
                tdur1 = 0.1
                tstart1 = self.led_info['start'] - tdur1
                tdur2 = self.led_info['length'] * 5.  # go 5 times the duration.
                tstart2 = self.led_info['start']
                if tstart2 + tdur2 > self.tend:
                    tdur2 = self.tend - tstart2  # restrict duration to end of the trace
            else:
                tstart1 = self.tstart
                tdur1 = self.tstart / 5.0
                tdur2 = self.tdur / 2.0
                tstart2 = self.tend - tdur2

            tend = self.tend - 0.001
            # reference window
            self.regions['lrwin1']['region'].setRegion([tstart1,
                                                        tstart1 + tdur1])
            # exclusion, same as data:
            self.regions['lrwin0']['region'].setRegion([tstart2,
                                                        tstart2 + tdur2])
            # meausurement:
            self.regions['lrwin2']['region'].setRegion([tstart2,
                                                        tstart2 + tdur2])
            # self.lrtau.setRegion([self.tstart+(self.tdur/5.0)+0.005,
            #                      self.tend])
            self.regions['lrrmp']['region'].setRegion([1.e-4, self.tstart * 0.9])  # rmp window

        # leak is on voltage (or current), not times
        # self.regions['lrleak']['region'].setRegion(
        #     [self.regions['lrleak']['start'].value(),  # self.ctrl.PSPReversal_LeakMin.value(),
        #      self.regions['lrleak']['stop'].value()])  # self.ctrl.PSPReversal_LeakMax.value()])
        for r in ['lrwin0', 'lrwin1', 'lrwin2', 'lrrmp']:
            self.regions[r]['region'].setBounds([0., np.max(self.tx)])  # limit regions to data

    def update_all_analysis(self, region=None):
        """
        update_all_analysis: re-reads the time parameters, counts the spikes
            and forces an update of all the analysis in the process...
        :param region: nominal analysis window region (not used)
        :return: nothing
        """
        self.read_parameters(clear_flag=True, pw=True)
        self.update_rmp_analysis()  # rmp must be done separately
        self.count_spikes()

    def make_cell_summary(self):
        (date, slice, cell, proto, p2) = self.file_cell_protocol()
        self.cell_summary(self.current_dirhandle)
        self.CellSummary['CellID'] = str(date+'/'+slice+'/'+cell)
        self.CellSummary['Protocol'] = proto

        jp = float(self.junction)
        ho = float(self.holding) * 1e3  # convert to mV
        self.CellSummary['JP'] = jp
        self.CellSummary['HoldV'] = ho
        vc = np.array(self.win2IV[0]+jp+ho)
        im = np.array(self.win2IV[1])
        imsd = np.array(self.win2IV[2])
        polyorder = 3
        p = np.polyfit(vc, im, polyorder)  # 3rd order polynomial
        for n in range(polyorder+1):
            self.CellSummary['p'+str(n)] = p[n]
        # find the roots
        r = np.roots(p)
        reversal = [None]*polyorder
        for i in range(0, polyorder):
            reversal[i] = {'value': r[i], 'valid': False}
        anyrev = False
        revvals = ''
        revno = []
        for n in range(len(reversal)):  # print only the valid reversal values, which includes real, not imaginary roots
            if ((np.abs(np.imag(reversal[n]['value'])) == 0.0) and (-100. < np.real(reversal[n]['value']) < 40.)):
                reversal[n]['valid'] = True
                if anyrev:
                    revvals += ', '
                revvals += ('{:5.1f}'.format(float(np.real(reversal[n]['value']))))
                revno.append(np.real(reversal[n]['value']))
                anyrev = True
        if not anyrev:
            revvals = 'Not fnd'
        self.CellSummary['revvals'] = revvals
        self.CellSummary['Erev'] = revno[0]
        # computes slopes at Erev[0] and at -60 mV (as a standard)
        p1 = np.polyder(p,1)
        p60 = np.polyval(p1,-60.)
        perev = np.polyval(p1, revno[0])
        self.CellSummary['gsyn_60'] = p60 * 1e3  # im in nA, vm in mV, g converted to nS
        self.CellSummary['gsyn_Erev'] = perev * 1e3  # nS
        self.CellSummary['I_ionic-'] = np.min(self.measure['win1'])*1e9  # nA
        self.CellSummary['I_ionic+'] = np.max(self.measure['win1'])*1e9  # nA

        self.CellSummary['LPF'] = self.clamp_state['LPFCutoff'] * 1e-3  # kHz
        self.CellSummary['Gain'] = self.clamp_state['primaryGain']
        self.CellSummary['Rs'] = self.amp_settings['WCResistance'] * 1e-6  # Mohm
        self.CellSummary['Cm'] = self.amp_settings['WCCellCap'] * 1e12  # pF
        self.CellSummary['Comp'] = self.amp_settings['CompCorrection']
        self.CellSummary['BW'] = self.amp_settings['CompBW'] * 1e-3  # kHz
        self.CellSummary['Ru'] = self.r_uncomp * 1e-6  # Mohm
        self.CellSummary['ILeak'] = self.averageRMP*1e9  # express in nA

    def print_analysis(self):
        """
        Print the CCIV summary information (Cell, protocol, etc)
        Printing goes to the results window, where the data can be copied
        to another program like a spreadsheet.
        :return: html-decorated text
        """
        self.make_cell_summary()
        (date, slice, cell, proto, p2) = self.file_cell_protocol()
        # The day summary may be missing elements, so we need to create dummies (dict is read-only)
        day = {}
        for x in ['age', 'weight', 'sex']:  # check to see if these are filled out
            if x not in self.CellSummary.keys():
                day[x] = 'unknown'
               # self.CellSummary['Day'][x] = day[x]
            else:
                day[x] = self.CellSummary['Day'][x]
        for cond in ['ACSF', 'Internal', 'Temp']:
            if self.CellSummary[cond] == '':
                self.CellSummary[cond] = 'unknown'

        # format output in html
        rtxt = '<font face="monospace, courier">'  # use a monospaced font.
        rtxt += '<div style="white-space: pre;">'  # css to force repsect of spaces in text
        rtxt += ("{:^15s}  {:^5s}  {:^4s}  {:^12s}<br>".format
                 ("Date", "Slice", "Cell", "E<sub>rev</sub>"))
        rtxt += ("<b>{:^15s}  {:^5s}  {:^4s}  {:^12s}</b><br>".format
                 (date, slice[-3:], cell[-3:], self.CellSummary['Erev']))
        rtxt += ('{:<8s}: <b>{:<32s}</b><br>'.format('Protocol', proto))
        rtxt += ('{:^8s}\t{:^8s}\t{:^8s}\t{:^8s}<br>'.format
                 ('Temp', 'Age', 'Weight', 'Sex'))
        rtxt += ('{:^8s}\t{:^8s}\t{:^8s}\t{:^8s}<br>'.format
                 (self.CellSummary['Temp'], day['age'], day['weight'], day['sex']))
        rtxt += ('{:<8s}: {:<32s}<br>'.format('ACSF', self.CellSummary['ACSF']))
        rtxt += ('{:<8s}: {:<32s}<br>'.format('Internal', self.CellSummary['Internal']))
        if self.amp_settings['WCCompValid'] is True:
            rtxt += (u'{:<4s} {:5.2f} {:2s} '.format('LPF', self.clamp_state['LPFCutoff'] * 1e-3, 'kHz'))
            rtxt += (u'{:<4s} {:5.2f} {:2s}<br>'.format('Gain', self.clamp_state['primaryGain'], ''))
            rtxt += (u'{:<4s} {:4.1f} {:2s} '.format('Rs', self.amp_settings['WCResistance'] * 1e-6, u"M\u2126"))
            rtxt += (u'{:<4s} {:4.1f} {:2s}<br>'.format('Cm', self.amp_settings['WCCellCap'] * 1e12, 'pF'))
            rtxt += (u'{:<4s} {:4.0f} {:<2s} '.format('Comp', self.amp_settings['CompCorrection'], '%'))
            rtxt += (u'{:<4s} {:4.1f} {:3s}<br>'.format('BW', self.amp_settings['CompBW'] * 1e-3, 'kHz'))
            rtxt += (u'{:<4s} {:5.2f} {:2s}<br>'.format('Ru', self.r_uncomp * 1e-6, u"M\u2126"))
        else:
            rtxt += ('No WC or Rs Compensation')

        rtxt += ('{:<8s}: [{:5.1f}-{:5.1f}{:2s}] mode: {:<12s}<br>'.format(
            'Win 1', self.regions['lrwin1']['start'].value(), self.regions['lrwin1']['stop'].value(),
            self.regions['lrwin1']['units'], self.regions['lrwin1']['mode'].currentText()))
        rtxt += ('{:<8s}: [{:5.1f}-{:5.1f}{:2s}] mode: {:<12s}<br>'.format(
            'Win 2', self.regions['lrwin2']['start'].value(), self.regions['lrwin2']['stop'].value(),
            self.regions['lrwin2']['units'], self.regions['lrwin2']['mode'].currentText()))

        rtxt += 'HP: {:5.1f} mV  JP: {:5.1f} mV<br>'.format(self.CellSummary['HoldV'], self.CellSummary['JP'])
        if self.diffFit is not None:
            rtxt += ('{0:<5s}: {1}<br>').format('Poly', ''.join('{:5.2e} '.format(a) for a in self.diffFit))
        rtxt += ('-' * 40) + '<br>'
        rtxt += ('<b>{:2s}</b> Comp: {:<3s} <br>'.  # {:>19s}:{:>4d}<br>'.
                 format('IV',
                        ('Off', 'On ')[self.ctrl.PSPReversal_RsCorr.isChecked()]))
        # 'Repeats', self.nrepc))
        if self.ctrl.PSPReversal_RsCorr.isChecked():
            vtitle = 'mV (corr)'
        else:
            vtitle = 'mV (cmd)'
            # rtxt += '<i>{:>9s} </i>'.format('mV (cmd)')
        rtxt += '<i>{:>10s} {:>9s} {:>9s} {:>6s}</i><br>'.format(vtitle, 'nA', 'SD', 'N')
        # print self.measure.keys()
        for i in range(len(self.win2IV[0])):
            if self.ctrl.PSPReversal_RsCorr.isChecked():
                rtxt += (' {:>9.1f} '.format(self.win2IV[0][i] + self.CellSummary['JP'] + self.CellSummary['HoldV']))
            else:
                rtxt += (' {:>9.1f} '.format(self.win2IV[3][i] + self.CellSummary['JP'] + self.CellSummary['HoldV']))
            rtxt += ('{:>9.3f} {:>9.3f} {:>6d}<br>'.format(self.win2IV[1][i], self.win2IV[2][i], self.nrepc))
        rtxt += ('-' * 40) + '<br></div></font>'
        self.results.resultsPSPReversal_text.setText(rtxt)
        # now raise the dock for visibility
        self._host_.dockArea.findAll()[1]['Results'].raiseDock()
        return rtxt

    def remove_html_markup(self, s):
        """
        simple html stripper for our own generated text (output of analysis, above).
        This is not generally useful but is better than requiring yet another library
        for the present purpose.
        Taken from a stackoverflow answer.
        :param s: input html marked text
        :return: cleaned text
        """
        tag = False
        quote = False
        out = ""
        s = s.replace('<br>', '\n') # first just take of line breaks
        for c in s:
                if c == '<' and not quote:
                    tag = True
                elif c == '>' and not quote:
                    tag = False
                elif (c == '"' or c == "'") and tag:
                    quote = not quote
                elif not tag:
                    out = out + c

        return out

    def read_script(self, name=''):
        if not name:
            self.script_name = '/Users/pbmanis/Desktop/acq4_scripts/PSPReversal.cfg'

        self.script = configfile.readConfigFile(self.script_name)
        if self.script is None:
            print 'failed to read script'
            return
#        print 'script ok:', self.script
        fh = open(self.script_name)  # read the raw text file too
        txt = fh.read()
        fh.close()
        self.scripts_form.PSPReversal_Script_TextEdit.setPlainText(txt)  # show script
        self.scripts_form.PSPReversal_ScriptFile.setText(self.script_name)
        if self.validate_script():
            self.run_script()
        else:
            raise Exception("Script failed validation - see terminal output")

    def rerun_script(self):
        if self.validate_script():
            self.run_script()
        else:
            raise Exception("Script failed validation - see terminal output")

    def validate_script(self):
        """
        validate the current script - by checking the existence of the files needed for the analysis

        :return: False if cannot find files; True if all are found
        """
        if self.script['module'] != 'PSPReversal':
            print 'script is not for PSPReversal (found %s)', self.script['module']
            return False
        all_found = True
        for c in self.script['Cells']:
            if self.script['Cells'][c]['include'] is False:
                continue
            sortedkeys = sorted(self.script['Cells'][c]['manip'].keys())  # sort by order of recording
            for p in sortedkeys:
                pr = self.script['protocol'] + '_' + p  # add the underscore here
                fn = os.path.join(c, pr)
                dm_selected_file = self.dataManager().selectedFile().name()
                fullpath = os.path.join(dm_selected_file, fn)
                file_ok = os.path.exists(fullpath)
                #if file_ok:
                #    print('File found: {:s}'.format(fullpath))
                if not file_ok:
                    print '  current dataManager self.dm points to file: ', dm_selected_file
                    print '  and file not found was: ', fullpath
                    all_found = False
                #else:
                #    print 'file found ok: %s' % fullpath
        return all_found

    def run_script(self):
        if self.script['testfiles']:
            return
        settext = self.scripts_form.PSPReversal_ScriptResults_text.setPlainText
        apptext = self.scripts_form.PSPReversal_ScriptResults_text.appendPlainText
        self.textout = ('Script File: {:<32s}'.format(self.script_name))
        settext(self.textout)
        script_header = True  # reset the table to a print new header for each cell
        for cell in self.script['Cells']:
            thiscell = self.script['Cells'][cell]
            if thiscell['include'] is False:
            #    print 'file not included'
                continue
            sortedkeys = sorted(thiscell['manip'].keys())  # sort by order of recording (# on protocol)
            for p in sortedkeys:
                if thiscell['manip'][p] not in self.script['datafilter']:  # pick out steady-state conditions
                 #   print 'p: %s not in data: ' % (thiscell['manip'][p]), self.script['datafilter']
                    continue
                #print 'working on %s' % thiscell['manip'][p]
                pr = self.script['protocol'] + '_' + p  # add the underscore here
                fn = os.path.join(cell, pr)
                dm_selected_file = self.dataManager().selectedFile().name()
                fullpath = os.path.join(dm_selected_file, fn)
                file_ok = os.path.exists(fullpath)
                if not file_ok:  # get the directory handle and take it from there
                    continue
                dh = self.dataManager().manager.dirHandle(fullpath)
                if not self.loadFileRequested([dh]):  # note: must pass a list
                    print 'failed to load requested file: ', fullpath
                    continue  # skip bad sets of records...
                apptext(('Protocol: {:<s} <br>Manipulation: {:<s}'.format(pr, thiscell['manip'][p])))
                self.CellSummary['Drugs'] = thiscell['manip'][p]
                alt_flag = bool(thiscell['alternation'])
                self.ctrl.PSPReversal_Alternation.setChecked((QtCore.Qt.Unchecked, QtCore.Qt.Checked)[alt_flag])
                if 'junctionpotential' in thiscell:
                   self.ctrl.PSPReversal_Junction.setValue(float(thiscell['junctionpotential']))
                else:
                    self.ctrl.PSPReversal_Junction.setValue(float(self.script['global_jp']))
                # set the analysis if it is identified
                if 'win1_mode' in thiscell:
                    r = self.ctrl.PSPReversal_win1mode.findText(thiscell['win1_mode'])
                    if r >= 0:
                        self.ctrl.PSPReversal_win1mode.setCurrentIndex(r)
                    else:
                        print 'win 1 analysis mode not recognized: %s' % thiscell['win1_mode']
                else:
                    if 'global_win1_mode' in self.script:
                        r = self.ctrl.PSPReversal_win1mode.findText(self.script['global_win1_mode'])
                        if r >= 0:
                            self.ctrl.PSPReversal_win1mode.setCurrentIndex(r)
                    else:
                        print 'win 1 global analysis mode not recognized: %s' % self.script['global_win1_mode']

                if 'win2_mode' in thiscell:
                    r = self.ctrl.PSPReversal_win1mode.findText(thiscell['win2_mode'])
                    if r >= 0:
                        self.ctrl.PSPReversal_win1mode.setCurrentIndex(r)
                    else:
                        print 'win 2 analysis mode not recognized: %s' % thiscell['win2_mode']
                else:
                    if 'global_win2_mode' in self.script:
                        r = self.ctrl.PSPReversal_win1mode.findText(self.script['global_win2_mode'])
                        if r >= 0:
                            self.ctrl.PSPReversal_win1mode.setCurrentIndex(r)
                    else:
                        print 'win 2 global analysis mode not recognized: %s' % self.script['global_win2_mode']

                for n in range(0, 3):
                    #print 'region to set: ', thiscell['win%d'%n]
                    self.regions['lrwin%d'%n]['region'].setRegion([x*1e-3 for x in thiscell['win%d'%n]])
                    self.regions['lrwin%d'%n]['region'].start = thiscell['win%d'%n][0]
                    self.regions['lrwin%d'%n]['region'].stop = thiscell['win%d'%n][1]
                    self.show_or_hide('lrwin%d'%n, forcestate=True)
                m = thiscell['manip'][p]  # get the tag for the manipulation
                self.update_all_analysis()  # run all current analyses
                self.make_cell_summary()
                ptxt = self.print_analysis()
                apptext(ptxt)
                self.textout += ptxt
                # print protocol result, optionally a cell header.
                self.append_script_output(script_header)
                script_header = False
        print '\nDone'

    def print_script_output(self):
        print self.remove_html_markup(self.textout)

    def copy_script_output(self):
        """
        Copy script output (results) to system clipboard
        :return: Nothing
        """
        self.scripts_form.PSPReversal_ScriptResults_text.copy()

    def append_script_output(self, script_header=True):
    #    pass  # do nothing for now...
    # actually, stole button for a different purpose...
    #def print_summary_table(self):
        data_template = (OrderedDict([('ElapsedTime', []), ('Drugs', []), ('HoldV', []), ('JP', []),
                                                                        ('Rs', []), ('Cm', []), ('Ru', []), ('Erev', []),
                                                                        ('gsyn_Erev', []), ('gsyn_60', []),
                                                                        ('p0', []), ('p1', []), ('p2', []), ('p3', []),
                                                                        ('I_ionic+', []), ('I_ionic-', []), ('ILeak', [])
                                                                        ]))
        # summary table header is written anew for each cell
        if script_header:
            print "Cell, Protocol, ",
            for k in data_template.keys():
                print('{:<s}, '.format(k)),
            print ''
        print '%s, %s, ' % (self.CellSummary['CellID'], self.CellSummary['Protocol']),
        for a in data_template.keys():
            if a in self.CellSummary.keys():
                print '%s, ' % str(self.CellSummary[a]),
            else:
                print '<missing>, ',
        print ''


        # fill table with current information


    def update_win_analysis(self, region=None, clear=True, pw=False):
        """
        Compute the current-voltage relationship from the selected time window

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

        :param region: which region of the linearRegion elements are used for
                       the time window.
        :param clear: a boolean flag that originally allowed accumulation of plots
                      presently, ignored.
        :param pw: print window flag = current ignored.
        :return: Nothing
        :modifies:
            ivss, yleak, ivss_cmd, cmd.
            dictionary of measurement window data in self.measure

        """

        # the first action of this routine is to set the text boxes correctly to represent the status of the
        # current LR region
        window = region
        region = 'lr' + window
        if window is None:
            return
        if self.traces is None:
            return
        rgninfo = self.regions[region]['region'].getRegion()
        self.regions[region]['start'].setValue(rgninfo[0] * 1.0e3)  # report values to screen
        self.regions[region]['stop'].setValue(rgninfo[1] * 1.0e3)

        if window == 'win0':
            return  # we don't use for calculations, just marking times

        wincmd = window + 'cmd'
        winoff = window + 'off'
        winon = window + 'on'
        windowsd = window + 'std'
        winaltcmd = window + 'altcmd'
        winunordered = window + '_unordered'
        winlinfit = window + '_linfit'
        winraw_i = window + 'rawI'  # save the raw (uncorrected) voltage as well
        winraw_v = window + 'rawV'
        winorigcmd = window + 'origcmd'
        winbkgd = window + 'bkgd'  # background current (calculated from win 1 fit)

        # these will always be filled
        self.measure[window] = []
        self.measure[wincmd] = []
        # The next ones will only be set if the alt flag is on
        self.measure[winoff] = []
        self.measure[winon] = []
        self.measure[winaltcmd] = []
        self.measure[winunordered] = []
        self.measure[windowsd] = []
        self.measure[winraw_i] = []
        self.measure[winraw_v] = []
        self.measure[winorigcmd] = []
        self.measure[winbkgd] = []

        mode = self.regions[region]['mode'].currentText()
        data1 = self.traces['Time': rgninfo[0]:rgninfo[1]]  # extract analysis region
        tx1 = ma.compressed(ma.masked_outside(self.tx, rgninfo[0], rgninfo[1]))  # time to match data1
        if tx1.shape[0] > data1.shape[1]:
            tx1 = tx1[0:-1]  # clip extra point. Rules must be different between traces clipping and masking.
        if window == 'win1':  # check if win1 overlaps with win0, and select data
            r0 = self.regions['lrwin0']['region'].getRegion()
            tx = ma.masked_inside(tx1, r0[0], r0[1])  #
            n_unmasked = ma.count(tx)
            if n_unmasked == 0:  # handle case where win1 is entirely inside win2
                print 'update_win_analysis: Window 1 is entirely inside Window 0: No analysis possible'
                print 'rgninfo: ', rgninfo
                print 'r0: ', r0
                return
            data1 = ma.array(data1, mask=ma.resize(ma.getmask(tx), data1.shape))
            self.txm = ma.compressed(tx)  # now compress tx as well
            self.win1fits = None  # reset the fits

        if data1.shape[1] == 0 or data1.shape[0] == 1:
            print 'no data to analyze?'
            return  # skip it
        commands = np.array(self.values)  # get clamp specified command levels
        if self.data_mode in self.ic_modes:
            self.count_spikes()
        if mode in ['Mean-Win1', 'Sum-Win1']:
            if 'win1_unordered' not in self.measure.keys() or len(
                    self.measure['win1_unordered']) == 0:  # Window not analyzed yet, but needed: do it
                self.update_win_analysis(region='win1')
        if mode == 'Min':
            self.measure[window] = data1.min(axis=1)
        elif mode == 'Max':
            self.measure[window] = data1.max(axis=1)
        elif mode == 'Mean' or mode is None:
            self.measure[window] = data1.mean(axis=1)
            self.measure[windowsd] = np.std(np.array(data1), axis=1)
        elif mode == 'Sum':
            self.measure[window] = np.sum(data1, axis=1)
        elif mode == 'Abs':  # find largest regardless of the sign ('minormax')
            x1 = data1.min(axis=1)
            x2 = data1.max(axis=1)
            self.measure[window] = np.zeros(data1.shape[0])
            for i in range(data1.shape[0]):
                if -x1[i] > x2[i]:
                    self.measure[window][i] = x1[i]
                else:
                    self.measure[window][i] = x2[i]
        elif mode == 'Linear' and window == 'win1':
            ntr = data1.shape[0]
            d1 = np.resize(data1.compressed(), (ntr, self.txm.shape[0]))
            p = np.polyfit(self.txm, d1.T, 1)
            self.win1fits = p
            txw1 = ma.compressed(ma.masked_inside(self.tx, rgninfo[0], rgninfo[1]))
            fits = np.zeros((data1.shape[0], txw1.shape[0]))
            for j in range(data1.shape[0]):  # polyval only does 1d
                fits[j, :] = np.polyval(self.win1fits[:, j], txw1)
            self.measure[winbkgd] = fits.mean(axis=1)
            self.measure[window] = data1.mean(axis=1)

        elif mode == 'Poly2' and window == 'win1':
            # fit time course of data
            ntr = data1.shape[0]
            d1 = np.resize(data1.compressed(), (ntr, self.txm.shape[0]))
            p = np.polyfit(self.txm, d1.T, 3)
            self.win1fits = p
            txw1 = ma.compressed(ma.masked_inside(self.tx, rgninfo[0], rgninfo[1]))
            fits = np.zeros((data1.shape[0], txw1.shape[0]))
            for j in range(data1.shape[0]):  # polyval only does 1d
                fits[j, :] = np.polyval(self.win1fits[:, j], txw1)
            self.measure[winbkgd] = fits.mean(axis=1)
            self.measure[window] = data1.mean(axis=1)
        if mode in ['Min', 'Max', 'Mean', 'Sum', 'Abs', 'Linear', 'Poly2']:
            self.measure[winraw_i] = self.measure[window]  # save raw measured current before corrections
        elif mode not in ['Mean-Win1', 'Mean-Linear', 'Mean-Poly2', 'Sum-Win1']:
            print 'update_win_analysis: Mode %s is not recognized (1)' % mode
            return
        else:
            pass

        # continue with difference modes
        if mode == 'Mean-Win1' and len(self.measure['win1_unordered']) == data1.shape[0]:
            self.measure[winraw_i] = data1.mean(axis=1)
            self.measure[window] = self.measure[winraw_i] - self.measure['win1_unordered']
            self.measure[windowsd] = np.std(np.array(data1), axis=1) - self.measure['win1_unordered']
        elif mode in ['Mean-Linear', 'Mean-Poly2'] and window == 'win2':  # and self.txm.shape[0] == data1.shape[0]:
            fits = np.zeros((data1.shape[0], tx1.shape[0]))
            for j in range(data1.shape[0]):  # polyval only does 1d
                fits[j, :] = np.polyval(self.win1fits[:, j], tx1)
            self.measure[winraw_i] = np.mean(data1, axis=1)
            self.measure[window] = np.mean(data1 - fits, axis=1)
            self.measure[windowsd] = np.std(data1 - fits, axis=1)
        elif mode == 'Sum-Win1' and len(self.measure['win1_unordered']) == data1.shape[0]:
            u = self.measure['win1_unordered']._data
            self.measure[winraw_i] = np.sum(data1, axis=1)
            self.measure[window] = np.sum(data1 - u[:, np.newaxis], axis=1)
        elif mode not in ['Min', 'Max', 'Mean', 'Sum', 'Abs', 'Linear', 'Poly2']:
            print 'update_win_analysis: Mode %s is not recognized (2)' % mode
            return
        else:
            pass

        if self.ctrl.PSPReversal_SubBaseline.isChecked():
            self.measure[window] = self.measure[window] - self.measure['rmp']
        if len(self.nospk) >= 1 and self.data_mode in self.ic_modes:
            # Steady-state IV where there are no spikes
            print 'update_win_analysis: Removing traces with spikes from analysis'
            self.measure[window] = self.measure[window][self.nospk]
            if len(self.measure[windowsd]) > 0:
                self.measure[windowsd] = self.measure[windowsd][self.nsopk]
            self.measure[wincmd] = commands[self.nospk]
            self.cmd = commands[self.nospk]
            # compute Rin from the SS IV:
            if len(self.cmd) > 0 and len(self.measure[window]) > 0:
                self.r_in = np.max(np.diff
                                   (self.measure[window]) / np.diff(self.cmd))
                self.ctrl.PSPReversal_Rin.setText(u'%9.1f M\u03A9'
                                                  % (self.r_in * 1.0e-6))
            else:
                self.ctrl.PSPReversal_Rin.setText(u'No valid points')
        else:
            if self.data_mode in self.vc_modes and self.r_uncomp > 0.0 and self.ctrl.PSPReversal_RsCorr.isChecked():
                # correct command voltages. This is a bit more complicated than it appears at first
                #
                self.measure[winorigcmd] = commands
                # print 'commands, uncomp, measure'
                # print np.array(commands).shape
                # print self.r_uncomp
                # print np.array(self.measure[winraw_i]).shape
                # print 'winraw_i: ', winraw_i
                self.measure[wincmd] = np.array(commands) - self.r_uncomp * np.array(self.measure[winraw_i])  # IR drop across uncompensated
                self.cmd = commands
            else:
                self.measure[winorigcmd] = commands
                self.measure[wincmd] = commands
                self.cmd = commands
            self.measure['leak'] = np.zeros(len(self.measure[window]))
        self.measure[winunordered] = self.measure[window]

        # now separate the data into alternation groups, then sort by command level
        if self.alternation and window == 'win2':
            #            print 'in alternation'
            nm = len(self.measure[window])  # get the number of measurements
            xoff = range(0, nm, 2)  # really should get this from loadrequestedfile
            xon = range(1, nm, 2)  # get alternating ranges
            measure_voff = self.measure[wincmd][xoff]  # onset same as the other
            measure_von = self.measure[wincmd][xon]
            measure_con = self.measure[winorigcmd][xon]
            measure_off = self.measure[window][xoff]
            measure_on = self.measure[window][xon]
            vcs_on = np.argsort(measure_von)
            ccs_on = np.argsort(measure_con)
            vcs_off = np.argsort(measure_voff)
            measure_von = measure_von[vcs_on]
            measure_con = measure_con[ccs_on]
            measure_off = measure_off[vcs_off]
            measure_on = measure_on[vcs_on]
            self.measure[winon] = np.array(measure_on)
            self.measure[winoff] = np.array(measure_off)
            self.measure[winaltcmd] = np.array(measure_von)
            self.measure[winraw_v] = np.array(measure_con)
            self.measure[winraw_i] = np.array(self.measure[winraw_i][vcs_on])
        else:
            isort = np.argsort(self.measure[wincmd])  # get sort order for commands
            self.measure[wincmd] = self.measure[wincmd][isort]  # sort the command values
            self.measure[window] = self.measure[window][isort]  # sort the data in the window
            self.measure[winraw_v] = self.measure[winorigcmd][isort]
        self.update_IVPlot()
        self.update_command_timeplot(wincmd)

    def update_command_timeplot(self, wincmd):
        (pen, filledbrush, emptybrush, symbol, n, clear_flag) = self.map_symbol()

        self.command_plot.plot(x=self.trace_times, y=self.cmd, clear=clear_flag,
                               symbolSize=6,
                               symbol=symbol, pen=pen,
                               symbolPen=pen, symbolBrush=filledbrush)

    def update_rmp_analysis(self, region=None, clear=True, pw=False):
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
        self.update_rmp_plot()

    def makemap_symbols(self):
        """
        Given the current state of things, (keep analysis count, for example),
        return a tuple of pen, fill color, empty color, a symbol from
        our lists, and a clear_flag. Used to overplot different data.
        """
        n = self.keep_analysis_count
        pen = self.color_list.next()
        filledbrush = pen
        emptybrush = None
        symbol = self.symbol_list.next()
        if n == 0:
            clear_flag = True
        else:
            clear_flag = False
        self.current_symbol_dict = {'pen': pen, 'filledbrush': filledbrush,
                                    'emptybrush': emptybrush, 'symbol': symbol,
                                    'n': n, 'clear_flag': clear_flag}

    def map_symbol(self):
        cd = self.current_symbol_dict
        if cd['filledbrush'] == 'w':
            cd['filledbrush'] = pg.mkBrush((128, 128, 128))
        if cd['pen'] == 'w':
            cd['pen'] = pg.mkPen((128, 128, 128))
        self.last_symbol = (cd['pen'], cd['filledbrush'],
                            cd['emptybrush'], cd['symbol'],
                            cd['n'], cd['clear_flag'])
        return self.last_symbol

    def update_IVPlot(self):
        """
            Draw the peak and steady-sate IV to the I-V window
            Note: x axis is always I or V, y axis V or I
        """
        if self.ctrl.PSPReversal_KeepAnalysis.isChecked() is False:
            self.iv_plot.clear()
            self.iv_plot.addLine(x=0, pen=pg.mkPen('888', width=0.5, style=QtCore.Qt.DashLine))
            self.iv_plot.addLine(y=0, pen=pg.mkPen('888', width=0.5, style=QtCore.Qt.DashLine))
        jp = self.junction  # get offsets for voltage
        ho = float(self.holding) * 1e3
        offset = jp + ho  # combine
        (pen, filledbrush, emptybrush, symbol, n, clear_flag) = self.map_symbol()
        if self.data_mode in self.ic_modes:
            self.label_up(self.iv_plot, 'I (pA)', 'V (mV)', 'I-V (CC)')
            if (len(self.measure['win1']) > 0 and
                    self.regions['lrwin1']['state'].isChecked()):
                self.iv_plot.plot(offset + self.measure['win1cmd'] * 1e12, self.measure['win1'] * 1e3,
                                  symbol=symbol, pen=None,
                                  symbolSize=6, symbolPen=pg.mkPen({'color': "0F0", 'width': 1}),
                                  symbolBrush=emptybrush)
            if (len(self.measure['win2']) > 0 and
                    self.regions['lrwin2']['state'].isChecked()):
                self.iv_plot.plot(offset + self.measure['win2cmd'] * 1e12, self.measure['win2'] * 1e3,
                                  symbol=symbol, pen=None,
                                  symbolSize=6, symbolPen=pg.mkPen({'color': "00F", 'width': 1}),
                                  symbolBrush=filledbrush)
        if self.data_mode in self.vc_modes:
            self.label_up(self.iv_plot, 'V (mV)', 'I (nA)', 'I-V (VC)')
            if (len(self.measure['win1']) > 0 and
                    self.regions['lrwin1']['state'].isChecked()):
                self.iv_plot.plot(offset + self.measure['win1cmd'] * 1e3, self.measure['win1'] * 1e9,
                                  symbol=symbol, pen=None,
                                  symbolSize=6, symbolPen=pg.mkPen({'color': "FF0", 'width': 1}),
                                  symbolBrush=emptybrush)
            if (len(self.measure['win2']) > 0 and
                    self.regions['lrwin2']['state'].isChecked()):
                if not self.alternation:
                    self.iv_plot.plot(offset + self.measure['win2cmd'] * 1e3, self.measure['win2'] * 1e9,
                                      symbol=symbol, pen=None,
                                      symbolSize=6, symbolPen=pg.mkPen({'color': "00F", 'width': 1}),
                                      symbolBrush=filledbrush)
                else:
                    if len(self.measure['win2altcmd']) > 0:
                        self.iv_plot.plot(offset + self.measure['win2altcmd'] * 1e3, self.measure['win2on'] * 1e9,
                                          symbol=symbol, pen=None,
                                          symbolSize=6, symbolPen=pg.mkPen({'color': "00F", 'width': 1}),
                                          symbolBrush=filledbrush)
                        # compute polynomial fit to iv
                        # this should have it's own method
                        p = np.polyfit(self.measure['win2altcmd'], self.measure['win2on'], 3)
                        vpl = np.arange(float(np.min(self.measure['win2altcmd'])),
                                        float(np.max(self.measure['win2altcmd'])), 1e-3)
                        ipl = np.polyval(p, vpl)
                        # get the corrected voltage command (Vm = Vc - Rs*Im)
                        m = self.measure['win2altcmd']
                        calt = m.reshape(m.shape[0] / self.nrepc, self.nrepc)
                        vc = calt.mean(axis=1)
                        # get the original commmand voltage (for reference
                        mvc = self.measure['win2rawV']
                        cmdalt = mvc.reshape(mvc.shape[0] / self.nrepc, self.nrepc)
                        mvc = cmdalt.mean(axis=1)
                        # get the current for the window (after subtractions,etc)
                        m2 = self.measure['win2on']
                        ialt = m2.reshape(m2.shape[0] / self.nrepc, self.nrepc)
                        im = ialt.mean(axis=1)
                        imsd = ialt.std(axis=1)
                        avPen = pg.mkPen({'color': "F00", 'width': 1})
                        fitPen = pg.mkPen({'color': "F00", 'width': 2})
                        self.iv_plot.plot(offset + vc * 1e3, im * 1e9,
                                          pen=None,  # no lines
                                          symbol='s', symbolSize=6,
                                          symbolPen=avPen, symbolBrush=filledbrush)
                        self.iv_plot.plot(offset + vpl * 1e3, ipl * 1e9,
                                          pen=fitPen)  # lines
                        self.win2IV = [vc * 1e3, im * 1e9, imsd * 1e9, mvc * 1e3]
                        self.diffFit = p  # save the difference fit

    def update_rmp_plot(self):
        """
            Draw the RMP to the I-V window
            Note: x axis can be I, T, or  # spikes
        """
        if self.ctrl.PSPReversal_KeepAnalysis.isChecked() is False:
            self.rmp_plot.clear()
        if len(self.measure['rmp']) > 0:
            (pen, filledbrush, emptybrush, symbol, n, clear_flag) = self.map_symbol()
            mode = self.ctrl.PSPReversal_RMPMode.currentText()
            if self.data_mode in self.ic_modes:
                sf = 1e3
                self.rmp_plot.setLabel('left', 'V mV')
            else:
                sf = 1e12
                self.rmp_plot.setLabel('left', 'I (pA)')
            if mode == 'T (s)':
                self.rmp_plot.plot(self.trace_times, sf * np.array(self.measure['rmp']),
                                   symbol=symbol, pen=pen,
                                   symbolSize=6, symbolPen=pen,
                                   symbolBrush=filledbrush)
                self.rmp_plot.setLabel('bottom', 'T (s)')
            elif mode == 'I (pA)':
                self.rmp_plot.plot(self.cmd,
                                   1.e3 * np.array(self.measure['rmp']), symbolSize=6,
                                   symbol=symbol, pen=pen,
                                   symbolPen=pen, symbolBrush=filledbrush)
                self.rmp_plot.setLabel('bottom', 'I (pA)')
            elif mode == 'Sp (#/s)':
                self.rmp_plot.plot(self.spikecount,
                                   1.e3 * np.array(self.measure['rmp']), symbolSize=6,
                                   symbol=symbol, pen=pen,
                                   symbolPen=pen, symbolBrush=emptybrush)
                self.rmp_plot.setLabel('bottom', 'Spikes')
            else:
                print 'Selected RMP x axis mode not known: %s' % mode

    def update_spike_plots(self):
        """
            Draw the spike counts to the FI and FSL windows
            Note: x axis can be I, T, or  # spikes
        """
        if self.data_mode in self.vc_modes:
            # self.command_plot.clear()  # no plots of spikes in VC
            # self.fslPlot.clear()
            return
        (pen, filledbrush, emptybrush, symbol, n, clear_flag) = self.map_symbol()
        mode = self.ctrl.PSPReversal_RMPMode.currentIndex()  # get x axis mode
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
        tsf = 1.0e3
        if self.modelmode:
            tsf = 1.0
        # print 'Regions: ', self.regions.keys()
        if self.regions['lrrmp']['state'].isChecked():
            rgnx1 = self.regions['lrrmp']['start'].value() / tsf
            rgnx2 = self.regions['lrrmp']['start'].value() / tsf
            self.regions['lrrmp']['region'].setRegion([rgnx1, rgnx2])
            self.update_rmp_analysis(clear=clear_flag, pw=pw)

        if self.regions['lrwin1']['state'].isChecked():
            rgnx1 = self.regions['lrwin1']['start'].value() / 1e3
            rgnx2 = self.regions['lrwin1']['stop'].value() / 1e3
            self.regions['lrwin1']['region'].setRegion([rgnx1, rgnx2])
            self.update_win_analysis(region='win1', clear=clear_flag, pw=pw)

        if self.regions['lrwin0']['state'].isChecked():
            rgnx1 = self.regions['lrwin0']['start'].value() / 1e3
            rgnx2 = self.regions['lrwin0']['stop'].value() / 1e3
            self.regions['lrwin0']['region'].setRegion([rgnx1, rgnx2])
            self.update_win_analysis(region='win1', clear=clear_flag, pw=pw)

        if self.regions['lrwin2']['state'].isChecked():
            rgnx1 = self.regions['lrwin2']['start'].value() / 1e3
            rgnx2 = self.regions['lrwin2']['stop'].value() / 1e3
            self.regions['lrwin2']['region'].setRegion([rgnx1, rgnx2])
            self.update_win_analysis(region='win2', clear=clear_flag, pw=pw)

        # if self.regions['lrleak']['state'].isChecked():
        #     rgnx1 = self.regions['lrleak']['start'].value() / 1e3
        #     rgnx2 = self.regions['lrleak']['stop'].value() / 1e3
        #     self.regions['lrleak']['region'].setRegion([rgnx1, rgnx2])
        #     self.update_win_analysis(region='win1')
        #     self.update_win_analysis(region='win2')

        # if self.ctrl.PSPReversal_showHide_lrtau.isChecked():
        #     # include tau in the list... if the tool is selected
        #     self.update_tauh()

        if self.regions['lrwin1']['mode'].currentIndexChanged:
            self.update_win_analysis(region='win1')

        if self.regions['lrwin2']['mode'].currentIndexChanged:
            self.update_win_analysis(region='win2')

    def count_spikes(self):
        """
        count_spikes: Using the threshold set in the control panel, count the
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
        if self.spikes_counted:  # only do once for each set of traces
            return
        if self.keep_analysis_count == 0:
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
        if self.data_mode not in self.ic_modes or self.tx is None:
            # print ('PSPReversal::count_spikes: Cannot count spikes, ' +
            #       'and dataMode is ', self.dataMode, 'and ICModes are: ', self.ic_modes , 'tx is: ', self.tx)
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
        # threshold = self.ctrl.PSPReversal_SpikeThreshold.value() * 1e-3
        threshold = 0.0
        # rmp = np.zeros(ntr)
        # # rmp is taken from the mean of all the baselines in the traces
        # self.Rmp = np.mean(rmp)

        for i in range(ntr):
            (spike, spk) = Utility.findspikes(self.tx, self.traces[i],
                                              threshold, t0=self.tstart,
                                              t1=self.tend,
                                              dt=self.sample_interval,
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
            if (len(spike) >= minspk) and (len(spike) <= maxspk):
                misi = np.mean(np.diff(spike[-3:]))
                self.ar[i] = misi / self.isi[i]
            (self.rmp[i], r2) = Utility.measure('mean', self.tx, self.traces[i],
                                                0.0, self.tstart)
        # iAR = np.where(ar > 0)
        # ARmean = np.mean(ar[iAR])  # only where we made the measurement
        # self.adapt_ratio = ARmean
        # self.ctrl.PSPReversal_AR.setText(u'%7.3f' % (ARmean))
        self.fisi = self.fisi * 1.0e3
        self.fsl = self.fsl * 1.0e3
        self.nospk = np.where(self.spikecount == 0)
        self.spk = np.where(self.spikecount > 0)
        self.update_spike_plots()

    def update_tau(self, print_window=True):
        """
        Compute time constant (single exponential) from the
        onset of the response
        using lrwin2 window, and only the smallest 3 steps...
        """
        if not self.cmd:  # probably not ready yet to do the update.
            return
        if self.data_mode not in self.ic_modes:  # only permit in IC
            return
        rgnpk = self.lrwin2.getRegion()
        func = 'exp1'  # single exponential fit.
        fits = Fitting.Fitting()
        initpars = [-60.0 * 1e-3, -5.0 * 1e-3, 10.0 * 1e-3]
        icmdneg = np.where(self.cmd < 0)
        maxcmd = np.min(self.cmd)
        ineg = np.where(self.cmd[icmdneg] >= maxcmd / 3)
        whichdata = ineg[0]
        itaucmd = self.cmd[ineg]
        whichaxis = 0

        (fpar, xf, yf, names) = fits.FitRegion(whichdata, whichaxis,
                                               self.tx,
                                               self.traces,
                                               dataType='xy',
                                               t0=rgnpk[0], t1=rgnpk[1],
                                               fitFunc=func,
                                               fitPars=initpars,
                                               method='simplex')
        if fpar == []:
            print 'PSPReversal::update_tau: Charging tau fitting failed - see log'
            return
        taus = []
        for j in range(0, fpar.shape[0]):
            outstr = ""
            taus.append(fpar[j][2])
            for i in range(0, len(names[j])):
                outstr = outstr + ('%s = %f, ' % (names[j][i], fpar[j][i]))
            if print_window:
                print("FIT(%d, %.1f pA): %s " %
                      (whichdata[j], itaucmd[j] * 1e12, outstr))
        meantau = np.mean(taus)
        self.ctrl.PSPReversal_Tau.setText(u'%18.1f ms' % (meantau * 1.e3))
        self.tau = meantau
        tautext = 'Mean Tau: %8.1f'
        if print_window:
            print tautext % (meantau * 1e3)

    def update_tauh(self, printWindow=False):
        """ compute tau (single exponential) from the onset of the markers
            using lrtau window, and only for the step closest to the selected
            current level in the GUI window.

            Also compute the ratio of the sag from the peak (marker1) to the
            end of the trace (marker 2).
            Based on analysis in Fujino and Oertel, J. Neuroscience 2001,
            to type cells based on different Ih kinetics and magnitude.
        """
        if self.ctrl.PSPReversal_showHide_lrtau.isChecked() is not True:
            return
        rgn = self.lrtau.getRegion()
        func = 'exp1'  # single exponential fit to the whole region
        fits = Fitting.Fitting()
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
        peak_region = self.lrwin2.getRegion()
        steadstate_region = self.lrwin1.getRegion()
        vpk = target['Time': peak_region[0]:peak_region[1]].min() * 1000
        self.neg_pk = (vpk - vrmp) / 1000.
        vss = np.median(target['Time': steadstate_region[0]:steadstate_region[1]]) * 1000
        self.neg_ss = (vss - vrmp) / 1000.
        whichdata = [int(amin)]
        itaucmd = [self.cmd[amin]]
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
        (fpar, xf, yf, names) = fits.FitRegion(whichdata, whichaxis,
                                               self.traces.xvals('Time'),
                                               self.traces.view(np.ndarray),
                                               dataType='2d',
                                               t0=rgn[0], t1=rgn[1],
                                               fitFunc=func,
                                               fitPars=initpars)
        if not fpar:
            print 'PSPReversal::update_tauh: tau_h fitting failed - see log'
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
        s = np.shape(fpar)
        taus = []
        for j in range(0, s[0]):
            outstr = ""
            taus.append(fpar[j][2])
            for i in range(0, len(names[j])):
                outstr += ('%s = %f, ' %
                           (names[j][i], fpar[j][i] * 1000.))
            if printWindow:
                print("Ih FIT(%d, %.1f pA): %s " %
                      (whichdata[j], itaucmd[j] * 1e12, outstr))
        meantau = np.mean(taus)
        self.ctrl.PSPReversal_Tauh.setText(u'%8.1f ms' % (meantau * 1.e3))
        self.tau2 = meantau
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

    def dbstore_clicked(self):
        """
        Store data into the current database for further analysis
        """
        self.update_all_analysis()
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
            'PSPReversal_rinp': self.r_in,
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

    # ---- Helpers ----
    # Some of these would normally live in a pyqtgraph-related module, but are
    # just stuck here to get the job done.
    #
    def label_up(self, plot, xtext, ytext, title):
        """helper to label up the plot"""
        plot.setLabel('bottom', xtext)
        plot.setLabel('left', ytext)
        plot.setTitle(title)
