# -*- coding: utf-8 -*-

## Uses code yanked from nipy project
import nipy_stolen.minc as minc

mri = minc.load('VMBA/129SV_atlas.mnc').get_data()
atlas = minc.load('VMBA/129SV_atlas_labelling.mnc').get_data()

from pyqtgraph.graphicsWindows import *
win = ImageWindow()
win.setImage(mri.transpose((1,2, 0))[:,:,::-1])
