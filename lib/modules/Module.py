# -*- coding: utf-8 -*-


class Module:
    def __init__(self, manager, name, config):
        self.name = name
        self.manager = manager
        self.config = config
    
    def window(self):
        if hasattr(self, 'win'):
            return self.win
        return None
    
    def quit(self):
        """Must be called after modules exit."""
        self.manager.moduleHasQuit(self)
        
    
    