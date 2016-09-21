# CalibRaTe
Calibration tool set for the Cosmic Ray Tagger

## Installation
CalibRaTor.py has some dependencies which need to be compiled:
- febdrv is the Front-End Board's driver
- histos is a histogram builder
- fitter is a histogram fitter

The python dependencies are best installed in within a virtual environment using virtualenv.
Numpy and zeromq are required in order to run CalibRaTor.py.

## Python API
The api folder is a python module and contains the required functionality to configure and run data acquistion on several CRT modules and evaluate and analyze the collected data. The api is split into two files to group the functionality into data acquisition (daq) and data evaluation (calc).

## Calibration process
To run CalibRaTor successfully start the driver

start the fitters instances

and run CalibRaTor.py
