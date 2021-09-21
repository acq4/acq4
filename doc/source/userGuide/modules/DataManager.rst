.. _userModulesDataManager:

The Data Manager Module
=======================

The Data Manager module allows the user to browse, view, and export data, view experiment logs, and manage annotations and other meta-data. Additionally, this module is used to specify the default storage location for data during an experiment. To streamline experiment execution, all modules record data into this default directory rather than prompting the user for a location. 

For large studies, keeping data properly annotated and organized consistently is both essential and time consuming. The Data Manager encourages consistent, hierarchical organization of data by allowing the user to define a set of directory types, each having its own set of meta-data fields. These fields may be configured by the user at the beginning of a series of experiments to encourage the user to store and annotate data with a consistent organization. During an experiment, the user simply indicates key transitions such as placing a new sample on the microscope or patching a new cell. The data manager uses these transitions to construct a hierarchy of directories which organize the experimental data and prompt the user to supply the necessary meta-data. For more information on this topic, see the :ref:`data organization tutorial <userTutorialsDataOrganization>`.
    
    .. figure:: images/dataManager.svg
    


Configuration
-------------

Although the Data Manager module does not accept any configuration options of its own, it must (like all modules) appear in the :ref:`modules section <userConfigurationModules>` of the configuration::
    
    modules:
        Data Manager:
            module: 'Data Manager'
            shortcut: 'F2'
    
The Data Manager does make use of some :ref:`system-wide configuration <userConfiguration>` settings. Most importantly, a base storage directory must be specified either on the command line using the ``-b`` flag or in the configuration::

    storageDir: "C:\\Documents\\Data"

This specifies the top-level directory from which the module will be allowed to create new sub-directories for storing data. The Data Manager module also uses the :ref:`'folderTypes' configuration settings <userConfigurationFolderTypes>` to determine what folder types the user may create, and what default metadata fields they will be given.
    

.. _userModulesDataManagerStorageDirectory:


Acquired data storage
---------------------

During most data acquisition, modules will not prompt the user for a location to store data in. Instead, modules communicate with the Data Manager, which specifies a current storage directory set previously by the user. Before acquiring any data, the user must select the desired storage folder in the Data Manager, and then click the **Set** button to the right of **Storage Directory**. The current storage directory will be highlighted red.


Creating new folders
--------------------

Users are encouraged to store experimental results in a hierarchical folder structure that best organizes ther data (see the :ref:`data organization tutorial <userTutorialsDataOrganization>`). To facilitate this, the Data Manager module includes a drop-down list of user-defined folder types that may be created at any time. When a folder type is selected from this list, a new folder is created and the current storage directory is set to this location. The location where the folder is created depends on the structure of folder types created previously:

* If the current storage directory has the same type as the new folder to be created, then the new folder is created as sibling of the current storage directory (that is, both the current storage directory and the newly created folder will exist within the same parent directory).
* Likewise, if the *parent* or *grandparent* of the current storage directory has the same type as the folder to be created, then the new folder is created as a sibling of either the parent or grandparent. 
* Otherwise, the new folder is created *within* the current storage directory. 

Folders are named using the naming rule specified in the configuration for that folder type, followed by a numerical identifier "_XXX" that increments to avoid creating duplicate names.

For example, suppose we define three folder types for storing data in slice electrophysiology experiments: 'Day', 'Slice', and 'Cell'. For each Day, there will be one or more Slices, and for each Slice there will be one or more Cells. If we create new folders in the following order: [Day, Slice, Cell, Cell, Slice, Cell, Cell], then they will be automatically organized into the following structure:
    
    Day/
        Slice_000/
            Cell_000/
            Cell_001/
        Slice_001/
            Cell_000/
            Cell_001/
            

Annotations
-----------

Each folder type defines a specific set of metadata fields which should be automatically added to the folder upon creation. After creating a folder, the **Info** tab in the Data Manager module can be used to access and edit this metadata.

    .. figure:: images/dataManagerFolderInfo.png

In addition, *all* files are automatically given a "Notes" field which may be used to provide annotations. Individual modules are also free to add extra metadata fields to any files or folders. 

Logging
-------

During data acquisition, a log directory may be selected in which system event messages will be appended to a ".log" file. This typically includes information about when tasks are started or stopped and any error messages that may have been generated. Logs may be viewed later by opening the **Log** tab in the Data Manager module.

Data display
------------

The **Data** tab is used to display the contents of individual data files. Although some file types require specialized analysis modules to view, most data collected consists of 2D images, 3D image stacks, or 2D signal-vs-time recordings. Each of these may be displayed via the Data Manager. 

