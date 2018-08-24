from acq4.devices.OptomechDevice import OptomechDevice
from acq4.devices.Device import Device
from acq4.util.PrairieView import PrairieView
from acq4.util.imaging.frame import Frame
from PIL import Image
import os
from optoanalysis import xml_parse
from collections import OrderedDict
import os, time
import numpy as np
from PyQt4 import QtCore, QtGui
from ModuleInterfaces import PVImagerCamModInterface
from acq4.pyqtgraph import SRTTransform3D, Point
import deviceTemplate


class PrairieViewImager(OptomechDevice, Device):

    sigNewFrame = QtCore.Signal(object)

    def __init__(self, deviceManager, config, name):
        Device.__init__(self, deviceManager, config, name)
        OptomechDevice.__init__(self, deviceManager, config, name)

        ip = config.get('ipaddress', None)
        self.pv = PrairieView(ip)
        #self.pv.setSaveDirectory('C:/Megan/acq4_data')
        self._saveDirectory = os.path.abspath('C:/Megan/acq4_data') ## where we tell Prairie to save data
        self._imageDirectory = os.path.abspath('Z:/Megan/acq4_data') ## where we retrieve prairie's data from
        self._frameIDcounter = 0
        self.scale = 1e-6

    def setup(self):
        self.pv.setSaveDirectory(self._saveDirectory)

    def deviceTransform(self, subdev=None):
        return SRTTransform3D(OptomechDevice.deviceTransform(self, subdev))
        

    def acquireFrames(self, n=1, stack=True):
        """Immediately acquire and return a specific number of frames.

        This method blocks until all frames are acquired and may not be supported by all camera
        types.

        All frames are returned stacked within a single Frame instance, as a 3D or 4D array.

        If *stack* is False, then the first axis is dropped and the resulting data will instead be
        2D or 3D.
        """

        ### Have pv acquire a frame, grab it, display it.

        if n > 1:
            raise Exception("%s can only acquire one frame at a time." % self.name())

        imageBaseName = "ACQ4_image"
        imageID = self._frameIDcounter
        self._frameIDcounter += 1

        self.pv.saveImage(imageBaseName, imageID)


        imageName = imageBaseName+'-%03d'%imageID
        imagePath = os.path.join(self._imageDirectory, imageName)
        xmlPath = os.path.join(imagePath, imageName+'.xml')

        while not self.isXmlDone(xmlPath):
            QtGui.QApplication.processEvents()

        xml_attrs = xml_parse.ParseTSeriesXML(xmlPath, imagePath)

        for im in xml_attrs['SingleImage']['Frames'][0]['Images']:
            p = os.path.join(imagePath, im)
            while not self.isTifDone(p):
                QtGui.QApplication.processEvents()


        #time.sleep(1)## wait for images to be written
        images = self.loadImages(xml_attrs['SingleImage']['Frames'][0]['Images'], imagePath)

        info = OrderedDict()

        if xml_attrs['Environment']['XAxis_umPerPixel'] == xml_attrs['Environment']['YAxis_umPerPixel']:
            info['pixelSize'] = xml_attrs['Environment']['XAxis_umPerPixel']*self.scale

        x = xml_attrs['Environment']['XAxis']
        y = xml_attrs['Environment']['YAxis']
        z = xml_attrs['Environment']['ZAxis']

        info['frameTransform'] = self.makeFrameTransform(xml_attrs)
        info['deviceTransform'] = self.globalTransform()
        info['PrairieMetaInfo'] = xml_attrs
        info['time'] = time.time()

        frame = Frame(images, info)
        self.sigNewFrame.emit(frame)
        return frame

    def makeFrameTransform(self, info):
        ### Need to make a transform that maps from image coordinates (0,0 in top left) to device coordinates.
        ### Need to divide pixelSize here by objective scale so that it can be re-devided by Microscope in the deviceTransform
        xPixelSize = info['Environment']['XAxis_umPerPixel']*self.scale
        yPixelSize = info['Environment']['YAxis_umPerPixel']*self.scale
        
        tr = SRTTransform3D()
        

        ### Scaling
        # calculate scale of device transform 
        dtrans = self.globalTransform()
        dxscale = Point(dtrans.map(Point(0, 0)) - dtrans.map(Point(1, 0))).length()
        dyscale = Point(dtrans.map(Point(0, 0)) - dtrans.map(Point(0, 1))).length()

        # frame scale takes us the rest of the way
        fxscale = xPixelSize / dxscale
        fyscale = yPixelSize / dyscale

        
        tr.setScale(fxscale, fyscale)
        tr.setRotate(-90.) ## to match what's on PrairieView screen
        #print("FrameTransform scale:", fxscale, fyscale)
        #print("               pixelSize:", xPixelSize, yPixelSize)

        ## Translation
        ## move center of image to center of device
        imageWidth = info['Environment']['PixelsPerLine']*xPixelSize
        imageHeight = info['Environment']['LinesPerFrame']*yPixelSize

        voltageWidth = info['Environment']['ScannerVoltages']['XAxis_maxVoltage'] - info['Environment']['ScannerVoltages']['XAxis_minVoltage']
        voltageHeight = info['Environment']['ScannerVoltages']['YAxis_maxVoltage'] - info['Environment']['ScannerVoltages']['YAxis_minVoltage']

        centerVoltageX = info['Environment']['ScannerVoltages']['XAxis_currentScanCenter']
        centerVoltageY = info['Environment']['ScannerVoltages']['YAxis_currentScanCenter']

        centerX = (imageWidth/voltageWidth)*centerVoltageX
        centerY = (imageHeight/voltageHeight)*centerVoltageY

        ## find bottom-left corner, from center
        x = (centerX - imageWidth/2.)
        y = (centerY - imageHeight/2.)

        globalTopLeft = Point(x, -y)
        idtrans = self.inverseGlobalTransform()
        localTopLeft = idtrans.map(globalTopLeft) - idtrans.map(Point([0, 0]))

        tr.setTranslate(localTopLeft.x(), localTopLeft.y())


        return tr

    def isXmlDone(self, filePath):
        if not os.path.exists(filePath):
            return False
        size = os.path.getsize(filePath)
        end = ''
        if size > 9:
            f = open(filePath, 'r')
            f.seek(-9, os.SEEK_END)
            end = f.read()
            f.close()
        if end == '</PVScan>':
            return True
       
        return False

    def isTifDone(self, filePath):
        if not os.path.exists(filePath):
            return False
        return True

        




    def loadImages(self, images, dirPath):
        ## images is a tuple of image file names (as strings) as saved in Prairie's .xml meta info
        ## dirPath is the directory path that contains those images
        
        if images[0] is not None:
            filepath = os.path.join(dirPath, images[0])
            rChn = np.array(Image.open(filepath))
            #rChn = np.transpose(rChn)

        if images[1] is not None:
            filepath = os.path.join(dirPath, images[1])
            gChn = np.array(Image.open(filepath))
            #gChn = np.transpose(gChn)
        bChn = np.zeros(rChn.shape)

        return np.stack([rChn, gChn, bChn], axis=-1)

    def moduleInterface(self, mod):
        return PVImagerCamModInterface(self, mod)

    def deviceInterface(self, win):
        #return PrairieImagerDeviceGui(self, win) ## use for debugging transform, doesn't display info that makes sense for a user
        return None

    def setOffset(self, pos):
        tr = self.deviceTransform()
        tr.setTranslate(pos)
        self.setDeviceTransform(tr)


    # def isDone(self, imagePath):
    #     # If 'RAWDATA' file appears in the tseries folder, then we assume the tseries is not done yet
    #     if not any('RAWDATA' in substring for substring in [f for f in os.listdir(imagePath)]):
    #         return True
    #     else:
    #         return False


