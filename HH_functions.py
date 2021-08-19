"""
Defines relevant functions for the HVAC system
"""
import gridlabd
import pandas
from dateutil import parser
from datetime import timedelta
import scipy.stats

from HH_global import interval, HVAC_bid_rule, allocation_rule

##############################
# Read in physical HVAC parameters
##############################

# Collect characteristics relevant for bidding
def get_settings_houses(houselist,interval,mysql=False):
	dt = parser.parse(gridlabd.get_global('clock')) #Better: getstart time!
	prev_timedate = dt - timedelta(minutes=interval/60)
	cols_market_hvac = ['house_name','heating_system','P_heat','gamma_heat','heating_setpoint','T_min']
	cols_market_hvac += ['cooling_system','P_cool','gamma_cool','cooling_setpoint','T_max','alpha','comf_temperature','beta','air_temperature','system_mode','active']
	df_market_hvac = pandas.DataFrame(columns=cols_market_hvac)

	# read out GLD model characteristics
	for house in houselist:            
		house_obj = gridlabd.get_object(house)
		alpha = float(house_obj['alpha'])
		beta = float(house_obj['beta'])
		gamma_cool = float(house_obj['gamma_cool'])
		gamma_heat = float(house_obj['gamma_heat'])
		heating_system = house_obj['heating_system_type']
		cooling_system = house_obj['cooling_system_type']
		comf_temperature = float(house_obj['comf_temperature'])
		T_min = float(house_obj['T_min'])
		T_max = float(house_obj['T_max'])
		heat_q = float(house_obj['heating_demand']) #heating_demand is in kW - gets overwritten by HVAC_settings
		hvac_q = float(house_obj['cooling_demand']) #cooling_demand is in kW
		heating_setpoint = float(house_obj['heating_setpoint'])
		cooling_setpoint = float(house_obj['cooling_setpoint'])
		T_air = float(house_obj['air_temperature'])
		# Save
		data_house = [house,heating_system,heat_q,gamma_heat,heating_setpoint,T_min]
		data_house += [cooling_system,hvac_q,gamma_cool,cooling_setpoint,T_max,alpha,comf_temperature,beta,T_air,'OFF',0]
		df_market_hvac = df_market_hvac.append(pandas.Series(data_house,index=cols_market_hvac),ignore_index=True) 
	df_market_hvac.index = range(1,len(df_market_hvac)+1)

	return df_market_hvac

#Read previous temperature of each house and forecast current temperature (not synchronized yet!!)
def update_house(dt_sim_time,df_market_hvac):
	# Update physical parameters
	for i in df_market_hvac.index:
		# Measure current temperature  - but it's actually the temperature from -5min bec it's not synchronized yet !!!
		df_market_hvac.at[i,'air_temperature'] = float(gridlabd.get_value(df_market_hvac['house_name'].loc[i],'air_temperature')[:-5])
		# Update P_heat and P_cool based on last activity (only if HVAC was previously active)
		if df_market_hvac.at[i,'active'] == 1:
			if gridlabd.get_value(df_market_hvac['house_name'].loc[i],'system_mode') == 'HEAT':
				if not df_market_hvac.at[i,'heating_system'] == 'GAS':
					df_market_hvac.at[i,'P_heat'] = float(gridlabd.get_value(df_market_hvac['house_name'].loc[i],'hvac_load')[:-3])
			elif gridlabd.get_value(df_market_hvac['house_name'].loc[i],'system_mode') == 'COOL':
				df_market_hvac.at[i,'P_cool'] = float(gridlabd.get_value(df_market_hvac['house_name'].loc[i],'hvac_load')[:-3])
	
	# This makes a forecast of the actual temperature in t (i.e. g(theta_t-1) = est_theta_t )
	# Forecast : theta_t = beta*theta_t-1 + (1-beta)*theta_out_t + m*P_m*gamma_m*duration*d
	# m = 1 for heating, m = -1 for cooling
	# d = 1 (dispatch), d = 0 (no dispatch)
	T_out = float(gridlabd.get_object('weather')['temperature'])
	df_market_hvac['air_temperature'] = df_market_hvac['beta']*df_market_hvac['air_temperature'] + (1.- df_market_hvac['beta'])*T_out
	ind_cool = df_market_hvac.loc[(df_market_hvac['active'] == 1) & (df_market_hvac['system_mode'] == 'COOL')].index
	df_market_hvac['air_temperature'].loc[ind_cool] = df_market_hvac['air_temperature'].loc[ind_cool] - (df_market_hvac['P_cool']*df_market_hvac['gamma_cool']*interval/3600.).loc[ind_cool]
	ind_heat = df_market_hvac.loc[(df_market_hvac['active'] == 1) & (df_market_hvac['system_mode'] == 'HEAT')].index
	df_market_hvac['air_temperature'].loc[ind_heat] = df_market_hvac['air_temperature'].loc[ind_heat] + (df_market_hvac['P_heat']*df_market_hvac['gamma_heat']*interval/3600.).loc[ind_heat]
	return df_market_hvac

