import sys
assert(sys.version_info.major>2)
import gridlabd
from HH_global import glm_model

def run_system():

	##################
	# Assemble correct glm files
	#################

	# Change start + end date
	# Change result folder
	# Change gridlabd_function import

	#re-write glm model for flexible devices - deactivate if no new file needs to be generated
	import glm_functions
	glm_functions.change_glmfile() # only changes start and end time, result folder, and HVAC settings
	#import pdb; pdb.set_trace()

	##################
	# Run GridlabD
	#################

	gridlabd.command('Input_files/' + glm_model.split('.')[0] + '_modified.glm')
	print('Running GLD model ' + glm_model)
	gridlabd.command('-D')
	gridlabd.command('suppress_repeat_messages=FALSE')
	#gridlabd.command('--debug')
	#gridlabd.command('--verbose')
	gridlabd.command('--warn')
	gridlabd.start('wait')
