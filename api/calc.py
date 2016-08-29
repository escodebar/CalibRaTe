from plotly.offline import iplot
from scipy.optimize import curve_fit

import plotly.graph_objs as go
import numpy             as np
import glob
import pickle
import sys


## TODO: write code documentation!


## internal functions

def _clean_results(params, uncerts):

  # The first result must be right
  yield(params[0], uncerts[0])

  # store it's width
  σ0 = params[0][2]

  for i in range(1, len(params)):
    _, μ, σ = params[i]
    _, σμ, σσ = uncerts[i]

    if (σ + np.sqrt(σσ)) > σ0 and σμ/μ < 0.1:
      yield(params[i], uncerts[i])
      σ0 = σ
    else:
      break


def _gauss(x, A, μ, σ):
  return A * np.exp(- (x-μ)**2 / (2.0 * σ**2))


## api functions

def aggregate(template='*.histos', events=np.inf, visuals=False, channel=0):

  filenames = sorted(glob.glob(template))

  pedestals = {}
  spectra   = {}

  total = 0

  # stores the precedent configuration
  c = ''

  for filename in filenames:

    # you know your code is bad, when a 'break' becomes an elegant solution
    if total > events:
      break

    file = open(filename, 'rb')
    mac5, config, pp, ss = pickle.load(file)
    #if c != '' and c != config:
    #  raise ValueError("Prevented aggregation with different configurations")
    file.close()
    c = config

    # discount events added
    total += np.sum(ss[0])

    if mac5 not in pedestals:
      pedestals[mac5] = np.zeros((32, 4096))
      spectra[mac5] = np.zeros((32, 4096))

    for chnr, p_h, s_h in zip(range(len(pp)), pp, ss):
      pedestals[mac5][chnr] += np.array(p_h)
      spectra[mac5][chnr] += np.array(s_h)

  if visuals:

    for mac5 in pedestals:

      # define the layout of the plot
      layout = go.Layout(
        title='Histograms FEB %d' % mac5,
        xaxis={'title':'ADC Counts / Bin Nr'},
        yaxis={'title':'Nr Events'}
      )

      # generate a range to enumerate the bins
      xdata = np.arange(0, 4096)

      # plot
      iplot(go.Figure(
        data=[
          go.Bar(x=xdata, y=pedestals[mac5][channel], name='Pedestal'),
          go.Bar(x=xdata, y=spectra[mac5][channel],   name='Spectrum'),
        ],
        layout=go.Layout(
          title='Histograms FEB %d Channel %d' % (mac5, channel),
          xaxis={'title': 'ADC Counts / Bin Nr'},
          yaxis={
            'title'     : 'Nr Events',
            'type'      : 'log',
            'autorange' : True
          }
        )
      ))

  return pedestals, spectra


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


def fit_gaussian(histogram, A=0, μ=0, σ=0, visuals=False):
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


def rebin(histogram, bin_size=1, visuals=False):

  # split histogram into values and bins
  values = list(histogram.values())
  bins = list(histogram)

  # Rebin data
  xdata = [np.mean(bins[nr:nr+bin_size]) for nr in range(0, len(bins), bin_size)]
  ydata = [sum(values[nr:nr+bin_size]) for nr in range(0, len(values), bin_size)]

  # generate histogram
  rebinned = dict(zip(xdata, ydata))

  if visuals:
    layout = go.Layout(
      title='Bining data',
      xaxis={'title':'ADC Counts / Bin Nr'},
      yaxis={'title':'Nr Events'}
    )

    iplot(go.Figure(
      data=[go.Bar(
        x=bins,
        y=values,
        name='data'
      ), go.Bar(
        x=xdata,
        y=ydata,
        name='bin size %d' % bin_size
      )],
      layout=layout
    ))

  return rebinned


def split(histogram, threshold=3, visuals=False):

  # split histogram into values and bins
  values = list(histogram.values())
  bins = list(histogram)

  # Try to determine the noise
  noise = dict(zip(bins, values))

  iterate = True
  size = len(noise)
  mean = np.mean(values)
  std = np.std(values)

  while iterate:
    noise = dict([(b, noise[b]) for b in noise if noise[b] < mean + threshold*std])

    # If no more bins were removed, stop iterating
    # else calculate the new mean and standard deviation of the new histogram
    if len(noise) == size:
      iterate = False

    else:
      size = len(noise)
      mean = np.mean(list(noise.values()))
      std  = np.std(list(noise.values()))

  # Separate the foreground from the noise
  signal = dict([(b, v) for b, v in zip(bins, values) if b not in noise])

  x_min = min(signal)
  x_max = max(signal)

  background = dict([(b, v) for b, v in zip(bins, values) if b < x_min or x_max < b])
  foreground = dict([(b, v) for b, v in zip(bins, values) if x_min <= b <= x_max])

  if visuals:
    layout = go.Layout(
      title='Selected region for polynomial fit',
      xaxis={'title':'Bin Nr'},
      yaxis={'title':'Nr Events'}
    )

    iplot(go.Figure(
      data=[go.Bar(
        x=list(foreground),
        y=list(foreground.values()),
        name='peak search region'
      ), go.Bar(
        x=list(background),
        y=list(background.values()),
        name='ignored region'
      )],
      layout=layout
    ))

  return foreground, background

