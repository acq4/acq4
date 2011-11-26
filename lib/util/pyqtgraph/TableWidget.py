# -*- coding: utf-8 -*-
from PyQt4 import QtCore, QtGui
import numpy as np
try:
    import metaarray
    HAVE_METAARRAY = True
except:
    HAVE_METAARRAY = False

class TableWidget(QtGui.QTableWidget):
    """Extends QTableWidget with some useful functions for automatic data handling.
    Can automatically format and display:
        numpy arrays
        numpy record arrays 
        metaarrays
        list-of-lists  [[1,2,3], [4,5,6]]
        dict-of-lists  {'x': [1,2,3], 'y': [4,5,6]}
        list-of-dicts  [
                         {'x': 1, 'y': 4}, 
                         {'x': 2, 'y': 5}, 
                         {'x': 3, 'y': 6}
                       ]
    """
    
    def __init__(self, *args):
        QtGui.QTableWidget.__init__(self, *args)
        self.setVerticalScrollMode(self.ScrollPerPixel)
        self.clear()
        self.contextMenu = QtGui.QMenu()
        self.contextMenu.addAction('copy').triggered.connect(self.copy)
        
    def clear(self):
        QtGui.QTableWidget.clear(self)
        self.headersSet = False
        self.items = []
        self.setRowCount(0)
        self.setColumnCount(0)
        
    def setData(self, data):
        self.clear()
        self.appendData(data)
        
    def appendData(self, data):
        """Types allowed:
        1 or 2D numpy array or metaArray
        1D numpy record array
        list-of-lists, list-of-dicts or dict-of-lists
        """
        fn0, header0 = self.iteratorFn(data)
        if fn0 is None:
            self.clear()
            return
        it0 = fn0(data)
        try:
            first = it0.next()
        except StopIteration:
            return
        #if type(first) == type(np.float64(1)):
        #   return
        fn1, header1 = self.iteratorFn(first)
        if fn1 is None:
            self.clear()
            return
        
        #print fn0, header0
        #print fn1, header1
        firstVals = [x for x in fn1(first)]
        self.setColumnCount(len(firstVals))
        
        if not self.headersSet:
            if header0 is not None:
                #print "set header 0:", header0
                self.setRowCount(len(header0))
                self.setVerticalHeaderLabels(header0)
            if header1 is not None:
                #print "set header 1:", header1
                self.setHorizontalHeaderLabels(header1)
            self.headersSet = True
        
        self.setRow(0, firstVals)
        i = 1
        for row in it0:
            self.setRow(i, [x for x in fn1(row)])
            i += 1
            
    def iteratorFn(self, data):
        """Return 1) a function that will provide an iterator for data and 2) a list of header strings"""
        if isinstance(data, list):
            return lambda d: d.__iter__(), None
        elif isinstance(data, dict):
            return lambda d: d.itervalues(), map(str, data.keys())
        elif HAVE_METAARRAY and isinstance(data, metaarray.MetaArray):
            if data.axisHasColumns(0):
                header = [str(data.columnName(0, i)) for i in xrange(data.shape[0])]
            elif data.axisHasValues(0):
                header = map(str, data.xvals(0))
            else:
                header = None
            return self.iterFirstAxis, header
        elif isinstance(data, np.ndarray):
            return self.iterFirstAxis, None
        elif isinstance(data, np.void):
            return self.iterate, map(str, data.dtype.names)
        elif data is None:
            return (None,None)
        else:
            raise Exception("Don't know how to iterate over data type: %s" % str(type(data)))
        
    def iterFirstAxis(self, data):
        for i in xrange(data.shape[0]):
            yield data[i]
            
    def iterate(self, data):  ## for numpy.void, which can be iterated but mysteriously has no __iter__ (??)
        for x in data:
            yield x
        
    def appendRow(self, data):
        self.appendData([data])
        
    def addRow(self, vals):
        #print "add row:", vals
        row = self.rowCount()
        self.setRowCount(row+1)
        self.setRow(row, vals)
        
    def setRow(self, row, vals):
        if row > self.rowCount()-1:
            self.setRowCount(row+1)
        for col in xrange(self.columnCount()):
            val = vals[col]
            if isinstance(val, float) or isinstance(val, np.floating):
                s = "%0.3g" % val
            else:
                s = str(val)
            item = QtGui.QTableWidgetItem(s)
            item.value = val
            #print "add item to row %d:"%row, item, item.value
            self.items.append(item)
            self.setItem(row, col, item)
            

    def copy(self):
        """Copy selected data to clipboard."""
        s = u''
        for r in range(self.rowCount()):
            row = []
            for c in range(self.columnCount()):
                item = self.item(r, c)
                if item is not None:
                    row.append(unicode(item.value))
                else:
                    row.append(u'')
            s += (u'\t'.join(row) + u'\n')
        QtGui.QApplication.clipboard().setText(s)

    def contextMenuEvent(self, ev):
        self.contextMenu.popup(ev.globalPos())
        
    def keyPressEvent(self, ev):
        if ev.text() == 'c' and ev.modifiers() == QtCore.Qt.ControlModifier:
            ev.accept()
            self.copy()
        else:
            ev.ignore()



if __name__ == '__main__':
    app = QtGui.QApplication([])
    win = QtGui.QMainWindow()
    t = TableWidget()
    win.setCentralWidget(t)
    win.resize(800,600)
    win.show()
    
    ll = [[1,2,3,4,5]] * 20
    ld = [{'x': 1, 'y': 2, 'z': 3}] * 20
    dl = {'x': range(20), 'y': range(20), 'z': range(20)}
    
    a = np.ones((20, 5))
    ra = np.ones((20,), dtype=[('x', int), ('y', int), ('z', int)])
    
    if HAVE_METAARRAY:
        ma = metaarray.MetaArray(np.ones((20, 3)), info=[
            {'values': np.linspace(1, 5, 20)}, 
            {'cols': [
                {'name': 'x'},
                {'name': 'y'},
                {'name': 'z'},
            ]}
        ])
    
    t.setData(ll)
    