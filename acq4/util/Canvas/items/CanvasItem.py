from acq4.pyqtgraph.canvas.CanvasItem import CanvasItem as OrigCanvasItem

class CanvasItem(OrigCanvasItem):
    ## extent canvasitem to have support for filehandles
    
    def __init__(self, *args, **kargs):
        OrigCanvasItem.__init__(self, *args, **kargs)
        
        if 'handle' not in self.opts:
            self.opts['handle'] = None
        
        ## reload user transform from disk if possible
        if self.opts['handle'] is not None:
            trans = self.opts['handle'].info().get('userTransform', None)
            if trans is not None:
                self.restoreTransform(trans)
            elif 'defaultUserTransform' in self.opts:
                self.restoreTransform(self.opts['defaultUserTransform'])
            if self.opts['name'] is None:
                self.opts['name'] = self.opts['handle'].shortName()
        
    def getHandle(self):
        """Return the file handle for this item, if any exists."""
        return self.opts['handle']
    
    @classmethod
    def checkFile(cls, handle):
        """
        Decide whether this item type can load the file specified. 
        If so, return an integer (the class returning the largest value wins)
        If not, return 0
        """
        return 0

    def storeUserTransform(self, fh=None):
        """Store the current user transform to disk.
        If fh is specified, store data to that file handle.
        Otherwise, use self.handle if it is set."""
        if fh is None:
            fh = self.getHandle()
        if fh is None:
            raise Exception("Can not store transform--no file handle for this item.", 1)
        trans = self.saveTransform()
        if 0 in trans['scale']:
            raise Exception("Transform has invalid scale; not saving: %s" % str(trans))
        fh.setInfo(userTransform=trans)
    

