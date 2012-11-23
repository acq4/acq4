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
            'color': (1., 1., 1., 0.5),
            'shader': None,
            'smooth': True,
            'computeNormals': True,
        }
        
        GLGraphicsItem.__init__(self)
        glopts = kwds.pop('glOptions', 'opaque')
        self.setGLOptions(glopts)
        
        self.setData(**kwds)
        
        ## storage for data compiled from MeshData object
        self.vertexes = None
        self.normals = None
        self.colors = None
        self.faces = None
        
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
        md = kwds.get('meshdata', None)
        if md is None:
            opts = {}
            for k in ['vertexes', 'faces', 'edges', 'vertexColors', 'faceColors']:
                try:
                    opts[k] = kwds.pop(k)
                except KeyError:
                    pass
            md = MeshData(**opts)
        
        self.opts['meshdata'] = md
        self.opts.update(kwds)
        self.update()
        
        
    def initializeGL(self):
        pass
    
    #def setupGLState(self):
        #"""Prepare OpenGL state for drawing. This function is called immediately before painting."""
        ##glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        #glBlendFunc(GL_SRC_ALPHA, GL_ONE)
        ##glEnable(GL_BLEND)
        ##glEnable(GL_ALPHA_TEST)
        ##glAlphaFunc(GL_ALWAYS, 0.5)  ## fragments are always drawn regardless of alpha
        ##glEnable( GL_POINT_SMOOTH )
        #glEnable(GL_DEPTH_TEST)  ## fragments are always drawn regardless of depth
    
    
    def parseMeshData(self):
        ## interpret vertex / normal data before drawing
        ## This can:
        ##   - automatically generate normals if they were not specified
        ##   - pull vertexes/noormals/faces from MeshData if that was specified
        
        if self.vertexes is not None and self.normals is not None:
            return
        #if self.opts['normals'] is None:
            #if self.opts['meshdata'] is None:
                #self.opts['meshdata'] = MeshData(vertexes=self.opts['vertexes'], faces=self.opts['faces'])
        if self.opts['meshdata'] is not None:
            md = self.opts['meshdata']
            if self.opts['smooth'] and not md.hasFaceIndexedData():
                self.vertexes = md.vertexes()
                if self.opts['computeNormals']:
                    self.normals = md.vertexNormals()
                self.faces = md.faces()
                if md.hasVertexColor():
                    self.colors = md.vertexColors()
                if md.hasFaceColor():
                    self.colors = md.faceColors()
            else:
                self.vertexes = md.vertexes(indexed='faces')
                if self.opts['computeNormals']:
                    if self.opts['smooth']:
                        self.normals = md.vertexNormals(indexed='faces')
                    else:
                        self.normals = md.faceNormals(indexed='faces')
                self.faces = None
                if md.hasVertexColor():
                    self.colors = md.vertexColors(indexed='faces')
                elif md.hasFaceColor():
                    self.colors = md.faceColors(indexed='faces')
                    
            return
    
    def paint(self):
        self.setupGLState()
        
        self.parseMeshData()        
        
        self.shader = shaders.getShaderProgram(self.opts['shader'])
        with self.shader:
            #glCallList(self.triList)
            verts = self.vertexes
            norms = self.normals
            color = self.colors
            faces = self.faces
            #print "========"
            #print verts
            #print norms
            #print color
            #print faces
            glEnableClientState(GL_VERTEX_ARRAY)
            try:
                glVertexPointerf(verts)
                
                if self.colors is None:
                    color = self.opts['color']
                    if isinstance(color, QtGui.QColor):
                        glColor4f(*fn.glColor(color))
                    else:
                        glColor4f(*color)
                else:
                    glEnableClientState(GL_COLOR_ARRAY)
                    glColorPointerf(color)
                
                
                if norms is not None:
                    glEnableClientState(GL_NORMAL_ARRAY)
                    glNormalPointerf(norms)
                
                if faces is None:
                    glDrawArrays(GL_TRIANGLES, 0, np.product(verts.shape[:-1]))
                else:
                    faces = faces.astype(np.uint).flatten()
                    glDrawElements(GL_TRIANGLES, faces.shape[0], GL_UNSIGNED_INT, faces)
            finally:
                glDisableClientState(GL_NORMAL_ARRAY)
                glDisableClientState(GL_VERTEX_ARRAY)
                glDisableClientState(GL_COLOR_ARRAY)
            
