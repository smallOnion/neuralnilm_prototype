from __future__ import print_function, division
import matplotlib
matplotlib.use('Agg') # Must be before importing matplotlib.pyplot or pylab!
from neuralnilm import Net, RealApplianceSource, BLSTMLayer, DimshuffleLayer
from lasagne.nonlinearities import sigmoid, rectify, tanh
from lasagne.objectives import crossentropy, mse
from lasagne.init import Uniform, Normal
from lasagne.layers import LSTMLayer, DenseLayer, Conv1DLayer, ReshapeLayer, FeaturePoolLayer
from lasagne.updates import nesterov_momentum
from functools import partial
import os
from neuralnilm.source import standardise, discretize, fdiff, power_and_fdiff
from neuralnilm.experiment import run_experiment
from neuralnilm.net import TrainingError
import __main__
from copy import deepcopy
from math import sqrt

NAME = os.path.splitext(os.path.split(__main__.__file__)[1])[0]
PATH = "/homes/dk3810/workspace/python/neuralnilm/figures"
SAVE_PLOT_INTERVAL = 250
GRADIENT_STEPS = 100

"""
e233
based on e131c but with:
* lag=32
* pool

e234
* init final layer and conv layer

235
no lag

236
should be exactly as 131c: no pool, no lag, no init for final and conv layer

237
putting the pool back

238
seems pooling hurts us! disable pooling.
enable lag = 32

239
BLSTM
lag = 20

240
LSTM not BLSTM
various lags

241
output is prediction

252
attempt to predict fdiff 1 sample ahead.  Unfair?

253
regurgitate fdiff from 1 sample ago

254
lag of 10 time steps

255
lag of 5 time steps

257
slowly increasing lag

258
output is different appliances diff

259
start off just trying to regurgitate diff of aggregate 
then swap to disaggregation (to diff)
"""

source_dict = dict(
    filename='/data/dk3810/ukdale.h5',
    appliances=[
        ['fridge freezer', 'fridge', 'freezer'], 
        'hair straighteners', 
        'television',
        'dish washer',
        ['washer dryer', 'washing machine']
    ],
    max_appliance_powers=[2500]*5,
    on_power_thresholds=[5] * 5,
    max_input_power=5900,
    min_on_durations=[60, 60, 60, 1800, 1800],
    min_off_durations=[12, 12, 12, 1800, 600],
    window=("2013-06-01", "2014-07-01"),
    seq_length=1500,
    output_one_appliance=False,
    boolean_targets=False,
    train_buildings=[1],
    validation_buildings=[1], 
    # skip_probability=0.0,
    n_seq_per_batch=50,
    # subsample_target=5,
    include_diff=True,
    include_power=False,
    clip_appliance_power=True,
    target_is_prediction=True,
    lag=1,
    target_is_diff=True
)

def change_learning_rate(net, epoch, learning_rate):
    net.updates = partial(nesterov_momentum, learning_rate=learning_rate)
    net.compile()

def change_lag(net, epoch, lag):
    net.source.lag = lag
    net.compile()

from theano.ifelse import ifelse
import theano.tensor as T

THRESHOLD = 0
def scaled_cost(x, t):
    sq_error = (x - t) ** 2
    def mask_and_mean_sq_error(mask):
        masked_sq_error = sq_error[mask.nonzero()]
        mean = masked_sq_error.mean()
        mean = ifelse(T.isnan(mean), 0.0, mean)
        return mean
    above_thresh_mean = mask_and_mean_sq_error(t > THRESHOLD)
    below_thresh_mean = mask_and_mean_sq_error(t <= THRESHOLD)
    return (above_thresh_mean + below_thresh_mean) / 2.0

def new_source(net, epoch):
    source_dict_copy = deepcopy(source_dict)
    source_dict_copy['target_is_prediction'] = False
    net.source = RealApplianceSource(**source_dict_copy)
    net.generate_validation_data_and_set_shapes()
    net.loss_function = scaled_cost

net_dict = dict(        
    save_plot_interval=SAVE_PLOT_INTERVAL,
    loss_function=mse,
    updates=partial(nesterov_momentum, learning_rate=0.1),
    layers_config=[
        {
            'type': LSTMLayer,
            'num_units': 50,
            'gradient_steps': GRADIENT_STEPS,
            'peepholes': False,
            'W_in_to_cell': Normal(std=1.)
        }
    ],
    layer_changes={
         1001: {
             'remove_from': -3,
             'callback': new_source,
             'new_layers': [
                {
                    'type': DenseLayer,
                    'num_units': 5,
                    'nonlinearity': None,
                    'W': Normal(std=(1/sqrt(50)))
                }                 
             ]
         }
    }
)


def exp_x(name):
    global source
    # source = RealApplianceSource(**source_dict)
    net_dict_copy = deepcopy(net_dict)
    net_dict_copy.update(dict(
        experiment_name=name, 
        source=source
    ))
    net_dict_copy['layers_config'].append(
        {
            'type': DenseLayer,
            'num_units': source.n_outputs,
            'nonlinearity': None,
            'W': Normal(std=(1/sqrt(50)))
        }
    )
    net = Net(**net_dict_copy)
    return net


def main():
    experiment = 'a'
    full_exp_name = NAME + experiment
    path = os.path.join(PATH, full_exp_name)
    print("***********************************")
    print("Preparing", full_exp_name, "...")
    try:
        net = exp_x(full_exp_name)
        run_experiment(net, path, epochs=None)
    except KeyboardInterrupt:
        return
    except TrainingError as exception:
        print("EXCEPTION:", exception)
    except Exception as exception:
        print("EXCEPTION:", exception)


if __name__ == "__main__":
    main()
