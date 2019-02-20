# -*- coding: utf-8 -*-
from .FileType import FileType
#from ..modules.MultiPatch.logfile import IrregularTimeSeries
from ..devices.TwoPhotonPhotostimulator.StimulationPoint import StimulationPoint
import json

class PhotostimulationLog(FileType):
    """Filetype written by the PrairiePhotostimulator module."""

    extensions = ['.log']   ## list of extensions handled by this class
    dataTypes = []    ## list of python types handled by this class
    priority = 0      ## priority for this class when multiple classes support the same file types

    @classmethod
    def read(cls, fileHandle):
        """Read a file, return a data object"""
        #from ..modules.MultiPatch.logfile import MultiPatchLog
        return PhotostimLog(fileHandle.name())
        
    @classmethod
    def acceptsFile(cls, fileHandle):
        """Return priority value if the file can be read by this class.
        Otherwise return False.
        The default implementation just checks for the correct name extensions."""
        name = fileHandle.shortName()
        if (name.startswith('PhotoStimulationLog_') or name.startswith('PrairieStimulation')) and name.endswith('.log'):
            return cls.priority
        return False

class PhotostimLog(object):

    def __init__(self, filename=None):
        self._points = {}
        
        if filename is not None:
            self.read(filename)

    def read(self, filename):

        with open(filename, 'rb') as f:
            line = f.readline()
            vline = json.loads(line.rstrip(',\r\n'))
            version = vline.get('version', None)
            if version == None:
                f.seek(0)


            for line in f.readlines():


                stim = json.loads(line.rstrip(',\r\n'))

                i = stim.keys()[0]

                if version == None:
                    ptid = stim[i]['stimulationPoint']
                else:
                    ptid = stim[i]['stimulationPoint']['id']

                if version == 2:
                    pos = stim[i]['stimPointPos']
                else:
                    pos = stim[i]['pos']

                if ptid not in self._points.keys():
                    self._points[ptid] = StimulationPoint('Point', ptid, pos[:-1], pos[-1])

                self._points[ptid].addStimulation(stim[i], ptid)

                self._points[ptid].updatePosition(pos)

        #raise Exception("Stop here!")

    def listPoints(self):
        return self._points.values()


