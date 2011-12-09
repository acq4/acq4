from Qt import QtCore, QtGui, QtOpenGL, QtSvg
import weakref
from Point import Point
import functions as fn
import ptime

try:
    import sip
    HAVE_SIP = True
except:
    HAVE_SIP = False



class GraphicsScene(QtGui.QGraphicsScene):
    """
    Extension of QGraphicsScene that: 
    -  Generates MouseClicked events in addition to the usual press/move/release events. 
       (This works around a problem where it is impossible to have one item respond to a 
       drag if another is watching for a click.)
    -  Adjustable radius around click that will catch objects so you don't have to click *exactly* over small/thin objects
    -  Global context menu--if an item implements a context menu, then its parent(s) may also add items to the menu.
    -  Allows items to decide _before_ a mouse click which item will be the recipient of mouse events.
       This lets us indicate unambiguously to the user which item they are about to click/drag on
    -  Eats mouseMove events that occur too soon after a mouse press.
    -  Reimplements items() and itemAt() to circumvent PyQt bug
    
    Mouse interaction is as follows:
    1) Every time the mouse moves, the scene checks to see which objects nearby could catch a mouseClickEvent or 
       mouseDragEvent.
       Each item is sent a mouseHoverEvent and may optionally call event.acceptClicks(), acceptDrags() or both.
       The first item(s) to accept will receive a call to item.mouseClickReceiver(True) or 
       item.mouseDragReceiver(True), informing the item that _if_ the user clicks the mouse, the item will be the 
       recipient of click/drag events (the item may wish to change its appearance to indicate this)
       The former recipient of these events is sent mouseClick/DragReceiver(False).
    2) If the mouse is clicked, a mousePressEvent is generated as usual. If any items accept this press event, then
       No click/drag events will be generated and mouse interaction proceeds as defined by Qt. This allows
       items to function properly if they are expecting the usual press/move/release sequence of events.
       (It is recommended that items do NOT accept press events, and instead use click/drag events)
    3) If no item accepts the mousePressEvent, then the scene will begin delivering mouseDrag and/or mouseClick events.
       If the mouse is moved a sufficient distance before the button is released, then a mouseDragEvent is generated.
       If no drag events are generated before the button is released, then a mouseClickEvent is generated. 
    4) Click/drag events are delivered to the item that called acceptClicks/acceptDrags on the mouseHoverEvent
       in step 1. If no such items exist, then the scene attempts to deliver the events to items near the event. 
       ClickEvents may be delivered in this way even if no
       item originally claimed it could accept the click. DragEvents may only be delivered this way if it is the initial
       move in a drag.
    """
    
    
    _addressCache = weakref.WeakValueDictionary()
    sigSceneContextMenuEvent = QtCore.Signal(object)
    sigSceneHoverEvent = QtCore.Signal(object)
    
    @classmethod
    def registerObject(cls, obj):
        """
        Workaround for PyQt bug in qgraphicsscene.items()
        All subclasses of QGraphicsObject must register themselves with this function.
        (otherwise, mouse interaction with those objects will likely fail)
        """
        if HAVE_SIP and isinstance(obj, sip.wrapper):
            cls._addressCache[sip.unwrapinstance(sip.cast(obj, QtGui.QGraphicsItem))] = obj
            
            
    def __init__(self, clickRadius=2, moveDistance=5):
        QtGui.QGraphicsScene.__init__(self)
        self.setClickRadius(clickRadius)
        self.setMoveDistance(moveDistance)
        self.clickEvents = []
        self.dragButtons = []
        self.mouseGrabber = None
        self.dragItem = None
        self.lastDrag = None
        #self.searchRect = QtGui.QGraphicsRectItem()
        #self.searchRect.setPen(fn.mkPen(200,0,0))
        #self.addItem(self.searchRect)
        

    def setClickRadius(self, r):
        """
        Set the distance away from mouse clicks to search for interacting items.
        When clicking, the scene searches first for items that directly intersect the click position
        followed by any other items that are within a rectangle that extends r pixels away from the 
        click position. 
        """
        self._clickRadius = r
        
    def setMoveDistance(self, d):
        """
        Set the distance the mouse must move after a press before mouseMoveEvents will be delivered.
        This ensures that clicks with a small amount of movement are recognized as clicks instead of
        drags.
        """
        self._moveDistance = d

    def mousePressEvent(self, ev):
        print 'scenePress'
        QtGui.QGraphicsScene.mousePressEvent(self, ev)
        print "mouseGrabberItem: ", self.mouseGrabberItem()
        if self.mouseGrabberItem() is None:  ## nobody claimed press; we are free to generate drag/click events
            self.clickEvents.append(MouseClickEvent(ev))
        #else:
            #addr = sip.unwrapinstance(sip.cast(self.mouseGrabberItem(), QtGui.QGraphicsItem))
            #item = GraphicsScene._addressCache.get(addr, self.mouseGrabberItem())            
            #print "click grabbed by:", item
        
    def mouseMoveEvent(self, ev):
        #print 'sceneMove'
        QtGui.QGraphicsScene.mouseMoveEvent(self, ev)
        if int(ev.buttons()) == 0: ## nothing pressed; send mouseHoverOver/OutEvents
            #print "Scene emitting hover event. items:", self.items(ev.scenePos())
            self.sigSceneHoverEvent.emit(self.items(ev.scenePos()))
        
        else:
            if self.mouseGrabberItem() is None:
                now = ptime.time()
                init = False
                ## keep track of which buttons are involved in dragging
                for btn in [QtCore.Qt.LeftButton, QtCore.Qt.MidButton, QtCore.Qt.RightButton]:
                    if int(ev.buttons() & btn) == 0:
                        continue
                    if int(btn) not in self.dragButtons:  ## see if we've dragged far enough yet
                        cev = [e for e in self.clickEvents if int(e.button()) == int(btn)][0]
                        dist = Point(ev.screenPos() - cev.screenPos())
                        if dist.length() < self._moveDistance and now - cev.time() < 0.5:
                            continue
                        init = init or (len(self.dragButtons) == 0)  ## If this is the first button to be dragged, then init=True
                        self.dragButtons.append(int(btn))
                if len(self.dragButtons) > 0:
                    if self.sendDragEvent(ev, init=init):
                        ev.accept()
                
    def mouseReleaseEvent(self, ev):
        #print 'sceneRelease'
        if self.mouseGrabberItem() is None:
            #print "sending click/drag event"
            if ev.button() in self.dragButtons:
                if self.sendDragEvent(ev, final=True):
                    #print "sent drag event"
                    ev.accept()
                self.dragButtons.remove(ev.button())
            else:
                cev = [e for e in self.clickEvents if int(e.button()) == int(ev.button())]
                if self.sendClickEvent(cev[0]):
                    print "sent click event"
                    ev.accept()
                self.clickEvents.remove(cev[0])
                
        if int(ev.buttons()) == 0:
            self.dragItem = None
            self.dragButtons = []
            self.clickEvents = []
            self.lastDrag = None
        QtGui.QGraphicsScene.mouseReleaseEvent(self, ev)

    def mouseDoubleClickEvent(self, ev):
        QtGui.QGraphicsScene.mouseDoubleClickEvent(self, ev)
        if self.mouseGrabberItem() is None:  ## nobody claimed press; we are free to generate drag/click events
            self.clickEvents.append(MouseClickEvent(ev, double=True))
        


    def sendDragEvent(self, ev, init=False, final=False):
        ## Send a MouseDragEvent to the current dragItem or to 
        ## items near the beginning of the drag
        event = MouseDragEvent(ev, self.clickEvents[0], self.lastDrag, start=init, finish=final)
        print "dragEvent: init=", init, 'final=', final, 'self.dragItem=', self.dragItem
        if init and self.dragItem is None:
            print "   drag1"
            for item in self.itemsNearEvent(event):
                print "check item:", item
                if hasattr(item, 'mouseDragEvent'):

                    event.currentItem = item
                    item.mouseDragEvent(event)
                    print 'sent DragEvent to ', item
                    if event.isAccepted():
                        #print "   --> accepted"
                        self.dragItem = item
                        break
        elif self.dragItem is not None:
            event.currentItem = self.dragItem
            self.dragItem.mouseDragEvent(event)
            
        self.lastDrag = event
        
        return event.isAccepted()
            
        
    def sendClickEvent(self, ev):
        ## if we are in mid-drag, click events may only go to the dragged item.
        if self.dragItem is not None and hasattr(self.dragItem, 'mouseClickEvent'):
            ev.currentItem = self.dragItem
            self.dragItem.mouseClickEvent(ev)
            
        ## otherwise, search near the cursor
        else:
            for item in self.itemsNearEvent(ev):
                if hasattr(item, 'mouseClickEvent'):
                    ev.currentItem = item
                    item.mouseClickEvent(ev)
                    print 'sent clickEvent to ', item
                    if ev.isAccepted():
                        break
            if not ev.isAccepted() and ev.button() == QtCore.Qt.RightButton: ## context menu event
                print "Scene emitting contextMenuEvent"
                self.sigSceneContextMenuEvent.emit(ev)
                
        return ev.isAccepted()
        
    def items(self, *args):
        #print 'args:', args
        items = QtGui.QGraphicsScene.items(self, *args)
        ## PyQt bug: items() returns a list of QGraphicsItem instances. If the item is subclassed from QGraphicsObject,
        ## then the object returned will be different than the actual item that was originally added to the scene
        if HAVE_SIP and isinstance(self, sip.wrapper):
            items2 = []
            for i in items:
                addr = sip.unwrapinstance(sip.cast(i, QtGui.QGraphicsItem))
                i2 = GraphicsScene._addressCache.get(addr, i)
                #print i, "==>", i2
                items2.append(i2)
        #print 'items:', items
        return items2

    def itemAt(self, *args):
        item = QtGui.QGraphicsScene.itemAt(self, *args)
        
        ## PyQt bug: items() returns a list of QGraphicsItem instances. If the item is subclassed from QGraphicsObject,
        ## then the object returned will be different than the actual item that was originally added to the scene
        if HAVE_SIP and isinstance(self, sip.wrapper):
            addr = sip.unwrapinstance(sip.cast(item, QtGui.QGraphicsItem))
            item = GraphicsScene._addressCache.get(addr, item)
        return item

    def itemsNearEvent(self, event, selMode=QtCore.Qt.IntersectsItemShape, sortOrder=QtCore.Qt.DescendingOrder):
        """
        Return an iterator that iterates first through the items that directly intersect point (in Z order)
        followed by any other items that are within the scene's click radius.
        """
        #tr = self.getViewWidget(event.widget()).transform()
        view = self.views()[0]
        tr = view.viewportTransform()
        r = self._clickRadius
        rect = view.mapToScene(QtCore.QRect(0, 0, 2*r, 2*r)).boundingRect()
        
        seen = set()
        if hasattr(event, 'buttonDownScenePos'):
            point = event.buttonDownScenePos()
        else:
            point = event.scenePos()
        w = rect.width()
        h = rect.height()
        rgn = QtCore.QRectF(point.x()-w, point.y()-h, 2*w, 2*h)
        #self.searchRect.setRect(rgn)

        #for item in self.items(point, selMode, sortOrder, tr):
            ##seen.add(item)
            #print item
            #print item.mapToScene(item.shape()).contains(point)
            #yield item
        #print x
        for item in self.items(rgn, selMode, sortOrder, tr):
            #if item not in seen:
            shape = item.mapToScene(item.shape())
            if not (shape.contains(rgn) or shape.intersects(rgn)):
                continue

            #print 'yeilding item:', item
            yield item
        
    def getViewWidget(self, widget):
        ## same pyqt bug -- mouseEvent.widget() doesn't give us the original python object.
        ## [[doesn't seem to work correctly]]
        if HAVE_SIP and isinstance(self, sip.wrapper):
            addr = sip.unwrapinstance(sip.cast(widget, QtGui.QWidget))
            #print "convert", widget, addr
            for v in self.views():
                addr2 = sip.unwrapinstance(sip.cast(v, QtGui.QWidget))
                #print "   check:", v, addr2
                if addr2 == addr:
                    return v
        else:
            return widget

