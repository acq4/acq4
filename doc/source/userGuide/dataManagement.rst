Data Management
===============

The data management system in ACQ4 is designed to emphasize flexibility and longevity. Data is organized into a hierarchy of directories with user-defined structure. Each folder contains a human readable index file that stores annotations and other metadata related to both the folder and any files contained within it. Most data acquired by ACQ4 is stored using the HDF5 file format (www.hdfgroup.org). These files contain both the raw data arrays, for example from camera and digitized recordings, as well as meta-information related to the recordings. ACQ4 provides libraries for reading these files in both Python and MATLAB. When the data is analyzed, the results may be stored in an SQLite relational database file (www.sqlite.org). The use of industry-standard HDF5 and SQLite formats helps to ensure that data is readable by a variety of different applications, both now and in the future. 

Hierarchical File Storage
-------------------------

All directories created by ACQ4 contain a file named ".index". This file is a human-readable collection of metadata pertaining to the folder it lives in as well as all files living in that folder. During an experiment, the user may create any arbitrary hierarchy of directories (via the :ref:`Data Manager module <userModulesDataManager>`) to organize acquired data as they see fit. At any time, one folder is designated the current *storage folder*; all acquired data is stored to this location.


Meta Information
----------------

The .index files stored in each folder serve as a repository of metadata for the files in the same folder. This metadata includes automatically-generated information pertaining to the acquisition of the data, as well as user-supplied annotations. 

.. note:: Because metadata is stored separately from files, it is necessary to use the Data Manager module when moving or reorganizing these files; it will ensure that metadata is moved properly with each file.


User-defined Folder Types
-------------------------

For large studies, keeping data properly annotated and organized consistently is both essential and time consuming. The Data Manager encourages consistent, hierarchical organization of data by allowing the user to :ref:`define a set of folder types <userConfigurationFolderTypes>`, each having its own set of meta-data fields. These fields may be configured by the user at the beginning of a series of experiments to encourage the user to store and annotate data with a consistent organization. During an experiment, the user simply indicates key transitions such as placing a new sample on the microscope or patching a new cell. The data manager uses these transitions to construct a hierarchy of directories which organize the experimental data and prompt the user to supply the necessary meta-data. (More on this topic, see :ref:`Data Manager <userModulesDataManager>`)


.. _userDataManagementLogging:
    
Notes and Logs
--------------

ACQ4 manages a log file to which messages are written about acquisition events and errors as they occur. The user may also add custom messages to this log file. (More on this topic, see :ref:`Data Manager <userModulesDataManager>`)

.. _userMetaArrayFiles:
    
MetaArray Files
---------------

Raw data in ACQ4 is most commonly handled and stored using the MetaArray format. A single MetaArray consists of an N-dimensional array of values accompanied by meta-info describing the data. Here is an example of the type of data one might store as MetaArray:

.. image:: images/metaarray.png

Notice that each axis is named and can store different types of meta information:
    
* The Signal axis has named columns with different units for each column
* The Time axis associates a numerical value with each row
* The Trial axis uses normal integer indexes

MetaArrays may also include a extra meta data pertaining to the entire data set. For example, camera images are recorded along with the current exposure time, binning, region of interest, etc.

On disk, MetaArrays are stored using the standard HDF5 file format, which allows these files to be easily read by other analysis programs. 


