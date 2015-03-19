__author__ = 'pbmanis'
"""
dataSummary: This script reads all of the data files in a given directory, and prints out top level information
including notes, protocols run (and whether or not they are complete), and image files associated with a cell.
Currently, this routine makes assumptions about the layout as a hierarchical structure [days, slices, cells, protocols]
and does not print out information if there are no successful protocols run.
June, 2014, Paul B. Manis.

"""
from collections import OrderedDict
import sys
from acq4.util.metaarray import MetaArray
from acq4.analysis.dataModels import PatchEPhys
from acq4.util import DataManager
import numpy as np
import os
import re
import os.path
import textwrap
import gc




class DataSummary():
    def __init__(self, basedir=None, daylistfile=None):
        print 'basedir: ', basedir
        self.monitor = False
        self.analysis_summary = {}
        self.dataModel = PatchEPhys
        self.basedir = basedir
        self.InvestigateProtocols = False  # set True to check out the protocols in detail
        self.tw = {}  # for notes
        self.tw['day'] = textwrap.TextWrapper(initial_indent="Notes: ", subsequent_indent=" "*4)
        self.tw['slice'] = textwrap.TextWrapper(initial_indent="Notes: ", subsequent_indent=" "*4)
        self.tw['cell'] = textwrap.TextWrapper(initial_indent="Notes: ", subsequent_indent=" "*4)

        self.twd = {}  # for description
        self.twd['day'] = textwrap.TextWrapper(initial_indent="Description: ", subsequent_indent=" "*4)
        self.twd['slice'] = textwrap.TextWrapper(initial_indent="Description: ", subsequent_indent=" "*4)
        self.twd['cell'] = textwrap.TextWrapper(initial_indent="Description: ", subsequent_indent=" "*4)
        
        self.img_re = re.compile('^[Ii]mage_(\d{3,3}).tif')  # make case insensitive - for some reason in Xuying's data
        self.s2p_re = re.compile('^2pStack_(\d{3,3}).ma')
        self.i2p_re = re.compile('^2pImage_(\d{3,3}).ma')
        self.video_re = re.compile('^[Vv]ideo_(\d{3,3}).ma')

        self.reportIncompleteProtocols = False  # do include incomplete protocol runs in print
        allfiles = os.listdir(basedir)
        # look for names that match the acq4 "day" template:
        # example: 2013.03.28_000
        daytype = re.compile("(\d{4,4}).(\d{2,2}).(\d{2,2})_(\d{3,3})")
