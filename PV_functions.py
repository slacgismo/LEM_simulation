"""
Defines relevant functions for PV systems
"""
import gridlabd
import datetime
import numpy as np
import pandas
from dateutil import parser
from datetime import timedelta

from HH_global import PV_bid_rule, PV_forecast_rule, PV_forecast, allocation_rule
from HH_global import interval, prec, load_forecast, city, month

##############################
# Read in physical PV parameters
##############################

# Collect characteristics relevant for bidding
def get_settings(pvlist,interval,mysql=False):
      cols_PV = ['PV_name','house_name','inverter_name','rated_power','P_Out','P_before_curt','active','active_t1']
      df_PV = pandas.DataFrame(columns=cols_PV)

      # read out GLD model characteristics
      for PV in pvlist:
            house_name = 'GLD_'+PV[3:]
            inverter_name = 'PV_inverter_' + PV[3:]
            rated_power = float(gridlabd.get_object(inverter_name)['rated_power'])/1000
            df_PV = df_PV.append(pandas.Series([PV,house_name,inverter_name,rated_power,0.0,0.0,-1,-1],index=cols_PV),ignore_index=True)
      return df_PV

# Read previous generation of each PV (not synchronized yet, so from t-1)
def update_PV(dt_sim_time,df_PV_state):
      # Reset activity
      df_PV_state['active_t1'] = df_PV_state['active']
      df_PV_state['active'] = -1 # Reset : 1 - generating, 0 - curtailed, -1 - not generating/not curtailed
      # Read out generation and switch inverter back on if previously curtailed
      for ind in df_PV_state.index:
            P_Out = float(gridlabd.get_object(df_PV_state['inverter_name'].loc[ind])['P_Out'])/1000  #PV production in kW
            df_PV_state.at[ind,'P_Out'] = P_Out
            if df_PV_state['active_t1'].loc[ind] == 0:
                  PV = df_PV_state['PV_name'].loc[ind]
                  inverter = gridlabd.get_object(PV)['parent']
                  gridlabd.set_value(inverter,'generator_status','ONLINE')
      return df_PV_state

##############################
# Determine PV bids
##############################

# Determine PV bids according to provided PV bidding rule
def determine_bids(dt_sim_time,df_PV_state,retail):
      # Price component
      if PV_bid_rule == 'zero_MC':
            df_PV_state = calc_bids_PV_0MC(dt_sim_time,df_PV_state,retail)
      else:
            print('Provided PV rule does not exist.')
            print('Existing PV rules: zero_MC')
            print('Using zero_MC (zero marginal cost of supply) as default')
            df_PV_state = calc_bids_PV_0MC(dt_sim_time,df_PV_state,retail)
      # Quantity component
      if PV_forecast_rule == 'myopic':
            df_PV_state = calc_q_PV_myopic(dt_sim_time,df_PV_state,retail)
      elif PV_forecast_rule == 'perfect':
            df_PV_state = calc_q_PV_perfect(dt_sim_time,df_PV_state,retail)
      return df_PV_state

# Bids at marginal cost = 0
def calc_bids_PV_0MC(dt_sim_time,df_PV_state,retail):
      df_PV_state['p_sell'] = 0.0
      return df_PV_state

# Uses past generation to estimate generation in upcoming period
def calc_q_PV_myopic(dt_sim_time,df_PV_state,retail):
      df_PV_state['q_sell'] = df_PV_state['P_Out']
      # If PV system had been curtailed, bid last power when not curtailed
      df_PV_state['q_sell'].loc[df_PV_state['active_t1'] == 0] = df_PV_state['P_before_curt'].loc[df_PV_state['active_t1'] == 0]
      return df_PV_state

# Uses PV generation from benchmark scenario as perfect PV forecast
def calc_q_PV_perfect(dt_sim_time,df_PV_state,retail):
      try:
            df_PV_forecast = pandas.read_csv('Input_files/' + PV_forecast)
            df_PV_forecast['# timestamp'] = df_PV_forecast['# timestamp'].str.replace(r' UTC$', '')
            df_PV_forecast['# timestamp'] = pandas.to_datetime(df_PV_forecast['# timestamp'])
            df_PV_forecast.set_index('# timestamp',inplace=True)
            df_PV_forecast = df_PV_forecast[df_PV_state.PV_name]
            max_PV_forecast = df_PV_forecast.loc[(df_baseload.index >= dt_sim_time) & (df_baseload.index < dt_sim_time + pandas.Timedelta(str(int(interval/60))+' min'))].max()
      except:
            # Use myopic forecast if no PV forecast is found
            df_PV_state = calc_q_PV_myopic(dt_sim_time,df_PV_state,retail)
      return df_PV_state

