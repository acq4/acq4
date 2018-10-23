from __future__ import print_function


if __name__ == '__main__':
    from . import items
    app = Qt.QApplication([])
    w1 = Qt.QMainWindow()
    c1 = Canvas(name="Canvas1")
    w1.setCentralWidget(c1)
    w1.show()
    w1.resize(600, 600)
    
    w2 = Qt.QMainWindow()
    c2 = Canvas(name="Canvas2")
    w2.setCentralWidget(c2)
    w2.show()
    w2.resize(600, 600)
    

    import numpy as np
    
    img1 = np.random.normal(size=(200, 200))
    img2 = np.random.normal(size=(200, 200))
    def fn(x, y):
        return (x**2 + y**2)**0.5
    img1 += np.fromfunction(fn, (200, 200))
    img2 += np.fromfunction(lambda x,y: fn(x-100, y-100), (200, 200))
    
    img3 = np.random.normal(size=(200, 200, 200))
    
    i1 = items.ImageCanvasItem(img1, scale=[0.01, 0.01], name="Image 1", z=10)
    c1.addItem(i1)
    
    gr = c1.addGroup('itemGroup')
    i2 = items.ImageCanvasItem(img2, scale=[0.01, 0.01], pos=[-1, -1], name="Image 2", z=100, parent=gr)
    i3 = items.ImageCanvasItem(img3, scale=[0.01, 0.01], pos=[1, -1], name="Image 3", z=-100, parent=gr)
    c1.addItem(i2)
    c1.addItem(i3)
    
    i1.setMovable(True)
    i2.setMovable(True)
