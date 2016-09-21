import pickle
import struct
import subprocess
import time
import zmq

from datetime import datetime


## internal variables

# keeps the configuration hex strings for the febs
_configs = {}


## internal functions

def _bits_to_hex(bitstring):
    """Converts a string of bits into a string of hexadecimals

       IMPORTANT: byte inverted
       '0101110111101001' = '5DE9'
        --------========     --==
           '--------|--------'  |
                    '-----------'
    """
    # encrypted changes endiannes of the bitstring,
    # change the docstring above if encrypt change this behavior
    encrypted = _encrypt(bitstring)
    return ("{:02x}"*len(encrypted)).format(*encrypted)


def _bits_from_file(path='CONF/CITIROC_SC_PROFILE1.txt'):
    """Reads the content of a file and strips comments, whitespace and newlines"""

    conffile = open(path, 'r')
    bitstring = "".join([line.split("'")[0].replace(' ','') for line in conffile])
    conffile.close()
    return bitstring


def _edit_bits(bitstring, position, length, value):
    """Returns a bitstring with the given value of length length at position position"""

    powers = list(range(length))
    conf = ""

    # iterate through the bits (powers of 2)
    # from most significant bit to least significant bit
    powers.reverse()
    for power in powers:
        if value >= 2**power:
            conf = conf + '1'
            value -= 2**power
        else:
            conf = conf + '0'

    return bitstring[:position] + conf + bitstring[position + length:]


def _encrypt(bitstring):
    """generates a list of bytes out of a string of bits

       IMPORTANT: byte inverted
       '0101110111101001' = [93, 233]
        --------========     --  ===
           '--------|--------'    |
                    '-------------'
    """

    size = len(bitstring)

    encrypted = []
    for byte in range(int(size / 8)):

        # get the next 8 bits and convert them to integers
        value = int(bitstring[8*byte:8*(byte+1)], 2)

        # by inserting the values at position 0, we're inverting
        # the sequence of bytes, as required by the driver
        encrypted.insert(0, value)

    return encrypted


# API functions

def connected_febs(socket="tcp://localhost:5557"):
    """Returns a list containing the serial numbers of the connected febs"""

    # zeromq connections
    context = zmq.Context()

    # statistics publisher
    statistics = context.socket(zmq.SUB)
    statistics.connect(socket)
    statistics.setsockopt(zmq.SUBSCRIBE, b"")

    # get the list of connected febs
    message = statistics.recv_string()
    message_parts = message.split('\n')[1:-1]
    feb_entries = [entry for entry in message_parts if 'FEB' in entry]
    mac_addresses = [feb.split(' ')[1] for feb in feb_entries]

    # the connected feb's serial numbers
    febs = [int(address.split(':')[-1], 16) for address in mac_addresses]

    # close the context and the socket
    statistics.close()
    context.term()

    # store the febs
    for feb in febs:
        if feb not in _configs:
            _configs[feb] = None

    # TODO: close the context

    return febs


def load_config_file(path="CONF/CITIROC_SC_PROFILE1.txt", febs=[]):
    """Loads a configuration file for the given list of febs.
    If the list of febs is empty, load configuration for all the febs."""

    # We need a list of febs, if only one is given,
    # generate a list witha single element
    if type(febs) == int:
        febs = [febs]

    # Use all connected febs if the given list is empty
    if not len(febs):
        febs = _configs.keys()

    # Load the bitstring from the configuration file
    bitstring = _bits_from_file(path)

    for feb in febs:
        _configs[feb] = bitstring


def set_voltages(values, febs=[]):
    """Sets the voltages for the given febs.
    If only one voltage is set, set all channels to the same value.
    If the list of febs is empty, set the voltages for all the febs."""

    # We need a list of febs, if only one is given,
    # generate a list with a single element
    if type(febs) == int:
        febs = [febs]

    # Use all connected febs if the given list is empty
    if not len(febs):
        febs = _configs.keys()

    # We need a list of voltages, if only one is given,
    # generate a list of 32 elements with the same value
    if type(values) == int:
        values = [values]*32

    # Set the voltages for the given febs
    for feb in febs:
        bitstring = _configs[feb]

        for channel in range(32):
            bitstring = _edit_bits(
                bitstring=bitstring,
                position=331+9*channel,
                length=8,
                value=values[channel]
            )

        _configs[feb] = bitstring


