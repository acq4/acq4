

class HelpfulException(Exception):
    """Allows for stacked exceptions.
        Initiation:
           message: The error message to the user. ex: Device could not be found.
           exc: The original exception object
           reasons: Reasons why the exception may have occurred. ex: "a. Device initialization failed during startup. b. Device Gui was closed."
           docs: Referral to documentation.
        When you catch a HelpfulException:
           -- add additional information to the original exception
           -- use self.prependErr("Additional message, ex: Protocol initiation failed. ", exc, reasons="a. A device could not be found.", docs='')
           """
    def __init__(self, message='', exc=(None, None, None), reasons='', docs='', **kwargs):
        Exception.__init__(self, message)
        self.kwargs = kwargs
        self.excs=[exc]
        self.messages = [message]
        self.reasons = [reasons]
        self.docs=[docs]
        
    def prependErr(self, msg, exc, reasons='', docs=''):
        self.messages.insert(0, msg)
        self.excs.insert(0, exc)
        self.reasons.insert(0, reasons)
        self.reasons.insert(0, docs)
    