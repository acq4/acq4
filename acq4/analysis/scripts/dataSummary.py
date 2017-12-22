from __future__ import print_function
__author__ = 'pbmanis'
"""
dataSummary: This script reads all of the data files in a given directory, and prints out top level information
including notes, protocols run (and whether or not they are complete), and image files associated with a cell.
Currently, this routine makes assumptions about the layout as a hierarchical structure [days, slices, cells, protocols]
and does not print out information if there are no successful protocols run.
June, 2014, Paul B. Manis.

Mar 2015:
added argparse to expand command line options rather than editing file. 
The following options are recognized:
begin (b) (define start date; end is set to current date) default: 1/1/1970
end (e)(define end date: start date set to 1/1/1970; end is set to the end date) default: "today"
mode =  full (f) : do a full investigation of the data files. Makes processing very slow. (reports incomplete protocols)
        partial (p) : do a partial investiagion of protocols: is there anything in every protocol directory? (reports incomplete protocols) - slow
        quick (q) : do a quick scan : does not run through protocols to find incomplete protocols. Default (over full and partial)
debug (d) : debug monitoring of progress
output (o) : define output file (tab delimited file for import to other programs)

Future:
    Provide interface
"""
import sys
import os
import re
import os.path

import gc

import argparse
import datetime
import numpy as np
import textwrap
from collections import OrderedDict

from acq4.util.metaarray import MetaArray
from acq4.analysis.dataModels import PatchEPhys
from acq4.util import DataManager




class DataSummary():
    def __init__(self, basedir=None, daylistfile=None):
        self.monitor = False
        self.analysis_summary = {}
        self.dataModel = PatchEPhys
        self.basedir = basedir
        # column definitions - may need to adjust if change data that is pasted into the output
        self.coldefs = 'Date \tDescription \tNotes \tGenotype \tAge \tSex \tWeight \tTemp \tElapsed T \tSlice \tSlice Notes \t'
        self.coldefs += 'Cell \t Cell Notes \t \tProtocols \tImages \t'

        self.outputMode = 'terminal' # 'tabfile'
        outputDir = os.path.join(os.path.expanduser("~"), 'Desktop/acq4_scripts')
        if self.outputMode == 'tabfile':
            self.outFilename = basedir.replace('/', '_') + '.tab'
            self.outFilename = self.outFilename.replace('\\', '_')
            if self.outFilename[0] == '_':
                self.outFilename = self.outFilename[1:]
            self.outFilename = os.path.join(outputDir, self.outFilename)
            print('Writing to: {:<s}'.format(self.outFilename))
            h = open(self.outFilename, 'w')  # write new file
            h.write(basedir+'\n')
            h.write(self.coldefs + '\n')
            h.close()
        else:
            print('Base Directory: ', basedir)
            print(self.coldefs)
            
        self.InvestigateProtocols = False  # set True to check out the protocols in detail
        self.tw = {}  # for notes
        self.tw['day'] = textwrap.TextWrapper(initial_indent="", subsequent_indent=" "*2)  # used to say "initial_indent ="Description: ""
        self.tw['slice'] = textwrap.TextWrapper(initial_indent="", subsequent_indent=" "*2)
        self.tw['cell'] = textwrap.TextWrapper(initial_indent="", subsequent_indent=" "*2)

        self.twd = {}  # for description
        self.twd['day'] = textwrap.TextWrapper(initial_indent="", subsequent_indent=" "*2)  # used to ays initial_indent ="Notes: ""
        self.twd['slice'] = textwrap.TextWrapper(initial_indent="", subsequent_indent=" "*2)
        self.twd['cell'] = textwrap.TextWrapper(initial_indent="", subsequent_indent=" "*2)
        
        self.img_re = re.compile('^[Ii]mage_(\d{3,3}).tif')  # make case insensitive - for some reason in Xuying's data
        self.s2p_re = re.compile('^2pStack_(\d{3,3}).ma')
        self.i2p_re = re.compile('^2pImage_(\d{3,3}).ma')
        self.video_re = re.compile('^[Vv]ideo_(\d{3,3}).ma')

        self.reportIncompleteProtocols = False  # do include incomplete protocol runs in print
        
        # look for names that match the acq4 "day" template:
        # example: 2013.03.28_000
        self.daytype = re.compile("(\d{4,4}).(\d{2,2}).(\d{2,2})_(\d{3,3})")