##############################
# Submit PV bids
##############################

#Submits PV bids to market
def submit_bids_PV(dt_sim_time,retail,df_bids,df_supply_bids):
      for ind in df_bids.index:
            if df_bids['q_sell'].loc[ind] > 0.0:
                  retail.sell(df_bids['q_sell'].loc[ind],df_bids['p_sell'].loc[ind],gen_name=df_bids['PV_name'].loc[ind]) #later: pot. strategic quantity reduction
                  df_supply_bids = df_supply_bids.append(pandas.DataFrame(columns=df_supply_bids.columns,data=[[dt_sim_time,df_bids['PV_name'].loc[ind],float(df_bids['p_sell'].loc[ind]),float(df_bids['q_sell'].loc[ind])]]),ignore_index=True)
      return retail, df_supply_bids

##############################
# Set PVs according to allocation rule
##############################

# Sets PV after market clearing
def set_PV(dt_sim_time,market,df_bids,df_awarded_bids):
      if allocation_rule == 'by_price':
            # All buy bids above or at the clearing price dispatch (vice versa for demand)
            df_bids,df_awarded_bids = set_PV_by_price(dt_sim_time,df_bids,market.Pd,df_awarded_bids) 
      elif allocation_rule == 'by_award':
            # Bids only dispatch if explicitely selected by market operator (concerns bids == clearing_price)
            df_bids,df_awarded_bids = set_PV_by_award(dt_sim_time,df_bids,market,df_awarded_bids) 
      elif allocation_rule == 'statistical':
            # Bids only dispatch if explicitely selected by market operator (concerns bids == clearing_price) which is random
            df_bids,df_awarded_bids = set_PV_by_award(dt_sim_time,df_bids,market,df_awarded_bids)
      else:
            df_bids,df_awarded_bids = set_PV_by_price(dt_sim_time,df_bids, market.Pd,df_awarded_bids)
      return df_bids,df_awarded_bids

# Determines `active' based on price
def set_PV_by_price(dt_sim_time,df_bids,Pd,df_awarded_bids):
      # Determine activity
      df_bids['active'].loc[(df_bids['p_sell'] <= Pd) & (df_bids['q_sell'] > 0.0)] = 1.0 # active
      df_bids['active'].loc[(df_bids['p_sell'] > Pd) & (df_bids['q_sell'] > 0.0)] = 0.0 # curtail
      # For curtailed systems, save last P
      df_bids['P_before_curt'].loc[(df_bids['active'] == 0) & (df_bids['P_Out'] > 0.0)] = df_bids['P_Out'].loc[(df_bids['active'] == 0) & (df_bids['P_Out'] > 0.0)]
      # Curtail PV if necessary (previously curtailed systems are always re-dispatched in update())
      df_bids,df_awarded_bids = set_PV_GLD(dt_sim_time,df_bids,df_awarded_bids)
      return df_bids, df_awarded_bids

# Determines `active' based on market result
def set_PV_by_award(dt_sim_time,df_bids,market,df_awarded_bids):
      # Determine activity
      try:
            list_awards_S = market.S_awarded[:,3]
            list_awards_S = [x for x in list_awards_S if x is not None]
      except:
            list_awards_S = []
      for ind in df_bids.index:
            PV = df_bids['PV_name'].loc[ind]
            if PV in list_awards_S:
                  df_bids['active'].loc[ind] = 1.0
            elif df_bids['q_sell'].loc[ind] > 0.0: # positive bid but not cleared
                  df_bids['active'].loc[ind] = 0.0
            # else: neither cleared nor positive generation
      # Curtail PV if necessary (previously curtailed systems are always re-dispatched in update())
      df_bids,df_awarded_bids = set_PV_GLD(dt_sim_time,df_bids,df_awarded_bids)
      return df_bids, df_awarded_bids

# Implements `active' = 0 (curtailment)
def set_PV_GLD(dt_sim_time,df_bids,df_awarded_bids):
      for ind in df_bids.index:
            PV = df_bids['PV_name'].loc[ind]
            # Save awarded bid
            if df_bids['active'].loc[ind] == 1:
                  p_bid = df_bids['p_sell'].loc[ind]
                  q_bid = df_bids['q_sell'].loc[ind]
                  df_awarded_bids = df_awarded_bids.append(pandas.DataFrame(columns=df_awarded_bids.columns,data=[[dt_sim_time,PV,float(p_bid),float(q_bid),'S']]),ignore_index=True)
            #Set system_mode for active systems
            elif df_bids['active'].loc[ind] == 0:
                  # Curtail system
                  inverter = gridlabd.get_object(PV)['parent']
                  gridlabd.set_value(inverter,'generator_status','OFFLINE')
      return df_bids, df_awarded_bids

