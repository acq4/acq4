from moduleTemplate import Ui_Form
from PyQt4 import QtGui, QtCore
from acq4.modules.Camera import CameraModuleInterface
from acq4.util.imaging.imaging_ctrl import ImagingCtrl
import acq4.pyqtgraph as pg

class PVImagerModuleGui(QtGui.QWidget):
    """For controlling the module gui for PrairieViewImager"""
    def __init__(self):

        self.ui = Ui_Form()
        self.ui.setupUi(self)




class PVImagerCamModInterface(CameraModuleInterface):
    """For plugging PrairieView images into the camera module"""

    def __init__(self, dev, cameraModule):
        CameraModuleInterface.__init__(self, dev, cameraModule)
        # self.widget = PVImagerModuleGui()

        self.view = cameraModule.window().view

        self.imagingCtrl = ImagingCtrl()
        #self.frameDisplay = self.imagingCtrl.frameDisplay
        #self.imageItem = self.frameDisplay.imageItem()
        self.imageItem = pg.ImageItem()

        self.view.addItem(self.imageItem)

        # ## set up item groups
        # self.cameraItemGroup = pg.ItemGroup()  ## translated with scope, scaled with camera objective
        # self.imageItemGroup = pg.ItemGroup()   ## translated and scaled as each frame arrives
        # self.view.addItem(self.imageItemGroup)
        # self.view.addItem(self.cameraItemGroup)
        # self.cameraItemGroup.setZValue(0)
        # self.imageItemGroup.setZValue(-2)

        # ## video image item
        # self.imageItem = self.frameDisplay.imageItem()
        # self.view.addItem(self.imageItem)
        # self.imageItem.setParentItem(self.imageItemGroup)
        # self.imageItem.setZValue(-10)

        self.imagingCtrl.sigAcquireFrameClicked.connect(self.acquireFrameClicked)
        #self.frameDisplay.imageUpdated.connect(self.imageUpdated)



    def graphicsItems(self):
        """Return a list of all graphics items displayed by this interface.
        """
        raise NotImplementedError()

    def controlWidget(self):
        """Return a widget to be docked in the camera module window.

        May return None.
        """
        return None

    def boundingRect(self):
        """Return the bounding rectangle of all graphics items.
        """
        raise NotImplementedError()

    def getImageItem(self):
        """Return the ImageItem used to display imaging data from this device.

        May return None.
        """
        #return None
        return self.frameDisplay.imageItem()

    def takeImage(self, closeShutter=None):
        """Request the imaging device to acquire a single frame.

        The optional closeShutter argument is used to tell laser scanning devices whether
        to close their shutter after imaging. Cameras can simply ignore this option.
        """
        # Note: this is a bit kludgy. 
        # Would be nice to have a more natural way of handling this..
        #raise NotImplementedError(str(self))
        return self.getDevice().acquireFrames(1, stack=False)

    def acquireFrameClicked(self):
        frame = self.getDevice().acquireFrames(1, stack=False)
        #self.imagingCtrl.newFrame(frame)
        self.imageItem.setImage(frame.data())
        self.imageUpdated(frame)

    def imageUpdated(self, frame):
        ## according to ImagingCtrl docs we should set the image transform here
        #raise NotImplementedError()
        pass




# class ImagerCamModInterface(CameraModuleInterface):
#     """For plugging in the 2p imager system to the camera module.
#     """
#     def __init__(self, imager, mod):
#         self.imager = imager

#         CameraModuleInterface.__init__(self, imager, mod)

#         mod.window().addItem(imager.imageItem, z=10)

#         self.imager.imagingThread.sigNewFrame.connect(self.newFrame)

#     def graphicsItems(self):
#         gitems = [self.getImageItem()] + list(self.imager.objectiveROImap.values())
#         return gitems

#     def takeImage(self, closeShutter=True):
#         self.imager.imagingThread.takeFrame(closeShutter=closeShutter)

#     def getImageItem(self):
#         return self.imager.imageItem

#     def newFrame(self, frame):
#         self.sigNewFrame.emit(self, frame)
