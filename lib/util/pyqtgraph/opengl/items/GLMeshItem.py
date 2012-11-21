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
    def __init__(self, **kwds):
        """
        All initialization arguments are passed to setData(...)
        """
        self.opts = {
            'meshdata': None,
            'vertexes': None,
            'faces': None,
            'normals': None,
            'color': (1., 1., 1., 0.5),
            'shader': 'balloon',
            'smooth': True,
        }
        
        GLGraphicsItem.__init__(self)
        self.setData(**kwds)
        #self.meshdata = meshdata
        #self.vertexes = vertexes
        #self.faces = faces
        #self.normals = normals
        #self.color = color
        #self.shader = shader
        
        #if isinstance(faces, MeshData):
            #self.data = faces
        #else:
            #self.data = MeshData()
            #self.data.setFaces(faces, vertexes)
        
    def setData(self, **kwds):
        if kwds.get('meshdata', None) is not None:
            self.opts['vectors'] = None
            self.opts['normals'] = None
            self.opts['faces'] = None
        self.opts.update(kwds)
        self.update()
        
        
    def initializeGL(self):
        pass
        #self.shader = shaders.getShaderProgram(self.opts['shader'])
        
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
        self.shader = shaders.getShaderProgram(self.opts['shader'])
                
                
    def parseMeshData(self):
        ## interpret vertex / normal data before drawing
        ## This can:
        ##   - automatically generate normals if they were not specified
        ##   - pull vertexes/noormals/faces from MeshData if that was specified
        
        if self.opts['vertexes'] is not None and self.opts['normals'] is not None:
            return
        if self.opts['normals'] is None:
            if self.opts['meshdata'] is None:
                self.opts['meshdata'] = MeshData(vertexes=self.opts['vertexes'], faces=self.opts['faces'])
            #else:
                #self.opts['meshdata'].setFaces(vertexes=self.opts['vertexes'], faces=self.opts['faces'])
        if self.opts['meshdata'] is not None:
            md = self.opts['meshdata']
            if self.opts['smooth']:
                self.opts['vertexes'] = md.vertexes()
                self.opts['normals'] = md.vertexNormals()
                self.opts['faces'] = md.faces()
            else:
                self.opts['vertexes'] = md.vertexes(indexed='faces')
                self.opts['normals'] = md.faceNormals(indexed='faces')
                self.opts['faces'] = None
            return
                
        
                
    def paint(self):
        self.setupGLState()
        
        self.parseMeshData()        
        
        with self.shader:
            #glCallList(self.triList)
            verts = self.opts['vertexes']
            norms = self.opts['normals']
            color = self.opts['color']
            faces = self.opts['faces']
            
            glEnableClientState(GL_VERTEX_ARRAY)
            try:
                glVertexPointerf(verts)
                
                if isinstance(color, np.ndarray):
                    glEnableClientState(GL_COLOR_ARRAY)
                    glColorPointerf(color)
                else:
                    if isinstance(color, QtGui.QColor):
                        glColor4f(*fn.glColor(color))
                    else:
                        glColor4f(*color)
                
                if norms is None:
                    pass  ## construct normals here
                    
                
                glEnableClientState(GL_NORMAL_ARRAY)
                glNormalPointerf(norms)
                
                if faces is None:
                    glDrawArrays(GL_TRIANGLES, 0, len(verts))
                else:
                    faces = faces.astype(np.uint).flatten()
                    glDrawElements(GL_TRIANGLES, len(faces), GL_UNSIGNED_INT, faces)
            finally:
                glDisableClientState(GL_NORMAL_ARRAY)
                glDisableClientState(GL_VERTEX_ARRAY)
                glDisableClientState(GL_COLOR_ARRAY)
            
