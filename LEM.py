import gldimport
import os
import random
import pandas
# import json
import numpy as np
# import datetime
from datetime import timedelta
from dateutil import parser
import HH_functions as HHfct
import battery_functions as Bfct
import EV_functions as EVfct
import PV_functions as PVfct
import market_functions as Mfct
import time

from HH_global import results_folder, C_import, C_export, p_max, market_data, which_price
from HH_global import interval, prec, price_intervals, allocation_rule, unresp_factor, load_forecast
from HH_global import FIXED_TARIFF
from HH_global import grid_tariffs

# Default settings in new HH_global
results_folder = 'Results'
share_t = 1/12. # 5 min / 1 hour
file_perfect_PV_forecast = 'glm_generation_Austin/perfect_PV_forecast_july_all.csv'
file_market_data = 'glm_generation_Austin/Ercot_LZ_South.csv'
saving_interval = 24

def on_init(t):
	# Global simulation parameters
	global t0;
	t0 = time.time()
	global step;
	step = 0

	# Prepare dfs to save intermediate market results
	global df_buy_bids, df_supply_bids, df_awarded_bids, df_prices;
	df_buy_bids = pandas.DataFrame(columns=['timestamp','appliance_name','bid_price','bid_quantity'])
	df_supply_bids = pandas.DataFrame(columns=['timestamp','appliance_name','bid_price','bid_quantity'])
	df_awarded_bids = pandas.DataFrame(columns=['timestamp','appliance_name','bid_price','bid_quantity','S_D'])
	df_prices = pandas.DataFrame(columns=['clearing_price','clearing_quantity','unresponsive_loads'])

	# Read-out flexible devices from GLD model
	global houses;
	houses = gldimport.find_objects('class=house')
	batteries = gldimport.find_objects('class=battery')
	global batterylist, EVlist;
	batterylist, EVlist = gldimport.sort_batteries(batteries)
	global df_battery_state;
	df_battery_state = Bfct.get_settings_batteries(batterylist,interval)
	global df_EV_state;
	df_EV_state = EVfct.get_settings_EVs(EVlist,interval)
	pvs = gldimport.find_objects('class=solar')
	global pvlist, pvinvlist;
	pvlist, pvinvlist = gldimport.sort_pvs(pvs)
	global df_PV_state;
	df_PV_state = PVfct.get_settings(pvlist,interval)

	# If available, read in perfect PV forecast
	if load_forecast == 'perfect':
		global df_PV_forecast;
		try:
			df_PV_all = pandas.read_csv(file_perfect_PV_forecast,parse_dates=True,skiprows=8)
			df_PV_all['# timestamp'] = df_PV_all['# timestamp'].str.replace(r' UTC$', '')
			df_PV_all['# timestamp'] = pandas.to_datetime(df_PV_all['# timestamp'])
			df_PV_all.set_index('# timestamp',inplace=True)
			df_PV_forecast = pandas.DataFrame(index=df_PV_all.index,columns=['PV_infeed'],data=df_PV_all[df_PV_state['inverter_name']].sum(axis=1))
			df_PV_forecast.to_csv(file_perfect_PV_forecast)
		except:
			print('No perfect PV forecast found, use myopic PV forecast')
			df_PV_forecast = None

	# If available, read in historic market data
	global df_WS;
	df_WS = pandas.read_csv(file_market_data,parse_dates=[-1],index_col=[0])
	df_WS = pandas.DataFrame(index=pandas.to_datetime(df_WS.index.astype(str)),columns=df_WS.columns,data=df_WS.values.astype(float))
	df_WS['time'] = df_WS.index
	df_WS.drop_duplicates(subset='time',keep='last',inplace=True)
	df_WS.drop('time',axis=1,inplace=True)

	# Terminate initialization
	print('Initialize finished after '+str(time.time()-t0))
	return True

