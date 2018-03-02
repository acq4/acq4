#  -*- coding: utf-8 -*-
from __future__ import print_function
"""
PSPReversal: Analysis module that analyzes the current-voltage relationships
relationships of PSPs from voltage clamp data.
This is part of Acq4
Based on IVCurve (as of 5/2014)
Paul B. Manis, Ph.D.
2014.


"""


from collections import OrderedDict
import os
import os.path
import itertools
import functools
from acq4.util import Qt
import numpy as np
import numpy.ma as ma
import scipy

from acq4.analysis.AnalysisModule import AnalysisModule
import acq4.pyqtgraph as pg
from acq4.pyqtgraph import configfile
from acq4.util.metaarray import MetaArray

standard_font = 'Arial'

import acq4.analysis.tools.Utility as Utility  # pbm's utilities...
#from acq4.analysis.modules.PSPReversal.ctrlTemplate import ctrlTemplate
from . import ctrlTemplate
from . import resultsTemplate
from . import scriptTemplate
#import acq4.analysis.modules.PSPReversal.ctrlTemplate as ctrlTemplate
#import acq4.analysis.modules.PSPReversal.resultsTemplate as resultsTemplate
#import acq4.analysis.modules.PSPReversal.scriptTemplate as scriptTemplate

def trace_calls_and_returns(frame, event, arg, indent=[0]):
    """
    http://pymotw.com/2/sys/tracing.html
    :param frame:
    :param event:
    :param arg:
    :return:
    """
    ignore_funcs = ['map_symbol', 'makemap_symbols', 'label_up', 'show_or_hide',
                    'update_command_timeplot', '<genexpr>', 'write',
                    'boundingRect', 'shape']
    frame_code = frame.f_code
    func_name = frame_code.co_name
    if func_name in ignore_funcs:
        # Ignore write() calls from print statements
        return
    line_no = frame.f_lineno
    filename = os.path.basename(frame_code.co_filename)
    #print 'file: ', filename
    if filename.find('PSPReversal') == -1:  # ignore calls not in our own code
        return
    if event == 'call':
        indent[0] += 1
        print('%sCall to %s on line %s of %s' % ("   " * indent[0], func_name, line_no, filename))
       # print '%s   args: %s ' % ("   " * indent[0], arg)  # only gets return args...
        return trace_calls_and_returns
    elif event == 'return':
        print('%s%s => %s' % ("   " * indent[0], func_name, arg))
        indent[0] -= 1
    return


class MultiLine(Qt.QGraphicsPathItem):
    def __init__(self, x, y, downsample=1):
        """x and y are 2D arrays of shape (Nplots, Nsamples)"""
        if x.ndim == 1:
            x = np.tile(x, y.shape[0]).reshape(y.shape[0], x.shape[0])
        x = x[:, 0::downsample].view(np.ndarray)
        y = y[:, 0::downsample].view(np.ndarray)
        if x.ndim == 1:
            x = np.tile(x, y.shape[0]).reshape(y.shape[0], x.shape[0])
        connect = np.ones(x.shape, dtype=bool)
        connect[:, -1] = 0  # don't draw the segment between each trace
        self.path = pg.arrayToQPath(x.flatten(), y.flatten(), connect.flatten())
        Qt.QGraphicsPathItem.__init__(self, self.path)
        self.setPen(pg.mkPen('w'))

    def shape(self): # override because QGraphicsPathItem.shape is too expensive.
        return Qt.QGraphicsItem.shape(self)

    def boundingRect(self):
        return self.path.boundingRect()


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
        self.auto_updater = True  # turn off for script analysis.
        self.cmd = None
        self.junction = 0.0  # junction potential (user adjustable)
        self.holding = 0.0  # holding potential (read from commands)
        self.regions_exist = False
        self.regions = {}
        self.fit_curve = None
        self.fitted_data = None
        self.time_base = None
        self.keep_analysis_count = 0
        self.spikes_counted = False
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
        self.time_base = None

        # -----------------(some) results elements----------------------

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
        self.adaptation_ratio= None

        self.cmd = []
        self.sequence = {}
        self.measure = {'rmp': [], 'rmpcmd': [],
                        'leak': [],
                        'win1': [], 'win1cmd': [], 'win1off': [], 'win1on': [],
                        'winaltcmd': [],
                        'win2': [], 'win2cmd': [], 'win2off': [], 'win2on': [],
                        'win2altcmd': [],
                        }

        self.rmp = []  # resting membrane potential during sequence
        self.analysis_parameters = {}

        # -----------------scripting-----------------------
        self.script = None
        self.script_name = None

        # --------------graphical elements-----------------
        self._sizeHint = (1280, 900)  # try to establish size of window
        self.ctrl_widget = Qt.QWidget()
        self.ctrl = ctrlTemplate.Ui_Form()
        self.ctrl.setupUi(self.ctrl_widget)
        self.results_widget = Qt.QWidget()
        self.results = resultsTemplate.Ui_ResultsDialogBox()
        self.results.setupUi(self.results_widget)
        self.scripts_widget = Qt.QWidget()
        self.scripts_form = scriptTemplate.Ui_Form()
        self.scripts_form.setupUi(self.scripts_widget)
        self.main_layout = pg.GraphicsView()  # instead of GraphicsScene?
        # make fixed widget for the module output
        self.widget = Qt.QWidget()
        self.grid_layout = Qt.QGridLayout()
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
        self.ctrl.PSPReversal_Update.clicked.connect(self.interactive_analysis)
        self.ctrl.PSPReversal_PrintResults.clicked.connect(self.print_analysis)
        self.ctrl.PSPReversal_KeepAnalysis.clicked.connect(self.reset_keep_analysis)
        self.ctrl.PSPReversal_rePlotData.clicked.connect(self.plot_traces)
        self.ctrl.PSPReversal_Alternation.setTristate(False)
        self.ctrl.PSPReversal_Alternation.stateChanged.connect(self.get_alternation)
        self.ctrl.PSPReversal_SubBaseline.stateChanged.connect(self.get_baseline)
        self.ctrl.PSPReversal_Junction.valueChanged.connect(self.get_junction)
        [self.ctrl.PSPReversal_RMPMode.currentIndexChanged.connect(x)
         for x in [self.update_rmp_analysis, self.count_spikes]]
        self.ctrl.dbStoreBtn.clicked.connect(self.dbstore_clicked)

        self.scripts_form.PSPReversal_ScriptFile_Btn.clicked.connect(self.read_script)
        self.scripts_form.PSPReversal_ScriptRerun_Btn.clicked.connect(self.rerun_script)
        self.scripts_form.PSPReversal_ScriptPrint_Btn.clicked.connect(self.print_script_output)
        self.scripts_form.PSPReversal_ScriptCopy_Btn.clicked.connect(self.copy_script_output)
        self.scripts_form.PSPReversal_ScriptFormatted_Btn.clicked.connect(self.print_formatted_script_output)

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
        self.colors = ['r', 'g', 'b', 'r', 'y', 'c']
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
        self.sequence = {}
        self.measure = {'rmp': [], 'rmpcmd': [],
                        'leak': [],
                        'win1': [], 'win1cmd': [], 'win1off': [], 'win1on': [],
                        'winaltcmd': [],
                        'win2': [], 'win2cmd': [], 'win2off': [], 'win2on': [],
                        'win2altcmd': [],
                        }
        #for m in self.measure.keys():
        #    self.measure[m] = []
        self.rmp = []  # resting membrane potential during sequence
        self.analysis_summary = {}
        self.win2IV = {}
        self.win1fits = None
        self.analysis_parameters = {}

    def reset_keep_analysis(self):
        """
        Reset the "keep analysis" counter
        :return:
        """
        self.keep_analysis_count = 0

    def get_alternation(self):
        """
        retrieve the state of the alternation checkbox
        :return:
        """
        self.analysis_parameters['alternation'] = self.ctrl.PSPReversal_Alternation.isChecked()

    def get_baseline(self):
        """
        retreive the state of the subtract baseline checkbox
        :return:
        """
        self.analysis_parameters['baseline'] = self.ctrl.PSPReversal_SubBaseline.isChecked()

    def get_junction(self):
        """
        retrieve the junction potential value
        :return:
        """
        self.analysis_parameters['junction'] = self.ctrl.PSPReversal_Junction.value()

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
            self.regions['lrwin0'] = {'name': 'win0',
                                      'region': pg.LinearRegionItem([0, 1],
                                                                    brush=pg.mkBrush(255, 255, 0, 50.)),
                                      'plot': self.data_plot,
                                      'state': self.ctrl.PSPReversal_showHide_lrwin1,
                                      'shstate': True,  # keep internal copy of the state
                                      'mode': self.ctrl.PSPReversal_win1mode,
                                      'start': self.ctrl.PSPReversal_win0TStart,
                                      'stop': self.ctrl.PSPReversal_win0TStop,
                                      'updater': self.update_windows,
                                      'units': 'ms'}
            self.ctrl.PSPReversal_showHide_lrwin0.region = self.regions['lrwin0']['region']  # save region with checkbox
            self.regions['lrwin1'] = {'name': 'win1',
                                      'region': pg.LinearRegionItem([0, 1],
                                                                    brush=pg.mkBrush(0, 255, 0, 50.)),
                                      'plot': self.data_plot,
                                      'state': self.ctrl.PSPReversal_showHide_lrwin1,
                                      'shstate': True,  # keep internal copy of the state
                                      'mode': self.ctrl.PSPReversal_win1mode,
                                      'start': self.ctrl.PSPReversal_win1TStart,
                                      'stop': self.ctrl.PSPReversal_win1TStop,
                                      'updater': self.update_windows,
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
                                      'updater': self.update_windows,
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
                                     'updater': self.update_rmp_window,
                                     'units': 'ms'}
            self.ctrl.PSPReversal_showHide_lrrmp.region = self.regions['lrrmp']['region']  # save region with checkbox
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
                # if self.regions[reg]['mode'] is not None:
                #     self.regions[reg]['mode'].currentIndexChanged.connect(self.interactive_analysis)
            self.regions_exist = True
        for reg in self.regions.keys():
            for s in ['start', 'stop']:
                self.regions[reg][s].setSuffix(' ' + self.regions[reg]['units'])

    def update_windows(self, **kwargs):
        """
        automatically update all the lr region windows in the display
        :param kwargs:
        :return:
        """
        if self.auto_updater:
            self.update_win_analysis(**kwargs)

    def update_rmp_window(self, **kwargs):
        """
        update the position of the lr region used to measure the resting membrane potential
        :param kwargs:
        :return:
        """
        if self.auto_updater:
            self.update_rmp_analysis(**kwargs)

    def show_or_hide(self, lrregion=None, forcestate=None):
        """
        Show or hide specific regions in the display
        :param lrregion: name of the region ('lrwin0', etc)
        :param forcestate: set True to force the show status
        :return:
        """
        if lrregion is None:
            print('PSPReversal:show_or_hide:: lrregion is {:<s}').format(lrregion)
            return
        region = self.regions[lrregion]
        if forcestate is not None:
            if forcestate:
                region['region'].show()
                region['state'].setChecked(Qt.Qt.Checked)
                region['shstate'] = True
            else:
                region['region'].hide()
                region['state'].setChecked(Qt.Qt.Unchecked)
                region['shstate'] = False
        else:
            if not region['shstate']:
                region['region'].show()
                region['state'].setChecked(Qt.Qt.Checked)
                region['shstate'] = True
            else:
                region['region'].hide()
                region['state'].setChecked(Qt.Qt.Unchecked)
                region['shstate'] = False

    def uniq(self, inlist):
        """
         order preserving detection of unique values in a list
        :param inlist:
        :return:
        """
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
        keys = list(self.sequence.keys())
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
        self.analysis_summary['Temp'] = self.dataModel.getTemp(dh)
        self.analysis_summary['CellType'] = self.dataModel.getCellType(dh)
        ct = self.analysis_summary['Cell']['__timestamp__']
        pt = dh.info()['__timestamp__']
        self.analysis_summary['ElapsedTime'] = pt-ct  # save elapsed time between cell opening and protocol start
        (date, sliceid, cell, proto, p3) = self.file_cell_protocol()
        self.analysis_summary['CellID'] = os.path.join(date, sliceid, cell)  # use this as the "ID" for the cell later on

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
#        print 'loadfilerequested dh: ', dh

        if len(dh) == 0:
            raise Exception("PSPReversal::loadFileRequested: " +
                            "Select an IV protocol directory.")
        if len(dh) != 1:
            raise Exception("PSPReversal::loadFileRequested: " +
                            "Can only load one file at a time.")
        self.clear_results()
