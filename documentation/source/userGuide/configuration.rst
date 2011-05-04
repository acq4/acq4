Configuration
=============

Configuring ACQ4 involves editing '.cfg' files in the *config* directory. In these files, you may define:
    
    * The devices in your system
    * The list of loadable modules 
    * Data storage locations
    * Per-user configurations
    
The easiest way to get started might be to look in the **config/backups** directory at examples of the .cfg files from other systems.
    

.cfg File Syntax
----------------

It is important to first understand that a 'configuration' is a single document, but for organization this document is often split up across multiple .cfg files. At its most basic level, a configuration is a list of name:value pairs:
    
::
    
    storageDir: "/home/luke/data"
    protocolDir: "config/protocols"
    
In the example above, the name "storageDir" is assigned the value "/home/luke/data".
Values may also contain nested lists of name:value pairs:
    
::
    
    Camera:
        config:
            serial: 'PCICamera0'
            scopeDevice: 'Microscope'
            scaleFactor: (1.0, 1.0)
        driver: 'PVCam'

In this example, we have Camera.driver = 'PVCam', Camera.config.serial = 'PCICamera0', etc. This syntax allows the creation of arbitrarily complex hierarchies of configuration data. *Note that each nested level must have the same amount of indentation for each line*. 

Since this configuration tree can become quite large and complex, it is often useful to break off the larger branches and move them to a file of their own:
    
::
    
    folderTypes: readConfigFile('folderTypes.cfg')
        
This example would read the entire contents of 'folderTypes.cfg' and insert that as the value for 'folderTypes'.

Further notes about this syntax:
    
    * You can use "double" or 'single' quotes, but not "both'
    * File or directory names should be quoted and use forward slashes (/) on Linux and OSX or double-back slashes (\\\\) on Windows (eg "/home/user/data" or "C:\\\\data\\\\user").
    * Some options will call for a list of values. This can be given just by separating the values with commas inline like ``value1, value2`` or with brackets like ``[value1, value2]``
    * Finally, you may add comments to .cfg if they are preceded with a hash (#) symbol
    
    

Configuration Structure
-----------------------

When ACQ4 first starts, it reads a single configuration from **config/default.cfg**  (it is possible to override this with the -c flag). The structure of this file should look like:
    
::
    
    storageDir: "storage/dir" 
    protocolDir: "config/protocols"
    modules:
        ...
    devices:
        ...
    folderTypes: 
        ...
    configurations:
        ...
        
In this format, the storageDir specifies the *default* location where data should be stored when no other location is specified. The protocolDir specifies the location where protocols designed in the Protocol Runner module are stored. All other sections are discussed below:
    
Modules Configuration
'''''''''''''''''''''

Loading a module requires knowing both the name of the module and specifying a specific set of configuration options for the module to use. For example, I have a patch clamp amplifier with two channels. When I load the *Patch* module, I need to specify whether it should use channel 1 or channel 2. To make this process easier for the end user, we define a list of pre-configured modules which the user may choose from. These names appear in the Manager module as the list of loadable modules.

The format for defining a pre-configured module is:
    
::
    
    UniqueName:
        module: "ModuleName"
        config:
            ...config options...
        shortcut: "shortcut key"

Here, *ModuleName* must refer to one of the modules defined in the directory **lib/modules**. The exact options specified under *config* will differ depending on the module being loaded. The *shortcut key* specifies a keyboard shortcut that can be used to raise the module's window (for example: 'F2', 'Ctrl+M', or 'Alt+Enter'). Taking this example, a very common module list might look like this:
    
::
    
    modules:
        Data Manager:
            module:  'DataManager'
            shortcut: 'F2'
        Camera:
            module:  'Camera'
            shortcut: 'F5'
            config:
                camDev: 'Camera'
        Patch Clamp 1:
            module: 'Patch'
            shortcut: 'F3'
            config:
                clampDev: 'Clamp1'
        Patch Clamp 2:
            module: 'Patch'
            shortcut: 'F4'
            config:
                clampDev: 'Clamp2'
        Protocol Runner:
            shortcut: 'F6'
            module: 'ProtocolRunner'

Note in this example that the name 'Camera' is used 3 times to refer to 3 different things: 1) the name of the preconfigured module that will appear in the loadable module list, 2) the name of the module to load, and 3) the name of the camera device that should be used by this module when it is loaded.



Devices Configuration
'''''''''''''''''''''

The format for defining a device is:
    
::
    
    UniqueName:
        driver: "deviceType"
        config:
            ...
            
Here, *deviceType* refers to one of the devices defined in the directory **lib/devices** (examples: NiDAQ, MultiClamp, Microscope). The contents of *config* will depend on the device, and are described in the documentation for that device type (see :ref:`userDevices`). Refer to the example configurations in **config/backups**.


FolderTypes Configuration
'''''''''''''''''''''''''

ACQ4 gives the user full control over deciding how best to organize their raw data as it is being collected. For example, a typical user might create a folder for every day they run experiments, and a sub-folder for every cell they record from. Each folder can be annotated by the experimenter, and often we want these annotations to be consistent from day to day. To facilitate this, we can define a set of folder types with a specific list of the data that should be annotated for each type. These types appear in the Data Manager module when adding new folders, and the annotations are automatically displayed as a form to be filled out by the experimenter. 

The basic syntax for a folder type is:
    
::
    
    UniqueName:
        name: 'storageName'
        info:
            ...
            
Here, *UniqueName* is the name that will appear in the Data Manager module list of folder types. *storageName* specifies how each new folder will be named as it is created, including the possibility for date formatting ("%Y.%m.%d"). *info* is a list of name:value pairs that specify the set of meta-data fields to be included with each folder type. There are two types of input that can be specified: 
    
::
    
    fieldName1: 'text', number_of_lines
    fieldName2: 'list', ['option1', 'option2', 'option3']
    
For either field type, information will be stored as plain text. If the field type is *list*, then the user will see a drop-down menu of options to choose from (although it will still be possible to type in any arbitrary response). If the field type is *text*, then the user will simply see an empty text box to type in.


Configurations Configuration
''''''''''''''''''''''''''''

Commonly, acquisition systems will be accessed by mutiple users requiring different configuration settings. One way to achieve this is to create a completely different set of configuration files for each user and specify which to use when starting the program. A simpler way is to define just the *differences* between these configurations and select them after the program has been started. 

The *configurations* section allows us to define a set of named modifications to the default configuration. For example: all users on a system want to use the same device and module configuration, but define their own data storage directory:
    
::
    
    configurations:
        Jeffrey:
            storageDir: 'C:\\data\\jeffrey'
        Walter:
            storageDir: 'C:\\data\\walter'
        Maude:
            storageDir: 'C:\\data\\maude'
        
In the example above, the three names would appear in the Manager module as loadable configurations. This allows each user to quickly select their storage settings. The settings for each user can be anything that would appear at the top-level configuration. Thus, users can specify their own folder types, preconfigured modules, etc (however devices may not be defined here). 



