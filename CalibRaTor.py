import argparse
import numpy as np
import os
import pickle

# import the APIs
import api.daq  as daq
import api.calc as calc

def calibrate(
  crts,
  gain=75,
  bias_range=[],
  bias_settings=[180, 185, 190, 195, 200],
  conf='CONF/CITIROC_SC_PROFILE1.txt',
  driver='tcp://localhost:5555',
  data='tcp://localhost:5556',
  task_output='tcp://localhost:7000',
  task_input='tcp://localhost:8000',
  path='data',
  sipms=range(32)
):

  # load the configuration file
  daq.load_config_file(path=conf, febs=crts)

  # acquire data for each bias voltage
  for bias in bias_settings:
    print("Acquiring data for bias %d" % bias)
    os.makedirs('%s/bias_%d' % (path, bias), exist_ok=True)
    daq.set_voltages(bias, crts)
    daq.acquire(
      crts,
      path='%s/bias_%d' % (path, bias),
      driver=driver,
      data=data
    )

  # compute the gains for each bias voltage
  gains = {}
  for bias in bias_settings:
    print("Loading the generated histograms for bias %d" % bias)
    histograms = calc.get_histograms('%s/bias_%d/*.histos' % (path, bias))
    for crt in crts:
      print("Fitting the peaks for CRT %d" % crt)
      peaks, distances = calc.get_peaks_and_distances(
          histograms[crt],
          output_socket=task_output,
          input_socket=task_input,
          sipms=sipms
      )
      print("Computing the gains for CRT %d" % crt)
      _gains = calc.get_gains(distances, sipms)
      for sipm in _gains:
        gains[(crt, sipm, bias)] = _gains[sipm]

  # Store the gains in a text file
  for crt in crts:
    for bias in bias_settings:
      f = open(
        '%s/bias_%d/%02x-%s.gains' % (args.path, bias, crt, str(datetime.now())),
        'w'
      )
      _sipms = [sipm for sipm in sipms if (crt, sipm, bias) in gains]
      _gains = [gains[(crt, sipm, bias)][0][1] for sipm in sipms if (crt, sipm, bias) in gains]
      _uncerts = [gains[(crt, sipm, bias)][0][2] for sipm in sipms if (crt, sipm, bias) in gains]
      f.write("\n".join(["%d: %.2f (%.2f)" % (_s, _g, _u)
        for _s, _g, _u in zip(_sipms, _gains, _uncerts)
      ]))
      f.close()
  print("Stored the computed gains")

  # compute the dependencies of the gain on the bias for each sipm
  print("Computing the dependencies of the gains on the bias setting")
  dependencies = {}
  for crt in crts:
    for sipm in sipms:
      # require at least 3 valid gains to compute the dependency
      if len([1
        for bias in bias_settings
        if (crt, sipm, bias) in gains
      ]) >= 3:

        a, b = np.polyfit(
          [bias for bias in bias_settings if (crt, sipm, bias) in gains],
          [gains[(crt, sipm, bias)][0][1]
            for bias in bias_settings
            if (crt, sipm, bias) in gains
          ],
          1,
          w=[1./gains[(crt, sipm, bias)][0][2]
            for bias in bias_settings
            if (crt, sipm, bias) in gains
          ]
        )
        # TODO: use the uncertainties!
        dependencies[(crt, sipm)] = (a, b)

  # Store the dependencies in a text file
  for crt in crts:
    f = open(
      '%s/%02x-%s.dependencies' % (args.path, crt, str(datetime.now())),
      'w'
    )
    _sipms = [sipm for sipm in sipms if (crt, sipm) in dependencies]
    _aa = [dependencies[(crt, sipm)][0] for sipm in sipms if (crt, sipm) in dependencies]
    _bb = [dependencies[(crt, sipm)][1] for sipm in sipms if (crt, sipm) in dependencies]
    f.write("SiPM\tSlope\tOffset" + "\n".join(["%d\t%.2f\t%.2f" % (_s, _g, _u)
      for _s, _g, _u in zip(_sipms, _aa, _bb)
    ]))
    f.close()
  print("Stored the computed dependencies")

  # compute the bias for each sipm to get the right gain
  print("Computing the bias settings for a gain of %d adc/p.e." % gain)
  bias_settings = {}
  for crt in crts:
    for sipm in sipms:
      if (crt, sipm) in dependencies:
        a, b = dependencies[(crt, sipm)]
        bias = int(round(gain - b) / a)
        _s = int(round(gain - b) / a)
        bias_settings[(crt, sipm)] = _s
        if _s < bias_range[0]:
          print("  Bias below range for CRT Module %d SiPM %d - setting %d" % (crt, sipm, min(bias_range)))
          bias_setting[(crt, sipm)] = min(bias_range)
        if _s > bias_range[1]:
          print("  Bias above range for CRT Module %d SiPM %d - setting %d" % (crt, sipm, max(bias_range)))
          bias_setting[(crt, sipm)] = max(bias_range)
      else:
        print("  Bias setting couldn't be computed for CRT Module %d SiPM %d - setting %d" % (crt, sipm, int(sum(bias_range)/2)))
        bias_settings[(crt, sipm)] = int(sum(bias_range)/2)

  # Store the computed bias settings in a text file
  for crt in crts:
    f = open(
      '%s/%02x-%s.caliblated_bias_settings' % (args.path, crt, str(datetime.now())),
      'w'
    )
    _sipms = [sipm for sipm in sipms if (crt, sipm) in bias_settings]
    _bias = [bias_settings[(crt, sipm)] for sipm in sipms if (crt, sipm) in bias_settings]
    f.write("SiPM\tbias" + "\n".join(["%d\t%d" % (_s, _b)
      for _s, _b in zip(_sipms, _bias)
    ]))
    f.close()
  print("Stored the computed bias settings")

  # acquire data to test the calibrated bias setting
  print("Acquiring data to evaluate calibration")
  for crt in crts:
    daq.set_voltages([bias_settings[(crt, sipm)] for sipm in sipms], crt)
  os.makedirs('%s/evaluation' % path, exist_ok=True)
  daq.acquire(
    crts,
    path='%s/evaluation' % path,
    driver=driver,
    data=data
  )

  # Compute the gains for evaluation
  print("Computing the gains to evaluate calibration")
  gains = {}
  histograms = calc.get_histograms('%s/evaluation/*.histos' % path)
  for crt in crts:
    peaks, distances = calc.get_peaks_and_distances(histograms[crt])
    _gains = calc.get_gains(distances, sipms)
    for sipm, _g in zip(sipms, _gains):
      gains[(crt, sipm)] = _g
  print(gains)

  # Store the results
  for crt in crts:
    f = open(
      '%s/evaluation/%02x-%s.gains' % (args.path, crt, str(datetime.now())),
      'w'
    )
    _sipms = [sipm for sipm in sipms if (crt, sipm) in gains]
    _gains = [gains[(crt, sipm)][0][1] for sipm in sipms if (crt, sipm) in gains]
    _uncerts = [gains[(crt, sipm)][0][2] for sipm in sipms if (crt, sipm) in gains]
    f.write("\n".join(["%d: %.2f (%.2f)" % (_s, _g, _u)
      for _s, _g, _u in zip(_sipms, _gains, _uncerts)
    ]))
    f.close()
  print("Stored the computed gains")


