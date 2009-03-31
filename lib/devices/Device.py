# -*- coding: utf-8 -*-

class Device:
    """Abstract class defining the standard interface for Device subclasses."""
    def __init__(self, deviceManager, config, name):
        pass
    
    def createTask(self):
        pass
    
    def __del__(self):
        self.quit()
        
    def quit(self):
        pass
    
    def prepareProtocol(cmd):
        ## Read configuration, configure tasks
        ## Return a handle unique to this task
        raise Exception("Function prepareProtocol() not defined in this subclass!")
        
    ## This should not be needed.
    #def setHolding(self):
        #"""set all channels for this device to their configured holding level"""
        #raise Exception("Function setHolding() not defined in this subclass!")

    def deviceInterface(self):
        """Return a widget with a UI to put in the device rack"""
        raise Exception("Function devRackInterface() not defined in this subclass!")
        
    def protocolInterface(self):
        """Return a widget with a UI to put in the protocol rack"""
        raise Exception("Function protocolInterface() not defined in this subclass!")


class DeviceTask:
    def __init__(self, command):
        pass
    
    def configure(self, tasks):
        pass
    
    def reserve(self):
        pass
    
    def start(self):
        pass
    
    def isDone(self):
        pass
    
    def stop(self):
        pass
    
    def release():
        pass
    
    def getResult(self):
        pass