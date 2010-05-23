# -*- coding: utf-8 -*-
from PyQt4 import QtGui, QtCore
from functions import siEval, siFormat
from math import log
from SignalProxy import proxyConnect

class SpinBox(QtGui.QAbstractSpinBox):
    """QSpinBox widget on steroids. Allows selection of numerical value, with extra features:
      - float values with linear, log, and decimal stepping (1-9,10-90,100-900,etc.)
      - Option for unbounded values
      - SI prefix notation
      - Sparse tables--list of acceptable values
      - Support for sequence variables (for ProtocolRunner)
    """
    
    def __init__(self, parent=None, value=0.0, **kwargs):
        QtGui.QAbstractSpinBox.__init__(self, parent)
        self.setMinimumWidth(0)
        self.setSizePolicy(QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Preferred)
        self.opts = {
            'bounds': [None, None],
            
            ## Log scaling options
            #'step': 0.1,
            #'minStep': 0.001,
            #'log': True,
            #'dec': False,
            
            ## decimal scaling option
            #'step': 0.1,
            #'minStep': -2,
            #'log': False,
            #'dec': True,
           
            ## arithmetic step
            'step': 0.01,
            'log': False,
            'dec': False,
            
            'suffix': '',
            'siPrefix': False,
            #'delay': False,
            'delayUntilEditFinished': True
        }
        self.val = value
        self.updateText()
        self.skipValidate = False
        self.setCorrectionMode(self.CorrectToPreviousValue)
        self.setOpts(**kwargs)
        
        QtCore.QObject.connect(self, QtCore.SIGNAL('editingFinished()'), self.editingFinished)
        self.proxy = proxyConnect(self, QtCore.SIGNAL('valueChanged(double)'), self.delayedChange)
        #QtCore.QObject.connect(self.lineEdit(), QtCore.SIGNAL('returnPressed()'), self.editingFinished)
        #QtCore.QObject.connect(self.lineEdit(), QtCore.SIGNAL('textChanged()'), self.textChanged)
        
    def delayedChange(self):
        #print "emit delayed change"
        self.emit(QtCore.SIGNAL('delayedChange'))
        
    def widgetGroupInterface(self):
        return ('delayedChange', SpinBox.value, SpinBox.setValue)
        
    def sizeHint(self):
        return QtCore.QSize(120, 0)
        
    ##lots of config options, just gonna stuff 'em all in here rather than do the get/set crap.
    def setOpts(self, **opts):
        for k in opts:
            self.opts[k] = opts[k]
        self.updateText()
    
    def stepEnabled(self):
        return self.StepUpEnabled | self.StepDownEnabled        
    
    #def fixup(self, *args):
        #print "fixup:", args
    
    def stepBy(self, n):
        s = [-1, 1][n >= 0]
        val = self.val
        for i in range(abs(n)):
            if self.opts['log']:
                step = abs(val) * self.opts['step']
                if 'minStep' in self.opts:
                    step = max(step, self.opts['minStep'])
                val += step * s
            elif self.opts['dec']:
                if val == 0:
                    exp = self.opts['minStep']
                else:
                    vs = [-1, 1][val >= 0]
                    exp = int(log(abs(val*(1.01**(s*vs)))) / log(10))
                    if 'minStep' in self.opts:
                        exp = max(exp, self.opts['minStep'])
                step = self.opts['step'] * 10**exp
                val += s * step
            else:
                val += s*self.opts['step']
                
            if 'minStep' in self.opts and abs(val) < self.opts['minStep']:
                val = 0.0
        self.setValue(val)
        
    def setValue(self, value, update=True):
        #print "setValue:", value
        #if value == 0.0:
            #import traceback
            #traceback.print_stack()
        bounds = self.opts['bounds']
        if bounds[0] is not None and value < bounds[0]:
            return
        if bounds[1] is not None and value > bounds[1]:
            return
            
        self.val = value
        if update:
            self.updateText()
        self.emit(QtCore.SIGNAL('valueChanged(double)'), self.val)
        self.lineEdit().setStyleSheet('border: 0px;')

    def setMaximum(self, m):
        self.opts['bounds'][1] = m
    
    def setMinimum(self, m):
        self.opts['bounds'][0] = m
        
    def setProperty(self, prop, val):
        """setProperty is just for compatibility with QSpinBox"""
        if prop == 'value':
            self.setValue(val)
        else:
            print "Warning: SpinBox.setProperty('%s', ..) not supported." % prop

    def value(self):
        return self.val

    def updateText(self):
        #print "Update text."
        self.skipValidate = True
        if self.opts['siPrefix']:
            self.lineEdit().setText(siFormat(self.val, suffix=self.opts['suffix']))
        else:
            self.lineEdit().setText('%g%s' % (self.val , self.opts['suffix']))
        self.skipValidate = False
        
    def validate(self, strn, pos):
        if self.skipValidate:
            return (QtGui.QValidator.Acceptable, pos)
        #print "Validate:", strn, pos
        try:
            val = self.interpret()
            if val is False:
                return (QtGui.QValidator.Invalid, pos)
                
            if not self.opts['delayUntilEditFinished']:
                self.setValue(val, update=False)
            #print "  OK:", self.val
            self.lineEdit().setStyleSheet('border: 0px;')
            
            return (QtGui.QValidator.Acceptable, pos)
        except:
            #print "  BAD"
            #import sys
            #sys.excepthook(*sys.exc_info())
            self.lineEdit().setStyleSheet('border: 2px solid #C55;')
            return (QtGui.QValidator.Intermediate, pos)
        
    def interpret(self):
        """Return value of text. Return False if text is invalid, raise exception if text is intermediate"""
        strn = self.lineEdit().text()
        suf = self.opts['suffix']
        if len(suf) > 0:
            if strn[-len(suf):] != suf:
                return False
            #raise Exception("Units are invalid.")
            strn = strn[:-len(suf)]
        val = siEval(strn)
        return val
        
    #def interpretText(self, strn=None):
        #print "Interpret:", strn
        #if strn is None:
            #strn = self.lineEdit().text()
        #self.setValue(siEval(strn), update=False)
        ##QtGui.QAbstractSpinBox.interpretText(self)
        
        
    def editingFinished(self):
        """Edit has finished; set value."""
        #print "Edit finished."
        try:
            val = self.interpret()
            if val is False:
                return
            self.setValue(val)  ## allow text update so that values are reformatted pretty-like
        except:
            pass
        
    #def textChanged(self):
        #print "Text changed."
        
    