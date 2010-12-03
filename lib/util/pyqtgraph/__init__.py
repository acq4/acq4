# -*- coding: utf-8 -*-
### import all the goodies and add some helper functions for easy CLI use

from functions import *
from graphicsItems import *
import PlotWidget
import ImageView

plots = []
images = []

def plot(*args, **kargs):
    w = PlotWindow(*args, **kargs)
    plots.append(w)
    w.show()
    return w
    
def show(*args, **kargs):
    w = ImageView(*args, **kargs)
    images.append(w)
    w.show()
    return w