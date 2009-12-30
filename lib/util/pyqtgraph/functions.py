# -*- coding: utf-8 -*-
"""
functions.py -  Miscellaneous functions with no other home
Copyright 2010  Luke Campagnola
Distributed under MIT/X11 license. See license.txt for more infomation.
"""

from PyQt4 import QtGui

def mkPen(color=None, width=1, style=None, cosmetic=True):
    if color is None:
        color = [255, 255, 255]
    pen = QtGui.QPen(QtGui.QBrush(mkColor(color)), width)
    pen.setCosmetic(cosmetic)
    if style is not None:
        pen.setStyle(style)
    return pen
    
def mkColor(*args):
    """make a QColor from a variety of argument types"""
    err = 'Not sure how to make a color from "%s"' % str(args)
    if len(args) == 1:
        if isinstance(args[0], QtGui.QColor):
            return QtGui.QColor(args[0])
        elif hasattr(args[0], '__len__'):
            if len(args[0]) == 3:
                (r, g, b) = args[0]
                a = 255
            elif len(args[0]) == 4:
                (r, g, b, a) = args[0]
            else:
                raise Exception(err)
        else:
            raise Exception(err)
    elif len(args) == 3:
        (r, g, b) = args
        a = 255
    elif len(args) == 4:
        (r, g, b, a) = args
    else:
        raise Exception(err)
    return QtGui.QColor(r, g, b, a)
    
def colorStr(c):
    """Generate a hex string code from a QColor"""
    return ('%02x'*4) % (c.red(), c.blue(), c.green(), c.alpha())

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