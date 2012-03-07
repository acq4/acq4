from OpenGL.GL import *
from .. GLGraphicsItem import GLGraphicsItem
from pyqtgraph.Qt import QtGui
import numpy as np

__all__ = ['GLMeshItem']

class GLMeshItem(GLGraphicsItem):
    def __init__(self, faces):
        self.faces = faces
        GLGraphicsItem.__init__(self)
        
    def initializeGL(self):
        l = glGenLists(1)
        self.meshList = l
        glNewList(l, GL_COMPILE)
        
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glEnable( GL_BLEND )
        glEnable( GL_ALPHA_TEST )
        #glAlphaFunc( GL_ALWAYS,0.5 )
        glEnable( GL_POINT_SMOOTH )
        glDisable( GL_DEPTH_TEST )
        glColor4f(1, 1, 1, .3)
        glBegin( GL_LINES )
        for f in self.faces:
            for i in [0,1,2]:
                j = (i+1) % 3
                glVertex3f(*f[i])
                glVertex3f(*f[j])
        glEnd()
        glEndList()

                
    def paint(self):
        glCallList(self.meshList)  ## draw axes
