# -*- coding: utf-8 -*-

__author__ = 'Brett Feltmate'

# external imports
import os
from csv import DictWriter
from random import randrange


# local imports
from get_key_state import get_key_state  # type: ignore[import]

import klibs
from klibs import P
from klibs.KLAudio import Tone
from klibs.KLConstants import STROKE_CENTER, STROKE_INNER
from klibs.KLCommunication import message
from klibs.KLExceptions import TrialException
from klibs.KLGraphics import KLDraw as kld
from klibs.KLGraphics import blit, fill, flip, clear
from klibs.KLUserInterface import any_key, key_pressed, ui_request, smart_sleep
from klibs.KLUtilities import hide_mouse_cursor, line_segment_len, pump
from klibs.KLBoundary import RectangleBoundary, BoundarySet
from klibs.KLTime import CountDown

from natnetclient_rough import NatNetClient  # type: ignore[import]
from OptiTracker import OptiTracker  # type: ignore[import]
from pyfirmata import serial  # type: ignore[import]

# experiment constants

# timings
GO_SIGNAL_ONSET = (500, 2000)
# TODO: Make this relative to rt
REACH_WINDOW_POST_GO_SIGNAL = 1000
POST_REACH_WINDOW = 1000
GBYK_DISTANCE_THRESHOLD = (
    50,
    100,
)  # these two determine when to present target
GBYK_TIMING_THRESHOLD = 0.2  # NOTE: this is in seconds, not ms

# audio
TONE_DURATION = 100
TONE_SHAPE = 'sine'
TONE_FREQ = 784  # ridin' on yo G5 airplane
TONE_VOLUME = 1.0


# fills
WHITE = (255, 255, 255, 255)
GRUE = (90, 90, 96, 255)
RED = (255, 0, 0, 255)

# anti-typo protections
LEFT = 'left'
RIGHT = 'right'
WIDE = 'wide'
TALL = 'tall'
TARGET = 'target'
DISTRACTOR = 'distractor'
GBYK = 'GBYK'
KBYG = 'KBYG'
GO_SIGNAL = 'go_signal'
REACH_WINDOW_CLOSED = 'reach_window_closed'
TRIAL_TIMEOUT = 'trial_timeout'
POS_X = 'pos_x'
POS_Y = 'pos_y'
POS_Z = 'pos_z'
SPACE = 'space'
PREMATURE_REACH = 'Premature reach'
REACH_TIMEOUT = 'Reach timeout'
OPEN = b'55'
CLOSE = b'56'
COMPORT = 'COM6'
BAUDRATE = 9600
NA = 'NA'
HAND_MARKER_LABEL = 'hand'


