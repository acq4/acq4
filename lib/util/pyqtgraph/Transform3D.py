# -*- coding: utf-8 -*-
from Qt import QtCore, QtGui
from Vector import Vector
import numpy as np

class Transform3D(QtGui.QMatrix4x4):
    """4x4 Transform matrix that can always be represented as a combination of 3 matrices: scale * rotate * translate
    This transform has no shear; angles are always preserved.
    """
    def __init__(self, init=None):
        QtGui.QMatrix4x4.__init__(self)
        self.reset()
        
        if isinstance(init, dict):
            self.restoreState(init)
        elif isinstance(init, Transform3D):
            self._state = {
                'pos': Vector(init._state['pos']),
                'scale': Vector(init._state['scale']),
                'angle': init._state['angle'],
                'axis': Vector(init._state['axis']),
            }
            self.update()
        elif isinstance(init, Transform):
            self._state = {
                'pos': Vector(init._state['pos']),
                'scale': Vector(init._state['scale']),
                'angle': init._state['angle'],
                'axis': Vector(0, 0, 1),
            }
            self.update()

        
    def getScale(self):
        return self._state['scale']
        
    def getOrientation(self):
        """Return (angle, axis) of rotation"""
        return self._state['angle'], self._state['axis']
        
    def getTranslation(self):
        return self._state['pos']
    
    def reset(self):
        self._state = {
            'pos': Vector(0,0,0),
            'scale': Vector(1,1,1),
            'angle': 0.0,  ## in degrees
            'axis': (0, 0, 1)
        }
        self.update()
        
    def translate(self, *args):
        t = Vector(*args)
        self.setTranslate(self._state['pos']+t)
        
    def setTranslate(self, *args):
        self._state['pos'] = Vector(*args)
        self.update()
        
    def scale(self, *args):
        s = Vector(*args)
        self.setScale(self._state['scale'] * s)
        
    def setScale(self, *args):
        self._state['scale'] = Vector(*args)
        self.update()
        
    #def rotate(self, angle, axis):
        #self.setRotate(self._state['angle'] + angle)
        
    def setRotate(self, angle, axis=(0,0,1)):
        """Set the transformation rotation to angle (in degrees)"""
        
        self._state['angle'] = angle
        self._state['axis'] = Vector(axis)
        self.update()

    #def __div__(self, t):
        #"""A / B  ==  B^-1 * A"""
        #dt = t.inverted()[0] * self
        #return Transform(dt)
        
    #def __mul__(self, t):
        #return Transform(QtGui.QTransform.__mul__(self, t))

    def saveState(self):
        p = self._state['pos']
        s = self._state['scale']
        ax = self._state['axis']
        #if s[0] == 0:
            #raise Exception('Invalid scale: %s' % str(s))
        return {
            'pos': (p[0], p[1], p[2]), 
            'scale': (s[0], s[1], s[2]), 
            'angle': self._state['angle'], 
            'axis': (ax[0], ax[1], ax[2])
        }

    def restoreState(self, state):
        self._state['pos'] = Vector(state.get('pos', (0.,0.,0.)))
        self._state['scale'] = Vector(state.get('scale', (1.,1.,1.)))
        self._state['angle'] = state.get('angle', 0.)
        self._state['axis'] = state.get('axis', (0, 0, 1))
        self.update()

    def update(self):
        QtGui.QMatrix4x4.setToIdentity(self)
        ## modifications to the transform are multiplied on the right, so we need to reverse order here.
        QtGui.QMatrix4x4.translate(self, *self._state['pos'])
        QtGui.QMatrix4x4.rotate(self, self._state['angle'], *self._state['axis'])
        QtGui.QMatrix4x4.scale(self, *self._state['scale'])

    def __repr__(self):
        return str(self.saveState())
        
    def matrix(self):
        return np.array(self.copyDataTo())
        
if __name__ == '__main__':
    import widgets
    import GraphicsView
    from functions import *
    app = QtGui.QApplication([])
    win = QtGui.QMainWindow()
    win.show()
    cw = GraphicsView.GraphicsView()
    #cw.enableMouse()  
    win.setCentralWidget(cw)
    s = QtGui.QGraphicsScene()
    cw.setScene(s)
    win.resize(600,600)
    cw.enableMouse()
    cw.setRange(QtCore.QRectF(-100., -100., 200., 200.))
    
    class Item(QtGui.QGraphicsItem):
        def __init__(self):
            QtGui.QGraphicsItem.__init__(self)
            self.b = QtGui.QGraphicsRectItem(20, 20, 20, 20, self)
            self.b.setPen(QtGui.QPen(mkPen('y')))
            self.t1 = QtGui.QGraphicsTextItem(self)
            self.t1.setHtml('<span style="color: #F00">R</span>')
            self.t1.translate(20, 20)
            self.l1 = QtGui.QGraphicsLineItem(10, 0, -10, 0, self)
            self.l2 = QtGui.QGraphicsLineItem(0, 10, 0, -10, self)
            self.l1.setPen(QtGui.QPen(mkPen('y')))
            self.l2.setPen(QtGui.QPen(mkPen('y')))
        def boundingRect(self):
            return QtCore.QRectF()
        def paint(self, *args):
            pass
            
    #s.addItem(b)
    #s.addItem(t1)
    item = Item()
    s.addItem(item)
    l1 = QtGui.QGraphicsLineItem(10, 0, -10, 0)
    l2 = QtGui.QGraphicsLineItem(0, 10, 0, -10)
    l1.setPen(QtGui.QPen(mkPen('r')))
    l2.setPen(QtGui.QPen(mkPen('r')))
    s.addItem(l1)
    s.addItem(l2)
    
    tr1 = Transform()
    tr2 = Transform()
    tr3 = QtGui.QTransform()
    tr3.translate(20, 0)
    tr3.rotate(45)
    print "QTransform -> Transform:", Transform(tr3)
    
    print "tr1:", tr1
    
    tr2.translate(20, 0)
    tr2.rotate(45)
    print "tr2:", tr2
    
    dt = tr2/tr1
    print "tr2 / tr1 = ", dt
    
    print "tr2 * tr1 = ", tr2*tr1
    
    tr4 = Transform()
    tr4.scale(-1, 1)
    tr4.rotate(30)
    print "tr1 * tr4 = ", tr1*tr4
    
    w1 = widgets.TestROI((19,19), (22, 22), invertible=True)
    #w2 = widgets.TestROI((0,0), (150, 150))
    w1.setZValue(10)
    s.addItem(w1)
    #s.addItem(w2)
    w1Base = w1.getState()
    #w2Base = w2.getState()
    def update():
        tr1 = w1.getGlobalTransform(w1Base)
        #tr2 = w2.getGlobalTransform(w2Base)
        item.setTransform(tr1)
        
    #def update2():
        #tr1 = w1.getGlobalTransform(w1Base)
        #tr2 = w2.getGlobalTransform(w2Base)
        #t1.setTransform(tr1)
        #w1.setState(w1Base)
        #w1.applyGlobalTransform(tr2)
        
    w1.sigRegionChanged.connect(update)
    #w2.sigRegionChanged.connect(update2)
    
    	