#        if self.current_dirhandle != dh[0]:  # is this the current file/directory?
        self.get_file_information(default_dh=dh)  # No, get info from most recent file requested
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

        # i = 0  # sometimes, the elements are not right...
        for i, directory_name in enumerate(dirs):  # dirs has the names of the runs withing the protocol
            data_dir_handle = dh[directory_name]  # get the directory within the protocol
            try:
                data_file_handle = self.dataModel.getClampFile(data_dir_handle)  # get pointer to clamp data
                # Check if no clamp file for this iteration of the protocol
                # (probably the protocol was stopped early)
                if data_file_handle is None:
                    print('PSPReversal::loadFileRequested: ',
                          'Missing data in %s, element: %d' % (directory_name, i))
                    continue
            except:
                print("Error loading data for protocol %s:"
                      % directory_name)
                continue  # If something goes wrong here, we just carry on
            data_file = data_file_handle.read()
            self.devicesUsed = self.dataModel.getDevices(data_dir_handle)
            self.holding = self.dataModel.getClampHoldingLevel(data_file_handle)
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
                self.command_scale_factor = 1e12
                self.command_units = 'pA'
            elif self.data_mode in self.vc_modes:
                self.command_units = 'mV'
                self.command_scale_factor = 1e3
            else:  # data mode not known; plot as voltage
                self.command_units = 'V'
                self.command_scale_factor = 1.0

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
                cval = self.command_scale_factor * sequence_values[i]
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
            # pick up and save the sequence values
            if len(sequence_values) > 0:
                self.values.append(sequence_values[i])
            else:
                self.values.append(cmd[len(cmd) / 2])
        #    i += 1
        #sys.settrace(trace_calls_and_returns)
        if traces is None or len(traces) == 0:
            print("PSPReversal::loadFileRequested: No data found in this run...")
            return False
        if self.amp_settings['WCCompValid']:
            if self.amp_settings['WCEnabled'] and self.amp_settings['CompEnabled']:
                self.r_uncomp = self.amp_settings['WCResistance'] * (1.0 - self.amp_settings['CompCorrection'] / 100.)
            else:
                self.r_uncomp = 0.
        self.ctrl.PSPReversal_R_unCompensated.setValue(self.r_uncomp * 1e-6)  # convert to Mohm to display
        self.ctrl.PSPReversal_R_unCompensated.setSuffix(u" M\u2126")
        self.ctrl.PSPReversal_Holding.setText('%.1f mV' % (float(self.holding) * 1e3))

        # put relative to the start
        self.trace_times -= self.trace_times[0]
        traces = np.vstack(traces)
        self.cmd_wave = np.vstack(cmd_wave)
        self.time_base = np.array(cmd.xvals('Time'))
        commands = np.array(self.values)
        self.color_scale.setIntColorScale(0, len(dirs), maxValue=200)
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

        vc_command = data_dir_handle.parent().info()['devices']['Clamp1']  # ['channels']['Command']
        vc_info = vc_command['waveGeneratorWidget']['stimuli']['Pulse']

        # cmddata = cmd.view(np.ndarray)
        # cmddiff = np.abs(cmddata[1:] - cmddata[:-1])
        # if self.data_mode in self.ic_modes:
        #     mindiff = 1e-12
        # else:
        #     mindiff = 1e-4
        # cmdtimes1 = np.argwhere(cmddiff >= mindiff)[:, 0]
        # cmddiff2 = cmdtimes1[1:] - cmdtimes1[:-1]
        # cmdtimes2 = np.argwhere(cmddiff2 > 1)[:, 0]
        # if len(cmdtimes1) > 0 and len(cmdtimes2) > 0:
        #     cmdtimes = np.append(cmdtimes1[0], cmddiff2[cmdtimes2])
        # else:  # just fake it
        #     cmdtimes = np.array([0.01, 0.1])
        pulsestart = vc_info['start']['value']
        pulsedur = vc_info['length']['value']
        cmdtimes = np.array([pulsestart, pulsedur])
        if self.ctrl.PSPReversal_KeepT.isChecked() is False:
            self.tstart = cmdtimes[0] # cmd.xvals('Time')[cmdtimes[0]]
            self.tend = np.sum(cmdtimes)  #cmd.xvals('Time')[cmdtimes[1]] + self.tstart
            self.tdur = self.tend - self.tstart

        # build the list of command values that are used for the fitting
        cmdList = []
        for i in range(len(self.values)):
            cmdList.append('%8.3f %s' %
                           (self.command_scale_factor * self.values[i], self.command_units))
        self.ctrl.PSPReversal_tauh_Commands.clear()
        self.ctrl.PSPReversal_tauh_Commands.addItems(cmdList)
        self.sample_interval = 1.0 / sfreq
        self.makemap_symbols()
        if self.ctrl.PSPReversal_KeepT.isChecked() is False:
            self.tstart += self.sample_interval
            self.tend += self.sample_interval
        # if self.data_mode in self.ic_modes:
        #     # for adaptation ratio:
        #     self.update_all_analysis()
        if self.data_mode in self.vc_modes:
            self.cmd = commands
            self.spikecount = np.zeros(len(np.array(self.values)))

        # and also plot
        self.plot_traces()
        self.setup_regions()
        self._host_.dockArea.findAll()[1]['Parameters'].raiseDock()  # parameters window to the top
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
        return (date, sliceid, cell, proto, p3)

    def plot_traces(self, multimode=False):
        """
        Plot the current data traces.
        :param multimode: try using "multiline plot routine" to speed up plots (no color though)
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
        self.data_plot.plotItem.clearPlots()
        self.cmd_plot.plotItem.clearPlots()
        average_flag = self.ctrl.PSPReversal_AveragePlot.isChecked()
        alternation_flag = self.ctrl.PSPReversal_Alternation.isChecked()
        ntr = self.traces.shape[0]
        self.data_plot.setDownsampling(auto=False, mode='mean')
        self.data_plot.setClipToView(True)
        self.cmd_plot.setDownsampling(auto=False, mode='mean')
        self.cmd_plot.setClipToView(True)
        self.data_plot.disableAutoRange()
        self.cmd_plot.disableAutoRange()
        cmdindxs = np.unique(self.cmd)  # find the unique voltages
        colindxs = [int(np.where(cmdindxs == self.cmd[i])[0]) for i in range(len(self.cmd))]  # make a list to use
        nskip = 1
        if average_flag:
            ntr = len(self.cmd)/len(self.repc)
            nskip = len(self.cmd)/len(self.repc)
        if alternation_flag:
            pass
            #ntr /= 2
        if multimode:
            datalines = MultiLine(self.time_base, self.traces, downsample=20)
            self.data_plot.addItem(datalines)
            cmdlines = MultiLine(self.time_base, self.cmd_wave, downsample=20)
            self.cmd_plot.addItem(cmdlines)
        else:
            for i in range(ntr):
                plotthistrace = True
                if alternation_flag:  # only plot the alternate traces
                    if ((self.ctrl.PSPReversal_EvenOdd.isChecked() and (i % 2 == 0))  # plot the evens
                            or (not self.ctrl.PSPReversal_EvenOdd.isChecked() and (i % 2 != 0))):  # plot the evens
                        plotthistrace = True
                    else:
                        plotthistrace = False
                if plotthistrace:
                    if average_flag:
                        atrace = np.mean(self.traces[i::nskip], axis=0)
                        acmdwave = np.mean(self.cmd_wave[i::nskip], axis=0)
                    else:
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
        and stimulus events (e.g., the blue LED time)
        :return:
        """
        prior_updater=self.auto_updater
        self.auto_updater=False
