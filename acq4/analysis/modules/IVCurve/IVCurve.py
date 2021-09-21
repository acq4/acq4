# -*- coding: utf-8 -*-
from __future__ import print_function
from six.moves import range
"""
IVCurve: Analysis module that analyzes current-voltage and firing
relationships from current clamp data.
This is part of Acq4

Paul B. Manis, Ph.D.
2011-2013.

Pep8 compliant (via pep8.py) 10/25/2013
Refactoring begun 3/21/2015

"""

from collections import OrderedDict
import os
import os.path
import itertools
import functools
import numpy as np
import scipy
from acq4.util import Qt
from acq4.analysis.AnalysisModule import AnalysisModule
import pyqtgraph as pg
import acq4.util.matplotlibexporter as matplotlibexporter
import acq4.analysis.tools.Utility as Utility  # pbm's utilities...
import acq4.analysis.tools.Fitting as Fitting  # pbm's fitting stuff...
import acq4.analysis.tools.ScriptProcessor as ScriptProcessor
import pprint
import time

Ui_Form = Qt.importTemplate('.ctrlTemplate')


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

        self.Clamps = self.dataModel.GetClamps()  # access the "GetClamps" class for reading data
        self.data_template = (
          OrderedDict([('Species', (12, '{:>12s}')), ('Age', (5, '{:>5s}')), ('Sex', (3, '{:>3s}')), ('Weight', (6, '{:>6s}')),
                       ('Temperature', (10, '{:>10s}')), ('ElapsedTime', (11, '{:>11.2f}')), 
                       ('RMP', (5, '{:>5.1f}')), ('Rin', (5, '{:>5.1f}')), ('Bridge', (5, '{:>5.1f}')),
                       ('tau', (5, '{:>5.1f}')), ('AdaptRatio', (9, '{:>9.3f}')),
                       ('tauh', (5, '{:>5.1f}')), ('Gh', (6, '{:>6.2f}')),
                       ('FiringRate', (12, '{:>9.1f}')), 
                       ('AP1_HalfWidth', (13, '{:>13.2f}')), ('AP1_Latency', (11, '{:>11.1f}')), 
                       ('AP2_HalfWidth', (13, '{:>13.2f}')), ('AP2_Latency', (11, '{:>11.1f}')), 
                       ('AHP_Depth', (9, '{:9.2f}')),
                       ('Description', (11, '{:s}')),
                      ]))
        self.Script = ScriptProcessor.ScriptProcessor(host)
        self.Script.setAnalysis(analysis=self.updateAnalysis, 
            fileloader = self.loadFileRequested, template = self.data_template,
            clamps = self.Clamps, printer=self.printAnalysis,
            dbupdate=self.dbStoreClicked)  # specify the routines to be called and data sets to be used
        self.loaded = None
        self.filename = None
        self.dirsSet = None
        self.lrss_flag = True  # show is default
        self.lrpk_flag = True
        self.rmp_flag = True
        self.bridgeCorrection = None # bridge  correction in Mohm.
        self.showFISI = True # show FISI or ISI as a function of spike number (when False)
        self.lrtau_flag = False
        self.regions_exist = False
        self.tauh_fits = {}
        self.tauh_fitted = {}
        self.tau_fits = {}
        self.tau_fitted = {}
        self.regions_exist = False
        self.regions = {}
        self.analysis_summary = {}
        self.tx = None
        self.keep_analysis_count = 0
        self.dataMarkers = []
        self.doUpdates = True
        self.colors = ['w', 'g', 'b', 'r', 'y', 'c']
        self.symbols = ['o', 's', 't', 'd', '+']
        self.color_list = itertools.cycle(self.colors)
        self.symbol_list = itertools.cycle(self.symbols)
        self.script_header = False
        self.Clamps.data_mode = 'IC'  # analysis depends on the type of data we have.
        self.clear_results()

        # --------------graphical elements-----------------
        self._sizeHint = (1280, 900)  # try to establish size of window
        self.ctrlWidget = Qt.QWidget()
        self.ctrl = Ui_Form()
        self.ctrl.setupUi(self.ctrlWidget)
        self.main_layout = pg.GraphicsView()  # instead of GraphicsScene?
        # make fixed widget for the module output
        self.widget = Qt.QWidget()
        self.gridLayout = Qt.QGridLayout()
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
        self.ctrl.IVCurve_PrintResults.clicked.connect(
            functools.partial(self.printAnalysis, printnow=True, 
            script_header=True))

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
         for x in [self.update_rmpAnalysis, self.analyzeSpikes]]
        self.ctrl.IVCurve_FISI_ISI_button.clicked.connect(self.displayFISI_ISI)
        self.ctrl.dbStoreBtn.clicked.connect(self.dbStoreClicked)
        self.ctrl.IVCurve_OpenScript_Btn.clicked.connect(self.read_script)
        self.ctrl.IVCurve_RunScript_Btn.clicked.connect(self.rerun_script)
        self.ctrl.IVCurve_PrintScript_Btn.clicked.connect(self.Script.print_script_output)
        #self.scripts_form.PSPReversal_ScriptCopy_Btn.clicked.connect(self.copy_script_output)
        #self.scripts_form.PSPReversal_ScriptFormatted_Btn.clicked.connect(self.print_formatted_script_output)
        self.ctrl.IVCurve_ScriptName.setText('None')
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
        Clear results resets variables.
        This is typically needed every time a new data set is loaded.
        """
        
        self.filename = ''
        self.r_in = 0.0
        self.tau = 0.0
        self.adapt_ratio = 0.0
        self.spikes_counted = False
        self.nospk = []
        self.spk = []
        self.Sequence = ''
        self.ivss = []  # steady-state IV (window 2)
        self.ivpk = []  # peak IV (window 1)

        self.fsl = []  # first spike latency
        self.fisi = []  # first isi
        self.rmp = []  # resting membrane potential during sequence
        self.analysis_summary = {}
        self.script_header = True

    def resetKeepAnalysis(self):
        self.keep_analysis_count = 0  # reset counter.

    def show_or_hide(self, lrregion='', forcestate=None):
        """
        Show or hide specific regions in the display
        
        Parameters
        ----------
        lrregion : str, default: ''
            name of the region('lrwin0', etc)
        forcestate : None or Boolean, default: None
            Set True to force the show status, False to Hide. 
            If forcestate is None, then uses the region's 'shstate' value 
            to set the state.
        
        Returns
        -------
        nothing
        
        """
        if lrregion == '':
            print('PSPReversal:show_or_hide:: lrregion is {:<s}'.format(lrregion))
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

    def displayFISI_ISI(self):
        """
        Control display of first interspike interval/first spike latency
        versus ISI over time.
        """
        if self.showFISI:  # currently showin FISI/FSL; switch to ISI over time
            self.showFISI = False
        else:
            self.showFISI = True
        self.update_SpikePlots()

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
            self.regions['lrleak'] = {'name': 'leak',  # use a "leak" window
                                      'region': pg.LinearRegionItem([0, 1], orientation=pg.LinearRegionItem.Horizontal,
                                                                    brush=pg.mkBrush(255, 255, 0, 50.)),
                                      'plot': self.cmd_plot,
                                      'state': self.ctrl.IVCurve_subLeak,
                                      'shstate': False,  # keep internal copy of the state
                                      'mode': self.ctrl.IVCurve_subLeak.isChecked(),
                                      'start': self.ctrl.IVCurve_LeakMin,
                                      'stop': self.ctrl.IVCurve_LeakMax,
                                      'updater': self.updateAnalysis,
                                      'units': 'pA'}
            self.ctrl.IVCurve_subLeak.region = self.regions['lrleak']['region']  # save region with checkbox
            self.regions['lrwin0'] = {'name': 'win0',  # peak window
                                      'region': pg.LinearRegionItem([0, 1],
                                                                    brush=pg.mkBrush(128, 128, 128, 50.)),
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
                                     'updater': self.update_Tauh,
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
        for reg in self.regions.values():
            for s in ['start', 'stop']:
                reg[s].setSuffix(' ' + reg['units'])
        self.regions_exist = True

    def get_file_information(self, default_dh=None):
        """
        get_file_information reads the sequence information from the
        currently selected data file
        Two-dimensional sequences are supported.
        
        Parameter
        ---------
        default_dh : data handle, default None
            the data handle to use to access the file information
            
        Return
        ------
        nothing:
        """
        
        if default_dh is None:
            dh = self.file_loader_instance.selectedFiles()
        else:
            dh = default_dh
        if not dh or len(dh) == 0:  # when using scripts, the fileloader may not know..
                return
        dh = dh[0]  # only the first file
        sequence = self.dataModel.listSequenceParams(dh)
        keys = list(sequence.keys())
        leftseq = [str(x) for x in sequence[keys[0]]]
        if len(keys) > 1:
            rightseq = [str(x) for x in sequence[keys[1]]]
        else:
            rightseq = []
        leftseq.insert(0, 'All')
        rightseq.insert(0, 'All')
        
        ### specific to our program - relocate
        self.ctrl.IVCurve_Sequence1.clear()
        self.ctrl.IVCurve_Sequence2.clear()
        self.ctrl.IVCurve_Sequence1.addItems(leftseq)
        self.ctrl.IVCurve_Sequence2.addItems(rightseq)
        self.sequence = sequence

    def updaterStatus(self, mode='on'):
        """
        Change the auto updater status
        """
        for regkey, reg in self.regions.items():
            if mode in ['on', 'On', True]:
                self.doUpdates = True
                reg['region'].sigRegionChangeFinished.connect(
                    functools.partial(reg['updater'], region=reg['name']))
            if  mode in ['off', 'Off', None, False]:
                self.doUpdates = False
                try:
                    reg['region'].sigRegionChangeFinished.disconnect()
                except:  # may already be disconnected...so fail gracefully
                    pass

    def loadFileRequested(self, dh, analyze=True, bridge=None):
        """
        loadFileRequested is called by "file loader" when a file is requested.
            FileLoader is provided by the AnalysisModule class
            dh is the handle to the currently selected directory (or directories)

        This function loads all of the successive records from the specified protocol.
        Ancillary information from the protocol is stored in class variables.
        Extracts information about the commands, sometimes using a rather
        simplified set of assumptions. Much of the work for reading the data is
        performed in the GetClamps class in PatchEPhys.
        :param dh: the directory handle (or list of handles) representing the selected
        entitites from the FileLoader in the Analysis Module
        :modifies: plots, sequence, data arrays, data mode, etc.
        :return: True if successful; otherwise raises an exception
        """

        self.data_plot.clearPlots()
        self.cmd_plot.clearPlots()
        self.clear_results()
        self.updaterStatus('Off')
        
        if len(dh) == 0:
            raise Exception("IVCurve::loadFileRequested: " +
                            "Select an IV protocol directory.")
        if len(dh) != 1:
            raise Exception("IVCurve::loadFileRequested: " +
                            "Can only load one file at a time.")

        self.get_file_information(default_dh=dh)  # Get info from most recent file requested
        dh = dh[0]  # just get the first one
        self.filename = dh.name()
        self.current_dirhandle = dh  # this is critical!
        self.loaded = dh
        self.analysis_summary = self.dataModel.cell_summary(dh)  # get other info as needed for the protocol
       # print 'analysis summary: ', self.analysis_summary
 
        pars = {}  # need to pass some parameters from the GUI
        pars['limits'] = self.ctrl.IVCurve_IVLimits.isChecked()  # checkbox: True if loading limited current range
        pars['cmin'] = self.ctrl.IVCurve_IVLimitMin.value()  # minimum current level to load
        pars['cmax'] = self.ctrl.IVCurve_IVLimitMax.value()  # maximum current level to load
        pars['KeepT'] = self.ctrl.IVCurve_KeepT.isChecked()  # keep timebase
        # sequence selections:
        # pars[''sequence'] is a dictionary
        # The dictionary has  'index' (currentIndex()) and 'count' from the GUI
        pars['sequence1'] = {'index': [self.ctrl.IVCurve_Sequence1.currentIndex() - 1]}
        pars['sequence1']['count'] = self.ctrl.IVCurve_Sequence1.count() - 1
        pars['sequence2'] = {'index': [self.ctrl.IVCurve_Sequence2.currentIndex() - 1]}
        pars['sequence2']['count'] = self.ctrl.IVCurve_Sequence2.count() - 1

        ci = self.Clamps.getClampData(dh, pars)
        if ci is None:
            return False
        self.ctrl.IVCurve_dataMode.setText(self.Clamps.data_mode)
        # self.bridgeCorrection = 200e6

        # print 'bridge: ', bridge
        if bridge is not None:
            self.bridgeCorrection = bridge
            self.ctrl.IVCurve_bridge.setValue(self.bridgeCorrection)
            #for i in range(self.Clamps.traces.shape[0]):
            print('******** Doing bridge correction: ', self.bridgeCorrection)
            self.Clamps.traces = self.Clamps.traces - (self.bridgeCorrection * self.Clamps.cmd_wave)
        else:
            br = self.ctrl.IVCurve_bridge.value()*1e6
            # print 'br: ', br
            if br != 0.0:
                self.bridgeCorrection = br
                self.Clamps.traces = self.Clamps.traces - (self.bridgeCorrection * self.Clamps.cmd_wave)
            else:
                self.bridgeCorrection = None
        # now plot the data 
        self.ctrl.IVCurve_tauh_Commands.clear()
        self.ctrl.IVCurve_tauh_Commands.addItems(ci['cmdList'])
        self.color_scale.setIntColorScale(0, len(ci['dirs']), maxValue=200)
        self.make_map_symbols()
        self.plot_traces()
        self.setup_regions()
        self.get_window_analysisPars()  # prepare the analysis parameters
        self.updaterStatus('on')  # re-enable update status
        if analyze:  # only do this if requested (default). Don't do in script processing ....yet
            self.updateAnalysis()
        return True

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
        self.clearDecorators()
        self.make_map_symbols()
        self.data_plot.plotItem.clearPlots()
        self.cmd_plot.plotItem.clearPlots()
        ntr = self.Clamps.traces.shape[0]
        self.data_plot.setDownsampling(auto=False, mode='mean')
        self.data_plot.setClipToView(False)  # setting True deletes some points used for decoration of spikes by shape
        self.cmd_plot.setDownsampling(auto=False, mode='mean')
        self.cmd_plot.setClipToView(True)  # can leave this true since we do not put symbols on the plot
        self.data_plot.disableAutoRange()
        self.cmd_plot.disableAutoRange()
        cmdindxs = np.unique(self.Clamps.commandLevels)  # find the unique voltages
        colindxs = [int(np.where(cmdindxs == self.Clamps.commandLevels[i])[0]) for i in range(len(self.Clamps.commandLevels))]  # make a list to use

        if multimode:
            pass
            # datalines = MultiLine(self.Clamps.time_base, self.Clamps.traces, downsample=10)
            # self.data_plot.addItem(datalines)
            # cmdlines = MultiLine(self.Clamps.time_base, self.Clamps.cmd_wave, downsample=10)
            # self.cmd_plot.addItem(cmdlines)
        else:
            for i in range(ntr):
                atrace = self.Clamps.traces[i]
                acmdwave = self.Clamps.cmd_wave[i]
                self.data_plot.plot(x=self.Clamps.time_base, y=atrace, downSample=10, downSampleMethod='mean',
                                    pen=pg.intColor(colindxs[i], len(cmdindxs), maxValue=255))
                self.cmd_plot.plot(x=self.Clamps.time_base, y=acmdwave, downSample=10, downSampleMethod='mean',
                                   pen=pg.intColor(colindxs[i], len(cmdindxs), maxValue=255))

        if self.Clamps.data_mode in self.dataModel.ic_modes:
            self.label_up(self.data_plot, 'T (s)', 'V (V)', 'Data')
            self.label_up(self.cmd_plot, 'T (s)', 'I (%s)' % self.Clamps.command_units, 'Data')
        elif self.Clamps.data_mode in self.dataModel.vc_modes:  # voltage clamp
            self.label_up(self.data_plot, 'T (s)', 'I (A)', 'Data')
            self.label_up(self.cmd_plot, 'T (s)', 'V (%s)' % self.Clamps.command_units, 'Data')
        else:  # mode is not known: plot both as V
            self.label_up(self.data_plot, 'T (s)', 'V (V)', 'Data')
            self.label_up(self.cmd_plot, 'T (s)', 'V (%s)' % self.Clamps.command_units, 'Data')
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
            tstart_pk = self.Clamps.tstart
            tdur_pk = self.Clamps.tdur * 0.4  # use first 40% of trace for peak
            tstart_ss = self.Clamps.tstart + 0.75 * self.Clamps.tdur
            tdur_ss = self.Clamps.tdur * 0.25
            tstart_tau = self.Clamps.tstart + 0.1 * self.Clamps.tdur
            tdur_tau = 0.9 * self.Clamps.tdur
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
            self.regions['lrrmp']['region'].setRegion([0., self.Clamps.tstart * 0.9])  # rmp window
            # print 'rmp window region: ', self.Clamps.tstart * 0.9
        for r in ['lrtau', 'lrwin0', 'lrwin1', 'lrrmp']:
            self.regions[r]['region'].setBounds([0., np.max(self.Clamps.time_base)])  # limit regions to data

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
        

    def updateAnalysis(self, presets=None, region=None):
        """updateAnalysis re-reads the time parameters and re-analyzes the spikes"""
#        print 'self.Script.script: ', self.Script.script['Cells'].keys()
        if presets in [True, False]:
            presets = None
#        print '\n\n*******\n', traceback.format_stack(limit=7)
        if presets is not None and type(presets) == type({}):  # copy from dictionary of presets into analysis parameters
            for k in presets.keys():
                self.analysis_summary[k] = presets[k]
            if 'SpikeThreshold' in presets.keys():
                self.ctrl.IVCurve_SpikeThreshold.setValue(float(presets['SpikeThreshold']))
                #print 'set threshold to %f' % float(presets['SpikeThreshold'])
            if 'bridgeCorrection' in presets.keys():
                self.bridgeCorrection = presets['bridgeCorrection']
                print('####### BRIDGE CORRRECTION #######: ', self.bridgeCorrection)
            else:
                self.bridgeCorrection = 0.
        self.get_window_analysisPars()
#        print 'updateanalysis: readparsupdate'
        self.readParsUpdate(clearFlag=True, pw=False)
        
    def readParsUpdate(self, clearFlag=False, pw=False):
        """
        Read the parameter window entries, set the lr regions to the values
        in the window, and do an update on the analysis
        
        Parameters
        ----------
        clearFlag : Boolean, False
            appears to be unused
        pw : Boolean, False
            appears to be unused
        
        """
        if not self.doUpdates:
            return
        # analyze spikes first (gets information on which traces to exclude/include for other calculations) 
#        print 'readparsupdate, calling analyze spikes'
        self.analyzeSpikes()

        self.analysis_summary['tauh'] = np.nan  # define these because they may not get filled...
        self.analysis_summary['Gh'] = np.nan
        
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
        
        self.analyzeSpikeShape()  # finally do the spike shape
        self.ctrl.IVCurve_bridge.setValue(0.)  # reset bridge value after analysis.

    def read_script(self, name=''):
        """
        read a script file from disk, and use that information to drive the analysis
        :param name:
        :return:
        """
        
        self.script_name = self.Script.read_script()
        if self.script_name is None:
            print('Failed to read script')
            self.ctrl.IVCurve_ScriptName.setText('None')
            return
        self.ctrl.IVCurve_ScriptName.setText(os.path.basename(self.script_name))
        self.Script.run_script()

    def rerun_script(self):
        """
        revalidate and run the current script
        :return:
        """
        self.Script.run_script()

    def analyzeSpikes(self):
        """
        analyzeSpikes: Using the threshold set in the control panel, count the
        number of spikes in the stimulation window (self.Clamps.tstart, self.Clamps.tend)
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
        self.analysis_summary['FI_Curve'] = None
        # print '***** analyzing Spikes'
        if self.Clamps.data_mode not in self.dataModel.ic_modes or self.Clamps.time_base is None:
            print('IVCurve::analyzeSpikes: Cannot count spikes, ' +
                  'and dataMode is ', self.Clamps.data_mode, 'and ICModes are: ', self.dataModel.ic_modes, 'tx is: ', self.tx)
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
        twin = self.Clamps.tend - self.Clamps.tstart  # measurements window in seconds
        maxspkrate = 50  # max rate to count  in adaptation is 50 spikes/second
        minspk = 4
        maxspk = int(maxspkrate*twin)  # scale max dount by range of spike counts
        threshold = self.ctrl.IVCurve_SpikeThreshold.value() * 1e-3
        self.analysis_summary['SpikeThreshold'] = self.ctrl.IVCurve_SpikeThreshold.value()
        ntr = len(self.Clamps.traces)
        self.spikecount = np.zeros(ntr)
        self.fsl = np.zeros(ntr)
        self.fisi = np.zeros(ntr)
        ar = np.zeros(ntr)
        self.allisi = {}
        self.spikes = [[] for i in range(ntr)]
        self.spikeIndices = [[] for i in range(ntr)]
        #print 'clamp start/end: ', self.Clamps.tstart, self.Clamps.tend
        for i in range(ntr):
            (spikes, spkx) = Utility.findspikes(self.Clamps.time_base, self.Clamps.traces[i],
                                              threshold, t0=self.Clamps.tstart,
                                              t1=self.Clamps.tend,
                                              dt=self.Clamps.sample_interval,
                                              mode='peak',  # best to use peak for detection
                                              interpolate=False,
                                              debug=False)
            if len(spikes) == 0:
                #print 'no spikes found'
                continue
            self.spikes[i] = spikes
            #print 'found %d spikes in trace %d' % (len(spikes), i)
            self.spikeIndices[i] = [np.argmin(np.fabs(self.Clamps.time_base-t)) for t in spikes]
            self.spikecount[i] = len(spikes)
            self.fsl[i] = (spikes[0] - self.Clamps.tstart)*1e3
            if len(spikes) > 1:
                self.fisi[i] = (spikes[1] - spikes[0])*1e3
                self.allisi[i] = np.diff(spikes)*1e3
            # for Adaptation ratio analysis
            if minspk <= len(spikes) <= maxspk:
                misi = np.mean(np.diff(spikes[-3:]))*1e3
                ar[i] = misi / self.fisi[i]

        iAR = np.where(ar > 0)
        self.adapt_ratio = np.mean(ar[iAR])  # only where we made the measurement
        self.analysis_summary['AdaptRatio'] = self.adapt_ratio
        self.ctrl.IVCurve_AR.setText(u'%7.3f' % self.adapt_ratio)
        self.nospk = np.where(self.spikecount == 0)
        self.spk = np.where(self.spikecount > 0)[0]
        self.analysis_summary['FI_Curve'] = np.array([self.Clamps.values, self.spikecount])
