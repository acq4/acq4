from OpenGL.GL import *
from .. GLGraphicsItem import GLGraphicsItem
from .. MeshData import MeshData
from pyqtgraph.Qt import QtGui
import pyqtgraph as pg
from .. import shaders
import numpy as np



__all__ = ['GLMeshItem']

class GLMeshItem(GLGraphicsItem):
    """
    **Bases:** :class:`GLGraphicsItem <pyqtgraph.opengl.GLGraphicsItem>`
    
    Displays a 3D triangle mesh. 
    """
    def __init__(self, meshdata=None, vertexes=None, faces=None, normals=None, color=None, shader=None):
        """
        See :class:`MeshData <pyqtgraph.opengl.MeshData>` for initialization arguments.
        """
        self.meshdata = meshdata
        self.vertexes = vertexes
        self.faces = faces
        self.normals = normals
        self.color = color
        self.shader = shader
        
        #if isinstance(faces, MeshData):
            #self.data = faces
        #else:
            #self.data = MeshData()
            #self.data.setFaces(faces, vertexes)
        GLGraphicsItem.__init__(self)
        
    def initializeGL(self):
        self.shader = shaders.getShaderProgram('balloon')
        
        #l = glGenLists(1)
        #self.triList = l
        #glNewList(l, GL_COMPILE)
        
        #glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        #glEnable( GL_BLEND )
        #glEnable( GL_ALPHA_TEST )
        ##glAlphaFunc( GL_ALWAYS,0.5 )
        #glEnable( GL_POINT_SMOOTH )
        #glDisable( GL_DEPTH_TEST )
        #glColor4f(1, 1, 1, .1)
        #glBegin( GL_TRIANGLES )
        #for face in self.data:
            #for (pos, norm, color) in face:
                #glColor4f(*color)
                #glNormal3f(norm.x(), norm.y(), norm.z())
                #glVertex3f(pos.x(), pos.y(), pos.z())
        #glEnd()
        #glEndList()
        
        
        #l = glGenLists(1)
        #self.meshList = l
        #glNewList(l, GL_COMPILE)
        #glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        #glEnable( GL_BLEND )
        #glEnable( GL_ALPHA_TEST )
        ##glAlphaFunc( GL_ALWAYS,0.5 )
        #glEnable( GL_POINT_SMOOTH )
        #glEnable( GL_DEPTH_TEST )
        #glColor4f(1, 1, 1, .3)
        #glBegin( GL_LINES )
        #for f in self.faces:
            #for i in [0,1,2]:
                #j = (i+1) % 3
                #glVertex3f(*f[i])
                #glVertex3f(*f[j])
        #glEnd()
        #glEndList()
    def setupGLState(self):
        """Prepare OpenGL state for drawing. This function is called immediately before painting."""
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glEnable( GL_BLEND )
        glEnable( GL_ALPHA_TEST )
        #glAlphaFunc( GL_ALWAYS,0.5 )
        #glEnable( GL_POINT_SMOOTH )
        glDisable( GL_DEPTH_TEST )
                
    def paint(self):
        self.setupGLState()
        with self.shader:
            #glCallList(self.triList)
            
            glEnableClientState(GL_VERTEX_ARRAY)
            try:
                glVertexPointerf(self.vertexes)
                
                if isinstance(self.color, np.ndarray):
                    glEnableClientState(GL_COLOR_ARRAY)
                    glColorPointerf(self.color)
                else:
                    if isinstance(self.color, QtGui.QColor):
                        glColor4f(*fn.glColor(self.color))
                    else:
                        glColor4f(*self.color)
                
                if self.normals is None:
                    pass  ## construct normals here
                    
                
                glEnableClientState(GL_NORMAL_ARRAY)
                glNormalPointerf(self.normals)
                
                if self.faces is None:
                    glDrawArrays(GL_TRIANGLES, 0, len(self.vertexes))
                else:
                    faces = self.faces.astype(np.uint).flatten()
                    glDrawElements(GL_TRIANGLES, len(faces), GL_UNSIGNED_INT, faces)
            finally:
                glDisableClientState(GL_NORMAL_ARRAY)
                glDisableClientState(GL_VERTEX_ARRAY)
                glDisableClientState(GL_COLOR_ARRAY)
            
