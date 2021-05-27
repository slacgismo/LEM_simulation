# Simulates the benchmark scenario (without a market)

import sys
assert(sys.version_info.major>2)
import gridlabd
import time
import pandas

# Use settings as documented in line 0 of settings file 
# Create result folder named after run
# Exclude gridlabd_functions module from IEEE123_BP_2bus_1min.glm
# Enter 01/01 as start and 12/31 as end date
# Include correct result folder

##################
#Run GridlabD
#################
print('run Gridlabd')
gridlabd.command('IEEE123_BP_2bus_1min.glm')
gridlabd.command('-D')
gridlabd.command('suppress_repeat_messages=FALSE')
#gridlabd.command('--debug')
#gridlabd.command('--verbose')
gridlabd.command('--warn')
gridlabd.start('wait')