#        print self.analysis_summary['FI_Curve']
        self.spikes_counted = True
        self.update_SpikePlots()

    def _timeindex(self, t):
        return np.argmin(self.Clamps.time_base-t)
        
    def analyzeSpikeShape(self, printSpikeInfo=False):
        # analyze the spike shape.
        #  based on Druckman et al. Cerebral Cortex, 2013
        begin_dV = 12.0  # V/s or mV/ms
        ntr = len(self.Clamps.traces)
#        print 'analyzespikeshape, self.spk: ', self.spk
        self.spikeShape = OrderedDict()
        rmp = np.zeros(ntr)
        iHold = np.zeros(ntr)
        for i in range(ntr):
            if len(self.spikes[i]) == 0:
                continue
            trspikes = OrderedDict()
            if printSpikeInfo:
                print(np.array(self.Clamps.values))
                print(len(self.Clamps.traces))
            (rmp[i], r2) = Utility.measure('mean', self.Clamps.time_base, self.Clamps.traces[i],
                                           0.0, self.Clamps.tstart)            
            (iHold[i], r2) = Utility.measure('mean', self.Clamps.time_base, self.Clamps.cmd_wave[i],
                                              0.0, self.Clamps.tstart)
            for j in range(len(self.spikes[i])):
                thisspike = {'trace': i, 'AP_number': j, 'AP_beginIndex': None, 'AP_endIndex': None, 
                             'peakIndex': None, 'peak_T': None, 'peak_V': None, 'AP_Latency': None,
                             'AP_beginV': None, 'halfwidth': None, 'trough_T': None,
                             'trough_V': None, 'peaktotroughT': None,
                             'current': None, 'iHold': None,
                             'pulseDuration': None, 'tstart': self.Clamps.tstart}  # initialize the structure
                thisspike['current'] = self.Clamps.values[i] - iHold[i]
                thisspike['iHold'] = iHold[i]
                thisspike['pulseDuration'] = self.Clamps.tend - self.Clamps.tstart  # in seconds
                thisspike['peakIndex'] = self.spikeIndices[i][j]
                thisspike['peak_T'] = self.Clamps.time_base[thisspike['peakIndex']]
                thisspike['peak_V'] = self.Clamps.traces[i][thisspike['peakIndex']]  # max voltage of spike
                thisspike['tstart'] = self.Clamps.tstart
                
                # find the minimum going forward - that is AHP min
                dt = (self.Clamps.time_base[1]-self.Clamps.time_base[0])
                dv = np.diff(self.Clamps.traces[i])/dt
                k = self.spikeIndices[i][j] + 1
                if j < self.spikecount[i] - 1:  # find end of spike (top of next, or end of trace)
                    kend = self.spikeIndices[i][j+1]
                else:
                    kend = len(self.Clamps.traces[i])
                try:
                    km = np.argmin(dv[k:kend])+k # find fastst falling point, use that for start of detection
                except:
                    continue
