from acq4.pyqtgraph.canvas import Canvas as OrigCanvas
import items

class Canvas(OrigCanvas):
    """Extends pyqtgraph's canvas to add integration with datamanager."""
    
    def addFile(self, fh, **opts):
        ## automatically determine what item type to load from file. May invoke dataModel for extra help.
        types = items.listItems()
        
        maxScore = 0
        bestType = None
        
        ## Of all available types, find the one that claims to have the best support for this file type
        for t in types:
            if not hasattr(t, 'checkFile'):
                continue
            score = t.checkFile(fh)
            if score > maxScore:
                maxScore = score
                bestType = t
        if bestType is None:
            raise Exception("Don't know how to load file: '%s'" % str(fh))
        citem = bestType(handle=fh, **opts)
        self.addItem(citem)
        return citem
        #if fh.isFile():
            #if fh.shortName()[-4:] == '.svg':
                #return self.addSvg(fh, **opts)
            #else:
                #return self.addImage(fh, **opts)
        #else:
            #return self.addScan(fh, **opts)
