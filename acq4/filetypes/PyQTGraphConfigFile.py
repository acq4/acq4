import os

from acq4.filetypes.FileType import FileType
from pyqtgraph.configfile import readConfigFile, writeConfigFile


class PyQTGraphConfigFile(FileType):
    @classmethod
    def write(cls, data, dirHandle, fileName, **args):
        writeConfigFile(data, os.path.join(dirHandle.name(), fileName))
        return fileName

    @classmethod
    def read(cls, fileHandle):
        return readConfigFile(fileHandle.name())

    extensions = [".cfg", "log.txt"]  # definitely abusing this
    dataTypes = [dict, list, tuple]
    priority = 50
