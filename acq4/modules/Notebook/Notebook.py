"""
Notebook Module - Integration of Jupyter notebooks with ACQ4
Copyright 2025
Distributed under MIT/X11 license. See license.txt for more information.

This module provides integration with Jupyter notebooks, allowing users to
create, view, and edit notebooks within the ACQ4 environment. It tracks
notebooks through the Data Manager and can render notebooks using Voila.
"""

import os

from acq4.modules.Module import Module
from .NotebookWindow import NotebookWindow


class Notebook(Module):
    """Module for Jupyter notebook integration in ACQ4.

    This module provides:
    - Creating and managing Jupyter notebooks
    - Viewing notebooks with Voila or static rendering
    - Integration with Data Manager for tracking notebooks
    - Launching external Jupyter for full editing capabilities
    """

    moduleDisplayName = "Notebook"
    moduleCategory = "Utilities"

    def __init__(self, manager, name, config):
        """Initialize the Notebook module.

        Parameters
        ----------
        manager : Manager
            The ACQ4 Manager instance
        name : str
            Name of this module instance
        config : dict
            Configuration dictionary from the ACQ4 config file
        """
        Module.__init__(self, manager, name, config)
        self.ui = NotebookWindow(self, config)

        # Set window icon if available
        mp = os.path.dirname(__file__)
        icon_path = os.path.join(mp, 'icon.png')
        if os.path.exists(icon_path):
            from acq4.util import Qt
            self.ui.setWindowIcon(Qt.QIcon(icon_path))

        # Declare interface for other modules to discover
        manager.declareInterface(name, ['notebookModule'], self)

    def window(self):
        """Return the main window widget.

        Returns
        -------
        NotebookWindow
            The main UI window for this module
        """
        return self.ui

    def quit(self, fromUi=False):
        """Clean up resources when module is closed.

        Parameters
        ----------
        fromUi : bool
            True if quit was initiated from the UI
        """
        if not fromUi:
            self.ui.quit()
        Module.quit(self)

    def getCurrentDir(self):
        """Get the current data directory from the Manager.

        Returns
        -------
        DirHandle or None
            The current directory handle, or None if not set
        """
        return self.manager.getCurrentDir()
