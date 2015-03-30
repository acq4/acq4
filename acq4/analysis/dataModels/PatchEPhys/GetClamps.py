# -*- coding: utf-8 -*-
"""

This is part of Acq4

Paul B. Manis, Ph.D.
2011-2013.

Pep8 compliant (via pep8.py) 10/25/2013
Refactoring begun 3/21/2015

"""


import os
import os.path
import numpy as np
import re
from acq4.analysis.AnalysisModule import AnalysisModule
from acq4.util.metaarray import MetaArray


# noinspection PyPep8
class GetClamps(AnalysisModule):
    def __init__(self, host):
        AnalysisModule.__init__(self, host)

    def cell_summary(self, dh, summary=None):
        """
        cell_summary generates a dictionary of information about the cell
        for the selected directory handle (usually a protocol; could be a file)
        :param dh: the directory handle for the data, as passed to loadFileRequested
        :return nothing:
        """
        # other info into a dictionary
        if summary is None:
            summary = {}
        summary['Day'] = self.dataModel.getDayInfo(dh)
        summary['Slice'] = self.dataModel.getSliceInfo(dh)
        summary['Cell'] = self.dataModel.getCellInfo(dh)
        summary['ACSF'] = self.dataModel.getACSF(dh)
        summary['Internal'] = self.dataModel.getInternalSoln(dh)
        summary['Temperature'] = self.dataModel.getTemp(dh)
        summary['CellType'] = self.dataModel.getCellType(dh)
        today = summary['Day']

        if today is not None:
            if 'species' in today.keys():
                summary['Species'] = today['species']
            if 'age' in today.keys():
                summary['Age'] = today['age']
            if 'sex' in today.keys():
                summary['Sex'] = today['sex']
            if 'weight' in today.keys():
                summary['Weight'] = today['weight']
            if 'temperature' in today.keys():
                summary['Temperature'] = today['temperature']
            if 'description' in today.keys():
                summary['Description'] = today['description']
        else:
            for k in ['species', 'age', 'sex', 'weight', 'temperature', 'description']:
                summary[k] = None
        if summary['Cell'] is not None:
            ct = summary['Cell']['__timestamp__']
        else:
            ct = 0.
        pt = dh.info()['__timestamp__']
        summary['ElapsedTime'] = pt - ct  # save elapsed time between cell opening and protocol start
        (date, sliceid, cell, proto, p3) = self.dataModel.file_cell_protocol(dh.name())
        summary['CellID'] = os.path.join(date, sliceid, cell)  # use this as the ID for the cell later on
        summary['Protocol'] = proto
        return summary
        	
    def getClampData(self, dh, pars=None):
        """
        Read the clamp data - whether it is voltage or current clamp, and put the results
        into our class variables. 
        dh is the file handle (directory)
        pars is a structure that provides some control parameters usually set by the GUI
        Returns a short dictionary of some values; others are accessed through the class
        """   
        pars = self.getParsDefaults(pars)
        clampInfo = {}
        if dh is None:
            return clampInfo

        dirs = dh.subDirs()
        clampInfo['dirs'] = dirs
        traces = []
        cmd = []
        cmd_wave = []
        data = []
        self.time_base = None
        self.values = []
        self.trace_times = np.zeros(0)
        sequence_values = None
        self.sequence = self.dataModel.listSequenceParams(dh)
        # building command voltages - get amplitudes to clamp
        clamp = ('Clamp1', 'Pulse_amplitude')
        reps = ('protocol', 'repetitions')

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
            dirs = []
