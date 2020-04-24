# -*- coding: utf-8 -*-
from __future__ import print_function
import re
from .FileType import FileType

class MultiPatchLog(FileType):
    """File type written by MultiPatch module.
    """
    extensions = ['.log']   ## list of extensions handled by this class
    dataTypes = []    ## list of python types handled by this class
    priority = 0      ## priority for this class when multiple classes support the same file types
    
    @classmethod
    def read(cls, fileHandle):
        """Read a file, return a data object"""
        from ..modules.MultiPatch.logfile import MultiPatchLog
        return MultiPatchLog(fileHandle.name())
        
    @classmethod
    def acceptsFile(cls, fileHandle):
        """Return priority value if the file can be read by this class.
        Otherwise return False.
        The default implementation just checks for the correct name extensions."""
        name = fileHandle.shortName()
        if name.startswith('MultiPatch_') and name.endswith('.log'):
            return cls.priority
        return False
