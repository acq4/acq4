# -*- coding: utf-8 -*-
from PyQt4 import QtCore

class Module(QtCore.QObject):
    def __init__(self, manager, name, config):
        QtCore.QObject.__init__(self)
        self.name = name
        self.manager = manager
        self.config = config
        manager.declareInterface(name, ['module'], self)

    ## deprecated. Use interfaces instead.
    #def hasInterface(self, interface):
        #"""Return True if this module implements the named interface.
            #Examples: 'DataSource', 'Canvas'"""
        #return False
    
    def window(self):
        """Return the Qt window for this module"""
        if hasattr(self, 'win'):
            return self.win
        return None
    
    def quit(self):
        """Must be called after modules exit."""
        #print "inform quit", self.name
        self.manager.moduleHasQuit(self)
        
    
    