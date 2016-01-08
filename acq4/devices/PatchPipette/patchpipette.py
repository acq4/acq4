from ..Pipette import Pipette


class PatchPipette(Pipette):
	"""Represents a single patch pipette, manipulator, and headstage.

	This class extends from the Pipette device class to provide automation and visual feedback
	on the status of the patch:

		* Whether a cell is currently patched
		* Input resistance, access resistance, and holding levels

	This is also a good place to implement pressure control, autopatching, slow voltage clamp, etc.
	"""
	def __init__(self, deviceManager, config, name):
		self.clamp = config.pop('clampDevice')

		Pipette.__init__(self, deviceManager, config, name)