#                v = self.Clamps.traces[i][km]
#                vlast = self.Clamps.traces[i][km]
                #kmin = np.argmin(np.argmin(dv2[k:kend])) + k  # np.argmin(np.fabs(self.Clamps.traces[i][k:kend]))+k
                kmin =  np.argmin(self.Clamps.traces[i][km:kend])+km
                thisspike['AP_endIndex'] = kmin
                thisspike['trough_T'] = self.Clamps.time_base[thisspike['AP_endIndex']]
                thisspike['trough_V'] = self.Clamps.traces[i][kmin]

                if thisspike['AP_endIndex'] is not None:
                    thisspike['peaktotrough'] = thisspike['trough_T'] - thisspike['peak_T']
                k = self.spikeIndices[i][j]-1
                if j > 0:
                    kbegin = self.spikeIndices[i][j-1] # trspikes[j-1]['AP_endIndex']  # self.spikeIndices[i][j-1]  # index to previ spike start
                else:
                    kbegin = k - int(0.002/dt)  # for first spike - 4 msec prior only
                    if kbegin*dt <= self.Clamps.tstart:
                        kbegin = kbegin + int(0.0002/dt)  # 1 msec 
                # revise k to start at max of rising phase
                try:
                    km = np.argmax(dv[kbegin:k]) + kbegin
                except:
                    continue
                if (km - kbegin < 1):
                    km = kbegin + int((k - kbegin)/2.) + 1
                kthresh = np.argmin(np.fabs(dv[kbegin:km] - begin_dV)) + kbegin  # point where slope is closest to begin
                thisspike['AP_beginIndex'] = kthresh
                thisspike['AP_Latency'] = self.Clamps.time_base[kthresh]
                thisspike['AP_beginV'] = self.Clamps.traces[i][thisspike['AP_beginIndex']]
                if thisspike['AP_beginIndex'] is not None and thisspike['AP_endIndex'] is not None:
                    halfv = 0.5*(thisspike['peak_V'] + thisspike['AP_beginV'])
                    kup = np.argmin(np.fabs(self.Clamps.traces[i][thisspike['AP_beginIndex']:thisspike['peakIndex']] - halfv))
                    kup += thisspike['AP_beginIndex']
                    kdown = np.argmin(np.fabs(self.Clamps.traces[i][thisspike['peakIndex']:thisspike['AP_endIndex']] - halfv))
                    kdown += thisspike['peakIndex'] 
                    if kup is not None and kdown is not None:
                        thisspike['halfwidth'] = self.Clamps.time_base[kdown] - self.Clamps.time_base[kup]
                        thisspike['hw_up'] = self.Clamps.time_base[kup]
                        thisspike['hw_down'] = self.Clamps.time_base[kdown]
                        thisspike['hw_v'] = halfv
                trspikes[j] = thisspike
            self.spikeShape[i] = trspikes
        if printSpikeInfo:
            pp = pprint.PrettyPrinter(indent=4)
            for m in sorted(self.spikeShape.keys()):
                print('----\nTrace: %d  has %d APs' % (m, len(list(self.spikeShape[m].keys()))))
                for n in sorted(self.spikeShape[m].keys()):
                    pp.pprint(self.spikeShape[m][n])
        self.analysis_summary['spikes'] = self.spikeShape  # save in the summary dictionary too       
        self.analysis_summary['iHold'] = np.mean(iHold)
        self.analysis_summary['pulseDuration'] = self.Clamps.tend - self.Clamps.tstart
        self.getClassifyingInfo()  # build analysis summary here as well.
        self.clearDecorators()
        self.spikeDecorator()

    def spikeDecorator(self):
        """
        Put markers on the spikes to visually confirm the analysis of thresholds, etc.
        """
        # get colors
        cmdindxs = np.unique(self.Clamps.commandLevels)  # find the unique voltages
        colindxs = [int(np.where(cmdindxs == self.Clamps.commandLevels[i])[0]) for i in range(len(self.Clamps.commandLevels))]  # make a list to use
        alllats = []
        allpeakt = []
        allpeakv = []
        for i, trace in enumerate(self.spikeShape):
            aps = []
            tps = []
            paps = []
            ptps = []
            taps = []
            ttps = []
            hwv = []
            tups = []
            tdps = []

            for j, spk in enumerate(self.spikeShape[trace]):
                aps.append(self.spikeShape[trace][spk]['AP_beginV'])
                alllats.append(self.spikeShape[trace][spk]['AP_Latency'])
                tps.append(self.spikeShape[trace][spk]['AP_Latency'])
            u =self.data_plot.plot(tps, aps, pen=None, symbol='o', brush=pg.mkBrush('g'), symbolSize=4)
            self.dataMarkers.append(u)
            for j, spk in enumerate(self.spikeShape[trace]):
                paps.append(self.spikeShape[trace][spk]['peak_V'])
                ptps.append(self.spikeShape[trace][spk]['peak_T'])
                allpeakt.append(self.spikeShape[trace][spk]['peak_T']+0.01)
                allpeakv.append(self.spikeShape[trace][spk]['peak_V'])
            # u = self.data_plot.plot(allpeakt, allpeakv, pen=None, symbol='o', brush=pg.mkBrush('r'), size=2)
            # self.dataMarkers.append(u)

            u = self.data_plot.plot(ptps, paps, pen=None, symbol='t', brush=pg.mkBrush('w'), symbolSize=4)
            self.dataMarkers.append(u)

            for j, spk in enumerate(self.spikeShape[trace]):
                taps.append(self.spikeShape[trace][spk]['trough_V'])
                ttps.append(self.spikeShape[trace][spk]['trough_T'])
            u = self.data_plot.plot(ttps, taps, pen=None, symbol='+', brush=pg.mkBrush('r'), symbolSize=4)
            self.dataMarkers.append(u)
            for j, spk in enumerate(self.spikeShape[trace]):
                tups.append(self.spikeShape[trace][spk]['hw_up'])
                tdps.append(self.spikeShape[trace][spk]['hw_down'])
                hwv.append(self.spikeShape[trace][spk]['hw_v'])
            u =self.data_plot.plot(tups, hwv, pen=None, symbol='d', brush=pg.mkBrush('c'), symbolSize=4)
            self.dataMarkers.append(u)
            d =self.data_plot.plot(tdps, hwv, pen=None, symbol='s', brush=pg.mkBrush('c'), symbolSize=4)
            self.dataMarkers.append(d)

    def clearDecorators(self):
        if len(self.dataMarkers) > 0:
            [self.dataMarkers[k].clear() for k,m in enumerate(self.dataMarkers)]
        self.dataMarkers = []        
        
    def getIVCurrentThresholds(self):
        # figure out "threshold" for spike, get 150% and 300% points.
        nsp = []
        icmd = []
        for m in sorted(self.spikeShape.keys()):
            n = len(self.spikeShape[m].keys()) # number of spikes in the trace
            if n > 0:
                nsp.append(len(self.spikeShape[m].keys()))
                icmd.append(self.spikeShape[m][0]['current'])
        try:
            iamin = np.argmin(icmd)
        except:
            raise ValueError('IVCurve:getIVCurrentThresholds - icmd seems to be ? : ', icmd)
        imin = np.min(icmd)
        ia150 = np.argmin(np.abs(1.5*imin-np.array(icmd)))
        iacmdthr = np.argmin(np.abs(imin-self.Clamps.values))
        ia150cmdthr = np.argmin(np.abs(icmd[ia150] - self.Clamps.values))
        #print 'thr indices and values: ', iacmdthr, ia150cmdthr, self.Clamps.values[iacmdthr], self.Clamps.values[ia150cmdthr]
        return (iacmdthr, ia150cmdthr)  # return threshold indices into self.Clamps.values array at threshold and 150% point
    
    def getClassifyingInfo(self):
        """
        Adds the classifying information according to Druckmann et al., Cerebral Cortex, 2013
        to the analysis summary
        """
 
        (jthr, j150) = self.getIVCurrentThresholds()  # get the indices for the traces we need to pull data from
        if jthr == j150:
            print('\n%s:' % self.filename)
            print('Threshold current T and 1.5T the same: using next up value for j150')
            print('jthr, j150, len(spikeShape): ', jthr, j150, len(self.spikeShape))
            print('1 ', self.spikeShape[jthr][0]['current']*1e12)
            print('2 ', self.spikeShape[j150+1][0]['current']*1e12)
            print(' >> Threshold current: %8.3f   1.5T current: %8.3f, next up: %8.3f' % (self.spikeShape[jthr][0]['current']*1e12,
                  self.spikeShape[j150][0]['current']*1e12, self.spikeShape[j150+1][0]['current']*1e12))
            j150 = jthr + 1
        if len(self.spikeShape[j150]) >= 1 and self.spikeShape[j150][0]['halfwidth'] is not None:
            self.analysis_summary['AP1_Latency'] = (self.spikeShape[j150][0]['AP_Latency'] - self.spikeShape[j150][0]['tstart'])*1e3
            self.analysis_summary['AP1_HalfWidth'] = self.spikeShape[j150][0]['halfwidth']*1e3
        else:
            self.analysis_summary['AP1_Latency'] = np.inf
            self.analysis_summary['AP1_HalfWidth'] = np.inf
        
        if len(self.spikeShape[j150]) >= 2 and self.spikeShape[j150][1]['halfwidth'] is not None:
            self.analysis_summary['AP2_Latency'] = (self.spikeShape[j150][1]['AP_Latency'] - self.spikeShape[j150][1]['tstart'])*1e3
            self.analysis_summary['AP2_HalfWidth'] = self.spikeShape[j150][1]['halfwidth']*1e3
        else:
            self.analysis_summary['AP2_Latency'] = np.inf
            self.analysis_summary['AP2_HalfWidth'] = np.inf
        
        rate = len(self.spikeShape[j150])/self.spikeShape[j150][0]['pulseDuration']  # spikes per second, normalized for pulse duration
        # first AHP depth
        # print 'j150: ', j150
        # print self.spikeShape[j150][0].keys()
        # print self.spikeShape[j150]
        AHPDepth = self.spikeShape[j150][0]['AP_beginV'] - self.spikeShape[j150][0]['trough_V']
        self.analysis_summary['FiringRate'] = rate
        self.analysis_summary['AHP_Depth'] = AHPDepth*1e3  # convert to mV
        # pprint.pprint(self.analysis_summary)
        # except:
        #     raise ValueError ('Failed Classification for cell: %s' % self.filename)

    def update_Tau_membrane(self, peak_time=None, printWindow=False, whichTau=1, vrange=[-5., -20.]):
        """
        Compute time constant (single exponential) from the
        onset of the response
        using lrpk window, and only steps that produce a voltage change between 5 and 20 mV below rest
        or as specified
        """

        if len(self.Clamps.commandLevels) == 0:  # probably not ready yet to do the update.
            return
        if self.Clamps.data_mode not in self.dataModel.ic_modes:  # only permit in IC
            return
        rgnpk = list(self.regions['lrwin0']['region'].getRegion())
        Func = 'exp1'  # single exponential fit with DC offset.
        Fits = Fitting.Fitting()
        if self.rmp == []:
            self.update_rmpAnalysis()
        #print self.rmp
        initpars = [self.rmp*1e-3, 0.010, 0.01]
        peak_time = None
        icmdneg = np.where(self.Clamps.commandLevels < -20e-12)
        maxcmd = np.min(self.Clamps.commandLevels)
        ineg = np.where(self.Clamps.commandLevels[icmdneg] < 0.0)
        if peak_time is not None and ineg != np.array([]):
            rgnpk[1] = np.max(peak_time[ineg[0]])
        dt = self.Clamps.sample_interval
        rgnindx = [int((rgnpk[1]-0.005)/dt), int((rgnpk[1])/dt)]
        rmps = self.ivbaseline
        vmeans = np.mean(self.Clamps.traces[:, rgnindx[0]:rgnindx[1]].view(np.ndarray), axis=1) - self.ivbaseline
        indxs = np.where(np.logical_and((vrange[0]*1e-3 >= vmeans[ineg]), 
                         (vmeans[ineg] >= vrange[1]*1e-3)))
        indxs = list(indxs[0])
        whichdata = ineg[0][indxs]  # restricts to valid values
        itaucmd = self.Clamps.commandLevels[ineg]
        whichaxis = 0
        fpar = []
        names = []
        okdata = []
        if len(self.tau_fitted.keys()) > 0:
            [self.tau_fitted[k].clear() for k in self.tau_fitted.keys()]
        self.tau_fitted = {}
        for j, k in enumerate(whichdata):
            self.tau_fitted[j] = self.data_plot.plot(self.Clamps.time_base,  self.Clamps.traces[k], pen=pg.mkPen('w'))
            (fparx, xf, yf, namesx) = Fits.FitRegion([k], whichaxis,
                                               self.Clamps.time_base,
                                               self.Clamps.traces,
                                               dataType='2d',
                                               t0=rgnpk[0], t1=rgnpk[1],
                                               fitFunc=Func,
                                               fitPars=initpars,
                                               method='SLSQP',
                                               bounds=[(-0.1, 0.1), (-0.1, 0.1), (0.005, 0.30)])
        
            if not fparx:
              raise Exception('IVCurve::update_Tau_membrane: Charging tau fitting failed - see log')
            #print 'j: ', j, len(fpar)
            if fparx[0][1] < 2.5e-3:  # amplitude must be > 2.5 mV to be useful
                continue
            fpar.append(fparx[0])
            names.append(namesx[0])
            okdata.append(k)
        self.taupars = fpar
        self.tauwin = rgnpk
        self.taufunc = Func
        self.whichdata = okdata
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
            print(tautext % (meantau * 1e3))
        self.show_tau_plot()

    def show_tau_plot(self):
        Fits = Fitting.Fitting()
        fitPars = self.taupars
        xFit = np.zeros((len(self.taupars), 500))
        for i in range(len(self.taupars)):
          xFit[i,:] = np.arange(0, self.tauwin[1]-self.tauwin[0], (self.tauwin[1]-self.tauwin[0])/500.)
        yFit = np.zeros((len(fitPars), xFit.shape[1]))
        fitfunc = Fits.fitfuncmap[self.taufunc]
        if len(self.tau_fits.keys()) > 0:
            [self.tau_fits[k].clear() for k in self.tau_fits.keys()]
        self.tau_fits = {}
        for k, whichdata in enumerate(self.whichdata):
            yFit[k] = fitfunc[0](fitPars[k], xFit[k], C=None)  # +self.ivbaseline[whichdata]
            self.tau_fits[k] = self.data_plot.plot(xFit[k]+self.tauwin[0], yFit[k], pen=pg.mkPen('r', width=2, style=Qt.Qt.DashLine))
        
    def update_Tauh(self, region=None, printWindow=False):
        """ compute tau (single exponential) from the onset of the markers
            using lrtau window, and only for the step closest to the selected
            current level in the GUI window.
            
            Parameters
            ----------
            region : dummy argument, default : None
            printWindow : Boolean, default : False
                
            region is a dummy argument... 
            Also compute the ratio of the sag from the peak (marker1) to the
            end of the trace (marker 2).
            Based on analysis in Fujino and Oertel, J. Neuroscience 2001,
            to type cells based on different Ih kinetics and magnitude.
        """
        self.analysis_summary['tauh'] = np.nan
        self.analysis_summary['Gh'] = np.nan
        if not self.ctrl.IVCurve_showHide_lrtau.isChecked():
            return
        rgn = self.regions['lrtau']['region'].getRegion()
        Func = 'exp1'  # single exponential fit to the whole region
        Fits = Fitting.Fitting()

        initpars = [-80.0 * 1e-3, -10.0 * 1e-3, 50.0 * 1e-3]

        # find the current level that is closest to the target current
        s_target = self.ctrl.IVCurve_tauh_Commands.currentIndex()
        itarget = self.Clamps.values[s_target]  # retrive actual value from commands
        self.neg_cmd = itarget
        idiff = np.abs(np.array(self.Clamps.commandLevels) - itarget)
        amin = np.argmin(idiff)  # amin appears to be the same as s_target
        # target trace (as selected in cmd drop-down list):
        target = self.Clamps.traces[amin]
        # get Vrmp -  # rmp approximation.
        vrmp = np.median(target['Time': 0.0:self.Clamps.tstart - 0.005]) * 1000.
        self.neg_vrmp = vrmp
        # get peak and steady-state voltages
        pkRgn = self.regions['lrwin0']['region'].getRegion()
        ssRgn = self.regions['lrwin1']['region'].getRegion()
        vpk = target['Time': pkRgn[0]:pkRgn[1]].min() * 1000
        self.neg_pk = (vpk - vrmp) / 1000.
        vss = np.median(target['Time': ssRgn[0]:ssRgn[1]]) * 1000
        self.neg_ss = (vss - vrmp) / 1000.
        whichdata = [int(amin)]
        itaucmd = [self.Clamps.commandLevels[amin]]
        self.ctrl.IVCurve_tau2TStart.setValue(rgn[0] * 1.0e3)
        self.ctrl.IVCurve_tau2TStop.setValue(rgn[1] * 1.0e3)
        fd = self.Clamps.traces['Time': rgn[0]:rgn[1]][whichdata][0]
        if len(self.tauh_fitted.keys()) > 0:
            [self.tauh_fitted[k].clear() for k in self.tauh_fitted.keys()]
        self.tauh_fitted = {}
        for k, d in enumerate(whichdata):
            self.tauh_fitted[k] = self.data_plot.plot(fd, pen=pg.mkPen('w'))
            # now do the fit
        whichaxis = 0
        (fpar, xf, yf, names) = Fits.FitRegion(whichdata, whichaxis,
                                               self.Clamps.traces.xvals('Time'),
                                               self.Clamps.traces.view(np.ndarray),
                                               dataType='2d',
                                               t0=rgn[0], t1=rgn[1],
                                               fitFunc=Func,
                                               fitPars=initpars)
        if not fpar:
            raise Exception('IVCurve::update_Tauh: tau_h fitting failed - see log')
        bluepen = pg.mkPen('b', width=2.0, style=Qt.Qt.DashLine)
        if len(self.tauh_fits.keys()) > 0:
            [self.tauh_fits[k].clear() for k in self.tauh_fits.keys()]
        self.tauh_fits = {}
        self.tauh_fits[0] = self.data_plot.plot(xf[0]+rgn[0], yf[0], pen=bluepen)