##############################
# Determine HVAC bids
##############################

# Determine HVAC bids according to provided HVAC bidding rule
def determine_bids(dt_sim_time,df_house_state,retail,mean_p,var_p):
	if HVAC_bid_rule == 'olympic_peninsula':
		df_house_state = calc_bids_HVAC_olypen(dt_sim_time,df_house_state,retail,mean_p,var_p)
	elif HVAC_bid_rule == 'quantile':
		df_house_state = calc_bids_HVAC_cdf(dt_sim_time,df_house_state,retail,mean_p,var_p)
	elif HVAC_bid_rule == 'economic_quadratic':
		df_house_state = calc_bids_HVAC_economic_quadratic(dt_sim_time,df_house_state,retail,mean_p,var_p)
	else:
		print('Provided HVAC rule does not exist.')
		print('Existing HVAC rules: quantile, economic_quadratic')
		print('Using quantile as default')
		df_house_state = calc_bids_HVAC_cdf(dt_sim_time,df_house_state,retail,mean_p,var_p)
	return df_house_state

# Calculates bids for HVAC systems according to bidding function used by Olympic peninsula
def calc_bids_HVAC_olypen(dt_sim_time,df_house_state,retail,mean_p,var_p):
	df_house_state['active'] = 0 #Reset from last period
	df_bids = df_house_state.copy()
	
	# Calculate bid prices
	delta = 3.0 #band of HVAC inactivity
	df_bids['T_h0'] = df_bids['T_min'] + (df_bids['T_max'] - df_bids['T_min'])/2 - delta/2
	df_bids['T_c0'] = df_bids['T_min'] + (df_bids['T_max'] - df_bids['T_min'])/2 + delta/2
	df_bids['bid_p'] = 0.0 #default
	df_bids['system_mode'] = 'OFF' #default
	#heating
	df_bids.at[df_bids['air_temperature'] <= df_bids['T_h0'],'system_mode'] = 'HEAT'
	df_bids.at[df_bids['system_mode'] == 'HEAT','bid_p'] = (mean_p + df_bids['alpha']*var_p) + (df_bids['air_temperature']-df_bids['T_min'])*(-2*df_bids['alpha']*var_p)/(df_bids['T_h0']-df_bids['T_min']).round(prec)
	df_bids.at[df_bids['air_temperature'] <= df_bids['T_min'],'bid_p'] = retail.Pmax
	#cooling
	df_bids.at[df_bids['air_temperature'] >= df_bids['T_c0'],'system_mode'] = 'COOL'
	df_bids.at[df_bids['system_mode'] == 'COOL','bid_p'] = (mean_p + df_bids['alpha']*var_p) - (df_bids['T_max']-df_bids['air_temperature'])*(2*df_bids['alpha']*var_p)/(df_bids['T_max']-df_bids['T_c0']).round(prec)
	df_bids.at[df_bids['air_temperature'] >= df_bids['T_max'],'bid_p'] = retail.Pmax
	
	# Write bids to dataframe
	df_house_state['bid_p'] = df_bids['bid_p']
	df_house_state['system_mode'] = df_bids['system_mode']
	return df_house_state

