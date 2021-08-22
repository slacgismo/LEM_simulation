import sys
assert(sys.version_info.major>2)
import pandas
import gridlabd

from HH_global import benchmarking_folder, input_folder, market_data
from HH_global import glm_model, start_time_str, end_time_str, interval, results_folder, PV_forecast, unresp_load_forecast


def generate_benchmarks():

	##################
	# Assemble correct glm file for benchmarking
	#################

	# Change start + end date
	# Change result folder
	# Change gridlabd_function import

	#re-write glm model for flexible devices - deactivate if no new file needs to be generated
	import glm_functions
	import pdb; pdb.set_trace()
	change_glmfile_to_benchmark() # resets to benchmark

	##################
	# Run GridlabD
	#################

	print('Run GridLAB-D model for benchmarking (fixed retail tariff)\n')
	gridlabd.command(input_folder + '/' + glm_model.split('.')[0] + '_modified.glm')
	print('Running GLD model ' + glm_model + ' for benchmarking')
	gridlabd.command('-D')
	gridlabd.command('suppress_repeat_messages=FALSE')
	#gridlabd.command('--debug')
	#gridlabd.command('--verbose')
	gridlabd.command('--warn')
	gridlabd.start('wait')
	#gridlabd.save(input_folder + '/' + glm_model + '_notrandom.glm') # If first run is based on random model - dump model as benchmarks are parameter specific

	##################
	# Generate benchmarks
	#################

	print('Results saved to ' + benchmarking_folder + ' folder\n')
	print('Calculate benchmarks\n')

	generate_perfect_PV_forecast()
	generate_perfect_unresp_load_forecast()
	calculate_RR()

	print('Manually include benchmarks into HH_global')
	sys.exit('Uncomment benchmarking command in _main.py and run actual simulation')
	return

def change_glmfile_to_benchmark():

    results_folder = 'Benchmarking'
    pricing = 'fixed'
    from HH_global import end_time_str, input_folder
    end_time_str = str(pandas.Timestamp(end_time_str) + pandas.Timedelta(seconds=interval))

    old_glm = open(input_folder + '/' + glm_model,'r')
    new_glm_name = glm_model.split('.')[0] + '_modified.glm'
    new_glm = open(input_folder + '/' + new_glm_name,'w') 

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
            if '"' in line:
            	new_glm.write(indent+'file "'+results_folder+'/'+file_name)
            else:
            	new_glm.write(indent+'file '+results_folder+'/'+file_name)
            flag_recorder = False
        else:
            new_glm.write(line)

    old_glm.close()
    new_glm.close()

    return

def generate_perfect_PV_forecast():
	df_solar = pandas.read_csv(benchmarking_folder + '/total_P_Out.csv',index_col=[0],skiprows=8)
	list_inverters = []
	for col in df_solar.columns:
		if 'PV' in col:
			list_inverters += [col]
	df_solar = df_solar[list_inverters]
	df_solar.to_csv(input_folder + '/' + PV_forecast)
	print('Perfect PV forecast generated and saved to Input_files')
	return

def generate_perfect_unresp_load_forecast():
	df_load_slack = pandas.read_csv(benchmarking_folder + '/substation.csv',index_col=[0],skiprows=8)
	# Calculate flexible load
	# Solar
	df_inverters = pandas.read_csv(benchmarking_folder + '/total_P_Out.csv',index_col=[0],skiprows=8)
	list_pvs = []
	for col in df_inverters.columns:
		if 'PV' in col:
			list_pvs += [col]
	df_solar = df_inverters[list_pvs]
	pv_infeed = df_solar.sum(axis=1)
	df_load_slack['pv'] = pv_infeed
	# HVAC
	df_hvac_load = pandas.read_csv(benchmarking_folder + '/hvac_load_all.csv',index_col=[0],skiprows=8)
	df_heating_systems = pandas.read_csv(benchmarking_folder + '/heating_system_type.csv',index_col=[0],skiprows=8)
	cols_hvac = []
	for system, house in zip(df_heating_systems.iloc[0],df_heating_systems.columns):
		if system != 'GAS':
			cols_hvac += [house]
	hvac = df_hvac_load[cols_hvac].sum(axis=1)
	df_load_slack['hvac'] = hvac
	# Batteries
	list_batts = []
	for col in df_inverters.columns:
		if 'Bat' in col:
			list_batts += [col]
	df_batts = df_inverters[list_batts]
	batt_load = df_batts.sum(axis=1)
	df_load_slack['batt'] = batt_load
	# EVs
	list_evs = []
	for col in df_inverters.columns:
		if 'EV' in col:
			list_evs += [col]
	df_ev = df_inverters[list_evs]
	ev_load = df_ev.sum(axis=1)
	df_load_slack['ev'] = ev_load
	# Get losses
	df_total_load_P = pandas.read_csv(benchmarking_folder + '/meter_load_P.csv',index_col=[0],skiprows=8)
	df_load_slack['unresp_load'] = df_load_slack['measured_real_power'] + df_load_slack['pv'] -  df_load_slack['hvac']*1000. + df_load_slack['batt'] + df_load_slack['ev'] # in W
	df_load_slack['unresp_load'] = df_load_slack['unresp_load']/1000.
	if '# end of tape' in df_load_slack.index:
		df_load_slack = df_load_slack.iloc[:-1]
	# Re-write index
	df_load_slack['# timestamp'] = df_load_slack.index
	df_load_slack['# timestamp'] = df_load_slack['# timestamp'].str.replace(r' UTC$', '')
	if '# end of tape' in df_load_slack['# timestamp']:
		inds = df_load_slack.loc[df_load_slack['# timestamp'] == '# end of tape'].index
		inds_keep = sorted(set(df_load_slack.index) - set(inds))
		df_load_slack = df_load_slack.loc[inds_keep]
	df_load_slack['# timestamp'] = pandas.to_datetime(df_load_slack['# timestamp'])
	df_load_slack.set_index('# timestamp',inplace=True)
	# Save
	df_unresp_load = pandas.DataFrame(index=df_load_slack.index,columns=['unresp_load'],data=df_load_slack['unresp_load'].values)
	df_unresp_load.to_csv(input_folder + '/' + unresp_load_forecast)
	print('Perfect unresponsive load forecast generated and saved to Input_files')
	return

