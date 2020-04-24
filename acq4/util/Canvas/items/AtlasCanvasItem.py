# -*- coding: utf-8 -*-
from __future__ import print_function
import weakref
from acq4.util import Qt
from .CanvasItem import CanvasItem
import acq4.pyqtgraph as pg
import acq4.pyqtgraph.graphicsItems.TargetItem
from .itemtypes import registerItemType

try:
    from aiccf.ui import AtlasSliceView
    from aiccf.data import CCFAtlasData
    HAVE_AICCF = True
except ImportError:
    HAVE_AICCF = False


class AtlasCanvasItem(CanvasItem):
    """
    Canvas item used for displaying common coordinate framework atlas data.
    
    """
    _typeName = "Atlas"
    
    def __init__(self, **kwds):
        if not HAVE_AICCF:
            raise Exception("This item requires the aiccf module, but it could not be imported.")
        kwds.pop('viewRect', None)
        
        self.atlas = CCFAtlasData()
        with pg.BusyCursor():
            self.atlasView = AtlasSliceView()
            self.atlasView.set_data(self.atlas)
        
        item = self.atlasView.img2
        opts = {'scalable': True, 'rotatable': True, 'movable': True}
        opts.update(kwds)        
        CanvasItem.__init__(self, item, **opts)
        
        self.__ctrl = Qt.QWidget()
        self.__layout = Qt.QGridLayout()
        self.__ctrl.setLayout(self.__layout)
        self.__layout.setContentsMargins(0, 0, 0, 0)
        self.__layout.addWidget(self.atlasView.display_ctrl, 0, 0)
        self.__layout.addWidget(self.atlasView.label_tree, 1, 0)
        
        self.showSliceBtn = Qt.QPushButton("Show slice")
        self.showSliceBtn.setCheckable(True)
        self.__layout.addWidget(self.showSliceBtn, 2, 0)
        self.showSliceBtn.toggled.connect(self.showSliceToggled)

        self.layout.addWidget(self.__ctrl, self.layout.rowCount(), 0, 1, 2)
        
        # Set up window for selecting slice plane
        self.sliceWidget = Qt.QWidget()
        self.sliceLayout = Qt.QGridLayout()
        self.sliceWidget.setLayout(self.sliceLayout)
        self.sliceGraphicsView = pg.GraphicsLayoutWidget()
        self.sliceLayout.addWidget(self.sliceGraphicsView, 0, 0)
        self.sliceView = self.sliceGraphicsView.addViewBox()
        self.sliceView.addItem(self.atlasView.img1)
        self.sliceView.autoRange()
        self.sliceView.setAspectLocked(True)
        self.sliceView.addItem(self.atlasView.line_roi)
        self.sliceLayout.addWidget(self.atlasView.zslider, 1, 0)
        self.sliceLayout.addWidget(self.atlasView.angle_slider, 2, 0)
        self.sliceWidget.resize(800, 800)

    def showSliceToggled(self):
        self.sliceWidget.setVisible(self.showSliceBtn.isChecked())

    @classmethod
    def checkFile(cls, fh):
        return 0

    def saveState(self, **kwds):
        return self.atlas.save_state()

    def restoreState(self, state):
        self.atlas.restore_state(state)


registerItemType(AtlasCanvasItem)
