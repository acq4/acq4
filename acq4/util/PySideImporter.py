# -*- coding: utf-8 -*-
from __future__ import print_function

"""This module installs an import hook which overrides PyQt4 imports to pull from 
PySide instead. Used for transitioning between the two libraries."""

import imp

class PyQtImporter:
    def find_module(self, name, path):
        if name == 'PyQt4' and path is None:
            print("PyQt4 -> PySide")
            self.modData = imp.find_module('PySide')
            return self
        return None
        
    def load_module(self, name):
        return imp.load_module(name, *self.modData)
        
import sys
sys.meta_path.append(PyQtImporter())