#        daytype = re.compile("(2011).(06).(08)_(\d{3,3})")  # specify a day
        #2011.10.17_000
        # operate in two modes:
        # second, between two dates
        daylist = None
        if daylistfile is None:
            minday = (2010, 1, 1)
            minday = minday[0]*1e4+minday[1]*1e2+minday[2]
            maxday = (2013, 1, 1)
            maxday = maxday[0]*1e4+maxday[1]*1e2+maxday[2]
        else:
            daylist = []
            with open(daylistfile, 'r') as f:
                for line in f:
                    if line[0] != '#':
                        daylist.append(line[0:10])
            f.close()
        print daylistfile
        print daylist
        
        days = []
        for thisfile in allfiles:
            m = daytype.match(thisfile)
            if m == '.DS_Store':
                continue
            if m is None:
               # print 'Top level file %s is incorrectly placed ' % thisfile
                continue  # no match
            if len(m.groups()) >= 3:  # perfect match
                # print m.groups()
                idl = [int(d) for d in m.groups()]
                id = idl[0]*1e4+idl[1]*1e2+idl[2]
                # print 'id: ', id
                # print 'minday: ', minday
                if daylist is None:
                    if id >= minday and id <= maxday:
                        days.append(thisfile)  # was [0:10]
                else:
                    #print 'using daylist, thisfile: ', thisfile[0:10]
                    #print 'daylist: ', daylist
                    if thisfile[0:10] in daylist:
                        days.append(thisfile)
        print 'Days reported: ', days
        for day in days:
            if self.monitor:
                print 'processing day: %s' % day
            self.daystring = '%s \t' % (day)
            dh = DataManager.getDirHandle(os.path.join(self.basedir, day), create=False)
            dx = self.dataModel.getDayInfo(dh)
            if dx is not None and 'description' in dx.keys() and len(dx['description']) > 0:
                l = self.twd['day'].wrap(dx['description'])
                for i in l:
                    i = i.replace('\t', '    ')  # clean out tabs so printed formatting is not confused
                    self.daystring += i
            else:
                self.daystring += ' [no description]'
            self.daystring += ' \t'
            if dx is not None and 'notes' in dx.keys() and len(dx['notes']) > 0:
                l = self.tw['day'].wrap(dx['notes'])
                for i in l:
                    i = i.replace('\t', '    ')  # clean out tabs so printed formatting is not confused
                    self.daystring += i
            else:
                self.daystring += ' [no notes]'
            self.daystring += ' \t'
            self.doSlices(os.path.join(self.basedir, day))
            os.closerange(8, 65535)  # close all files in each iteration
            gc.collect()

    def doSlices(self, day):
        """
        process all of the slices for a given day
        :param day:
        :return nothing:
        """

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
            self.slicestring = '%s \t' % (slice)
            dh = DataManager.getDirHandle(os.path.join(day, slice), create=False)
            sl = self.dataModel.getSliceInfo(dh)

            # if sl is not None and 'description' in sl.keys() and len(sl['description']) > 0:
            #     l = self.twd['slice'].wrap(sl['description'])
            #     for i in l:
            #         self.slicestring += i
            # else:
            #     self.slicestring += ' No slice description'
            # self.slicestring += '\t'

            if sl is not None and 'notes' in sl.keys() and len(sl['notes']) > 0:
                l = self.tw['slice'].wrap(sl['notes'])
                for i in l:
                    i = i.replace('\t', '    ')  # clean out tabs so printed formatting is not confused
                    self.slicestring += i
            else:
                self.slicestring += ' No slice notes'
            self.slicestring += ' \t'
            self.doCells(os.path.join(day, slice))
            DataManager.cleanup()
            del dh
            gc.collect()

    def doCells(self, slice):
        """
        process all of the cells from a slice
        :param slice:
        :return nothing:
        """
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
            cl = self.dataModel.getCellInfo(dh)
            if cl is not None and 'notes' in cl.keys() and len(cl['notes']) > 0:
                l = self.tw['cell'].wrap(cl['notes'])
                for i in l:
                    i = i.replace('\t', '    ')  # clean out tabs so printed formatting is not confused
                    self.cellstring += i
            else:
                self.cellstring += ' No cell notes'
            self.cellstring += ' \t'
            self.cell_summary(dh)
            
            # if cl is not None and 'description' in cl.keys() and len(cl['description']) > 0:
            #     l = self.twd['cell'].wrap(cl['description'])
            #     for i in l:
            #         self.cellstring += i
            # else:
            #     self.cellstring += ' No cell description'

            self.cellstring += ' \t'
            self.doProtocols(os.path.join(slice, cell))
            DataManager.cleanup() # clean up after each cell
            del dh
            gc.collect()

