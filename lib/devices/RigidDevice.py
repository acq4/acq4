from PyQt4 import QtCore, QtGui
from Device import Device
from Mutex import Mutex
from pyqtgraph import Transform3D

class RigidDevice(Device):
    """
    Rigid devices are devices which affect the mapping between an imaging/stimulation device 
    and the global coordinate system. For example: movable stages, changeable objective lenses, and
    the imaging/stimulation devices themselves are all considered rigid devices.
    
    These devices are organized hierarchically with each optionally having a parent device and multiple child
    devices. Each device defines its own coordinate transformation which maps from its own local coordinate system
    into its parent's coordinate system.
    
    This organization makes it simple to map coordinates between devices and the global coordinate system. 
    This allows, for example, asking what is the physical location corresponding to a specific pixel in a 
    camera image or asking what set of mirror voltages to use in order to stimulate a specific
    physical location.
    
    In most cases, the transformation will be in the form of an affine matrix multiplication.
    Devices are free, however, to define a non-affine transformation as well.
    
    """
    
    sigTransformChanged = QtCore.Signal(object)        # emitted when this device's transform changes
    sigGlobalTransformChanged = QtCore.Signal(object)  # emitted when the transform for this device or any of its parents changes
    
    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)
        self.sigTransformChanged.connect(self.sigGlobalTransformChanged)
        self.__children = []
        self.__parent = None
        self.__globalTransform = 0  ## 0 indicates the cache is invalid. None indicates the transform is non-affine.
        self.__inverseGlobalTransform = 0
        self.__transform = Transform3D()
        self.__inverseTransform = 0
        self.__lock = Mutex(recursive=True)
        if 'parentDevice' in config:
            self.setParentDevice(config['parentDevice'])
        if 'transform' in config:
            self.setDeviceTransform(config['transform'])
            
    def parentDevice(self):
        """Return this device's parent, or None if there is no parent."""
        with self.__lock:
            return self.__parent
            
    def setParentDevice(self, parent):
        with self.__lock:
            if self.__parent is not None:
                self.__parent.sigGlobalTransformChanged.disconnect(self.parentDeviceTransformChanged)
            if isinstance(parent, basestring):
                parent = self.dm.getDevice(parent)
            
            parent.sigGlobalTransformChanged.connect(self.parentDeviceTransformChanged)
            self.__parent = parent
        
    def mapToParentDevice(self, obj):
        """Map from local coordinates to the parent device (or to global if there is no parent)"""
        with self.__lock:
            tr = self.deviceTransform()
            if tr is None:
                raise Exception('Cannot map--device classes with no affine transform must override map methods.')
            return tr.map(obj)
    
    def mapToGlobal(self, obj):
        """Map *obj* from local coordinates to global."""
        with self.__lock:
            tr = self.globalTransform()
            if tr is not None:
                return tr.map(obj)
            
            ## If our transformation is nonlinear, then the local mapping step must be done separately.
            o2 = self.mapToParentDevice(obj)
            parent = self.parentDevice()
            if parent is None:
                return o2
            else:
                return parent.mapToGlobal(o2)
    
    def mapToDevice(self, device, obj):
        """Map *obj* from local coordinates to *device*'s coordinate system."""
        with self.__lock:
            return device.mapFromGlobal(self.mapToGlobal(obj))
    
    def mapFromParentDevice(self, obj):
        """Map *obj* from parent coordinates (or from global if there is no parent) to local coordinates."""
        with self.__lock:
            tr = self.inverseDeviceTransform()
            if tr is None:
                raise Exception('Cannot map--device classes with no affine transform must override map methods.')
            return tr.map(obj)
    
    def mapFromGlobal(self, obj):
        """Map *obj* from global to local coordinates."""
        with self.__lock:
            tr = self.inverseGlobalTransform()
            if tr is not None:
                return tr.map(obj)
        
            ## If our transformation is nonlinear, then the local mapping step must be done separately.
            parent = self.parentDevice()
            if parent is None:
                obj = parent.mapFromGlobal(obj)
            return self.mapFromParent(obj)
    
    def mapFromDevice(self, device, obj):
        """Map *obj* from the coordinate system of the specified *device* to local coordiantes."""
        with self.__lock:
            return self.mapFromGlobal(device.mapToGlobal(obj))
    
    def deviceTransform(self):
        """
        Return this device's affine transformation matrix. 
        This matrix maps from the device's local coordinate system to the parent device's coordinate system
        (or to the global coordinate system, if there is no parent device)
        If no such matrix exists, return None instead. (this indicates that the device's 
        transformation is non-affine, and thus the mapTo/mapFrom methods must be used instead.)
        """
        with self.__lock:
            return self.__transform
    
    def inverseDeviceTransform(self):
        with self.__lock:
            if self.__inverseTransform == 0:
                tr = self.transform()
                if tr is None:
                    self.__inverseTransform = None
                else:
                    inv, invertible = tr.inverted()
                    if not invertible:
                        raise Exception("Transform is not invertible.")
                    self.__inverseTransform = inv
            return self.__inverseTransform
    
    def setDeviceTransform(self, tr):
        with self.__lock:
            self.__transform = Transform3D(tr)
            self.invalidateCachedTransforms()
            self.sigTransformChanged.emit(self)

    def globalTransform(self):
        """
        Return the transform mapping from local device coordinates to global coordinates.
        If the resulting transform is non-affine, then None is returned and the mapTo/mapFrom
        methods must be used instead.
        """
        with self.__lock:
            if self.__globalTransform == 0:
                devices = [self] + self.parentDevices()
                transform = Transform3D()
                for d in devices:
                    tr = d.deviceTransform()
                    if tr is None:
                        self.__globalTransform = None
                        return None
                    transform = tr * transform
                self.__globalTransform = tr
            return self.__globalTransform

    def inverseGlobalTransform(self):
        with self.__lock:
            if self.__inverseGlobalTransform == 0:
                tr = self.globalTransform()
                if tr is None:
                    self.__inverseGlobalTransform = None
                else:
                    inv, invertible = tr.inverted()
                    if not invertible:
                        raise Exception("Transform is not invertible.")
                    self.__inverseGlobalTransform = inv
            return self.__inverseGlobalTransform
    
    def parentDevices(self):
        """
        Return a list of parent devices in hierarchical order:
        [parent, grandparent, ...]
        """
        parents = []
        p = self
        while True:
            p = p.parentDevice()
            if p is None:
                break
            parents.append(p)
        return parents

    def parentDeviceTransformChanged(self, p):
        ## called when any (grand)parent's transform has changed.
        self.invalidateCachedTransforms()
        self.sigGlobalTransformChanged.emit(self)

    def invalidateCachedTransforms(self):
        with self.__lock:
            self.__inverseTransform = 0
            self.__globalTransform = 0
            self.__inverseGlobalTransform = 0

        