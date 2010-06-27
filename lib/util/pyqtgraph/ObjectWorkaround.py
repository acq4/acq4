

## Multiple inheritance not allowed in PyQt. Retarded workaround:
def tryWorkaround(QtCore, QtGui):
    if not hasattr(QtGui, "QGraphicsObject"):
        class QObjectWorkaround:
            def __init__(self):
                self._qObj_ = QtCore.QObject()
            def connect(self, *args):
                return QtCore.QObject.connect(self._qObj_, *args)
            def disconnect(self, *args):
                return QtCore.QObject.disconnect(self._qObj_, *args)
            def emit(self, *args):
                return QtCore.QObject.emit(self._qObj_, *args)
                
        class QGraphicsObject(QtGui.QGraphicsItem, QObjectWorkaround):
            def __init__(self, *args):
                QtGui.QGraphicsItem.__init__(self, *args)
                QObjectWorkaround.__init__(self)
        QtGui.QGraphicsObject = QGraphicsObject
        
        QtCore.QObject.connect_original = QtCore.QObject.connect
        def connect(obj, signal, slot):
            if isinstance(obj, QtCore.QObject):
                QtCore.QObject.connect_original(obj, signal, slot)
            else:
                obj.connect(signal, slot)
        QtCore.QObject.connect = connect
        
        QtCore.QObject.disconnect_original = QtCore.QObject.disconnect
        def disconnect(obj, signal, slot):
            if isinstance(obj, QtCore.QObject):
                QtCore.QObject.disconnect_original(obj, signal, slot)
            else:
                obj.disconnect(signal, slot)
        QtCore.QObject.disconnect = disconnect