# -*- coding: utf-8 -*-
from PyQt4 import QtGui, QtCore
from functions import siEval, siFormat
from math import log

class SpinBox(QtGui.QAbstractSpinBox):
    """QSpinBox widget on steroids. Allows selection of numerical value, with extra features:
      - float values with linear, log, and decimal stepping (1-9,10-90,100-900,etc.)
      - Option for unbounded values
      - SI prefix notation
      - Sparse tables--list of acceptable values
      - Support for sequence variables (for ProtocolRunner)
    """
    
    def __init__(self, *args):
        QtGui.QAbstractSpinBox.__init__(self)
        self.opts = {
            'bounds': [None, None],
            
            'step': 0.1,
            'minStep': 0.001,
            'log': True,
            'dec': False,
            
            #'step': 0.1,
            #'minStep': -2,
            #'log': False,
            #'dec': True,
           
            #'step': 0.01,
            #'log': False,
            #'dec': False,
            
            'suffix': 'V',
            'siPrefix': False,
            'delay': False
        }
        self.val = 0.0
        self.updateText()
        self.setCorrectionMode(self.CorrectToPreviousValue)
        
    ##lots of config options, just gonna stuff 'em all in here rather than do the get/set crap.
    def setOpts(self, **opts):
        pass
    
    def stepEnabled(self):
        return self.StepUpEnabled | self.StepDownEnabled        
    
    def fixup(self, *args):
        print "fixup:", args
    
    def stepBy(self, n):
        s = [-1, 1][n >= 0]
        for i in range(abs(n)):
            if self.opts['log']:
                step = abs(self.val) * self.opts['step']
                step = max(step, self.opts['minStep'])
                self.val += step * s
            elif self.opts['dec']:
                if self.val == 0:
                    exp = self.opts['minStep']
                else:
                    vs = [-1, 1][self.val >= 0]
                    exp = int(log(abs(self.val*(1.01**(s*vs)))) / log(10))
                    exp = max(exp, self.opts['minStep'])
                step = self.opts['step'] * 10 ** exp
                self.val += s * step
                if abs(self.val) < self.opts['minStep']:
                    self.val = 0.0
            else:
                self.val = self.val + s*self.opts['step']
        self.updateText()
        #print "Step:", n
        
    def updateText(self):
        self.lineEdit().setText(siFormat(self.val, suffix=self.opts['suffix']))
        
    def validate(self, strn, pos):
        #print "Validate:", strn, pos
        try:
            self.interpretText(strn)
            #print "  OK:", self.val
            return (QtGui.QValidator.Acceptable, pos)
        except:
            #print "  BAD"
            return (QtGui.QValidator.Intermediate, pos)
        
    def interpretText(self, strn=None):
        if strn is None:
            strn = self.lineEdit().text()
        self.val = siEval(strn)
        QtGui.QAbstractSpinBox.interpretText(self)
        
        
        