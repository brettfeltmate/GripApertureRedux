# -*- coding: utf-8 -*-

__author__ = 'Brett Feltmate'

from random import randrange, shuffle
from csv import DictWriter
import os

# local imports
from get_key_state import get_key_state
from NatNetClient import NatNetClient

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

        # placeholder locs
        self.locs = {  # 12cm between placeholder centers
            LEFT: (P.screen_c[0] - OFFSET, P.screen_c[1]),
            RIGHT: (P.screen_c[0] + OFFSET, P.screen_c[1]),
        }

        # spawn default placeholders
        self.placeholders = {
            TARGET: {
                SMALL: kld.Annulus(SMALL_DIAM, BRIMWIDTH),
                LARGE: kld.Annulus(LARGE_DIAM, BRIMWIDTH),
            },
            DISTRACTOR: {
                SMALL: kld.Annulus(SMALL_DIAM, BRIMWIDTH),
                LARGE: kld.Annulus(LARGE_DIAM, BRIMWIDTH),
            },
        }

        self.go_signal = Tone(
            TONE_DURATION, TONE_SHAPE, TONE_FREQ, TONE_VOLUME
        )

        # TODO: Work out optitrack integration

        # randomize task sequence
        self.task_sequence = [GBYK, KBYG]

        # Stitch in practice block per task if enabled
        if P.run_practice_blocks:
            self.task_sequence = [
                task for task in self.task_sequence for _ in range(2)
            ]
            self.insert_practice_block(
                block_nums=[1, 3], trial_counts=P.trials_per_practice_block
            )

    def block(self):
        if P.practicing:
            self.mocap_data_dir = f'os.getcwd()/mocap_data/{P.participant_id}/practice/block_{P.block_number}'

        else:
            self.mocap_data_dir = f'os.getcwd()/mocap_data/{P.participant_id}/testing/block_{P.block_number}'

        self.client.mocap_data_dir = self.mocap_data_dir

        # grab task
        self.block_task = self.task_sequence.pop(0)

        # instrux
        instrux = (
            f'Task: {self.block_task}\n'
            + f'Block: {P.block_number} of {P.blocks_per_experiment}\n'
            + '(Instrux TBD, grab stuff)'
            + '\n\nAny key to start block.'
        )

        fill()
        message(instrux, location=P.screen_c)
        flip()

        any_key()

    def trial_prep(self):
        # shut goggles
        self.board.write(b'56')
        # extract trial setup
        self.target, self.distractor = self.arrangement.split('_')

        self.target_loc, _ = self.target.split('-')
        self.distractor_loc, _ = self.distractor.split('-')

        # induce slight uncertainty in the reveal time
        self.evm.add_event(label='go_signal', onset=GO_SIGNAL_ONSET)
        self.evm.add_event(label='response_timeout', onset=RESPONSE_TIMEOUT)

        # TODO: close plato

        # setup phase
        self.present_arrangment(phase='setup')

        while True:
            q = pump(True)
            if key_pressed(key='space', queue=q):
                break

    def trial(self):
        self.nnc.startup()

        self.present_arrangment()

        go_signal_delay = CountDown(0.3)

        while go_signal_delay.counting():
            ui_request()

        # open goggles
        self.board.write(b'55')
        hide_mouse_cursor()

        reaction_timer = Stopwatch(start=True)
        self.go_signal.play()

        rt = 'NA'
        while self.evm.before('response_timeout'):
            if get_key_state('space') == 0 and rt == 'NA':
                rt = reaction_timer.elapsed() / 1000

        # Stop polling opt data
        self.nnc.shutdown()

        return {
            'block_num': P.block_number,
            'trial_num': P.trial_number,
            'practicing': P.practicing,
            'left_right_hand': self.hand_used,
            'palm_back_hand': self.hand_side,
            'target_loc': self.target_loc,
            'distractor_loc': self.distractor_loc,
            'response_time': rt,
        }

    def trial_clean_up(self):
        self.client.data_dir = None
        self.client.trial_factors = None

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

    def rigid_bodies_listener(self, rigid_body):
        rigid_body.update(self.trial_property_table())

        fname = (
            f'{self.block_dir}/P{P.p_id}_T{P.trial_number}_rigidbody_data.csv'
        )

        if not os.path.exists(fname):
            with open(fname, 'a', newline='') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=rigid_body.keys())
                writer.writeheader()

        with open(fname, 'a', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=rigid_body.keys())
            writer.writerow(rigid_body)

    def marker_set_listener(self, marker_set):
        trial_details = self.trial_property_table()

        fname = f"{self.block_dir}/P{P.p_id}_T{P.trial_number}_{marker_set['label']}_markerset_data.csv"

        if not os.path.exists(fname):
            sample_marker = marker_set['markers'][0].items()
            sample_marker.update(trial_details)

            with open(fname, 'a', newline='') as csvfile:
                writer = csv.DictWriter(
                    csvfile, fieldnames=sample_marker.keys()
                )
                writer.writeheader()

        with open(fname, 'a', newline='') as csvfile:
            for marker in marker_set['markers']:
                marker.update(trial_details)
                writer = csv.DictWriter(csvfile, fieldnames=marker.keys())
                writer.writerow(marker)

    def get_hand_position(self):
        trial_details = self.trial_property_table()
        fname = f"{self.block_dir}/P{P.p_id}_T{P.trial_number}_{marker_set['hand']}_markerset_data.csv"

        if not os.path.exists(fname):
            return None

        with open(fname, newline='') as csvfile:
            reader = csv.DictReader(fname)
            rows = list(reader)

            if len(rows) >= 5:
                # NOTE: 5 markers used to track hand; avg over set to get hand pos
                x_pos = sum([row['pos_x'] for row in rows[-5:]]) / 5
                y_pos = sum([row['pos_y'] for row in rows[-5:]]) / 5
                z_pos = sum([row['pos_z'] for row in rows[-5:]]) / 5

                return x_pos, y_pos, z_pos
            else:
                return None
