# CalibRaTe
Calibration tool set for the Cosmic Ray Tagger

CalibRaTor needs some work to be done before running on any machine.
febdrv, histos and fitter need to be compiled in the host before CalibRaTor can be run.

febdrv is the Front-End Board's driver written in c by Igor Kreslo, the only dependency is libzmq3-dev

histos is a histogram builder written in c, the only dependency is libzmq3-dev

fitter is a histogram fitter written in c++, the dependencies are libboost-program-options and the data analysis framework root.

The api python module contains the required functionality to configure and run data acquistion on several CRT modules and evaluate and analyze the collected data. The api is split into two files to group the functionality into data acquisition (daq) and data evaluation (calc).

The python dependencies are best installed in within a virtual environment using virtualenv. Numpy and zeromq are required in order to run the software.

To run CalibRaTor successfully start the driver, check its output, start the fitters instances using the balancer.py script and run CalibRaTor.
This process can be improved by let CalibRaTor start the febdrv and fitter instances automatically.
