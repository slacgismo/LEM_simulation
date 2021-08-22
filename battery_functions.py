"""
Defines relevant functions for battery dispatch
"""
import gridlabd
import datetime
import numpy as np
import pandas
from dateutil import parser
from datetime import timedelta

from HH_global import battery_bid_rule, start_time_str, allocation_rule
from HH_global import interval, prec, which_price, M, results_folder
which_price = 'DA'

##############################
# Read in physical HVAC parameters
##############################

# Collect characteristics relevant for bidding
def get_settings_batteries(batterylist,interval,mysql=False):
      dt = parser.parse(gridlabd.get_global('clock')) #Better: getstart time!
      cols_battery = ['battery_name','house_name','SOC_min','SOC_max','i_max','u_max','efficiency','SOC_t','active_t1','active_t','threshold_sell','threshold_buy']
      df_battery = pandas.DataFrame(columns=cols_battery)

      # read out GLD model characteristics
      for battery in batterylist:
            battery_obj = gridlabd.get_object(battery)
            house_name = 'GLD_'+battery[8:]
            SOC_min = float(battery_obj['reserve_state_of_charge']) #in %
            SOC_max = float(battery_obj['battery_capacity'])/1000 #Wh in Gridlabd -> kWh
            str_i_max = battery_obj['I_Max'].replace('-','+')
            i_max = str_i_max.split('+')[1]
            u_max = float(battery_obj['V_Max'])*float(i_max)/1000 #W -> kW #better inverter?
            eff = float(battery_obj['base_efficiency'])
            SOC_0 = float(battery_obj['state_of_charge'])*SOC_max
            df_battery = df_battery.append(pandas.Series([battery,house_name,SOC_min,SOC_max,i_max,u_max,eff,SOC_0,0,0,0.0,0.0],index=cols_battery),ignore_index=True)          
             
      return df_battery

# Read previous SOC of each battery (not synchronized yet, so SOC from t-1) and forecast current SOC in t
def update_battery(df_battery_state):
      # Update physical parameters
      #-1: discharging, 0 no activity, 1 charging
      df_battery_state['active_t1'] = df_battery_state['active_t']
      df_battery_state['active_t'] = 0 # Reset from last period
      for ind in df_battery_state.index: #directly from mysql
            batt = df_battery_state['battery_name'].loc[ind]
            battery_obj = gridlabd.get_object(batt)
            SOC_t = float(battery_obj['state_of_charge'])*df_battery_state['SOC_max'].loc[ind] #In Wh #Losses updated by GridlabD ?
            df_battery_state.at[ind,'SOC_t'] = SOC_t
      return df_battery_state

##############################
# Determine battery bids
##############################

# Determine battery bids according to provided battery bidding rule
def determine_bids(dt_sim_time,df_WS,df_battery_state,retail,mean_p,var_p):
      # Price
      if battery_bid_rule == 'simple_mean':
            df_battery_state = calc_bids_battery_simple_mean(df_battery_state,mean_p)
      elif battery_bid_rule == 'threshold_based':
            # Determine new thresholds at midnight
            if ((dt_sim_time.hour == 0) and (dt_sim_time.minute == 0)) or (dt_sim_time == pandas.Timestamp(start_time_str)):
                  specifier = str(dt_sim_time.year)+format(dt_sim_time.month,'02d')+format(dt_sim_time.day,'02d')
                  df_battery_state = schedule_battery_ordered(df_WS,df_battery_state,dt_sim_time,specifier)
            df_battery_state = calc_bids_battery_bythreshold(df_battery_state,dt_sim_time)
      elif battery_bid_rule == 'optimal':
            df_battery_state = calc_bids_battery_optimal(dt_sim_time,df_battery_state,retail,mean_p,var_p)
      else:
            print('Provided battery rule does not exist.')
            print('Existing battery rules: simple_mean, threshold_based, optimal')
            print('Using simple_mean as default')
            df_battery_state = calc_bids_battery_simple_mean(df_battery_state,mean_p)
      # Quantity
      df_battery_state = calc_bids_battery_quantity(dt_sim_time,df_battery_state,retail,mean_p,var_p)
      return df_battery_state

# Calculates bids for battery in reference to mean price
def calc_bids_battery_simple_mean(df_bids_battery,mean_p):
      df_bids_battery['p_sell'] = mean_p / df_bids_battery['efficiency']
      df_bids_battery['p_buy'] = mean_p * df_bids_battery['efficiency']
      return df_bids_battery