#        self.tauh_fits.update()
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

        Parameters
        ----------
            None.
        
        Returns
        -------
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
        if self.Clamps.traces is None:
            return
        rgnss = self.regions['lrwin1']['region'].getRegion()
        r1 = rgnss[1]
        if rgnss[1] == rgnss[0]:
            print('Steady-state regions have no width; using 100 msec. window for ss ')
            r1 = rgnss[0] + 0.1
        self.ctrl.IVCurve_ssTStart.setValue(rgnss[0] * 1.0e3)
        self.ctrl.IVCurve_ssTStop.setValue(r1 * 1.0e3)
        data1 = self.Clamps.traces['Time': rgnss[0]:r1]
 #       print 'data shape: ', data1.shape
        if data1.shape[1] == 0 or data1.shape[0] == 1:
            return  # skip it
        self.ivss = []

        # check out whether there are spikes in the window that is selected
        threshold = self.ctrl.IVCurve_SpikeThreshold.value() * 1e-3
        ntr = len(self.Clamps.traces)
        if not self.spikes_counted:
            print('updatess: spikes not counted yet? ')
            self.analyzeSpikes()
            
        # spikecount = np.zeros(ntr)
        # for i in range(ntr):
        #     (spike, spk) = Utility.findspikes(self.Clamps.time_base, self.Clamps.traces[i],
        #                                       threshold,
        #                                       t0=rgnss[0], t1=r1,
        #                                       dt=self.Clamps.sample_interval,
        #                                       mode='schmitt',
        #                                       interpolate=False,
        #                                       debug=False)
        #     if len(spike) > 0:
        #         spikecount[i] = len(spike)
        # nospk = np.where(spikecount == 0)
        # print 'spikes checked'

        self.ivss = data1.mean(axis=1)  # all traces
        if self.ctrl.IVCurve_SubBaseline.isChecked():
            self.ivss = self.ivss - self.ivbaseline

        if len(self.nospk) >= 1:
            # Steady-state IV where there are no spikes
            self.ivss = self.ivss[self.nospk]
            self.ivss_cmd = self.Clamps.commandLevels[self.nospk]
