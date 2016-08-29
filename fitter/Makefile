VERSION = 1.0

# TODO: I used a local ROOT build in ~/builds
#       Change the include and library paths

fitter: fitter.cpp
	g++ -Wall -ansi fitter.cpp -o fitter -pthread -std=c++11 -Wno-deprecated-declarations -m64 -lboost_program_options -I/home/verges/builds/include -L/home/verges/builds/lib -lGui -lCore -lRIO -lNet -lHist -lGraf -lGraf3d -lGpad -lTree -lRint -lPostscript -lMatrix -lPhysics -lSpectrum -lMathCore -lThread -pthread -lm -ldl -rdynamic -lzmq

