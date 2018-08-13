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

        scale = config.get('scale', (1e-6, -1e-6, -1e-6)) #Flip y and z from what Prairie reports 
        # include a pollInterval in the configuration; how often should the stage position be queried
        # if not included, set to 100 ms

        #self.prairieDevice = man.getDevice('PrairieDevice')

        self.pv = PrairieView()

        self.stageThread = PrairieStageThread(interval, scale, self.pv)
        self.stageThread.start()
        self.stageThread.positionChanged.connect(self.posChanged)
 
        #man.sigAbortAll.connect(self.stop)

    def capabilities(self):

        if 'capabilities' in self.config:
            return self.config['capabilities']

        else:
            return {
                'getPos': (True, True, True),
                'setPos': (False, False, False), #Cannot move the stage -- can only get the position
                'limits': (False, False, False)
            }


    #def _getPosition(self):
        #return self.stageThread.getPosition()


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