# Calculates bids for HVAC systems as lowest price to realize required duty cycle
# e.g. if 20% duty cycle is required, 20% percentile of the price distribution is used as max willingness-to-pay
def calc_bids_HVAC_cdf(dt_sim_time,df_house_state,retail,mean_p,var_p):
	duty_cycle = pandas.read_csv('Input_files/HVAC_dutycycle.csv',index_col=[0])[str(dt_sim_time.hour)].loc[dt_sim_time.month]
	p_min = scipy.stats.norm.ppf(duty_cycle,loc=mean_p,scale=var_p) #var_p is std
	df_house_state['active'] = 0 #Reset from last period
	df_bids = df_house_state.copy()
	
	#Calculate bid prices
	delta = 3.0 #band of HVAC inactivity
	df_bids['T_h0'] = df_bids['T_min'] + (df_bids['T_max'] - df_bids['T_min'])/2 - delta/2
	df_bids['T_c0'] = df_bids['T_min'] + (df_bids['T_max'] - df_bids['T_min'])/2 + delta/2
	df_bids['bid_p'] = 0.0 #default
	df_bids['system_mode'] = 'OFF' #default
	# Heating
	df_bids['system_mode'].loc[df_bids['air_temperature'] <= df_bids['T_h0']] = 'HEAT'
	heat_ind = df_bids.loc[df_bids['system_mode'] == 'HEAT'].index
	df_bids['bid_p'].loc[heat_ind] = p_min + p_min*(df_bids['heating_setpoint'].loc[heat_ind]/df_bids['air_temperature'].loc[heat_ind] - 1.)*df_bids['alpha'].loc[heat_ind]
	df_bids['bid_p'].loc[df_bids['air_temperature'] <= df_bids['T_min']] = retail.Pmax
	# Cooling
	df_bids['system_mode'].loc[df_bids['air_temperature'] >= df_bids['T_c0']] = 'COOL'
	cool_ind = df_bids.loc[df_bids['system_mode'] == 'COOL'].index
	df_bids['bid_p'].loc[cool_ind] = p_min + p_min*(df_bids['air_temperature'].loc[cool_ind]/df_bids['cooling_setpoint'].loc[cool_ind] - 1.)*df_bids['alpha'].loc[cool_ind]
	df_bids['bid_p'].loc[df_bids['air_temperature'] >= df_bids['T_max']] = retail.Pmax
	
	# Write bids to dataframe
	df_house_state['bid_p'] = df_bids['bid_p']
	df_house_state['system_mode'] = df_bids['system_mode']
	return df_house_state

