from OpenGL.GL import *
from .. GLGraphicsItem import GLGraphicsItem
from pyqtgraph import QtGui
import numpy as np

__all__ = ['GLScatterPlotItem']

class GLScatterPlotItem(GLGraphicsItem):
    """Draws points at a list of 3D positions."""
    
    def __init__(self, **kwds):
        GLGraphicsItem.__init__(self)
        self.pos = []
        self.colors = None
        self.sizes = None
        self.size = 10
        self.color = [1.0,1.0,1.0,0.5]
        self.pxMode = True
        self.setData(**kwds)
    
    def setData(self, **kwds):
        """
        Data may be either a list of dicts (one dict per point) or a numpy record array.
        
        ====================  ==================================================
        Arguments
        data                  data to be plotted, including position, color, and
                              size (see below).
        pxMode                If True, size is interpreted as pixels. Otherwise,
                              size is expressed in the item's coordinate system.
        ====================  ==================================================
        
        
        ====================  ==================================================
        Allowed data fields:
        ------------------------------------------------------------------------
        pos                   (x,y,z) tuple of coordinate values or QVector3D
        color                 (r,g,b,a) tuple of floats (0.0-1.0) or QColor
        size                  (float) diameter of spot
        ====================  ==================================================
        
        
        """
        self.pos = kwds.get('pos', self.pos)
        self.color = kwds.get('color', self.color)
        self.size = kwds.get('size', self.size)
        self.colors = kwds.get('colors', self.colors)
        self.sizes = kwds.get('sizes', self.sizes)
        self.pxMode = kwds.get('pxMode', self.pxMode)
        self.update()

        
    def initializeGL(self):
        
        ## Generate texture for rendering points
        w = 64
        def fn(x,y):
            r = ((x-w/2.)**2 + (y-w/2.)**2) ** 0.5
            return 200 * (w/2. - np.clip(r, w/2.-1.0, w/2.))
        pData = np.empty((w, w, 4))
        pData[:] = 255
        pData[:,:,3] = np.fromfunction(fn, pData.shape[:2])
        #print pData.shape, pData.min(), pData.max()
        pData = pData.astype(np.ubyte)
        
        self.pointTexture = glGenTextures(1)
        glActiveTexture(GL_TEXTURE0)
        glEnable(GL_TEXTURE_2D)
        glBindTexture(GL_TEXTURE_2D, self.pointTexture)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, pData.shape[0], pData.shape[1], 0, GL_RGBA, GL_UNSIGNED_BYTE, pData)
        
    def paint(self):
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glEnable( GL_BLEND )
        glEnable( GL_ALPHA_TEST )
        glEnable( GL_POINT_SMOOTH )

        glHint(GL_POINT_SMOOTH_HINT, GL_NICEST)
        #glPointParameterfv(GL_POINT_DISTANCE_ATTENUATION, (0, 0, -1e-3))
        #glPointParameterfv(GL_POINT_SIZE_MAX, (65500,))
        #glPointParameterfv(GL_POINT_SIZE_MIN, (0,))
        
        
        if self.pxMode:     
            glVertexPointerf(self.pos)
            if self.colors is None:
                glColor4f(*self.color)
            else:
                glColorPointerf(self.colors)
            glPointSize(self.size)
            glEnableClientState(GL_VERTEX_ARRAY)
            glDrawArrays(GL_POINTS, 0, len(self.pos))
        else:
            glEnable(GL_POINT_SPRITE)
            glActiveTexture(GL_TEXTURE0)
            glEnable( GL_TEXTURE_2D )
            glBindTexture(GL_TEXTURE_2D, self.pointTexture)
        
            glTexEnvi(GL_POINT_SPRITE, GL_COORD_REPLACE, GL_TRUE)
            #glTexEnvi(GL_TEXTURE_ENV, GL_TEXTURE_ENV_MODE, GL_REPLACE)    ## use texture color exactly
            glTexEnvf( GL_TEXTURE_ENV, GL_TEXTURE_ENV_MODE, GL_MODULATE )  ## texture modulates current color
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
            
            
            for i in range(len(self.pos)):
                pos = self.pos[i]
                
                if self.colors is None:
                    color = self.color
                else:
                    color = self.colors[i]
                if isinstance(color, QtGui.QColor):
                    color = fn.glColor(color)
                    
                if self.sizes is None:
                    size = self.size
                else:
                    size = self.sizes[i]
                    
                    
                pxSize = self.view().pixelSize(QtGui.QVector3D(*pos))
                
                glPointSize(size / pxSize)
                glBegin( GL_POINTS )
                glColor4f(*color)  # x is blue
                #glNormal3f(size, 0, 0)
                glVertex3f(*pos)
                glEnd()

        
        
        
        