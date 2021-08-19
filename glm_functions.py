#Add manual thermostat control and flexible devices
import numpy as np
import glob
import os
import pandas
import re
import sys
import shutil

import math
import copy
import random

from HH_global import glm_model, start_time_str, end_time_str, results_folder, pricing

use_NOAA = False
time_step = 300

def change_glmfile():

    pricing_list = ['fixed','LEM']
    if not pricing in pricing_list:
        print('No such pricing scheme / operating mode.')
        print('Available options:')
        [print(p) for p in pricing_list]
        import sys; sys.exit()

    old_glm = open('Input_files/' + glm_model,'r')
    new_glm_name = glm_model.split('.')[0] + '_modified.glm'
    new_glm = open('Input_files/' + new_glm_name,'w') 

    # Re-write start and end time, result folder
    flag_recorder = False
    module_missing = True
    for line in old_glm:
        # Change date
        if 'starttime' in line:
            new_glm.write('\tstarttime "'+start_time_str+'";\n')
        elif 'stoptime' in line:
            new_glm.write('\tstoptime "'+end_time_str+'";\n')
        elif ('class' in line) and module_missing:
            if pricing != 'fixed':
                new_glm.write('module ' + pricing + ';')
                new_glm.write('\n')
            new_glm.write(line)
            module_missing = False
        elif 'recorder' in line:
            new_glm.write(line)
            flag_recorder = True
        # Change result folder in feeder glm
        elif ('file ' in line) and flag_recorder: # file in a recorder
            indent = line.split('file')[0]
            file_name = line.rsplit('/',1)[-1]
            new_glm.write(indent+'file '+results_folder+'/'+file_name)
            flag_recorder = False
        else:
            new_glm.write(line)

    old_glm.close()
    new_glm.close()

    return
