# Local electricity market and transactive system simulation

This code integrates Python-based market code with a GridLAB-D simulation model of residential distribution systems. At the beginning of each market interval, physical information is gathered, transformed into bids and sent to a central market place where dispatch is determined. The Gridlab-D simulation implements the market result and updates the physical parameters of the system.

## System requirements

We use the docker container gridlabd/slac-master:latest, provided by SLAC on https://hub.docker.com/r/slacgismo/gridlabd . After you have installed docker, type the following line on your terminal:

```
docker pull gridlabd/slac-master:latest
```

The docker container provides the right GridlabD and python versions.

## Getting started

Access the docker container:

```
docker run -it -v ~/path_to_repo/LEM_simulation:/docker_powernet gridlabd/slac-master:latest
```

Navigate to the main path:

```
cd ..
cd docker_powernet
```

Start the simulation:

```
python3 02_run_market.py
```

We provide a sample glm file IEEE123_BP_2bus_1min.glm and IEEE_123_homes.glm . You will find the results in the folder 'Test_0001'.

## Extensions

You can document and adjust parameters of the market simulation in the file settings.csv . Use the ind variable in 02_run_market.py to switch settings.

You can easily adjust the bidding functions of devices in the modules HH_functions (for HVAC system), PV_functions (for PV), EV_functions (for electric vehicles), and battery_functions (for electric storage). The current default glm files include HVAC systems only.

You can modify the market clearing algorithm in market_functions.py .