#Calculate budget-neutral retail rate
def calculate_RR():
	import pdb; pdb.set_trace()
	df_slack = pandas.read_csv(benchmarking_folder + '/substation.csv',skiprows=range(8))
	df_slack['# timestamp'] = df_slack['# timestamp'].map(lambda x: str(x)[:-4])
	if '# end of' in df_slack['# timestamp'].iloc[-1]:
		df_slack = df_slack.iloc[:-1]
	df_slack['# timestamp'] = pandas.to_datetime(df_slack['# timestamp'])
	df_slack.set_index('# timestamp',inplace=True)
	df_slack = df_slack.loc[pandas.Timestamp(start_time_str):pandas.Timestamp(end_time_str)]
	df_slack = df_slack/1000. #kW

	df_WS = pandas.read_csv(input_folder + '/' + market_data,parse_dates=[0],index_col=[0])
	df_WS = df_WS[~df_WS.index.duplicated(keep='last')]
	df_WS = df_WS.loc[pandas.Timestamp(start_time_str):pandas.Timestamp(end_time_str)]

	assert len(df_slack) == len(df_WS)

	df_WS['system_load'] = df_slack['measured_real_power']
	supply_wlosses = (df_WS['system_load']/1000./12.).sum() # MWh
	df_WS['supply_cost'] = df_WS['system_load']/1000.*df_WS['RT']/12.
	supply_cost_wlosses = df_WS['supply_cost'].sum()

	df_total_load = pd.read_csv(benchmarking_folder + '/total_load_all.csv',skiprows=range(8)) #in kW
	df_total_load['# timestamp'] = df_total_load['# timestamp'].map(lambda x: str(x)[:-4])
	df_total_load = df_total_load.iloc[:-1]
	df_total_load['# timestamp'] = pd.to_datetime(df_total_load['# timestamp'])
	df_total_load.set_index('# timestamp',inplace=True)
	df_total_load = df_total_load.loc[start:end]
	total_load = (df_total_load.sum(axis=1)/12.).sum() #kWh

	df_WS['res_load'] = df_total_load.sum(axis=1)
	supply_wolosses = (df_WS['res_load']/1000./12.).sum() # only residential load, not what is measured at trafo
	df_WS['res_cost'] = df_WS['res_load']/1000.*df_WS['RT']/12.
	supply_cost_wolosses = df_WS['res_cost'].sum()

	try:
		df_inv_load = pd.read_csv(benchmarking_folder + '/total_P_Out.csv',skiprows=range(8)) #in W
		df_inv_load['# timestamp'] = df_inv_load['# timestamp'].map(lambda x: str(x)[:-4])
		df_inv_load = df_inv_load.iloc[:-1]
		df_inv_load['# timestamp'] = pd.to_datetime(df_inv_load['# timestamp'])
		df_inv_load.set_index('# timestamp',inplace=True)  
		df_inv_load = df_inv_load.loc[start:end]
		PV_supply = (df_inv_load.sum(axis=1)/1000./12.).sum() #in kWh
	except:
		PV_supply = 0.0

	import pdb; pdb.set_trace()
	net_demand  = total_load - PV_supply
	retail_kWh = supply_cost_wlosses/net_demand
	retail_kWh_wolosses = supply_cost_wolosses/net_demand

	#import pdb; pdb.set_trace()
	return retail_kWh

	return

