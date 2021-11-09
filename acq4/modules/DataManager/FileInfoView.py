# -*- coding: utf-8 -*-
from __future__ import print_function

import time

import six

import acq4.Manager as Manager
from acq4.util import Qt
from acq4.util.DictView import DictView
from six.moves import range

Ui_Form = Qt.importTemplate('.FileInfoViewTemplate')


class FocusEventCatcher(Qt.QObject):
    
    sigLostFocus = Qt.Signal(object)
    
    def __init__(self):
        Qt.QObject.__init__(self)
        
    def eventFilter(self, obj, event):
        if event.type() == Qt.QEvent.FocusOut:
            self.sigLostFocus.emit(obj)
        return False


class MetadataField(object):
    class SignalEmitter(Qt.QObject):
        valueChanged = Qt.Signal(object)  # self

    configOrder = ['type']
        
    def __init__(self, widget, name, value, config):
        self.widget = widget
        self.name = name
        self.emitter = MetadataField.SignalEmitter()
        self.valueChanged = self.emitter.valueChanged  # maybe not necessary

        if value is None:
            value = self.configDict(config).get('default', None)
        
        if value is not None:
            self.setValue(value)

        self.focusEventCatcher = FocusEventCatcher()
        self.focusEventCatcher.sigLostFocus.connect(self.focusLost)
        self.widget.installEventFilter(self.focusEventCatcher)
        
    def configDict(self, config):
        return {name:config[i] for i,name in enumerate(self.configOrder) if i < len(config)}
        
    def getValue(self):
        raise NotImplementedError()
        
    def setValue(self, value):
        raise NotImplementedError()

    def focusLost(self, obj):
        self.valueChanged.emit(self)
            
        
class TextMetadata(MetadataField):
    configOrder = ['type', 'numLines', 'default']
    def __init__(self, name, value, config):
        widget = Qt.QTextEdit()
        widget.setTabChangesFocus(True)
        MetadataField.__init__(self, widget, name, value, config)

    def getValue(self):
        return str(self.widget.toPlainText())
        
    def setValue(self, value):
        self.widget.setText(value)


class StringMetadata(MetadataField):
    configOrder = ['type', 'default']
    def __init__(self, name, value, config):
        widget = Qt.QLineEdit()
        MetadataField.__init__(self, widget, name, value, config)

    def getValue(self):
        return str(self.widget.text())
        
    def setValue(self, value):
        self.widget.setText(value)


class ListMetadata(MetadataField):
    configOrder = ['type', 'values', 'default']
    def __init__(self, name, value, config):
        widget = Qt.QComboBox()
        widget.addItems([''] + self.configDict(config)['values'])
        widget.setEditable(True)
        MetadataField.__init__(self, widget, name, value, config)

    def getValue(self):
        return str(self.widget.currentText())
        
    def setValue(self, value):
        self.widget.lineEdit().setText(value)


class BoolMetadata(MetadataField):
    configOrder = ['type', 'default']
    def __init__(self, name, value, config):
        widget = Qt.QCheckBox()
        MetadataField.__init__(self, widget, name, value, config)

    def getValue(self):
        return self.widget.isChecked()
        
    def setValue(self, value):
        self.widget.setChecked(value)


fieldTypes = {
    'text': TextMetadata,
    'string': StringMetadata,
    'list': ListMetadata,
    'bool': BoolMetadata,
}


def registerFieldType(name, metadata_class):
    global fieldTypes
    fieldTypes[name] = metadata_class


class FileInfoView(Qt.QWidget):
    def __init__(self, parent):
        Qt.QWidget.__init__(self, parent)
        self.manager = Manager.getManager()
        self.ui = Ui_Form()
        self.ui.setupUi(self)
        self.current = None
        self.widgets = {}
        self.metadataFields = {}
        self.ui.fileInfoLayout = self.ui.formLayout_2
        
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
        infoKeys = list(info.keys())
        fields = self.manager.suggestedDirFields(file)
        
        ## Generate fields, populate if data exists

        for fieldName, fieldOpts in fields.items():
            if fieldName in infoKeys:
                infoKeys.remove(fieldName)
            
            # a single value is interpreted as the first element of a tuple
            if not isinstance(fieldOpts, (dict, tuple)):
                fieldOpts = (fieldOpts,)
            
            fieldTyp = fieldOpts[0]
            value = info.get(fieldName, None)
            metadata_class = fieldTypes[fieldTyp]
            w = metadata_class(name=fieldName, value=value, config=fieldOpts)
            self.addRow(fieldName, metadataField=w)
        
        ## Add fields for any other keys that happen to be present
        #print "Add %d rows.." % len(infoKeys)
        for f in infoKeys:
            if isinstance(info[f], dict):
                w = DictView(info[f])
            else:
                s = str(info[f])
                if isinstance(f, six.string_types) and 'time' in f.lower() and info[f] > 1e9 and info[f] < 2e9:  ## probably this is a timestamp
                    try:
                        t0 = file.parent().info()['__timestamp__']
                        dt = " [elapsed = %0.3f s]" % (info[f] - t0)
                    except:
                        dt = ""
                    s = time.strftime("%Y.%m.%d   %H:%M:%S", time.localtime(float(s))) + dt
                    
                w = Qt.QLabel(s)
            if type(f) is tuple:
                f = '.'.join(f)
            f = str(f).replace('__', '')
            self.addRow(f, widget=w)

    def fieldChanged(self, field):
        info = self.current.info()
        val = field.getValue()
        if field.name not in info or val != info[field.name]:
            self.current.setInfo({field.name: val})
            
    def addRow(self, name, metadataField=None, widget=None):
        """Add a row to the layout with a label/widget pair."""
        if metadataField is not None:
            widget = metadataField.widget
            metadataField.valueChanged.connect(self.fieldChanged)
            self.metadataFields[name] = metadataField
            
        self.widgets[name] = widget
        self.ui.fileInfoLayout.addRow(name, widget)
            
    def clear(self):
        ## remove all rows from layout
        while self.ui.fileInfoLayout.count() > 0:
            w = self.ui.fileInfoLayout.takeAt(0).widget()
            w.setParent(None)
        self.widgets = {}
        self.metadataFields = {}
