#ifndef EVENT_H
#define EVENT_H

typedef struct {
		uint16_t mac5;
		uint16_t flags;
		uint32_t ts0;
		uint32_t ts1;
		uint16_t adc[32];
} EVENT_t;

#define EVLEN 76 //76 bytes -> 608 bits
#define MAGICWORD8 0xa5 //marker for the buffer start in the file
#define MAGICWORD16 0xaa55 //marker for the buffer start in the file
#define MAGICWORD32 0x01020255 //marker for the buffer start in the file

#endif

/*
#ifndef DRIVER_STATUS_H
#define DRIVER_STATUS_H

typedef struct {
	int status;
	int daqon;
	time_t datime;
	int nfebs;
	int msperpoll;
	// char string[64];
} DRIVER_STATUS_t;

#endif

#ifndef FEB_STATUS_H
#define FEB_STATUS_H

typedef struct {
	uint8_t mac[6];
	char fwcpu[64];
	char fwfpga[64];
	int connected;
	int configured;
	int biason;
	int error;
	uint16_t evtperpoll;
	uint16_t lostcpu;
	uint16_t lostfpga;
	float evtrate;
	// char string[128];
} FEB_STATUS_t;

#endif
*/