# Calculates economic bids for HVAC systems with quadratic utility function (thermal comfort)
def calc_bids_HVAC_economic_quadratic(dt_sim_time,df_house_state,retail,mean_p,var_p):
	df_house_state['active'] = 0 #Reset from last period
	df_bids = df_house_state.copy()
	df_bids['bid_p'] = 0.0 #default
	df_bids['system_mode'] = 'OFF' #default
	df_bids['m'] = 0.0 #default
	df_bids['air_temperature_t+1'] = 0.0

	# Determine system mode
	delta = 0.0
	df_bids['T_h0'] = df_bids['comf_temperature'] - delta*(df_bids['comf_temperature'] - df_bids['heating_setpoint'])/(df_bids['cooling_setpoint'] - df_bids['heating_setpoint'])
	df_bids['T_c0'] = df_bids['comf_temperature'] + delta*(df_bids['cooling_setpoint'] - df_bids['comf_temperature'])/(df_bids['cooling_setpoint'] - df_bids['heating_setpoint'])
	# heating
	df_bids['system_mode'].loc[df_bids['air_temperature'] <= df_bids['T_h0']] = 'HEAT'
	df_bids['m'].loc[df_bids['air_temperature'] <= df_bids['T_h0']] = 1.
	heat_ind = df_bids.loc[df_bids['system_mode'] == 'HEAT'].index
	# cooling
	df_bids['system_mode'].loc[df_bids['air_temperature'] >= df_bids['T_c0']] = 'COOL'
	df_bids['m'].loc[df_bids['air_temperature'] >= df_bids['T_c0']] = -1.
	cool_ind = df_bids.loc[df_bids['system_mode'] == 'COOL'].index

	# Estimate new temperature w/o HVAC activity and determine bid
	T_out = float(gridlabd.get_object('weather')['temperature'])
	# heating
	df_bids['air_temperature_t+1'] = df_bids['beta']*df_bids['air_temperature'] + (1. - df_bids['beta'])*T_out + df_bids['m']*df_bids['P_heat']*df_bids['gamma_heat']*interval/3600.
	df_bids['air_temperature_mean'] = (df_bids['air_temperature'] + df_bids['air_temperature_t+1'])/2.
	df_bids['bid_p'].loc[heat_ind] = (2*df_bids['alpha']*df_bids['gamma_heat']*(df_bids['comf_temperature'] - df_bids['air_temperature_mean'])/(1. - df_bids['beta'])).loc[heat_ind]
	df_bids['bid_p'].loc[heat_ind] = df_bids['bid_p'].loc[heat_ind]*1000. #USD/MWh
	# cooling
	df_bids['air_temperature_t+1'] = df_bids['beta']*df_bids['air_temperature'] + (1. - df_bids['beta'])*T_out + df_bids['m']*df_bids['P_cool']*df_bids['gamma_cool']*interval/3600.
	df_bids['air_temperature_mean'] = (df_bids['air_temperature'] + df_bids['air_temperature_t+1'])/2.
	df_bids['bid_p'].loc[cool_ind] = (2*df_bids['alpha']*df_bids['gamma_cool']*(df_bids['air_temperature_mean'] - df_bids['comf_temperature'])/(1. - df_bids['beta'])).loc[cool_ind]
	df_bids['bid_p'].loc[cool_ind] = df_bids['bid_p'].loc[cool_ind]*1000. #USD/MWh
	
	# Write bids to dataframe
	df_house_state['bid_p'] = df_bids['bid_p']
	df_house_state['system_mode'] = df_bids['system_mode']
	return df_house_state

##############################
# Submit HVAC bids
##############################

#Submits HVAC bids to market and saves bids to database
def submit_bids_HVAC(dt_sim_time,retail,df_bids,df_buy_bids):
	#Submit bids (in kW)
	df_bids['bid_q'] = 0.0
	for ind in df_bids.index: # bids of p_min (or lower) don't get submitted
		#if df_bids['bid_p'].loc[ind] > p_min and df_bids['P_heat'].loc[ind] > 0.0 and df_bids['system_mode'].loc[ind] == 'HEAT':
		if df_bids['P_heat'].loc[ind] > 0.0 and df_bids['system_mode'].loc[ind] == 'HEAT':
			df_bids.at[ind,'bid_q'] = df_bids['P_heat'].loc[ind]
			retail.buy(df_bids['P_heat'].loc[ind],df_bids['bid_p'].loc[ind],active=int(df_bids['active'].loc[ind]),appliance_name=df_bids['house_name'].loc[ind])
			df_buy_bids = df_buy_bids.append(pandas.DataFrame(columns=df_buy_bids.columns,data=[[dt_sim_time,df_bids['house_name'].loc[ind],float(df_bids['bid_p'].loc[ind]),float(df_bids['P_heat'].loc[ind])]]),ignore_index=True)
		#elif df_bids['bid_p'].loc[ind] > p_min and df_bids['P_cool'].loc[ind] > 0.0 and df_bids['system_mode'].loc[ind] == 'COOL':
		elif df_bids['P_cool'].loc[ind] > 0.0 and df_bids['system_mode'].loc[ind] == 'COOL':
			df_bids.at[ind,'bid_q'] = df_bids['P_cool'].loc[ind]
			retail.buy(df_bids['P_cool'].loc[ind],df_bids['bid_p'].loc[ind],active=int(df_bids['active'].loc[ind]),appliance_name=df_bids['house_name'].loc[ind])
			df_buy_bids = df_buy_bids.append(pandas.DataFrame(columns=df_buy_bids.columns,data=[[dt_sim_time,df_bids['house_name'].loc[ind],float(df_bids['bid_p'].loc[ind]),float(df_bids['P_cool'].loc[ind])]]),ignore_index=True)
	return retail, df_buy_bids