###
### This is possibly broken -
### 
###
            ld = pars['sequence1']['index']
            rd = pars['sequence2']['index']
            if ld[0] == -1 and rd[0] == -1:
                pass
            else:
                if ld[0] == -1:  # 'All'
                    ld = range(pars['sequence2']['count'])
                if rd[0] == -1:  # 'All'
                    rd = range(pars['sequence2']['count'])

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
                    print 'PatchEPhys/GetClamps: Missing data in %s, element: %d' % (directory_name, i)
                    continue
            except:
                raise Exception("Error loading data for protocol %s:"
                                % directory_name)
            data_file = data_file_handle.read()
            # only consider data in a particular range
            data = self.dataModel.getClampPrimary(data_file)
            self.data_mode  = self.dataModel.getClampMode(data_file, dir_handle=dh)
            if self.data_mode is None:
                self.data_mode = self.dataModel.ic_modes[0]  # set a default mode
            if self.data_mode in ['vc']:  # should be "AND something"  - this is temp fix for Xuying's old data
                self.data_mode = self.dataModel.vc_modes[0]
            if self.data_mode in ['model_ic', 'model_vc']:  # lower case means model was run
                self.modelmode = True
            # Assign scale factors for the different modes to display data rationally
            if self.data_mode in self.dataModel.ic_modes:
                self.command_scale_factor = 1e12
                self.command_units = 'pA'
            elif self.data_mode in self.dataModel.vc_modes:
                self.command_units = 'mV'
                self.command_scale_factor = 1e3
            else:  # data mode not known; plot as voltage
                self.command_units = 'V'
                self.command_scale_factor = 1.0
            if pars['limits']:
                cval = self.command_scale_factor * sequence_values[i]
                cmin = pars['cmin']
                cmax = pars['cmax']
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
            # print '1,0: ', info1[0]
            # print '1,1: ', info1[1].keys()
            # we need to handle all the various cases where the data is stored in different parts of the
            # "info" structure
            if 'startTime' in info1[0].keys():
                start_time = info1[0]['startTime']
            elif 'startTime' in info1[1].keys():
                start_time = info1[1]['startTime']
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
            print "PatchEPhys/GetClamps: No data found in this run..."
            return False
        self.r_uncomp = 0.
        if self.amp_settings['WCCompValid']:
            if self.amp_settings['WCEnabled'] and self.amp_settings['CompEnabled']:
                self.r_uncomp = self.amp_settings['WCResistance'] * (1.0 - self.amp_settings['CompCorrection'] / 100.)
            else:
                self.r_uncomp = 0.

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
#        sfreq = self.dataModel.getSampleRate(data_file_handle)
        self.sample_interval = 1. / self.dataModel.getSampleRate(data_file_handle)
        vc_command = data_dir_handle.parent().info()['devices'][self.clampDevices[0]]
        self.tstart = 0.01
        self.tdur = 0.5
        self.tend = 0.510
        # print 'vc_command: ', vc_command.keys()
        # print vc_command['waveGeneratorWidget'].keys()
        if 'waveGeneratorWidget' in vc_command.keys():
            # print 'wgwidget'
            try:
                vc_info = vc_command['waveGeneratorWidget']['stimuli']['Pulse']
                # print 'stimuli/Pulse'
                pulsestart = vc_info['start']['value']
                pulsedur = vc_info['length']['value']
            except KeyError:
                try:
                    vc_info = vc_command['waveGeneratorWidget']['function']
                    # print 'function'
                    pulse = vc_info[6:-1].split(',')
                    pulsestart = eval(pulse[0])
                    pulsedur = eval(pulse[1])
                except:
                    raise Exception('WaveGeneratorWidget not found')
                    pulsestart = 0.
                    pulsedur = np.max(self.time_base)
        elif 'daqState' in vc_command:
            # print 'daqstate'
            vc_state = vc_command['daqState']['channels']['command']['waveGeneratorWidget']
            func = vc_state['function']
            if func == '':  # fake values so we can at least look at the data
                pulsestart = 0.01
                pulsedur = 0.001
            else:  # regex parse the function string: pulse(100, 1000, amp)
                pulsereg = re.compile("(^pulse)\((\d*),\s*(\d*),\s*(\w*)\)")
                match = pulsereg.match(func)
                g = match.groups()
                if g is None:
                    raise Exception('PatchEPhys/GetClamps cannot parse waveGenerator function: %s' % func)
                pulsestart = float(g[1]) / 1000.  # values coming in are in ms, but need s
                pulsedur = float(g[2]) / 1000.
        else:
            raise Exception("PatchEPhys/GetClamps: cannot find pulse information")
        # adjusting pulse start/duration is necessary for early files, where the values
        # were stored as msec, rather than sec. 
        # we do this by checking the values against the time base itself, which is always in seconds.
        # if they are too big, we guess (usually correctly) that the values are in the wrong units
        if pulsestart + pulsedur > np.max(self.time_base):
            pulsestart *= 1e-3
            pulsedur *= 1e-3
        cmdtimes = np.array([pulsestart, pulsedur])
        if pars['KeepT'] is False:  # update times with current times.
            self.tstart = cmdtimes[0]  # cmd.xvals('Time')[cmdtimes[0]]
            self.tend = np.sum(cmdtimes)  # cmd.xvals('Time')[cmdtimes[1]] + self.tstart
            self.tdur = self.tend - self.tstart
            clampInfo['PulseWindow'] = [self.tstart, self.tend, self.tdur]
#        print 'start/end/dur: ', self.tstart, self.tend, self.tdur
        # build the list of command values that are used for the fitting
        clampInfo['cmdList'] = []
        for i in range(len(self.values)):
            clampInfo['cmdList'].append('%8.3f %s' %
                           (self.command_scale_factor * self.values[i], self.command_units))

        if self.data_mode in self.dataModel.vc_modes:
            self.spikecount = np.zeros(len(np.array(self.values)))
        return clampInfo

    def getParsDefaults(self, pars):
        """
        pars is a dictionary that defines the special cases for getClamps. 
        Here, given the pars dictionary that was passed to getClamps, we make sure that all needed
        elements are present, and substitute logical values for those that are missing"""
        
        if pars is None:
            pars = {}
        # neededKeys = ['limits', 'cmin', 'cmax', 'KeepT', 'sequence1', 'sequence2']
        # hmm. could do this as a dictionary of value: default pairs and a loop
        k = pars.keys()
        if 'limits' not in k:
            pars['limits'] = False 
        if 'cmin' not in k:
            pars['cmin'] = -np.inf 
            pars['cmax'] = np.inf
        if 'KeepT' not in k:
            pars['KeepT'] = False 
        # sequence selections:
        # pars[''sequence'] is a dictionary
        # The dictionary has  'index' (currentIndex()) and 'count' from the GUI
        if 'sequence1' not in k:
            pars['sequence1'] = {'index': 0}  # index of '0' is "All"
            pars['sequence1']['count'] = 0 
        if 'sequence2' not in k:
            pars['sequence2'] = {'index': 0} 
            pars['sequence2']['count'] = 0
        return pars
        

