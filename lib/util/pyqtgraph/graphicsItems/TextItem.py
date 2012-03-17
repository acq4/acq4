from pyqtgraph.Qt import QtCore, QtGui
import pyqtgraph as pg
from UIGraphicsItem import *

class TextItem(UIGraphicsItem):
    """
    GraphicsItem displaying unscaled text (the text will always appear normal even inside a scaled ViewBox). 
    """
    def __init__(self, text='', color=(200,200,200), html=None, anchor=(0,0)):
        """
        Arguments:
        *text*   The text to display 
        *color*  The color of the text (any format accepted by pg.mkColor)
        *html*   If specified, this overrides both *text* and *color*
        *anchor* A QPointF or (x,y) sequence indicating what region of the text box will 
                 be anchored to the item's position. A value of (0,0) sets the upper-left corner
                 of the text box to be at the position specified by setPos(), while a value of (1,1)
                 sets the lower-right corner.
        """
        UIGraphicsItem.__init__(self)
        self.textItem = QtGui.QGraphicsTextItem()
        self._bounds = QtCore.QRectF()
        if html is None:
            self.setText(text, color)
        else:
            self.setHtml(html)
        self.anchor = pg.Point(anchor)
        #self.setFlag(self.ItemIgnoresTransformations)  ## This is required to keep the text unscaled inside the viewport

    def setText(self, text, color=(200,200,200)):
        color = pg.mkColor(color)
        self.textItem.setDefaultTextColor(color)
        self.textItem.setPlainText(text)
        #html = '<span style="color: #%s; text-align: center;">%s</span>' % (color, text)
        #self.setHtml(html)
        
    def updateAnchor(self):
        pass
        #self.resetTransform()
        #self.translate(0, 20)
        
    def setPlainText(self, *args):
        self.textItem.setPlainText(*args)
        self.updateText()
        
    def setHtml(self, *args):
        self.textItem.setHtml(*args)
        self.updateText()
        
    def setTextWidth(self, *args):
        self.textItem.setTextWidth(*args)
        self.updateText()
        
    def setFont(self, *args):
        self.textItem.setFont(*args)
        self.updateText()
        
    def updateText(self):
        self.img = None

    def getImage(self):
        if self.img is None:
            br = self.textItem.boundingRect()
            img = QtGui.QImage(int(br.width()), int(br.height()), QtGui.QImage.Format_ARGB32)
            p = QtGui.QPainter(img)
            self.textItem.paint(p, QtGui.QStyleOptionGraphicsItem(), None)
            p.end()
            self.img = img
        return self.img
        
    def sceneTransform(self):
        pos = self.scenePos()
        tr = self.transform()
        tr.translate(pos.x(), pos.y())
        return tr

    def viewRangeChanged(self):
        img = self.getImage()
        pos = self.scenePos()
        br = QtCore.QRectF(0, 0, img.width(), img.height())
        self._bounds = self.sceneTransform().mapRect(br)

    def boundingRect(self):
        return self._bounds
    
    def paint(self, p, *args):
        p.setPen(pg.mkPen('w'))
        #p.drawRect(self.boundingRect())
        p.setTransform(self.sceneTransform())
        img = self.getImage()
        #pos = self.scenePos()
        #p.drawRect(pos.x(), pos.y(), 1, 1)
        br = QtCore.QRectF(0, 0, img.width(), img.height())
        #p.drawRect(self.boundingRect())
        #p.setTransform(self.transform())
        p.drawRect(br)
        p.drawImage(br, img)
        