import os, sys
assert(sys.version_info.major>2)
import gridlabd
import time
import pandas

# Create result file
if not os.path.isdir('Test/Test_DLMP'):
	os.makedirs('Test/Test_DLMP')

##################
#Run GridlabD
#################
print('run Gridlabd')
gridlabd.command('model_test.glm')
gridlabd.command('-D')
gridlabd.command('suppress_repeat_messages=FALSE')
#gridlabd.command('--debug')
#gridlabd.command('--verbose')
gridlabd.command('--warn')
gridlabd.start('wait')
