Mosaic Editor
=============

The Mosaic Editor is designed to be used to 1) adjust the locations (both overall and relative) of images and photostimulation data, and 2) store location information about cell positions, stimulation sites, etc. to an analysis database using a pre-defined, custom atlas. Use of the Mosaic Editor to simply adjust locations of data does not require the use of an analysis database or atlas. 

Currently implemented atlases include:

* :ref:`Auditory Cortex Atlas<userAnalysisAuditoryCortexAtlas>`
* :ref:`Cochlear Nucleus Atlas<userAnalysisCochlearNucleusAtlas>`

Overview
========

Adjusting Locations
-------------------

There are many reasons an experimenter may want to adjust the locations associated with images, photostimulation sites, or any other data with a defined spatial relationship to the sample. For example, a user may want to normalize the positions of multiple samples by defining an arbitrary point (for example, the rostral pole of the hippocampus) to be at 0,0, and rotate or invert the sample so that rostral always points left. Or, it is possible that the sample accidentally moved at some point during the experiment, so data collected after the movement will not be automatically correctly aligned with data collected before the movement. The Mosaic Editor allows the experimenter to correct this data so that the entire experiment is correctly aligned. In addition, the Mosaic Editor allows the user to manually specify positions and reconstruct a mosaic of images collected on a system that is not position-aware. 

Importantly, position adjustments done in Mosaic Editor do not affect the original position information that was stored when the data was collected. Instead position adjustments are stored with the data in a separate userTransform parameter. UserTransforms can be reset at anytime by clicking the Reset Transforms button in the Canvas control panel within Mosaic Editor.

Storing Location Data
---------------------

The Mosaic Editor also allows the user to store location data in a database through the use of Atlases. For example, for a photostimulation experiment, the user may store information about each stimulation site such as:

* its absolute position
* its position relative to another location such as a cell
* its percent depth from one boundary to another (such as the pial surface to the white matter in cortical slices)
* a label for its location within the preparation (such as assigning it to a specific layer or section of nucleus). 

Similar information might be stored in a separate table for each recorded cell.

Detailed usage
==============

Adjusting Locations
-------------------

#. Load base image or set of images of the preparation using the :ref:`File Loader<userAnalysisFileLoader>` located on the left. This will be the set of images that all other images/cells/stimulation sites are referenced against. 

#. Adjust base images relative to each other if necessary. 
    * To select an image for adjustment click on the name of the image in the list on the right hand side of the screen. (If there is no list on the right hand side of the screen, click the arrow in the upper-right corner of the canvas dock to display the canvas controls.)
    * An ROI should appear around the corresponding image. This ROI can be used to translate the image grabbing inside the ROI and dragging, or to rotate the image by grabbing either of the circular handles at the corners of the ROI and dragging.
    * When aligning images relative to each other, it is often helpful to make one or both images partially transparent. This can be done using the alpha slider in the Canvas control panel.
    * The Z value of images can be adjusted by dragging the name of the image up or down in the list of images.
    * When an image is selected in the Canvas list, the canvas control panel displays a histogram of the values in that image. This can be used to adjust the contrast and brightness of the corresponding image.
    
#. Once images are aligned relative to each other, select all the images, by selecting all the image names in the Canvas list. 

#. The ROI that now appears can be used to translate and rotate all of the images together. Images can also be reflected across the y-axis or inverted (reflected across a y=-x line) by clicking "Mirror Selection" or "MirrorXY" respectively. 

Other operations
++++++++++++++++

* Copy/Paste: You can copy the user transform from one object and apply it to another using the copy and paste buttons. Simply select one object and click "Copy", then select another object (or multiple objects) and click "Paste". 
* Reset Transform: If you want to reset any transformations associated with an object or group of objects, you can use the "Reset Transform" buttons. This will set the userTransform to 0 for translation and rotation and to 1 for scaling, and the object(s) will move back to the position that was recorded when the data was acquired.




