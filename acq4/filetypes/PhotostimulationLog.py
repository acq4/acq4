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
        if name.startswith('PhotoStimulationLog_') and name.endswith('.log'):
            return cls.priority
        return False

class PhotostimLog(object):

    def __init__(self, filename=None):
        self._points = {}
        
        if filename is not None:
            self.read(filename)

    def read(self, filename):

        for line in open(filename, 'rb').readlines():

            stim = json.loads(line.rstrip(',\r\n'))
            id = stim.keys()[0]

            pt = stim[id]['stimulationPoint']

            if pt not in self._points.keys():
                self._points[pt] = StimulationPoint('Point', pt, stim[id]['pos'][:-1], stim[id]['pos'][-1])

            self._points[pt].addStimulation(stim[id], id)
            self._points[pt].updatePosition(stim[id]['pos'])

        #raise Exception("Stop here!")

    def listPoints(self):
        return self._points.values()


