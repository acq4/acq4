Getting Started with Development
=================================

Development Environment
-----------------------

Setting up a development environment
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

    # Clone the repository
    git clone https://github.com/acq4/acq4.git
    cd acq4

    # Create and activate a conda environment
    conda env create --name=acq4 --file=tools/requirements/acq4-torch.yml
    conda activate acq4

    # Install ACQ4 in development mode
    pip install -e .

Starting ACQ4
-------------

.. code-block:: bash

    python -m acq4 -x

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
* Requirements are stored in ``tools/requirements/acq4-torch*``; treat those environment files as the
  source of truth when new packages are needed.