class MouseDragEvent:
    def __init__(self, moveEvent, pressEvent, lastEvent, start=False, finish=False):
        self.start = start
        self.finish = finish
        self.accepted = False
        self.currentItem = None
        self._buttonDownScenePos = {}
        self._buttonDownScreenPos = {}
        for btn in [QtCore.Qt.LeftButton, QtCore.Qt.MidButton, QtCore.Qt.RightButton]:
            self._buttonDownScenePos[int(btn)] = moveEvent.buttonDownScenePos(btn)
            self._buttonDownScreenPos[int(btn)] = moveEvent.buttonDownScreenPos(btn)
        self._scenePos = moveEvent.scenePos()
        self._screenPos = moveEvent.screenPos()
        if lastEvent is None:
            self._lastScenePos = pressEvent.scenePos()
            self._lastScreenPos = pressEvent.screenPos()
        else:
            self._lastScenePos = lastEvent.scenePos()
            self._lastScreenPos = lastEvent.screenPos()
        self._buttons = moveEvent.buttons()
        self._button = pressEvent.button()
        self._modifiers = moveEvent.modifiers()
        
    def accept(self):
        self.accepted = True
        self.acceptedItem = self.currentItem
        
    def ignore(self):
        self.accepted = False
    
    def isAccepted(self):
        return self.accepted
    
    def scenePos(self):
        return Point(self._scenePos)
    
    def screenPos(self):
        return Point(self._screenPos)
    
    def buttonDownScenePos(self, btn=None):
        if btn is None:
            btn = self.button()
        return Point(self._buttonDownScenePos[int(btn)])
    
    def buttonDownScreenPos(self, btn=None):
        if btn is None:
            btn = self.button()
        return Point(self._buttonDownScreenPos[int(btn)])
    
    def lastScenePos(self):
        return Point(self._lastScenePos)
    
    def lastScreenPos(self):
        return Point(self._lastScreenPos)
    
    def buttons(self):
        return self._buttons
        
    def button(self):
        """Return the button that initiated the drag (may be different from the buttons currently pressed)"""
        return self._button
        
    def pos(self):
        return Point(self.currentItem.mapFromScene(self._scenePos))
    
    def lastPos(self):
        return Point(self.currentItem.mapFromScene(self._lastScenePos))
        
    def buttonDownPos(self, btn=None):
        if btn is None:
            btn = self.button()
        return Point(self.currentItem.mapFromScene(self._buttonDownScenePos[int(btn)]))
    
    def isStart(self):
        return self.start
        
    def isFinish(self):
        return self.finish

    def __repr__(self):
        lp = self.lastPos()
        p = self.pos()
        return "<MouseDragEvent (%g,%g)->(%g,%g) buttons=%d start=%s finish=%s>" % (lp.x(), lp.y(), p.x(), p.y(), int(self.buttons()), str(self.isStart()), str(self.isFinish()))
        
    def modifiers(self):
        return self._modifiers
        