##############################
# Set HVACs according to price
##############################

# Sets HVAC after market clearing
def set_HVAC(dt_sim_time,df_house_state,mean_p,var_p, retail,df_awarded_bids):
	if allocation_rule == 'by_price':
		# All buy bids above or at the clearing price dispatch (vice versa for demand)
		df_house_state,df_awarded_bids = set_HVAC_by_price(dt_sim_time,df_house_state,mean_p,var_p, retail.Pd,df_awarded_bids) #Switches the HVAC system on and off directly (depending on bid >= p)
	elif allocation_rule == 'by_award':
		# Bids only dispatch if explicitely selected by market operator (concerns bids == clearing_price)
		df_house_state,df_awarded_bids = set_HVAC_by_award(dt_sim_time,df_house_state,retail,df_awarded_bids) #Switches the HVAC system on and off directly (depending on award)
	elif allocation_rule == 'statistical':
		# Only statistical HVAC dispatch through setpoint
		df_house_state = set_HVAC_T(dt_sim_time,df_house_state,mean_p,var_p, retail.Pd)
	else:
		df_house_state,df_awarded_bids = set_HVAC_by_price(dt_sim_time,df_house_state,mean_p,var_p, retail.Pd,df_awarded_bids)
	return df_house_state,df_awarded_bids

# Determines `active' based on price
def set_HVAC_by_price(dt_sim_time,df_house_state,mean_p,var_p, Pd,df_awarded_bids):
	#df_house_state.at[(df_house_state['bid_p'] >= Pd) & (df_house_state['bid_p'] > p_min),'active'] = 1
	df_house_state.at[(df_house_state['bid_p'] >= Pd),'active'] = 1
	df_house_state,df_awarded_bids = set_HVAC_GLD(dt_sim_time,df_house_state,df_awarded_bids)
	return df_house_state, df_awarded_bids

# Determines `active' based on market result
def set_HVAC_by_award(dt_sim_time,df_house_state,market,df_awarded_bids):
	try:
		list_awards = market.D_awarded[:,3]
	except:
		list_awards = []
	for bidder in list_awards:
		if 'GLD_' in bidder:
			df_house_state.at[df_house_state['house_name'] == bidder,'active'] = 1
	df_house_state, df_awarded_bids = set_HVAC_GLD(dt_sim_time,df_house_state,df_awarded_bids)
	return df_house_state,df_awarded_bids

# Implements `active'
def set_HVAC_GLD(dt_sim_time,df_house_state,df_awarded_bids):
	for ind in df_house_state.index:		
		house = df_house_state['house_name'].loc[ind]
		#Switch on/off control for gas
		if (df_house_state['system_mode'].loc[ind] == 'HEAT') and (df_house_state['heating_system'].loc[ind] == 'GAS'):
			thermostat_control = 'FULL'
			gridlabd.set_value(house,'thermostat_control',thermostat_control)
		elif (df_house_state['system_mode'].loc[ind] == 'COOL') and (df_house_state['heating_system'].loc[ind] == 'GAS'):
			thermostat_control = 'NONE'
			gridlabd.set_value(house,'thermostat_control',thermostat_control)
		#Set system_mode for active systems
		if df_house_state['active'].loc[ind] == 1:
			#import pdb; pdb.set_trace()
			system_mode = df_house_state['system_mode'].loc[ind]
			gridlabd.set_value(house,'system_mode',system_mode) #Cool or heat
			p_bid = df_house_state['bid_p'].loc[ind]
			q_bid = df_house_state['bid_q'].loc[ind]
			#mysql_functions.set_values('awarded_bids','(appliance_name,p_bid,q_bid,timedate)',(house,float(p_bid),float(q_bid),dt_sim_time))
			df_awarded_bids = df_awarded_bids.append(pandas.DataFrame(columns=df_awarded_bids.columns,data=[[dt_sim_time,house,float(p_bid),float(q_bid),'D']]),ignore_index=True)
		elif not ((df_house_state['system_mode'].loc[ind] == 'HEAT') and (df_house_state['heating_system'].loc[ind] == 'GAS')):
			#import pdb; pdb.set_trace()
			system_mode = 'OFF'
			gridlabd.set_value(house,'system_mode',system_mode)
	return df_house_state,df_awarded_bids

