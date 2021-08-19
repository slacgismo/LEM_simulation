import os

# Result file
results_folder = 'Results'
if not os.path.exists(results_folder):
	os.makedirs(results_folder)

# Pricing
pricing = 'LEM' # to be implemented

# For glm
glm_model = 'default_model.glm'
slack_node = 'node_149'

# For market
interval = 300
HVAC_bid_rule = 'quantile'
allocation_rule = 'statistical'
C_import = 1000.
C_export = 0. # no export allowed
market_data = 'Ercot_LZ_South.csv'
grid_tariffs = 0.0 # [USD/kWh] additional price component, gets added to cost of supply

#glm parameters
city = 'Austin'
month = 'july'
start_time_str = '2016-07-31 00:00'
end_time_str = '2016-08-08 00:00'
player_dir = 'players_Austin'
tmy_file = '722540TYA.tmy3'

#Flexible appliances
EV_data = 'None'

#Market parameters

p_min = 0.0
p_max = 10000.0
load_forecast = 'myopic'
unresp_factor = 1.0
FIXED_TARIFF = False
interval = 300
allocation_rule = 'by_price'

#Appliance specifications
delta = 3.0 #temperature bandwidth - HVAC inactivity
ref_price = 'forward'
price_intervals = 36 #p average calculation 
which_price = 'none' #battery scheduling

#precision in bidding and clearing price
prec = 4
M = 10000 #large number
ip_address = 'none'
