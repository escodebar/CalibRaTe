#include "histos.h"


// Program documentation
const char *argp_program_version     = "histos 1.0";
const char *argp_program_bug_address = "<pablo.verges@lhep.unibe.ch>";
static char doc[] = "Histos -- a histogram builder for the feb driver";


// A description of the arguments we accept
static char args_doc[] = "[VCH0 [VCH1 VCH2 ... VCH31]]";


// Defines the input arguments
static struct argp_option options[] = {
	// General options
	{"verbose",    'v', 0,            0, "Produce verbose output" },
	{"debug",      'D', 0,            0, "Produce debug output" },
	{"continuous", 'C', 0,            0, "Run continuously" },
	{"all",        'A', 0,            0, "Enable all channels"},
	{"as_is",      'B', 0,            0, "Take power amplification from config file"},
	// Main histos options
	{"febsn",      'f', "SERIAL",     0, "The SERIAL number of the frontend board" },
	{"config",     'c', "FILE",       0, "Read configuration from FILE" },
	{"hexstring",  'x', "HEX",        0, "Read configuration from HEX" },
	{"events",     'n', "EVENTS",     0, "Number of EVENTS to collect" },
	// ZeroMQ ports to listen to
	{"driver",     'd', "DRIVER",     0, "Driver,      Ex. tcp://localhost:5555"},
	{"input",      'i', "INPUT",      0, "Data source, Ex. tcp://localhost:5556"},
	{"output",     'o', "OUTPUT",     0, "Data sink,   Ex. tcp://localhost:6000"},
	// Done
	{ 0 }
};


// Contains the available arguments
struct arguments {
	// Input 8bit DAC
	char     *args[32];
	// General options
	int      all;
	int      as_is;
	int      verbose;
	int      debug;
	int      continuous;
	int      voltages;
	// Main histos options
	uint8_t  feb;
	char     *sc_config;
	char     *pm_config;
	char     *sc_hex;
	char     *pm_hex;
	int      nrevents;
	// ZeroMQ ports to listen to
	char     *driver;
	char     *input;
	char     *output;
};


// Parses a single option
static error_t parse_opt (int key, char *arg, struct argp_state *state) {

	// Get the pointer to the arguments structure
	struct arguments *arguments = state->input;

	switch (key) {
		// General options
		case 'v':
			arguments->verbose = 1;
			break;
		case 'D':
			arguments->debug = 1;
			break;
		case 'C':
			arguments->continuous = 1;
			break;
		case 'A':
			arguments->all = 1;
			break;
		case 'B':
			arguments->as_is = 1;
			break;

		// Main histos options
		case 'f':
			arguments->feb = (uint8_t) atoi(arg);
			break;
		case 'c':
			arguments->sc_config = arg;
			break;
		case 'x':
			arguments->sc_hex = arg;
			break;
		case 'n':
			arguments->nrevents = atoi(arg);
			break;

		// ZeroMQ ports to listen to
		case 'd':
			arguments->driver = arg;
			break;
		case 'i':
			arguments->input = arg;
			break;
		case 'o':
			arguments->output = arg;
			break;

		// Input 8bit DAC
		case ARGP_KEY_ARG:
			if (state->arg_num >= 32) {
				argp_usage (state); // too many args
			}
			arguments->args[state->arg_num] = arg;
			break;
		case ARGP_KEY_END:
			arguments->voltages = 1;
			// if only one voltage is given, set it for all channels
			if (state->arg_num == 1) {
				for (int i = 1; i < 32; ++i) {
					arguments->args[i] = arguments->args[0];
				}
			}
			// either none, 1 or 32 input values need to be provided
			if (state->arg_num > 1 && state->arg_num < 32) {
				argp_usage (state); // not a valid range of arguments
			}
			break;

		// Unknown option
		default:
			return ARGP_ERR_UNKNOWN;
	}
	return 0;
}


// The argp parser
static struct argp argp = { options, parse_opt, args_doc, doc };


// Generates a config byte string as required by driver
void encrypt (uint8_t source[], uint8_t sink[], int length) {
	for (int from = length - 1; from >= 0; --from) {
		int to = (length - from - 1) / 8;
		if (source[from] == 1) {
			sink[to] |= (1 << (7 - from % 8));
		}
	}
}