#        daytype = re.compile("(2011).(06).(08)_(\d{3,3})")  # specify a day
        #2011.10.17_000
        # operate in two modes:
        # second, between two dates
        self.daylist = None
        self.daylistfile = daylistfile
        if daylistfile is None:
            mindayx = (1970, 1, 1)
            #mindayx = (20, 6, 12)
            self.minday = mindayx[0]*1e4+mindayx[1]*1e2+mindayx[2]
            #maxdayx = datetime.datetime.now().timetuple()[0:3]  # get today
            maxdayx = (2015, 1, 1)
            self.maxday = maxdayx[0]*1e4+maxdayx[1]*1e2+maxdayx[2]
        else:
            self.daylist = []
            with open(self.daylistfile, 'r') as f:
                for line in f:
                    if line[0] != '#':
                        self.daylist.append(line[0:10])
            f.close()
#        print self.daylistfile
#        print self.daylist

    def setMonitor(self):
        pass
    
    def setBaseDir(self):
        pass
    
    def setBegin(self):
        """
        begin (b) (define start date; end is set to current date) default: 1/1/1970
        """
        pass
    
    def setEnd(self):
        """
        end (e)(define end date: start date set to 1/1/1970; end is set to the end date) default: "today"
        """
        pass
    
    def setModeFull(self):
        """
        mode =  full (f) : do a full investigation of the data files. Makes processing very slow. (reports incomplete protocols)
        """
        pass
    
    def setModePartial(self):
        """
        partial (p) : do a partial investiagion of protocols: is there anything in every protocol directory? (reports incomplete protocols) - slow
        """
        pass
    
    def setModeQuick(self):
        """
        quick (q) : do a quick scan : does not run through protocols to find incomplete protocols. Default (over full and partial)
        """
        pass
    
    def setDebug(self):
        """
        debug (d) : debug monitoring of progress
        """
        pass
        
    def setOutput(self):
        """
        output (o) : define output file (tab delimited file for import to other programs)
        """
        pass
        
    def getSummary(self):
        """
        getSummary is the entry point for scanning through all the data files in a given directory,
        returning information about those within the date range, with details as specified by the options
        """
        allfiles = os.listdir(self.basedir)
        
        days = []
        for thisfile in allfiles:
            m = self.daytype.match(thisfile)
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
                if self.daylist is None:
                    if id >= self.minday and id <= self.maxday:
                        days.append(thisfile)  # was [0:10]
                else:
                    #print 'using daylist, thisfile: ', thisfile[0:10]
                    #print 'daylist: ', daylist
                    if thisfile[0:10] in self.daylist:
                        days.append(thisfile)
        if self.monitor:
            print('Days reported: ', days)
        for day in days:
            if self.monitor:
                print('processing day: %s' % day)
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
                    print('Investigating Protocol: %s', dh.name())
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
                    devices = list(dh.info()['devices'].keys())  # try to get clamp devices from another location
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
            ostring =  self.daystring + self.summarystring + self.slicestring + self.cellstring + self.protocolstring + self.imagestring + ' \t'
        else:
            ostring = self.daystring + self.summarystring + self.slicestring + self.cellstring + '<No complete protocols> \t' + self.imagestring + ' \t'
        self.outputString(ostring)

    def outputString(self, ostring):
        if self.outputMode == 'terminal':
            print(ostring)
        else:
            h = open(self.outFilename, 'a')  # append mode
            h.write(ostring + '\n')
            h.close()
        
    def get_file_information(self, dh=None):
        """
        get_file_information reads the sequence information from the
        currently selected data file

        Two-dimensional sequences are supported.
        :return nothing:
        """
        self.sequence = self.dataModel.listSequenceParams(dh)
        keys = list(self.sequence.keys())
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
        ds = DataSummary(basedir=sys.argv[1])
    if len(sys.argv) == 3:
        ds = DataSummary(basedir=sys.argv[1], daylistfile=sys.argv[2])
    ds.getSummary()