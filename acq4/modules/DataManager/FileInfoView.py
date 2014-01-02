# -*- coding: utf-8 -*-
from FileInfoViewTemplate import *
from PyQt4 import QtCore, QtGui
from acq4.util.DataManager import DirHandle
import acq4.Manager as Manager
#import sip
import time
import acq4.util.configfile as configfile
from acq4.util.DictView import *

class FocusEventCatcher(QtCore.QObject):
    
    sigLostFocus = QtCore.Signal(object)
    
    def __init__(self):
        QtCore.QObject.__init__(self)
        
    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.FocusOut:
            #self.emit(QtCore.SIGNAL("lostFocus"), obj)
            self.sigLostFocus.emit(obj)
        return False


class FileInfoView(QtGui.QWidget):
    def __init__(self, parent):
        QtGui.QWidget.__init__(self, parent)
        self.manager = Manager.getManager()
        self.ui = Ui_Form()
        self.ui.setupUi(self)
        self.current = None
        self.widgets = {}
        self.ui.fileInfoLayout = self.ui.formLayout_2
        self.focusEventCatcher = FocusEventCatcher()
        #QtCore.QObject.connect(self.focusEventCatcher, QtCore.SIGNAL('lostFocus'), self.focusLost)
        self.focusEventCatcher.sigLostFocus.connect(self.focusLost)
        
    def setCurrentFile(self, file):
        #print "=============== set current file ============"
        if file is self.current:
            return
            
        if file is None:
            self.clear()
            self.current = None
            return
        
        #if self.current is not None:
            #QtCore.QObject.disconnect(self.current, QtCore.SIGNAL('changed'), self.currentDirChanged)
        
        self.current = file
        self.clear()
        #QtCore.QObject.connect(self.current, QtCore.SIGNAL('changed'), self.currentDirChanged)
        
        ## Decide on the list of fields to display
        info = file.info()
        infoKeys = info.keys()
        #fields = OrderedDict()
        fields = self.manager.suggestedDirFields(file)
            
        
        ## Generate fields, populate if data exists
        #print "Add %d rows.." % len(fields)
        for f in fields:
            if f in infoKeys:
                infoKeys.remove(f)
                
            if type(fields[f]) is tuple:
                ft = fields[f][0]
            else:
                ft = fields[f]
                
            if ft == 'text':
                w = QtGui.QTextEdit()
                w.setTabChangesFocus(True)
                if f in info:
                    w.setText(info[f])
            elif ft == 'string':
                w = QtGui.QLineEdit()
                if f in info:
                    w.setText(info[f])
            elif ft == 'list':
                w = QtGui.QComboBox()
                w.addItems([''] + fields[f][1])
                w.setEditable(True)
                if f in info:
                    w.lineEdit().setText(info[f])
            elif ft == 'bool':
                w = QtGui.QCheckBox()
                if f in info:
                    w.setChecked(info[f])
            else:
                raise Exception("Don't understand info type '%s' (parameter %s)" % (fields[f][0], f))
            self.addRow(f, w)
        #self.ui.fileInfoLayout.setMinAndMaxSize()
        
        ## Add fields for any other keys that happen to be present
        #print "Add %d rows.." % len(infoKeys)
        for f in infoKeys:
            if isinstance(info[f], dict):
                w = DictView(info[f])
                #s = configfile.genString(info[f])
            else:
                s = str(info[f])
                if isinstance(f, basestring) and 'time' in f.lower() and info[f] > 1e9 and info[f] < 2e9:  ## probably this is a timestamp
                    try:
                        t0 = file.parent().info()['__timestamp__']
                        dt = " [elapsed = %0.3f s]" % (info[f] - t0)
                    except:
                        dt = ""
                        #raise
                    s = time.strftime("%Y.%m.%d   %H:%M:%S", time.localtime(float(s))) + dt
                    
                    
                w = QtGui.QLabel(s)
            if type(f) is tuple:
                f = '.'.join(f)
            f = str(f).replace('__', '')
            self.addRow(f, w)
            
    #def currentDirChanged(self, name, change, *args):
        #if change in ['renamed', 'moved', 'parent']:
            #self.setCurrentFile
            
    def addRow(self, name, widget):
        
        """Add a row to the layout with a label/widget pair."""
        #print "addRow"
        self.widgets[widget] = name
        self.ui.fileInfoLayout.addRow(name, widget)
        widget.installEventFilter(self.focusEventCatcher)
            
    def focusLost(self, obj):
        field = self.widgets[obj]
        #print "focus lost", obj, field
        if isinstance(obj, QtGui.QLineEdit):
            val = str(obj.text())
        elif isinstance(obj, QtGui.QTextEdit):
            val = str(obj.toPlainText())
        elif isinstance(obj, QtGui.QComboBox):
            val = str(obj.currentText())
        elif isinstance(obj, QtGui.QCheckBox):
            val = obj.isChecked()
        else:
            return
        #print "Update", field, val
        self.current.setInfo({field: val})
            
    def clear(self):
        #print "clear"
        ## remove all rows from layout
        #count = 0
        while self.ui.fileInfoLayout.count() > 0:
            w = self.ui.fileInfoLayout.takeAt(0).widget()
            #sip.delete(w)
            w.setParent(None)
            
            
            #w.setParent(None)
            #count += 1
        #print "removed %d widgets" % count
            
    
    