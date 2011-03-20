# -*- coding: utf-8 -*-
from mri_reader import readA75

data = readA75('Data/MAP2006.t2avg.hdr', 'Data/MAP2006.t2avg.img')
from pyqtgraph.graphicsWindows import *
w = ImageWindow()
w.setImage(data.transpose((0,2,1)))