#        print 'setup regions: auto updater: ', self.auto_updater
        self.initialize_regions()  # now create the analysis regions
        if self.ctrl.PSPReversal_KeepT.isChecked() is False:  # change regions; otherwise keep...
            if 'LED-Blue' in self.devicesUsed:
                tdur1 = 0.2
                tstart1 = self.led_info['start'] - 0.2
                tdur1 = self.tend-tstart1-(2e-3)
                tdur2 = self.led_info['length']  # go 5 times the duration.
                if tdur2 > 16e-3:
                    tdur2 = 16e-3
                tstart2 = self.led_info['start']+4*1e-3  # 4 msec auto delay
                if tstart2 + tdur2 > self.tend:
                    tdur2 = self.tend - tstart2  # restrict duration to end of the trace
                tstart0 = self.led_info['start']
                tdur0 = self.tend-tstart0-60.0e-3 # at least 50 msec before the end
            else:
                tstart1 = self.tstart+0.4
                tdur1 = self.tstart / 5.0
                tdur2 = self.tdur / 2.0
                tstart2 = self.tend - tdur2
                tstart0 = tstart2
                tdur0 = 0.1

            tend = self.tend - 0.001

            self.regions['lrwin0']['region'].setRegion([tstart0,
                                                        tstart0 + tdur0])
            # reference window
            self.regions['lrwin1']['region'].setRegion([tstart1,
                                                        tstart1 + tdur1])
            # meausurement:
            self.regions['lrwin2']['region'].setRegion([tstart2,
                                                        tstart2 + tdur2])
            self.regions['lrrmp']['region'].setRegion([1.e-4, self.tstart * 0.9])  # rmp window

        for r in ['lrwin0', 'lrwin1', 'lrwin2', 'lrrmp']:
            self.regions[r]['region'].setBounds([0., np.max(self.time_base)])  # limit regions to data
        self.auto_updater = prior_updater

    def interactive_analysis(self):
        """
        Interactive_analysis: reads the analysis parameters, counts the spikes
            and forces an update of all the analysis in the process...
        This method is meant to be called by a button click
        :param : None
        :return: nothing
        """
        self.auto_updater = True  # allow dynamic updating
        self.get_window_analysisPars()
        self.update_all_analysis()

    def update_all_analysis(self):
        """
        do an update of the analysis of all the windows with the current parameters
        Draws new plots to the IV curve window
        :return:
        """
        self.update_rmp_analysis()  # rmp must be done separately
        self.count_spikes()
        for i in range(0,3):
            win = 'win%d' % i #  in ['win0', 'win1', 'win2']:
            self.update_win_analysis(win)

