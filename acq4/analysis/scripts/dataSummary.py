__author__ = 'pbmanis'

import sys
from acq4.util.metaarray import MetaArray
from acq4.analysis.dataModels import PatchEPhys
from acq4.util import DataManager
import numpy as np
import os
import re
import os.path
import textwrap


class DataSummary():
    def __init__(self, basedir=None):
        print 'basedir: ', basedir
        self.analysis_summary = {}
        self.dataModel = PatchEPhys
        self.basedir = basedir
        self.tw = {}
        self.tw['day'] = textwrap.TextWrapper(initial_indent="Notes: ", subsequent_indent=" "*4)
        self.tw['slice'] = textwrap.TextWrapper(initial_indent="Notes: ", subsequent_indent=" "*4)
        self.tw['cell'] = textwrap.TextWrapper(initial_indent="Notes: ", subsequent_indent=" "*4)
        allfiles = os.listdir(basedir)
        # look for names that match the acq4 "day" template:
        # example: 2013.03.28_000
        daytype = re.compile("(\d{4,4}).(\d{2,2}).(\d{2,2})_(\d{3,3})")
#        daytype = re.compile("(2011).(06).(08)_(\d{3,3})")  # specify a day
        minday = (2012, 3, 8)
        maxday = (2014, 1, 1)
        days = []
        for thisfile in allfiles:
            m = daytype.match(thisfile)
            if m is None:
                continue  # no match
            if len(m.groups()) == 4:  # perfect match
                print m.groups()
                id = [int(d) for d in m.groups()]
                print id
                print minday
                if id[0] >= minday[0] and id[1] >= minday[1] and id[2] >= minday[2]:
                    if id[0] < maxday[0] and id[1] < maxday[1] and id[2] < maxday[2]:
                        days.append(thisfile)
        for day in days:
            #print 'processing day: %s' % day
            self.daystring = '%s\t' % (day)
            dh = DataManager.getDirHandle(os.path.join(self.basedir, day), create=False)
            dx = self.dataModel.getDayInfo(dh)
            if 'notes' in dx.keys() and len(dx['notes']) > 0:
                l = self.tw['day'].wrap(dx['notes'])
                for i in l:
                    self.daystring += i
            else:
                self.daystring += ' [no notes]'
            self.daystring += '\t'
            self.doSlices(os.path.join(self.basedir, day))

    def doSlices(self, day):
        allfiles = os.listdir(day)
        slicetype = re.compile("(slice\_)(\d{3,3})")
        slices = []
        for thisfile in allfiles:
            m = slicetype.match(thisfile)
            if m is None:
                continue
            if len(m.groups()) == 2:
                slices.append(thisfile)
        for slice in slices:
            self.slicestring = '%s\t' % (slice)
            dh = DataManager.getDirHandle(os.path.join(day, slice), create=False)
            sl = self.dataModel.getSliceInfo(dh)
            if 'notes' in sl.keys() and len(sl['notes']) > 0:
                l = self.tw['slice'].wrap(sl['notes'])
                for i in l:
                    self.slicestring += i
            else:
                self.slicestring += ' No slice notes'
            self.slicestring += '\t'
            self.doCells(os.path.join(day, slice))

    def doCells(self, slice):
        allfiles = os.listdir(slice)
        celltype = re.compile("(cell_)(\d{3,3})")
        cells = []
        for thisfile in allfiles:
            m = celltype.match(thisfile)
            if m is None:
                continue
            if len(m.groups()) == 2:
                cells.append(thisfile)
        for cell in cells:
            self.cellstring = '%s\t' % (cell)
            dh = DataManager.getDirHandle(os.path.join(slice, cell), create=False)
            cl = self.dataModel.getSliceInfo(dh)
            if 'notes' in cl.keys() and len(cl['notes']) > 0:
                l = self.tw['cell'].wrap(cl['notes'])
                for i in l:
                    self.cellstring += i
            else:
                self.cellstring += ' No cell notes'
            self.cellstring += '\t'
            self.doProtocols(os.path.join(slice, cell))

#        if len(cells) == 0:
#            print '      No cells in this slice'

    def doProtocols(self, cell):
        allfiles = os.listdir(cell)
        #celltype = re.compile("(Cell_)(\d{3,3})")
        protocols = []
        images = []  # tiff
        stacks2p = []
        images2p = []
        img = re.compile('(.tif)')
        s2p = re.compile('(2pStack)')
        i2p = re.compile('(2pImage)')
        for thisfile in allfiles:
            if os.path.isdir(os.path.join(cell, thisfile)):
                protocols.append(thisfile)
