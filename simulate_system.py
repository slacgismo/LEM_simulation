import sys
assert(sys.version_info.major>2)
import gridlabd
from HH_global import glm_model

def run_system():

	##################
	# User Input
	#################

	# str glm_model - path to GLD model

	# Parameters to market code
	# str market_file - path to market file

	# Changes in glm
	# start time
	# end time
	# results folder

	##################
	# Assemble correct glm files
	#################
	if False:
		#write global file with settings from csv file: HH_global.py
		import global_functions
		global_functions.write_global(df_settings.loc[ind],ind,'none')
		#re-write glm model for flexible devices - deactivate if no new file needs to be generated
		import glm_functions
		glm_functions.change_glmfile(df_settings.loc[ind]) # only changes start and end time, result folder, and HVAC settings

	##################
	# Run GridlabD
	#################

	gridlabd.command(glm_model)
	print('Running GLD model '+glm_model)
	gridlabd.command('-D')
	gridlabd.command('suppress_repeat_messages=FALSE')
	#gridlabd.command('--debug')
	#gridlabd.command('--verbose')
	gridlabd.command('--warn')
	gridlabd.start('wait')
