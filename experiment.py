# -*- coding: utf-8 -*-

__author__ = 'Brett Feltmate'

# external imports
import os
from random import randrange
from csv import DictWriter, DictReader
from pyfirmata import serial

# local imports
from get_key_state import get_key_state
from NatNetClient import NatNetClient

from math import sqrt

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
TRIAL_DURATION_POST_GO_SIGNAL = 3000

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
        # ensure marker count expectations are set in _params.py
        if P.expected_marker_count is None:
            raise RuntimeError(
                'Need to set a value for expected_marker_count in _params.py'
                + '\n\tThis value MUST MATCH the number of markers comprising the tracked hand!'
            )

        # setup optitrack client
        self.optitrack = NatNetClient()
        # pass marker set listener to client for callback
        self.optitrack.marker_listener = self.__marker_set_listener

        # setup firmata board (plato goggle controller)
        self.plato = serial.Serial(port='COM6', baudrate=9600)

        # placeholder space 12cm
        self.locs = {  # 12cm between placeholder centers
            LEFT: (P.screen_c[0] - POS_OFFSET, P.screen_c[1]),
            RIGHT: (P.screen_c[0] + POS_OFFSET, P.screen_c[1]),
        }

        # spawn object placeholders
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

        # spawn go signal
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

        if not os.path.exists('OptiData'):
            os.mkdir('OptiData')

        os.mkdir(f'OptiData/{P.p_id}')
        os.mkdir(f'OptiData/{P.p_id}/testing')

        if P.run_practice_blocks:
            os.mkdir(f'OptiData/{P.p_id}/practice')

    def block(self):

        # grab task for current block
        try:
            self.block_task = self.block_sequence[P.block_number]
        # probably impossible, but just in case
        except IndexError:
            raise RuntimeError(
                'Block number, somehow, exceeds expected block count.'
            )

        self.block_dir = f'OptiData/{P.p_id}'
        self.block_dir += '/practice' if P.practicing else '/testing'
        self.block_dir += f'/{self.block_task}'

        if exists := os.path.exists(self.block_dir):
            raise RuntimeError(
                f'Data directory "{self.block_dir}" already exists.'
            )

        os.mkdir(self.block_dir)

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

        # setup trial events/timings
        self.evm.add_event(
            label='go_signal', onset=randrange(*GO_SIGNAL_ONSET)
        )
        self.evm.add_event(
            label='trial_finished',
            onset=TRIAL_DURATION_POST_GO_SIGNAL,
            after='go_signal',
        )

        # determine targ/dist locations
        self.distractor_loc = LEFT if self.target_loc == RIGHT else RIGHT

        # instruct experimenter on prop placements
        self.plato.write(CLOSE)
        self.__present_stimuli(prep=True)

        while True:  # participant readiness signalled by keypress
            q = pump(True)
            if key_pressed(key='space', queue=q):
                break

        self.__present_stimuli()  # reset display for trial start
        self.optitrack.startup()  # start marker tracking

    def trial(self):
        # ad-hoc control flags
        rt = None
        velocity = None
        gbyk_target_is_visible = False

        hide_mouse_cursor()

        # immediately present trials in KBYG trials
        if self.block_task == 'KBYG':
            self.__present_stimuli(target=True)

        # restrict movement until go signal received
        while self.evm.before('go_signal'):
            _ = ui_request()
            if get_key_state('space') == 0:
                self.evm.reset()

                fill()
                message(
                    'Please keep your hand at rest until hearing the go signal.',
                    location=P.screen_c,
                    registration=5,
                )
                flip()

                raise TrialException(
                    f'{self.block_task}, B{P.block_number}-T{P.trial_number}: Participant moved before go signal.'
                )
        # used to calculate RT, also logged for analysis purposes
        go_signal_onset_time = self.evm.trial_time_ms()

        self.go_signal.play()   # play go-signal
        self.plato.write(OPEN)  # open goggles

        # monitor movements until trial completion
        while self.evm.before('trial_finished'):
            _ = ui_request()

            # key release indicates reach is (presumeably) in motion
            if get_key_state('space') == 0 and rt is None:
                # rt = time between go signal and keyrelease
                rt = self.evm.trial_time_ms() - go_signal_onset_time

            # if this is a GBYK trial, and reach is ongoing, monitor velocity
            if rt is not None and self.block_task == 'GBYK':
                velocity = self.__get_velocity()
                # present target once velocity threshold is met (and target is not already visible)
                if (
                    velocity >= P.velocity_threshold
                    and not gbyk_target_is_visible
                ):
                    self.__present_stimuli(target=True)
                    gbyk_target_is_visible = True

        # cease recording upon trial completion
        self.optitrack.shutdown()

        return {
            'block_num': P.block_number,
            'trial_num': P.trial_number,
            'practicing': P.practicing,
            'task_type': self.block_task,
            'target_loc': self.target_loc,
            'target_size': self.target_size,
            'distractor_size': self.distractor_size,
            'go_signal_onset': go_signal_onset_time,
            'velocity': velocity if not None else -1,
            'response_time': rt if not None else -1,
        }

    def trial_clean_up(self):
        pass

    def clean_up(self):
        pass

    # conditionally present stimuli
    def __present_stimuli(self, prep=False, target=False, dev=False):
        fill()

        if prep:
            message(
                'Place props within size-matched rings.\n\nKeypress to start trial.',
                location=[P.screen_c[0], P.screen_c[1] // 3],
            )

        if dev:
            message(
                '(DevMode)\nAny key to reveal target.',
                location=[P.screen_c[0], P.screen_c[1] // 3],
            )

        distractor_holder = self.placeholders[DISTRACTOR][self.distractor_size]
        distractor_holder.fill = GRUE

        target_holder = self.placeholders[TARGET][self.target_size]
        target_holder.fill = WHITE if target else GRUE

        blit(
            distractor_holder,
            registration=5,
            location=self.locs[self.distractor_loc],
        )
        blit(
            target_holder, registration=5, location=self.locs[self.target_loc]
        )

        flip()

    def __get_velocity(self) -> float:
        """Calculate instantaneous velocity from the last two frames of marker data.

        Returns:
            float: Instantaneous velocity in units per second.

        Raises:
            ValueError: If required parameters are not defined in _params.

        Notes:
            Requires parameters 'set_name', 'set_len', and 'framerate' to be defined in P.
        """
        for p in ['set_name', 'set_len', 'framerate']:
            if P.get(p) is None:
                raise ValueError(f'{p} not defined in _params')

        frames = self.__query_frames(n_frames=2)

        demarkation_point = len(frames) // 2
        prev_pos = self.__colwise_means(frames[0:demarkation_point])
        curr_pos = self.__colwise_means(frames[demarkation_point:])

        travel = self.__euclidean_distance(prev_pos, curr_pos)

        return self.__derivate(delta=travel)

    def __euclidean_distance(
        self,
        ref_pos: tuple[float, float, float],
        curr_pos: tuple[float, float, float],
    ):
        """Calculate Euclidean distance between two 3D points.

        Args:
            ref_pos (tuple[float, float, float]): Reference position (x, y, z).
            curr_pos (tuple[float, float, float]): Current position (x, y, z).

        Returns:
            float: Euclidean distance between the two points.
        """
        return sqrt(sum([(curr_pos[i] - ref_pos[i]) ** 2 for i in range(3)]))

    def __colwise_means(
        self, frames: tuple[tuple[float, float, float]]
    ) -> tuple[float, float, float]:
        """Calculate column-wise means for a series of 3D coordinates.

        Args:
            frames (tuple[tuple[float, float, float]]): Series of (x, y, z) coordinates.

        Returns:
            tuple[float, float, float]: Mean (x, y, z) coordinates.

        Raises:
            ValueError: If any frame does not contain exactly 3 coordinates.
        """
        if not all(len(frame) == 3 for frame in frames):
            raise ValueError('Frames must be tuples containing xyz tuples.')

        # stack coords by transposing frames, then average columns
        return tuple(sum(column) / len(frames) for column in zip(*frames))

    def __derivate(
        self, delta: float, sampling_rate: int = P.framerate
    ) -> float:
        """Calculate time derivative of a value using supplied sampling rate.

        Args:
            delta (float): Value to be converted to rate of change.
            sampling_rate (int, optional): Sampling rate (in Hz), defaults to P.framerate.

        Returns:
            float: Rate of change per second.
        """
        return delta / (1 / sampling_rate)

    def __marker_set_listener(self, marker_set: dict) -> None:
        """Write marker set data to CSV file.

        Args:
            marker_set (dict): Dictionary containing marker data to be written.
                Expected format: {'markers': [{'key1': val1, ...}, ...]}
        """
        # Append data to trial-specific CSV file
        fname = (
            f'{self.block_dir}/trial_{P.trial_number}_{P.set_name}_markers.csv'
        )

        with open(fname, 'a', newline='') as file:
            writer = DictWriter(
                file, fieldnames=marker_set['markers'][0].keys()
            )
            if not os.path.exists(fname):
                writer.writeheader()

            for marker in marker_set.get('markers', None):
                writer.writerow(marker)

    def __query_frames(self, n_frames: int = 2) -> list:
        """Read the last n_frames worth of marker data from CSV file.

        Args:
            n_frames (int, optional): Number of frames to query. Defaults to 2.

        Returns:
            list: List of frames, where each frame contains marker coordinates.

        Raises:
            FileNotFoundError: If marker data file does not exist.
            ValueError: If insufficient data exists in the file.

        Notes:
            Expected rows counts need to be determed ad-hoc at runtime.

            The expected value is computed assuming one row per marker contained in the set,
            times the number queried frames.

            A more stable solution would be query number of tracked markers at runtime, and compare against expected count.
        """

        fname = (
            f'{self.block_dir}/trial_{P.trial_number}_{P.set_name}_markers.csv'
        )

        if not os.path.exists(fname):
            raise FileNotFoundError(
                f'Marker data file not found at:\n{fname}!'
            )

        with open(fname, newline='') as csvfile:
            reader = DictReader(csvfile)

            rows = list(reader)

            # Insufficient data means something is broken
            if len(rows) < n_frames * P.set_len:
                raise ValueError(
                    'Insufficient data to query frames. '
                    + f'Expected {n_frames * P.set_len} rows, got {len(rows)}.'
                )

            frames = [[] for _ in range(n_frames)]

            # Iterate through frames in reverse chronological order
            #
            # For each frame, extract markers from CSV rows using negative indexing
            #
            # Formula: -(frame * markers_per_set + current_marker) gets the right row
            #
            # Example: For 3 markers per set, 2 frames:
            #   Frame 0, Marker 0: -0, Frame 0, Marker 1: -1, Frame 0, Marker 2: -2
            #   Frame 1, Marker 0: -3, Frame 1, Marker 1: -4, Frame 1, Marker 2: -5
            for frame in range(n_frames):
                for marker in range(P.set_len):
                    frames[frame].append(
                        float(rows[-(frame * P.set_len + marker)])
                    )

        return frames
