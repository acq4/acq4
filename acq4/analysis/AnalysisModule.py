# -*- coding: utf-8 -*-
from __future__ import print_function

import six

from acq4.util import Qt
import acq4.pyqtgraph as pg
import acq4.util.FileLoader as FileLoader
import acq4.util.DatabaseGui as DatabaseGui
import acq4.util.Canvas as Canvas
#import acq4.pyqtgraph.widgets.DataTreeWidget as DataTreeWidget
from collections import OrderedDict

class AnalysisModule(Qt.QObject):
    """
    Generic class for analysis modules. 
    The general purpose of a module is to perform a specific analysis task in any context
    A module may be used for any/all of:
        1. Read data as it is acquired and immediately display analysis
        2. Read data offline from disk and display analysis
        3. Read data (acquired or offline) and output analysis results that could
            - feed into another analysis module
            - be written to disk
            
    Modules have the following interface components:
        - processData()
            Perform the analysis task, display the results, and return the results
            Optionally, display can be disabled.
        - listElements()
            returns a dict describing gui widgets required to operate the module. 
            Some widgets will be created by the module (such as control panels)
            Other widgets may be provided externally, so the module can display results to existing widgets
            Widgets may be optional
        - getElement()
        - setElement()
        
    Notes:
        - Data may be fed in to the module piecewise or in a single chunk, thus we need a way to indicate that we have finished/started a chunk
        - Some modules will want to act like a filter (1-in : 1-out), while others will act as an aggregator (N-in : 1-out)
        - Aggregators may choose to accept multiple data types for input
        - Modules may store configuration information in DB
        - When loading data, we need to know:
            - Is this raw data or previously analyzed results?
                If this is raw data:
                    - Has this already been analyzed?
                    - Can we re-display the analysis results immediately?
                If this is an analysis result:
                    - Can we go backward from results to raw data 
                        - and if we do, are we allowed to re-analyze again?
                    - Is this data a mixture of previous results?
        - element requirements may change at runtime (for example, the user may request an extra plot)
    """
    
    def __init__(self, host):
        """Subclasses should define self._elements_ to take advantage of default methods. 
        self._elements_ is a dict of (name: element) pairs, but can be initially defined
        as (name: (args..)) pairs, and the element objects will be created automatically."""
        Qt.QObject.__init__(self)
        self._host_ = host
        self.dataModel = host.dataModel
        self._sizeHint = (800, 600)

    def initializeElements(self):
        """Must be called sometime during the construction of the module.
        Note: This function simply parses all of the element descriptions. 
              It does NOT create the actual element widgets; this happens 
              when getElement(..., create=True) is called.
        """
        for name, el in self._elements_.items():
            if isinstance(el, tuple):
                self._elements_[name] = Element(name, args=el)
            elif isinstance(el, dict):
                self._elements_[name] = Element(name, args=el)
            elif isinstance(el, six.string_types):
                self._elements_[name] = Element(name, type=el)
            self._elements_[name].sigObjectChanged.connect(self.elementChanged)
            
    def quit(self):
        """
        Called by AnalysisHost when window is closed.
        Default quit function calls close() on all elements.
        Module may return False to indicate that it is not ready to quit.
        """
        for el in self._elements_.values():
            if hasattr(el, 'close'):
                el.close()
        #self.logBtn.close()
        return True
    
    
    def processData(self, data):
        pass
    
    def listElements(self):
        """Return a dict of (name: element) pairs for all elements used by the module"""
        return self._elements_
    
    def getElement(self, name, create=False):
        """Return the named element's object. """
        el = self.elementSpec(name)
        if el.hasObject():
            return el.object()
        elif create:
            return self.createElement(name)
        else:
            return None
            #raise Exception("Element %s has no object yet." % name)

    def getAllElements(self):
        """Return a dict of all objects referenced by elements."""
        el = OrderedDict()
        for name in self.listElements():
            el[name] = self.getElement(name)
        return el
        

    def createElement(self, name):
        """Instruct the module to create its own element.
        The default implementation can create some of the more common elements used
          (plot, canvas, ...)"""
        spec = self.elementSpec(name)
        obj = spec.makeObject(self._host_)
        self.setElement(name, obj)
        return obj

    def setElement(self, name, obj):
        spec = self.elementSpec(name)
        spec.setObject(obj)
        
    def elementChanged(self, element, old, new):
        """Override this function to handle changes to elements."""
        pass

    def elementSpec(self, name):
        """Return the specification for the named element"""
        return self._elements_[name]

    def dataManager(self):
        return self._host_.dataManager()

    def sizeHint(self):
        return self._sizeHint

class Element(Qt.QObject):
    """Simple class for holding options and attributes for elements"""
    sigObjectChanged = Qt.Signal(object, object, object)  ## Element, old obj, new obj
    
    def __init__(self, name, type=None, args=None):
        Qt.QObject.__init__(self)
        self.params = {
            'type': type,         ## string such as 'plot', 'canvas', 'ctrl'
            'name': name,
            'optional': False,    ## bool
            'object': None,       ## any object; usually the widget associated with the element
            'pos': None,
            'size': (None, None),
            'args': {}            ## arguments to be passed to the element's object when it is created
        }
        self.setParams(**args)
        
    def __getattr__(self, attr):
        if attr in self.params:
            return lambda: self.params[attr]
        raise AttributeError(attr)
        
    def setParams(self, **args):
        for k in args:
            if k == 'args':
                self.params['args'].update(args[k])
            elif k in self.params:
                self.params[k] = args[k]
            else:
                self.params['args'][k] = args[k]
        return self
        
    def setObject(self, obj):
        old = self.params['object']
        self.params['object'] = obj
        self.sigObjectChanged.emit(self, old, obj)
        
    def hasObject(self):
        return self.params['object'] is not None
        
    def makeObject(self, host):
        
        typ = self.type()
        args = self.args()
        if typ == 'plot':
            obj = pg.PlotWidget(name=self.name(), **args)
        elif typ == 'imageView':
            obj = pg.ImageView(**args)
        elif typ == 'canvas':
            obj = Canvas.Canvas(**args)
        elif typ == 'fileInput':
            obj = FileLoader.FileLoader(host.dataManager(), **args)
        #elif typ == 'database':
            #obj = DatabaseGui.DatabaseGui(host.dataManager(), **args)
        elif typ == 'table':
            obj = pg.TableWidget(**args)
        elif typ == 'dataTree':
            obj = pg.DataTreeWidget(**args)
        elif typ == 'parameterTree':
            obj = pg.parametertree.ParameterTree(**args)
        elif typ == 'graphicsView':
            obj = pg.GraphicsView(**args)
        elif typ == 'graphicsLayout':
            obj = pg.GraphicsLayoutWidget(**args)
        elif typ == 'viewBox':
            obj = pg.GraphicsView()
            obj.setCentralItem(pg.ViewBox(**args))
        else:
            raise Exception("Cannot automatically create element '%s' (type=%s)" % (self.name, typ))
        #self.setObject(obj)  ## handled indirectly..
        return obj
