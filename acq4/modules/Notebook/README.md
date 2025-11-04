# Notebook Module

The Notebook module provides integration with Jupyter notebooks in ACQ4, allowing you to create, view, and manage computational notebooks alongside your experimental data.

## Features

- **Create and manage notebooks** - Create new Jupyter notebooks directly within ACQ4
- **Data Manager integration** - Notebooks are tracked and saved in your current data directory
- **Multiple viewing options**:
  - Embedded Voila viewer (if PyQtWebEngine is installed)
  - External Jupyter Lab/Notebook
  - System browser
- **File browsing** - Browse all notebooks in the current data directory

## Installation

### Required Dependencies

The basic module requires only the standard ACQ4 dependencies.

### Optional Dependencies

For enhanced functionality, install these optional packages:

```bash
# For embedded notebook viewing
pip install PyQtWebEngine

# For external Jupyter editing
pip install jupyterlab

# For Voila rendering
pip install voila
```

## Configuration

Add the Notebook module to your ACQ4 configuration file (e.g., `default.cfg`):

```yaml
modules:
    Notebook:
        module: 'Notebook'
        shortcut: 'F9'  # Optional keyboard shortcut
        config: {}
```

## Usage

### Creating a New Notebook

1. Open the Data Manager and select a directory for your experiment
2. Open the Notebook module
3. Click "New Notebook" in the toolbar
4. Enter a name for your notebook
5. The notebook is created and tracked in the Data Manager

### Viewing/Editing Notebooks

The module provides several options for working with notebooks:

- **Open in Jupyter** - Launch Jupyter Lab or Notebook for full editing capabilities
- **View with Voila** - Display the notebook interactively in the embedded web view (requires PyQtWebEngine and Voila)
- **Open in Browser** - Open the notebook file in your system browser

### Integration with Data Manager

Notebooks created through this module are:
- Automatically saved in the current Data Manager directory
- Tracked in the directory's `.index` file with metadata
- Listed in the file browser along with other experiment data
- Backed up and versioned with your experimental data

## File Type Support

The module includes a `NotebookFile` FileType that enables:
- Automatic recognition of `.ipynb` files
- Reading and writing notebook JSON format
- Metadata storage in the Data Manager
- Integration with other ACQ4 data types

## Workflow Example

A typical analysis workflow might look like:

1. Acquire data using ACQ4 acquisition modules (Camera, Patch, etc.)
2. Create a new notebook in the same directory
3. Open the notebook in Jupyter Lab
4. Write analysis code that loads ACQ4 data files
5. Generate figures and results
6. Save the notebook (it's already tracked in the Data Manager)
7. View the executed notebook using Voila for presentation

## Performance Considerations

To prevent performance degradation in ACQ4:

- **Voila runs in a subprocess** - The Voila server is launched as a separate process, isolating it from the ACQ4 event loop
- **Lazy loading** - Servers are only started when needed
- **External editor option** - For heavy editing work, use external Jupyter Lab to avoid loading the Qt application
- **Selective viewing** - The embedded viewer is optional; use external tools if preferred

## Architecture

The Notebook module consists of:

- **`Notebook.py`** - Main module class that integrates with ACQ4 Manager
- **`NotebookWindow.py`** - Qt-based UI with file browser and viewer
- **`NotebookFile.py`** (in `acq4/filetypes/`) - FileType for `.ipynb` files

## Troubleshooting

### "QWebEngineView is not available"

Install PyQtWebEngine:
```bash
pip install PyQtWebEngine
```

Or use the "Open in Jupyter" or "Open in Browser" buttons instead.

### "Voila is not installed"

Install Voila:
```bash
pip install voila
```

Or use the "Open in Jupyter" button for editing instead.

### "No directory selected in Data Manager"

Open the Data Manager module and select a directory before creating or viewing notebooks.

## License

Distributed under MIT/X11 license. See license.txt for more information.
