.. _devModulesCamera:

Camera Module
=============

The Camera module (``acq4/modules/Camera/``) provides a shared visual workspace for imaging devices and other modules that need to display or interact with data in a global coordinate space.


Architecture
------------

* **Camera** (``Camera.py``) — Thin ``Module`` subclass. Creates the ``CameraWindow`` and exposes it via ``window()``.
* **CameraWindow** (``CameraWindow.py``) — The main ``QMainWindow``. Hosts a ``pyqtgraph.ViewBox`` as the primary display area, a dock area for device-specific control panels, a depth plot, an ROI plotter, and an image sequencer.

At startup, ``CameraWindow`` iterates over all known devices and calls ``dev.cameraModuleInterface(self)`` on each one. Devices that return a non-``None`` interface are automatically added to the module.


CameraModuleInterface plugin API
---------------------------------

Any device driver can integrate with the Camera module by implementing a ``cameraModuleInterface(mod)`` method that returns a subclass of ``CameraModuleInterface``::

    from acq4.modules.Camera.CameraWindow import CameraModuleInterface

    class MyDeviceCameraInterface(CameraModuleInterface):
        canImage = True  # set False for non-imaging overlays

        def graphicsItems(self):
            """Return a list of GraphicsItems to display in the Camera ViewBox."""
            return [self._imageItem]

        def controlWidget(self):
            """Return a QWidget to dock in the camera window, or None."""
            return self._controlWidget

        def boundingRect(self):
            """Return the bounding QRectF of all displayed items."""
            return self._imageItem.boundingRect()

        def getImageItem(self):
            """Return the primary ImageItem, or None."""
            return self._imageItem

        def takeImage(self, closeShutter=None):
            """Acquire a single frame from the device."""
            ...

The interface object may optionally emit:

* ``sigNewFrame(iface, frame)`` — Emitted when a new frame arrives. The Camera module uses this to update cursor readout and trigger ROI plot updates.
* ``sigTransformChanged(iface)`` — Emitted when the device's coordinate transform changes (e.g., objective or stage change). The Camera module uses this to update item positions.

Graphics items returned by ``graphicsItems()`` are added directly to the Camera module's ``ViewBox``, placing them in the global coordinate space. Items should use real-world units (meters) for their coordinate system.


Coordinate system
-----------------

The Camera module's ``ViewBox`` uses the global stage coordinate system: x and y are in meters, with the convention established by the microscope and stage devices. Devices that supply images (cameras, laser scanners) apply a ``QTransform`` to their ``ImageItem`` to map pixel coordinates to global space. This transform is updated whenever the stage moves or the objective changes, keeping all displayed objects registered to each other.


Adding items from other modules
--------------------------------

Other modules may add graphics items to the Camera module's view by obtaining a reference to the Camera module and calling ``getView()``::

    camMod = manager.getModule('Camera')
    view = camMod.window().getView()
    view.addItem(myItem)

Items added this way participate in the shared coordinate space and are subject to the same zoom and pan controls as camera imagery. They should be removed explicitly when no longer needed::

    view.removeItem(myItem)


Depth plot
----------

The Camera window contains a depth plot (``CameraWindow.depthPlot``) that can be used to display depth-related information alongside the camera image. The plot's left axis is labeled in meters and covers the focal range of the objective.


ROI plotter
-----------

The **ROI Plot** dock allows users to draw regions of interest on the camera image and monitor intensity over time. The ``ROIPlotter`` widget handles ROI drawing, frame accumulation, and plotting. It connects to the active imaging interface's ``sigNewFrame`` signal to update the plot as frames arrive.


Image sequencer
---------------

The **Image Sequencer** dock (``acq4/util/imaging/sequencer.py``) provides controls for automated image sequences such as z-stacks, timelapse series, and mosaics. It is hosted in the Camera module window but operates independently of the specific imaging device.