#        if len(cells) == 0:
#            print '      No cells in this slice'

    def doProtocols(self, cell):
        """
        process all of the protocols for a given cell
        :param cell:
        :return nothing:
        """
        allfiles = os.listdir(cell)
        #celltype = re.compile("(Cell_)(\d{3,3})")
        protocols = []
        nonprotocols = []
        anyprotocols = False
        images = []  # tiff
        stacks2p = []
        images2p = []
        videos = []
        endmatch = re.compile("[\_(\d{3,3})]$")  # look for _lmn at end of directory name
        for thisfile in allfiles:
            if os.path.isdir(os.path.join(cell, thisfile)):
                protocols.append(thisfile)
            else:
                nonprotocols.append(thisfile)

        self.protocolstring = ''
        if self.InvestigateProtocols is True:
            self.summarystring = 'NaN \t'*6
            for np, protocol in enumerate(protocols):
                dh = DataManager.getDirHandle(os.path.join(cell, protocol), create=False)
                if np == 0:
                    self.cell_summary(dh)
                if self.monitor:
                    print 'Investigating Protocol: %s', dh.name()
                dirs = dh.subDirs()
                protocolok = True  # assume that protocol is ok
                modes = []
                nexpected = len(dirs)  # acq4 writes dirs before, so this is the expected fill
                ncomplete = 0  # count number actually done
                clampDevices = self.dataModel.getClampDeviceNames(dh)
                # must handle multiple data formats, even in one experiment...
                if clampDevices is not None:
                    data_mode = dh.info()['devices'][clampDevices[0]]['mode']  # get mode from top of protocol information
                else:  # try to set a data mode indirectly
                    if 'devices' not in dh.info().keys():
                        protocolok = False  # can't parse protocol device...
                        continue
                    devices = dh.info()['devices'].keys()  # try to get clamp devices from another location
                    #print dir(self.dataModel)
                    for kc in self.dataModel.knownClampNames():
                        if kc in devices:
                            clampDevices = [kc]
                    try:
                        data_mode = dh.info()['devices'][clampDevices[0]]['mode']
                    except:
                        data_mode = 'Unknown'
                        # protocolok = False
                        # print '<<cannot read protocol data mode>>'
                if data_mode not in modes:
                    modes.append(data_mode)
                for i, directory_name in enumerate(dirs):  # dirs has the names of the runs within the protocol
                    data_dir_handle = dh[directory_name]  # get the directory within the protocol
                    try:
                        data_file_handle = self.dataModel.getClampFile(data_dir_handle)  # get pointer to clamp data
                    except:
                        data_file_handle = None
                    if data_file_handle is not None:  # no clamp file found - skip
                        ncomplete += 1
                        # Check if there is no clamp file for this iteration of the protocol
                        # Usually this indicates that the protocol was stopped early.
                        # data_file = data_file_handle.read()
                        try:
                            self.holding = self.dataModel.getClampHoldingLevel(data_file_handle)
                        except:
                            self.holding = 0.
                        try:
                            self.amp_settings = self.dataModel.getWCCompSettings(data_file_handle)
                        except:
                            self.amp_settings = None
                            #raise ValueError('complete = %d when failed' % ncomplete)
                    #else:
                    #    break  # do not keep looking if the file is not found
                    DataManager.cleanup()  # close all opened files
                    # del dh
                    gc.collect()  # and force garbage collection of freed objects inside the loop
                if modes == []:
                    modes = ['Unknown mode']
                if protocolok and ncomplete == nexpected:  # accumulate protocols
                    self.protocolstring += '[{:<s}: {:s} {:d}], '.format(protocol, modes[0][0], ncomplete)
                    anyprotocols = True  # indicate that ANY protocol ran to completion
                else:
                    if self.reportIncompleteProtocols:
                        self.protocolstring += '[{:<s}, ({:s}, {:d}/{:d}, Incomplete)], '.format(protocol, modes[0][0], ncomplete, nexpected)

                DataManager.cleanup()
                del dh
                gc.collect()
        else:
            self.protocolstring += 'Protocols: '
            anyprotocols = True
            prots = {}
            for protocol in protocols:
                m = endmatch.search(protocol)
                if m is not None:
                    p = protocol[:-4]
                else:
                    p = protocol
                if p not in prots.keys():
                    prots[p] = 1
                else:
                    prots[p] += 1
            if len(prots.keys()) > 0:
                self.protocolstring += '['
                for p in prots.keys():
                    self.protocolstring += '{:<s}({:<d}), '.format(p, prots[p])
                self.protocolstring += ']'
            else:
                self.protocolstring = '<No protocols found>'
        self.protocolstring += ' \t'

        for thisfile in nonprotocols:
