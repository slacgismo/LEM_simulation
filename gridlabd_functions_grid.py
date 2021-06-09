# For the purpose of testing to read out grid information during operations

from dateutil import parser
import time
import gldimport

interval = 60

def on_init(t):
	global t0;
	t0 = time.time()

	global step;
	step = 0

	# Here, objects can be initialized
	# Careful: in the initilization phase, the GLD model has not been completed yet and only those properties are accessible,
	# which were hard-coded in the glm model
	# Others, like characteristics which are calculated based on hard-coded properties have not been calculated yet

	return True

def on_precommit(t):
	dt_sim_time = parser.parse(gridlabd.get_global('clock')).replace(tzinfo=None)

	#Run market only every interval
	if not (dt_sim_time.second%interval == 0):
		return t
	else: 
		print(dt_sim_time)

		# Gets all objects active in the simulation and accessible through python
		objects = gridlabd.get("objects") # this is a list
		print('All objects in this model')
		print(objects)
		print()

		# Get house characteristics for each house object
		houses = gldimport.find_objects('class=house') # function based on gridlabd.get("objects")
		for house in houses:
			house_obj = gridlabd.get_object(house) # this is a dictionary which includes all readable properties of this house object
			node = gridlabd.get_object(house_obj['parent'])['parent']
			k = float(house_obj['k'])
			T_min = float(house_obj['T_min'])
			T_max = float(house_obj['T_max'])
			heat_q = float(house_obj['heating_demand']) #heating_demand is in kW - gets overwritten by HVAC_settings
			hvac_q = float(house_obj['cooling_demand']) #cooling_demand is in kW
			heating_setpoint = float(house_obj['heating_setpoint'])
			cooling_setpoint = float(house_obj['cooling_setpoint'])
			T_air = float(house_obj['air_temperature'])
		
		# For last house (as an exmaple)
		print('Properties of '+house)
		print(house_obj)
		print('The house is connected to '+node+'\n')

		# Get characteristics of a node
		node_obj = gridlabd.get_object(node)
		print('Properties of '+node)
		print(node_obj)

		import pdb; pdb.set_trace()
		return t