#        if len(protocols) == 0:
#            pass
            #print '         No protocols this cell entry'
        ngoodprotocols = 0
        self.protocolstring = ''
        for protocol in protocols:
            dh = DataManager.getDirHandle(os.path.join(cell, protocol), create=False)
            self.cell_summary(dh)
            dirs = dh.subDirs()
            modes = []
            complete = False
            ncomplete = 0
            ntotal = 0
            clampDevices = self.dataModel.getClampDeviceNames(dh)
            # must handle multiple data formats, even in one experiment...
            protocolok = True
            if clampDevices is not None:
                data_mode = dh.info()['devices'][clampDevices[0]]['mode']  # get mode from top of protocol information
            else:
                if 'devices' not in dh.info().keys():
                    protocolok = False
                    ntotal = -1
                    continue
                devices = dh.info()['devices'].keys()  # try to get clamp devices from another location
                for kc in self.dataModel.knownClamps():
                    if kc in devices:
                        clampDevices = [kc]
                try:
                    data_mode = dh.info()['devices'][clampDevices[0]]['mode']
                except:
                    # protocolok = False
                    # print '<<cannot read protocol data mode>>'
                    continue
            if data_mode not in modes:
                modes.append(data_mode)
            for i, directory_name in enumerate(dirs):  # dirs has the names of the runs within the protocol
                data_dir_handle = dh[directory_name]  # get the directory within the protocol
                ntotal += 1
                try:
                    data_file_handle = self.dataModel.getClampFile(data_dir_handle)  # get pointer to clamp data
                    # Check if there is no clamp file for this iteration of the protocol
                    # Usually this indicates that the protocol was stopped early.
                    data_file = data_file_handle.read()
                    self.holding = self.dataModel.getClampHoldingLevel(data_file_handle)
                    self.amp_settings = self.dataModel.getWCCompSettings(data_file)

                    if data_file_handle is not None:
                        ncomplete += 1
                except:
                    pass
            if ncomplete == ntotal:
                complete = True
            if modes == []:
                modes = ['uUknown mode']
            if complete and protocolok:  # accumulate protocols
                self.protocolstring += '{:<s} ({:s}, {:d}), '.format(protocol, modes[0][0], ncomplete)
                ngoodprotocols += 1
#                print ' mode: %s  complete, %d traces' % (modes[0], ncomplete)
#            else:
#                if len(modes) > 0:
#                    print ' mode: %s  Incomplete (%d of %d)' % (modes[0], ncomplete, ntotal)
#                else:
#                    print 'No data in protocol'
#        if len(protocols) == 0:
#            print '         No protocols this cell'
        self.protocolstring += '\t'

        for thisfile in allfiles:
            if os.path.isdir(os.path.join(cell, thisfile)):
                continue
            x = img.match(thisfile)
            if x is not None:
                images.append(thisfile)
            x = s2p.match(thisfile)
            if x is not None:
                stacks2p.append(thisfile)
            x = i2p.match(thisfile)
            if x is not None:
                images2p.append(thisfile)
        self.imagestring = ''
        if len(images) > 0:
            self.imagestring += 'Images: %d' % len(images)
        if len(stacks2p) > 0:
            self.imagestring += '2pStacks: %d' % len(stacks2p)
        if len(images2p) > 0:
            self.imagestring += '2pImages: %d' % len(images2p)
        if ngoodprotocols > 0 or len(self.imagestring) > 0:
            print self.daystring + self.slicestring + self.cellstring + self.protocolstring + self.imagestring + '\t'


    def get_file_information(self, dh=None):
        """
        get_file_information reads the sequence information from the
        currently selected data file

        Two-dimensional sequences are supported.
        :return nothing:
        """
        self.sequence = self.dataModel.listSequenceParams(dh)
        keys = self.sequence.keys()
        leftseq = [str(x) for x in self.sequence[keys[0]]]
        if len(keys) > 1:
            rightseq = [str(x) for x in self.sequence[keys[1]]]
        else:
            rightseq = []
        leftseq.insert(0, 'All')
        rightseq.insert(0, 'All')

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
        self.analysis_summary['ElapsedTime'] = pt-ct  # save elapsed time between cell opening and protocol start
        (date, sliceid, cell, proto, p3) = self.file_cell_protocol(dh.name())
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
            raise Exception("IVCurve::loadFileRequested: " +
                            "Select an IV protocol directory.")
        if len(dh) != 1:
            raise Exception("IVCURVE::loadFileRequested: " +
                            "Can only load one file at a time.")
