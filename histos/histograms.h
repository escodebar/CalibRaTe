#ifndef HISTOGRAMS_H
#define HISTOGRAMS_H

#include <stdint.h>
#include "definitions.h"

typedef struct {
	uint8_t  mac5;
	uint8_t  sc[SCRBYTELEN];
	uint32_t pedestal[NRCHNPERFEB][NRBINPERCHN];
	uint16_t gain[NRCHNPERFEB][NRBINPERCHN];
} HISTOGRAMS_t;

#endif