if __name__ == '__main__':

  parser = argparse.ArgumentParser(
    description='Calibrates CRT modules'
  )
  parser.add_argument(
    '--crt', nargs='*', type=int, default=[],
    help='CRT modules to calibrate'
  )
  parser.add_argument(
    '--bias', nargs='*', type=int, default=[180, 185, 190, 195, 200],
    help='Bias settings to sample histograms to determine the gain vs bias dependency.'
  )
  parser.add_argument(
    '--bias_range', nargs=2, type=int, default=[],
    help='Range of allowed bias settings'
  )
  parser.add_argument(
    '--gain', nargs='?', type=int, default=75,
    help='Nominal gain in adc/p.e. to which the CRT modules are set'
  )
  parser.add_argument(
    '--driver', nargs='?', type=str, default='tcp://localhost:5555',
    help='Socket to driver              Ex. tcp://localhost:5555'
  )
  parser.add_argument(
    '--data', nargs='?', type=str, default='tcp://localhost:5556',
    help='Socket to data                Ex. tcp://localhost:5556'
  )
  parser.add_argument(
    '--fitter_input', nargs='?', type=str, default='tcp://localhost:7000',
    help='Socket to push tasks to       Ex tcp://localhost:7000'
  )
  parser.add_argument(
    '--fitter_output', nargs='?', type=str, default='tcp://localhost:8000',
    help='Socket to push tasks to       Ex tcp://localhost:8000'
  )
  parser.add_argument(
    '--stats', nargs='?', type=str, default='tcp://localhost:5557',
    help='Socket to stats               Ex. tcp://localhost:5557'
  )
  parser.add_argument(
    '--conf', nargs='?', type=str, default='CONF/SC.txt',
    help='Path to template config file  Ex. CONF/SC.txt'
  )
  parser.add_argument(
    '--path', nargs='?', type=str, default='data',
    help='Path to folder where the adquired data and results are stored'
  )
  args = parser.parse_args()

  crts = args.crt or daq.connected_febs(socket=args.stats)
  bias_range = args.bias_range or [min(args.bias), max(args.bias)]

  calibrate(
    crts,
    gain=args.gain,
    bias_settings=args.bias,
    bias_range=bias_range,
    conf=args.conf,
    driver=args.driver,
    data=args.data,
    path=args.path,
    task_output=args.fitter_input,  # input, output, it's all a point of view
    task_input=args.fitter_output,
    sipms=range(32)
  )

