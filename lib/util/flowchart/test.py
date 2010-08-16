# -*- coding: utf-8 -*-

from Node import *
from PyQt4.QtGui import *
from PyQt4.QtCore import *


class TestNode(Node):
    def __init__(self, name):
        Node.__init__(self, name,
            terminals = {
                'X': ('in'),
                'Y': ('in'),
                'param': ('in'),
                'out1': ('out'),
                'out2': ('out'),
            }        
        )



app = QApplication([])

gv = QGraphicsView()
s =  QGraphicsScene()
gv.setScene(s)
gv.window().resize(400, 400)
gv.show()

n1 = TestNode("Node 1")
n2 = TestNode("Node 2")
i1 = n1.graphicsItem()
i2 = n2.graphicsItem()

s.addItem(i1)
s.addItem(i2)
i2.setPos(150, 0)