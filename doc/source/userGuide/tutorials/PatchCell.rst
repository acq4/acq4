.. _userTutorialsPatching:

Patching a Cell
===============

This tutorial describes a typical procedure for patching a neuron using the :ref:`Patch module<userModulesPatch>`, :ref:`Camera module<userModulesCamera>`, and :ref:`Data Manager module<userModulesDataManager>`.

#. Open the :ref:`Camera module<userModulesCamera>`.
    #. Start the camera
    #. Focus on tissue, adjust illumination for optimal contrast.
    #. To enhance contrast when illumination is uneven (eg, if dark corners dominate the image contrast):
        #. Focus just above tissue until the entire view is out of focus
        #. Click **Collect background** and wait for the 3-second timer to count down.
        #. Click **Divide background**; the image should become flat and noisy.
        #. Focus back down to the tissue; the contrast should be noticeably improved.
        #. At any time, click **Divide background** again to disable/enable background removal, or repeat the process if the illumination structure has changed.
#. Navigate to find a healthy cell, then click the square ROI button (bottom panel of the Camera module). 
#. Drag the new ROI around the cell. This will mark its location so that it may be quickly found after refocusing to bring in the patch electrode. If ACQ4 is configured to receive stage positioning information, the ROI will follow the cell even as the stage is moved.
#. Open the :ref:`Data Manager module<userModulesDataManager>` and create a new folder to hold the data for this cell. The new folder should be highlighted in red to indicate that all modules will store data to that location. See the :ref:`userTutorialsDataOrganization` tutorial for more on this topic.
#. Open the :ref:`Patch module<userModulesPatch>` configured for the clamp channel you will be using.
#. Place electrode in the bath, then click:
    * **Bath** to instruct the amplifier to use VC mode, holding at 0 mV.
    * **Start** to begin recording repeatedly.
    * **Reset History** to clear any previously collected analysis results from the plot display (if any).
#. Correct the pipette offset at the amplifier.
#. Begin sealing the electrode onto a cell. When the input resistance measurement exceeds 100 MΩ, click **Patch**. This will activate the selected holding potential (by default, this is set to -65 mV), ensuring that the cell will be held at a reasonable potential after the membrane is ruptured.
#. Monitor the input resistance as it increases to > 1 GΩ.
#. Adjust pipette compensation at the amplifier until capacitive transients are fully compensated.
#. Rupture the cell membrane.
#. Press **Cell** to switch to current-clamp mode. Check for appropriate resting membrane potential, input resistance, and access resistance.
#. Press **Record**; a 'Patch' folder should appear in the data manager; all analysis results collected by the Patch module are stored here. As long as the **Record** button remains depressed, new results are being appended to this stored data set.
#. Optionally, press **Monitor**; this increases the cycle time to 40 seconds and increases averaging as well. The Patch module may then be left running in the background to make periodic cell-health measurements for the duration of the experiment.
#. After removing the electrode from the cell, apply positive pressure to clear the tip (while still in the bath) and press **Bath** again to verify that the pipette offset is stable.
#. When the experiment for this cell is complete, press **Stop** and **Record** to discontinue recording.

