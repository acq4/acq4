# Notebook Module

The Notebook module provides integration with Jupyter notebooks in ACQ4, allowing you to create, view, and manage computational notebooks alongside your experimental data.

## Features

- **Create and manage notebooks** - Create new Jupyter notebooks directly within ACQ4
- **Data Manager integration** - Notebooks are tracked and saved in your current data directory
- **Embedded Jupyter console** - Run notebooks in-process with full ACQ4 memory access (requires qtconsole)
  - Access the Manager, devices, and all live data
  - Same memory space as ACQ4 - no subprocess isolation
  - Full IPython kernel with code completion and rich output
- **Multiple editing options**:
  - **Edit (Embedded)** - Embedded Jupyter console with ACQ4 memory access ⭐ **RECOMMENDED**
  - **Edit (External)** - External Jupyter Lab/Notebook (separate process, no ACQ4 access)
- **Viewing options**:
  - Embedded Voila viewer (if PyQtWebEngine is installed)
  - System browser
- **File browsing** - Browse all notebooks in the current data directory

## Installation

### Required Dependencies

The basic module requires only the standard ACQ4 dependencies.

### Optional Dependencies

For enhanced functionality, install these optional packages:

```bash
# For embedded Jupyter with ACQ4 memory access (HIGHLY RECOMMENDED)
pip install qtconsole

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

- **Edit (Embedded)** ⭐ **RECOMMENDED** - Open in an embedded Jupyter console that runs in the same process as ACQ4
  - Full access to ACQ4 Manager, devices, and live data
  - Variables `man`, `manager`, `pg`, `np`, `Qt` are pre-loaded
  - Execute notebook cells and interact with ACQ4 in real-time
  - Changes are NOT auto-saved to the .ipynb file (use "Edit (External)" to save)
  - Requires: `qtconsole`

- **Edit (External)** - Launch Jupyter Lab or Notebook in a separate process
  - Full Jupyter editing and saving capabilities
  - NO access to ACQ4's memory (separate process)
  - Good for editing notebook structure and saving changes
  - Requires: `jupyterlab`

- **View with Voila** - Display the notebook interactively in the embedded web view
  - Requires: `PyQtWebEngine`, `voila`

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

## Workflow Examples

### Interactive Analysis (Embedded)

1. Acquire data using ACQ4 acquisition modules (Camera, Patch, etc.)
2. Create a new notebook in the same directory
3. Click "Edit (Embedded)" to open the notebook
4. In the embedded console, you have direct access to ACQ4:
   ```python
   # Access current directory
   current_dir = man.getCurrentDir()

   # Get a device
   camera = man.getDevice('Camera')

   # Access live data from modules
   data_manager = man.getModule('Data Manager')

   # Load and analyze data files
   import acq4.util.DataManager as dm
   fh = current_dir['my_data.ma']
   data = fh.read()
   ```
5. Results and plots appear in the console
6. Variables persist in memory as long as ACQ4 is running

### Notebook Development (External)

1. Create a new notebook
2. Click "Edit (External)" to open in Jupyter Lab
3. Write and structure your analysis code
4. Save the notebook with proper markdown, code organization
5. Click "Edit (Embedded)" to run it with ACQ4 access
6. Iterate between external editing and embedded execution

## Memory Access and Performance

### Embedded Mode (In-Process)

The "Edit (Embedded)" option runs a Jupyter kernel **in the same process** as ACQ4:

✅ **Advantages:**
- Direct access to ACQ4 Manager, devices, and live data
- No serialization overhead
- Can call ACQ4 functions and access internal state
- Shared memory space - perfect for interactive analysis

⚠️ **Considerations:**
- Shares ACQ4's event loop (Qt + Jupyter)
- Long-running computations will block ACQ4 UI
- Keep computations short or use threads/processes for heavy work
- Kernel state persists as long as the Notebook module is loaded

### External Mode (Separate Process)

The "Edit (External)" option runs Jupyter in a **separate process**:

✅ **Advantages:**
- No performance impact on ACQ4
- Full Jupyter editing and saving capabilities
- Won't block ACQ4 UI

❌ **Limitations:**
- NO access to ACQ4's memory
- Can only load saved data files
- Cannot access Manager, devices, or live data

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
