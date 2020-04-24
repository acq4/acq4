from __future__ import print_function
import numpy as np
import acq4.pyqtgraph as pg
from acq4.util import Qt


class MaskPainter(Qt.QWidget):
    def __init__(self, parent=None):
        Qt.QWidget.__init__(self, parent)
        self.layout = Qt.QGridLayout()
        self.setLayout(self.layout)
        
        self.view = pg.ImageView()
        self.layout.addWidget(self.view, 0, 0)
        
        self.ctrlWidget = Qt.QWidget()
        self.layout.addWidget(self.ctrlWidget, 0, 1)
        
        self.maskItem = pg.ImageItem()
        self.maskItem.setZValue(10)
        self.maskItem.setCompositionMode(Qt.QPainter.CompositionMode_Multiply)
        lut = np.zeros((256, 3), dtype='ubyte')
        lut[:,0:2] = np.arange(256).reshape(256,1)
        self.maskItem.setLookupTable(lut)
        
        kern = np.fromfunction(lambda x,y: np.clip(((5 - (x-5)**2+(y-5)**2)**0.5 * 255), 0, 255), (11, 11))
        self.maskItem.setDrawKernel(kern, mask=kern, center=(5,5), mode='add')        

        self.view.addItem(self.maskItem)
        
        self.view.sigTimeChanged.connect(self.updateMaskImage)

    def setImage(self, image):
        self.view.setImage(image)
        self.mask = np.zeros(image.shape, dtype='ubyte')
        self.updateMaskImage()
        
    def updateMaskImage(self):
        self.maskItem.setImage(self.mask[self.view.currentIndex])
        
    
        
    
        
if __name__ == '__main__':
    img = np.random.normal(size=(100, 100, 100))
    mp = MaskPainter()
    mp.setImage(img)
    mp.show()
    