class MouseClickEvent:
    def __init__(self, pressEvent, double=False):
        self.accepted = False
        self.currentItem = None
        self._double = double
        self._scenePos = pressEvent.scenePos()
        self._screenPos = pressEvent.screenPos()
        self._button = pressEvent.button()
        self._buttons = pressEvent.buttons()
        self._modifiers = pressEvent.modifiers()
        self._time = ptime.time()
        
        
    def accept(self):
        self.accepted = True
        self.acceptedItem = self.currentItem
        
    def ignore(self):
        self.accepted = False
    
    def isAccepted(self):
        return self.accepted
    
    def scenePos(self):
        return Point(self._scenePos)
    
    def screenPos(self):
        return Point(self._screenPos)
    
    def buttons(self):
        return self._buttons
    
    def button(self):
        return self._button
    
    def double(self):
        return self._double

    def pos(self):
        return Point(self.currentItem.mapFromScene(self._scenePos))
    
    def lastPos(self):
        return Point(self.currentItem.mapFromScene(self._lastScenePos))
        
    def modifiers(self):
        return self._modifiers

    def __repr__(self):
        p = self.pos()
        return "<MouseClickEvent (%g,%g) button=%d>" % (p.x(), p.y(), int(self.button()))
        
    def time(self):
        return self._time
        