# Precommit : runs at every market interval
def on_precommit(t):
	dt_sim_time = parser.parse(gridlabd.get_global('clock')).replace(tzinfo=None)

	#Run market only every five minutes
	if not ((dt_sim_time.second == 0) and (dt_sim_time.minute % (interval/60) == 0)):
		return t
	else:
		global step;
		global df_house_state, df_battery_state, df_EV_state, df_PV_state;
		global df_buy_bids, df_supply_bids, df_awarded_bids; 

		# Get settings after model objects have been synchronized for the first time (after init)
		if step == 0:
			df_house_state = HHfct.get_settings_houses(houses,interval)

		#Save intermediate market result files and shorten dfs every X hours (X = saving_interval)
		if step == 0:
			global time_daystart 
			time_daystart = time.time()
		if step > 0 and (dt_sim_time.hour%saving_interval == 0) and (dt_sim_time.minute == 0):
			dt_sim_time_prev = dt_sim_time - pandas.Timedelta(days=1)
			specifier = str(dt_sim_time_prev.year)+format(dt_sim_time_prev.month,'02d')+format(dt_sim_time_prev.day,'02d')+format(dt_sim_time_prev.hour,'02d')

			df_supply_bids.to_csv(results_folder+'/df_supply_bids_'+specifier+'.csv')
			df_buy_bids.to_csv(results_folder+'/df_buy_bids_'+specifier+'.csv')
			df_awarded_bids = df_awarded_bids.loc[df_awarded_bids['timestamp'] >= dt_sim_time_prev] #keep last period for unresp_load calculation
			df_awarded_bids.to_csv(results_folder+'/df_awarded_bids_'+specifier+'.csv')

			dt_sim_time_lastperiod = dt_sim_time - pandas.Timedelta(seconds=interval)
			df_awarded_bids = df_awarded_bids.loc[df_awarded_bids['timestamp'] == dt_sim_time_lastperiod]
			df_buy_bids = pandas.DataFrame(columns=df_buy_bids.columns)
			df_supply_bids = pandas.DataFrame(columns=['timestamp','appliance_name','bid_price','bid_quantity'])
			time_dayend = time.time()
			print('Time needed for past simulation day '+str(dt_sim_time_prev)+': '+str((time_dayend - time_daystart)/60.)+' min')
			time_daystart = time_dayend

		##############################
		# Get updated physical values for new period from GLD model
		##############################

		df_house_state = HHfct.update_house(dt_sim_time,df_house_state)
		if len(batterylist) > 0:
			df_battery_state = Bfct.update_battery(df_battery_state)
		if len(EVlist) > 0:
			df_EV_state = EVfct.update_EV(dt_sim_time,df_EV_state)
		if len(pvlist) > 0:
			df_PV_state = PVfct.update_PV(dt_sim_time,df_PV_state)

		##############################
		# Determine and submit bids
		##############################

		#Initialize market
		global df_prices, df_WS;
		retail, mean_p, var_p = Mfct.create_market(df_WS,df_prices,p_max,prec,price_intervals,dt_sim_time)

		# HVAC systems
		df_house_state = HHfct.determine_bids(dt_sim_time,df_house_state,retail,mean_p,var_p)
		retail,df_buy_bids = HHfct.submit_bids_HVAC(dt_sim_time,retail,df_house_state,df_buy_bids)

		#Batteries
		if len(batterylist) > 0:
			if ((dt_sim_time.hour == 0) and (dt_sim_time.minute == 0)) or step == 0:
				specifier = str(dt_sim_time.year)+format(dt_sim_time.month,'02d')+format(dt_sim_time.day,'02d')
				df_battery_state = Bfct.schedule_battery_ordered(df_WS,df_battery_state,dt_sim_time,specifier)
				#sell, buy = Bfct.schedule_battery_cvx(df_WS,df_battery_state,dt_sim_time)
			df_battery_state = Bfct.calc_bids_battery(dt_sim_time,df_battery_state,retail,mean_p,var_p)
			retail,df_supply_bids,df_buy_bids = Bfct.submit_bids_battery(dt_sim_time,retail,df_battery_state,df_supply_bids,df_buy_bids)
		
		# EVs
		if len(EVlist) > 0:
			df_EV_state = EVfct.calc_bids_EV(dt_sim_time,df_EV_state,retail,mean_p,var_p)
			retail,df_buy_bids = EVfct.submit_bids_EV(dt_sim_time,retail,df_EV_state,df_buy_bids)

		# PVs
		if len(pvlist) > 0:
			global df_PV_forecast;
			if (load_forecast == 'myopic') or (df_PV_forecast is None):
				df_PV_state = PVfct.calc_bids_PV(dt_sim_time,df_PV_state,retail)
				retail,df_supply_bids = PVfct.submit_bids_PV(dt_sim_time,retail,df_PV_state,df_supply_bids)
			elif load_forecast == 'perfect':
				#PV_forecast = df_PV_forecast['PV_infeed'].loc[dt_sim_time]
				PV_forecast = df_PV_forecast['PV_infeed'].loc[(df_PV_forecast.index >= dt_sim_time) & (df_PV_forecast.index < dt_sim_time + pandas.Timedelta(str(int(interval/60))+' min'))].min()/1000
				if PV_forecast > 0.0:
					retail.sell(PV_forecast,0.0,gen_name='PV')
					df_supply_bids = df_supply_bids.append(pandas.DataFrame(columns=df_supply_bids.columns,data=[[dt_sim_time,'PV',0.0,PV_forecast]]),ignore_index=True)

		# Include unresponsive load
		retail, load_SLACK, unresp_load, df_buy_bids = Mfct.include_unresp_load(dt_sim_time,retail,df_prices,df_buy_bids,df_awarded_bids)
		
		# Include WS supply
		WS_supply_costs = float(min(df_WS['RT'].loc[dt_sim_time],retail.Pmax))
		supply_costs = WS_supply_costs + grid_tariffs*1000
		retail.sell(C_import,supply_costs,gen_name='WS') #in [USD/kW] #How can I tweak clearing that we can name biider 'WS'?
		df_supply_bids = df_supply_bids.append(pandas.DataFrame(columns=df_supply_bids.columns,data=[[dt_sim_time,'WS',supply_costs,C_import]]),ignore_index=True)
		
		# Include WS export
		retail.buy(C_export,supply_costs-0.01,appliance_name='WS_export') #in [USD/kW] #How can I tweak clearing that we can name biider 'WS'?
		df_buy_bids = df_buy_bids.append(pandas.DataFrame(columns=df_buy_bids.columns,data=[[dt_sim_time,'WS_export',supply_costs-0.01,C_export]]),ignore_index=True)

		##############################
		# Clear market
		##############################

		retail.clear()
		Pd = retail.Pd # cleared demand price
		Qd = retail.Qd #in kW
		df_temp = pandas.DataFrame(index=[dt_sim_time],columns=['clearing_price','clearing_quantity','unresponsive_loads'],data=[[Pd,Qd,unresp_load]])
		df_prices = df_prices.append(df_temp)
		
		##############################
		# Redistribute prices and quantities to market participants
		##############################

		# HVAC system
		df_house_state,df_awarded_bids = HHfct.set_HVAC(dt_sim_time,df_house_state,mean_p,var_p, retail,df_awarded_bids)

		# PV
		if len(pvlist) > 0:
			df_awarded_bids = PVfct.set_PV(dt_sim_time,retail,df_PV_state,df_awarded_bids)

		# Battery
		if len(batterylist) > 0:
			if allocation_rule == 'by_price':
				df_bids_battery, df_awarded_bids = Bfct.set_battery_by_price(dt_sim_time,df_battery_state,mean_p,var_p, Pd, df_awarded_bids) #Controls battery based on bid <-> p
			elif allocation_rule == 'by_award':
				df_bids_battery, df_awarded_bids = Bfct.set_battery_by_award(dt_sim_time,df_battery_state,retail, df_awarded_bids) #Controls battery based on award

		# EV
		if len(EVlist) > 0:
			if allocation_rule == 'by_price':
				df_EV_state, df_awarded_bids = EVfct.set_EV_by_price(dt_sim_time,df_EV_state,mean_p,var_p, Pd, df_awarded_bids) #Controls EV based on bid <-> p
			elif allocation_rule == 'by_award':
				df_EV_state, df_awarded_bids = EVfct.set_EV_by_award(dt_sim_time,df_EV_state,retail,df_awarded_bids) #Controls EV based on award

		step += 1
		retail.reset()
		return t

