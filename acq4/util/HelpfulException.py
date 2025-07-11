import sys


class HelpfulException(Exception):
    """Allows for stacked exceptions.
        Initialization:
           message: The error message to the user. ex: Device could not be found.
           exc:
               The original exception object
           reasons:
               List of reasons why the exception may have occurred. ex:
                   ["Device initialization failed during startup.", "Device Gui was closed."]
           docs:
               Referral to documentation.
        When you catch a HelpfulException, you can add additional information to the original exception.
   """
    def __init__(self, message='', exc=None, reasons=None, docs=None, **kwargs):
        Exception.__init__(self, message)
        self.kwargs = kwargs
        if exc is None:
            exc = sys.exc_info()
        self.oldExc = exc
        
        if reasons is None:
            self.reasons = []
        else:
            self.reasons = reasons
            
        if docs is None:
            self.docs = []
        else:
            self.docs = docs
