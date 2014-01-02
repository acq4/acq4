Mosaic Editor
=============

The Mosaic Editor is designed to be used to 1) adjust the locations (both overall and relative) of images and photostimulation data, and 2) store location information about cell positions, stimulation sites, etc. to an analysis database. 

Overview
========

Adjusting Locations
-------------------

There are many reasons an experimenter may want to adjust the locations associated of images, photostimulation sites, or any other data with a defined spatial relationship to the sample. For example, a user may want to normalize the positions of multiple samples by defining arbitrary point (for example the rostral pole of the hippocampus) to be at 0,0, rotate the image so that rostral always points left. Or, it is possible that the sample accidentally moved at some point during the experiment, so data collected after the movement will not be automatically correctly aligned with data collected before the movement. The Mosaic Editor allows the experimenter to correct this data so that the entire experiment is correctly aligned. In addition, the Mosaic Editor allows the user to manually specify positions and reconstruct a mosaic of images collected on a system that is not position-aware. 

Importantly, position adjustments do not affect the original position information that was stored when the data was collected. Instead position adjustments are stored with the data in a separate userTransform parameter. 

Storing Location Data
---------------------