// Removes spaces from char strings returning its new length
int remove_spaces(char *source) {
	char *i = source;
	char *j = source;
	do {
		*i = *j++;
		if (*i != ' ') {
			++i;
		}
	} while (*j != 0);
	*i = 0;
	return i - source; // return the new length
}


// reads a configuration from a file into a buffer of given size
// removing all line breaks, comments and spaces
void init_conf(char * fname, uint8_t * buf, int size) {

	// make sure the buffer is empty
	memset (buf, 0, MAXPACKLEN);

	// try to open file
	FILE * file = fopen(fname, "r");
	if (file <= 0) {
		// TODO Nr1
		printf ("Error: no such file %s\n", fname);
		exit(1);
	}

	// read the configuration file removing the comments and spaces
	char line[128];
	while (fgets (line, sizeof (line), file)) {
		char * ptr = strtok (line, "'");
		if (ptr != NULL) {
			strcat (buf, ptr);
		}
		else {
			strcat (buf, line);
		}
	}
	fclose (file);
	int bitlen = remove_spaces (buf);

	// check if the size of the configuration file is right
	if (bitlen != size) {
		// TODO Nr1
		printf (
			"Error: config %s mismatches length %d != %d\n",
			fname,
			bitlen,
			size
		);
		exit(1);
	}

	// translate from ascii to uint8_t
	for (int i = 0; i < bitlen; ++i) {
		if (buf[i] == '1') {
			buf[i] = 1;
		}
		if (buf[i] == '0') {
			buf[i] = 0;
		}
	}
}


// initializes a configuration buffer of given size
void init_hex_conf(char * hex, uint8_t * buf, int size) {

	// start with empty buffers
	uint8_t tmp[MAXPACKLEN] = {0};
	memset (buf, 0, MAXPACKLEN);

	// translate from hex to uint8_t
	for (int i = 0; i < size; ++i) {
		int x = 0;
		sscanf (hex + i, "%1x", &x);
		for (int j = 0; j < 4; ++j) {
			if (x >= pow(2,3-j)) {
				tmp[i*4+j] = 1;
				x -= pow (2,3-j);
			}
		}
	}

	// change endianness
	for (int i = 0; i < size/2; ++i) {
		for (int j = 0; j < 8; ++j) {
			buf[8*i+j] = tmp[8*(size/2 - i - 1)+j];
		}
	}

}


// changes the value of the input 8 bit dac in a configugariton buffer
void set_input_8bit_dac (uint8_t sc[], char * voltages[]) {

	// translate from ascii to uint8_t
	for (int chn = 0; chn < NRCHNPERFEB; ++chn) {
		int bit = 331 + chn * 9;
		uint8_t voltage = (uint8_t) atoi(voltages[chn]);
		for (int j = 0; j < 8; ++j) {
			sc[bit + 7 - j] = voltage % 2;
			voltage = voltage / 2;
		}
	}
}


// sends configuration bitstring to driver
void send_conf (uint8_t sc[], uint8_t pm[], void * driver, uint8_t mac5, int debug) {
	
	// configurations need to be byte coded
	uint8_t sc_bytes[MAXPACKLEN] = {0};
	uint8_t pm_bytes[MAXPACKLEN] = {0};
	encrypt (sc, sc_bytes, SCRBITLEN);
	encrypt (pm, pm_bytes, SCRBITLEN);

	if (debug) {
		printf("SETCONF for %02x: ", mac5);
		for (int i = 0; i < SCRBYTELEN; ++i) {
			printf("%02x", sc_bytes[i]);
		}
		printf("\n");
	}

	char cmd[32];
	sprintf (cmd,"SETCONF");
	cmd[8] = mac5;

	uint8_t buffer[MAXPACKLEN] = {0};

	memcpy (buffer, cmd, 9);
	memcpy (buffer + 9, sc_bytes, SCRBYTELEN);
	memcpy (buffer + 9 + SCRBYTELEN, pm_bytes, PMRBYTELEN);

	zmq_send_const (driver, buffer, 9 + SCRBYTELEN + PMRBYTELEN, 0);
	zmq_recv (driver, buffer, 3, 0);

	// TODO: Nr3
}


