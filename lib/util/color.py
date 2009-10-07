from PyQt4 import QtGui

#def clip(x):
    #return max(0, min(x, 255))
    
def intColor(ind, colors=9, values=3, maxValue=255, minValue=150, sat=255):
    """Creates a QColor from a single index. Useful for stepping through a predefined list of colors."""
    colors = int(colors)
    values = int(values)
    ind = int(ind) % (colors * values)
    indh = ind % colors
    indv = ind / colors
    v = minValue + indv * ((maxValue-minValue) / (values-1))
    h = (indh * 360) / colors
    
    c = QtGui.QColor()
    c.setHsv(h, sat, v)
    return c
    
    #x = (ind * 280) % (256*3)
    #r = clip(255-abs(x)) + clip(255-abs(x-768))
    #g = clip(255-abs(x-256))
    #b = clip(255-abs(x-512))
    #return QtGui.QColor(r, g, b)

