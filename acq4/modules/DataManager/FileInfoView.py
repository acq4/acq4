# -*- coding: utf-8 -*-
from FileInfoViewTemplate import *
from PyQt4 import QtCore, QtGui
from acq4.util.DataManager import DirHandle
import acq4.Manager as Manager
import time
import acq4.util.configfile as configfile
from acq4.util.DictView import *

class FocusEventCatcher(QtCore.QObject):
    
    sigLostFocus = QtCore.Signal(object)
    
    def __init__(self):
        QtCore.QObject.__init__(self)
        
    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.FocusOut:
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
        self.focusEventCatcher.sigLostFocus.connect(self.focusLost)
        
    def setCurrentFile(self, file):
        #print "=============== set current file ============"
        if file is self.current:
            return
            
        if file is None:
            self.clear()
            self.current = None
            return
        
        self.current = file
        self.clear()
        
        ## Decide on the list of fields to display
        info = file.info()
        infoKeys = info.keys()
        fields = self.manager.suggestedDirFields(file)
        
        ## Generate fields, populate if data exists
        #print "Add %d rows.." % len(fields)

        # each field has a number of options that can be set by providing
        # either a dict or a tuple (where the order of arguments determine their meaning).
        fieldTypeArgs = {
            'text': ['numLines', 'default'],
            'string': ['default'],
            'list': ['values', 'default'],
            'bool': ['default'],
        }

        for fieldName, fieldOpts in fields.items():
            if fieldName in infoKeys:
                infoKeys.remove(fieldName)
            
            # a single value is interpreted as the first element of a tuple
            if not isinstance(fieldOpts, (dict, tuple)):
                fieldOpts = (fieldOpts,)
            
            if isinstance(fieldOpts, tuple):
                fieldTyp = fieldOpts[0]
                # convert to dict based on order of args
                fieldOpts = {fieldTypeArgs[fieldTyp][i-1]:fieldOpts[i] for i in range(1, len(fieldOpts))}
                fieldOpts['type'] = fieldTyp

            fieldTyp = fieldOpts['type']

            # now use args to create a widget for this field                
            value = info.get(fieldName, fieldOpts.get('default', None))
            if fieldTyp == 'text':
                w = QtGui.QTextEdit()
                w.setTabChangesFocus(True)
                if value is not None:
                    w.setText(value)
            elif fieldTyp == 'string':
                w = QtGui.QLineEdit()
                if value is not None:
                    w.setText(value)
            elif fieldTyp == 'list':
                w = QtGui.QComboBox()
                w.addItems([''] + fieldOpts['values'])
                w.setEditable(True)
                if value is not None:
                    w.lineEdit().setText(value)
            elif fieldTyp == 'bool':
                w = QtGui.QCheckBox()
                if value is not None:
                    w.setChecked(value)
            else:
                raise Exception("Don't understand info type '%s' (parameter %s)" % (fieldTyp, fieldName))
            self.addRow(fieldName, w)
        
        ## Add fields for any other keys that happen to be present
        #print "Add %d rows.." % len(infoKeys)
        for f in infoKeys:
            if isinstance(info[f], dict):
                w = DictView(info[f])
            else:
                s = str(info[f])
                if isinstance(f, basestring) and 'time' in f.lower() and info[f] > 1e9 and info[f] < 2e9:  ## probably this is a timestamp
                    try:
                        t0 = file.parent().info()['__timestamp__']
                        dt = " [elapsed = %0.3f s]" % (info[f] - t0)
                    except:
                        dt = ""
                    s = time.strftime("%Y.%m.%d   %H:%M:%S", time.localtime(float(s))) + dt
                    
                    
                w = QtGui.QLabel(s)
            if type(f) is tuple:
                f = '.'.join(f)
            f = str(f).replace('__', '')
            self.addRow(f, w)
            
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
        info = self.current.info()
        if field not in info or val != info[field]:
            self.current.setInfo({field: val})
            
    def clear(self):
        #print "clear"
        ## remove all rows from layout
        while self.ui.fileInfoLayout.count() > 0:
            w = self.ui.fileInfoLayout.takeAt(0).widget()
            w.setParent(None)