#            if os.path.isdir(os.path.join(cell, thisfile)):  # skip protocols
#                continue
            x = self.img_re.match(thisfile)  # look for image files
            if x is not None:
                images.append(thisfile)
            x = self.s2p_re.match(thisfile)  # two photon stacks
            if x is not None:
                stacks2p.append(thisfile)
            x = self.i2p_re.match(thisfile)  # simple two photon images
            if x is not None:
                images2p.append(thisfile)
            x = self.video_re.match(thisfile)  # video images
            if x is not None:
                videos.append(thisfile)
        self.imagestring = ''
        if len(images) > 0:
            self.imagestring += 'Images: %d ' % len(images)
        if len(stacks2p) > 0:
            self.imagestring += '2pStacks: %d ' % len(stacks2p)
        if len(images2p) > 0:
            self.imagestring += '2pImages: %d ' % len(images2p)
        if len(videos) > 0:
            self.imagestring += 'Videos: %d' % len(videos)
        if len(images) + len(stacks2p) + len(images2p) + len(videos) == 0:
            self.imagestring = 'No Images or Videos'
        
        if anyprotocols:
            print self.daystring + self.summarystring + self.slicestring + self.cellstring + self.protocolstring + self.imagestring + ' \t'
        else:
            print self.daystring + self.summarystring + self.slicestring + self.cellstring + '<No complete protocols> \t' + self.imagestring + ' \t'


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
        builds a formatted string with some of the information.
        :param dh: the directory handle for the data, as passed to loadFileRequested
        :return nothing:
        """
        self.analysis_summary = {}  # always clear the summary.
        self.summarystring = ''
        # other info into a dictionary
        self.analysis_summary['Day'] = self.dataModel.getDayInfo(dh)
        self.analysis_summary['Slice'] = self.dataModel.getSliceInfo(dh)
        self.analysis_summary['Cell'] = self.dataModel.getCellInfo(dh)
        self.analysis_summary['ACSF'] = self.dataModel.getACSF(dh)
        self.analysis_summary['Internal'] = self.dataModel.getInternalSoln(dh)
        self.analysis_summary['Temp'] = self.dataModel.getTemp(dh)
        self.analysis_summary['CellType'] = self.dataModel.getCellType(dh)
        today = self.analysis_summary['Day']
        if today is not None:
            #print today.keys()
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
            if 'description' in today.keys():
                self.analysis_summary['Description'] = today['description']
            if 'notes' in today.keys():
                self.analysis_summary['Notes'] = today['notes']
        
        if self.analysis_summary['Cell'] is not None:
            ct = self.analysis_summary['Cell']['__timestamp__']
        else:
            ct = 0.
        try:
            pt = dh.info()['__timestamp__']
        except:
            pt = 0.
        self.analysis_summary['ElapsedTime'] = pt-ct  # save elapsed time between cell opening and protocol start
        (date, sliceid, cell, proto, p3) = self.file_cell_protocol(dh.name())
        self.analysis_summary['CellID'] = os.path.join(date, sliceid, cell)  # use this as the "ID" for the cell later on
        data_template = (
            OrderedDict([('Species', '{:>s}'), ('Age', '{:>5s}'), ('Sex', '{:>1s}'), ('Weight', '{:>5s}'),
                         ('Temperature', '{:>5s}'), ('ElapsedTime', '{:>8.2f}')]))
 
        ltxt = ''
        for a in data_template.keys():
            if a in self.analysis_summary.keys():
                ltxt += ((data_template[a] + ' \t').format(self.analysis_summary[a]))
            else:
                ltxt += (('NaN \t'))
        self.summarystring = ltxt

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
            raise Exception("DataSummary::loadFileRequested: " +
                            "Select an IV protocol directory.")
        if len(dh) != 1:
            raise Exception("DataSummary::loadFileRequested: " +
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
            data_file.close()
            del data_file
            
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
        dh.close()
        del dh
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
    if len(sys.argv) == 2:
        DataSummary(basedir=sys.argv[1])
    if len(sys.argv) == 3:
        DataSummary(basedir=sys.argv[1], daylistfile=sys.argv[2])
