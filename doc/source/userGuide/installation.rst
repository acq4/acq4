Installation
============

ACQ4 depends on several free software packages to work properly. We provide interactive installer scripts that handle the complete installation process, including optional dependencies and hardware-specific packages.

1. We use conda to create and manage the python environments used by acq4. If you do not already have conda available, download and install `Miniconda <https://docs.conda.io/en/latest/miniconda.html>`_ (recommended) or `Anaconda <https://www.anaconda.com/download/>`_.

2. We use git to download the source code of acq4, automatically apply updates, and track local changes to the code. If you do not already have git available, download and install from `<https://git-scm.com/downloads>`_.

3. Clone the ACQ4 source repository. The commands below must be run from a console, and will download the acq4 source code into a new directory called `acq4` in the current working directory::

    git clone https://github.com/acq4/acq4.git
    cd acq4

4. Quick Installation (Recommended). These scripts automatically execute the steps listed below under "(alt) Manual Installation"

   **Linux/macOS:**::

    ./tools/install.sh

   **Windows (from Anaconda Prompt):**::

     tools\install.bat

   The installer will ask you to:

   - Choose an environment name (default: acq4)
   - Select optional dependencies for enhanced functionality (GPU acceleration, advanced analysis tools, etc.)
   - Select hardware-specific drivers for your equipment (NIDAQmx, Sensapex, μManager, etc.)

5. (alt) Manual Installation

  1. Create a conda environment for acq4::

      conda env create --name=acq4 --file=tools/requirements/acq4-torch.yml
      conda activate acq4

  2. Install acq4 into your new conda environment::

      pip install -e .

  3. Consider which of the rest of these dependencies you need, and install them as needed.

     **Non-Dev Libraries:**

     Unless you're actively developing ACQ4 or these libraries, or have explicit custom features in use,
     you need to install all the libraries listed in `tools/requirements/non-dev-deps.txt` to ensure
     full functionality. Development envs will likely want to install local, editable versions of these
     packages instead.

     The interactive installer will prompt you to install these components, or you can install them all
     manually with::

         pip install -r tools/requirements/non-dev-deps.txt

     **Hardware Support:**

     Hardware-specific packages can be installed as needed:
       - `pydaqmx` for National Instruments DAQmx devices
       - `sensapex-py` for Sensapex micromanipulators and stages
       - `pymmcore` for μManager camera and device control

     See `tools/requirements/hardware-deps.txt` for a full list of hardware-specific packages. You can install all of them with::

         pip install -r tools/requirements/hardware-deps.txt

     **GPU Acceleration:**

     ACQ4 can use nVidia GPUs to offload image processing if the `cupy` python package is installed. See
     the `cupy documentation <https://docs.cupy.dev/en/stable/install.html>`_ for more information on
     configuring CUDA and cupy correctly.

Starting ACQ4
-------------

To start acq4, first activate your `acq4` conda environment (or a different environment name if you chose a different one) from a conda-enabled command prompt::

    conda activate acq4
    python -m acq4

This should load the main manager window, from which you can interact with some devices and load modules. If this is a fresh installation with the default configuration files, 
acq4 will start with a demo configuration that includes several mock devices for testing. 


Legacy Python 2 support
-----------------------

For systems that still require python 2 support, the ``python2`` git branch contains the most recent ACQ4 version known to support python 2. More information can be found in the README for that branch: https://github.com/acq4/acq4/tree/python2
