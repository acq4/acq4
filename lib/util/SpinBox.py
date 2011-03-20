# -*- coding: utf-8 -*-
from PyQt4 import QtGui, QtCore
if not hasattr(QtCore, 'Signal'):
    QtCore.Signal = QtCore.pyqtSignal

from functions import siEval, siFormat
from math import log
from SignalProxy import proxyConnect
from decimal import Decimal as D  ## Use decimal to avoid accumulating floating-point errors
from decimal import *
import sip, weakref

class SpinBox(QtGui.QAbstractSpinBox):
    """QSpinBox widget on steroids. Allows selection of numerical value, with extra features:
      - float values with linear and decimal stepping (1-9,10-90,100-900,etc.)
      - Option for unbounded values
      - SI prefix notation
      - delayed signals (allows multiple rapid changes with only one change signal)
      - Sparse tables--list of acceptable values
      - Support for sequence variables (for ProtocolRunner)
      
    """
    
    ## There's a PyQt bug that leaks a reference to the 
    ## QLineEdit returned from QAbstractSpinBox.lineEdit()
    ## This makes it possible to crash the entire program 
    ## by making accesses to the LineEdit after the spinBox has been deleted.
    
    ## As a workaround, all SpinBoxes are disabled and stored permanently 
    ## after the call to __del__
    dead_spins = []
    
    valueChanged = QtCore.Signal(object)     # (value)  for compatibility with QSpinBox
    sigValueChanged = QtCore.Signal(object)  # (self)
    sigValueChanging = QtCore.Signal(object)  # (value)
    
    def __init__(self, parent=None, value=0.0, **kwargs):
        QtGui.QAbstractSpinBox.__init__(self, parent)
        self.lastValEmitted = None
        self.setMinimumWidth(0)
        self.setSizePolicy(QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Preferred)
        self.opts = {
            'bounds': [None, None],
            
            ## Log scaling options   #### Log mode is no longer supported.
            #'step': 0.1,
            #'minStep': 0.001,
            #'log': True,
            #'dec': False,
            
            ## decimal scaling option
            #'step': 0.1,    ## 
            #'minStep': -2,
            #'log': False,
            #'dec': True,
           
            ## normal arithmetic step
            'step': D('0.01'),
            'log': False,
            'dec': False,
            
            'suffix': '',
            'siPrefix': False,   ## Set to True to display numbers with SI prefix (ie, 100pA instead of 1e-10A)
            
            'delayUntilEditFinished': True   ## do not send signals until text editing has finished
        }
        
        self.decOpts = ['step', 'minStep']
        
        self.val = D(str(value))  ## Value is precise decimal. Ordinary math not allowed.
        self.updateText()
        self.skipValidate = False
        self.setCorrectionMode(self.CorrectToPreviousValue)
        self.setKeyboardTracking(False)
        self.setOpts(**kwargs)
        
        #QtCore.QObject.connect(self, QtCore.SIGNAL('editingFinished()'), self.editingFinished)
        self.editingFinished.connect(self.editingFinishedEvent)
        #self.proxy = proxyConnect(self, QtCore.SIGNAL('valueChanging'), self.delayedChange)
        self.proxy = proxyConnect(None, self.sigValueChanging, self.delayedChange)
        
        #QtCore.QObject.connect(self.lineEdit(), QtCore.SIGNAL('returnPressed()'), self.editingFinished)
        #QtCore.QObject.connect(self.lineEdit(), QtCore.SIGNAL('textChanged()'), self.textChanged)
        
        self.lineEditCache = weakref.ref(self.lineEdit())  ## Need this so se can work around a pyqt bug in __del__
        
        
    ## Note: can't rely on __del__ since it may not be called for a long time
    def __del__(self):
        #print "deleted"
        #QtCore.QObject.disconnect(self.proxy, QtCore.SIGNAL('valueChanged(double)'), self.delayedChange)
        #QtCore.QObject.disconnect(self, QtCore.SIGNAL('editingFinished()'), self.editingFinished)
        #del self.proxy
        #del self.opts
        #del self.decOpts
        #del self.val
        
        lec = self.lineEditCache()
        if lec is not None:
            sip.setdeleted(lec)  ## PyQt should handle this, but does not. Potentially leads to crashes.
        #del self.lineEditCache
        
    def emitChanged(self):
        self.lastValEmitted = self.val
        #self.emit(QtCore.SIGNAL('valueChanged(double)'), float(self.val))
        #self.emit(QtCore.SIGNAL('valueChanged'), self)
        self.valueChanged.emit(float(self.val))
        self.sigValueChanged.emit(self)
        
    def delayedChange(self):
        #print "delayedChange", self
        #print "emit delayed change"
        try:
            #self.emit(QtCore.SIGNAL('delayedChange'), self.value())
            if self.val != self.lastValEmitted:
                self.emitChanged()
        except RuntimeError:
            pass  ## This can happen if we try to handle a delayed signal after someone else has already deleted the underlying C++ object.
        
    def widgetGroupInterface(self):
        return (self.valueChanged, SpinBox.value, SpinBox.setValue)
        
    def sizeHint(self):
        return QtCore.QSize(120, 0)
        
    ##lots of config options, just gonna stuff 'em all in here rather than do the get/set crap.
    def setOpts(self, **opts):
        for k in opts:
            if k == 'bounds':
                #print opts[k]
                for i in [0,1]:
                    if opts[k][i] is None:
                        self.opts[k][i] = None
                    else:
                        self.opts[k][i] = D(str(opts[k][i]))
            elif k in ['step', 'minStep']:
                self.opts[k] = D(str(opts[k]))
            elif k == 'value':
                pass   ## don't set value until bounds have been set
            else:
                self.opts[k] = opts[k]
        if 'value' in opts:
            self.setValue(opts['value'])
        self.updateText()
    
    def stepEnabled(self):
        return self.StepUpEnabled | self.StepDownEnabled        
    
    #def fixup(self, *args):
        #print "fixup:", args
    
    def stepBy(self, n):
        n = D(int(n))   ## n must be integral number of steps.
        s = [D(-1), D(1)][n >= 0]  ## determine sign of step
        val = self.val
        
        for i in range(abs(n)):
            
            if self.opts['log']:
                raise Exception("Log mode no longer supported.")
            #    step = abs(val) * self.opts['step']
            #    if 'minStep' in self.opts:
            #        step = max(step, self.opts['minStep'])
            #    val += step * s
            if self.opts['dec']:
                if val == 0:
                    step = self.opts['minStep']
                    exp = None
                else:
                    vs = [D(-1), D(1)][val >= 0]
                    #exp = D(int(abs(val*(D('1.01')**(s*vs))).log10()))
                    fudge = D('1.01')**(s*vs) ## fudge factor. at some places, the step size depends on the step sign.
                    exp = abs(val * fudge).log10().quantize(1, ROUND_FLOOR)
                    step = self.opts['step'] * D(10)**exp
                if 'minStep' in self.opts:
                    step = max(step, self.opts['minStep'])
                val += s * step
                #print "Exp:", exp, "step", step, "val", val
            else:
                val += s*self.opts['step']
                
            if 'minStep' in self.opts and abs(val) < self.opts['minStep']:
                val = D(0)
        self.setValue(val, delaySignal=True)  ## note all steps (arrow buttons, wheel, up/down keys..) emit delayed signals only.
        
    def setValue(self, value, update=True, delaySignal=False):
        #print "setValue:", value
        #if value == 0.0:
            #import traceback
            #traceback.print_stack()
        value = D(str(value))
        if value == self.val:
            #print "  value not changed; ignore."
            return
        
        bounds = self.opts['bounds']
        if bounds[0] is not None and value < bounds[0]:
            return
        if bounds[1] is not None and value > bounds[1]:
            return
        self.val = value
        if update:
            self.updateText()
            
        #self.emit(QtCore.SIGNAL('valueChanging'), float(self.val))  ## change will be emitted in 300ms if there are no subsequent changes.
        self.sigValueChanging.emit(float(self.val))  ## change will be emitted in 300ms if there are no subsequent changes.
        if not delaySignal:
            self.emitChanged()
        self.lineEdit().setStyleSheet('border: 0px;')

    def setMaximum(self, m):
        self.opts['bounds'][1] = D(str(m))
    
    def setMinimum(self, m):
        self.opts['bounds'][0] = D(str(m))
        
    def setProperty(self, prop, val):
        """setProperty is just for compatibility with QSpinBox"""
        if prop == 'value':
            if type(val) is QtCore.QVariant:
                val = val.toDouble()[0]
            self.setValue(val)
        else:
            print "Warning: SpinBox.setProperty('%s', ..) not supported." % prop

    def setSuffix(self, suf):
        self.setOpts(suffix=suf)

    def setSingleStep(self, step):
        self.setOpts(step=step)

    def value(self):
        return float(self.val)

    def updateText(self):
        #print "Update text."
        self.skipValidate = True
        if self.opts['siPrefix']:
            self.lineEdit().setText(siFormat(float(self.val), suffix=self.opts['suffix']))
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
            import sys
            sys.excepthook(*sys.exc_info())
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
        
        
    def editingFinishedEvent(self):
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
        
        
        