class GripApertureRedux(klibs.Experiment):
    def setup(self):
        # sizings
        self.px_cm = int(P.ppi / 2.54)
        PX_WIDE = P.cm_wide * self.px_cm  # type: ignore[known-attribute]
        PX_TALL = P.cm_tall * self.px_cm  # type: ignore[known-attribute]
        PX_BRIM = P.cm_brim * self.px_cm  # type: ignore[known-attribute]
        PX_OFFSET = P.cm_offset * self.px_cm  # type: ignore[known-attribute]

        # for working with streamed motion capture data
        self.ot = OptiTracker(marker_count=10, sample_rate=120, window_size=5)

        # manages stream
        self.nnc = NatNetClient()

        # what to do with incoming data
        self.nnc.markers_listener = self.marker_set_listener

        # plato goggles controller
        self.goggles = serial.Serial(port=COMPORT, baudrate=BAUDRATE)

        # 12cm between placeholder centers
        self.locs = {
            LEFT: (P.screen_c[0] - PX_OFFSET, P.screen_c[1]),  # type: ignore[attr-defined]
            RIGHT: (P.screen_c[0] + PX_OFFSET, P.screen_c[1]),  # type: ignore[attr-defined]
        }

        self.sizes = {
            WIDE: (PX_WIDE, PX_TALL),
            TALL: (PX_TALL, PX_WIDE),
        }

        # spawn object placeholders
        self.placeholders = {
            item: {
                shape: kld.Rectangle(
                    *self.sizes[shape],
                    stroke=[
                        STROKE_CENTER,
                        PX_BRIM,
                        WHITE if item == TARGET else GRUE,
                    ],
                    fill=WHITE if item == TARGET else GRUE,
                )
                for shape in (WIDE, TALL)
            }
            for item in (TARGET, DISTRACTOR)
        }

        if P.development_mode:
            self.cursor = kld.Annulus(
                self.px_cm * 2,
                self.px_cm // 5,
                stroke=[STROKE_INNER, self.px_cm // 10, RED],
                fill=RED,
            )

        self.pts = {
            side: {
                shape: self.calc_bounds(self.locs[side], self.sizes[shape])
                for shape in (WIDE, TALL)
            }
            for side in (LEFT, RIGHT)
        }

        # spawn go signal
        self.go_signal = Tone(
            TONE_DURATION, TONE_SHAPE, TONE_FREQ, TONE_VOLUME
        )

        # inject practice blocks into fixed block sequence
        if P.run_practice_blocks:
            self.block_sequence = [GBYK, GBYK, KBYG, KBYG]  # type: ignore[attr-defined]
            self.insert_practice_block(
                block_nums=[1, 3],
                trial_counts=P.trials_per_practice_block,  # type: ignore[attr-defined]
            )
        else:
            self.block_sequence = P.task_order  # type: ignore[attr-defined]

        # where motion capture data is stored
        if not os.path.exists('OptiData'):
            os.mkdir('OptiData')

        if not os.path.exists(f'OptiData/{P.condition}'):
            os.mkdir(f'OptiData/{P.condition}')

        os.mkdir(f'OptiData/{P.condition}/{P.p_id}')
        os.mkdir(f'OptiData/{P.condition}/{P.p_id}/testing')

        if P.run_practice_blocks:
            os.mkdir(f'OptiData/{P.condition}/{P.p_id}/practice')

    def block(self):
        self.block_task = self.block_sequence.pop(0)

        self.block_dir = f'OptiData/{P.condition}/{P.p_id}'
        self.block_dir += '/practice' if P.practicing else '/testing'
        self.block_dir += f'/{self.block_task}'

        # data directories are (or should be) unique to individuals
        if os.path.exists(self.block_dir):
            raise RuntimeError(
                f'Data directory already exists at {self.block_dir}'
            )
        else:
            os.mkdir(self.block_dir)

        # TODO: Proper instructions
        instrux = (
            f'Task: {self.block_task}\n'
            + f'Block: {P.block_number} of {P.blocks_per_experiment}\n\n'
            + 'Press down on space key to start trial.\n'
            + 'Once you hear the beep, let go of space key and start moving.\n'
            + 'Grab the target object and bring it back towards you.\n'
            + 'You have less than a second to complete the action before the goggles close.\n'
            + '\n\nPress any key to start block.'
        )

        fill()
        message(instrux, location=P.screen_c)
        flip()

        any_key()

    def trial_prep(self):
        # when to label a reach as being in-progress
        self.reach_threshold = randrange(*GBYK_DISTANCE_THRESHOLD, step=10)

        # event timings
        self.evm.add_event(
            label='go_signal', onset=randrange(*GO_SIGNAL_ONSET)
        )
        self.evm.add_event(
            label=REACH_WINDOW_CLOSED,
            onset=REACH_WINDOW_POST_GO_SIGNAL,
            after=GO_SIGNAL,
        )
        self.evm.add_event(
            label=TRIAL_TIMEOUT,
            onset=POST_REACH_WINDOW,
            after=REACH_WINDOW_CLOSED,
        )

        # determine targ/dist locations
        self.distractor_loc = LEFT if self.target_loc == RIGHT else RIGHT  # type: ignore[attr-defined]

        # if hand position falls within one of these, presume object within it has been grasped
        self.target_boundary = RectangleBoundary(
            label=TARGET,
            p1=self.pts[self.target_loc][self.target_orientation][0],  # type: ignore[attr-defined]
            p2=self.pts[self.target_loc][self.target_orientation][1],  # type: ignore[attr-defined]
        )

        self.distractor_boundary = RectangleBoundary(
            label=DISTRACTOR,
            p1=self.pts[self.distractor_loc][self.distractor_orientation][0],  # type: ignore[attr-defined]
            p2=self.pts[self.distractor_loc][self.distractor_orientation][1],  # type: ignore[attr-defined]
        )

        self.bounds = BoundarySet(
            [self.target_boundary, self.distractor_boundary]
        )

        # blind participant during prop setup
        self.goggles.write(CLOSE)
        self.present_stimuli(prep=True)

        while True:  # participant readiness signalled by keypress
            q = pump(True)
            if key_pressed(key=SPACE, queue=q):
                break

        self.present_stimuli()  # reset display

        # touch datafile for present trial
        self.ot.data_dir = (
            f'{self.block_dir}/'
            + f'trial_{P.trial_number}'
            + f'_targetOn_{self.target_loc}'  # type: ignore[attr-defined]
            + f'_targetOrientation_{self.target_orientation}'  # type: ignore[attr-defined]
            + f'_distractorOrientation_{self.distractor_orientation}'  # type: ignore[attr-defined]
            + '_hand_markers.csv'
        )

        self.nnc.startup()  # start marker tracking

        # sometimes datafile is queried before being created, give headstart
        # FIXME: why tho
        nnc_lead_time = CountDown(0.034)
        while nnc_lead_time.counting():
            _ = ui_request()

    def trial(self):  # type: ignore[override]
        hide_mouse_cursor()

        # control flags
        self.rt = None
        self.mt = None
        self.target_onset_time = NA
        self.target_visible = False
        self.object_grasped = None

        if self.block_task == KBYG:
            # target is immediately available
            self.present_stimuli(target=True)
            self.target_visible = True

        # reference point to determine if/when to present targets in GBYK trials
        start_pos = self.ot.position()
        start_pos = (
            start_pos[POS_X][0].item() * self.px_cm,
            start_pos[POS_Z][0].item() * self.px_cm,
        )

        # restrict movement until go signal received
        while self.evm.before(GO_SIGNAL):
            _ = ui_request()
            if get_key_state(SPACE) == 0:
                self.abort_trial(PREMATURE_REACH)

        # used to calculate RT, also logged for analysis purposes
        go_signal_onset_time = self.evm.trial_time_ms

        self.go_signal.play()
        self.goggles.write(OPEN)

        # monitor movement status following go-signal
        while self.evm.before(REACH_WINDOW_CLOSED):
            _ = ui_request()

            # key release indicates reach is in motion
            if self.rt is None:
                if get_key_state('space') == 0:
                    # treat time from go-signal to button release as reaction time
                    self.rt = self.evm.trial_time_ms - go_signal_onset_time

            # Whilst reach in motion
            else:
                curr_pos = self.ot.position()
                curr_pos = (
                    curr_pos[POS_X][0].item() * self.px_cm,
                    curr_pos[POS_Z][0].item() * self.px_cm,
                )

                # In GBYK blocks, present target once reach exceeds distance threshold
                if not self.target_visible:
                    if (
                        line_segment_len(start_pos, curr_pos)
                        > self.reach_threshold
                    ):
                        self.present_stimuli(target=True)
                        self.target_visible = True
                        # note time at which target was presented
                        self.target_onset_time = self.evm.trial_time_ms

                # log if & which object has been grasped
                elif self.object_grasped is None:
                    self.object_grasped = self.bounds.which_boundary(curr_pos)

                else:
                    self.mt = self.evm.trial_time_ms - self.rt

                    timeout = CountDown(0.3)
                    while timeout.counting():
                        q = pump(True)
                        _ = ui_request(queue=q)

                    self.nnc.shutdown()
                    # time from button release to object grasped
                    break

        # if reach window closes before object is grasped, trial is aborted
        if self.object_grasped is None:
            self.abort_trial(REACH_TIMEOUT)

        clear()

        # Don't lock up system while waiting for trial to end
        while self.evm.before(TRIAL_TIMEOUT):
            _ = ui_request()

        return {
            'block_num': P.block_number,
            'trial_num': P.trial_number,
            'practicing': P.practicing,
            'exp_condition': P.condition,
            'task_type': self.block_task,
            'target_loc': self.target_loc,  # type: ignore[attr-defined]
            'target_orientation': self.target_orientation,  # type: ignore[attr-defined]
            'distractor_orientation': self.distractor_orientation,  # type: ignore[attr-defined]
            'go_signal_onset': go_signal_onset_time,
            'distance_threshold': (
                self.reach_threshold if self.block_task == GBYK else NA
            ),
            'target_onset': self.target_onset_time,
            'response_time': self.rt,
            'movement_time': self.mt,
            'object_grasped': self.object_grasped,
        }

    def trial_clean_up(self):
        self.nnc.shutdown()

    def clean_up(self):
        pass

    def abort_trial(self, err=''):
        msgs = {
            PREMATURE_REACH: 'Please wait for the go signal.',
            REACH_TIMEOUT: 'Too slow!',
        }

        self.goggles.write(OPEN)
        self.nnc.shutdown()
        os.remove(self.ot.data_dir)

        fill()
        message(
            msgs.get(err, 'Unknown error'), location=P.screen_c, blit_txt=True
        )
        flip()

        smart_sleep(1000)

        raise TrialException(err)

    # conditionally present stimuli
    def present_stimuli(self, prep=False, target=False):
        fill()

        if P.development_mode:
            hand_marker = self.ot.position()
            hand_pos = (
                hand_marker[POS_X][0].item() * self.px_cm,
                hand_marker[POS_Z][0].item() * self.px_cm,
            )
            blit(
                kld.Circle(10, stroke=[STROKE_CENTER, 2, RED], fill=RED),
                registration=5,
                location=hand_pos,
            )

        if prep:
            message(
                'Place props within size-matched rings.\n\nKeypress to start trial.',
                location=[P.screen_c[0], P.screen_c[1] // 3],  # type: ignore[attr-defined]
            )

        distractor_holder = self.placeholders[DISTRACTOR][self.distractor_orientation]  # type: ignore[attr-defined]
        distractor_holder.fill = GRUE

        target_holder = self.placeholders[TARGET][self.target_orientation]  # type: ignore[attr-defined]
        target_holder.fill = WHITE if target else GRUE

        blit(
            distractor_holder,
            registration=5,
            location=self.locs[self.distractor_loc],
        )
        blit(target_holder, registration=5, location=self.locs[self.target_loc])  # type: ignore[attr-defined]

        flip()

    def marker_set_listener(self, marker_set: dict) -> None:
        """Write marker set data to CSV file.

        Args:
            marker_set (dict): Dictionary containing marker data to be written.
                Expected format: {'markers': [{'key1': val1, ...}, ...]}
        """

        if marker_set.get('label') == HAND_MARKER_LABEL:
            # Append data to trial-specific CSV file
            fname = self.ot.data_dir
            header = list(marker_set['markers'][0].keys())

            # if file doesn't exist, create it and write header
            if not os.path.exists(fname):
                with open(fname, 'w', newline='') as file:
                    writer = DictWriter(file, fieldnames=header)
                    writer.writeheader()

            # append marker data to file
            with open(fname, 'a', newline='') as file:
                writer = DictWriter(file, fieldnames=header)
                for marker in marker_set.get('markers', None):  # type: ignore[iterable]
                    if marker is not None:
                        writer.writerow(marker)

    def calc_bounds(self, loc, size, extend=1.5):
        return (
            (loc[0] - size[0] / 2, loc[1] - size[1] / 2) + (extend * self.px_cm),  # type: ignore[attr-defined, operation]
            (loc[0] + size[0] / 2, loc[1] + size[1] / 2) + (extend * self.px_cm),  # type: ignore[attr-defined, operation]
        )
