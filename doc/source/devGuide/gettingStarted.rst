Getting Started with Development
=================================

Setting up a development environment
------------------------------------

If you already have a working ACQ4 installation from the user guide
(see `Installation <installation.html>`_), you can use that as-is for development.

If you would like to check out ACQ4 from git manually, you will need a python 3.12 environment.
These instructions demonstrate using conda, but any valid python environment should do.

.. code-block::

    git clone https://github.com/acq4/acq4.git
    cd acq4
    conda create --name acq4 python=3.12
    conda activate acq4
    pip install -e .[dev]

Other optional dependencies can be specified (separated by commas) in addition to `dev`:
 * `hardware` - for hardware support (NIDAQmx, Sensapex, etc)
 * `ml-models` - for computer vision features
 * `analysis` - for some legacy analysis tools
 * `docs` - for building the documentation

See pyproject.toml for what those dependencies are.

Starting ACQ4
-------------

.. code-block:: bash

    python -m acq4 -x

Look through the other `--help` options for more ways to start ACQ4.

Running Tests
-------------

.. code-block:: bash

    # Run all tests
    pytest

    # Run specific test file
    pytest acq4/tests/test_geometry.py

    # Run specific test module
    pytest acq4/devices/tests/test_OdorDelivery.py

    # Run tests with verbose output
    pytest -v

Technology Notes
----------------

* The UI and acquisition stacks are Qt-heavy with many scientific and ML dependencies.
* Import Qt from the unified wrapper: ``from acq4.util import Qt`` for cross-backend compatibility.
* PyQtGraph is used extensively for UI components, especially data visualization.
