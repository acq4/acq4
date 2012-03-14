from pyqtgraph.Qt import QtCore, QtGui
import pyqtgraph as pg

class TextItem(QtGui.QGraphicsTextItem):
    """
    QGraphicsTextItem displaying unscaled text (the text will always appear normal even inside a scaled ViewBox). 
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
        QtGui.QGraphicsTextItem.__init__(self)
        if html is None:
            color = pg.colorStr(pg.mkColor(color))[:6]
            html = '<span style="color: #%s;">%s</span>' % (color, text)
        self.setHtml(html)
        self.anchor = pg.Point(anchor)
        self.setFlag(self.ItemIgnoresTransformations)  ## This is required to keep the text unscaled inside the viewport

    def setText(self, text, color=(200,200,200)):
        color = pg.colorStr(pg.mkColor(color))[:6]
        html = '<span style="color: #%s;">%s</span>' % (color, text)
        self.setHtml(html)
        
    def updateAnchor(self):
        self.resetTransform()
        self.translate(0, 20)
        
    def setPlainText(self, *args):
        QtGui.QGraphicsTextItem.setPlainText(self, *args)
        self.updateAnchor()
        
    def setHtml(self, *args):
        QtGui.QGraphicsTextItem.setPlainText(self, *args)
        self.updateAnchor()
        
    def setTextWidth(self, *args):
        QtGui.QGraphicsTextItem.setTextWidth(self, *args)
        self.updateAnchor()
        
    def setFont(self, *args):
        QtGui.QGraphicsTextItem.setFont(self, *args)
        self.updateAnchor()
        
    

        