#     def get_window_analysisPars(self):
# #        print '\ngetwindow: analysis pars: ', self.analysis_parameters
#         for region in ['lrwin0', 'lrwin1', 'lrwin2', 'lrrmp']:
#             rgninfo = self.regions[region]['region'].getRegion()  # from the display
#             self.regions[region]['start'].setValue(rgninfo[0] * 1.0e3)  # report values to screen
#             self.regions[region]['stop'].setValue(rgninfo[1] * 1.0e3)
#             self.analysis_parameters[region] = {'times': rgninfo}
# #        print '\nafter loop: ', self.analysis_parameters
#         for region in ['lrwin1', 'lrwin2']:
#             self.analysis_parameters[region]['mode'] = self.regions[region]['mode'].currentText()
#         self.analysis_parameters['lrwin0']['mode'] = 'Mean'
# #        print '\nand finally: ', self.analysis_parameters
#         self.get_alternation()  # get values into the analysisPars dictionary
#         self.get_baseline()
#         self.get_junction()

    def finalize_analysis_summary(self):
        """
        finish filling out the analysis_summary dictionary with general information
        about the cell, in preparation for print out.
        Computes the best fit polynomial to the IV curve in window 2.
        :return:
        """
        (date, sliceid, cell, proto, p2) = self.file_cell_protocol()
        self.cell_summary(self.current_dirhandle)
        self.analysis_summary['CellID'] = str(date+'/'+sliceid+'/'+cell)
        self.analysis_summary['Protocol'] = proto
        jp = float(self.analysis_parameters['junction'])
        ho = float(self.holding) * 1e3  # convert to mV
        self.analysis_summary['JP'] = jp
        self.analysis_summary['HoldV'] = ho
       #  vc = np.array(self.win2IV['vc']+jp+ho)
       #  im = np.array(self.win2IV['im'])
       # # imsd = np.array(self.win2IV['imsd'])
       #  fit_order = 3
       #  #fit_coeffs = np.polyfit(vc, im, fit_order)  # 3rd order polynomial
       #  tck = scipy.interpolate.splrep(vc, im, s=0, k=fit_order)
        tck = self.win2IV['spline']  # get spline data fit
        fit_order = tck[2]
        fit_coeffs = tck[1]
        for n in range(fit_order+1):
            self.analysis_summary['p'+str(n)] = fit_coeffs[n]
        # find the roots
        #r = np.roots(fit_coeffs)
        r = scipy.interpolate.sproot(tck)
        #reversal = [None]*fit_order
        r = [x*1e3+jp+ho for x in r]  # add jp and holding here
        reversal = [None]*len(r)
        #for i in range(0, fit_order):
        for i in range(0, len(r)):
            reversal[i] = {'value': r[i], 'valid': False}
        anyrev = False
        revvals = ''
        revno = []
        self.analysis_summary['Erev'] = np.isnan
        for n in range(len(reversal)):  # print only the valid reversal values, which includes real, not imaginary roots
            if (np.abs(np.imag(reversal[n]['value'])) == 0.0) and (-100. < np.real(reversal[n]['value']) < 40.):
                reversal[n]['valid'] = True
                if anyrev:
                    revvals += ', '
                revvals += ('{:5.1f}'.format(float(np.real(reversal[n]['value']))))
                revno.append(float(np.real(reversal[n]['value'])))
                anyrev = True
        if not anyrev:
            revvals = 'Not fnd'
        self.analysis_summary['revvals'] = revvals
        if anyrev:
            self.analysis_summary['Erev'] = revno[0]
        else:
            self.analysis_summary['Erev'] = np.nan
        # computes slopes at Erev[0] and at -60 mV (as a standard)
        ## using polynomials
        # #p1 = np.polyder(fit_coeffs, 1)
        #p60 = np.polyval(p1, -60.)
        # using spline fit
        # The spline fit was done with data not corrected for the jp or ho, so 
        # we make that adjustment here for the relative voltages
        # e.g., -60 - (-7+-50) is -60+57 = -3 mV relative to holding (-50-7)
        v60 = (-60 - (jp + ho))/1e3
        p60 = scipy.interpolate.splev([v60], tck, der=1)
        # same correction for +13 mV, which is the top command voltage used
        # e.g., 13 + 57 = 70 mV
        v13 = (13 - (jp + ho))/1e3
        p13 = scipy.interpolate.splev([v13], tck, der=1)
        #p60 = scipy.interpolate.splev(p1, tck, der=0)
        if len(revno) > 0:
            #perev = np.polyval(p1, revno[0])
            v0 = (revno[0] -(jp + ho))/1e3
           # print 'v0: ', v0
            perev = scipy.interpolate.splev([v0], tck, der=1)
        else:
            perev = 0.
       # print 'p60: ', p60
        self.analysis_summary['spline'] = tck  # save the spline fit information
        self.analysis_summary['gsyn_60'] = p60[0] * 1e9  #  original im in A, vm in V, g converted to nS
        self.analysis_summary['gsyn_13'] = p13[0] * 1e9
        self.analysis_summary['gsyn_Erev'] = perev[0] * 1e9  # nS
        self.analysis_summary['I_ionic-'] = np.min(self.measure['win1'])*1e9  # nA
        self.analysis_summary['I_ionic+'] = np.max(self.measure['win1'])*1e9  # nA

        self.analysis_summary['LPF'] = self.clamp_state['LPFCutoff'] * 1e-3  # kHz
        self.analysis_summary['Gain'] = self.clamp_state['primaryGain']
        self.analysis_summary['Rs'] = self.amp_settings['WCResistance'] * 1e-6  # Mohm
        self.analysis_summary['Cm'] = self.amp_settings['WCCellCap'] * 1e12  # pF
        self.analysis_summary['Comp'] = self.amp_settings['CompCorrection']
        self.analysis_summary['BW'] = self.amp_settings['CompBW'] * 1e-3  # kHz
        self.analysis_summary['Ru'] = self.r_uncomp * 1e-6  # Mohm
        self.analysis_summary['ILeak'] = self.averageRMP*1e9  # express in nA

        for win in ['win1', 'win2', 'win0']:
            region = 'lr' + win
            rinfo = self.regions[region]['region'].getRegion()
            self.analysis_summary[win+'Start'] = rinfo[0]
            self.analysis_summary[win+'End'] = rinfo[1]

    def print_analysis(self):
        """
        Print the CCIV summary information (Cell, protocol, etc)
        Printing goes to the results window, where the data can be copied
        to another program like a spreadsheet.
        :return: html-decorated text
        """
        self.finalize_analysis_summary()
        (date, sliceid, cell, proto, p2) = self.file_cell_protocol()
        # The day summary may be missing elements, so we need to create dummies (dict is read-only)
        day = {}
        for x in ['age', 'weight', 'sex']:  # check to see if these are filled out
            if x not in self.analysis_summary.keys():
                day[x] = 'unknown'
               # self.analysis_summary['Day'][x] = day[x]
            else:
                day[x] = self.analysis_summary['Day'][x]
        for cond in ['ACSF', 'Internal', 'Temp']:
            if self.analysis_summary[cond] == '':
                self.analysis_summary[cond] = 'unknown'

        # format output in html
        rtxt = '<font face="monospace, courier">'  # use a monospaced font.
        rtxt += '<div style="white-space: pre;">'  # css to force repsect of spaces in text
        rtxt += ("{:^15s}  {:^5s}  {:^4s}  {:^12s}<br>".format
                 ("Date", "Slice", "Cell", "E<sub>rev</sub>"))
        rtxt += ("<b>{:^15s}  {:^5s}  {:^4s}  {:^8.2f}</b><br>".format
                 (date, sliceid[-3:], cell[-3:], self.analysis_summary['Erev']))
        rtxt += ('{:<8s}: <b>{:<32s}</b><br>'.format('Protocol', proto))
        rtxt += ('{:^8s}\t{:^8s}\t{:^8s}\t{:^8s}<br>'.format
                 ('Temp', 'Age', 'Weight', 'Sex'))
        rtxt += ('{:^8s}\t{:^8s}\t{:^8s}\t{:^8s}<br>'.format
                 (self.analysis_summary['Temp'], day['age'], day['weight'], day['sex']))
        rtxt += ('{:<8s}: {:<32s}<br>'.format('ACSF', self.analysis_summary['ACSF']))
        rtxt += ('{:<8s}: {:<32s}<br>'.format('Internal', self.analysis_summary['Internal']))
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

        rtxt += 'HP: {:5.1f} mV  JP: {:5.1f} mV<br>'.format(self.analysis_summary['HoldV'], self.analysis_summary['JP'])
        if 'diffFit' in self.win2IV.keys() and self.win2IV['diffFit'] is not None:
            rtxt += ('{0:<5s}: {1}<br>').format('Poly', ''.join('{:5.2e} '.format(a) for a in self.win2IV['diffFit']))
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
        for i in range(len(self.win2IV['vc'])):
            if self.ctrl.PSPReversal_RsCorr.isChecked():
                rtxt += (' {:>9.1f} '.format(self.win2IV['vc'][i] + self.analysis_summary['JP'] + self.analysis_summary['HoldV']))
            else:
                rtxt += (' {:>9.1f} '.format(self.win2IV['mvc'][i] + self.analysis_summary['JP'] + self.analysis_summary['HoldV']))
            rtxt += ('{:>9.3f} {:>9.3f} {:>6d}<br>'.format(self.win2IV['im'][i], self.win2IV['imsd'][i], self.nrepc))
        rtxt += ('-' * 40) + '<br></div></font>'
        self.results.resultsPSPReversal_text.setText(rtxt)
        # now raise the dock for visibility
        self._host_.dockArea.findAll()[1]['Results'].raiseDock()
        self.print_formatted_script_output(script_header=True, copytoclipboard=True)
        return rtxt

    def remove_html_markup(self, html_string):
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
        html_string = html_string.replace('<br>', '\n') # first just take of line breaks
        for char in html_string:
            if char == '<' and not quote:
                tag = True
            elif char == '>' and not quote:
                tag = False
            elif (char == '"' or char == "'") and tag:
                quote = not quote
            elif not tag:
                out = out + char
        return out

    def read_script(self, name=''):
        """
        read a script file from disk, and use that information to drive the analysis
        :param name:
        :return:
        """
        if not name:
            self.script_name = '/Users/pbmanis/Desktop/acq4_scripts/PSPReversal.cfg'

        self.script = configfile.readConfigFile(self.script_name)
        if self.script is None:
            print('failed to read script')
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
        """
        revalidate and run the current script
        :return:
        """
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
            print('script is not for PSPReversal (found %s)', self.script['module'])
            return False
        all_found = True
        trailingchars = [c for c in map(chr, range(97, 123))]  # trailing chars used to identify different parts of a cell's data
        for c in self.script['Cells']:
            if self.script['Cells'][c]['include'] is False:
                continue
            sortedkeys = sorted(self.script['Cells'][c]['manip'].keys())  # sort by order of recording
            for p in sortedkeys:
                pr = self.script['protocol'] + '_' + p  # add the underscore here
                if c[-1] in trailingchars:
                    cell = c[:-1]
                else:
                    cell = c
                fn = os.path.join(cell, pr)
                dm_selected_file = self.dataManager().selectedFile().name()
                fullpath = os.path.join(dm_selected_file, fn)
                file_ok = os.path.exists(fullpath)
                #if file_ok:
                #    print('File found: {:s}'.format(fullpath))
                if not file_ok:
                    print('  current dataManager self.dm points to file: ', dm_selected_file)
                    print('  and file not found was: ', fullpath)
                    all_found = False
                #else:
                #    print 'file found ok: %s' % fullpath
        return all_found

    def run_script(self):
        """
        Run a script, doing all of the requested analysis
        :return:
        """
        if self.script['testfiles']:
            return
        settext = self.scripts_form.PSPReversal_ScriptResults_text.setPlainText
        apptext = self.scripts_form.PSPReversal_ScriptResults_text.appendPlainText
        self.textout = ('Script File: {:<32s}'.format(self.script_name))
        settext(self.textout)
        script_header = True  # reset the table to a print new header for each cell
        trailingchars = [c for c in map(chr, range(97, 123))]  # trailing chars used to identify different parts of a cell's data
        for cell in self.script['Cells']:
            thiscell = self.script['Cells'][cell]
            if thiscell['include'] is False:  # skip this cell
                continue
            sortedkeys = sorted(thiscell['manip'].keys())  # sort by order of recording (# on protocol)
            for p in sortedkeys:
                if thiscell['manip'][p] not in self.script['datafilter']:  # pick out steady-state conditions
                 #   print 'p: %s not in data: ' % (thiscell['manip'][p]), self.script['datafilter']
                    continue
                #print 'working on %s' % thiscell['manip'][p]
                pr = self.script['protocol'] + '_' + p  # add the underscore here
                if cell[-1] in trailingchars:  # check last letter - if not a number clip it
                    cell_file = cell[:-1]
                else:
                    cell_file = cell
                fn = os.path.join(cell_file, pr)
                dm_selected_file = self.dataManager().selectedFile().name()
                fullpath = os.path.join(dm_selected_file, fn)
                file_ok = os.path.exists(fullpath)
                if not file_ok:  # get the directory handle and take it from there
                    continue
                self.ctrl.PSPReversal_KeepT.setChecked(Qt.Qt.Unchecked)  # make sure this is unchecked
                dh = self.dataManager().manager.dirHandle(fullpath)
                if not self.loadFileRequested([dh]):  # note: must pass a list
                    print('failed to load requested file: ', fullpath)
                    continue  # skip bad sets of records...
                apptext(('Protocol: {:<s} <br>Manipulation: {:<s}'.format(pr, thiscell['manip'][p])))
                self.analysis_summary['Drugs'] = thiscell['manip'][p]
                # alt_flag = bool(thiscell['alternation'])
                # self.analysis_parameters['alternation'] = alt_flag
                # self.ctrl.PSPReversal_Alternation.setChecked((Qt.Qt.Unchecked, Qt.Qt.Checked)[alt_flag])
                # if 'junctionpotential' in thiscell:
                #     self.analysis_parameters['junction'] = thiscell['junctionpotential']
                #     self.ctrl.PSPReversal_Junction.setValue(float(thiscell['junctionpotential']))
                # else:
                #     self.analysis_parameters['junction'] = float(self.script['global_jp'])
                #     self.ctrl.PSPReversal_Junction.setValue(float(self.script['global_jp']))

                self.auto_updater = False
                self.get_script_analysisPars(self.script, thiscell)
                m = thiscell['manip'][p]  # get the tag for the manipulation
                self.update_all_analysis()
                # self.update_rmp_analysis()
                # for win in ['win0', 'win1', 'win2']:
                #     self.update_win_analysis(win)
                ptxt = self.print_analysis()
                apptext(ptxt)
                self.textout += ptxt
               # print protocol result, optionally a cell header.
                self.print_formatted_script_output(script_header)
                script_header = False
        self.auto_updater = True # restore function
        print('\nDone')

    def get_window_analysisPars(self):
        """
        Retrieve the settings of the lr region windows, and some other general values
        in preparation for analysis
        :return:
        """
        self.analysis_parameters = {}  # start out empty so we are not fooled by priors