// sends command to driver
void send_command (const char * command, void * driver, uint8_t mac5) {
	char cmd[9];
	sprintf (cmd, command);
	cmd[8] = mac5;

	// generate the buffer to send
	zmq_send_const (driver, cmd, 9, 0);
	zmq_recv (driver, cmd, 3, 0);

	// TODO: Nr3
}


int main (int argc, char **argv) {

	struct arguments arguments;

	/* Default values. */
	arguments.verbose    = 0;
	arguments.debug      = 0;
	arguments.all        = 0;
	arguments.as_is      = 0;
	arguments.continuous = 0;
	arguments.feb        = 255;
	arguments.nrevents   = 5000;
	arguments.sc_config  = "CONF/SC.txt";
	arguments.pm_config  = "CONF/PM.txt";
	arguments.sc_hex     = "";
	arguments.pm_hex     = "";
	arguments.driver     = "tcp://localhost:5555";
	arguments.input      = "tcp://localhost:5556";
	arguments.output     = "tcp://localhost:6000";
	arguments.voltages   = 0;

	for (int i = 0; i < 32; ++i) {
		arguments.args[i] = "";
	}

	/* Parse our arguments; every option seen by parse_opt will
	 *      be reflected in arguments. */
	argp_parse (&argp, argc, argv, 0, 0, &arguments);

	// TODO: add the config file in hexadecimal to output
	if (arguments.verbose) {
		printf ("FEB S/N = %02x\n", arguments.feb);

		if (arguments.voltages) {
			puts("VOLTAGE = [");
			for (int i = 0; i < 32; ++i) {
				printf ("%02d", atoi (arguments.args[i]));
				if (i != 31) {
					printf (",");
				}
			}
			printf("]\n");
		}
	}

	// START
	// create the zmq context and their sockets
	void *context  = zmq_ctx_new ();
	void *driver   = zmq_socket (context, ZMQ_REQ);
	void *input    = zmq_socket (context, ZMQ_SUB);
	void *output   = zmq_socket (context, ZMQ_PUSH);

	// connect the sockets and set the right options
	zmq_connect (driver, arguments.driver);
	zmq_connect (input,  arguments.input);
	zmq_connect (output, arguments.output);
	
	if (arguments.verbose) {
		printf ("Connected to driver: %s\n", arguments.driver);
		printf ("Connected to input:  %s\n", arguments.input);
		printf ("Connected to output: %s\n", arguments.output);
	}
	
	// set the subscription options
	zmq_setsockopt (input, ZMQ_SUBSCRIBE, NULL, 0);

	// initialize the config arrays
	uint8_t sc[MAXPACKLEN] = {0};
	uint8_t pm[MAXPACKLEN] = {0};

	// start the configurations either from the hex-string or file
	if (arguments.sc_hex != "") {
		if (arguments.debug) {
			puts ("Reading SC configuration from hex string");
		}
		init_hex_conf (arguments.sc_hex, sc, SCRHEXLEN);
	}
	else {
		if (arguments.debug) {
			puts ("Reading SC configuration from file");
		}
		init_conf (arguments.sc_config, sc, SCRBITLEN);
	}
	if (arguments.pm_hex != "") {
		if (arguments.debug) {
			puts ("Reading PM configuration from file");
		}
		init_hex_conf (arguments.pm_hex, pm, PMRHEXLEN);
	}
	else {
		if (arguments.debug) {
			puts ("Reading PM configuration from hex string");
		}
		init_conf (arguments.pm_config, pm, PMRBITLEN);
	}

	if (arguments.verbose) {
		printf ("Using configuration: %s\n", arguments.sc_config);
	}

	if (arguments.verbose) {
		printf ("Collecting %d events\n", arguments.nrevents);
	}

	//set_input_8bit_dac (sc, arguments.args);

	do {

		// initialize the histogram and add feb's mac5 and the used config
		HISTOGRAMS_t histogram = {0};
		histogram.mac5 = arguments.feb;
		encrypt (sc, histogram.sc, SCRBITLEN);

		/**
		 * Start data collection
		 **/

		for (int pair = 0; (2*pair) < NRCHNPERFEB; ++pair) {

			// Display progress bar
			if (arguments.verbose) {
				printf("\rCollecting data[");
				for (int i = 0; i < NRCHNPERFEB; ++i) {
					if (i <= (2*pair) + 1) {
						printf("#");
					}
					else {
						printf(" ");
					}
				}
				printf("]");
				fflush(stdout);
			}

			// set power amplification to trigger only for 'pair'
			// refer to CITIROC Slow Control Register
			if (arguments.as_is != 1) {
				for (int chn = 0; chn < NRCHNPERFEB; ++chn) {
					int bit = 633 + chn * 15;
					if (chn/2 == pair || arguments.all == 1) {
						sc[bit] = 0; // set 0 to enable !!
					}
					else {
						sc[bit] = 1; // set 1 to disable !!
					}
				}
			}

			// change the configuration for this feb,
			// stop daq temporarily
			send_command ("DAQ_END", driver, 255);
			send_command ("BIAS_OF", driver, arguments.feb);
			send_conf (sc, pm, driver, arguments.feb, arguments.debug);
			send_command ("BIAS_ON", driver, arguments.feb);
			sleep(2);
			send_command ("DAQ_BEG", driver, 255);

			// collect events and sort them in a histogram
			int nr_events_left;
			if (arguments.as_is == 1 || arguments.all == 1) {
				nr_events_left  = arguments.nrevents / 16;
			}
			else {
				nr_events_left = arguments.nrevents;
			}

			do {

				// get some events
				zmq_msg_t events;
				zmq_msg_init (&events);
				zmq_msg_recv (&events, input, 0);

				// iterate through the events and add them to the histogram
				EVENT_t event;
				void * ptr = (void *) zmq_msg_data (&events);

				do {
					// read event and move the pointer to the next one
					memcpy (&event, ptr, sizeof (EVENT_t));
					ptr += sizeof (EVENT_t);

					// handle only events for our feb
					if (event.mac5 == arguments.feb) {

						--nr_events_left;

						// TODO: FEATURE: process events differently here to use histos as an event filter

						if (arguments.all == 1 || arguments.as_is == 1) {
							int max = 0;
							int triggered_channel = 0;

							// Find which channel has the highest signal
							for (int i = 0; i < NRCHNPERFEB; ++i) {
								if (event.adc[i] > max) {
									max = event.adc[i];
									triggered_channel = i;
								}
							}

							int triggered_pair = triggered_channel / 2;

							for (int i = 0; i < NRCHNPERFEB; ++i) {
								if (i/2 != triggered_pair) {
									// store into pedestal if the signal isn't the highest
									histogram.pedestal[i][event.adc[i]]++;
								}
								else {
									// store into gain if the signal is the highest
									histogram.gain[i][event.adc[i]]++;
								}
							}
						}
						else {
							// store the event's data in the histogram
							for (int i = 0; i < NRCHNPERFEB; ++i) {
								if (i/2 != pair) {
									// store into pedestal if the channel is
									// not one of the active pair
									histogram.pedestal[i][event.adc[i]]++;
								}
								else {
									// store into gain if the channel is one
									// of the active pair
									histogram.gain[i][event.adc[i]]++;
								}
							}
						}
					}

				// TODO: do more checking here
				} while (event.ts1 != MAGICWORD32);

				zmq_msg_close (&events);

			} while (nr_events_left > 0);

		}

		if (arguments.verbose) {
			printf("\n");
		}

		/**
		 * Push data to output
		 **/

		// send histograms to output
		zmq_msg_t task;
		zmq_msg_init_size (&task, sizeof (HISTOGRAMS_t));
		memcpy (zmq_msg_data (&task), &histogram, sizeof (HISTOGRAMS_t));
		zmq_msg_send (&task, output, 0);
		zmq_msg_close (&task);

		if (arguments.verbose) {
			puts ("Sent task to output");
		}
	
	} while (arguments.continuous);

	zmq_close (driver);
	zmq_close (input);
	zmq_close (output);

	zmq_ctx_destroy (context);

	return 0;
}
