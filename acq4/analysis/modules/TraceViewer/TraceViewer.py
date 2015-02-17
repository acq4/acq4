# -*- coding: utf-8 -*-
"""
TraceViewer: Analysis module to display data from protocols
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
# import acq4.analysis.tools.Utility as Utility  # pbm's utilities...
# import acq4.analysis.tools.Fitting as Fitting  # pbm's fitting stuff...
import ctrlTemplate


# noinspection PyPep8
class TraceViewer(AnalysisModule):
    """
    TraceViewer is an Analysis Module for Acq4.

    TraceViewer shows traces from a particular protocol, with the following options:
    -- show just the average of the traces
    -- Resting potential or holding current (average RMP through the episodes in the protocol).
    
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
        self.ctrl.TraceView_Update.clicked.connect(self.updateAnalysis)
        self.ctrl.TraceView_PrintResults.clicked.connect(self.printAnalysis)
        if not matplotlibexporter.HAVE_MPL:
            self.ctrl.TraceView_MPLExport.setEnabled = False  # make button inactive
        #        self.ctrl.TraceView_MPLExport.clicked.connect(self.matplotlibExport)
        else:
            self.ctrl.TraceView_MPLExport.clicked.connect(
                functools.partial(matplotlibexporter.matplotlibExport, gridlayout=self.gridLayout,
                                  title=self.filename))
        self.ctrl.TraceView_KeepAnalysis.clicked.connect(self.resetKeepAnalysis)
        self.ctrl.TraceView_getFileInfo.clicked.connect(self.get_file_information)
        [self.ctrl.TraceView_RMPMode.currentIndexChanged.connect(x)
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
        self.ar = []  # adaptation ratio
        self.rmp = []  # resting membrane potential during sequence
        self.analysis_summary = {}

    def resetKeepAnalysis(self):
        self.keep_analysis_count = 0  # reset counter.



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
        self.ctrl.TraceView_Sequence1.clear()
        self.ctrl.TraceView_Sequence2.clear()
        self.ctrl.TraceView_Sequence1.addItems(leftseq)
        self.ctrl.TraceView_Sequence2.addItems(rightseq)

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
        if self.analysis_summary['Cell'] is not None:
            ct = self.analysis_summary['Cell']['__timestamp__']
        else:
            ct = 0.
        pt = dh.info()['__timestamp__']
        self.analysis_summary['ElapsedTime'] = pt - ct  # save elapsed time between cell opening and protocol start
        (date, sliceid, cell, proto, p3) = self.file_cell_protocol()
        self.analysis_summary['CellID'] = os.path.join(date, sliceid, cell)  # use this as the ID for the cell later on

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
            raise Exception("TraceView::loadFileRequested: " +
                            "Select an IV protocol directory.")
        if len(dh) != 1:
            raise Exception("TraceView::loadFileRequested: " +
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
            ld = [self.ctrl.TraceView_Sequence1.currentIndex() - 1]
            rd = [self.ctrl.TraceView_Sequence2.currentIndex() - 1]
            if ld[0] == -1 and rd[0] == -1:
                pass
            else:
                if ld[0] == -1:  # 'All'
                    ld = range(self.ctrl.TraceView_Sequence1.count() - 1)
                if rd[0] == -1:  # 'All'
                    rd = range(self.ctrl.TraceView_Sequence2.count() - 1)
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
                    print 'TraceView.loadFileRequested: Missing data in %s, element: %d' % (directory_name, i)
                    # raise Exception('TraceView.loadFileRequested: Missing data in %s, element: %d' % (directory_name, i))
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
            self.ctrl.TraceView_dataMode.setText(self.data_mode)
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
            if self.ctrl.TraceView_IVLimits.isChecked():
                cval = self.command_scale_factor * sequence_values[i]
                cmin = self.ctrl.TraceView_IVLimitMin.value()
                cmax = self.ctrl.TraceView_IVLimitMax.value()
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
            print "TraceView::loadFileRequested: No data found in this run..."
            return False
        self.r_uncomp = 0.
        if self.amp_settings['WCCompValid']:
            if self.amp_settings['WCEnabled'] and self.amp_settings['CompEnabled']:
                self.r_uncomp = self.amp_settings['WCResistance'] * (1.0 - self.amp_settings['CompCorrection'] / 100.)
            else:
                self.r_uncomp = 0.
        # self.ctrl.TraceView_R_unCompensated.setValue(self.r_uncomp * 1e-6)  # convert to Mohm to display
        # self.ctrl.TraceView_R_unCompensated.setSuffix(u" M\u2126")
        # self.ctrl.TraceView_Holding.setText('%.1f mV' % (float(self.holding) * 1e3))

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
                raise Exception('loadFileRequested (TraceView) cannot parse waveGenerator function: %s' % func)
            pulsestart = float(g[1]) / 1000.  # values coming in are in ms, but need s
            pulsedur = float(g[2]) / 1000.
        else:
            raise Exception("loadFileRequested (TraceView): cannot find pulse information")
        cmdtimes = np.array([pulsestart, pulsedur])
        if self.ctrl.TraceView_KeepT.isChecked() is False:
            self.tstart = cmdtimes[0]  # cmd.xvals('Time')[cmdtimes[0]]
            self.tend = np.sum(cmdtimes)  # cmd.xvals('Time')[cmdtimes[1]] + self.tstart
            self.tdur = self.tend - self.tstart
        # if self.ctrl.TraceView_KeepT.isChecked() is False:
        #     self.tstart += self.sample_interval
        #     self.tend += self.sample_interval

        # build the list of command values that are used for the fitting
        cmdList = []
        for i in range(len(self.values)):
            cmdList.append('%8.3f %s' %
                           (self.command_scale_factor * self.values[i], self.command_units))
        self.ctrl.TraceView_tauh_Commands.clear()
        self.ctrl.TraceView_tauh_Commands.addItems(cmdList)
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
        if self.ctrl.TraceView_KeepAnalysis.isChecked():
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
        if self.ctrl.TraceView_KeepT.isChecked() is False:  # change regions; otherwise keep...
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
        data_template = (
            OrderedDict([('ElapsedTime', '{:>8.2f}'), ('Drugs', '{:<8s}'), ('HoldV', '{:>5.1f}'), ('JP', '{:>5.1f}'),
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
        if script_header:
            print('{:34s}\t{:24s}\t'.format("Cell", "Protocol")),
            for k in data_template.keys():
                print('{:<s}\t'.format(k)),
            print ''
        ltxt = ''
        ltxt += ('{:34s}\t{:24s}\t'.format(self.analysis_summary['CellID'], self.analysis_summary['Protocol']))

        for a in data_template.keys():
            if a in self.analysis_summary.keys():
                ltxt += ((data_template[a] + '\t').format(self.analysis_summary[a]))
            else:
                ltxt += '<   >\t'
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

    def update_rmpAnalysis(self, **kwargs):
        """
            Compute the RMP over time/commands from the selected window
        """
        if self.traces is None:
            return
        rgnrmp = self.regions['lrrmp']['region'].getRegion()
        self.ctrl.TraceView_rmpTStart.setValue(rgnrmp[0] * 1.0e3)
        self.ctrl.TraceView_rmpTStop.setValue(rgnrmp[1] * 1.0e3)
        data1 = self.traces['Time': rgnrmp[0]:rgnrmp[1]]
        data1 = data1.view(np.ndarray)
        self.ivbaseline = []
        commands = np.array(self.values)
        self.ivbaseline = data1.mean(axis=1)  # all traces
        self.ivbaseline_cmd = commands
        self.cmd = commands
        self.averageRMP = np.mean(self.ivbaseline) * 1e3  # convert to mV
        self.ctrl.TraceView_vrmp.setText('%8.2f' % self.averageRMP)

        self.update_RMPPlot()

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

    def update_RMPPlot(self):
        """
            Draw the RMP to the I-V window
            Note: x axis can be I, T, or  # spikes
        """
        if self.ctrl.TraceView_KeepAnalysis.isChecked() is False:
            self.RMP_plot.clear()
        if len(self.ivbaseline) > 0:
            (pen, filledbrush, emptybrush, symbol, n, clearFlag) = \
                self.map_symbol()
            mode = self.ctrl.TraceView_RMPMode.currentIndex()
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

    def dbStoreClicked(self):
        """
        Store data into the current database for further analysis
        """
        self.updateAnalysis()
        db = self._host_.dm.currentDatabase()
        table = 'DirTable_Cell'
        columns = OrderedDict([
            ('TraceView_rmp', 'real'),
            ('TraceView_rinp', 'real'),
            ('TraceView_taum', 'real'),
            ('TraceView_neg_cmd', 'real'),
            ('TraceView_neg_pk', 'real'),
            ('TraceView_neg_ss', 'real'),
            ('TraceView_h_tau', 'real'),
            ('TraceView_h_g', 'real'),
        ])

        rec = {
            'TraceView_rmp': self.neg_vrmp / 1000.,
            'TraceView_rinp': self.r_in,
            'TraceView_taum': self.tau,
            'TraceView_neg_cmd': self.neg_cmd,
            'TraceView_neg_pk': self.neg_pk,
            'TraceView_neg_ss': self.neg_ss,
            'TraceView_h_tau': self.tau2,
            'TraceView_h_g': self.Gh,
        }

        with db.transaction():
            # Add columns if needed
            if 'TraceView_rmp' not in db.tableSchema(table):
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

