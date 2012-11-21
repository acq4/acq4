from pyqtgraph.Qt import QtGui
import pyqtgraph.functions as fn
import numpy as np

class MeshData(object):
    """
    Class for storing and operating on 3D mesh data. May contain:
    
    - list of vertex locations
    - list of edges
    - list of triangles
    - colors per vertex, edge, or tri
    - normals per vertex or tri
    """

    def __init__(self, vertexes=None, faces=None, edges=None, ):
        print "init", self
        ##  Ways we could specify this data:
        ##  
        ##  Nv = len(vertexes),  Ne = len(edges),  Nf = len(triangles)
        ##  vertexes - vertex list (Nv, 3), face list (Nf, 3, 3), or edge list (Ne, 2, 3)
        ##  faceIndex - (Nf, 3)
        ##  edgeIndex - (Ne, 2)
        ##  vertexNormals - vertex list (Nv, 3), face list (Nf, 3, 3), 
        ##  faceNormals - face list (Nf, 3)
        ##  vertexColors - vertex list (Nv, 4), face list (Nf, 3, 4), edge list (Ne, 2, 4)
        ##  faceColors - face list (Nf, 4)
        ##  edgeColors - edge list (Ne, 4)
        ##  
        ##  quantization limits: 1e-16 ?
        ##  
        ##  
        ##  
        ##  Ways we could use this data:
        ##  
        ##  vertexes (Nv, 3), vertexNormals (Nv, 3), vertexColors (Nv, 4), faceIndex   (smooth, indexed)
        ##  vertexes (Nf, 3, 3), vertexNormals (Nf, 3, 3), vertexColors (Nv, 3, 4)     (rough, non-indexed)
        ##       note vertexNormals / vertexColors could be specified directly
        ##       or computed from vertexColors / faceColors / edgeColors...
             
        
        
        
        
        
        
        
        
        self._vertexes = None  # Mx3 array of vertex coordinates
        self._faces = None   # Nx3 array of indexes into self._vertexes specifying three vertexes for each face
        self._edges = None
        self._vertexFaces = None  ## maps vertex ID to a list of face IDs
        self._vertexNormals = None
        self._faceNormals = None
        self._vertexColors = None
        self._edgeColors = None
        self._faceColors = None
        self._meshColor = (1, 1, 1, 0.1)  # default color to use if no face/edge/vertex colors are given
        
        if vertexes is not None:
            self.setFaces(vertexes, faces)
        
    def setFaces(self, vertexes, faces=None):
        """
        Set the faces in this data set.
        Data may be provided either as an Nx3x3 array of floats (9 float coordinate values per face)::
        
            faces = [ [(x, y, z), (x, y, z), (x, y, z)], ... ] 
            
        or as an Nx3 array of ints (vertex integers) AND an Mx3 array of floats (3 float coordinate values per vertex)::
        
            faces = [ (p1, p2, p3), ... ]
            vertexes = [ (x, y, z), ... ]
            
        """
        if not isinstance(vertexes, np.ndarray):
            vertexes = np.array(vertexes)
        if faces is None:
            print "unindexed", self
            self._setUnindexedFaces(vertexes)
        else:
            print "indexed", self
            self._setIndexedFaces(faces, vertexes)
        print self.vertexes().shape
        print self.faces().shape
        
    
    def setMeshColor(self, color):
        """Set the color of the entire mesh. This removes any per-face or per-vertex colors."""
        color = fn.Color(color)
        self._meshColor = color.glColor()
        self._vertexColors = None
        self._faceColors = None
    
        
    def __iter__(self):
        """Iterate over all faces, yielding a list of three tuples [(position, normal, color), ...] for each face."""
        vnorms = self.vertexNormals()
        vcolors = self.vertexColors()
        for i in range(self._faces.shape[0]):
            face = []
            for j in [0,1,2]:
                vind = self._faces[i,j]
                pos = self._vertexes[vind]
                norm = vnorms[vind]
                if vcolors is None:
                    color = self._meshColor
                else:
                    color = vcolors[vind]
                face.append((pos, norm, color))
            yield face
    
    def __len__(self):
        return len(self._faces)
    
    def faces(self):
        """Return an array (N, 3) of vertex indexes, three per triangular face in the mesh."""
        return self._faces
        
    def vertexes(self, indexed=None):
        """Return an array (N,3) of the positions of vertexes in the mesh. 
        By default, each unique vertex appears only once in the array.
        If indexed is 'faces', then the array will instead contain three vertexes
        per face in the mesh (and a single vertex may appear more than once in the array)."""
        print "vertexes", self
        print self.faces().shape
        if indexed is None:
            return self._vertexes
        elif indexed == 'faces':
            return self._vertexes[self.faces().flatten()]
        else:
            raise Exception("Invalid indexing mode. Accepts: None, 'faces'")
        
        
    def faceNormals(self, indexed=None):
        """
        Computes and stores normal of each face.
        """
        
        if self._faceNormals is None:
            #self._faceNormals = np.empty(self._faces.shape, dtype=float)
            #for i in xrange(self._faces.shape[0]):
                #face = self._faces[i]
                ### compute face normal
                #pts = [self._vertexes[vind] for vind in face]
                #norm = np.cross(pts[1]-pts[0], pts[2]-pts[0])
                #mag = (norm**2).sum()**0.5
                #self._faceNormals[i] = norm / mag
            v = self.vertexes()[self.faces()]
            self._faceNormals = np.cross(v[:,1]-v[:,0], v[:,2]-v[:,0])
        
        if indexed is None:
            return self._faceNormals
        elif indexed == 'faces':
            norms = np.empty((self._faceNormals.shape[0], 3, 3))
            norms[:] = self._faceNormals[:,np.newaxis,:]
            return norms
        else:
            raise Exception("Invalid indexing mode. Accepts: None, 'faces'")
        
    
    def vertexNormals(self, indexed=None):
        """
        Return an array of normal vectors.
        By default, the array will be (N, 3) with one entry per unique vertex in the mesh.
        If indexed is 'faces', then the array will contain three normal vectors per face
        (and some vertexes may be repeated).
        """
        if self._vertexNormals is None:
            faceNorms = self.faceNormals()
            vertFaces = self.vertexFaces()
            self._vertexNormals = np.empty(self._vertexes.shape, dtype=float)
            for vindex in xrange(self._vertexes.shape[0]):
                norms = faceNorms[vertFaces[vindex]]  ## get all face normals
                norm = norms.sum(axis=0)       ## sum normals
                norm /= (norm**2).sum()**0.5  ## and re-normalize
                self._vertexNormals[vindex] = norm
                
        if indexed is None:
            return self._vertexNormals
        elif indexed == 'faces':
            return self._vertexNormals[self.faces().flatten()]
        else:
            raise Exception("Invalid indexing mode. Accepts: None, 'faces'")
        
    def vertexColors(self, indexed=None):
        if indexed is None:
            return self._vertexColors
        elif indexed == 'faces':
            return self._vertexColors[self.faces().flatten()]
        else:
            raise Exception("Invalid indexing mode. Accepts: None, 'faces'")
        
    def faceColors(self):
        return self._faceColors
        
    def edgeColors(self):
        return self._edgeColors
        
    def _setUnindexedFaces(self, faces):
        print "setUnindexed:", faces.shape
        verts = {}  ## used to remember the index of each vertex position
        self._faces = np.empty(faces.shape[:2], dtype=np.uint)
        self._vertexes = []
        self._vertexFaces = []
        self._faceNormals = None
        self._vertexNormals = None
        for i in xrange(faces.shape[0]):
            face = faces[i]
            inds = []
            for j in range(face.shape[0]):
                pt = face[j]
                pt2 = tuple([round(x*1e14) for x in pt])  ## quantize to be sure that nearly-identical points will be merged
                index = verts.get(pt2, None)
                if index is None:
                    #self._vertexes.append(QtGui.QVector3D(*pt))
                    self._vertexes.append(pt)
                    self._vertexFaces.append([])
                    index = len(self._vertexes)-1
                    verts[pt2] = index
                self._vertexFaces[index].append(i)  # keep track of which vertexes belong to which faces
                self._faces[i,j] = index
                #inds.append(index)
            #self._faces.append(tuple(inds))
        self._vertexes = np.array(self._vertexes, dtype=float)
    
    def _setIndexedFaces(self, faces, vertexes):
        self._vertexes = vertexes #[QtGui.QVector3D(*v) for v in vertexes]
        self._faces = faces.astype(np.uint)
        self._edges = None
        self._vertexFaces = None
        self._faceNormals = None
        self._vertexNormals = None

    def vertexFaces(self):
        """
        Return list mapping each vertex index to a list of face indexes that use the vertex.
        """
        if self._vertexFaces is None:
            self._vertexFaces = [None] * len(self._vertexes)
            for i in xrange(self._faces.shape[0]):
                face = self._faces[i]
                for ind in face:
                    if self._vertexFaces[ind] is None:
                        self._vertexFaces[ind] = []  ## need a unique/empty list to fill
                    self._vertexFaces[ind].append(i)
        return self._vertexFaces
        
    #def reverseNormals(self):
        #"""
        #Reverses the direction of all normal vectors.
        #"""
        #pass
        
    #def generateEdgesFromFaces(self):
        #"""
        #Generate a set of edges by listing all the edges of faces and removing any duplicates.
        #Useful for displaying wireframe meshes.
        #"""
        #pass
        
    def save(self):
        """Serialize this mesh to a string appropriate for disk storage"""
        import pickle
        names = ['_vertexes', '_edges', '_faces', '_vertexFaces', '_vertexNormals', '_faceNormals', '_vertexColors', '_edgeColors', '_faceColors', '_meshColor']
        state = {n:getattr(self, n) for n in names}
        return pickle.dumps(state)
        
    def restore(self, state):
        """Restore the state of a mesh previously saved using save()"""
        import pickle
        state = pickle.loads(state)
        for k in state:
            setattr(self, k, state[k])
        
        
        