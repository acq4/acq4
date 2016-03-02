from PyQt4 import QtCore, QtGui
from Device import Device
from acq4.util.Mutex import Mutex
import acq4.pyqtgraph as pg
import collections
import numpy as np

class OptomechDevice(object):
    """
    OptomechDevice is an extenstion to the Device class which manages coordinate system mapping between
    rigidly-connected optomechanical devices. For example: movable stages, changeable objective lenses, and
    the imaging/stimulation devices themselves are all considered optomechanical devices.
    
    These devices are organized hierarchically with each optionally having a parent device and multiple child
    devices. Each device defines its own coordinate transformation which maps from its own local coordinate system
    into its parent's coordinate system.
    
    This organization makes it simple to map coordinates between devices and the global coordinate system. 
    This allows, for example, asking what is the physical location corresponding to a specific pixel in a
    camera image or asking what set of mirror voltages to use in order to stimulate a specific
    physical location.
    
    In most cases, the transformation will be in the form of an affine matrix multiplication.
    Devices are free, however, to define an arbitrary transformation as well.
    
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
    
    ## these signals are proxied from the OptomechDevice object
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
            ## Emitted when this device changes its current subdevice
        sigGlobalSubdeviceChanged = QtCore.Signal(object, object, object, object) ## self, dev, new subdev, old subdev
            ## Emitted when this device or any (grand)parent changes its current subdevice
    
        sigSubdeviceListChanged = QtCore.Signal(object) ## self
            ## Emitted when this device changes its list of available subdevices
        sigGlobalSubdeviceListChanged = QtCore.Signal(object, object) ## self, dev
            ## Emitted when this device or any (grand)parent changes its list of available subdevices
    
    def __init__(self, dm, config, name):
        object.__init__(self)
        
        ## create proxy object and wrap in its signals
        self.__sigProxy = OptomechDevice.SignalProxyObject()
        self.sigTransformChanged = self.__sigProxy.sigTransformChanged
        self.sigGlobalTransformChanged = self.__sigProxy.sigGlobalTransformChanged
        self.sigSubdeviceTransformChanged = self.__sigProxy.sigSubdeviceTransformChanged
        self.sigGlobalSubdeviceTransformChanged = self.__sigProxy.sigGlobalSubdeviceTransformChanged
        self.sigSubdeviceChanged = self.__sigProxy.sigSubdeviceChanged
        self.sigGlobalSubdeviceChanged = self.__sigProxy.sigGlobalSubdeviceChanged
        self.sigSubdeviceListChanged = self.__sigProxy.sigSubdeviceListChanged
        self.sigGlobalSubdeviceListChanged = self.__sigProxy.sigGlobalSubdeviceListChanged
        
        self.__devManager = dm
        self.__config = config
        self.__children = []
        self.__parent = None
        self.__globalTransform = 0  ## 0 indicates the cache is invalid. None indicates the transform is non-affine.
        self.__inverseGlobalTransform = 0
        self.__transform = pg.SRTTransform3D()
        self.__inverseTransform = 0
        self.__lock = Mutex(recursive=True)
        self.__subdevices = collections.OrderedDict()
        self.__subdevice = None
        self.__name = name
        
        self.sigTransformChanged.connect(self.__emitGlobalTransformChanged)
        self.sigSubdeviceTransformChanged.connect(self.__emitGlobalSubdeviceTransformChanged)
        self.sigSubdeviceChanged.connect(self.__emitGlobalSubdeviceChanged)
        self.sigSubdeviceListChanged.connect(self.__emitGlobalSubdeviceListChanged)
        if config is not None:
            if 'parentDevice' in config:
                try:
                    self.setParentDevice(config['parentDevice'])
                except Exception as ex:
                    if "No device named" in ex.message:
                        print "Cannot set parent device %s; no device by that name." % config['parentDevice']
                    else:
                        raise
            if 'transform' in config:
                self.setDeviceTransform(config['transform'])
            
    def implements(self, interface=None):
        ints = ['OptomechDevice']
        if interface is None:
            return ints
        return interface in ints
            
            
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
                self.__parent.sigGlobalSubdeviceListChanged.disconnect(self.__parentSubdeviceListChanged)
            if isinstance(parent, basestring):
                parent = self.__devManager.getDevice(parent)
            
            parent.sigGlobalTransformChanged.connect(self.__parentDeviceTransformChanged)
            parent.sigGlobalSubdeviceTransformChanged.connect(self.__parentSubdeviceTransformChanged)
            parent.sigGlobalSubdeviceChanged.connect(self.__parentSubdeviceChanged)
            parent.sigGlobalSubdeviceListChanged.connect(self.__parentSubdeviceListChanged)
            self.__parent = parent
        
    def mapToParentDevice(self, obj, subdev=None):
        """Map from local coordinates to the parent device (or to global if there is no parent)"""
        with self.__lock:
            tr = self.deviceTransform(subdev)
            if tr is None:
                raise Exception('Cannot map--device classes with no affine transform must override map methods.')
            return self._mapTransform(obj, tr)
    
    def mapToGlobal(self, obj, subdev=None):
        """Map *obj* from local coordinates to global."""
        with self.__lock:
            tr = self.globalTransform(subdev)
            if tr is not None:
                return self._mapTransform(obj, tr)
            
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
            return self._mapTransform(obj, tr)
    
    def mapFromGlobal(self, obj, subdev=None):
        """Map *obj* from global to local coordinates."""
        with self.__lock:
            tr = self.inverseGlobalTransform(subdev)
            if tr is not None:
                return self._mapTransform(obj, tr)
        
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
    
    def mapGlobalToParent(self, obj, subdev=None):
        """Map *obj* from global coordinates to the parent device coordinates.
        If this device has no parent, then *obj* is returned unchanged.
        """
        with self.__lock:
            if self.parentDevice() is None:
                return obj
            else:
                return self.parentDevice().mapFromGlobal(obj, subdev)
            
    def mapParentToGlobal(self, obj, subdev=None):
        """Map *obj* from parent device coordinates to global coordinates.
        If this device has no parent, then *obj* is returned unchanged.
        """
        with self.__lock:
            if self.parentDevice() is None:
                return obj
            else:
                return self.parentDevice().mapToGlobal(obj, subdev)
        
    def _mapTransform(self, obj, tr):
        # convert to a type that can be mapped
        retType = None
        if isinstance(obj, (tuple, list)):
            retType = type(obj)
            if np.isscalar(obj[0]):
                if len(obj) == 2:
                    obj = QtCore.QPointF(*obj)
                elif len(obj) == 3:
                    obj = QtGui.QVector3D(*obj)
                else:
                    raise TypeError("Cannot map %s of length %d." % (type(obj).__name__, len(obj)))
            elif isinstance(obj[0], np.ndarray):
                obj = np.concatenate([x[np.newaxis, ...] for x in obj])
            else:
                raise Exception ('Cannot map--object of type %s ' % str(type(obj[0])))

        if isinstance(obj, QtCore.QPointF):
            ret = tr.map(obj)
            if retType is not None:
                return retType([ret.x(), ret.y()])
            return ret
        elif isinstance(obj, QtGui.QVector3D):
            ret = tr.map(obj)
            if retType is not None:
                return retType([ret.x(), ret.y(), ret.z()])
            return ret

        elif isinstance(obj, np.ndarray):
            # m = np.array(tr.copyDataTo()).reshape(4,4)
            # m1 = m[:2,:2, np.newaxis]
            # obj = obj[np.newaxis,...]
            # m2 = (m1*obj).sum(axis=0)
            # m2 += m[:2,3,np.newaxis]
            m2 = pg.transformCoordinates(tr, obj)
            return m2
        else:
            raise Exception('Cannot map--object of type %s ' % str(type(obj))) 
    
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
            self.__transform = pg.SRTTransform3D(tr)
            self.invalidateCachedTransforms()
        #print "setDeviceTransform", self
        #print "   -> emit sigTransformChanged"
        #import traceback
        #traceback.print_stack()
        
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
            #dev = self.getSubdevice(subdev)
            if subdev is None: ## return cached transform
                if self.__globalTransform == 0:
                    self.__globalTransform = self.__computeGlobalTransform()
                return QtGui.QMatrix4x4(self.__globalTransform)
            else:
                return self.__computeGlobalTransform(subdev)
                
    def __computeGlobalTransform(self, subdev=None, inverse=False):
        ## subdev must be a dict
        with self.__lock:
            devices = self.parentDevices()
            transform = pg.SRTTransform3D()
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
            #dev = self.getSubdevice(subdev)
            if subdev is None: ## return cached transform
                if self.__inverseGlobalTransform == 0:
                    tr = self.globalTransform()
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
    
    def __emitGlobalSubdeviceTransformChanged(self, sender, subdev):
        #print "emit sigGlobalSubdeviceTransformChanged", sender, self, subdev
        self.sigGlobalSubdeviceTransformChanged.emit(self, self, subdev)
    
    def __emitGlobalSubdeviceChanged(self, sender, newDev, oldDev):
        self.sigGlobalSubdeviceChanged.emit(self, self, newDev, oldDev)
    
    def __emitGlobalSubdeviceListChanged(self, device):
        self.sigGlobalSubdeviceListChanged.emit(self, device)
    
    def __parentDeviceTransformChanged(self, sender, changed):
        ## called when any (grand)parent's transform has changed.
        prof = pg.debug.Profiler(disabled=True)
        self.invalidateCachedTransforms()
        self.sigGlobalTransformChanged.emit(self, changed)
        
    def __parentSubdeviceTransformChanged(self, sender, parent, subdev):
        ## called when any (grand)parent's subdevice transform has changed.
        self.invalidateCachedTransforms()
        self.sigGlobalSubdeviceTransformChanged.emit(self, parent, subdev)
        
    def __parentSubdeviceChanged(self, sender, parent, newDev, oldDev):
        ## called when any (grand)parent's current subdevice has changed.
        self.invalidateCachedTransforms()
        self.sigGlobalSubdeviceChanged.emit(self, parent, newDev, oldDev)
        
    def __parentSubdeviceListChanged(self, sender, device):
        ## called when any (grand)parent's subdevice list has changed.
        self.sigGlobalSubdeviceListChanged.emit(self, device)
        
    def parentDevices(self):
        """
        Return a list of this device and its parent devices in hierarchical order:
        [self, parent, grandparent, ...]
        """
        parents = [self]
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

            
    def addSubdevice(self, subdev):
        subdev.setParentDevice(self)
        self.invalidateCachedTransforms()
        subdev.sigTransformChanged.connect(self.__subdeviceTransformChanged)
        with self.__lock:
            self.__subdevices[subdev.name()] = subdev
            if self.__subdevice is None:
                self.setCurrentSubdevice(subdev)
        self.sigSubdeviceListChanged.emit(self)
    
    def removeSubdevice(self, subdev):
        self.invalidateCachedTransforms()
        subdev = self.getSubdevice(subdev)
        subdev.sigTransformChanged.disconnect(self.__subdeviceTransformChanged)
        with self.__lock:
            del self.__subdevices[subdev.name()]
            if len(self.__subdevices) == 0:
                self.setCurrentSubdevice(None)
        self.sigSubdeviceListChanged.emit(self)
    
    def listSubdevices(self):
        with self.__lock:
            return self.__subdevices.values()

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
            elif hasattr(dev, 'implements') and dev.implements('OptomechDevice'):
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
            dev = self.__subdevice
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
                self.__subdevice = dev
        self.sigSubdeviceChanged.emit(self, dev, oldDev)
        self.sigTransformChanged.emit(self)
        
    def treeSubdeviceState(self):
        """return a dict of {devName: subdevName} pairs indicating the currently
        selected subdevices throughout the tree."""
        devices = [self] + self.parentDevices()
        #print 'OptomechDevice.treeSubdeviceState(), devices:', devices
        subdevs = collections.OrderedDict()
        for dev in devices:
            subdev = dev.getSubdevice()
            #print "    ", dev, subdev
            if subdev is not None:
                subdevs[dev.name()] = subdev.name()
        return subdevs

    def listTreeSubdevices(self):
        """return a dict of {device: [subdev1, ...]} pairs listing
        all available subdevices in the tree."""
        devices = [self] + self.parentDevices()
        subdevs = collections.OrderedDict()
        for dev in devices:
            subdev = dev.listSubdevices()
            if len(subdev) > 0:
                subdevs[dev] = subdev
        return subdevs
        
    def __subdeviceTransformChanged(self, subdev):
        #print "Subdevice transform changed", self, subdev
        #print "   -> emit sigSubdeviceTransformChanged"
        self.invalidateCachedTransforms()
        self.sigTransformChanged.emit(self)
        self.sigSubdeviceTransformChanged.emit(self, subdev)
        
    def getDeviceStateKey(self):
        """
        Return a tuple that uniquely identifies the state of all subdevice selections in the system.
        This may be used as a key for storing/retrieving calibration data.
        """
        state = self.treeSubdeviceState()
        devs = state.keys()
        devs.sort()
        return tuple([dev + "__" + state[dev] for dev in devs])
        
        
class DeviceTreeItemGroup(pg.ItemGroup):
    """
    Extension of QGraphicsItemGroup that maintains a hierarchy of item groups
    with transforms taken from their associated devices.
    
    This makes it simpler to display graphics that are automatically positioned and scaled relative to 
    devices.
    
    
    """
    
    def __init__(self, device, includeSubdevices=True):
        """
        *item* must be a OptomechDevice instance. For the device and each
        of its (grand)parent devices, at least one item group
        will be created which automatically tracks the transform 
        of its device. By default, any devices which have subdevices
        will have one item group per subdevice.
        """
        pg.ItemGroup.__init__(self)
        self.groups = {}  ## {device: {subdevice: items}}
        self.device = device
        self.includeSubdevs = includeSubdevices
        self.topItem = None
        
        device.sigGlobalTransformChanged.connect(self.transformChanged)
        device.sigGlobalSubdeviceTransformChanged.connect(self.subdevTransformChanged)
        device.sigGlobalSubdeviceChanged.connect(self.subdevChanged)
        device.sigGlobalSubdeviceListChanged.connect(self.subdevListChanged)
        self.rebuildGroups()
        
    def makeGroup(self, dev, subdev):
        """Construct a QGraphicsItemGroup for the specified device/subdevice.
        This is a good method to extend in subclasses."""
        newGroup = QtGui.QGraphicsItemGroup()
        newGroup.setTransform(pg.SRTTransform(dev.deviceTransform(subdev)))
        return newGroup
        
        
        
    def transformChanged(self, sender, device):
        for subdev, items in self.groups[device].iteritems():
            tr = pg.SRTTransform(device.deviceTransform(subdev))
            for item in items:
                item.setTransform(tr)
        
        
    def subdevTransformChanged(self, sender, device, subdev):
        tr = pg.SRTTransform(device.deviceTransform(subdev))
        #print "subdevTransformChanged:", sender, device, subdev
        for item in self.groups[device][subdev]:
            item.setTransform(tr)

    def subdevChanged(self, sender, device, newSubdev, oldSubdev):
        pass
            
    def subdevListChanged(self, sender, device):
        self.rebuildGroups()
    
    
    #def removeGroups(self, device, subdev, parentGroup=None):
        #rem = []
        #for group in self.groups[device][subdev]:
            #if parentGroup is None or group.parentItem() is parentGroup:
                #rem.append(group)
                #for child in device.childDevices():
                    #if child in self.groups:
                        #self.removeGroups(child, subdev=None, parentGroup=group)
        #for group in rem:
            #self.groups[device][subdev].remove(group)
            #scene = group.scene()
            #if scene is not None:
                #scene.removeItem(group)
    
    def rebuildGroups(self):
        """Create the tree of graphics items needed to display camera boundaries"""
        if self.topItem is not None:
            scene = self.topItem.scene()
            if scene is not None:
                scene.removeItem(self.topItem)
                self.topItem = None
        self.groups = {}
        
        devices = self.device.parentDevices()
        parentItems = [self]
        for dev in devices[::-1]:
            self.groups[dev] = {}
            subdevs = dev.listSubdevices()
            if len(subdevs) == 0:
                subdevs = [None]
            newItems = []
            for subdev in subdevs:
                ## create one new group per parent group
                self.groups[dev][subdev] = []
                
                for parent in parentItems:
                    newGroup = self.makeGroup(dev, subdev)
                    self.groups[dev][subdev].append(newGroup)
                    newItems.append(newGroup)
                    newGroup.setParentItem(parent)
                    if parent is self:
                        self.topItem = newGroup
                    
            parentItems = newItems
            
    def getGroups(self, device):
        """Return a list of all item groups for the given device"""
        groups = []
        for subdev, items in self.groups[device].iteritems():
            groups.extend(items)
        return groups
    

        
