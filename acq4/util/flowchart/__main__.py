from __future__ import print_function
import os, sys
path = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(path, '..'))
sys.path.insert(0, os.path.join(path, '..', '..', '..'))

from acq4.util import Qt
import acq4.util.flowchart as flowchart
app = Qt.QApplication([])

fc = flowchart.Flowchart(terminals={
    'dataIn': {'io': 'in'},
    'dataOut': {'io': 'out'}    
})
w = fc.widget()
w.resize(800,600)
w.show()

n1 = fc.createNode('Add')
n2 = fc.createNode('Subtract')
n3 = fc.createNode('Abs')
n4 = fc.createNode('Add')

fc.connectTerminals(fc.dataIn, n1.A)
fc.connectTerminals(fc.dataIn, n1.B)
fc.connectTerminals(fc.dataIn, n2.A)
fc.connectTerminals(n1.Out, n4.A)
fc.connectTerminals(n1.Out, n2.B)
fc.connectTerminals(n2.Out, n3.In)
fc.connectTerminals(n3.Out, n4.B)
fc.connectTerminals(n4.Out, fc.dataOut)


def process(**kargs):
    return fc.process(**kargs)

    
print(process(dataIn=7))

fc.setInput(dataIn=3)

s = fc.saveState()
fc.clear()

fc.restoreState(s)

fc.setInput(dataIn=3)

if sys.flags.interactive == 0:
    app.exec_()
