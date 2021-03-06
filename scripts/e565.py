from __future__ import print_function, division
import matplotlib
import logging
from sys import stdout
matplotlib.use('Agg') # Must be before importing matplotlib.pyplot or pylab!
from neuralnilm import (Net, RealApplianceSource)
from neuralnilm.source import (standardise, discretize, fdiff, power_and_fdiff,
                               RandomSegments, RandomSegmentsInMemory,
                               SameLocation, MultiSource)
from neuralnilm.experiment import run_experiment, init_experiment
from neuralnilm.net import TrainingError
from neuralnilm.layers import (MixtureDensityLayer, DeConv1DLayer,
                               SharedWeightsDenseLayer, BLSTMLayer)
from neuralnilm.objectives import (scaled_cost, mdn_nll,
                                   scaled_cost_ignore_inactive, ignore_inactive,
                                   scaled_cost3)
from neuralnilm.plot import MDNPlotter, CentralOutputPlotter, Plotter, RectangularOutputPlotter, StartEndMeanPlotter
from neuralnilm.updates import clipped_nesterov_momentum
from neuralnilm.disaggregate import disaggregate
from neuralnilm.rectangulariser import rectangularise

from lasagne.nonlinearities import (sigmoid, rectify, tanh, identity, softmax)
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
Max powers:
microwave = 3000W
"""


NAME = os.path.splitext(os.path.split(__main__.__file__)[1])[0]
#PATH = "/homes/dk3810/workspace/python/neuralnilm/figures"
PATH = "/data/dk3810/figures"
# PATH = "/home/jack/experiments/neuralnilm/figures"
SAVE_PLOT_INTERVAL = 1000

UKDALE_FILENAME = '/data/dk3810/ukdale.h5'

MAX_TARGET_POWER = 3000
ON_POWER_THRESHOLD = 200
MIN_ON_DURATION = 18
MIN_OFF_DURATION = 30
TARGET_APPLIANCE = 'microwave'

TRAIN_BUILDINGS = [1, 2]
VALIDATION_BUILDINGS = [5]
SKIP_PROBABILITY_FOR_TARGET = 0.5
INDEPENDENTLY_CENTER_INPUTS = True
SUBSAMPLE_TARGET = 1
INPUT_PADDING = 0

WINDOW_PER_BUILDING = {
    1: ("2013-03-17", "2014-12-01"),
    2: ("2013-05-22", "2013-10-01"),
    3: ("2013-02-27", "2013-04-01"),
    4: ("2013-03-09", "2013-09-20"),
    5: ("2014-06-29", "2014-08-27")
}

INPUT_STATS = {
    'mean': np.array([297.87216187], dtype=np.float32),
    'std': np.array([374.43884277], dtype=np.float32)
}


def only_train_on_real_data(net, iteration):
    net.logger.info(
        "Iteration {}: Now only training on real data.".format(iteration))
    net.source.sources[0]['train_probability'] = 0.0
    net.source.sources[1]['train_probability'] = 1.0


net_dict = dict(
    save_plot_interval=SAVE_PLOT_INTERVAL,
    loss_function=lambda x, t: squared_error(x, t).mean(),
    updates_func=nesterov_momentum,
    learning_rate=1e-2,
    learning_rate_changes_by_iteration={
        1000: 1e-3,
        10000: 1e-4
    },
    epoch_callbacks={
        350000: only_train_on_real_data
    },
    do_save_activations=True,
    auto_reshape=True,
    layers_config=[
        {
            'type': DenseLayer,
            'num_units': 64,
            'nonlinearity': tanh
        },
        {
            'type': BLSTMLayer,
            'num_units': 128,
            'merge_mode': 'concatenate'
        },
        {
            'type': BLSTMLayer,
            'num_units': 256,
            'merge_mode': 'concatenate'
        },
        {
            'type': DenseLayer,
            'num_units': 128,
            'nonlinearity': tanh
        },
        {
            'type': DenseLayer,
            'num_units': 1,
            'nonlinearity': None
        }
    ]
)


def exp_a(name):
    # longer seq length
    logger = logging.getLogger(name)
    global multi_source

    SEQ_LENGTH = 2048
    N_SEQ_PER_BATCH = 8

    # real_appliance_source1 = RealApplianceSource(
    #     logger=logger,
    #     filename=UKDALE_FILENAME,
    #     appliances=[
    #         TARGET_APPLIANCE,
    #         ['fridge freezer', 'fridge', 'freezer'],
    #         'dish washer',
    #         'kettle',
    #         ['washer dryer', 'washing machine']
    #     ],
    #     max_appliance_powers=[MAX_TARGET_POWER, 300, 2500, 2600, 2400],
    #     on_power_thresholds=[ON_POWER_THRESHOLD] + [10] * 4,
    #     min_on_durations=[MIN_ON_DURATION, 60, 1800, 12, 1800],
    #     min_off_durations=[MIN_OFF_DURATION, 12, 1800, 12, 600],
    #     divide_input_by_max_input_power=False,
    #     window_per_building=WINDOW_PER_BUILDING,
    #     seq_length=SEQ_LENGTH,
    #     output_one_appliance=True,
    #     train_buildings=TRAIN_BUILDINGS,
    #     validation_buildings=VALIDATION_BUILDINGS,
    #     n_seq_per_batch=N_SEQ_PER_BATCH,
    #     skip_probability=0.75,
    #     skip_probability_for_first_appliance=SKIP_PROBABILITY_FOR_TARGET,
    #     standardise_input=True,
    #     input_stats=INPUT_STATS,
    #     independently_center_inputs=INDEPENDENTLY_CENTER_INPUTS,
    #     subsample_target=SUBSAMPLE_TARGET,
    #     input_padding=INPUT_PADDING
    # )

    # same_location_source1 = SameLocation(
    #     logger=logger,
    #     filename=UKDALE_FILENAME,
    #     target_appliance=TARGET_APPLIANCE,
    #     window_per_building=WINDOW_PER_BUILDING,
    #     seq_length=SEQ_LENGTH,
    #     train_buildings=TRAIN_BUILDINGS,
    #     validation_buildings=VALIDATION_BUILDINGS,
    #     n_seq_per_batch=N_SEQ_PER_BATCH,
    #     skip_probability=SKIP_PROBABILITY_FOR_TARGET,
    #     standardise_input=True,
    #     offset_probability=1,
    #     divide_target_by=MAX_TARGET_POWER,
    #     input_stats=INPUT_STATS,
    #     independently_center_inputs=INDEPENDENTLY_CENTER_INPUTS,
    #     on_power_threshold=ON_POWER_THRESHOLD,
    #     min_on_duration=MIN_ON_DURATION,
    #     min_off_duration=MIN_OFF_DURATION,
    #     include_all=True,
    #     allow_incomplete=True,
    #     subsample_target=SUBSAMPLE_TARGET,
    #     input_padding=INPUT_PADDING
    # )

    # multi_source = MultiSource(
    #     sources=[
    #         {
    #             'source': real_appliance_source1,
    #             'train_probability': 0.5,
    #             'validation_probability': 0
    #         },
    #         {
    #             'source': same_location_source1,
    #             'train_probability': 0.5,
    #             'validation_probability': 1
    #         }
    #     ],
    #     standardisation_source=same_location_source1
    # )

    net_dict_copy = deepcopy(net_dict)
    net_dict_copy.update(dict(
        experiment_name=name,
        source=multi_source,
        plotter=Plotter(
            n_seq_to_plot=32,
            n_training_examples_to_plot=16
        ),
        learning_rate=1e-7,
        learning_rate_changes_by_iteration={
            1000: 1e-8,
            10000: 1e-9
        },
        layers_config=[
            {
                'type': DenseLayer,
                'num_units': 64,
                'nonlinearity': tanh
            },
            {
                'type': BLSTMLayer,
                'num_units': 128,
                'merge_mode': 'concatenate',
                'grad_clipping': 1.0
#                'gradient_steps': 200
            },
            {
                'type': BLSTMLayer,
                'num_units': 256,
                'merge_mode': 'concatenate',
                'grad_clipping': 1.0
#                'gradient_steps': 200                
            },
            {
                'type': DenseLayer,
                'num_units': 128,
                'nonlinearity': tanh
            },
            {
                'type': DenseLayer,
                'num_units': 1,
                'nonlinearity': None
            }
        ]
    ))
    net = Net(**net_dict_copy)
    return net


def exp_b(name):
    # conv at beginning
    logger = logging.getLogger(name)
    global multi_source

    SEQ_LENGTH = 256
    N_SEQ_PER_BATCH = 64

    real_appliance_source1 = RealApplianceSource(
        logger=logger,
        filename=UKDALE_FILENAME,
        appliances=[
            TARGET_APPLIANCE,
            ['fridge freezer', 'fridge', 'freezer'],
            'dish washer',
            'kettle',
            ['washer dryer', 'washing machine']
        ],
        max_appliance_powers=[MAX_TARGET_POWER, 300, 2500, 2600, 2400],
        on_power_thresholds=[ON_POWER_THRESHOLD] + [10] * 4,
        min_on_durations=[MIN_ON_DURATION, 60, 1800, 12, 1800],
        min_off_durations=[MIN_OFF_DURATION, 12, 1800, 12, 600],
        divide_input_by_max_input_power=False,
        window_per_building=WINDOW_PER_BUILDING,
        seq_length=SEQ_LENGTH,
        output_one_appliance=True,
        train_buildings=TRAIN_BUILDINGS,
        validation_buildings=VALIDATION_BUILDINGS,
        n_seq_per_batch=N_SEQ_PER_BATCH,
        skip_probability=0.75,
        skip_probability_for_first_appliance=SKIP_PROBABILITY_FOR_TARGET,
        standardise_input=True,
        input_stats=INPUT_STATS,
        independently_center_inputs=INDEPENDENTLY_CENTER_INPUTS,
        subsample_target=SUBSAMPLE_TARGET,
        input_padding=INPUT_PADDING
    )

    same_location_source1 = SameLocation(
        logger=logger,
        filename=UKDALE_FILENAME,
        target_appliance=TARGET_APPLIANCE,
        window_per_building=WINDOW_PER_BUILDING,
        seq_length=SEQ_LENGTH,
        train_buildings=TRAIN_BUILDINGS,
        validation_buildings=VALIDATION_BUILDINGS,
        n_seq_per_batch=N_SEQ_PER_BATCH,
        skip_probability=SKIP_PROBABILITY_FOR_TARGET,
        standardise_input=True,
        offset_probability=1,
        divide_target_by=MAX_TARGET_POWER,
        input_stats=INPUT_STATS,
        independently_center_inputs=INDEPENDENTLY_CENTER_INPUTS,
        on_power_threshold=ON_POWER_THRESHOLD,
        min_on_duration=MIN_ON_DURATION,
        min_off_duration=MIN_OFF_DURATION,
        include_all=True,
        allow_incomplete=True,
        subsample_target=SUBSAMPLE_TARGET,
        input_padding=INPUT_PADDING
    )

    multi_source = MultiSource(
        sources=[
            {
                'source': real_appliance_source1,
                'train_probability': 0.5,
                'validation_probability': 0
            },
            {
                'source': same_location_source1,
                'train_probability': 0.5,
                'validation_probability': 1
            }
        ],
        standardisation_source=same_location_source1
    )

    net_dict_copy = deepcopy(net_dict)
    net_dict_copy.update(dict(
        auto_reshape=True,
        experiment_name=name,
        source=multi_source,
        plotter=Plotter(
            n_seq_to_plot=32,
            n_training_examples_to_plot=16
        ),
        layers_config=[
            {
                'type': DimshuffleLayer,
                'pattern': (0, 2, 1)  # (batch, features, time)
            },
            {
                'type': Conv1DLayer,  # convolve over the time axis
                'num_filters': 16,
                'filter_size': 4,
                'stride': 1,
                'nonlinearity': None,
                'border_mode': 'same'
            },
            {
                'type': DimshuffleLayer,
                'pattern': (0, 2, 1),  # back to (batch, time, features)
                'label': 'dimshuffle3'
            },
            {
                'type': BLSTMLayer,
                'num_units': 128,
                'merge_mode': 'concatenate'
            },
            {
                'type': BLSTMLayer,
                'num_units': 256,
                'merge_mode': 'concatenate'
            },
            {
                'type': DenseLayer,
                'num_units': 128,
                'nonlinearity': tanh
            },
            {
                'type': DenseLayer,
                'num_units': 1,
                'nonlinearity': None
            }
        ]

    ))
    net = Net(**net_dict_copy)
    net.load_params(1500)
    return net


def exp_c(name):
    # elemwise sum
    logger = logging.getLogger(name)
    global multi_source

    SEQ_LENGTH = 256
    N_SEQ_PER_BATCH = 64

    real_appliance_source1 = RealApplianceSource(
        logger=logger,
        filename=UKDALE_FILENAME,
        appliances=[
            TARGET_APPLIANCE,
            ['fridge freezer', 'fridge', 'freezer'],
            'dish washer',
            'kettle',
            ['washer dryer', 'washing machine']
        ],
        max_appliance_powers=[MAX_TARGET_POWER, 300, 2500, 2600, 2400],
        on_power_thresholds=[ON_POWER_THRESHOLD] + [10] * 4,
        min_on_durations=[MIN_ON_DURATION, 60, 1800, 12, 1800],
        min_off_durations=[MIN_OFF_DURATION, 12, 1800, 12, 600],
        divide_input_by_max_input_power=False,
        window_per_building=WINDOW_PER_BUILDING,
        seq_length=SEQ_LENGTH,
        output_one_appliance=True,
        train_buildings=TRAIN_BUILDINGS,
        validation_buildings=VALIDATION_BUILDINGS,
        n_seq_per_batch=N_SEQ_PER_BATCH,
        skip_probability=0.75,
        skip_probability_for_first_appliance=SKIP_PROBABILITY_FOR_TARGET,
        standardise_input=True,
        input_stats=INPUT_STATS,
        independently_center_inputs=INDEPENDENTLY_CENTER_INPUTS,
        subsample_target=SUBSAMPLE_TARGET,
        input_padding=INPUT_PADDING
    )

    same_location_source1 = SameLocation(
        logger=logger,
        filename=UKDALE_FILENAME,
        target_appliance=TARGET_APPLIANCE,
        window_per_building=WINDOW_PER_BUILDING,
        seq_length=SEQ_LENGTH,
        train_buildings=TRAIN_BUILDINGS,
        validation_buildings=VALIDATION_BUILDINGS,
        n_seq_per_batch=N_SEQ_PER_BATCH,
        skip_probability=SKIP_PROBABILITY_FOR_TARGET,
        standardise_input=True,
        offset_probability=1,
        divide_target_by=MAX_TARGET_POWER,
        input_stats=INPUT_STATS,
        independently_center_inputs=INDEPENDENTLY_CENTER_INPUTS,
        on_power_threshold=ON_POWER_THRESHOLD,
        min_on_duration=MIN_ON_DURATION,
        min_off_duration=MIN_OFF_DURATION,
        include_all=True,
        allow_incomplete=True,
        subsample_target=SUBSAMPLE_TARGET,
        input_padding=INPUT_PADDING
    )

    multi_source = MultiSource(
        sources=[
            {
                'source': real_appliance_source1,
                'train_probability': 0.5,
                'validation_probability': 0
            },
            {
                'source': same_location_source1,
                'train_probability': 0.5,
                'validation_probability': 1
            }
        ],
        standardisation_source=same_location_source1
    )

    net_dict_copy = deepcopy(net_dict)
    net_dict_copy.update(dict(
        auto_reshape=True,
        experiment_name=name,
        source=multi_source,
        plotter=Plotter(
            n_seq_to_plot=32,
            n_training_examples_to_plot=16
        ),
        layers_config=[
            {
                'type': DenseLayer,
                'num_units': 64,
                'nonlinearity': tanh
            },
            {
                'type': BLSTMLayer,
                'num_units': 128,
                'merge_mode': 'sum'
            },
            {
                'type': BLSTMLayer,
                'num_units': 256,
                'merge_mode': 'sum'
            },
            {
                'type': DenseLayer,
                'num_units': 128,
                'nonlinearity': tanh
            },
            {
                'type': DenseLayer,
                'num_units': 1,
                'nonlinearity': None
            }
        ]

    ))
    net = Net(**net_dict_copy)
    return net


def exp_d(name):
    # sigmoid
    logger = logging.getLogger(name)
    global multi_source

    SEQ_LENGTH = 256
    N_SEQ_PER_BATCH = 64

    real_appliance_source1 = RealApplianceSource(
        logger=logger,
        filename=UKDALE_FILENAME,
        appliances=[
            TARGET_APPLIANCE,
            ['fridge freezer', 'fridge', 'freezer'],
            'dish washer',
            'kettle',
            ['washer dryer', 'washing machine']
        ],
        max_appliance_powers=[MAX_TARGET_POWER, 300, 2500, 2600, 2400],
        on_power_thresholds=[ON_POWER_THRESHOLD] + [10] * 4,
        min_on_durations=[MIN_ON_DURATION, 60, 1800, 12, 1800],
        min_off_durations=[MIN_OFF_DURATION, 12, 1800, 12, 600],
        divide_input_by_max_input_power=False,
        window_per_building=WINDOW_PER_BUILDING,
        seq_length=SEQ_LENGTH,
        output_one_appliance=True,
        train_buildings=TRAIN_BUILDINGS,
        validation_buildings=VALIDATION_BUILDINGS,
        n_seq_per_batch=N_SEQ_PER_BATCH,
        skip_probability=0.75,
        skip_probability_for_first_appliance=SKIP_PROBABILITY_FOR_TARGET,
        standardise_input=True,
        input_stats=INPUT_STATS,
        independently_center_inputs=INDEPENDENTLY_CENTER_INPUTS,
        subsample_target=SUBSAMPLE_TARGET,
        input_padding=INPUT_PADDING
    )

    same_location_source1 = SameLocation(
        logger=logger,
        filename=UKDALE_FILENAME,
        target_appliance=TARGET_APPLIANCE,
        window_per_building=WINDOW_PER_BUILDING,
        seq_length=SEQ_LENGTH,
        train_buildings=TRAIN_BUILDINGS,
        validation_buildings=VALIDATION_BUILDINGS,
        n_seq_per_batch=N_SEQ_PER_BATCH,
        skip_probability=SKIP_PROBABILITY_FOR_TARGET,
        standardise_input=True,
        offset_probability=1,
        divide_target_by=MAX_TARGET_POWER,
        input_stats=INPUT_STATS,
        independently_center_inputs=INDEPENDENTLY_CENTER_INPUTS,
        on_power_threshold=ON_POWER_THRESHOLD,
        min_on_duration=MIN_ON_DURATION,
        min_off_duration=MIN_OFF_DURATION,
        include_all=True,
        allow_incomplete=True,
        subsample_target=SUBSAMPLE_TARGET,
        input_padding=INPUT_PADDING
    )

    multi_source = MultiSource(
        sources=[
            {
                'source': real_appliance_source1,
                'train_probability': 0.5,
                'validation_probability': 0
            },
            {
                'source': same_location_source1,
                'train_probability': 0.5,
                'validation_probability': 1
            }
        ],
        standardisation_source=same_location_source1
    )

    net_dict_copy = deepcopy(net_dict)
    net_dict_copy.update(dict(
        auto_reshape=True,
        experiment_name=name,
        source=multi_source,
        plotter=Plotter(
            n_seq_to_plot=32,
            n_training_examples_to_plot=16
        ),
        layers_config=[
            {
                'type': DenseLayer,
                'num_units': 64,
                'nonlinearity': sigmoid
            },
            {
                'type': BLSTMLayer,
                'num_units': 128,
                'nonlinearity_out': sigmoid,
                'merge_mode': 'concatenate'
            },
            {
                'type': BLSTMLayer,
                'num_units': 256,
                'nonlinearity_out': sigmoid,
                'merge_mode': 'concatenate'
            },
            {
                'type': DenseLayer,
                'num_units': 128,
                'nonlinearity': sigmoid
            },
            {
                'type': DenseLayer,
                'num_units': 1,
                'nonlinearity': None
            }
        ]

    ))
    net = Net(**net_dict_copy)
    return net


def exp_e(name):
    # conv at beginning
    # b but smaller net
    logger = logging.getLogger(name)
    global multi_source

    SEQ_LENGTH = 256
    N_SEQ_PER_BATCH = 64

    real_appliance_source1 = RealApplianceSource(
        logger=logger,
        filename=UKDALE_FILENAME,
        appliances=[
            TARGET_APPLIANCE,
            ['fridge freezer', 'fridge', 'freezer'],
            'dish washer',
            'kettle',
            ['washer dryer', 'washing machine']
        ],
        max_appliance_powers=[MAX_TARGET_POWER, 300, 2500, 2600, 2400],
        on_power_thresholds=[ON_POWER_THRESHOLD] + [10] * 4,
        min_on_durations=[MIN_ON_DURATION, 60, 1800, 12, 1800],
        min_off_durations=[MIN_OFF_DURATION, 12, 1800, 12, 600],
        divide_input_by_max_input_power=False,
        window_per_building=WINDOW_PER_BUILDING,
        seq_length=SEQ_LENGTH,
        output_one_appliance=True,
        train_buildings=TRAIN_BUILDINGS,
        validation_buildings=VALIDATION_BUILDINGS,
        n_seq_per_batch=N_SEQ_PER_BATCH,
        skip_probability=0.75,
        skip_probability_for_first_appliance=SKIP_PROBABILITY_FOR_TARGET,
        standardise_input=True,
        input_stats=INPUT_STATS,
        independently_center_inputs=INDEPENDENTLY_CENTER_INPUTS,
        subsample_target=SUBSAMPLE_TARGET,
        input_padding=INPUT_PADDING
    )

    same_location_source1 = SameLocation(
        logger=logger,
        filename=UKDALE_FILENAME,
        target_appliance=TARGET_APPLIANCE,
        window_per_building=WINDOW_PER_BUILDING,
        seq_length=SEQ_LENGTH,
        train_buildings=TRAIN_BUILDINGS,
        validation_buildings=VALIDATION_BUILDINGS,
        n_seq_per_batch=N_SEQ_PER_BATCH,
        skip_probability=SKIP_PROBABILITY_FOR_TARGET,
        standardise_input=True,
        offset_probability=1,
        divide_target_by=MAX_TARGET_POWER,
        input_stats=INPUT_STATS,
        independently_center_inputs=INDEPENDENTLY_CENTER_INPUTS,
        on_power_threshold=ON_POWER_THRESHOLD,
        min_on_duration=MIN_ON_DURATION,
        min_off_duration=MIN_OFF_DURATION,
        include_all=True,
        allow_incomplete=True,
        subsample_target=SUBSAMPLE_TARGET,
        input_padding=INPUT_PADDING
    )

    multi_source = MultiSource(
        sources=[
            {
                'source': real_appliance_source1,
                'train_probability': 0.5,
                'validation_probability': 0
            },
            {
                'source': same_location_source1,
                'train_probability': 0.5,
                'validation_probability': 1
            }
        ],
        standardisation_source=same_location_source1
    )

    net_dict_copy = deepcopy(net_dict)
    net_dict_copy.update(dict(
        auto_reshape=True,
        experiment_name=name,
        source=multi_source,
        plotter=Plotter(
            n_seq_to_plot=32,
            n_training_examples_to_plot=16
        ),
        layers_config=[
            {
                'type': DimshuffleLayer,
                'pattern': (0, 2, 1)  # (batch, features, time)
            },
            {
                'type': Conv1DLayer,  # convolve over the time axis
                'num_filters': 16,
                'filter_size': 4,
                'stride': 1,
                'nonlinearity': None,
                'border_mode': 'same'
            },
            {
                'type': DimshuffleLayer,
                'pattern': (0, 2, 1),  # back to (batch, time, features)
                'label': 'dimshuffle3'
            },
            {
                'type': BLSTMLayer,
                'num_units': 128,
                'merge_mode': 'concatenate'
            },
            {
                'type': BLSTMLayer,
                'num_units': 128,
                'merge_mode': 'concatenate'
            },
            {
                'type': DenseLayer,
                'num_units': 64,
                'nonlinearity': tanh
            },
            {
                'type': DenseLayer,
                'num_units': 1,
                'nonlinearity': None
            }
        ]

    ))
    net = Net(**net_dict_copy)
    return net


def exp_f(name):
    # conv at beginning
    # e but small conv filter size
    logger = logging.getLogger(name)
    global multi_source

    SEQ_LENGTH = 256
    N_SEQ_PER_BATCH = 64

    real_appliance_source1 = RealApplianceSource(
        logger=logger,
        filename=UKDALE_FILENAME,
        appliances=[
            TARGET_APPLIANCE,
            ['fridge freezer', 'fridge', 'freezer'],
            'dish washer',
            'kettle',
            ['washer dryer', 'washing machine']
        ],
        max_appliance_powers=[MAX_TARGET_POWER, 300, 2500, 2600, 2400],
        on_power_thresholds=[ON_POWER_THRESHOLD] + [10] * 4,
        min_on_durations=[MIN_ON_DURATION, 60, 1800, 12, 1800],
        min_off_durations=[MIN_OFF_DURATION, 12, 1800, 12, 600],
        divide_input_by_max_input_power=False,
        window_per_building=WINDOW_PER_BUILDING,
        seq_length=SEQ_LENGTH,
        output_one_appliance=True,
        train_buildings=TRAIN_BUILDINGS,
        validation_buildings=VALIDATION_BUILDINGS,
        n_seq_per_batch=N_SEQ_PER_BATCH,
        skip_probability=0.75,
        skip_probability_for_first_appliance=SKIP_PROBABILITY_FOR_TARGET,
        standardise_input=True,
        input_stats=INPUT_STATS,
        independently_center_inputs=INDEPENDENTLY_CENTER_INPUTS,
        subsample_target=SUBSAMPLE_TARGET,
        input_padding=INPUT_PADDING
    )

    same_location_source1 = SameLocation(
        logger=logger,
        filename=UKDALE_FILENAME,
        target_appliance=TARGET_APPLIANCE,
        window_per_building=WINDOW_PER_BUILDING,
        seq_length=SEQ_LENGTH,
        train_buildings=TRAIN_BUILDINGS,
        validation_buildings=VALIDATION_BUILDINGS,
        n_seq_per_batch=N_SEQ_PER_BATCH,
        skip_probability=SKIP_PROBABILITY_FOR_TARGET,
        standardise_input=True,
        offset_probability=1,
        divide_target_by=MAX_TARGET_POWER,
        input_stats=INPUT_STATS,
        independently_center_inputs=INDEPENDENTLY_CENTER_INPUTS,
        on_power_threshold=ON_POWER_THRESHOLD,
        min_on_duration=MIN_ON_DURATION,
        min_off_duration=MIN_OFF_DURATION,
        include_all=True,
        allow_incomplete=True,
        subsample_target=SUBSAMPLE_TARGET,
        input_padding=INPUT_PADDING
    )

    multi_source = MultiSource(
        sources=[
            {
                'source': real_appliance_source1,
                'train_probability': 0.5,
                'validation_probability': 0
            },
            {
                'source': same_location_source1,
                'train_probability': 0.5,
                'validation_probability': 1
            }
        ],
        standardisation_source=same_location_source1
    )

    net_dict_copy = deepcopy(net_dict)
    net_dict_copy.update(dict(
        auto_reshape=True,
        experiment_name=name,
        source=multi_source,
        plotter=Plotter(
            n_seq_to_plot=32,
            n_training_examples_to_plot=16
        ),
        layers_config=[
            {
                'type': DimshuffleLayer,
                'pattern': (0, 2, 1)  # (batch, features, time)
            },
            {
                'type': Conv1DLayer,  # convolve over the time axis
                'num_filters': 16,
                'filter_size': 2,
                'stride': 1,
                'nonlinearity': None,
                'border_mode': 'same'
            },
            {
                'type': DimshuffleLayer,
                'pattern': (0, 2, 1),  # back to (batch, time, features)
                'label': 'dimshuffle3'
            },
            {
                'type': BLSTMLayer,
                'num_units': 128,
                'merge_mode': 'concatenate'
            },
            {
                'type': BLSTMLayer,
                'num_units': 128,
                'merge_mode': 'concatenate'
            },
            {
                'type': DenseLayer,
                'num_units': 64,
                'nonlinearity': tanh
            },
            {
                'type': DenseLayer,
                'num_units': 1,
                'nonlinearity': None
            }
        ]

    ))
    net = Net(**net_dict_copy)
    return net


def exp_g(name):
    # conv at beginning
    # b but with dropout
    logger = logging.getLogger(name)
    global multi_source

    SEQ_LENGTH = 256
    N_SEQ_PER_BATCH = 64

    real_appliance_source1 = RealApplianceSource(
        logger=logger,
        filename=UKDALE_FILENAME,
        appliances=[
            TARGET_APPLIANCE,
            ['fridge freezer', 'fridge', 'freezer'],
            'dish washer',
            'kettle',
            ['washer dryer', 'washing machine']
        ],
        max_appliance_powers=[MAX_TARGET_POWER, 300, 2500, 2600, 2400],
        on_power_thresholds=[ON_POWER_THRESHOLD] + [10] * 4,
        min_on_durations=[MIN_ON_DURATION, 60, 1800, 12, 1800],
        min_off_durations=[MIN_OFF_DURATION, 12, 1800, 12, 600],
        divide_input_by_max_input_power=False,
        window_per_building=WINDOW_PER_BUILDING,
        seq_length=SEQ_LENGTH,
        output_one_appliance=True,
        train_buildings=TRAIN_BUILDINGS,
        validation_buildings=VALIDATION_BUILDINGS,
        n_seq_per_batch=N_SEQ_PER_BATCH,
        skip_probability=0.75,
        skip_probability_for_first_appliance=SKIP_PROBABILITY_FOR_TARGET,
        standardise_input=True,
        input_stats=INPUT_STATS,
        independently_center_inputs=INDEPENDENTLY_CENTER_INPUTS,
        subsample_target=SUBSAMPLE_TARGET,
        input_padding=INPUT_PADDING
    )

    same_location_source1 = SameLocation(
        logger=logger,
        filename=UKDALE_FILENAME,
        target_appliance=TARGET_APPLIANCE,
        window_per_building=WINDOW_PER_BUILDING,
        seq_length=SEQ_LENGTH,
        train_buildings=TRAIN_BUILDINGS,
        validation_buildings=VALIDATION_BUILDINGS,
        n_seq_per_batch=N_SEQ_PER_BATCH,
        skip_probability=SKIP_PROBABILITY_FOR_TARGET,
        standardise_input=True,
        offset_probability=1,
        divide_target_by=MAX_TARGET_POWER,
        input_stats=INPUT_STATS,
        independently_center_inputs=INDEPENDENTLY_CENTER_INPUTS,
        on_power_threshold=ON_POWER_THRESHOLD,
        min_on_duration=MIN_ON_DURATION,
        min_off_duration=MIN_OFF_DURATION,
        include_all=True,
        allow_incomplete=True,
        subsample_target=SUBSAMPLE_TARGET,
        input_padding=INPUT_PADDING
    )

    multi_source = MultiSource(
        sources=[
            {
                'source': real_appliance_source1,
                'train_probability': 0.5,
                'validation_probability': 0
            },
            {
                'source': same_location_source1,
                'train_probability': 0.5,
                'validation_probability': 1
            }
        ],
        standardisation_source=same_location_source1
    )

    net_dict_copy = deepcopy(net_dict)
    net_dict_copy.update(dict(
        auto_reshape=True,
        experiment_name=name,
        source=multi_source,
        plotter=Plotter(
            n_seq_to_plot=32,
            n_training_examples_to_plot=16
        ),
        layers_config=[
            {
                'type': DimshuffleLayer,
                'pattern': (0, 2, 1)  # (batch, features, time)
            },
            {
                'type': Conv1DLayer,  # convolve over the time axis
                'num_filters': 16,
                'filter_size': 4,
                'stride': 1,
                'nonlinearity': None,
                'border_mode': 'same'
            },
            {
                'type': DimshuffleLayer,
                'pattern': (0, 2, 1),  # back to (batch, time, features)
                'label': 'dimshuffle3'
            },
            {
                'type': DropoutLayer
            },
            {
                'type': BLSTMLayer,
                'num_units': 128,
                'merge_mode': 'concatenate'
            },
            {
                'type': DropoutLayer
            },
            {
                'type': BLSTMLayer,
                'num_units': 256,
                'merge_mode': 'concatenate'
            },
            {
                'type': DropoutLayer
            },
            {
                'type': DenseLayer,
                'num_units': 128,
                'nonlinearity': tanh
            },
            {
                'type': DenseLayer,
                'num_units': 1,
                'nonlinearity': None
            }
        ]

    ))
    net = Net(**net_dict_copy)
    return net


def main():
    EXPERIMENTS = list('gef')  # don't bother with D.
    for experiment in EXPERIMENTS:
        full_exp_name = NAME + experiment
        func_call = init_experiment(PATH, experiment, full_exp_name)
        logger = logging.getLogger(full_exp_name)
        try:
            net = eval(func_call)
            run_experiment(net, epochs=5000)
        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt")
            break
        except Exception:
            logger.exception("Exception")
            # raise
        finally:
            logging.shutdown()


if __name__ == "__main__":
    main()


"""
Emacs variables
Local Variables:
compile-command: "cp /home/jack/workspace/python/neuralnilm/scripts/e565.py /mnt/sshfs/imperial/workspace/python/neuralnilm/scripts/"
End:
"""
