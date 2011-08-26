from lib.Manager import getManager


def logMsg(*args, **kwargs):
    """See lib.LogWindow.logMsg() for arguments and how to use."""
    getManager().logMsg(*args, **kwargs)
    
#def logExc(exc, tags=None):
    #if isinstance(exc, HelpfulException):
        #pass
    #else:
        #logMsg(exc.message, exception=exc)

def logExc(*args, **kwargs):
    getManager().logExc(*args, **kwargs)
    
class HelpfulException(Exception):
    
    def __init__(self, message, **kwargs):
        Exception.__init__(self, message)
        self.kwargs = kwargs
        self.prependedMsgs = []
        
    def prependMsg(self, msg):
        self.prependedMsgs.insert(0, msg)