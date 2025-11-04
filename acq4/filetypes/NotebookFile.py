"""
NotebookFile.py - FileType for Jupyter notebook (.ipynb) files
Distributed under MIT/X11 license. See license.txt for more information.

This class handles reading and writing Jupyter notebook files (.ipynb)
which are JSON-formatted files containing code, markdown, and outputs.
"""

import os
import json

from .FileType import FileType


class NotebookFile(FileType):
    """FileType implementation for Jupyter notebook (.ipynb) files."""

    extensions = [".ipynb"]
    dataTypes = [dict]
    priority = 50

    @classmethod
    def write(cls, data, dirHandle, fileName, **args):
        """Write notebook data to a .ipynb file.

        Parameters
        ----------
        data : dict
            Notebook data structure (should contain 'cells', 'metadata', etc.)
        dirHandle : DirHandle
            Directory handle where the file should be written
        fileName : str
            Name of the file to write
        **args
            Additional arguments (unused)

        Returns
        -------
        str
            The actual filename written (with extension added if needed)
        """
        # Ensure file has .ipynb extension
        if not any(ext in fileName for ext in cls.extensions):
            fileName = f"{fileName}.ipynb"

        # Validate basic notebook structure
        if isinstance(data, dict):
            # Ensure minimal notebook structure
            if 'cells' not in data:
                data = {
                    'cells': [],
                    'metadata': data.get('metadata', {}),
                    'nbformat': data.get('nbformat', 4),
                    'nbformat_minor': data.get('nbformat_minor', 4)
                }

        # Write JSON with proper formatting
        filePath = os.path.join(dirHandle.name(), fileName)
        with open(filePath, 'w', encoding='utf-8') as fh:
            json.dump(data, fh, indent=1, ensure_ascii=False)

        return fileName

    @classmethod
    def read(cls, fileHandle):
        """Read a Jupyter notebook file.

        Parameters
        ----------
        fileHandle : FileHandle
            Handle to the notebook file to read

        Returns
        -------
        dict
            Notebook data structure containing cells, metadata, etc.
        """
        with open(fileHandle.name(), 'r', encoding='utf-8') as fh:
            return json.load(fh)

    @classmethod
    def acceptsData(cls, data, fileName):
        """Check if this FileType can write the given data.

        Accepts dict data that has notebook structure or if filename suggests notebook.
        """
        if not isinstance(data, dict):
            return False

        # Check if filename suggests notebook
        if any(ext in fileName.lower() for ext in cls.extensions):
            return cls.priority

        # Check if data has notebook structure
        if 'cells' in data or 'nbformat' in data:
            return cls.priority

        # Generic dict might be notebook metadata
        return cls.priority // 2

    @classmethod
    def createEmptyNotebook(cls, title="Untitled"):
        """Create an empty notebook structure.

        Parameters
        ----------
        title : str
            Title for the notebook metadata

        Returns
        -------
        dict
            A valid empty notebook structure
        """
        return {
            "cells": [],
            "metadata": {
                "kernelspec": {
                    "display_name": "Python 3",
                    "language": "python",
                    "name": "python3"
                },
                "language_info": {
                    "name": "python",
                    "version": "3.8.0"
                },
                "title": title
            },
            "nbformat": 4,
            "nbformat_minor": 4
        }
