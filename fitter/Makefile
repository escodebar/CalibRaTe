VERSION = 1.0

ROOTC=`root-config --cflags`
ROOTL=`root-config --glibs`

fitter: fitter.cpp
	g++ -ansi fitter.cpp -o fitter $(ROOTC) -lboost_program_options $(ROOTL) -lGui -lCore -lRIO -lNet -lHist -lGraf -lGraf3d -lGpad -lTree -lRint -lPostscript -lMatrix -lPhysics -lSpectrum -lMathCore -lThread -pthread -lm -ldl -rdynamic -lzmq

