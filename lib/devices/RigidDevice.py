from PyQt4 import QtCore, QtGui
from Device import Device
from Mutex import Mutex
from pyqtgraph import Transform3D
import collections

class RigidDevice(object):
    """
    Rigid devices are extenstions to devices which affect the mapping between an imaging/stimulation device 
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
    
    Devices may also have selectable sub-devices, providing a set of interchangeable transforms.
    For example, a microscope with multiple objectives may define one sub-device per objective.
    This does not affect the hierarchy of devices, but instead simply affects the way the microscope
    device reports its transformation. Furthermore, it is recommended to use information about the currently 
    selected set of subdevices when storing and loading device calibration data (for example,
    a scanner device may store one calibration per objective).
    
    Example device hierarchy:
    
            [Motorized Stage]
                 |
         [Microscope focus drive]
                 |
         [Microscope objectives] ---- subdevices: [ 5x objective ], [ 63x objective ]
          |       |       |
       [Camera]   |    [Laser] (per-objective power calibration)
                  |
            [Scan Mirrors] 
             (per-objective voltage calibration)
    """
    
    ## these signals are proxied from the RigidDevice object
    ## we do this to avoid QObject double-inheritance issues.
    class SignalProxyObject(QtCore.QObject):
        sigTransformChanged = QtCore.Signal(object)        # self
            ## emitted when this device's transform changes
        sigGlobalTransformChanged = QtCore.Signal(object, object)  # self, changed device
            ## emitted when the transform for this device or any of its parents changes
            
        sigSubdeviceTransformChanged = QtCore.Signal(object, object)  ## self, subdev
            ## Emitted when the transform of a subdevice has changed
        sigGlobalSubdeviceTransformChanged = QtCore.Signal(object, object, object)  # self, dev, subdev
            ## Emitted when the transform of a subdevice or any (grand)parent's subdevice has changed
            
        sigSubdeviceChanged = QtCore.Signal(object, object, object) ## self, new subdev, old subdev
            ## Emitted when this device changes its subdevice
        sigGlobalSubdeviceChanged = QtCore.Signal(object, object, object, object) ## self, dev, new subdev, old subdev
            ## Emitted when this device or any (grand)parent changes its subdevice
    
    def __init__(self, dm, config, name):
        object.__init__(self)
        
        ## create proxy object and wrap in its signals
        self.__sigProxy = RigidDevice.SignalProxyObject()
        self.sigTransformChanged = self.__sigProxy.sigTransformChanged
        self.sigGlobalTransformChanged = self.__sigProxy.sigGlobalTransformChanged
        self.sigSubdeviceTransformChanged = self.__sigProxy.sigSubdeviceTransformChanged
        self.sigGlobalSubdeviceTransformChanged = self.__sigProxy.sigGlobalSubdeviceTransformChanged
        self.sigSubdeviceChanged = self.__sigProxy.sigSubdeviceChanged
        self.sigGlobalSubdeviceChanged = self.__sigProxy.sigGlobalSubdeviceChanged
        
        self.__devManager = dm
        self.__config = config
        self.__children = []
        self.__parent = None
        self.__globalTransform = 0  ## 0 indicates the cache is invalid. None indicates the transform is non-affine.
        self.__inverseGlobalTransform = 0
        self.__transform = Transform3D()
        self.__inverseTransform = 0
        self.__lock = Mutex(recursive=True)
        self.__subdevices = collections.OrderedDict()
        self.__subdevice = None
        self.__name = name
        
        
        self.sigTransformChanged.connect(self.__emitGlobalTransformChanged)
        self.sigSubdeviceTransformChanged.connect(self.__emitGlobalSubdeviceTransformChanged)
        self.sigSubdeviceChanged.connect(self.__emitGlobalSubdeviceChanged)
        if 'parentDevice' in config:
            self.setParentDevice(config['parentDevice'])
        if 'transform' in config:
            self.setDeviceTransform(config['transform'])
            
    def name(self):
        return self.__name
            
    def parentDevice(self):
        """Return this device's parent, or None if there is no parent."""
        with self.__lock:
            return self.__parent
            
    def setParentDevice(self, parent):
        with self.__lock:
            if self.__parent is not None:
                self.__parent.sigGlobalTransformChanged.disconnect(self.__parentDeviceTransformChanged)
                self.__parent.sigGlobalSubdeviceTransformChanged.disconnect(self.__parentSubdeviceTransformChanged)
                self.__parent.sigGlobalSubdeviceChanged.disconnect(self.__parentSubdeviceChanged)
            if isinstance(parent, basestring):
                parent = self.__devManager.getDevice(parent)
            
            parent.sigGlobalTransformChanged.connect(self.__parentDeviceTransformChanged)
            parent.sigGlobalSubdeviceTransformChanged.connect(self.__parentSubdeviceTransformChanged)
            parent.sigGlobalSubdeviceChanged.connect(self.__parentSubdeviceChanged)
            self.__parent = parent
        
    def mapToParentDevice(self, obj, subdev=None):
        """Map from local coordinates to the parent device (or to global if there is no parent)"""
        with self.__lock:
            tr = self.deviceTransform(subdev)
            if tr is None:
                raise Exception('Cannot map--device classes with no affine transform must override map methods.')
            return tr.map(obj)
    
    def mapToGlobal(self, obj, subdev=None):
        """Map *obj* from local coordinates to global."""
        with self.__lock:
            tr = self.globalTransform(subdev)
            if tr is not None:
                return tr.map(obj)
            
            ## If our transformation is nonlinear, then the local mapping step must be done separately.
            subdev = self._subdevDict(subdev)
            o2 = self.mapToParentDevice(obj, subdev)
            parent = self.parentDevice()
            if parent is None:
                return o2
            else:
                return parent.mapToGlobal(o2, subdev)
    
    def mapToDevice(self, device, obj, subdev=None):
        """Map *obj* from local coordinates to *device*'s coordinate system."""
        with self.__lock:
            subdev = self._subdevDict(subdev)
            return device.mapFromGlobal(self.mapToGlobal(obj, subdev), subdev)
    
    def mapFromParentDevice(self, obj, subdev=None):
        """Map *obj* from parent coordinates (or from global if there is no parent) to local coordinates."""
        with self.__lock:
            tr = self.inverseDeviceTransform(subdev)
            if tr is None:
                raise Exception('Cannot map--device classes with no affine transform must override map methods.')
            return tr.map(obj)
    
    def mapFromGlobal(self, obj, subdev=None):
        """Map *obj* from global to local coordinates."""
        with self.__lock:
            tr = self.inverseGlobalTransform(subdev)
            if tr is not None:
                return tr.map(obj)
        
            ## If our transformation is nonlinear, then the local mapping step must be done separately.
            subdev = self._subdevDict(subdev)
            parent = self.parentDevice()
            if parent is None:
                obj = parent.mapFromGlobal(obj, subdev)
            return self.mapFromParent(obj, subdev)
    
    def mapFromDevice(self, device, obj, subdev=None):
        """Map *obj* from the coordinate system of the specified *device* to local coordiantes."""
        with self.__lock:
            subdev = self._subdevDict(subdev)
            return self.mapFromGlobal(device.mapToGlobal(obj, subdev), subdev)
    
    def deviceTransform(self, subdev=None):
        """
        Return this device's affine transformation matrix. 
        This matrix maps from the device's local coordinate system to the parent device's coordinate system
        (or to the global coordinate system, if there is no parent device)
        If no such matrix exists, return None instead. (this indicates that the device's 
        transformation is non-affine, and thus the mapTo/mapFrom methods must be used instead.)
        
        If the device has sub-devices, then this function will account for the current
        sub-device when computing the transform.
        If *subdev* is given, then the transform is computed with that subdevice instead.
        *subdev* may be the name of the device or the device itself.
        """
        with self.__lock:
            tr = QtGui.QMatrix4x4(self.__transform)
            
            ## if a subdevice is specified, multiply by the subdevice's transform before returning
            dev = self.getSubdevice(subdev)
            if dev is None:
                return tr
            else:
                return tr * dev.deviceTransform()
                
    
    def inverseDeviceTransform(self, subdev=None):
        """
        See deviceTransform; this method returns the inverse.
        """
        with self.__lock:
            if self.__inverseTransform == 0:
                tr = QtGui.QMatrix4x4(self.__transform)
                if tr is None:
                    self.__inverseTransform = None
                else:
                    inv, invertible = tr.inverted()
                    if not invertible:
                        raise Exception("Transform is not invertible.")
                    self.__inverseTransform = inv
            tr = QtGui.QMatrix4x4(self.__inverseTransform)
            if subdev == 0:  ## indicates we should skip any subdevices
                return tr
            ## if a subdevice is specified, multiply by the subdevice's transform before returning
            dev = self.getSubdevice(subdev)
            if dev is None:
                return tr
            else:
                return dev.inverseDeviceTransform() * tr 
    
    def setDeviceTransform(self, tr):
        with self.__lock:
            self.__transform = Transform3D(tr)
            self.invalidateCachedTransforms()
        self.sigTransformChanged.emit(self)

    def globalTransform(self, subdev=None):
        """
        Return the transform mapping from local device coordinates to global coordinates.
        If the resulting transform is non-affine, then None is returned and the mapTo/mapFrom
        methods must be used instead.
        
        If *subdev* is given, it must be a dictionary of {deviceName: subdevice} or
        {deviceName: subdeviceName} pairs specifying the state to compute.
        """
        if subdev is None:
            subdev = {}
            
        with self.__lock:
            dev = self.getSubdevice(subdev)
            if dev is None or dev is self.__subdevice: ## return cached transform
                if self.__globalTransform == 0:
                    self.__globalTransform = self.__computeGlobalTransform(subdev)
                return QtGui.QMatrix4x4(self.__globalTransform)
            else:
                return self.__computeGlobalTransform(subdev)
                
    def __computeGlobalTransform(self, subdev=None, inverse=False):
        ## subdev must be a dict
        with self.__lock:
            devices = [self] + self.parentDevices()
            transform = Transform3D()
            for d in devices:
                tr = d.deviceTransform(subdev)
                if tr is None:
                    self.__globalTransform = None
                    return None
                transform = tr * transform
                
        if inverse:
            inv, invertible = transform.inverted()
            if not invertible:
                raise Exception("Transform is not invertible.")
            return inv
        else:
            return transform
        
    def inverseGlobalTransform(self, subdev=None):
        """
        See globalTransform; this method returns the inverse.
        """
        with self.__lock:
            dev = self.getSubdevice(subdev)
            if dev is None or dev is self.__subdevice: ## return cached transform
                if self.__inverseGlobalTransform == 0:
                    tr = self.globalTransform(subdev)
                    if tr is None:
                        self.__inverseGlobalTransform = None
                    else:
                        inv, invertible = tr.inverted()
                        if not invertible:
                            raise Exception("Transform is not invertible.")
                        self.__inverseGlobalTransform = inv
                return QtGui.QMatrix4x4(self.__inverseGlobalTransform)
            else:
                return self.__computeGlobalTransform(subdev, inverse=True)
    
    def __emitGlobalTransformChanged(self):
        self.sigGlobalTransformChanged.emit(self, self)
    
    def __emitGlobalSubdeviceTransformChanged(self, subdev):
        self.sigGlobalSubdeviceTransformChanged.emit(self, self, subdev)
    
    def __emitGlobalSubdeviceChanged(self, newDev, oldDev):
        self.sigGlobalSubdeviceChanged.emit(self, self, newDev, oldDev)
    
    def __parentDeviceTransformChanged(self, p):
        ## called when any (grand)parent's transform has changed.
        self.invalidateCachedTransforms()
        self.sigGlobalTransformChanged.emit(self, p)
        
    def __parentSubdeviceTransformChanged(self, parent, subdev):
        ## called when any (grand)parent's subdevice transform has changed.
        self.invalidateCachedTransforms()
        self.sigGlobalSubdeviceTransformChanged.emit(self, parent, subdev)
        
    def __parentSubdeviceChanged(self, parent, newDev, oldDev):
        ## called when any (grand)parent's current subdevice has changed.
        self.invalidateCachedTransforms()
        self.sigGlobalSubdeviceChanged.emit(self, parent, newDev, oldDev)
        
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

    def invalidateCachedTransforms(self):
        with self.__lock:
            self.__inverseTransform = 0
            self.__globalTransform = 0
            self.__inverseGlobalTransform = 0

            
    def addSubdevice(self, dev):
        dev.setParentDevice(self)
        self.invalidateCachedTransforms()
        dev.sigTransformChanged.connect(self.__subdeviceChanged)
        with self.__lock:
            self.__subdevices[dev.name()] = dev
            if self.__subdevice is None:
                self.setCurrentSubdevice(dev)
    
    def removeSubdevice(self, dev):
        self.invalidateCachedTransforms()
        dev = self.getSubdevice(dev)
        dev.sigTransformChanged.disconnect(self.__subdeviceChanged)
        with self.__lock:
            del self.__subdevices[dev.name()]
            if len(self.__subdevices) == 0:
                self.setCurrentSubdevice(None)
    
    def listSubdevices(self):
        with self.__lock:
            return self.__subdevices.keys()

    def getSubdevice(self, dev=None):
        """
        Return a subdevice.
        If *dev* is None return the current subdevice. (If there is no current subdevice, return None)
        If *dev* is a subdevice name, return the named device
        """
        with self.__lock:
            if isinstance(dev, dict):
                dev = dev.get(self.name(), None)
            
            if dev is None:
                dev = self.__subdevice
                
            if dev is None:
                return None
            elif isinstance(dev, RigidDevice):
                return dev
            elif isinstance(dev, basestring):
                return self.__subdevices[dev]
            else:
                raise Exception("Invalid argument: %s" % str(dev))
        
    def __subdevDict(self, dev):
        ## Convert a variety of argument types to a 
        ## dictionary {devName: subdevName}
        if isinstance(dev, dict):
            return dev
        if dev is None:
            dev = self.__subdevices.get(self.__subdevice, None)
            return {self.name(): dev}
        if isinstance(dev, basestring):
            return {self.name(): self.__subdevices[dev]}
            
    def setCurrentSubdevice(self, dev):
        self.invalidateCachedTransforms()
        with self.__lock:
            oldDev = self.__subdevice
            if dev is None:
                self.__subdevice = None
            else:
                dev = self.getSubdevice(dev)
                self.__subdevice = dev.name()
            self.sigSubdeviceChanged.emit(self, dev, oldDev)
        
    def listTreeSubdevices(self):
        """return a dict of {devName: subdevName} pairs indicating the currently
        selected subdevices throughout the tree."""
        devices = [self] + self.parentDevices()
        subdevs = collections.OrderedDict()
        for dev in devices:
            subdev = dev.getSubdevice()
            if subdev is not None:
                subdevs[dev.name()] = subdev.name()
        return subdevs
    
    def __subdeviceChanged(self, dev):
        self.invalidateCachedTransforms()
        self.sigTransformChanged.emit(self)
        self.sigSubdeviceTransformChanged.emit(self, dev)