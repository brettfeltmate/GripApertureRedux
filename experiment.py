# -*- coding: utf-8 -*-

__author__ = 'Brett Feltmate'

# external imports
import os
from random import randrange
from csv import DictWriter, DictReader
from pyfirmata import serial
from pprint import pprint

# local imports
from get_key_state import get_key_state
from NatNetClient import NatNetClient

import klibs
from klibs import P
from klibs.KLAudio import Tone
from klibs.KLCommunication import message
from klibs.KLExceptions import TrialException
from klibs.KLGraphics import KLDraw as kld
from klibs.KLGraphics import blit, fill, flip
from klibs.KLTime import Stopwatch
from klibs.KLUserInterface import any_key, key_pressed, ui_request
from klibs.KLUtilities import hide_mouse_cursor, pump

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
OPEN = b'55'
CLOSE = b'56'


class GripApertureRedux(klibs.Experiment):
    def setup(self):
        if P.expected_marker_count is None:
            raise RuntimeError(
                'Must define a value for expected_marker_count in _params.py!'
            )

        # TODO: pull frame to confirm that actual marker count matches expected

        # setup optitrack client
        self.optitrack = NatNetClient()

        # setup firmata board (plato goggle controller)
        self.plato = serial.Serial(port='COM6', baudrate=9600)

        # placeholder space 12cm
        self.locs = {  # 12cm between placeholder centers
            LEFT: (P.screen_c[0] - POS_OFFSET, P.screen_c[1]),
            RIGHT: (P.screen_c[0] + POS_OFFSET, P.screen_c[1]),
        }

        # spawn default placeholders
        self.placeholders = {
            TARGET: {
                SMALL: kld.Annulus(DIAM_SMALL, BRIMWIDTH),
                LARGE: kld.Annulus(DIAM_LARGE, BRIMWIDTH),
            },
            DISTRACTOR: {
                SMALL: kld.Annulus(DIAM_SMALL, BRIMWIDTH),
                LARGE: kld.Annulus(DIAM_LARGE, BRIMWIDTH),
            },
        }

        self.go_signal = Tone(
            TONE_DURATION, TONE_SHAPE, TONE_FREQ, TONE_VOLUME
        )

        # generate block sequence
        if P.run_practice_blocks:
            self.block_sequence = [
                task for task in P.task_order for _ in range(2)
            ]
            self.insert_practice_block(
                block_nums=[1, 3], trial_counts=P.trials_per_practice_block
            )
        else:
            self.block_sequence = P.task_order

    def block(self):
        # grab task for current block
        try:
            self.block_task = self.block_sequence[P.block_number]
        except IndexError:
            raise RuntimeError(
                'Block number, somehow, exceeds expected block count.'
            )

        # TODO: actual instructions
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

        self.evm.add_event(
            label='go_signal', onset=randrange(*GO_SIGNAL_ONSET)
        )
        self.evm.add_event(
            label='response_timeout',
            onset=RESPONSE_TIMEOUT,
            after=GO_SIGNAL_ONSET,
        )

        self.distractor_loc = LEFT if self.target_loc == RIGHT else RIGHT

        # instruct experimenter on prop placement
        self.plato.write(CLOSE)
        self.present_stimuli(prep=True)

        self.present_stimuli()  # base display

        while True:  # participant readiness signalled by keypress
            q = pump(True)
            if key_pressed(key='space', queue=q):
                break

    def trial(self):
        hide_mouse_cursor()

        self.optitrack.startup()

        if self.block_task == 'KBYG':
            self.present_stimuli(show_target=True)

        # idle until go-signal
        while self.evm.before('go_signal'):
            _ = ui_request()
            if get_key_state('space') == 0:
                self.evm.reset()

                fill()
                message(
                    'Please keep your hand at rest until the go signal.',
                    location=P.screen_c,
                    registration=5,
                )
                flip()

                raise TrialException(
                    f'{self.block_task}, B{P.block_number}-T{P.trial_number}: Participant moved before go signal.'
                )

        self.plato.write(OPEN)  # open goggles

        self.go_signal.play()

        reaction_timer = Stopwatch(start=True)
        rt = None  # logs rt to go_signal
        while self.evm.before('response_timeout'):
            _ = ui_request()

            if get_key_state('space') == 0 and rt is None:
                rt = reaction_timer.elapsed()

            elif get_key_state('space') == 1 and rt is not None:
                self.optitrack.shutdown()  # stop tracking
                break

            else:
                # TODO: implement velocity tracking here
                pass

        return {
            'block_num': P.block_number,
            'trial_num': P.trial_number,
            'practicing': P.practicing,
            'task_type': self.block_task,
            'target_loc': self.target_loc,
            'target_size': self.target_size,
            'distractor_size': self.distractor_size,
            'response_time': rt if not None else -1,
        }

    def trial_clean_up(self):
        self.optitrack.data_dir = None
        self.optitrack.trial_factors = None

    def clean_up(self):
        pass

    def present_stimuli(self, prep=False, show_target=False, dev_mode=False):
        fill()

        if prep:
            message(
                'Place props within size-matched rings.\n\nKeypress to start trial.',
                location=[P.screen_c[0], P.screen_c[1] // 3],
            )

        if dev_mode:
            message(
                '(DevMode)\nAny key to reveal target.',
                location=[P.screen_c[0], P.screen_c[1] // 3],
            )

        distractor_holder = self.placeholders[DISTRACTOR][self.distractor_size]
        distractor_holder.fill = GRUE

        target_holder = self.placeholders[TARGET][self.target_size]
        target_holder.fill = WHITE if show_target else GRUE

        blit(
            distractor_holder,
            registration=5,
            location=self.locs[self.distractor_loc],
        )
        blit(
            target_holder, registration=5, location=self.locs[self.target_loc]
        )

        flip()

    def marker_set_listener(self, marker_set: dict) -> None:
        set_name = marker_set.get('label', 'label_missing')
        fname = f'{set_name}_markers.csv'

        if not os.path.exists(fname):
            with open(fname, 'a', newline='') as file:
                writer = DictWriter(
                    file, fieldnames=marker_set['markers'][0].keys()
                )
                writer.writeheader()
        else:
            with open(fname, 'a', newline='') as file:
                for marker in marker_set.get('markers', None):
                    writer = DictWriter(
                        file, fieldnames=marker_set['markers'][0].keys()
                    )
                    writer.writerow(marker)

    def query_markers(self, file: str, numM: int, numF: int) -> list:

        fname = f'{file}_markers.csv'

        with open(fname, newline='') as csvfile:
            reader = DictReader(csvfile)

            rows = list(reader)
            frames = [[] for _ in range(numF)]

            for frame in range(frames):
                for marker in range(numM):
                    frames[frame].append(rows[-(frame * numM + marker)])

        return frames
