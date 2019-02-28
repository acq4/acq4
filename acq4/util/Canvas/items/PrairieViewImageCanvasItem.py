from ImageCanvasItem import ImageCanvasItem
from optoanalysis import xml_parse
from PIL import Image
from .itemtypes import registerItemType
import acq4.util.DataManager as DataManager
import numpy as np


class PrairieViewImageCanvasItem(ImageCanvasItem):

    _typeName = "PrairieViewImage"

    def __init__(self, image=None, **opts):

        ## If no image was specified, check for a file handle..
        if image is None:
            image = opts.get('handle', None)

        ## image should be 'TSeries' or 'ZSeries' dirHandle
        if not isinstance(image, DataManager.DirHandle):
            raise Exception("A directory must be selected in order to load images from PrairieView")

        xmls = [f for f in image.ls() if f.endswith('.xml') and 'MarkPoints' not in f] # Don't want MP XML
        if len(xmls) > 1:
            raise Exception("Found more than one xml file.")
        xml_attrs = xml_parse.ParseTSeriesXML(image.getFile(xmls[0]).name(), image.name())

        if "ZSeries" in image.name():
            data = self.get_zseries_images(xml_attrs, image)
            opts = self.get_zseries_metainfo(xml_attrs)

        ImageCanvasItem.__init__(self, image=data, **opts)



    @classmethod
    def checkFile(cls, fh):
        if 'ZSeries' in fh.name() and isinstance(fh, DataManager.DirHandle):
            return 100
        else:
            return 0

    def get_zseries_images(self, xml_attrs, dh):
        rChn = None
        gChn = None
        for k in xml_attrs['ZSeries']['Frames']:
            ims = k['Images']
            #filepath = '/'.join([self.base_dir, tseries, ims[0]])
            filepath = dh.getFile(ims[0]).name()
            if rChn is None:
                rChn = np.array(Image.open(filepath))
            else:  
                rChn = np.dstack((rChn, np.array(Image.open(filepath))))

            #filepath = '/'.join([self.base_dir, tseries, ims[1]])
            filepath = dh.getFile(ims[1]).name()
            if gChn is None:
                gChn = np.array(Image.open(filepath))
            else:  
                gChn = np.dstack((gChn, np.array(Image.open(filepath))))
        
        rChn = np.transpose(rChn)
        gChn = np.transpose(gChn)

        combined = np.zeros((rChn.shape[0], rChn.shape[1], rChn.shape[2], 3), rChn.dtype)
        #if self.redCheck.isChecked():
        combined[..., 0] = rChn
        #if self.greenCheck.isChecked():
        combined[..., 1] = gChn

        return combined
        #self.add_image_item(combined, env_dict, tseries, base)

    def get_zseries_metainfo(self, xml_attrs):

        xPos = xml_attrs['ZSeries']['XAxis'] * 1e-6 ## convert from um to m
        yPos = xml_attrs['ZSeries']['YAxis'] * 1e-6
        zPos = []
        for f in xml_attrs['ZSeries']['Frames']:
            zPos.append(f['ZAxis'] * 1e-6)

        scale = (xml_attrs['Environment']['XAxis_umPerPixel']*1e-6,
                 xml_attrs['Environment']['YAxis_umPerPixel']*1e-6,
                 xml_attrs['Environment']['ZAxis_umPerPixel']*1e-6)

        opts = {}
        opts['pos'] = [xPos, yPos]
        opts['zDepths'] = zPos
        opts['scale'] = scale

        return opts

registerItemType(PrairieViewImageCanvasItem)