#Schedules battery for next 24 hours by ranking of DA prices 
def schedule_battery_ordered(df_WS,df_battery_state,dt_sim_time,i):
      df_WS_prices = df_WS.loc[dt_sim_time:dt_sim_time+datetime.timedelta(hours=23,minutes=55)]
      df_WS_prices = df_WS_prices.sort_values(which_price,axis=0,ascending=False) #,inplace=True)
      #Calculate number of charging/discharging periods
      df_battery_state['no_periods'] = 0
      df_battery_state['no_periods'] = (3600/interval)*((df_battery_state['SOC_max'] - df_battery_state['SOC_min'])/df_battery_state['u_max'])
      df_battery_state['no_periods'] = df_battery_state['no_periods'].astype(int)
      #Sort prices and calculate average prices of no_periods cheapest/most expensive periods
      for ind in df_battery_state.index:
            threshold_sell = df_WS_prices[which_price].iloc[df_battery_state['no_periods'].loc[ind] - 1]
            df_battery_state.at[ind,'threshold_sell'] = threshold_sell
            threshold_buy = df_WS_prices[which_price].iloc[-df_battery_state['no_periods'].loc[ind]]
            df_battery_state.at[ind,'threshold_buy'] = threshold_buy
      df_battery_state.drop('no_periods',axis=1,inplace=True)
      df_battery_state.to_csv(results_folder+'/df_battery_thresholds_'+str(i)+'.csv')
      return df_battery_state

# Uses threshold provided by schedule_battery_ordered() as bid
def calc_bids_battery_bythreshold(df_bids_battery,dt_sim_time):
      df_bids_battery['p_sell'] = df_bids_battery['threshold_sell']
      df_bids_battery['p_buy'] = df_bids_battery['threshold_buy']
      return df_bids_battery

# Optimally schedule maximum charge or discharge, unless technically not feasible
def calc_bids_battery_quantity(dt_sim_time,df_state_battery,retail,mean_p,var_p):
      #Quantity depends on SOC and u
      df_state_battery['residual_s'] = round((3600./interval)*(df_state_battery['SOC_t'] - df_state_battery['SOC_min']*df_state_battery['SOC_max']),prec) #Recalculate to kW
      df_state_battery['q_sell'] = df_state_battery[['residual_s','u_max']].min(axis=1) #in kW / only if fully dischargeable
      df_state_battery['q_sell'].loc[df_state_battery['q_sell'] < 0.1] = 0.0

      safety_fac = 0.99
      df_state_battery['residual_b'] = round((3600./interval)*(safety_fac*df_state_battery['SOC_max'] - df_state_battery['SOC_t']),prec) #Recalculate to kW
      df_state_battery['q_buy'] = df_state_battery[['residual_b','u_max']].min(axis=1) #in kW
      df_state_battery['q_buy'].loc[df_state_battery['q_buy'] < 0.1] = 0.0
      return df_state_battery

##############################
# Submit battery bids
##############################

# Submits battery bids to market
def submit_bids_battery(dt_sim_time,retail,df_bids,df_supply_bids,df_buy_bids):
      for ind in df_bids.index:
            if df_bids['q_sell'].loc[ind] > 0.0:
                  retail.sell(df_bids['q_sell'].loc[ind],df_bids['p_sell'].loc[ind],gen_name=ind)
                  df_supply_bids = df_supply_bids.append(pandas.DataFrame(columns=df_supply_bids.columns,data=[[dt_sim_time,ind,float(df_bids['p_sell'].loc[ind]),float(df_bids['q_sell'].loc[ind])]]),ignore_index=True)
            if df_bids['q_buy'].loc[ind] > 0.0:
                  retail.buy(df_bids['q_buy'].loc[ind],df_bids['p_buy'].loc[ind],active=df_bids['active_t1'].loc[ind],appliance_name=ind)
                  df_buy_bids = df_buy_bids.append(pandas.DataFrame(columns=df_buy_bids.columns,data=[[dt_sim_time,ind,float(df_bids['p_buy'].loc[ind]),float(df_bids['q_buy'].loc[ind])]]),ignore_index=True)
      df_bids['active_t1'] = 0
      return retail,df_supply_bids,df_buy_bids

##############################
# Set batteries according to allocation rule
##############################