class PrairieImagerDeviceGui(QtGui.QWidget):

    def __init__(self, dev, win):
        QtGui.QWidget.__init__(self)

        self.dev = dev
        self.win = win

        self.ui = deviceTemplate.Ui_Form()
        self.ui.setupUi(self)

        opts = {'suffix': 'm',
                'siPrefix': True,
                'step': 1e-6,
                'decimals':4}
        self.ui.xOffsetSpin.setOpts(**opts)
        self.ui.yOffsetSpin.setOpts(**opts)
        self.ui.zOffsetSpin.setOpts(**opts)
        self.blockSpinChange = False

        self.ui.xOffsetSpin.sigValueChanged.connect(self.offsetSpinChanged)
        self.ui.yOffsetSpin.sigValueChanged.connect(self.offsetSpinChanged)
        self.dev.sigTransformChanged.connect(self.updateSpins)

        self.updateSpins()

    def offsetSpinChanged(self, spin):
        if self.blockSpinChange:
            return

        self.dev.sigTransformChanged.disconnect(self.updateSpins)
        try:
            self.dev.setOffset((self.ui.xOffsetSpin.value(), self.ui.yOffsetSpin.value()))
        finally:
            self.dev.sigTransformChanged.connect(self.updateSpins)

        
    def updateSpins(self):
        offset = self.dev.deviceTransform().getTranslation()
        self.ui.xOffsetSpin.setValue(offset.x())
        self.ui.yOffsetSpin.setValue(offset.y())
        self.ui.zOffsetSpin.setValue(offset.z())
