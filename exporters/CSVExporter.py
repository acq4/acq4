from ..Qt import QtGui, QtCore
from .Exporter import Exporter
from ..parametertree import Parameter
from .. import PlotItem

__all__ = ['CSVExporter']
    
    
class CSVExporter(Exporter):
    Name = "CSV from plot data"
    windows = []
    def __init__(self, item):
        Exporter.__init__(self, item)
        self.params = Parameter(name='params', type='group', children=[
            {'name': 'separator', 'type': 'list', 'value': 'comma', 'values': ['comma', 'tab']},
            {'name': 'precision', 'type': 'int', 'value': 10, 'limits': [0, None]},
        ])
        
    def parameters(self):
        return self.params
    
    def export(self, fileName=None):
        
        if not isinstance(self.item, PlotItem):
            raise Exception("Must have a PlotItem selected for CSV export.")
        
        if fileName is None:
            self.fileSaveDialog(filter=["*.csv", "*.tsv"])
            return

        fd = open(fileName, 'w')
        data = []
        header = []

        for i,c in enumerate(self.item.curves):
            cd = c.getData()
            if cd[0] is None:
                continue
            data.append(cd)
            if hasattr(c, 'implements') and c.implements('plotData') and c.name() is not None:
                name = c.name().replace('"', '""') + '_'
                xName, yName = '"'+name+'x"', '"'+name+'y"'
            else:
                xName = 'x%04d' % i
                yName = 'y%04d' % i
            header.extend([xName, yName])

        if self.params['separator'] == 'comma':
            sep = ','
        else:
            sep = '\t'
            
        fd.write(sep.join(header) + '\n')
        i = 0
        numFormat = '%%0.%dg' % self.params['precision']
        numRows = max([len(d[0]) for d in data])
        for i in range(numRows):
            for d in data:
                if d is not None and i < len(d[0]):
                    fd.write('%g%s%g%s'%(d[0][i], sep, d[1][i], sep))
                else:
                    fd.write(' %s %s' % (sep, sep))
            fd.write('\n')
        fd.close()

CSVExporter.register()        
                
        