# Sets battery after market clearing
def set_battery(dt_sim_time,df_bids_battery,mean_p,var_p, retail,df_awarded_bids):
      if allocation_rule == 'by_price':
            # All buy bids above or at the clearing price dispatch (vice versa for demand)
            df_bids_battery, df_awarded_bids = set_battery_by_price(dt_sim_time,df_bids_battery,mean_p,var_p, retail.Pd, df_awarded_bids)
      elif allocation_rule == 'by_award':
            # Bids only dispatch if explicitely selected by market operator (concerns bids == clearing_price)
            df_bids_battery,df_awarded_bids = set_battery_by_award(dt_sim_time,df_bids_battery,retail, df_awarded_bids) #Controls battery based on award
      elif allocation_rule == 'statistical':
            # Bids only dispatch if explicitely selected by market operator (concerns bids == clearing_price) which is random
            df_bids_battery,df_awarded_bids = set_battery_by_award(dt_sim_time,df_bids_battery,retail, df_awarded_bids) #Controls battery based on award
      else:
            df_bids_battery,df_awarded_bids = set_battery_by_price(dt_sim_time,df_bids_battery,mean_p,var_p, retail.Pd,df_awarded_bids)
      return df_bids_battery,df_awarded_bids

# Determines `active' based on price
def set_battery_by_price(dt_sim_time,df_bids_battery,mean_p,var_p,Pd,df_awarded_bids):
      #Determine activity
      df_bids_battery.at[(df_bids_battery['p_buy'] >= Pd) & (df_bids_battery['SOC_t'] < df_bids_battery['SOC_max']),'active_t'] = 1
      df_bids_battery.at[(df_bids_battery['p_sell'] <= Pd) & (df_bids_battery['SOC_t'] > 0.0),'active_t'] = -1
      # Let battery charge or discharge
      df_bids_battery, df_awarded_bids = set_battery_GLD(dt_sim_time,df_bids_battery,df_awarded_bids)
      return df_bids_battery,df_awarded_bids

# Determines `active' based on market result
def set_battery_by_award(dt_sim_time,df_bids_battery,market,df_awarded_bids):
      # Determine activity
      try:
            list_awards_D = market.D_awarded[:,3]
            list_awards_D = [x for x in list_awards_D if x is not None]
      except:
            list_awards_D = []
      import pdb; pdb.set_trace()
      for bidder in list_awards_D:
            if 'Battery_' in bidder:
                  df_bids_battery.at[bidder,'active_t'] = 1
      try:
            list_awards_S = market.S_awarded[:,3]
            list_awards_S = [x for x in list_awards_S if x is not None]
      except:
            list_awards_S = []
      for bidder in list_awards_S:
            if 'Battery_' in bidder:
                  df_bids_battery.at[bidder,'active_t'] = -1
      # Let battery charge or discharge
      df_bids_battery, df_awarded_bids = set_battery_GLD(dt_sim_time,df_bids_battery,df_awarded_bids)
      return df_bids_battery, df_awarded_bids

# Implements `active'
def set_battery_GLD(dt_sim_time,df_bids_battery,df_awarded_bids):
      #Check efficiencies!!!
      #Set charging/discharging
      #Change from no to battery_name
      #Do more quickly by setting database through Gridlabd?
      for ind in df_bids_battery.index:
            battery = df_bids_battery['battery_name'].loc[ind]
            inverter = gridlabd.get_object(battery)['parent']
            SOC = df_bids_battery['SOC_t'].loc[ind] #this is SOC at the beginning of the period t
            active = df_bids_battery['active_t'].loc[ind] #this is activity in t
            if active == 1:
                  q_bid = df_bids_battery['q_buy'].loc[ind]
                  p_bid = df_bids_battery['p_buy'].loc[ind]
                  gridlabd.set_value(inverter,'P_Out',str(-1000*q_bid)) #kW -> W    
                  df_awarded_bids = df_awarded_bids.append(pandas.DataFrame(columns=df_awarded_bids.columns,data=[[dt_sim_time,battery,float(p_bid),float(q_bid),'D']]),ignore_index=True)
            elif active == -1:
                  q_bid = df_bids_battery['q_sell'].loc[ind]
                  p_bid = df_bids_battery['p_sell'].loc[ind]
                  gridlabd.set_value(inverter,'P_Out',str(1000*q_bid)) #kW -> W
                  #Include sales as negative
                  df_awarded_bids = df_awarded_bids.append(pandas.DataFrame(columns=df_awarded_bids.columns,data=[[dt_sim_time,battery,float(p_bid),float(q_bid),'S']]),ignore_index=True)
            else:
                  gridlabd.set_value(inverter,'P_Out','0.0')
      return df_bids_battery, df_awarded_bids






