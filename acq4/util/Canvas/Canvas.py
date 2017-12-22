from __future__ import print_function
from acq4.pyqtgraph.canvas import Canvas as OrigCanvas
from . import items

class Canvas(OrigCanvas):
    """Extends pyqtgraph's canvas to add integration with datamanager and
    an item type registration system."""
    
    def addFile(self, fh, **opts):
        ## automatically determine what item type to load from file. May invoke dataModel for extra help.
        types = list(items.itemTypes().values())
        
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

    def addItem(self, item=None, type=None, **opts):
        """Add an item to the canvas.

        May provide either *item* which is a CanvasItem instance, or
        *type* which is a string specifying the type of item to create and add.
        Types are specified using :func:`acq4.util.Canvas.registerItemType`.
        """
        if item is None:
            if type is None:
                raise ValueError("Must provide either item or type argument.")
            vr = self.view.viewRect()
            opts['viewRect'] = vr
            item = items.getItemType(type)(**opts)
        else:
            if len(opts) > 0:
                raise TypeError("Cannot apply extra options to an existing CanvasItem: %s" % opts)
        return OrigCanvas.addItem(self, item)
