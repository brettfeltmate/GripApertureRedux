# -*- coding: utf-8 -*-

__author__ = "Brett Feltmate"

# external imports
import os
from csv import DictWriter
from random import randrange

import klibs

# local imports
from get_key_state import get_key_state  # type: ignore[import]
from klibs import P
from klibs.KLAudio import Tone
from klibs.KLCommunication import message
from klibs.KLExceptions import TrialException
from klibs.KLGraphics import KLDraw as kld
from klibs.KLGraphics import blit, fill, flip
from klibs.KLUserInterface import any_key, key_pressed, ui_request
from klibs.KLUtilities import hide_mouse_cursor, pump
from klibs.KLBoundary import BoundaryInspector, CircleBoundary
from natnetclient_rough import NatNetClient  # type: ignore[import]
from OptiTracker import OptiTracker  # type: ignore[import]
from pyfirmata import serial

# experiment constants

# timings
GO_SIGNAL_ONSET = (500, 2000)
REACH_WINDOW_POST_GO_SIGNAL = 500
TRIAL_DURATION = 5000

# audio
TONE_DURATION = 50
TONE_SHAPE = "sine"
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
LEFT = "left"
RIGHT = "right"
SMALL = "small"
LARGE = "large"
TARGET = "target"
DISTRACTOR = "distractor"
GBYK = "GBYK"
KBYG = "KBYG"
OPEN = b"55"
CLOSE = b"56"


