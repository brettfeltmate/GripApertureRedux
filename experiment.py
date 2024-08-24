# -*- coding: utf-8 -*-

__author__ = 'Brett Feltmate'

from random import randrange, shuffle
from csv import DictWriter
import os

# local imports
from get_key_state import get_key_state
from NatNetClient import NatNetClient
from Parser import Parser

import klibs
from klibs import P
from klibs.KLAudio import Tone
from klibs.KLCommunication import message
from klibs.KLExceptions import TrialException
from klibs.KLGraphics import KLDraw as kld
from klibs.KLGraphics import blit, clear, fill, flip
from klibs.KLTime import CountDown
from klibs.KLUserInterface import any_key, key_pressed, ui_request
from klibs.KLUtilities import hide_mouse_cursor, now, pump


# experiment constants

# timings
GO_SIGNAL_ONSET = (500, 2000)
RESPONSE_TIMEOUT = 5000

# audio
TONE_DURATION = 50
TONE_SHAPE = 'sine'
TONE_FREQ = 784  # ridin' on yo G5 airplane
TONE_VOLUME = 0.5

# sizings
PX_PER_CM = int(P.ppi / 2.54)
DIAM_SMALL = 4 * PX_PER_CM
DIAM_LARGE = 8 * PX_PER_CM
BRIMWIDTH = 1 * PX_PER_CM
POS_OFFSET = 6 * PX_PER_CM


# fills
WHITE = (255, 255, 255, 255)
GRUE = (90, 90, 96, 255)

# anti-typo protections
LEFT = 'left'
RIGHT = 'right'
SMALL = 'small'
LARGE = 'large'
TARGET = 'target'
DISTRACTOR = 'distractor'
GBYK = 'GBYK'
KBYG = 'KBYG'


class GripApertureRedux(klibs.Experiment):
    def setup(self):
        self.client = NatNetClient()
        # positional anchors
        self.places = {
            LEFT: (P.screen_c[0] - POS_OFFSET, P.screen_c[1]),
            RIGHT: (P.screen_c[0] + POS_OFFSET, P.screen_c[1]),
        }

        # NOTE:
        # Annuli serve as placement locations for physical dowels
        # Target dowel is signaled by applying a white fill to its annulus
        self.targets = {
            SMALL: kld.Annulus(DIAM_SMALL, BRIMWIDTH),
            LARGE: kld.Annulus(DIAM_LARGE, BRIMWIDTH),
        }

        self.nontargets = {
            SMALL: kld.Annulus(DIAM_SMALL, BRIMWIDTH),
            LARGE: kld.Annulus(DIAM_LARGE, BRIMWIDTH),
        }

        self.go_signal = Tone(
            TONE_DURATION, TONE_SHAPE, TONE_FREQ, TONE_VOLUME
        )

        if not os.path.exists('mocap_data'):
            os.mkdir('mocap_data')

        os.mkdir(f'mocap_data/{P.participant_id}')
        os.mkdir(f'mocap_data/{P.participant_id}/practice')
        os.mkdir(f'mocap_data/{P.participant_id}/testing')

    def block(self):
        if P.practicing:
            os.mkdir(
                f'mocap_data/{P.participant_id}/practice/block_{P.block_number}'
            )

        else:
            os.mkdir(
                f'mocap_data/{P.participant_id}/testing/block_{P.block_number}'
            )

        fill()
        message(
            'Press any key to begin the block.',
            location=P.screen_c,
            blit_txt=True,
        )
        flip()

        any_key()

    def trial_prep(self):
        fill()
        message(
            'Press any key to begin the trial.',
            location=P.screen_c,
            blit_txt=True,
        )

        flip()

        any_key()

        self.client.run()

    def trial(self):

        return {'block_num': P.block_number, 'trial_num': P.trial_number}

    def trial_clean_up(self):
        pass

    def clean_up(self):
        pass

    def trial_property_table(self):
        return {
            'participant_id': P.participant_id,
            'practicing': P.practicing,
            'block_num': P.block_number,
            'trial_num': P.trial_number,
            'task_type': self.block_task,
            'target_size': self.target_size,
            'target_loc': self.target_loc,
            'distractor_size': self.distractor_size,
            'distractor_loc': self.distractor_loc,
        }

    # TODO:
    # this will only result in blocking
    # see note in NatNetClient.py

    def natnet_marker_callback(self, markers):
        trial_props = self.trial_property_table()

        # markers is a container, so need to coerce keys to list
        fields = list(markers[0].keys())
        # include trial descriptors
        fields.append(trial_props.keys())

        fname = f'mocap_data/{P.participant_id}/'
        fname += 'practice/' if P.practicing else 'testing/'
        fname += f'block_{trial_props.block_num}/'
        fname += f'{markers[0].label}'

        if not os.path.exists(fname):
            os.mkdir(fname)

        fname += f'/trial_{trial_props.trial_num}.csv'

        if not os.path.exists(fname):
            with open(fname, 'a') as file:
                writer = DictWriter(file, fieldnames=fields)
                writer.writeheader()

        with open(fname, 'a') as file:
            writer = DictWriter(file, fieldnames=fields)
            for marker in markers:
                marker.update(trial_props)
                writer.writerow(marker)

        # if markers[0].label == 'hand':
        #     self.x_curr = sum([m.x_pos for m in markers]) / len(markers)
        #     self.y_curr = sum([m.y_pos for m in markers]) / len(markers)
        #     self.z_curr = sum([m.z_pos for m in markers]) / len(markers)

    def natnet_rigidbody_callback(self, rigidbodies):
        trial_props = self.trial_property_table()

        # markers is a container, so need to coerce keys to list
        fields = list(rigidbodies[0].keys())
        # include trial descriptors
        fields.append(trial_props.keys())

        fname = f'mocap_data/{P.participant_id}/'
        fname += 'practice/' if P.practicing else 'testing/'
        fname += f'block_{trial_props.block_num}/'
        fname += 'rigidbodies'

        if not os.path.exists(fname):
            os.mkdir(fname)

        fname += f'/trial_{trial_props.trial_num}.csv'

        if not os.path.exists(fname):
            with open(fname, 'a') as file:
                writer = DictWriter(file, fieldnames=fields)
                writer.writeheader()

        with open(fname, 'a') as file:
            writer = DictWriter(file, fieldnames=fields)
            for rigidbody in rigidbodies:
                rigidbody.update(trial_props)
                writer.writerow(rigidbody)