def on_term(t):
	print('Simulation ended, saving results')
	saving_results() # 

	global t0;
	t1 = time.time()
	print('Time needed (min):')
	print((t1-t0)/60)
	return None

def saving_results():

	#Save settings of objects
	global df_house_state;
	df_house_state.to_csv(results_folder+'/df_house_state.csv')
	global df_battery_state
	df_battery_state.to_csv(results_folder+'/df_battery_state.csv')
	global df_EV_state
	df_EV_state.to_csv(results_folder+'/df_EV_state.csv')
	global df_PV_state;
	df_PV_state.to_csv(results_folder+'/df_PV_state.csv')

	#Save market results
	global df_prices;
	df_prices.to_csv(results_folder+'/df_prices.csv')
	global df_supply_bids;
	df_supply_bids.to_csv(results_folder+'/df_supply_bids.csv')
	global df_buy_bids;
	df_buy_bids.to_csv(results_folder+'/df_buy_bids.csv')
	global df_awarded_bids;
	df_awarded_bids.to_csv(results_folder+'/df_awarded_bids.csv')

	#Saving globals
	file = 'HH_global.py'
	new_file = results_folder+'/HH_global.py'
	glm = open(file,'r') 
	new_glm = open(new_file,'w') 
	j = 0
	for line in glm:
	    new_glm.write(line)
	glm.close()
	new_glm.close()

	return