# No specific, but statistical HVAC dispatch
def set_HVAC_T(dt_sim_time,df_bids_HVAC,mean_p,var_p, Pd):
	df_bids_HVAC['p_max'] = mean_p+df_bids_HVAC['alpha']*var_p
	delta = 0.0
	df_bids_HVAC['T_h0'] = df_bids_HVAC['comf_temperature'] - delta*(df_bids_HVAC['comf_temperature'] - df_bids_HVAC['heating_setpoint'])/(df_bids_HVAC['cooling_setpoint'] - df_bids_HVAC['heating_setpoint'])
	df_bids_HVAC['T_c0'] = df_bids_HVAC['comf_temperature'] + delta*(df_bids_HVAC['cooling_setpoint'] - df_bids_HVAC['comf_temperature'])/(df_bids_HVAC['cooling_setpoint'] - df_bids_HVAC['heating_setpoint'])

	df_bids_HVAC['temp'] = df_bids_HVAC['T_min'] + (df_bids_HVAC['p_max'] - Pd)*(df_bids_HVAC['T_h0'] - df_bids_HVAC['T_min'])/(2*df_bids_HVAC['alpha']*var_p)
	df_bids_HVAC['temp'] = df_bids_HVAC[['temp','T_min']].max(axis=1)
	df_bids_HVAC['temp'] = df_bids_HVAC[['temp','T_h0']].min(axis=1)
	df_bids_HVAC.loc[df_bids_HVAC['system_mode'] == 'HEAT','heating_setpoint'] = df_bids_HVAC['temp']
	df_bids_HVAC.loc[df_bids_HVAC['system_mode'] == 'HEAT','cooling_setpoint'] = df_bids_HVAC['p_max'].loc[df_bids_HVAC['system_mode'] == 'HEAT'] #p_max
	df_bids_HVAC.loc[df_bids_HVAC['system_mode'] == 'OFF','cooling_setpoint'] = df_bids_HVAC['p_max'].loc[df_bids_HVAC['system_mode'] == 'COOL']#p_max
	
	df_bids_HVAC['temp'] = df_bids_HVAC['T_max'] + (df_bids_HVAC['p_max'] - Pd)*(df_bids_HVAC['T_c0'] - df_bids_HVAC['T_max'])/(2*df_bids_HVAC['alpha']*var_p)
	df_bids_HVAC['temp'] = df_bids_HVAC[['temp','T_c0']].max(axis=1)
	df_bids_HVAC['temp'] = df_bids_HVAC[['temp','T_max']].min(axis=1)
	df_bids_HVAC.loc[df_bids_HVAC['system_mode'] == 'COOL','cooling_setpoint'] = df_bids_HVAC['temp']
	df_bids_HVAC.loc[df_bids_HVAC['system_mode'] == 'COOL','heating_setpoint'] = 0.0
	df_bids_HVAC.loc[df_bids_HVAC['system_mode'] == 'OFF','heating_setpoint'] = 0.0

	#Write new temperature setpoints to GridlabD objects
	for ind in df_bids_HVAC.index:	
		house = df_bids_HVAC['house_name'].loc[ind]	
		cooling_setpoint = df_bids_HVAC['cooling_setpoint'].loc[ind]
		heating_setpoint = df_bids_HVAC['heating_setpoint'].loc[ind]
		gridlabd.set_value(house,'cooling_setpoint',str(cooling_setpoint))
		gridlabd.set_value(house,'heating_setpoint',str(heating_setpoint))

	return df_bids_HVAC