class GripApertureRedux(klibs.Experiment):
    def setup(self):
        # ensure marker count expectations are set in _params.py
        if P.expected_marker_count is None:  # type: ignore[attr-defined]
            raise RuntimeError(
                "Need to set a value for expected_marker_count in _params.py"
                + "\n\tThis value MUST MATCH the number of tracked markers"
            )

        self.ot = OptiTracker()
        self.ot.window_size = 2

        # setup optitrack client
        self.nnc = NatNetClient()

        # pass marker set listener to client for callback
        self.nnc.markers_listener = self.marker_set_listener
        self.nnc.rigid_bodies_listener = self.rigid_bodies_listener
        self.nnc.legacy_markers_listener = self.legacy_markers_listener

        # setup firmata board (plato goggle controller)
        self.goggles = serial.Serial(port="COM6", baudrate=9600)

        # placeholder space 12cm
        self.locs = {  # 12cm between placeholder centers
            LEFT: (P.screen_c[0] - POS_OFFSET, P.screen_c[1]),  # type: ignore[attr-defined]
            RIGHT: (P.screen_c[0] + POS_OFFSET, P.screen_c[1]),  # type: ignore[attr-defined]
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
        self.go_signal = Tone(TONE_DURATION, TONE_SHAPE, TONE_FREQ, TONE_VOLUME)

        # generate block sequence
        if P.run_practice_blocks:
            self.block_sequence = [task for task in P.task_order for _ in range(2)]  # type: ignore[attr-defined]
            self.insert_practice_block(
                block_nums=[1, 3], trial_counts=P.trials_per_practice_block  # type: ignore[attr-defined]
            )
        else:
            self.block_sequence = P.task_order  # type: ignore[attr-defined]

        # create data directories
        if not os.path.exists("OptiData"):
            os.mkdir("OptiData")

        os.mkdir(f"OptiData/{P.p_id}")
        os.mkdir(f"OptiData/{P.p_id}/testing")

        if P.run_practice_blocks:
            os.mkdir(f"OptiData/{P.p_id}/practice")

    def block(self):

        # TODO: assign correct data directory to self.opti

        self.block_task = self.block_sequence[P.block_number]

        self.block_dir = f"OptiData/{P.p_id}"
        self.block_dir += "/practice" if P.practicing else "/testing"

        if os.path.exists(self.block_dir):
            raise RuntimeError(f"Data directory already exists at {self.block_dir}")

        os.mkdir(self.block_dir)

        # TODO: actual instructions
        instrux = (
            f"Task: {self.block_task}\n"
            + f"Block: {P.block_number} of {P.blocks_per_experiment}\n"
            + "(Instrux TBD, grab stuff)"
            + "\n\nAny key to start block."
        )

        fill()
        message(instrux, location=P.screen_c)
        flip()

        any_key()

    def trial_prep(self):

        self.trial_file_stub = f"{self.block_dir}/trial_{P.trial_number}"  # type: ignore[attr-defined]
        self.ot.data_dir = f"{self.trial_file_stub}_markers.csv"  # type: ignore[attr-defined]

        # setup trial events/timings
        self.evm.add_event(label="go_signal", onset=randrange(*GO_SIGNAL_ONSET))
        self.evm.add_event(
            label="reach_window_closed",
            onset=REACH_WINDOW_POST_GO_SIGNAL,
            after="go_signal",
        )
        self.evm.add_event(label="trial_timeout", onset=TRIAL_DURATION)

        # determine targ/dist locations
        self.distractor_loc = LEFT if self.target_loc == RIGHT else RIGHT  # type: ignore[attr-defined]

        self.target_boundary = CircleBoundary(
            label="target",
            center=self.locs[self.target_loc],  # type: ignore[attr-defined]
            radius=self.target_size,  # type: ignore[attr-defined]
        )

        self.distractor_boundary = CircleBoundary(
            label="distractor",
            center=self.locs[self.distractor_loc],  # type: ignore[attr-defined]
            radius=self.distractor_size,  # type: ignore[attr-defined]
        )

        self.bounds = BoundaryInspector(
            [self.target_boundary, self.distractor_boundary]
        )

        # instruct experimenter on prop placements
        self.goggles.write(CLOSE)
        self.present_stimuli(prep=True)

        while True:  # participant readiness signalled by keypress
            q = pump(True)
            if key_pressed(key="space", queue=q):
                break

        self.present_stimuli()  # reset display for trial start
        self.nnc.startup()  # start marker tracking

    def trial(self):  # type: ignore[override]
        # ad-hoc control flags
        rt = None
        velocity = None
        gbyk_target_is_visible = False
        object_grasped = None

        hide_mouse_cursor()

        # immediately present trials in KBYG trials
        if self.block_task == "KBYG":
            self.present_stimuli(target=True)

        # restrict movement until go signal received
        while self.evm.before("go_signal"):
            _ = ui_request()
            if get_key_state("space") == 0:
                self.evm.reset()

                fill()
                message(
                    "Please keep your hand at rest until hearing the go signal.",
                    location=P.screen_c,
                    registration=5,
                )
                flip()

                raise TrialException(
                    # TODO: write log of recycled trials
                    f"{self.block_task}, B{P.block_number}-T{P.trial_number}: Participant moved before go signal."
                )
        # used to calculate RT, also logged for analysis purposes
        go_signal_onset_time = self.evm.trial_time_ms

        self.go_signal.play()  # play go-signal
        self.goggles.write(OPEN)  # open goggles

        # monitor for movement start
        while self.evm.before("reach_window_closed"):
            _ = ui_request()

            # key release indicates reach is (presumeably) in motion
            if get_key_state("space") == 0 and rt is None:
                # rt = time between go signal and keyrelease
                rt = self.evm.trial_time_ms - go_signal_onset_time
                break

            if rt is not None:
                if self.block_task == "GBYK":
                    velocity = self.ot.velocity()
                    # present target once velocity threshold is met (and target is not already visible)
                    if (
                        velocity >= P.velocity_threshold  # type: ignore[unknown-attr]
                        and not gbyk_target_is_visible
                    ):
                        self.present_stimuli(target=True)
                        gbyk_target_is_visible = True

            if gbyk_target_is_visible and object_grasped is None:
                current_position = self.ot.position()
                if self.bounds.within_boundary("target", current_position):
                    object_grasped = TARGET
                elif self.bounds.within_boundary("distractor", current_position):
                    object_grasped = DISTRACTOR
                else:
                    pass

            if object_grasped is not None:
                break

        if object_grasped is None or (self.block_task == "GBYK" and not gbyk_target_is_visible):
            raise TrialException(f"{self.block_task}, B{P.block_number}-T{P.trial_number}: Reach timeout.")

        while self.evm.before("trial_finished"):
            _ = ui_request()

        # cease recording upon trial completion
        self.nnc.shutdown()

        return {
            "block_num": P.block_number,
            "trial_num": P.trial_number,
            "practicing": P.practicing,
            "task_type": self.block_task,
            "target_loc": self.target_loc,  # type: ignore[attr-defined]
            "target_size": self.target_size,  # type: ignore[attr-defined]
            "distractor_size": self.distractor_size,  # type: ignore[attr-defined]
            "go_signal_onset": go_signal_onset_time,
            "velocity": velocity if not None else -1,
            "response_time": rt if not None else -1,
            "object_grasped": object_grasped if not None else "NA",
        }

    def trial_clean_up(self):
        pass

    def clean_up(self):
        pass

    # conditionally present stimuli
    def present_stimuli(self, prep=False, target=False, dev=False):
        fill()

        if prep:
            message(
                "Place props within size-matched rings.\n\nKeypress to start trial.",
                location=[P.screen_c[0], P.screen_c[1] // 3],  # type: ignore[attr-defined]
            )

        if dev:
            message(
                "(DevMode)\nAny key to reveal target.",
                location=[P.screen_c[0], P.screen_c[1] // 3],  # type: ignore[attr-defined]
            )

        distractor_holder = self.placeholders[DISTRACTOR][self.distractor_size]  # type: ignore[attr-defined]
        distractor_holder.fill = GRUE

        target_holder = self.placeholders[TARGET][self.target_size]  # type: ignore[attr-defined]
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
        # Append data to trial-specific CSV file
        fname = f"{self.trial_file_stub}_markers.csv"  # type: ignore[attr-defined]

        with open(fname, "a", newline="") as file:
            writer = DictWriter(file, fieldnames=marker_set["markers"][0].keys())
            if not os.path.exists(fname):
                writer.writeheader()

            for marker in marker_set.get("markers", None):
                writer.writerow(marker)

    def legacy_markers_listener(self, markers: list) -> None:
        """Write legacy marker data to CSV file.

        Args:
            markers (list): List of legacy marker data to be written.
        """

        pass

    def rigid_bodies_listener(self, bodies: list) -> None:
        """Write rigid body data to CSV file.

        Args:
            bodies (list): List of rigid body data to be written.
        """

        pass
