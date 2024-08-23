# -*- coding: utf-8 -*-

__author__ = 'Brett Feltmate'

import klibs
from klibs import P

from klibs.KLGraphics import KLDraw as kld
from klibs.KLGraphics import fill, blit, flip, clear
from klibs.KLUserInterface import any_key, ui_request, key_pressed
from klibs.KLCommunication import message
from klibs.KLUtilities import hide_mouse_cursor, now, pump
from klibs.KLAudio import Tone
from klibs.KLExceptions import TrialException
from klibs.KLTime import CountDown

from random import randrange, shuffle

from Parser import Parser
from NatNetClient import NatNetClient
from get_key_state import get_key_state

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

    def block(self):
        pass

    def trial_prep(self):
        pass

    def trial(self):

        return {'block_num': P.block_number, 'trial_num': P.trial_number}

    def trial_clean_up(self):
        pass

    def clean_up(self):
        pass
