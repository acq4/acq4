from acq4.modules.Module import Module
from acq4.util import Qt


class SolutionEditor(Module):
    """Manages a database of experimental reagents, solutions, and recipes.

    Requires pycsf, which is available at github.com/AllenInstitute/pycsf

    Configuration options:

    * recipeFile : location of a recipe file to load by default. It is recommended to 
      keep this file under git revision control. If not specified, then the default
      databse will be loaded.
    """
    moduleDisplayName = "Solution Editor"
    moduleCategory = "Utilities"

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
