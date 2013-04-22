The Data Manager Module
=======================

The Data Manager provides an interface to browse through data. Use it to:

    * Create new folders and specify where data should be saved during aquisition.
    * Browse through and annotate data that has been collected.
    * Access analysis modules.

Configuration
-------------

There are two important config files for the Data Manager: default.cfg and folderTypes.cfg.

default.cfg
+++++++++++

While this is the main configuration file for the Acq4 Manager module, it has important implications for the Data Manager. These are the default Storage Directory, and the configurations. You can create different configurations for each user, or for each way of accessing data (for example, data that is on an internal harddrive vs. an external drive).

Specify the default storage directory (the directory that Data Manager will open up to if no individual configurations are selected) by giving a directory path after the key::

    storageDir: "\C:\Documents\Data\junk"
    
If you have multiple users, we recommend setting the default to a communnal folder, and giving each user their own configuration, like so::

    configurations:
        Luke:
            storageDir: "c:\\Documents\Luke"
        Megan:
            storageDir: "c:\\Documents\Megan"
            
In the default.cfg file you also need to specify folderTypes. We usually do this by pulling in a separate folderTypes config file::

    folderTypes: readConfigFile('folderTypes.cfg')
    
folderTypes.cfg
+++++++++++++++

The folderTypes config file specifies the special types of folders you may want to use to store your data. We currently have folders for Days, Slices, Cells, Sites, and Pairs. These are completely modifiable and it is easy to add new types. In a Data Manager these types are available under the New.... drop down menu. Each of the types has it's own fields to fill in, making it easy to make meta data uniform. Specify folder types like so (each keyword under info appears as a field):

    Day:                    
        name: "%Y.%m.%d"            
        info:
            description: "text", 6          
            species: "list", ["CBA Mouse", "DBA Mouse", "Rat"] 
            age: "string" 
            sex: "list", ['M', 'F']
            weight: "string"
            temperature: "list", ['34C', '25C', '37C']
            solution: "list", ["Standard ACSF", "Physiological ACSF"]

Each folder type needs to have a name and info. The name can be a date (like in the Day folder) or it can simply be "slice" or "cell". When the folder is created a three digit specifier will be added to the name, so in one Day folder you could have multiple subfolders, for example: slice_000, slice_001 and slice_002. 

Within info you can specify any number of fields that will always appear when you create a new folder of that type. There are 3 types of fields: "text", "string", and "list". 

    * "text" and "string": Both create an empty field where text can be entered. (LUKE! How are these different and what do the numbers after them mean?)
    * "list": Creates a drop down menu where the user can select any of the items that are listed in the brackets. The user is not limited to the items in the list, they will also have the option of typing in whatever they like. 

Acquisition
-----------

During acquisition you will use the Data Manager to specify where your data is stored and annotate the data as you collect it. 

The top-level directory is shown at the top. Everything that is in this directory will appear in the file list on the left side of the window. The Data Manager opens to the top-level directory that is specified in the default.cfg file. To (temporarily) change the top-level directory, click the "..." button. 

By default, no storage directory is set. When you create a new folder (of any type) that folder becomes the storage directory. To set a storage directory without creating a new folder (for example after restarting the program during the middle of an experiment) select the storage directory that you want in the list on the left. Then click "Set". The path to that folder should appear in the Storage Directory box.

Creating new folders
++++++++++++++++++++

We usually create folders in a hierarchy starting with Day, then Slice, then Cell, Pair or Site. Because of this hierarchy, folders of different types will automatically be created within the previous folder. For example, the Slice folder will be created within the Day folder, and the Cell folder will be created within the Slice folder. However, when you create two folders of the same type, they will be created at the same hierarchical level. For example, if you patch multiple cells within one slice, after creating the first Cell folder (cell_000), when you create a new Cell (cell_001) folder it will be created within the slice folder. If you switch slices and create a new slice folder, it will be created within the Day folder. The order of the hierarchy is determined by the order that you first create folders in. If you first create a Day folder, then a Cell folder, then a Slice folder, the slice folder will be created within the Cell folder which will be created within the Day folder. 

Annotating and Log
++++++++++++++++++

In addition to specific fields, each folder type and each data file have a Notes field. Here notes can be made about the data in the folder - for example you might note that a Cell was slightly depolarized, or looked like a dendrite had been cut. You can enter information into the notes field at any time, so you can also put notes about analysis here. 

There is also a way to create notes about the entire day using the log. On startup the Log should appear at the bottom of the Data Manager. Log entries are timestamped, so are useful for noting things that affect the whole experiment from then on, like adding drugs to solution. To access the log after the experiment click on the Log tab.

Analysis
--------

The Data Manager is also the gateway for getting to the Analysis modules. To access analysis modules, click on the Analysis tab. Some of the modules (ex: PhotoStim) require you to have a database specified. Acq4 analysis currently uses sqlite databases. You can create an sqlite database by clicking "Create" or select a previously existing sqlite database by clicking "Open". I'm not sure what "Refresh" does LUKE????.

Data Model is used as a translation step between the data and the analysis. It basically takes data collected from any setup and organizes it so that the Analysis modules can make sense of it. For example, voltage traces on different rigs might by saved as "Clamp1.ma" or as "Axopatch.ma" and have different metadata depending on which device was used. Data Model will recognize both of these files as voltage traces and allow the Analysis software to interact with them both. However, creating new Data Models or adjusting them to fit any system currently requires some knowledge of python programming. If you need help with this, ask Luke.

Different analysis modules are accessed through the drop down menu on the right. Most of these analysis modules are still in development, so you should expect them to change frequently for the next while. 