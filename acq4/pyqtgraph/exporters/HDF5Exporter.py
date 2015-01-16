from ..Qt import QtGui, QtCore
from .Exporter import Exporter
from ..parametertree import Parameter
from .. import PlotItem

import numpy 
import h5py

__all__ = ['HDF5Exporter']
    
    
class HDF5Exporter(Exporter):
    Name = "HDF5 Export: plot (x,y)"
    windows = []
    allowCopy = False

    def __init__(self, item):
        Exporter.__init__(self, item)
        self.params = Parameter(name='params', type='group', children=[
            {'name': 'Name', 'type': 'str', 'value': 'Export',},
            {'name': 'columnMode', 'type': 'list', 'values': ['(x,y) per plot', '(x,y,y,y) for all plots']},
        ])
        
    def parameters(self):
        return self.params
    
    def export(self, fileName=None):
        
        if not isinstance(self.item, PlotItem):
            raise Exception("Must have a PlotItem selected for HDF5 export.")
        
        if fileName is None:
            self.fileSaveDialog(filter=["*.h5", "*.hdf", "*.hd5"])
            return
        dsname = self.params['Name']
        fd = h5py.File(fileName, 'a') # forces append to file... 'w' doesn't seem to "delete/overwrite"
        data = []

        appendAllX = self.params['columnMode'] == '(x,y) per plot'
        #print dir(self.item.curves[0])
        tlen = 0
        for i, c in enumerate(self.item.curves):
            d = c.getData()
            if i > 0 and len(d[0]) < tlen:
                continue
            if appendAllX or i == 0:
                data.append(d[0])
                tlen = len(d[0])
            data.append(d[1])
            print 'len(d): %d  for c = ' % len(d),
            print c.objectName()

        #print 'hdf5export data: ', fdata
        #fdata = np.zeros((len(d)))
        for i in range(len(data)):
            print 'i %d: data: ', (i, len(data[i]))
        fdata = numpy.array(data).astype('double')
        dset = fd.create_dataset(dsname, data=fdata)
        fd.close()


HDF5Exporter.register()
