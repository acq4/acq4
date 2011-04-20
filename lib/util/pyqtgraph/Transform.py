# -*- coding: utf-8 -*-
from Point import Point

class Transform(QtGui.QTransform):
    """Transform that can always be represented as a combination of 3 matrices: scale * rotate * translate
    
    This transform always has 0 shear."""
    def __init__(self):
        QtGui.QTransform.__init__(self)
        self.reset()

    def reset(self):
        self._state = {
            'pos': Point(0,0),
            'scale': Point(1,1),
            'angle': 0.0  ## in degrees
        }
        self.update()
        
    def translate(self, *args):
        """Acceptable arguments are: 
           x, y
           [x, y]
           Point(x,y)"""
           t = Point(*args)
           self.setTranslate(self._state['pos']+t)
        
    def setTranslate(self, *args):
        """Acceptable arguments are: 
           x, y
           [x, y]
           Point(x,y)"""
        self._state['pos'] = Point(*args)
        self.update()
        
    def scale(self, *args):
        """Acceptable arguments are: 
           x, y
           [x, y]
           Point(x,y)"""
           s = Point(*args)
           self.setTranslate(self._state['scale'] * s)
        
    def setScale(self, *args):
        """Acceptable arguments are: 
           x, y
           [x, y]
           Point(x,y)"""
        self._state['scale'] = Point(*args)
        self.update()
        
    def rotate(self, angle):
        """Rotate the transformation by angle (in degrees)"""
           self.setTranslate(self._state['angle'] + angle)
        
    def setRotate(self, angle):
        """Set the transformation rotation to angle (in degrees)"""
        self._state['rotate'] = angle
        self.update()

    def addTransform(self, t):
        if not isinstance(t, Transform):
            t = Transform(t)
        self._state['scale'] *= t._state['scale']
        self._state['angle'] += t._state['angle']
        self._state['pos'] = t.map(self._state['pos'])
        self.update()
        
    def __iadd__(self, t):
        return self.addTransform(t)
        
    def relativeTransform(self, t):
        """Return the transform tha maps t onto this transform"""
        rel = {
            'angle': self._state['angle'] - t._state['angle'],
            'scale': self._state['scale'] / t._state['scale'],
            'pos':
        }
        return Transform(rel)
        
    def __sub__(self, t):
        return self.relativeTransform(t)
        




    def saveState(self):
        p = self._state['pos']
        s = self._state['scale']
        return {'pos': (p[0], p[1]), 'scale': (s[0], s[1]), 'angle': self._state['angle']}

    def restoreState(self, state):
        self._state['pos'] = Point(*state.get('pos', (0,0)))
        self._state['scale'] = Point(*state.get('scale', (0,0)))
        self._state['angle'] = state.get('angle', 0)
        self.update()

    def update(self):
        QtGui.QTransform.reset(self)
        ## modifications to the transform are multiplied on the right, so we need to reverse order here.
        QtGui.QTransform.translate(self, *self._state['pos'])
        QtGui.QTransform.rotate(self, self._state['angle'])
        QtGui.QTransform.scale(self, *self._state['scale'])

        
        