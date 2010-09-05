# -*- coding: utf-8 -*-

from TreeWidget import *

app = QtGui.QApplication([])

w = TreeWidget()
w.setColumnCount(2)
w.show()

i1  = QtGui.QTreeWidgetItem(["Item 1"])
i11  = QtGui.QTreeWidgetItem(["Item 1.1"])
i12  = QtGui.QTreeWidgetItem(["Item 1.2"])
i2  = QtGui.QTreeWidgetItem(["Item 2"])
i21  = QtGui.QTreeWidgetItem(["Item 2.1"])
i211  = QtGui.QTreeWidgetItem(["Item 2.1.1"])
i212  = QtGui.QTreeWidgetItem(["Item 2.1.2"])
i22  = QtGui.QTreeWidgetItem(["Item 2.2"])

w.addTopLevelItem(i1)
w.addTopLevelItem(i2)
i1.addChild(i11)
i1.addChild(i12)
i2.addChild(i21)
i21.addChild(i211)
i21.addChild(i212)
i2.addChild(i22)

b1 = QtGui.QPushButton("B1")
w.setItemWidget(i1, 1, b1)