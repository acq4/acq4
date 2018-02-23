from acq4.modules.Module import Module
from PyQt4 import QtGui, QtCore


class SolutionEditor(Module):
    """Manages a database of experimental reagents, solutions, and recipes.
    """
    def __init__(self, manager, name, config):
        from pycsf.editor import SolutionEditorWindow
        from pycsf.core import SolutionDatabase
        
        Module.__init__(self, manager, name, config) 
        self.man = manager
        self.db = SolutionDatabase()
        self.win = SolutionEditorWindow(db=self.db)
        if 'recipeFile' in config:
            self.win.loadFile(config['recipeFile'])
        else:
            self.db.loadDefault()

        self.win.show()
        self.win.tabs.setCurrentIndex(2)