#        print '\ngetwindow: analysis pars: ', self.analysis_parameters
        for region in ['lrwin0', 'lrwin1', 'lrwin2', 'lrrmp']:
            rgninfo = self.regions[region]['region'].getRegion()  # from the display
            self.regions[region]['start'].setValue(rgninfo[0] * 1.0e3)  # report values to screen
            self.regions[region]['stop'].setValue(rgninfo[1] * 1.0e3)
            self.analysis_parameters[region] = {'times': rgninfo}
#        print '\nafter loop: ', self.analysis_parameters
        for region in ['lrwin1', 'lrwin2']:
            self.analysis_parameters[region]['mode'] = self.regions[region]['mode'].currentText()
        self.analysis_parameters['lrwin0']['mode'] = 'Mean'
#        print '\nand finally: ', self.analysis_parameters
        self.get_alternation()  # get values into the analysisPars dictionary
        self.get_baseline()
        self.get_junction()

    def get_script_analysisPars(self, script_globals, thiscell):
        """
        set the analysis times and modes from the script. Also updates the qt windows
        :return: Nothing.
        """
        self.analysis_parameters = {}
        self.analysis_parameters['baseline'] = False

        self.analysis_parameters['lrwin1'] = {}
        self.analysis_parameters['lrwin2'] = {}
        self.analysis_parameters['lrwin0'] = {}
        self.analysis_parameters['lrrmp'] = {}
        self.auto_updater = False  # turn off the updates
        scriptg = {'global_jp': ['junction'], 'global_win1_mode': ['lrwin1', 'mode'],
                   'global_win2_mode': ['lrwin2', 'mode']}
        for k in scriptg.keys():  # set globals first
            if len(scriptg[k]) == 1:
                self.analysis_parameters[scriptg[k][0]] = script_globals[k]
            else:
                self.analysis_parameters[scriptg[k][0]] = {scriptg[k][1]: script_globals[k]}
        if 'junctionpotential' in thiscell:
            self.analysis_parameters['junction'] = thiscell['junctionpotential']
        if 'alternation' in thiscell:
            self.analysis_parameters['alternation'] = thiscell['alternation']
        else:
            self.analysis_parameters['alternation'] = True

        for n in range(0, 3):  # get the current region definitions
            self.regions['lrwin%d'%n]['region'].setRegion([x*1e-3 for x in thiscell['win%d'%n]])
            self.regions['lrwin%d'%n]['start'].setValue(thiscell['win%d'%n][0])
            self.regions['lrwin%d'%n]['stop'].setValue(thiscell['win%d'%n][1])
            self.analysis_parameters['lrwin%d'%n]['times'] = [t*1e-3 for t in thiscell['win%d'%n]]  # convert to sec
            self.show_or_hide('lrwin%d'%n, forcestate=True)

        for win in ['win1', 'win2']:  # set the modes for the 2 windows
            winmode = win+'_mode'
            lrwinx = 'lr'+win
            if winmode in thiscell:
                thiswin = thiscell[winmode]
                r = self.regions[lrwinx]['mode'].findText(thiswin)
                if r >= 0:
                    print('setting %s mode to %s ' % (win, thiswin))
                    self.regions[lrwinx]['mode'].setCurrentIndex(r)
                    self.analysis_parameters[lrwinx]['mode'] = thiswin
                else:
                    print('%s analysis mode not recognized: %s' % (win, thiswin))
            else:
                r = self.regions[lrwinx]['mode'].findText(self.analysis_parameters[lrwinx]['mode'])
                if r >= 0:
                    self.regions[lrwinx]['mode'].setCurrentIndex(r)
        return

    def print_script_output(self):
        """
        print(a clean version of the results to the terminal)
        :return:
        """
        print(self.remove_html_markup(self.textout))

    def copy_script_output(self):
        """
        Copy script output (results) to system clipboard
        :return: Nothing
        """
        self.scripts_form.PSPReversal_ScriptResults_text.copy()

    def print_formatted_script_output(self, script_header=True, copytoclipboard=False):
        """
        Print a nice formatted version of the analysis output to the terminal.
        The output can be copied to another program (excel, prism) for further analysis
        :param script_header:
        :return:
        """
        data_template = (OrderedDict([('ElapsedTime', '{:>8.2f}'), ('Drugs', '{:<8s}'), ('HoldV', '{:>5.1f}'), ('JP', '{:>5.1f}'),
                                                                        ('Rs', '{:>6.2f}'), ('Cm', '{:>6.1f}'), ('Ru', '{:>6.2f}'),
                                                                        ('Erev', '{:>6.2f}'),
                                                                        ('gsyn_Erev', '{:>9.2f}'), ('gsyn_60', '{:>7.2f}'), ('gsyn_13', '{:>7.2f}'), 
                                                                        #('p0', '{:6.3e}'), ('p1', '{:6.3e}'), ('p2', '{:6.3e}'), ('p3', '{:6.3e}'),
                                                                        ('I_ionic+', '{:>8.3f}'), ('I_ionic-', '{:>8.3f}'), ('ILeak', '{:>7.3f}'),
                                                                        ('win1Start', '{:>9.3f}'), ('win1End', '{:>7.3f}'),
                                                                        ('win2Start', '{:>9.3f}'), ('win2End', '{:>7.3f}'),
                                                                        ('win0Start', '{:>9.3f}'), ('win0End', '{:>7.3f}'),
                                                                        ]))
        # summary table header is written anew for each cell
        if script_header:
            print('{:34s}\t{:24s}\t'.format("Cell", "Protocol")),
            for k in data_template.keys():
                print('{:<s}\t'.format(k)),
            print('')
        ltxt = ''
        ltxt += ('{:34s}\t{:24s}\t'.format(self.analysis_summary['CellID'], self.analysis_summary['Protocol']))

        for a in data_template.keys():
            if a in self.analysis_summary.keys():
                ltxt += ((data_template[a] + '\t').format(self.analysis_summary[a]))
            else:
                ltxt += '<   >\t'
        print(ltxt)
        if copytoclipboard:
            clipb = Qt.QApplication.clipboard()
            clipb.clear(mode=clipb.Clipboard )
            clipb.setText(ltxt, mode=clipb.Clipboard)


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
#        if not self.auto_updater:  # do nothing if auto update is off
#            return 'no auto updater'
        window = region
        region = 'lr' + window
        if window is None:
            return 'no window'
        if self.traces is None:
            return 'no traces'

        if window == 'win0':
            return 'window 0 called' # we don't use for calculations, just marking times


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

       # import pprint
       # pp = pprint.PrettyPrinter(indent=4)
       # pp.pprint(self.analysis_parameters)

        mode = self.analysis_parameters[region]['mode']
        rgninfo = self.analysis_parameters[region]['times']
        data1 = self.traces['Time': rgninfo[0]:rgninfo[1]]  # extract analysis region
        tx1 = ma.compressed(ma.masked_outside(self.time_base, rgninfo[0], rgninfo[1]))  # time to match data1
        if tx1.shape[0] > data1.shape[1]:
            tx1 = tx1[0:-1]  # clip extra point. Rules must be different between traces clipping and masking.
        if window == 'win1':  # check if win1 overlaps with win0, and select data
