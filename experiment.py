# -*- coding: utf-8 -*-

__author__ = 'Brett Feltmate'

# external imports
import os
from csv import DictWriter
from datetime import datetime
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

# colour fills
WHITE = (255, 255, 255, 255)
GRUE = (90, 90, 96, 255)
RED = (255, 0, 0, 255)
BLUE = (0, 0, 255, 255)
GREEN = (0,255, 0, 255)
PURP = (255, 0, 255, 255)

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
NA = 'NA'
P1 = 'p1'
P2 = 'p2'


class GripApertureRedux(klibs.Experiment):
    def setup(self):
        # sizings
        self.px_cm = int(P.ppi / 2.54)

        self.px_wide = P.cm_wide * self.px_cm  # type: ignore[known-attribute]
        self.px_tall = P.cm_tall * self.px_cm  # type: ignore[known-attribute]
        self.px_brim = P.cm_brim * self.px_cm  # type: ignore[known-attribute]
        self.px_offset = P.cm_offset * self.px_cm  # type: ignore[known-attribute]

        # manages stream
        self.nnc = NatNetClient()

        # what to do with incoming data
        # TODO: OptiTracker class should handle this directly
        self.nnc.markers_listener = self.marker_set_listener

        # middleman between natnet stream and experiment
        self.ot = OptiTracker(marker_count=10, sample_rate=120, window_size=5)

        # plato goggles controller
        self.goggles = serial.Serial(port=P.arduino_comport, baudrate=P.baudrate)  # type: ignore[known-attribute]

        # 12cm centre-to-centre; aligned hoizontally along screen centre
        self.locs = {
            LEFT: (P.screen_c[0] - self.px_offset, P.screen_c[1]),
            RIGHT: (P.screen_c[0] + self.px_offset, P.screen_c[1]),
        }

        self.shapes = {
            WIDE: (self.px_wide, self.px_tall),
            TALL: (self.px_tall, self.px_wide),
        }

        # visual placeholders
        self.placeholders = {
            item: {
                shape: kld.Rectangle(
                    *self.shapes[shape],
                    stroke=[
                        self.px_brim,
                        WHITE if item == TARGET else GRUE,
                        STROKE_CENTER,
                    ],
                    fill=WHITE if item == TARGET else GRUE,
                )
                for shape in (WIDE, TALL)
            }
            for item in (TARGET, DISTRACTOR)
        }

        # for visualizing hand pos during debug
        if P.development_mode:
            self.cursor = kld.Annulus(
                self.px_cm * 2,
                self.px_cm // 5,
                stroke=[self.px_cm // 10, RED, STROKE_INNER],
                fill=RED,
            )
            self.tl_left = kld.Annulus(
                self.px_cm,
                self.px_cm // 5,
                stroke=[self.px_cm // 10, GREEN, STROKE_INNER],
                fill=GREEN,
            )
            self.br_left = kld.Annulus(
                self.px_cm,
                self.px_cm // 5,
                stroke=[self.px_cm // 10, BLUE, STROKE_INNER],
                fill=BLUE,
            )
            self.tl_right = kld.Annulus(
                self.px_cm,
                self.px_cm // 5,
                stroke=[self.px_cm // 10, RED, STROKE_INNER],
                fill=RED,
            )
            self.br_right = kld.Annulus(
                self.px_cm,
                self.px_cm // 5,
                stroke=[self.px_cm // 10, PURP, STROKE_INNER],
                fill=PURP,
            )

        # pre-calc object boundary points
        self.pts = {
            side: {
                shape: self.calc_boundary_pts(side, shape)
                for shape in (WIDE, TALL)
            }
            for side in (LEFT, RIGHT)
        }

        self.go_signal = Tone(
            P.tone_duration, P.tone_shape, P.tone_freq, P.tone_volume  # type: ignore[known-attribute]
        )

        # inject practice blocks into fixed block sequence
        if P.run_practice_blocks:
            self.block_sequence = [
                cond
                for cond in P.task_order  # type: ignore[known-attribute]
                for _ in range(P.blocks_per_experiment // 2)
            ]
            self.insert_practice_block(
                block_nums=[
                    i for i in range(P.blocks_per_experiment) if i % 2 != 0
                ],
                trial_counts=P.trials_per_practice_block,  # type: ignore[known-attribute]
            )
        else:
            self.block_sequence = P.task_order  # type: ignore[known-attribute]

        # where motion capture data is stored
        self._ensure_dir_exists(P.opti_data_dir)  # type: ignore[known-attribute]
        participant_dir = self._get_participant_base_dir()
        self._ensure_dir_exists(participant_dir)
        self._ensure_dir_exists(os.path.join(participant_dir, 'testing'))

        if P.run_practice_blocks:
            self._ensure_dir_exists(os.path.join(participant_dir, 'practice'))

    def block(self):
        self.block_task = self.block_sequence.pop(0)

        participant_dir = self._get_participant_base_dir()
        self.block_dir = self._get_block_dir_path(
            participant_dir, P.practicing, self.block_task
        )

        # data directories are (or should be) unique to individuals
        if os.path.exists(self.block_dir):
            raise RuntimeError(
                f'Data directory already exists at {self.block_dir}'
            )
        else:
            self._ensure_dir_exists(self.block_dir)

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
        self.reach_threshold = randrange(
            *P.gbyk_distance_threshold, step=10  # type: ignore[known-attribute]
        )

        # event timings
        self.evm.add_event(
            label='go_signal', onset=randrange(*P.go_signal_onset)  # type: ignore[known-attribute]
        )
        self.evm.add_event(
            label=REACH_WINDOW_CLOSED,
            onset=P.reach_window_post_go_signal,  # type: ignore[known-attribute]
            after=GO_SIGNAL,
        )
        self.evm.add_event(
            label=TRIAL_TIMEOUT,
            onset=P.post_reach_window,  # type: ignore[known-attribute]
            after=REACH_WINDOW_CLOSED,
        )

        # determine targ/dist locations
        self.distractor_loc = LEFT if self.target_loc == RIGHT else RIGHT  # type: ignore[known-attribute]

        # if hand position falls within one of these, presume object within it has been grasped
        self.target_boundary = RectangleBoundary(
            label=TARGET,
            p1=self.pts[self.target_loc][self.target_shape][P1],  # type: ignore[known-attribute]
            p2=self.pts[self.target_loc][self.target_shape][P2],  # type: ignore[known-attribute]
        )

        self.distractor_boundary = RectangleBoundary(
            label=DISTRACTOR,
            p1=self.pts[self.distractor_loc][self.distractor_shape][P1],  # type: ignore[known-attribute]
            p2=self.pts[self.distractor_loc][self.distractor_shape][P2],  # type: ignore[known-attribute]
        )

        self.bounds = BoundarySet(
            [self.target_boundary, self.distractor_boundary]
        )

        # blind participant during prop setup
        self.goggles.write(P.plato_close_cmd)  # type: ignore[known-attribute]
        self.present_stimuli(prep=True)

        while True:  # participant readiness signalled by keypress
            q = pump(True)
            if key_pressed(key=SPACE, queue=q):
                break

        # touch datafile for present trial
        self.ot.data_dir = self._get_trial_filename(
            self.block_dir,
            P.trial_number,
            self.target_loc,  # type: ignore[known-attribute]
            self.target_shape,  # type: ignore[known-attribute]
            self.distractor_shape,  # type: ignore[known-attribute]
        )

        self.nnc.startup()  # start marker tracking

        # ensure some data exists before beginning trial
        smart_sleep(P.opti_trial_lead_time)  # type: ignore[known-attribute]

    def trial(self):  # type: ignore[override]
        # Validate trial data file exists and contains data
        self._validate_trial_data_file(self.ot.data_dir)

        hide_mouse_cursor()

        # control flags
        self.target_visible = self.block_task == KBYG
        self.rt = None
        self.mt = None
        self.target_onset_time = None
        self.object_grasped = None

        self.present_stimuli(target=self.target_visible)

        # reference point to determine if/when to present targets in GBYK trials
        start_pos = self.get_hand_pos()

        if self.block_task == KBYG:
            self.goggles.write(P.plato_open_cmd)  # type: ignore[known-attribute]

        # restrict movement until go signal received
        while self.evm.before(GO_SIGNAL):
            _ = ui_request()
            if get_key_state(SPACE) == 0:
                self.abort_trial(PREMATURE_REACH)

        # used to calculate RT, also logged for analysis purposes
        go_signal_onset_time = self.evm.trial_time_ms

        self.go_signal.play()

        if self.block_task == GBYK:
            self.goggles.write(P.plato_open_cmd)  # type: ignore[known-attribute]

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
                curr_pos = self.get_hand_pos()

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
                        smart_sleep(10)

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
            'task_type': self.block_task,
            'target_loc': self.target_loc,  # type: ignore[known-attribute]
            'target_shape': self.target_shape,  # type: ignore[known-attribute]
            'distractor_shape': self.distractor_shape,  # type: ignore[known-attribute]
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

    def get_hand_pos(self):
        markers = self.ot.position()
        hand_pos = {
            axis: markers[axis][0].item() * self.px_cm
            for axis in (POS_X, POS_Y, POS_Z)
        }
        return self._translate_pos(hand_pos)

    def _translate_pos(self, pos):
        return (P.screen_x - pos[POS_X], P.screen_y - pos[POS_Z])

    def abort_trial(self, err=''):
        msgs = {
            PREMATURE_REACH: 'Please wait for the go signal.',
            REACH_TIMEOUT: 'Too slow!',
        }

        self.goggles.write(P.plato_open_cmd)  # type: ignore[known-attribute]

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

        if prep:
            message(
                'Place props within matching placeholders.\n\nKeypress to start trial.',
                location=[P.screen_c[0], P.screen_c[1] // 3],  # type: ignore[known-attribute]
            )

        distractor_holder = self.placeholders[DISTRACTOR][self.distractor_shape]  # type: ignore[known-attribute]
        distractor_holder.fill = GRUE

        if not target:
            target_holder = self.placeholders[DISTRACTOR][self.target_shape]  # type: ignore[known-attribute]
            target_holder.fill = GRUE

        else:
            target_holder = self.placeholders[TARGET][self.target_shape]  # type: ignore[known-attribute]
            target_holder.fill = WHITE

        blit(
            distractor_holder,
            registration=5,
            location=self.locs[self.distractor_loc],
        )

        blit(target_holder, registration=5, location=self.locs[self.target_loc])  # type: ignore[known-attribute]

        if P.development_mode:
            if not prep:
                blit(self.cursor, registration=5, location=self.get_hand_pos())
            blit(self.tl_right, registration=5, location=self.pts[RIGHT][self.target_shape if self.target_loc == RIGHT else self.distractor_shape][P1])
            blit(self.br_right, registration=5, location=self.pts[RIGHT][self.target_shape if self.target_loc == RIGHT else self.distractor_shape][P2])
            blit(self.tl_left, registration=5, location=self.pts[LEFT][self.target_shape if self.target_loc == LEFT else self.distractor_shape][P1])
            blit(self.br_left, registration=5, location=self.pts[LEFT][self.target_shape if self.target_loc == LEFT else self.distractor_shape][P2])


        flip()

    def marker_set_listener(self, marker_set: dict) -> None:
        """Write marker set data to CSV file.

        Args:
            marker_set (dict): Dictionary containing marker data to be written.
                Expected format: {'markers': [{'key1': val1, ...}, ...]}
        """

        if marker_set.get('label') == P.hand_marker_setname:  # type: ignore[known-attribute]
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

    def calc_boundary_pts(self, loc, shape):
        """
        Calculate goalzone region, entry serves as proxy for object grasping.
        Due to grasp shape, averaged hand pos often falls below objects.
        Crudely compensates by extending obj boundaries a 1/2 handwidth (ballpark) downwards.
            (by crudely I mean both the solution and the implementation)
        """

        # I'm sorry that you have to read this
        if loc == LEFT:
            top_left = (0, 0)
            bot_right = (
                P.screen_c[0]
                - self.px_offset
                + (self.shapes[shape][0] // 2)
                + (
                    # goalzone was a terrible choice of name
                    # the boundary extends slightly beyond inner-bottom edge of object
                    P.goalzone_padding['side']  # type: ignore[known-attribute]
                    * self.px_cm
                ),
                P.screen_c[1]
                + (self.shapes[shape][1] // 2)
                + (P.goalzone_padding['bottom'] * self.px_cm),  # type: ignore[known-attribute]
            )
        else:
            top_left = (
                P.screen_c[0]
                + self.px_offset
                - (self.shapes[shape][0] // 2)
                - (P.goalzone_padding['side'] * self.px_cm),  # type: ignore[known-attribute]
                0,
            )
            bot_right = (
                P.screen_x,
                P.screen_c[1]
                + (self.shapes[shape][1] // 2)
                + (P.goalzone_padding['bottom'] * self.px_cm),  # type: ignore[known-attribute]
            )

        return {P1: top_left, P2: bot_right}

    def _ensure_dir_exists(self, path):
        """Create directory if it doesn't exist. Raises exception on failure."""
        try:
            os.makedirs(path, exist_ok=True)
        except OSError as e:
            raise OSError(f"Failed to create directory '{path}': {e}")

    def _get_participant_base_dir(self):
        """Get base directory path for current participant."""

        if P.development_mode:  # Don't pollute real data with dev tests
            timestamp = datetime.now().strftime('%m%d_%H%M%S')
            p_id = 'DEV_' + timestamp
        else:
            p_id = str(P.p_id)
        return os.path.join(
            P.opti_data_dir, p_id  # type: ignore[known-attribute]
        )

    def _get_block_dir_path(self, participant_dir, is_practice, block_task):
        """Construct block directory path."""
        phase = 'practice' if is_practice else 'testing'
        return os.path.join(participant_dir, phase, block_task)

    def _get_trial_filename(
        self,
        block_dir,
        trial_num,
        target_loc,
        target_orient,
        distractor_orient,
    ):
        """Construct trial data filename."""
        # TODO: markup file with factor levels instead of shoehorning into filename
        filename = f'trial_{trial_num}_tSide_{target_loc}_tShape{target_orient}_dShape_{distractor_orient}_markers.csv'
        return os.path.join(block_dir, filename)

    def _validate_trial_data_file(self, filepath):
        """Validate that trial data file exists and contains data. Raises exception if not."""
        if not os.path.exists(filepath):
            raise FileNotFoundError(
                f'Trial data file does not exist: {filepath}'
            )

        try:
            with open(filepath, 'r') as f:
                lines = f.readlines()
                # Should have at least header + some data lines
                if len(lines) < 6:
                    raise ValueError(
                        f'OptiData file at \n\t{filepath}\nis sparser than expected, with only {len(lines)} lines.'
                    )
        except IOError as e:
            raise IOError(f'Cannot read trial data file: {filepath} - {e}')
