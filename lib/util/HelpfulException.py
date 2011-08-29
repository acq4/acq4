## test to see if new branch is working

class HelpfulException(Exception):
    
    def __init__(self, message, **kwargs):
        Exception.__init__(self, message)
        self.kwargs = kwargs
        self.prependedMsgs = []
        
    def prependMsg(self, msg):
        self.prependedMsgs.insert(0, msg)