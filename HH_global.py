import os

# Result file
benchmarking_folder = 'Benchmarking'
input_folder = 'Input_files'
results_folder = 'Results'
if not os.path.exists(results_folder):
	os.makedirs(results_folder)

# Pricing
pricing = 'LEM' # Options: fixed, LEM ; to be implemented: ToU

# For glm
glm_model = '6houses_model.glm' #'default_model.glm' # 
slack_node = 'node_149'

# For market
interval = 300 # runs market every X second
p_min = -10000.0
p_max = 10000.0
C_import = 1000.
C_export = 0. # no export allowed
market_data = 'Ercot_LZ_South.csv'
grid_tariffs = 0.0 # [USD/kWh] additional price component, gets added to cost of supply
allocation_rule = 'price'

# Customer behavior
unresp_load_forecast_rule = 'perfect'
unresp_load_forecast = 'perfect_unrespload_forecast.csv'
HVAC_bid_rule = 'economic_quadratic'
PV_bid_rule = 'zero_MC'
PV_forecast_rule = 'perfect' # Option: myopic, perfect
PV_forecast = 'perfect_PV_forecast.csv' # Refers to file with PV forecast
battery_bid_rule = 'threshold_based' # simple_mean, threshold_based, optimal

#glm parameters
city = 'Austin'
month = 'july'
start_time_str = '2016-07-31 12:00'
end_time_str = '2016-08-01 00:00'
player_dir = 'players_Austin'
tmy_file = '722540TYA.tmy3'

#Flexible appliances
EV_data = 'None'

#Market parameters


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
