from __future__ import print_function, division
import matplotlib
import logging
from sys import stdout
matplotlib.use('Agg') # Must be before importing matplotlib.pyplot or pylab!
from neuralnilm import (Net, RealApplianceSource)
from neuralnilm.source import (standardise, discretize, fdiff, power_and_fdiff,
                               RandomSegments, RandomSegmentsInMemory,
                               SameLocation)
from neuralnilm.experiment import run_experiment, init_experiment
from neuralnilm.net import TrainingError
from neuralnilm.layers import (MixtureDensityLayer, DeConv1DLayer,
                               SharedWeightsDenseLayer)
from neuralnilm.objectives import (scaled_cost, mdn_nll,
                                   scaled_cost_ignore_inactive, ignore_inactive,
                                   scaled_cost3)
from neuralnilm.plot import MDNPlotter, CentralOutputPlotter, Plotter, RectangularOutputPlotter, StartEndMeanPlotter
from neuralnilm.updates import clipped_nesterov_momentum
from neuralnilm.disaggregate import disaggregate
from neuralnilm.rectangulariser import rectangularise

from lasagne.nonlinearities import sigmoid, rectify, tanh, identity, softmax
from lasagne.objectives import squared_error, binary_crossentropy
from lasagne.init import Uniform, Normal
from lasagne.layers import (DenseLayer, Conv1DLayer,
                            ReshapeLayer, FeaturePoolLayer,
                            DimshuffleLayer, DropoutLayer, ConcatLayer, PadLayer)
from lasagne.updates import nesterov_momentum, momentum
from functools import partial
import os
import __main__
from copy import deepcopy
from math import sqrt
import numpy as np
import theano.tensor as T
import gc

"""
447: first attempt at disaggregation
"""

NAME = os.path.splitext(os.path.split(__main__.__file__)[1])[0]
#PATH = "/homes/dk3810/workspace/python/neuralnilm/figures"
PATH = "/data/dk3810/figures"
SAVE_PLOT_INTERVAL = 25000

N_SEQ_PER_BATCH = 64

source_dict = dict(
    filename='/data/dk3810/ukdale.h5',
    # date finished installing meters in house 1 = 2013-04-12
    window=("2013-04-12", "2014-12-10"),
    output_one_appliance=True,
    train_buildings=[1],
    validation_buildings=[1],
    n_seq_per_batch=N_SEQ_PER_BATCH,
    standardise_input=True,
    independently_center_inputs=False,
    skip_probability=0.75,
#    skip_probability_for_first_appliance=0.5,
    target_is_start_and_end_and_mean=True,
    one_target_per_seq=False
)


net_dict = dict(
    save_plot_interval=SAVE_PLOT_INTERVAL,
    loss_function=lambda x, t: squared_error(x, t).mean(),
    updates_func=nesterov_momentum,
    learning_rate=1e-3,
    learning_rate_changes_by_iteration={
        250000: 1e-4,
        275000: 1e-5
    },
    do_save_activations=True,
    auto_reshape=False,
    layers_config=[
        {
            'type': DimshuffleLayer,
            'pattern': (0, 2, 1)  # (batch, features, time)
        },
        {
            'type': PadLayer,
            'width': 4
        },
        {
            'type': Conv1DLayer,  # convolve over the time axis
            'num_filters': 16,
            'filter_size': 4,
            'stride': 1,
            'nonlinearity': None,
            'border_mode': 'valid'
        },
        {
            'type': Conv1DLayer,  # convolve over the time axis
            'num_filters': 16,
            'filter_size': 4,
            'stride': 1,
            'nonlinearity': None,
            'border_mode': 'valid'
        },
        {
            'type': DimshuffleLayer,
            'pattern': (0, 2, 1),  # back to (batch, time, features)
            'label': 'dimshuffle3'
        },
        {
            'type': DenseLayer,
            'num_units': 512 * 8,
            'nonlinearity': rectify,
            'label': 'dense0'
        },
        {
            'type': DenseLayer,
            'num_units': 512 * 6,
            'nonlinearity': rectify,
            'label': 'dense1'
        },
        {
            'type': DenseLayer,
            'num_units': 512 * 4,
            'nonlinearity': rectify,
            'label': 'dense2'
        },
        {
            'type': DenseLayer,
            'num_units': 512,
            'nonlinearity': rectify
        },
        {
            'type': DenseLayer,
            'num_units': 3,
            'nonlinearity': None
        }
    ]
)