#            print '***** WINDOW 1 SETUP *****'
            r0 = self.analysis_parameters['lrwin0']['times'] #regions['lrwin0']['region'].getRegion()
            tx = ma.masked_inside(tx1, r0[0], r0[1])  #
            if tx.mask.all():  # handle case where win1 is entirely inside win2
                print('update_win_analysis: Window 1 is entirely inside Window 0: No analysis possible')
                print('rgninfo: ', rgninfo)
                print('r0: ', r0)
                return 'bad window1/0 relationship'
            data1 = ma.array(data1, mask=ma.resize(ma.getmask(tx), data1.shape))
            self.txm = ma.compressed(tx)  # now compress tx as well
            self.win1fits = None  # reset the fits

        if data1.shape[1] == 0 or data1.shape[0] == 1:
            print('no data to analyze?')
            return 'no data'  # skip it
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
            txw1 = ma.compressed(ma.masked_inside(self.time_base, rgninfo[0], rgninfo[1]))
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
            txw1 = ma.compressed(ma.masked_inside(self.time_base, rgninfo[0], rgninfo[1]))
            fits = np.zeros((data1.shape[0], txw1.shape[0]))
            for j in range(data1.shape[0]):  # polyval only does 1d
                fits[j, :] = np.polyval(self.win1fits[:, j], txw1)
            self.measure[winbkgd] = fits.mean(axis=1)
            self.measure[window] = data1.mean(axis=1)
        if mode in ['Min', 'Max', 'Mean', 'Sum', 'Abs', 'Linear', 'Poly2']:
            self.measure[winraw_i] = self.measure[window]  # save raw measured current before corrections
        elif mode not in ['Mean-Win1', 'Mean-Linear', 'Mean-Poly2', 'Sum-Win1']:
            print('update_win_analysis: Mode %s is not recognized (1)' % mode)
            return 'bad mode'
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
            print('update_win_analysis: Mode %s is not recognized (2)' % mode)
            return 'bad mode'
        else:
            pass

        if self.analysis_parameters['baseline']:
            self.measure[window] = self.measure[window] - self.measure['rmp']
        if len(self.nospk) >= 1 and self.data_mode in self.ic_modes:
            # Steady-state IV where there are no spikes
            print('update_win_analysis: Removing traces with spikes from analysis')
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
                self.measure[winorigcmd] = commands  # save original
                self.measure[wincmd] = np.array(commands) - self.r_uncomp * np.array(self.measure[winraw_i])  # IR drop across uncompensated
                self.cmd = commands
            else:
                self.measure[winorigcmd] = commands
                self.measure[wincmd] = commands
                self.cmd = commands
            self.measure['leak'] = np.zeros(len(self.measure[window]))
        self.measure[winunordered] = self.measure[window]

        # now separate the data into alternation groups, then sort by command level
        if self.analysis_parameters['alternation'] and window == 'win2':
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
        self.fit_IV()
        self.update_IVPlot()
        self.update_command_timeplot(wincmd)
        return 'OK'

    def fit_IV(self):
        """
        compute polynomial fit to iv
        No corrections for holding or jp are done here.
        :return: True if successful; False if the analysis hasn't been done
        """
        if 'win2altcmd' in self.measure.keys() and len(self.measure['win2altcmd']) == 0:
            self.win2IV = {}
            return False

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

        fit_order = 3  # minimum to use root finder in splines
        tck = scipy.interpolate.splrep(self.measure['win2altcmd'], self.measure['win2on'],
                                       s=1, k=fit_order)
        vpl = np.arange(float(np.min(self.measure['win2altcmd'])),
                        float(np.max(self.measure['win2altcmd'])), 1e-3)
        #p = np.polyfit(self.measure['win2altcmd'], self.measure['win2on'], 3)
        #ipl = np.polyval(p, vpl)
        ipl = scipy.interpolate.splev(vpl, tck)
        self.win2IV = {'vc': vc * 1e3, 'im': im * 1e9, 'imsd': imsd * 1e9, 'mvc': mvc * 1e3,
                       'vpl': vpl, 'ipl': ipl, 'diffFit': [], 'spline': tck, 'poly': []}
        return True


    def update_command_timeplot(self, wincmd):
        """
        replot the command voltage versus time
        :param wincmd:
        :return:
        """
        (pen, filledbrush, emptybrush, symbol, n, clear_flag) = self.map_symbol()

        self.command_plot.plot(x=self.trace_times, y=self.cmd, clear=clear_flag,
                               symbolSize=6,
                               symbol=symbol, pen=pen,
                               symbolPen=pen, symbolBrush=filledbrush)

    def update_rmp_analysis(self, region=None, clear=True, pw=False):
        """
            Compute the RMP over time/commands from the selected window
        """
        if not self.auto_updater:
            return False
        if self.traces is None:
            return False
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
        return True

    def makemap_symbols(self):
        """
        Given the current state of things, (keep analysis count, for example),
        return a tuple of pen, fill color, empty color, a symbol from
        our lists, and a clear_flag. Used to overplot different data.
        """
        n = self.keep_analysis_count
        pen = next(self.color_list)
        filledbrush = pen
        emptybrush = None
        symbol = next(self.symbol_list)
        if n == 0:
            clear_flag = True
        else:
            clear_flag = False
        self.current_symbol_dict = {'pen': pen, 'filledbrush': filledbrush,
                                    'emptybrush': emptybrush, 'symbol': symbol,
                                    'n': n, 'clear_flag': clear_flag}

    def map_symbol(self):
        """
        return a new map symbol
        :return:
        """
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
            self.iv_plot.addLine(x=0, pen=pg.mkPen('888', width=0.5, style=Qt.Qt.DashLine))
            self.iv_plot.addLine(y=0, pen=pg.mkPen('888', width=0.5, style=Qt.Qt.DashLine))
        jp = self.analysis_parameters['junction']  # get offsets for voltage
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
                if not self.analysis_parameters['alternation']:
                    self.iv_plot.plot(offset + self.measure['win2cmd'] * 1e3, self.measure['win2'] * 1e9,
                                      symbol=symbol, pen=None,
                                      symbolSize=6, symbolPen=pen, # pg.mkPen({'color': "00F", 'width': 1}),
                                      symbolBrush=filledbrush)
                else:
                    if len(self.measure['win2altcmd']) > 0:
                        self.iv_plot.plot(offset + self.measure['win2altcmd'] * 1e3, self.measure['win2on'] * 1e9,
                                          symbol=symbol, pen=None,
                                          symbolSize=4, symbolPen=pen, # pg.mkPen({'color': "00F", 'width': 1}),
                                          symbolBrush=filledbrush)
                        if len(self.win2IV) == 0:
                            return
                        avPen = pg.mkPen({'color': "F00", 'width': 1})
                        fitPen = pg.mkPen({'color': "F00", 'width': 1})
                        self.iv_plot.plot(offset + self.win2IV['vc'], self.win2IV['im'],
                                          pen=None,  # no lines
                                          symbol=symbol, symbolSize=8, # 'o', symbolSize=6,
                                          symbolPen=pen, symbolBrush=filledbrush)
                        self.iv_plot.plot(offset + self.win2IV['vpl'] * 1e3, self.win2IV['ipl'] * 1e9,
                                          pen=fitPen)  # lines

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
                print('Selected RMP x axis mode not known: %s' % mode)

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
            return 'spikes already counted'
        if self.keep_analysis_count == 0:
            clear_flag = True
        else:
            clear_flag = False
        ntr = len(self.traces)
        self.spikecount = np.zeros(ntr)
        self.fsl = np.zeros(ntr)
        self.fisi = np.zeros(ntr)
        self.adaptation_ratio = np.zeros(ntr)
        self.nospk = range(0, len(self.traces))
        self.spk = np.zeros(ntr)
        if self.data_mode not in self.ic_modes or self.time_base is None:
            # print ('PSPReversal::count_spikes: Cannot count spikes, ' +
            #       'and dataMode is ', self.dataMode, 'and ICModes are: ', self.ic_modes , 'tx is: ', self.time_base)
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
            return 'not in a current-clamp mode'
        minspk = 4
        maxspk = 10  # range of spike counts
        # threshold = self.ctrl.PSPReversal_SpikeThreshold.value() * 1e-3
        threshold = 0.0
        # rmp = np.zeros(ntr)
        # # rmp is taken from the mean of all the baselines in the traces
        # self.Rmp = np.mean(rmp)

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
            self.fsl[i] = spike[0] - self.tstart
            if len(spike) > 1:
                self.fisi[i] = spike[1] - spike[0]
                # for Adaptation ratio analysis
            if (len(spike) >= minspk) and (len(spike) <= maxspk):
                misi = np.mean(np.diff(spike[-3:]))
                self.ar[i] = misi / self.isi[i]
            (self.rmp[i], r2) = Utility.measure('mean', self.time_base, self.traces[i],
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
        return 'OK'

    # def update_tau(self, print_window=True):
    #     """
    #     Compute time constant (single exponential) from the
    #     onset of the response
    #     using lrwin2 window, and only the smallest 3 steps...
    #     """
    #     if not self.cmd:  # probably not ready yet to do the update.
    #         return
    #     if self.data_mode not in self.ic_modes:  # only permit in IC
    #         return
    #     rgnpk = self.lrwin2.getRegion()
    #     func = 'exp1'  # single exponential fit.
    #     fits = Fitting.Fitting()
    #     initpars = [-60.0 * 1e-3, -5.0 * 1e-3, 10.0 * 1e-3]
    #     icmdneg = np.where(self.cmd < 0)
    #     maxcmd = np.min(self.cmd)
    #     ineg = np.where(self.cmd[icmdneg] >= maxcmd / 3)
    #     whichdata = ineg[0]
    #     itaucmd = self.cmd[ineg]
    #     whichaxis = 0
    #
    #     (fpar, xf, yf, names) = fits.FitRegion(whichdata, whichaxis,
    #                                            self.time_base,
    #                                            self.traces,
    #                                            dataType='xy',
    #                                            t0=rgnpk[0], t1=rgnpk[1],
    #                                            fitFunc=func,
    #                                            fitPars=initpars,
    #                                            method='simplex')
    #     if fpar == []:
    #         print 'PSPReversal::update_tau: Charging tau fitting failed - see log'
    #         return
    #     taus = []
    #     for j in range(0, fpar.shape[0]):
    #         outstr = ""
    #         taus.append(fpar[j][2])
    #         for i in range(0, len(names[j])):
    #             outstr = outstr + ('%s = %f, ' % (names[j][i], fpar[j][i]))
    #         if print_window:
    #             print("FIT(%d, %.1f pA): %s " %
    #                   (whichdata[j], itaucmd[j] * 1e12, outstr))
    #     meantau = np.mean(taus)
    #     self.ctrl.PSPReversal_Tau.setText(u'%18.1f ms' % (meantau * 1.e3))
    #     self.tau = meantau
    #     tautext = 'Mean Tau: %8.1f'
    #     if print_window:
    #         print tautext % (meantau * 1e3)
    #
    # def update_tauh(self, printWindow=False):
    #     """ compute tau (single exponential) from the onset of the markers
    #         using lrtau window, and only for the step closest to the selected
    #         current level in the GUI window.
    #
    #         Also compute the ratio of the sag from the peak (marker1) to the
    #         end of the trace (marker 2).
    #         Based on analysis in Fujino and Oertel, J. Neuroscience 2001,
    #         to type cells based on different Ih kinetics and magnitude.
    #     """
    #     if self.ctrl.PSPReversal_showHide_lrtau.isChecked() is not True:
    #         return
    #     rgn = self.lrtau.getRegion()
    #     func = 'exp1'  # single exponential fit to the whole region
    #     fits = Fitting.Fitting()
    #     initpars = [-80.0 * 1e-3, -10.0 * 1e-3, 50.0 * 1e-3]
    #
    #     # find the current level that is closest to the target current
    #     s_target = self.ctrl.PSPReversal_tauh_Commands.currentIndex()
    #     itarget = self.values[s_target]  # retrive actual value from commands
    #     self.neg_cmd = itarget
    #     idiff = np.abs(np.array(self.cmd) - itarget)
    #     amin = np.argmin(idiff)  # amin appears to be the same as s_target
    #     # target trace (as selected in cmd drop-down list):
    #     target = self.traces[amin]
    #     # get Vrmp -  # rmp approximation.
    #     vrmp = np.median(target['Time': 0.0:self.tstart - 0.005]) * 1000.
    #     self.ctrl.PSPReversal_vrmp.setText('%8.2f' % (vrmp))
    #     self.neg_vrmp = vrmp
    #     # get peak and steady-state voltages
    #     peak_region = self.lrwin2.getRegion()
    #     steadstate_region = self.lrwin1.getRegion()
    #     vpk = target['Time': peak_region[0]:peak_region[1]].min() * 1000
    #     self.neg_pk = (vpk - vrmp) / 1000.
    #     vss = np.median(target['Time': steadstate_region[0]:steadstate_region[1]]) * 1000
    #     self.neg_ss = (vss - vrmp) / 1000.
    #     whichdata = [int(amin)]
    #     itaucmd = [self.cmd[amin]]
    #     self.ctrl.PSPReversal_tau2TStart.setValue(rgn[0] * 1.0e3)
    #     self.ctrl.PSPReversal_tau2TStop.setValue(rgn[1] * 1.0e3)
    #     fd = self.traces['Time': rgn[0]:rgn[1]][whichdata][0]
    #     if self.fitted_data is None:  # first time through..
    #         self.fitted_data = self.data_plot.plot(fd, pen=pg.mkPen('w'))
    #     else:
    #         self.fitted_data.clear()
    #         self.fitted_data = self.data_plot.plot(fd, pen=pg.mkPen('w'))
    #         self.fitted_data.update()
    #     # now do the fit
    #     whichaxis = 0
    #     (fpar, xf, yf, names) = fits.FitRegion(whichdata, whichaxis,
    #                                            self.traces.xvals('Time'),
    #                                            self.traces.view(np.ndarray),
    #                                            dataType='2d',
    #                                            t0=rgn[0], t1=rgn[1],
    #                                            fitFunc=func,
    #                                            fitPars=initpars)
    #     if not fpar:
    #         print 'PSPReversal::update_tauh: tau_h fitting failed - see log'
    #         return
    #     redpen = pg.mkPen('r', width=1.5, style=Qt.Qt.DashLine)
    #     if self.fit_curve is None:
    #         self.fit_curve = self.data_plot.plot(xf[0], yf[0],
    #                                              pen=redpen)
    #     else:
    #         self.fit_curve.clear()
    #         self.fit_curve = self.data_plot.plot(xf[0], yf[0],
    #                                              pen=redpen)
    #         self.fit_curve.update()
    #     s = np.shape(fpar)
    #     taus = []
    #     for j in range(0, s[0]):
    #         outstr = ""
    #         taus.append(fpar[j][2])
    #         for i in range(0, len(names[j])):
    #             outstr += ('%s = %f, ' %
    #                        (names[j][i], fpar[j][i] * 1000.))
    #         if printWindow:
    #             print("Ih FIT(%d, %.1f pA): %s " %
    #                   (whichdata[j], itaucmd[j] * 1e12, outstr))
    #     meantau = np.mean(taus)
    #     self.ctrl.PSPReversal_Tauh.setText(u'%8.1f ms' % (meantau * 1.e3))
    #     self.tau2 = meantau
    #     bovera = (vss - vrmp) / (vpk - vrmp)
    #     self.ctrl.PSPReversal_Ih_ba.setText('%8.1f' % (bovera * 100.))
    #     self.ctrl.PSPReversal_win2Amp.setText('%8.2f' % (vss - vrmp))
    #     self.ctrl.PSPReversal_win1Amp.setText('%8.2f' % (vpk - vrmp))
    #     if bovera < 0.55 and self.tau2 < 0.015:  #
    #         self.ctrl.PSPReversal_FOType.setText('D Stellate')
    #     else:
    #         self.ctrl.PSPReversal_FOType.setText('T Stellate')
    #         # estimate of Gh:
    #     Gpk = itarget / self.neg_pk
    #     Gss = itarget / self.neg_ss
    #     self.Gh = Gss - Gpk
    #     self.ctrl.PSPReversal_Gh.setText('%8.2f nS' % (self.Gh * 1e9))

    def dbstore_clicked(self):
        """
        Store data into the current database for further analysis
        """
        return
        # self.update_all_analysis()
        # db = self._host_.dm.currentDatabase()
        # table = 'DirTable_Cell'
        # columns = OrderedDict([
        #     ('PSPReversal_rmp', 'real'),
        #     ('PSPReversal_rinp', 'real'),
        #     ('PSPReversal_taum', 'real'),
        #     ('PSPReversal_neg_cmd', 'real'),
        #     ('PSPReversal_neg_pk', 'real'),
        #     ('PSPReversal_neg_ss', 'real'),
        #     ('PSPReversal_h_tau', 'real'),
        #     ('PSPReversal_h_g', 'real'),
        # ])
        #
        # rec = {
        #     'PSPReversal_rmp': self.neg_vrmp / 1000.,
        #     'PSPReversal_rinp': self.r_in,
        #     'PSPReversal_taum': self.tau,
        #     'PSPReversal_neg_cmd': self.neg_cmd,
        #     'PSPReversal_neg_pk': self.neg_pk,
        #     'PSPReversal_neg_ss': self.neg_ss,
        #     'PSPReversal_h_tau': self.tau2,
        #     'PSPReversal_h_g': self.Gh,
        # }
        #
        # with db.transaction():
        #     # Add columns if needed
        #     if 'PSPReversal_rmp' not in db.tableSchema(table):
        #         for col, typ in columns.items():
        #             db.addColumn(table, col, typ)
        #
        #     db.update(table, rec, where={'Dir': self.current_dirhandle.parent()})
        # print "updated record for ", self.current_dirhandle.name()

    # ---- Helpers ----
    # Some of these would normally live in a pyqtgraph-related module, but are
    # just stuck here to get the job done.
    #
    def label_up(self, plot, xtext, ytext, title):
        """helper to label up the plot"""
        plot.setLabel('bottom', xtext)
        plot.setLabel('left', ytext)
        plot.setTitle(title)
