from plotly.offline import iplot
from random         import sample
from scipy.optimize import curve_fit

import plotly.graph_objs as go
import numpy             as np
import glob
import json
import pickle
import sys
import zmq

## internal functions

def _gauss(x, A, μ, σ):
  return A * np.exp(- (x-μ)**2 / (2.0 * σ**2))

def _fit_gaussian(histogram, A=0, μ=0, σ=0, visuals=False):
  # histogram is a dict of {binnr: value}

  try:
    xdata = [x for x in histogram if int(μ-3*σ) <= x <= int(μ+3*σ)]
    ydata = [histogram[x] for x in xdata]

    missing = 3 - len(xdata)

    params, pcov = curve_fit(
      _gauss,
      xdata + [0]*missing,
      ydata + [0]*missing,
      p0=[A, μ, σ]
    )

    x_range = np.linspace(min(xdata), max(xdata), 100)
    y_gauss = _gauss(x_range, params[0], params[1], params[2])

    if visuals:
      iplot(go.Figure(
        data=[go.Bar(
          x=xdata,
          y=ydata,
          name='data'
        ), go.Scatter(
          x=x_range,
          y=y_gauss,
          name='μ=%.2f (%.2f)' % (params[1], pcov[1][1])
        )],
        layout=go.Layout(
          title='Fitted gaussian',
          xaxis={'title':'ADC Counts / Bin Nr'},
          yaxis={'title':'Nr Events'}
        )
      ))

    return (params[0], params[1], params[2]), pcov

  except Exception as e:
    #print(e)
    raise


def _rebin(histogram, bin_size=1, visuals=False):
  # split histogram into values and bins
  values = list(histogram.values())
  bins = list(histogram)

  # Rebin data
  xdata = [np.mean(bins[nr:nr+bin_size]) for nr in range(0, len(bins), bin_size)]
  ydata = [sum(values[nr:nr+bin_size]) for nr in range(0, len(values), bin_size)]

  # generate histogram
  rebinned = dict(zip(xdata, ydata))

  return rebinned


## api functions

def get_histograms(template='*.histos'):
  filenames = sorted(glob.glob(template))
  histograms = {}
  for filename in filenames:
    file = open(filename, 'rb')
    mac5, config, pp, ss = pickle.load(file)
    file.close()
    if mac5 not in histograms:
      histograms[mac5] = []
    histograms[mac5].append((config, pp, ss))
  return histograms


def get_peaks_and_distances(
  histograms,
  sipms=range(32),
  output_socket='tcp://localhost:7000',
  input_socket='tcp://localhost:8000'
):
  """Returns the found peak positions and
  computed distances for the given list
  of SiPMs using the peak finder / fitter"""

  # connects to the peak finder and fitter
  context = zmq.Context()

  pusher = context.socket(zmq.PUSH)
  pusher.connect(output_socket)

  puller = context.socket(zmq.PULL)
  puller.connect(input_socket)

  # stores the results of the peak finder and fitter
  distances = {}
  peaks     = {}

  # compute the gain for every channel
  for sipm in sipms:
    
    sent = 0
    received = 0

    # get the spectra of a SiPM of the crt
    spectra = [ss[sipm] for config, pp, ss in histograms]

    # the data is collected in sets of 5000 events
    # since most of the peaks do not show at that
    # number of events, several histograms need to
    # be combined into one histogram.
    # let's take 15 aggregated histograms of 50k events
    # and cut out the relevant part of it
    aggregated = [[sum(_) for _ in zip(*sample(spectra, 10))][300:1000]
      for i in range(15)
    ]

    # generate a key to recognize the results
    # (improve this if several subprocesses need to communicate with the fitter,
    # at the same time in order to know which task belongs to which subprocess.
    # use a subscribtion socket using the key as filter instead of a puller)
    key = json.dumps({'sipm': sipm})

    # send the tasks to the fitter
    for spectrum in aggregated:

      # the fitter needs a histogram { binnr:value, ... }
      hist = dict(zip(range(len(spectrum)), spectrum))
      message = json.dumps({
        'key':      key,
        'spectrum': hist
      })
      pusher.send_string(message)
      sent += 1

    # get the distances between the peaks
    # from the fitter's result / response
    errors = 0
    for i in range(sent):

      answer = puller.recv_string()

      # TODO: this can be improved:
      # the error should be given
      # by an error key in the response
      if answer == 'ERR':
        errors += 1
        continue

      # the response of the fitter is a json
      # structure containing the key,
      # peak positions and computed distances
      answer = json.loads(str(answer))

      key = json.loads(answer['key'])
      _s = key['sipm']

      if 'distances' not in answer:
        errors += 1
        continue

      if _s not in distances:
        distances[_s] = []

      if _s not in peaks:
        peaks[_s] = []

      distances[_s] += answer['distances']
      peaks[_s] += answer['peaks']
      received += 1
    
    print('  SiPM %02d - Sent / Received / Errors: %d / %d / %d' % (sipm, sent, received, errors))

  # TODO: close the context or use the decorator given by pyzmq
  
  return peaks, distances


def get_gains(distances, sipms=range(32)):
  """Returns the gains computed using the
  list of computed distances between peaks"""

  # Stores the gains
  gains = {}

  # Compute the gains
  for sipm in sipms:
    errors = 0

    # A histogram with 5 peaks corresponds to 10 distances
    # (4 singles, 3 doubles, 2 tripples and 1 quadruple)
    # if 15 histograms are sent, 150 distances are computed
    # at least. Something goes totally wrong if less than 100
    # distances are collected.
    if sipm in distances:
      if len(distances[sipm]) < 100:
        errors += 1

      # Build a histogram using the distances
      ydata, edges = np.histogram(
          [d for d, _ in distances[sipm]],
          bins=50,
          range=[20, 120]
      )
      xdata = (edges[:-1] + edges[1:]) / 2

      pos = ydata.argmax()

      res = []
      try:
        (A, mu, sigma), pcov = _fit_gaussian(
          dict(zip(xdata, ydata)),
          max(ydata),
          xdata[pos],
          8 # TODO: don't like this hard coded stuff
        )

        # store the gain if its uncertainty is less than 10%
        if (np.sqrt(pcov[1][1]) / mu)**2 < .1**2:
          gains[sipm] = (A, mu, sigma), pcov

      except RuntimeError as e:
        errors += 1

    print('  SiPM %d: %d errors' % (sipm, errors))

  return gains
