The Protocol Runner Module
==========================

The Protocol Runner is ACQ4's primary data acquisition module. It allows one to rapidly design stimulation and recording protocols using any combination of devices in the system. It can be used for relatively simple protocols, like steps of current injection, or more complex protocols like recording a response to a sequence of stimulations. 


Loader Dock
-----------

The loader dock is used to load previously saved protocols, create new protocols and save changes to protocols. The file list on the left shows all of the existing protocols. These are read from the config/protocols directory.

* To create a new protocol: Click the "New" button. Add any devices to the protocol (using the Protocol Dock, explained in the next section). Then press either the "Save" or the "Save As..." button. Name the protocol by double clicking the current name (probably something like protocol_000) and typing the name you want. 

* To create a new protocol based on an existing protocol: Load the existing protocol by selecting it in the list and pressing the "Load" button. Make any changes to it. Then, press the "Save As..." button. The "Save As..." button saves that protocol under the name of the existing protocol with _000 added to it. The original protocol is not affected. To change the name of the protocol, double-click it in the list and type the new name. 

* To load an existing protocol: Select it in the list and press the "Load" button.

* To make changes to a protocol: Load the protocol. Make your changes, then press the "Save" button.

* The "New Dir" button creates a directory that you can then move protocols into. Move protocols by selecting and dragging them to the folder you want them to be in. 

* To delete a protocol: Select the protocol and press the "Delete" button. It will then ask if you really want to delete it. Press the button (that now says "Really?") again to delete the protocol.



Protocol Dock
-------------

The Protocol Dock is where you select which devices to use in the protocol, set the length of the protocol, and run single trials of the protocol.

Selecting Devices: To include a device in the protocol, check the box next to the device. For each device that is checked, the Protocol interface for that device will appear in the lower space of the window. You can include any number of devices in the protocol. Docks may be rearranged and stacked by dragging their title bars.

* Continuous: [not yet supported]
* Duration: Sets the length of one trial of the protocol. 
* Lead Time: This forces the protocol system to reserve the selected hardware for the time specified before running the protocol. This is useful, for example, for allowing a patch clamp amplifier to settle after switching modes before making a recording.
* Loop: When checked, the protocol runs repeatedly until the "Stop Single" button is pressed. 
* Cycle Time: Specifies the time interval between runs when in loop mode.

Buttons:

* Test: Runs the protocol once (unless loop is checked) without saving any data.
* Record Single: Runs the protocol once and saves the data.
* Stop Single: Aborts the currently running recording.


Sequence Dock
-------------

Once a stimulation/recording protocol is designed, it is common to repeat that protocol mutiple times while varying parameters. Each device dock will have its own capabilities for specifying parameters to vary. Any sequence parameters in use will be displayed in the list. If there are multiple parameters, they can be re-ordered by dragging to new positions in the list. 

[more]



Analysis Dock
-------------

Lists all available plugins for online analysis. 
