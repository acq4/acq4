from acq4.devices.OptomechDevice import OptomechDevice
from acq4.util.PrairieView import PrairieView
from acq4.util.imaging.Frame import Frame
from PIL import Image
import os
from optoanalysis import xml_parse
from collections import OrderedDict

class PrairieViewImager(OptomechDevice):


    def __init__(self, deviceManager, config, name):
        OptomechDevice.__init__(self, deviceManager, config, name)

        self.pv = PrairieView()
        self.pv.setSaveDirectory('C:/Megan/acq4')
        self._imageDirectory = 'Z:/Megan/acq4'
        self._frameIDcounter = 0
        self.scale = 1e-6

        

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
        imagePath = os.join(self._imageDirectory, imageName)
        xmlPath = os.join(imagePath, imageName+'.xml')

        xml_attrs = xml_parse.ParseTSeriesXML(xmlPath, imagePath)

        images = self.loadImages(xml_attrs['SingleImage']['Frames'][0]['Images'], imagePath)

        info = OrderedDict()

        if xml_attrs['Environment']['XAxis_umPerPixel'] == xml_attrs['Environment']['YAxis_umPerPixel']:
            info['pixelSize'] = xml_attrs['Environment']['XAxis_umPerPixel']/self.scale

        x = xml_attrs['Environment']['XAxis']
        y = xml_attrs['Environment']['YAxis']
        z = xml_attrs['Environment']['ZAxis']

        info['frameTransform'] = {'pos':(x, y, z)}
        info['deviceTransform'] = {}
        info['PrairieMetaInfo'] = xml_attrs

        return Frame(images, info)


        ## connect to Manager.sigCurrentDirChanged to have Prairie change the save path to match acq4's directory structure?

        ## save file using DirHandle.writeFile

    def loadImages(self, images, dirPath):
        ## images is a tuple of image file names (as strings) as saved in Prairie's .xml meta info
        ## dirPath is the directory path that contains those images
        
        if images[0] is not None:
            filepath = os.path.join(dirPath, images[0])
            rChn = np.array(Image.open(filepath))
            #rChn = np.transpose(rChn)

        if images[1] is not None:
            filepath = os.path.join(imagePath, images[1])
            gChn = np.array(Image.open(filepath))
            #gChn = np.transpose(gChn)

        return np.stack([rChn, gChn], axis=-1)