if __name__ == '__main__':
    app = QtGui.QApplication([])
    win = QtGui.QMainWindow()
    g = QtGui.QFormLayout()
    w = QtGui.QWidget()
    w.setLayout(g)
    win.setCentralWidget(w)
    s1 = SpinBox(value=5, step=0.1, bounds=[-1.5, None], suffix='units')
    t1 = QtGui.QLineEdit()
    g.addRow(s1, t1)
    s2 = SpinBox(dec=True, step=0.1, minStep=1e-6, suffix='A', siPrefix=True)
    t2 = QtGui.QLineEdit()
    g.addRow(s2, t2)
    s3 = SpinBox(dec=True, step=0.5, minStep=1e-6, bounds=[0, 10])
    t3 = QtGui.QLineEdit()
    g.addRow(s3, t3)
    s4 = SpinBox(dec=True, step=1, minStep=1e-6, bounds=[-10, 1000])
    t4 = QtGui.QLineEdit()
    g.addRow(s4, t4)

    win.show()
    import sys
    for sb in [s1, s2, s3,s4]:
        #QtCore.QObject.connect(sb, QtCore.SIGNAL('valueChanged(double)'), lambda v: sys.stdout.write(str(sb) + " valueChanged\n"))
        #QtCore.QObject.connect(sb, QtCore.SIGNAL('editingFinished()'), lambda: sys.stdout.write(str(sb) + " editingFinished\n"))
        sb.valueChanged.connect(lambda v: sys.stdout.write(str(sb) + " valueChanged\n"))
        sb.editingFinished.connect(lambda: sys.stdout.write(str(sb) + " editingFinished\n"))

    
        