#        if self.current_dirhandle != dh[0]:  # is this the current file/directory?
        self.get_file_information(default_dh=dh)  # No, get info from most recent file requested
        self.current_dirhandle = dh[0]  # this is critical!
        dh = dh[0]  # just get the first one
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
        sequence_values = []
        # builidng command voltages - get amplitudes to clamp
        clamp = ('Clamp1', 'Pulse_amplitude')
        reps = ('protocol', 'repetitions')

        # the sequence was retrieved from the data file by get_file_information
        if clamp in self.sequence:
            self.clampValues = self.sequence[clamp]
            self.nclamp = len(self.clampValues)
            if sequence_values is not None:
                sequence_values = [x for x in self.clampValues for y in sequence_values]
            else:
                sequence_values = [x for x in range(self.clampValues)]
        else:
            sequence_values = []
            nclamp = 0

        # if sequence has repeats, build pattern
        if reps in self.sequence:
            self.repc = self.sequence[reps]
            self.nrepc = len(self.repc)
            sequence_values = [x for y in range(self.nrepc) for x in sequence_values]

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
                continue  # If something goes wrong here, we just carry on
            data_file = data_file_handle.read()
            # only consider data in a particular range
            data = self.dataModel.getClampPrimary(data_file)
            self.data_mode = self.dataModel.getClampMode(data)
            if self.data_mode is None:
                self.data_mode = self.ic_modes[0]  # set a default mode
            if self.data_mode in ['model_ic', 'model_vc']:  # lower case means model was run
                self.modelmode = True
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

            self.devicesUsed = self.dataModel.getDevices(data_dir_handle)
            self.clampDevices = self.dataModel.getClampDeviceNames(data_dir_handle)
            self.holding = self.dataModel.getClampHoldingLevel(data_file_handle)
            self.amp_settings = self.dataModel.getWCCompSettings(data_file)
            self.clamp_state = self.dataModel.getClampState(data_file)
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
        sfreq = self.dataModel.getSampleRate(data)
        self.sample_interval = 1./sfreq
        vc_command = data_dir_handle.parent().info()['devices'][self.clampDevices[0]]
        if 'waveGeneratorWidget' in vc_command:
            vc_info = vc_command['waveGeneratorWidget']['stimuli']['Pulse']
            pulsestart = vc_info['start']['value']
            pulsedur = vc_info['length']['value']
        elif 'daqState' in vc_command:
            vc_state = vc_command['daqState']['channels']['command']['waveGeneratorWidget']
            func = vc_state['function']
            # regex parse the function string: pulse(100, 1000, amp)
            pulsereg = re.compile("(^pulse)\((\d*),\s*(\d*),\s*(\w*)\)")
            match = pulsereg.match(func)
            g = match.groups()
            if g is None:
                raise Exception('loadFileRequested (IVCurve) cannot parse waveGenerator function: %s' % func)
            pulsestart = float(g[1])/1000. # values coming in are in ms, but need s
            pulsedur = float(g[2])/1000.
        else:
            raise Exception("loadFileRequested (IVCurve): cannot find pulse information")
        cmdtimes = np.array([pulsestart, pulsedur])

        # build the list of command values that are used for the fitting
        cmdList = []
        for i in range(len(self.values)):
            cmdList.append('%8.3f %s' %
                           (self.command_scale_factor * self.values[i], self.command_units))
        return True

    def file_cell_protocol(self, filename):
        """
        file_cell_protocol breaks the current filename down and returns a
        tuple: (date, cell, protocol)
        last argument returned is the rest of the path...
        """
        (p0, proto) = os.path.split(filename)
        (p1, cell) = os.path.split(p0)
        (p2, sliceid) = os.path.split(p1)
        (p3, date) = os.path.split(p2)
        return (date, sliceid, cell, proto, p3)


if __name__ == "__main__":
    DataSummary(basedir=sys.argv[1])