#            self.commandLevels = commands[self.nospk]
            # compute Rin from the SS IV:
            # this makes the assumption that:
            # successive trials are in order (as are commands)
            # commands are not repeated...
            if len(self.ivss_cmd) > 0 and len(self.ivss) > 0:
                self.r_in = np.max(np.diff
                                   (self.ivss) / np.diff(self.ivss_cmd))
                self.ctrl.IVCurve_Rin.setText(u'%9.1f M\u03A9' % (self.r_in * 1.0e-6))
                self.analysis_summary['Rin'] = self.r_in*1.0e-6
            else:
                self.ctrl.IVCurve_Rin.setText(u'No valid points')
        self.yleak = np.zeros(len(self.ivss))
        if self.ctrl.IVCurve_subLeak.isChecked():
            if self.Clamps.data_mode in self.dataModel.ic_modes:
                sf = 1e-12
            elif self.Clamps.data_mode in self.dataModel.vc_modes:
                sf = 1e-3
            else:
                sf = 1.0
            (x, y) = Utility.clipdata(self.ivss, self.ivss_cmd,
                                      self.ctrl.IVCurve_LeakMin.value() * sf,
                                      self.ctrl.IVCurve_LeakMax.value() * sf)
            try:
                p = np.polyfit(x, y, 1)  # linear fit
                self.yleak = np.polyval(p, self.ivss_cmd)
                self.ivss = self.ivss - self.yleak
            except: 
                raise ValueError('IVCurve Leak subtraction: no valid points to correct')
        isort = np.argsort(self.ivss_cmd)
        self.ivss_cmd = self.ivss_cmd[isort]
        self.ivss = self.ivss[isort]
        self.analysis_summary['IV_Curve_ss'] = [self.ivss_cmd, self.ivss]
        self.update_IVPlot()

    def update_pkAnalysis(self, clear=False, pw=False):
        """
        Compute the peak IV (minimum) from the selected window
        mode can be 'min', 'max', or 'abs'

        Parameters
        ----------
        clear : Boolean, False
        pw : Boolean, False
            pw is passed to update_taumembrane to control printing.
        """
        if self.Clamps.traces is None:
            return
        mode = self.ctrl.IVCurve_PeakMode.currentText()
        rgnpk = self.regions['lrwin0']['region'].getRegion()
        self.ctrl.IVCurve_pkTStart.setValue(rgnpk[0] * 1.0e3)
        self.ctrl.IVCurve_pkTStop.setValue(rgnpk[1] * 1.0e3)
        data2 = self.Clamps.traces['Time': rgnpk[0]:rgnpk[1]]
        if data2.shape[1] == 0:
            return  # skip it - window missed the data
        # check out whether there are spikes in the window that is selected
        # but only in current clamp
        nospk = []
        peak_pos = None
        if self.Clamps.data_mode in self.dataModel.ic_modes:
            threshold = self.ctrl.IVCurve_SpikeThreshold.value() * 1e-3
            ntr = len(self.Clamps.traces)
            if not self.spikes_counted:
                print('update_pkAnalysis: spikes not counted')
                self.analyzeSpikes()
            spikecount = np.zeros(ntr)
            # for i in range(ntr):
            #     (spike, spk) = Utility.findspikes(self.Clamps.time_base, self.Clamps.traces[i],
            #                                       threshold,
            #                                       t0=rgnpk[0], t1=rgnpk[1],
            #                                       dt=self.Clamps.sample_interval,
            #                                       mode='schmitt',
            #                                       interpolate=False, debug=False)
            #     if len(spike) == 0:
            #         continue
            #     spikecount[i] = len(spike)
            # nospk = np.where(spikecount == 0)
            # nospk = np.array(nospk)[0]
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
        if len(self.nospk) >= 1:
            # Peak (min, max or absmax voltage) IV where there are no spikes
            self.ivpk = self.ivpk[self.nospk]
            self.ivpk_cmd = self.Clamps.commandLevels[self.nospk]
        else:
            self.ivpk_cmd = self.Clamps.commandLevels
        self.ivpk = self.ivpk.view(np.ndarray)
        if self.ctrl.IVCurve_subLeak.isChecked():
            self.ivpk = self.ivpk - self.yleak
        # now sort data in ascending command levels
        isort = np.argsort(self.ivpk_cmd)
        self.ivpk_cmd = self.ivpk_cmd[isort]
        self.ivpk = self.ivpk[isort]
        self.analysis_summary['IV_Curve_pk'] = [self.ivpk_cmd, self.ivpk]
        self.update_IVPlot()
        peak_time = self.Clamps.time_base[peak_pos]
        self.update_Tau_membrane(peak_time=peak_time, printWindow=pw)

    def update_rmpAnalysis(self, **kwargs):
        """
        Compute the RMP over time/commands from the selected window
        """
        if self.Clamps.traces is None:
            return
        rgnrmp = self.regions['lrrmp']['region'].getRegion()
        self.ctrl.IVCurve_rmpTStart.setValue(rgnrmp[0] * 1.0e3)
        self.ctrl.IVCurve_rmpTStop.setValue(rgnrmp[1] * 1.0e3)
        data1 = self.Clamps.traces['Time': rgnrmp[0]:rgnrmp[1]]
        data1 = data1.view(np.ndarray)
        self.ivbaseline = data1.mean(axis=1)  # all traces
        self.ivbaseline_cmd = self.Clamps.commandLevels
        self.rmp = np.mean(self.ivbaseline) * 1e3  # convert to mV
        self.ctrl.IVCurve_vrmp.setText('%8.2f' % self.rmp)
        self.update_RMPPlot()
        self.analysis_summary['RMP'] = self.rmp

    def make_map_symbols(self):
        """
        Given the current state of things, (keeping the analysis, when
        superimposing multiple results, for example),
        sets self.currentSymDict with a dict of pen, fill color, empty color, a symbol from
        our lists, and a clearflag. Used to overplot different data.
        """
        n = self.keep_analysis_count
        pen = next(self.color_list)
        filledbrush = pen
        emptybrush = None
        symbol = next(self.symbol_list)
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
        if self.Clamps.data_mode in self.dataModel.ic_modes:
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
        if self.Clamps.data_mode in self.dataModel.vc_modes:
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
            if self.Clamps.data_mode in self.dataModel.ic_modes:
                sf = 1e3
                self.RMP_plot.setLabel('left', 'V mV')
            else:
                sf = 1e12
                self.RMP_plot.setLabel('left', 'I (pA)')
            if mode == 0:
                self.RMP_plot.plot(self.Clamps.trace_StartTimes, sf * np.array(self.ivbaseline),
                                   symbol=symbol, pen=pen,
                                   symbolSize=6, symbolPen=pen,
                                   symbolBrush=filledbrush)
                self.RMP_plot.setLabel('bottom', 'T (s)')
            elif mode == 1:
                self.RMP_plot.plot(self.Clamps.commandLevels,
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
        if self.Clamps.data_mode in self.dataModel.vc_modes:
            self.fiPlot.clear()  # no plots of spikes in VC
            self.fslPlot.clear()
            return
        (pen, filledbrush, emptybrush, symbol, n, clearFlag) = self.map_symbol()
        mode = self.ctrl.IVCurve_RMPMode.currentIndex()  # get x axis mode
        self.spcmd = self.Clamps.commandLevels[self.spk]  # get command levels iwth spikes
        iscale = 1.0e12  # convert to pA
        yfslsc = 1.0  # convert to msec
        if mode == 0:  # plot with time as x axis
            xfi = self.Clamps.trace_StartTimes
            xfsl = self.Clamps.trace_StartTimes
            select = range(len(self.Clamps.trace_StartTimes))
            xlabel = 'T (s)'
        elif mode == 1:  # plot with current as x
            select = self.spk
            xfi = self.Clamps.commandLevels * iscale
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
        fslmax = 0.
        if self.showFISI:
            self.fslPlot.plot(x=xfsl, y=self.fsl[select] * yfslsc, clear=clearFlag,
                          symbolSize=6,
                          symbol=symbol, pen=pen,
                          symbolPen=pen, symbolBrush=filledbrush)
            self.fslPlot.plot(x=xfsl, y=self.fisi[select] * yfslsc, symbolSize=6,
                          symbol=symbol, pen=pen,
                          symbolPen=pen, symbolBrush=emptybrush)
            if len(xfsl) > 0:
                self.fslPlot.setXRange(0.0, np.max(xfsl))
                self.fslPlot.setYRange(0., max(max(self.fsl[select]), max(self.fisi[select])))
            ylabel = 'Fsl/Fisi (ms)'
            xfsllabel = xlabel
            self.fslPlot.setTitle('FSL/FISI')
        else:
            maxspk = 0
            maxisi = 0.
            clear = clearFlag
            for i, k in enumerate(self.allisi.keys()):
                nspk = len(self.allisi[k])
                xisi = np.arange(nspk)
                self.fslPlot.plot(x=xisi, y=self.allisi[k] * yfslsc, clear=clear,
                              symbolSize=6,
                              symbol=symbol, pen=pen,
                              symbolPen=pen, symbolBrush=filledbrush)
                clear = False
                maxspk = max(nspk, maxspk)
                maxisi = max(np.max(self.allisi[k]), maxisi)
            self.fslPlot.setXRange(0.0, maxspk)
            self.fslPlot.setYRange(0.0, maxisi)
            xfsllabel = 'Spike Number'
            ylabel = 'ISI (s)'
            self.fslPlot.setTitle('ISI vs. Spike Number')
        self.fiPlot.setLabel('bottom', xlabel)
        self.fslPlot.setLabel('bottom', xfsllabel)
        self.fslPlot.setLabel('left', ylabel)

    def printAnalysis(self, printnow=True, script_header=True, copytoclipboard=False):
        """
        Print the analysis summary information (Cell, protocol, etc)
        in a nice formatted version to the terminal.
        The output can be copied to another program (excel, prism) for further analysis
        Parameters
        ----------
        printnow : Boolean, optional
            Set true to print to terminal, default: True
        script_header : Boolean, optional
            Set to print the header line, default: True
        copytoclipboard : Boolean, optional
            copy the text to the system clipboard, default: False
        
        Return
        ------
        ltxt : string
            The text that would be printed. Might be useful to capture for other purposes
        """
        
        # Dictionary structure: key = information about 
        if self.Clamps.data_mode in self.dataModel.ic_modes or self.Clamps.data_mode == 'vc':
            data_template = self.data_template
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
        htxt = ''
        if script_header:
            htxt = '{:34s}\t{:15s}\t{:24s}\t'.format("Cell", "Genotype", "Protocol")
            for k in data_template.keys():
                cnv = '{:<%ds}' % (data_template[k][0])
                # print 'cnv: ', cnv
                htxt += (cnv + '\t').format(k)
            script_header = False
            htxt += '\n'

        ltxt = ''
        if 'Genotype' not in self.analysis_summary.keys():
            self.analysis_summary['Genotype'] = 'Unknown'
        ltxt += '{:34s}\t{:15s}\t{:24s}\t'.format(self.analysis_summary['CellID'], self.analysis_summary['Genotype'], self.analysis_summary['Protocol'])
          
        for a in data_template.keys():
            if a in self.analysis_summary.keys():
                txt = self.analysis_summary[a]
                if a in ['Description', 'Notes']:
                    txt = txt.replace('\n', ' ').replace('\r', '')  # remove line breaks from output, replace \n with space
                #print a, data_template[a]
                ltxt += (data_template[a][1]).format(txt) + ' \t'
            else:
                ltxt += ('{:>%ds}' % (data_template[a][0]) + '\t').format('NaN')
        ltxt = ltxt.replace('\n', ' ').replace('\r', '')  # remove line breaks
        ltxt = htxt + ltxt
        if printnow:
            print(ltxt)
        
        if copytoclipboard:
            clipb = Qt.QApplication.clipboard()
            clipb.clear(mode=clipb.Clipboard)
            clipb.setText(ltxt, mode=clipb.Clipboard)

        return ltxt
        
    def dbStoreClicked(self):
        """
        Store data into the current database for further analysis
        """
        #self.updateAnalysis()
        if self.loaded is None:
            return
        self.dbIdentity = 'IVCurve'  # type of data in the database
        db = self._host_.dm.currentDatabase()
        # print 'dir (db): ', dir(db)
        # print 'dir (db.db): ', dir(db.db)
        # print 'db.listTables: ', db.listTables()
        # print 'db.tables: ', db.tables
        #       
        table = self.dbIdentity

        columns = OrderedDict([
#            ('ProtocolDir', 'directory:Protocol'),
            ('AnalysisDate', 'text'),
            ('ProtocolSequenceDir', 'directory:ProtocolSequence'),
            ('Dir', 'text'),
            ('Protocol', 'text'),
            ('Genotype', 'text'),
            ('Celltype', 'text'),
            ('UseData', 'int'),
            ('RMP', 'real'),
            ('R_in', 'real'),
            ('tau_m', 'real'),
            ('iHold', 'real'),
            ('PulseDuration', 'real'),
            ('neg_cmd', 'real'),
            ('neg_pk', 'real'),
            ('neg_ss', 'real'),
            ('h_tau', 'real'),
            ('h_g', 'real'),
            ('SpikeThreshold', 'real'),
            ('AdaptRatio', 'real'),
            ('FiringRate', 'real'),
            ('AP1_HalfWidth', 'real'),
            ('AP1_Latency', 'real'),
            ('AP2_HalfWidth', 'real'),
            ('AP2_Latency', 'real'),
            ('AHP_Depth', 'real'),
            ('FI_Curve', 'text'),
            ('IV_Curve_pk', 'text'),
            ('IV_Curve_ss', 'text'),
        ])

        if table not in db.tables:
            db.createTable(table, columns, owner=self.dbIdentity)
        try:
            z = self.neg_cmd
        except:
            self.neg_cmd = 0.
            self.neg_pk = 0.
            self.neg_ss = 0.
            self.tau2 = 0.
            self.Gh = 0.

        if 'Genotype' not in self.analysis_summary:
            self.analysis_summary['Genotype'] = 'Unknown'
#        print 'genytope: ', self.analysis_summary['Genotype']
        if 'Celltype' not in self.Script.analysis_parameters:
            self.analysis_summary['Celltype'] = 'Unknown'
        
        data = {
            'AnalysisDate': time.strftime("%Y-%m-%d %H:%M:%S"),
            'ProtocolSequenceDir': self.loaded,
#            'ProtocolSequenceDir': self.dataModel.getParent(self.loaded, 'ProtocolSequence'),
            'Dir': self.loaded.parent().name(),
            'Protocol': self.loaded.name(),
            'Genotype': self.analysis_summary['Genotype'],
            'Celltype': self.Script.analysis_parameters['Celltype'],  # uses global info, not per cell info
            'UseData' : 1,
            'RMP': self.rmp / 1000.,
            'R_in': self.r_in,
            'tau_m': self.tau,
            'iHold': self.analysis_summary['iHold'],
            'PulseDuration': self.analysis_summary['pulseDuration'],
            'AdaptRatio': self.adapt_ratio,
            'neg_cmd': self.neg_cmd,
            'neg_pk': self.neg_pk,
            'neg_ss': self.neg_ss,
            'h_tau': self.analysis_summary['tauh'],
            'h_g': self.analysis_summary['Gh'],
            'SpikeThreshold': self.analysis_summary['SpikeThreshold'],
            'FiringRate': self.analysis_summary['FiringRate'],
            'AP1_HalfWidth': self.analysis_summary['AP1_HalfWidth'],
            'AP1_Latency': self.analysis_summary['AP1_Latency'],
            'AP2_HalfWidth': self.analysis_summary['AP2_HalfWidth'],
            'AP2_Latency': self.analysis_summary['AP2_Latency'],
            'AHP_Depth': self.analysis_summary['AHP_Depth'],
            'FI_Curve': repr(self.analysis_summary['FI_Curve'].tolist()), # convert array to string for storage
            'IV_Curve_pk': repr(np.array(self.analysis_summary['IV_Curve_pk']).tolist()),
            'IV_Curve_ss': repr(np.array(self.analysis_summary['IV_Curve_ss']).tolist()),
         }
        ## If only one record was given, make it into a list of one record
        if isinstance(data, dict):
            data = [data]
            ## Make sure target table exists and has correct columns, links to input file
        
        fields = db.describeData(data)
        ## override directory fields since describeData can't guess these for us
#        fields['ProtocolDir'] = 'directory:Protocol'
        fields['ProtocolSequenceDir'] = 'directory:ProtocolSequence'
        
        with db.transaction():
            db.checkTable(table, owner=self.dbIdentity, columns=fields, create=True, addUnknownColumns=True, indexes=[['ProtocolSequenceDir'],])
            
            dirtable = db.dirTableName(self.loaded)  # set up the DirTable Protocol Sequence directory.
            if not db.hasTable(dirtable):
                db.createDirTable(self.loaded)

            # delete old
            for source in set([d['ProtocolSequenceDir'] for d in data]):
                db.delete(table, where={'ProtocolSequenceDir': source})

            # write new
            with pg.ProgressDialog("Storing IV Results..", 0, 100) as dlg:
                for n, nmax in db.iterInsert(table, data, chunkSize=30):
                    dlg.setMaximum(nmax)
                    dlg.setValue(n)
                    if dlg.wasCanceled():
                        raise HelpfulException("Scan store canceled by user.", msgType='status')
        #db.close()
        #db.open()
        print("Updated record for ", self.loaded.name())

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

