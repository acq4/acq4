Data Management
===============


Hierarchical File Storage
-------------------------



Meta Information
----------------


User-defined Folder Types
-------------------------

.. _UserGuide/dataManagement/logging:
    
Notes and Logs
--------------



.. _user-metaarray-files:
    
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