def exp_a(name):
    global source
    MAX_TARGET_POWER = 2400
    source_dict_copy = deepcopy(source_dict)
    source_dict_copy.update(dict(
        logger=logging.getLogger(name),
        appliances=[
            ['washer dryer', 'washing machine'],
            'kettle',
            'HTPC',
            'dish washer',
            ['fridge freezer', 'fridge', 'freezer']
        ],
        max_appliance_powers=[MAX_TARGET_POWER, 2600, 200, 2500, 300],
        on_power_thresholds=[5] * 5,
        min_on_durations=[1800, 30, 60, 1800, 60],
        min_off_durations=[600, 1, 12, 1800, 12],
        seq_length=2048
    ))
    source = RealApplianceSource(**source_dict_copy)
    net_dict_copy = deepcopy(net_dict)
    net_dict_copy.update(dict(
        experiment_name=name,
        source=source,
        plotter=StartEndMeanPlotter(
            n_seq_to_plot=32, max_target_power=MAX_TARGET_POWER)
    ))
    net = Net(**net_dict_copy)
    return net


def exp_b(name):
    global source
    MAX_TARGET_POWER = 2600
    source_dict_copy = deepcopy(source_dict)
    source_dict_copy.update(dict(
        logger=logging.getLogger(name),
        appliances=[
            'kettle',
            'HTPC',
            'dish washer',
            ['fridge freezer', 'fridge', 'freezer'],
            ['washer dryer', 'washing machine']
        ],
        max_appliance_powers=[MAX_TARGET_POWER, 200, 2500, 300, 2400],
        on_power_thresholds=[5] * 5,
        min_on_durations=[30, 60, 1800, 60, 1800],
        min_off_durations=[1, 12, 1800, 12, 600],
        seq_length=128
    ))
    source = RealApplianceSource(**source_dict_copy)
    net_dict_copy = deepcopy(net_dict)
    net_dict_copy.update(dict(
        experiment_name=name,
        source=source,
        plotter=StartEndMeanPlotter(
            n_seq_to_plot=32, max_target_power=MAX_TARGET_POWER)
    ))
    net = Net(**net_dict_copy)
    net.load_params(175000)
    return net


def exp_c(name):
    global source
    MAX_TARGET_POWER = 200
    source_dict_copy = deepcopy(source_dict)
    source_dict_copy.update(dict(
        logger=logging.getLogger(name),
        appliances=[
            'HTPC',
            'dish washer',
            ['fridge freezer', 'fridge', 'freezer'],
            ['washer dryer', 'washing machine'],
            'kettle'
        ],
        max_appliance_powers=[MAX_TARGET_POWER, 2500, 300, 2400, 2600],
        on_power_thresholds=[5] * 5,
        min_on_durations=[60, 1800, 60, 1800, 30],
        min_off_durations=[12, 1800, 12, 600, 1],
        seq_length=2048
    ))
    source = RealApplianceSource(**source_dict_copy)
    net_dict_copy = deepcopy(net_dict)
    net_dict_copy.update(dict(
        experiment_name=name,
        source=source,
        plotter=StartEndMeanPlotter(
            n_seq_to_plot=32, max_target_power=MAX_TARGET_POWER),
        learning_rate_changes_by_iteration={
            150000: 1e-4,
            275000: 1e-5
        }
    ))
    net = Net(**net_dict_copy)
    net.load_params(107746)
    return net


def exp_d(name):
    global source
    MAX_TARGET_POWER = 2500
    source_dict_copy = deepcopy(source_dict)
    source_dict_copy.update(dict(
        logger=logging.getLogger(name),
        appliances=[
            'dish washer',
            ['fridge freezer', 'fridge', 'freezer'],
            ['washer dryer', 'washing machine'],
            'kettle',
            'HTPC'
        ],
        max_appliance_powers=[MAX_TARGET_POWER, 300, 2400, 2600, 200],
        on_power_thresholds=[5] * 5,
        min_on_durations=[1800, 60, 1800, 30, 60],
        min_off_durations=[1800, 12, 600, 1, 12],
        seq_length=2048
    ))
    source = RealApplianceSource(**source_dict_copy)
    net_dict_copy = deepcopy(net_dict)
    net_dict_copy.update(dict(
        experiment_name=name,
        source=source,
        plotter=StartEndMeanPlotter(
            n_seq_to_plot=32, max_target_power=MAX_TARGET_POWER)
    ))
    net = Net(**net_dict_copy)
    return net


def main():
    EXPERIMENTS = list('cd')
    for experiment in EXPERIMENTS:
        full_exp_name = NAME + experiment
        func_call = init_experiment(PATH, experiment, full_exp_name)
        logger = logging.getLogger(full_exp_name)
        try:
            net = eval(func_call)
            run_experiment(net, epochs=300000)
        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt")
            break
        except Exception as exception:
            logger.exception("Exception")
            # raise
        finally:
            logging.shutdown()


if __name__ == "__main__":
    main()


"""
Emacs variables
Local Variables:
compile-command: "cp /home/jack/workspace/python/neuralnilm/scripts/e545.py /mnt/sshfs/imperial/workspace/python/neuralnilm/scripts/"
End:
"""