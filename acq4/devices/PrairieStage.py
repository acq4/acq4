import time, socket
import numpy as np
from acq4.Manager import getManager
from acq4.devices.Stage import Stage, MoveFuture
from acq4.util.Thread import Thread
from acq4.util.PrairieView import PrairieView   
import acq4.pyqtgraph as pg
from acq4.pyqtgraph.Qt import QtGui, QtCore
from acq4.util.Mutex import Mutex
import win32com.client
import pythoncom

class PrairieStage(Stage):

    """
    A Prairie "Stage": Uses the PrairieView API to query the position of the Scientifica stage configured
    through PrairieView
    """
    def __init__(self, man, config, name):
        Stage.__init__(self, man, config, name)

        interval = config.get('pollInterval', 0.1)

        self.scale = config.get('scale', (1e-6, -1e-6, -1e-6)) #Flip y and z from what Prairie reports 
        # include a pollInterval in the configuration; how often should the stage position be queried
        # if not included, set to 100 ms

        #self.prairieDevice = man.getDevice('PrairieDevice')

        self.pv = PrairieView()

        self.stageThread = PrairieStageThread(interval, self.scale, self.pv)
        self.stageThread.start()
        self.stageThread.positionChanged.connect(self.posChanged)

        # clear cached position for this device and re-read to generate an initial position update
        self._lastPos = None
        #self.getPosition(refresh=True)

        self._lastMove = None
 
        #man.sigAbortAll.connect(self.stop)

    def capabilities(self):

        if 'capabilities' in self.config:
            return self.config['capabilities']

        else:
            return {
                'getPos': (True, True, True),
                'setPos': (False, False, True), #Cannot move the stage, but can move focus (Moving the stage is not yet implemented)
                'limits': (False, False, False)
            }

    def _move(self, abs, rel, speed, linear):
        """Must be reimplemented by subclasses and return a MoveFuture instance.
        """
        ## position arguments are in meters
        with self.lock:
            pos = self._toAbsolutePosition(abs, rel)
            #if pos[0] is not None or pos[1] is not None:
            #    raise Exception("X and Y movement are not implemented. Position requested was %s" % str(pos))

            if linear and (pos.count(None) < 2):
                raise Exception("PrairieView does not support diagonal movement.")

            if self._lastMove is not None and not self._lastMove.isDone():
                raise Exception("Previous PrairieView move is not finished.")

            self._lastMove = PrairieMoveFuture(self, pos, None)
            return self._lastMove


    def stop(self):
        """Stop moving the device immediately.
        """
        raise NotImplementedError()

    def targetPosition(self):
        """If the stage is moving, return the target position. Otherwise return 
        the current position.
        """
        with self.lock:
            if self._lastMove is None or self._lastMove.isDone():
                return self.getPosition()
            else:
                return self._lastMove.targetPos


    def _getPosition(self):
        # Called by superclass when user requests position refresh
        with self.lock:
            pos = self.pv.getPos()
            pos = [pos[i] * self.scale[i] for i in (0, 1, 2)]
            if pos != self._lastPos:
                self._lastPos = pos
                emit = True
            else:
                emit = False

        if emit:
            # don't emit signal while locked
            self.posChanged(pos)

        return pos


    def quit(self):
        self.stageThread.quit() # will eventually cause break in the run method of PrairieStageThread
        self.stageThread.wait(10000) #wait 10 seconds for disconnect from Prairie



class PrairieStageThread(Thread):

    """ Thread used to query stage position from PrairieView.

    Emits a signal when the stage position is different from the last query
    """

    positionChanged = QtCore.Signal(object) 
    # Emitted when the stage position has changed from the last time it was queried. The query 
    # interval is specified when initializing PrairieStageThread and ultimately comes from the 
    # user-specified config

    def __init__(self, interval, scale, prairieView):
        self.stopped = False

        self.scale = scale

        self.pos = np.zeros(3)
        self.prairieView = prairieView

        self.interval = interval #interval defined in config

        Thread.__init__(self)


    def start(self):
        self.stopped = False
        Thread.start(self)


    def stop(self):
        self.stopped = True #will cause break in run()

    def quit(self):
        self.stop() #quit method


    def run(self):


        try:
            while True:
                if self.stopped:
                    break

                if not self.prairieView.connected:
                    self.prairieView.connect_to_prairie() #Connect to Prairie

                if not self.prairieView.connected:
                    time.sleep(1) 
                    # If connection failed or becomes disconnected at run-time, wait 1 second
                    # before trying again
                    continue

                x = float(self.prairieView.call_pl('-GetMotorPosition X')[0])*self.scale[0]
                y = float(self.prairieView.call_pl('-GetMotorPosition Y')[0])*self.scale[1]
                z = float(self.prairieView.call_pl('-GetMotorPosition Z')[0])*self.scale[2]

                pos = np.array([x, y, z]) 
                #print pos

                #if type(z) != np.float:
                    #print z

                #if type(x) != np.float:
                    #print x

                #if type(y) != np.float:
                    #print y

                if any(pos != self.pos): # only emit a signal if tany change in position
                    self.pos = pos # reset the position
                    #print self.pos
                    self.positionChanged.emit(self.pos) # emit a signal

                time.sleep(self.interval) #wait for a user defined interval

        finally:

            #self.pl.Disconnect() # clear disconnect or PrairieView crashes
            self.prairieView.quit()
            # if a clean disconnect occured, this line will be printed in the acq4 console


class PrairieMoveFuture(MoveFuture):

    def __init__(self, dev, pos, speed=None):
        MoveFuture.__init__(self, dev, pos, None)
         
        target = pos[2]/self.dev.scale[2]
        self.dev.pv.move('Z', target)

    def wasInterrupted(self, debug=False):
        """Return True if the move was interrupted before completing.
        """
        self.update()
        with self.lock:
            reachedTarget = self._reachedTarget

        if debug:
            print "     in wasInterrupted...     reachedTarget:",reachedTarget,  " moving:", self.isMoving()
        if reachedTarget:
            return False
        elif self.isMoving():
            return False
        else:
            return True

        #return not reachedTarget and not self.isMoving()
        

    def isMoving(self, interval=0.25):
        pos1 = self.dev.getPosition(refresh=True)
        time.sleep(interval)
        pos2 = self.dev.getPosition(refresh=True)

        if pos1 != pos2:
            return True
        else:
            return False

        #### TODO:
        #   -get rid of sleep
        #   -instead, get a position and a time
        #   -if it is a new position save them
        #   -if it is the same position, ask if it's been more than
        #    interval and return False if it has
        #    