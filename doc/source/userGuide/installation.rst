Installation
============

Data Acquisition with ACQ4
--------------------------

For users who want to set up ACQ4 for data acquisition, we provide an automated installer that
handles the installation of ACQ4 and its dependencies.

Windows
~~~~~~~

.. code-block:: bat

    curl -o install_acq4.bat http://acq4.org/install_acq4.bat && install_acq4.bat && del install_acq4.bat

Which will create a desktop shortcut to launch ACQ4.

Linux
~~~~~

.. code-block:: bash

    wget http://acq4.org/install_acq4.sh -O install_acq4.sh && bash install_acq4.sh && rm install_acq4.sh

After installation, you can start ACQ4 by running:

.. code-block:: bash

    cd acq4/acq4
    conda activate ../conda_env
    python -m acq4 -x

Data Access and Analysis with ACQ4
----------------------------------

For users who want to access and analyze data recorded with ACQ4, we recommend installing ACQ4 via pip:

.. code-block:: bash

    pip install acq4

Or alternately, you can clone the git repository and install in editable mode:

.. code-block:: bash

    git clone https://github.com/acq4/acq4.git
    cd acq4
    pip install -e .

The ACQ4 package can then be imported in python scripts for data access and analysis:

.. code-block:: python

    from acq4.util.DataManager import getDirHandle

    dm = getDirHandle('/path/to/acq4/data/')
    # ...access and analyze data