def set_thresholds(values, febs=[]):
    """Sets the threshold for the given febs.
    If only one threshold is set, set both thresholds to the same value.
    If the list of febs is empty, set the threshold for all the febs."""

    # We need a list of febs, if only one is given,
    # generate a list with a single element
    if type(febs) == int:
        febs = [febs]

    # Use all connected febs if the given list is empty
    if not len(febs):
        febs = _configs.keys()

    # We need a list of voltages, if only one is given,
    # generate a list of 32 elements with the same value
    if type(values) == int:
        values = [values]*2

    # Set the threshold for the given febs
    for feb in febs:
        bitstring = _configs[feb]

        bitstring = _edit_bits(
            bitstring=bitstring,
            position=1107,
            length=10,
            value=values[0]
        )

        bitstring = _edit_bits(
            bitstring=bitstring,
            position=1117,
            length=10,
            value=values[1]
        )

        _configs[feb] = bitstring


def start_histos(
    febs=[],
    events=1000,
    driver='tcp://localhost:5555',
    input_socket='tcp://localhost:5556',
    output_socket='tcp://localhost:9999',
    continuous=False,
    enable_all=False
):
    """Starts histogram builders for the given list of febs.
    If the list of febs is empty, start histogram builders for all the febs."""

    # We need a list of febs, if only one is given,
    # generate a list with a single element
    if type(febs) == int:
        febs = [febs]

    # Use all connected febs if the given list is empty
    if not len(febs):
        febs = _configs.keys()

    # Standard input arguments
    input_args = [
        './histos/histos',
        '--events', str(events),
        '--driver', driver,
        '--input',  input_socket,
        '--output', output_socket
    ]

    # Run in continuous mode
    if continuous:
      input_args += ['--continuous']

    # Enable all channels
    if enable_all:
      input_args += ['--all']

    # Start a histos subprocess for every connected feb
    return [subprocess.Popen(
        input_args + ['--febsn', str(feb), '--hexstring', _bits_to_hex(_configs[feb])]
    ) for feb in febs if feb in _configs and _configs[feb] is not None]


def task_to_data(data):
  """Unpacks a histos task into a tuple of data containing"""

  # generate the structure and unpack the data to it
  U = struct.unpack(
      'B' + 'B'*143 + 'I'*32*4096 + 'H'*32*4096,
      data[:1+143+4*32*4096+2*32*4096]
  )

  # read out the data
  mac5      = U[0]
  config    = ('{:02x}'*143).format(*U[1:1+143])
  pedestals = [U[1+143+i*4096:][:4096] for i in range(32)]
  spectra   = [U[1+143+32*4096+i*4096:][:4096] for i in range(32)]

  # return the unpacked data
  return mac5, config, pedestals, spectra


def acquire(
  crts,
  path='data',
  nr_histograms=12,
  events=5000,
  driver='tcp://localhost:5555',
  data='tcp://localhost:5556',
  port=6000
):
  """Collects and stores a number of histograms with a given
  number of events for the given list of CRT modules"""

  context = zmq.Context()
  puller  = context.socket(zmq.PULL)
  puller.bind('tcp://*:%d' % port)

  # force crts to be a list
  if type(crts) == int:
    crts = [crts]

  # Start the histogram builders
  histos = start_histos(
    febs=crts,
    events=events,
    driver=driver,
    input_socket=data,
    output_socket='tcp://localhost:%d' % port,
    continuous=True
  )
  print("  Started observations ", str(datetime.now()))

  # Collect a certain number of histograms in total
  counters = [0]*len(crts)
  while min(counters) < nr_histograms:
    task = puller.recv()
    crt, config, pedestals, spectra = task_to_data(task)

    # Count up the task
    counters[crts.index(crt)] += 1

    now = str(datetime.now())
    print(now, ' - got histograms from CRT module %d' % crt)

    f = open('%s/%02x-%s.task' % (path, crt, now), "wb")
    pickle.dump(task, f)
    f.close()

    f = open('%s/%02x-%s.histos' % (path, crt, now), "wb")
    pickle.dump((crt, config, pedestals, spectra), f)
    f.close()

  # Stop the running histos instances
  for h in histos:
    h.terminate()

  print('Finished round at %s' % str(datetime.now()))

  # TODO: close the context or use the python decorator
