## test to see if new branch is working
from __future__ import print_function
import sys

class HelpfulException(Exception):
    """Allows for stacked exceptions.
        Initalization:
           message: The error message to the user. ex: Device could not be found.
           exc: The original exception object
           reasons: Reasons why the exception may have occurred. ex: "a. Device initialization failed during startup. b. Device Gui was closed."
           docs: Referral to documentation.
        When you catch a HelpfulException:
           -- add additional information to the original exception
           -- use self.prependErr("Additional message, ex: Protocol initiation failed. ", exc, reasons="a. A device could not be found.", docs='')
           """
    def __init__(self, message='', exc=None, reasons=None, docs=None, **kwargs):
        Exception.__init__(self, message)
        self.kwargs = kwargs
        if exc is None:
            exc = sys.exc_info()
        self.oldExc = exc
        
        #self.messages = [message]
        if reasons is None:
            self.reasons = []
        else:
            self.reasons = reasons
            
        if docs is None:
            self.docs = []
        else:
            self.docs = docs
        
    #def prependErr(self, msg, exc, reasons='', docs=''):
        #self.messages.insert(0, msg)
        #self.excs.insert(0, exc)
        #self.reasons.insert(0, reasons)
        #self.reasons.insert(0, docs)
    