Key Utilities and Patterns
===========================

Interface System
----------------

Component discovery and capability declaration using ``acq4/Interfaces.py``:

.. code-block:: python

    # Register a component:
    self.dm.declareInterface(name, ['device'], self)

    # Discover components:
    if hasattr(obj, 'implements') and obj.implements('my_api'):
        # Safe to use API methods

DataManager
-----------

Handle-based file/directory access (thread-safe) using ``acq4/util/DataManager/``:

.. code-block:: python

    from acq4.util.DataManager import getDataManager, getDirHandle

    dm = getDataManager()
    dirHandle = dm.getDirHandle('/path/to/data')
    fileHandle = dirHandle['filename.ext']
    data = fileHandle.read()
    dirHandle.writeFile(data, 'output.ma')

Resource Locking
----------------

Prevent device conflicts using mutex locks (``acq4/util/Mutex.py``):

.. code-block:: python

    # Recommended context manager pattern:
    with device.reserved():
        device.doSomething()

    # Multiple device reservation:
    with manager.reserveDevices(['dev1', 'dev2'], block=True, timeout=20):
        # Safe to operate on dev1 and dev2

Manager Access
--------------

.. code-block:: python

    from acq4.Manager import getManager

    manager = getManager()  # Get current manager singleton
    # or often instances will keep a reference at `self.dm`

Task Execution
--------------

Tasks coordinate multi-device operations:

.. code-block:: python

    # Task creation:
    task = manager.createTask(cmd)
    task.execute()  # Run all device tasks
    result = task.getResult()

Dependency management relies on ``getConfigOrder()`` and ``getStartOrder()`` to declare task sequencing.

Data Formats and I/O
====================

MetaArray (Primary Data Format)
--------------------------------

.. code-block:: python

    from MetaArray import MetaArray as MA

    # Create with metadata:
    data = MA(array_data, info=[
        {'name': 'Time', 'units': 's', 'values': time_array},
        {'name': 'Channel', 'values': ['Voltage', 'Current']},
    ])

    # Access with named indexing:
    voltage = data['Channel', 'Voltage']

File Type System
----------------

Custom file handlers in ``acq4/filetypes/``:

* Each FileType declares ``extensions``, ``dataTypes``, and ``priority``
* Implements ``read(fileHandle)`` and ``write(data, dirHandle, fileName)``
* The system automatically selects appropriate handlers based on priority

Common Development Tasks
========================

When working with this codebase:

1. Follow existing patterns for adding new devices or modules.
2. Use the Interface system for component discovery.
3. For UI work, check existing modules for patterns and conventions.
4. Use device locking when extended operations require continuous hardware control.
5. Keep heavy processing off the Qt GUI thread; otherwise call ``Qt.QApplication.processEvents()`` in
   long loops.
6. Access data files through DataManager handles, not direct file operations.
7. Use unit constants from ``pyqtgraph.units``; store values in unscaled SI units.
8. DeviceTask lifecycle: configure → start → isDone → getResult.
