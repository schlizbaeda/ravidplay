#!/usr/bin/python3

# ravidplay.py -- Random Video Player
# Copyright (C) 2021 schlizbäda
#
# ravidplay.py is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#             
# ravidplay.py is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with ravidplay.py. If not, see <http://www.gnu.org/licenses/>.
#
#
# Contributions:
# --------------
# Demo videos created by @Goldjunge from the German Raspberry Pi forum.
# https://forum-raspberrypi.de/user/42424-goldjunge/
# The videos are licensed as CC BY-SA 3.0.
#
#
# ravidplay.py uses the following modules:
# ----------------------------------------
#
# * python-omxplayer-wrapper v0.3.3                           LGPL v3
#


# TODO:
# - get video parameters (transparency, fade times) from cfg resp. meta files

import time, random
import io      # for command # if type(f) is io.TextIOWrapper:
import os      # getpid(): Get current process id
import sys     # argv[], exitcode
#from omxplayer.player import OMXPlayer
import omxplayer.player
import gpiozero



VERSION = '1.0'

OMXINSTANCE_ERR_WRONG_STATE = -3 # No video selected due to wrong state in StateMachine.select_video(...)
OMXINSTANCE_ERR_NO_VIDEO = -2 # No video defined for idle/applause
OMXINSTANCE_NONE = -1 # No free omxplayer instance
OMXINSTANCE_VIDEO1 = 0
OMXINSTANCE_VIDEO2 = 1
OMXLAYER = [52, 51, 53]

VID_INDEX = 0
VID_FILENAM = 1

# states of class StateMachine:
STATE_EXIT = 0
STATE_ERROR = 1
STATE_PREPARE_CNTDN_VIDEO = 5
STATE_SELECT_CNTDN_VIDEO = 7
STATE_SELECT_APPL_VIDEO = 8
STATE_SELECT_IDLE_VIDEO = 9
STATE_START_IDLE1_VIDEO = 10
STATE_PLAY_IDLE1_VIDEO = 11
STATE_START_IDLE2_VIDEO = 20
STATE_PLAY_IDLE2_VIDEO = 21

VERBOSE_NONE = 0
VERBOSE_ERROR = 1
VERBOSE_WARNING = 2
VERBOSE_VERSION = 3
VERBOSE_STATE = 4
VERBOSE_STATE_PROGRESS = 5
VERBOSE_GPIO = 6
VERBOSE_VIDEOINFO = 7
VERBOSE_DEBUG = 8
VERBOSE_SHOW_INSTANCES = 9


# Global constants set by code, config file, command line parameters.
# These are the default values by code if no config file nor cmdlin param:
DEFAULT_VERBOSITY = VERBOSE_DEBUG
DEFAULT_TIMESLOT = 0.02
DEFAULT_RANDOMINDEX_IDLE = 0  # -1 random selection 0 continuous selection
DEFAULT_RANDOMINDEX_CNTDN = 0 # -1 random selection 0 continuous selection
DEFAULT_RANDOMINDEX_APPL = 0  # -1 random selection 0 continuous selection

DEFAULT_IDLE_FADETIME_START = 0.5 #1.75
DEFAULT_IDLE_FADETIME_END = 0.5 #1.75
DEFAULT_IDLE_ALPHA_START = 0
DEFAULT_IDLE_ALPHA_PLAY = 255
DEFAULT_IDLE_ALPHA_END = 0
DEFAULT_CNTDN_FADETIME_START = 0.5 #1.75
DEFAULT_CNTDN_FADETIME_END = 0.5 #1.75
DEFAULT_CNTDN_GPIO_ON = 2.0  # time in seconds before video sequence ends
DEFAULT_CNTDN_GPIO_OFF = 1.0 # time in seconds before video sequence ends
DEFAULT_CNTDN_ALPHA_START = 0
DEFAULT_CNTDN_ALPHA_PLAY = 255
DEFAULT_CNTDN_ALPHA_END = 0


gl_verbosity = DEFAULT_VERBOSITY


def print_verbose(txt, verbosity, newline=True):
    if gl_verbosity >= verbosity:
        if newline: print()
        
        if verbosity == VERBOSE_ERROR:
            prefix = 'ERROR:     '
        elif verbosity == VERBOSE_WARNING:
            prefix = 'Warning:   '
        elif verbosity == VERBOSE_SHOW_INSTANCES:
            prefix = 'SHOW_INSTANCES: '
        elif verbosity == VERBOSE_DEBUG:
            prefix = 'DEBUG:     '
        else:
            prefix = ''
        print('{}{}'.format(prefix, txt), end='', flush=True)	

class Config():
    def print_properties(self, caption=None, verbosity=VERBOSE_DEBUG):
        if caption is not None:
            print_verbose('==== {} ===='.format(caption), verbosity)
        print_verbose('gl_verbosity: {}'.format(gl_verbosity), verbosity)
        print_verbose('', VERBOSE_DEBUG)
        print_verbose('timeslot=={}'.format(self.timeslot), verbosity)
        print_verbose('randomindex_idle=={}'.format(self.randomindex_idle), verbosity)
        print_verbose('randomindex_cntdn=={}'.format(self.randomindex_cntdn), verbosity)
        print_verbose('randomindex_appl=={}'.format(self.randomindex_appl), verbosity)
        print_verbose('', VERBOSE_DEBUG)
        print_verbose('fadetime_start_idle=={}'.format(self.fadetime_start_idle), verbosity)
        print_verbose('fadetime_end_idle=={}'.format(self.fadetime_end_idle), verbosity)
        print_verbose('fadetime_start_cntdn=={}'.format(self.fadetime_start_cntdn), verbosity)
        print_verbose('fadetime_end_cntdn=={}'.format(self.fadetime_end_cntdn), verbosity)
        print_verbose('gpio_on_cntdn=={}'.format(self.gpio_on_cntdn), verbosity)
        print_verbose('gpio_off_cntdn=={}'.format(self.gpio_off_cntdn), verbosity)
        print_verbose('', VERBOSE_DEBUG)
        print_verbose('alpha_start_idle=={}'.format(self.alpha_start_idle), verbosity)
        print_verbose('alpha_play_idle=={}'.format(self.alpha_play_idle), verbosity)
        print_verbose('alpha_end_idle=={}'.format(self.alpha_end_idle), verbosity)
        print_verbose('alpha_start_cntdn=={}'.format(self.alpha_start_cntdn), verbosity)
        print_verbose('alpha_play_cntdn=={}'.format(self.alpha_play_cntdn), verbosity)
        print_verbose('alpha_end_cntdn=={}'.format(self.alpha_end_cntdn), verbosity)
        print_verbose('\n', VERBOSE_DEBUG)

    def set_code_defaults(self):
        global gl_verbosity
        gl_verbosity = DEFAULT_VERBOSITY
        
        # Set the config parameters from code defaults
        # given in global constants DEFAULT_...
        self.timeslot = DEFAULT_TIMESLOT
        self.randomindex_idle = DEFAULT_RANDOMINDEX_IDLE
        self.randomindex_cntdn = DEFAULT_RANDOMINDEX_CNTDN
        self.randomindex_appl = DEFAULT_RANDOMINDEX_APPL

        self.fadetime_start_idle = DEFAULT_IDLE_FADETIME_START
        self.fadetime_end_idle = DEFAULT_IDLE_FADETIME_END
        self.alpha_start_idle = DEFAULT_IDLE_ALPHA_START
        self.alpha_play_idle = DEFAULT_IDLE_ALPHA_PLAY
        self.alpha_end_idle = DEFAULT_IDLE_ALPHA_END
        self.fadetime_start_cntdn = DEFAULT_CNTDN_FADETIME_START
        self.fadetime_end_cntdn = DEFAULT_CNTDN_FADETIME_END
        self.gpio_on_cntdn = DEFAULT_CNTDN_GPIO_ON
        self.gpio_off_cntdn = DEFAULT_CNTDN_GPIO_OFF
        self.alpha_start_cntdn = DEFAULT_CNTDN_ALPHA_START
        self.alpha_play_cntdn = DEFAULT_CNTDN_ALPHA_PLAY
        self.alpha_end_cntdn = DEFAULT_CNTDN_ALPHA_END
        
    def read_from_cfg(self, filenam=None):
        global gl_verbosity
        
        randomidx = None
        randomidx_idle = None
        randomidx_cntdn = None
        randomidx_appl = None
        
        fadetime = None
        fadetime_start = None
        fadetime_end = None
        fadetime_start_idle = None
        fadetime_end_idle = None
        fadetime_start_cntdn = None
        fadetime_end_cntdn = None
        gpio_on_cntdn = None
        gpio_off_cntdn = None
        
        alpha = None
        alpha_start = None
        alpha_play = None
        alpha_end = None
        alpha_start_idle = None
        alpha_play_idle = None
        alpha_end_idle = None
        alpha_start_cntdn = None
        alpha_play_cntdn = None
        alpha_end_cntdn = None
        
        if filenam is None:
            # Check the command line parameters for config stuff:
            f = [w[1:] for w in sys.argv[1:] if w[0] == '-']
        else:
            if filenam == '':
                # Look for common config file at ~/.config:
                filenam = os.path.realpath(sys.argv[0])
                confnam = os.path.basename(filenam)  + '.conf'
                confdir = os.path.join(os.path.expanduser('~'), '.config')
                filenam = os.path.join(confdir, confnam)
            try:
                f = open(filenam, 'r')
            except Exception:
                f = []
        for lin in f:
            lin = lin.split('#')[0] # Remove comments marked with #
            lin = [w.strip() for w in lin.split('=')]
            if len(lin) >= 2:
                # Integer parameters:
                try:
                    value = int(lin[1])
                except Exception:
                    value = None
                else:
                    if lin[0] == 'verbosity':
                        gl_verbosity = value
                    elif lin[0] == 'randomindex':
                        randomidx = value
                    elif lin[0] == 'randomindex_idle':
                        randomidx_idle = value
                    elif lin[0] == 'randomindex_cntdn':
                        randomidx_cntdn = value
                    elif lin[0] == 'randomindex_appl':
                        randomidx_appl = value
                    elif lin[0] == 'alpha':
                        alpha = value
                    elif lin[0] == 'alpha_start':
                        alpha_start = value
                    elif lin[0] == 'alpha_play':
                        alpha_play = value
                    elif lin[0] == 'alpha_end':
                        alpha_end = value
                    elif lin[0] == 'alpha_start_idle':
                        alpha_start_idle = value
                    elif lin[0] == 'alpha_play_idle':
                        alpha_play_idle = value
                    elif lin[0] == 'alpha_end_idle':
                        alpha_end_idle = value
                    elif lin[0] == 'alpha_start_cntdn':
                        alpha_start_cntdn = value
                    elif lin[0] == 'alpha_play_cntdn':
                        alpha_play_cntdn = value
                    elif lin[0] == 'alpha_end_cntdn':
                        alpha_end_cntdn = value
                # Floating-point parameters:
                try:
                    value = float(lin[1])
                except Exception:
                    value = None
                else:
                    if lin[0] == 'timeslot':
                        self.timeslot = value
                    elif lin[0] == 'fadetime':
                        fadetime = value
                    elif lin[0] == 'fadetime_start':
                        fadetime_start = value
                    elif lin[0] == 'fadetime_end':
                        fadetime_end = value
                    elif lin[0] == 'fadetime_start_idle':
                        fadetime_start_idle = value
                    elif lin[0] == 'fadetime_end_idle':
                        fadetime_end_idle = value
                    elif lin[0] == 'fadetime_start_cntdn':
                        fadetime_start_cntdn = value
                    elif lin[0] == 'fadetime_end_cntdn':
                        fadetime_end_cntdn = value
                    elif lin[0] == 'gpio_on_cntdn':
                        gpio_on_cntdn = value
                    elif lin[0] == 'gpio_off_cntdn':
                        gpio_off_cntdn = value
        # Close f only if it is really a file handle:
        if type(f) is io.TextIOWrapper:
            f.close()

        # randomindex: # -1 random selection 0 continuous selection
        if randomidx is not None:
            self.randomindex_idle = randomidx
            self.randomindex_cntdn = randomidx
            self.randomindex_appl = randomidx
        if randomidx_idle is not None:
            self.randomindex_idle = randomidx_idle
        if randomidx_cntdn is not None:
            self.randomindex_cntdn = randomidx_cntdn
        if randomidx_appl is not None:
            self.randomindex_appl = randomidx_appl
        
        # fadetime in seconds:
        if fadetime is not None:
            self.fadetime_start_idle = fadetime
            self.fadetime_end_idle = fadetime
            self.fadetime_start_cntdn = fadetime
            self.fadetime_end_cntdn = fadetime
        if fadetime_start is not None:
            self.fadetime_start_idle = fadetime_start
            self.fadetime_start_cntdn = fadetime_start
        if fadetime_end is not None:
            self.fadetime_end_idle = fadetime_end
            self.fadetime_end_cntdn = fadetime_end
        if fadetime_start_idle is not None:
            self.fadetime_start_idle = fadetime_start_idle
        if fadetime_start_cntdn is not None:
            self.fadetime_start_cntdn = fadetime_start_cntdn
        if fadetime_end_idle is not None:
            self.fadetime_end_idle = fadetime_end_idle
        if fadetime_end_cntdn is not None:
            self.fadetime_end_cntdn = fadetime_end_cntdn
        # GPIO time in seconds:
        if gpio_on_cntdn is not None:
            self.gpio_on_cntdn = gpio_on_cntdn
        if gpio_off_cntdn is not None:
            self.gpio_off_cntdn = gpio_off_cntdn
            
        # alpha (video transparency):
        if alpha is not None:
            self.alpha_start_idle = alpha
            self.alpha_play_idle = alpha
            self.alpha_end_idle = alpha
            self.alpha_start_cntdn = alpha
            self.alpha_play_cntdn = alpha
            self.alpha_end_cntdn = alpha
        if alpha_start is not None:
            self.alpha_start_idle = alpha_start
            self.alpha_start_cntdn = alpha_start
        if alpha_play is not None:
            self.alpha_play_idle = alpha_play
            self.alpha_play_cntdn = alpha_play
        if alpha_end is not None:
            self.alpha_end_idle = alpha_end
            self.alpha_end_cntdn = alpha_end
        if alpha_start_idle is not None:
            self.alpha_start_idle = alpha_start_idle
        if alpha_start_cntdn is not None:
            self.alpha_start_cntdn = alpha_start_cntdn
        if alpha_play_idle is not None:
            self.alpha_play_idle = alpha_play_idle
        if alpha_play_cntdn is not None:
            self.alpha_play_cntdn = alpha_play_cntdn
        if alpha_end_idle is not None:
            self.alpha_end_idle = alpha_end_idle
        if alpha_end_cntdn is not None:
            self.alpha_end_cntdn = alpha_end_cntdn

    def set_common_config(self):
        self.set_code_defaults() # Take hard-coded default parameters
        self.read_from_cfg('')   # Overwrite parameters with common config file
        self.read_from_cfg(None) # Overwrite parameters with command line
        pass

    def videos(self, category):
        # Take video list from filenames given by command line parameters,
        # introduced by a category parameter like "-idle:", "-cntdn:", "-appl:"
        found = False
        files = []
        for w in sys.argv[1:]:
            if w == category: 
                found = True
            elif w[0] == '-':
                found = False
            else:
                if found:
                    # TODO: parse m3u files
                    files.append(os.path.realpath(w)) # Follow symbolic links!
        return files


class VideoPlayer:
    def __init__(self, layer):
        self.layer = layer # omxplayer video render layer 
                           # (higher numbers are on top)
        self.videosize = '0,0,1919,1079' # TODO: read resolution from system
        self.fadetime_start = 0
        self.fadetime_end = 0
        self.alpha_start = 0
        self.alpha_play = 0
        self.alpha_end = 0
        self.gpio_pin = None
        self.gpio_on = 0
        self.gpio_off = 0
        
        self.last_alpha = 0
        
        self.omxplayer = None
        self.duration = 0 # < 0: An error occurred when examining the duration
        self.position = 0
        self.playback_status = 'None'
        self.is_fading = False

    def unload_omxplayer(self):
        if self.omxplayer is not None:
            # Remove current instance of omxplayer even if it is running:
            ###self.omxplayer.stop() # Debug!
            self.omxplayer.quit()
            
            # The following two commands were found at
            # https://github.com/willprice/python-omxplayer-wrapper/issues/176#issuecomment-586520583
            self.omxplayer._connection._bus.close()
            self.omxplayer._connection = None
            
            self.omxplayer = None
            self.playback_status = 'None'
            ret = 0
        else:
            # The omxplayer instance was already removed:
            ret = 1
        return ret

    # On an RPi1 or RPi0 this omxplayer init takes about 2.5s - 3.0s!
    def load_omxplayer(self,
                       filenam, args=None,
                       bus_address_finder=None,
                       Connection=None,
                       dbus_name=None,
                       pause=True):
        if filenam is None:
            # No video filename was given, e.g. due to empty video list:
            ret = 10
        elif not os.path.exists(filenam):
            # Given filename doesn't exist:
            ret = 11
        elif os.path.isdir(filenam):
        #elif os.path.ismount(filenam) or os.path.isdir(filenam):
            # Given filename is a (mount point) directory:
            ret = 12
        elif not os.access(filenam, os.R_OK):
            # Read permission denied to filenam:
            ret = 13
        elif self.omxplayer is None:
            # Create a new omxplayer instance:
            try:
                self.omxplayer = omxplayer.player.OMXPlayer(filenam, args,
                                                            bus_address_finder,
                                                            Connection,
                                                            dbus_name,
                                                            pause)
            except Exception:
                ret = 1
            else:
                ret = 0
                self.last_alpha = 0
                try:
                    # store video sequence duration in the class property
                    # self.duration to get faster access on repeated calls:
                    self.duration = self.omxplayer.duration()
                    self.position = 0
                except Exception:
                    # An error occurred when examining the video duration:
                    self.duration = -1
                    ret = 2
        else:
            # The current instance is still running:
            ret = 3
        return ret

    def updt_playback_status(self):
        # Returns from omxplayer 'Playing', 'Paused', 'Stopped'
        # and further            'None', 'Exception <text>'
        if self.omxplayer is None:
            self.playback_status = 'None'
        else:
            try:
                self.position = self.omxplayer.position()
            except Exception as e:
                self.position = -1
                self.playback_status = 'Exception {}: {}'.format(
                                       str(type(e)),
                                       str(e.args[0]))
            else:
                try:
                    # The omxplayer returns 'Playing', 'Paused', 'Stopped':
                    self.playback_status = self.omxplayer.playback_status()
                except Exception as e:
                    self.playback_status = 'Exception {}: {}'.format(
                                           str(type(e)),
                                           str(e.args[0]))
        return self.playback_status

    def set_alpha(self, alpha):
        # Check if change of alpha value is really necessary:
        if alpha < 0: alpha = 0
        if alpha > 255: alpha = 255
        if alpha != self.last_alpha:
            if self.omxplayer is not None:
                try:
                    self.omxplayer.set_alpha(alpha)
                except Exception:
                    pass
                try:
                    self.omxplayer.set_volume(alpha / 255)
                except Exception:
                    pass
            self.last_alpha = alpha

    def fade(self):
        if self.omxplayer is None:
            # do nothing!
            self.is_fading = False
        elif self.playback_status == 'Stopped' or \
             self.position >= self.duration:
                # End of video sequence reached:
                alpha = self.alpha_end
                self.set_alpha(alpha)
                self.is_fading = False
        elif self.playback_status == 'Playing':
            if self.position > (self.duration - self.fadetime_end):
                # Smooth fading-out at the end of the video sequence:
                tim = 1 - ((self.duration - self.position)
                           / self.fadetime_end)
                alpha = (self.alpha_play
                         - tim * (self.alpha_play - self.alpha_end)
                        )
                self.is_fading = True
            elif self.position < self.fadetime_start:
                # Smooth fading-in at start of the video sequence:
                
                #tim = self.position / self.fadetime_start
                # avoid division by zero:
                tim = 1 if self.fadetime_start == 0 \
                        else self.position / self.fadetime_start
                alpha = (self.alpha_start 
                         + tim * (self.alpha_play - self.alpha_start)
                        )
                self.is_fading = True
            else:
                # current video position somewhere in the middle:
                alpha = self.alpha_play
                self.is_fading = False
            self.set_alpha(alpha)
            
            # Check GPIO signaling:
            if type(self.gpio_pin) == gpiozero.output_devices.LED:
                remaining = self.duration - self.position
                if remaining - self.gpio_off <= 0:
                    # switch off trigger pin (falling slope)
                    if self.gpio_pin.is_lit == True:
                        self.gpio_pin.off()
                        print_verbose(
                             '-> camera trigger signal via GPIO stopped. ',
                             VERBOSE_GPIO)
                elif remaining - self.gpio_on <= 0:
                    # switch on trigger pin (rising slope):
                    if self.gpio_pin.is_lit == False:
                        self.gpio_pin.on()
                        print_verbose(
                             '-> camera trigger signal via GPIO started. ',
                             VERBOSE_GPIO)
        

class StateMachine:
    def __init__(self):
        self.progname = os.path.realpath(sys.argv[0])
        self.exitcode = 0
        self.omxplayer_cmdlin_params = []

        self.cfg = Config()
        self.cfg.set_common_config()
        print_verbose('Welcome to {} v{}'.format(
                os.path.basename(self.progname),
                VERSION),
                VERBOSE_VERSION)
        self.cfg.print_properties(caption='COMMON CONFIGURATION')
        
        # Non-video properties:
        self.timeslot = self.cfg.timeslot
        
        self.randomindex_idle = self.cfg.randomindex_idle
        self.randomindex_cntdn = self.cfg.randomindex_cntdn
        self.randomindex_appl = self.cfg.randomindex_appl
        
        # Lists of video files:
        self.videos_idle = self.cfg.videos('-idle:')
        self.videos_cntdn = self.cfg.videos('-cntdn:')
        self.videos_appl = self.cfg.videos('-appl:')
        if len(self.videos_appl) == 0:
            # Create another instance of list with identical contents!
            self.videos_appl = self.videos_idle.copy()

        # Create two instances of omxplayer management:
        self.manage_instance = 0
        self.pl = [None, None]
        self.pl[OMXINSTANCE_VIDEO1] = VideoPlayer(OMXLAYER[OMXINSTANCE_VIDEO1])
        self.pl[OMXINSTANCE_VIDEO2] = VideoPlayer(OMXLAYER[OMXINSTANCE_VIDEO2])
#        self.pl[OMXINSTANCE_VIDEO1].videosize = '260,50,1220,590' # DEBUG!
#        self.pl[OMXINSTANCE_VIDEO2].videosize = '870,150,1830,690' # DEBUG!
        
        # GPIO access:
        self.gpio_buzzer = gpiozero.Button(17) # J8 pin 11
        self.gpio_triggerpin = gpiozero.LED(7) # J8 pin 26
        self.gpio_exitbtn = gpiozero.Button(23) # J8 pin 16
        
        
        # Initialisation of the state machine:
        self.warnmsg = ''
        self.errmsg = ''
        self.state = STATE_SELECT_IDLE_VIDEO
        self.buzzer_enabled = 0 # True

    def show_omxinstances(self, inst=OMXINSTANCE_NONE, press_enter=False):
        start = OMXINSTANCE_VIDEO1 if inst == OMXINSTANCE_NONE else inst
        stop = (OMXINSTANCE_VIDEO2 if inst == OMXINSTANCE_NONE else inst) + 1
        for i in range(start, stop):
            print_verbose('    omxplayer instance[{}]: "{}"'.format(
                          i, self.pl[i].playback_status),
                          VERBOSE_SHOW_INSTANCES)
        if press_enter == True and gl_verbosity >= VERBOSE_SHOW_INSTANCES:
            print_verbose('--> press <ENTER>...', VERBOSE_SHOW_INSTANCES)
            input()
        
    def state_name(self, state=-1):
        if state == -1:
            state = self.state
        
        if state == STATE_EXIT:
            name = 'STATE_EXIT'
        elif state == STATE_ERROR:
            name = 'STATE_ERROR'

        elif state == STATE_PREPARE_CNTDN_VIDEO:
            name = 'STATE_PREPARE_CNTDN_VIDEO'
        elif state == STATE_SELECT_CNTDN_VIDEO:
            name = 'STATE_SELECT_CNTDN_VIDEO'
        elif state == STATE_SELECT_APPL_VIDEO:
            name = 'STATE_SELECT_APPL_VIDEO'
        elif state == STATE_SELECT_IDLE_VIDEO:
            name = 'STATE_SELECT_IDLE_VIDEO'
        elif state == STATE_START_IDLE1_VIDEO:
            name = 'STATE_START_IDLE1_VIDEO'
        elif state == STATE_PLAY_IDLE1_VIDEO:
            name = 'STATE_PLAY_IDLE1_VIDEO'
        elif state == STATE_START_IDLE2_VIDEO:
            name = 'STATE_START_IDLE2_VIDEO'
        elif state == STATE_PLAY_IDLE2_VIDEO:
            name = 'STATE_PLAY_IDLE2_VIDEO'
        else:
            name = '<unknown state {}>'.format(state)
        return name

    def random_video(self, order, state=STATE_EXIT):
        if state == STATE_EXIT: # If so, take current state of state machine
            state = self.state
        if state == STATE_SELECT_IDLE_VIDEO:
            length = len(self.videos_idle)
            if length <= 0:
                index = -1
                filenam = None
            elif self.randomindex_idle < 0:
                # random selection:
                index = random.randint(0, length - 1)
            else:
                # continuous selection:
                index = self.randomindex_idle
                filenam = self.videos_idle[index]
                self.randomindex_idle += order
                if self.randomindex_idle >= length:
                    self.randomindex_idle = 0
                if self.randomindex_idle < 0:
                    self.randomindex_idle = length - 1
        elif state == STATE_SELECT_APPL_VIDEO:
            length = len(self.videos_appl)
            if length <= 0:
                index = -1
                filenam = None
            elif self.randomindex_appl < 0:
                # random selection:
                index = random.randint(0, length - 1)
            else:
                # continuous selection:
                index = self.randomindex_appl
                filenam = self.videos_appl[index]
                self.randomindex_appl += 1
                if self.randomindex_appl >= length:
                    self.randomindex_appl = 0
                if self.randomindex_appl < 0:
                    self.randomindex_appl = length - 1
        elif state == STATE_SELECT_CNTDN_VIDEO or \
             state == STATE_PREPARE_CNTDN_VIDEO:
            length = len(self.videos_cntdn)
            if length <= 0:
                index = -1
                filenam = None
            elif self.randomindex_cntdn < 0:
                # random selection:
                index = random.randint(0, length - 1)
            else:
                # continuous selection:
                index = self.randomindex_cntdn
                filenam = self.videos_cntdn[index]
                self.randomindex_cntdn += 1
                if self.randomindex_cntdn >= length:
                    self.randomindex_cntdn = 0
                if self.randomindex_cntdn < 0:
                    self.randomindex_cntdn = length - 1
        else: # invalid state of state machine
            index = -2
            filenam = None
        return [index, filenam]

    def get_free_idle_instance(self):
        if self.pl[OMXINSTANCE_VIDEO1].playback_status == 'None' or \
           self.pl[OMXINSTANCE_VIDEO1].playback_status == 'Stopped' or \
           self.pl[OMXINSTANCE_VIDEO1].playback_status[0:9] == 'Exception':
               inst = OMXINSTANCE_VIDEO1
        elif self.pl[OMXINSTANCE_VIDEO2].playback_status == 'None' or \
             self.pl[OMXINSTANCE_VIDEO2].playback_status == 'Stopped' or \
             self.pl[OMXINSTANCE_VIDEO2].playback_status[0:9] == 'Exception':
               inst = OMXINSTANCE_VIDEO2
        else:
               # There is no free idle-instance to init with a new video file:
               inst = OMXINSTANCE_NONE
        return inst

    def select_video(self, filenam):
        inst = self.get_free_idle_instance()
        if inst <= OMXINSTANCE_NONE:
            self.warnmsg = 'No free omxplayer instance available for ' \
                           'file "{}".'.format(filenam)
        else: # A free omxplayer instance is available:
            if self.state == STATE_SELECT_IDLE_VIDEO or \
               self.state == STATE_SELECT_APPL_VIDEO:
                self.pl[inst].fadetime_start = self.cfg.fadetime_start_idle
                self.pl[inst].fadetime_end = self.cfg.fadetime_end_idle
                self.pl[inst].alpha_start = self.cfg.alpha_start_idle
                self.pl[inst].alpha_play = self.cfg.alpha_play_idle
                self.pl[inst].alpha_end = self.cfg.alpha_end_idle
                self.pl[inst].last_alpha = 0
            elif self.state == STATE_SELECT_CNTDN_VIDEO:
                self.pl[inst].fadetime_start = self.cfg.fadetime_start_cntdn
                self.pl[inst].fadetime_end = self.cfg.fadetime_end_cntdn
                self.pl[inst].alpha_start = self.cfg.alpha_start_cntdn
                self.pl[inst].alpha_play = self.cfg.alpha_play_cntdn
                self.pl[inst].alpha_end = self.cfg.alpha_end_cntdn
                self.pl[inst].last_alpha = 0
                
                # This is necessary if self.state_prepare_cntdn_video()
                # gave the responsibility to load a CNTDN video sequence
                # to self.state_select_idle_video(). This usually happens
                # when the buzzer is pressed during active fading between
                # two video sequences.
                # TODO: update default parameters for CNTDN
                self.pl[inst].gpio_pin = self.gpio_triggerpin
                self.pl[inst].gpio_on = self.cfg.gpio_on_cntdn
                self.pl[inst].gpio_off = self.cfg.gpio_off_cntdn
            else:    
                inst = OMXINSTANCE_ERR_WRONG_STATE

        if inst > OMXINSTANCE_NONE:
            print_verbose('+++ initiate new omxplayer instance[{}] +++'.format(
                              inst),
                          VERBOSE_SHOW_INSTANCES) # Debug!
            self.show_omxinstances() # Debug!
            
            # Initialise a new omxplayer instance with given video file:
            dbus_path = 'org.mpris.MediaPlayer2.omxplayer{}_{}' \
                        .format(os.getpid(), inst)
            
            # On an RPi1 or RPi0 this omxplayer init takes about 2.5s - 3.0s!
            ret = self.pl[inst].load_omxplayer(
                    filenam,
                    ['--win', self.pl[inst].videosize,
                     '--aspect-mode', 'letterbox',
                     '--layer', OMXLAYER[inst],
                     '--alpha', self.pl[inst].last_alpha,
                     '--vol', '-10000'
                    ] + self.omxplayer_cmdlin_params,
                    dbus_name=dbus_path,
                    pause=True)
            
            if ret == 0:
                print_verbose(
                    'instance[{}] initialised with video "{}" '.format(
                        inst,
                        filenam),
                    VERBOSE_VIDEOINFO)
            else:
                inst = OMXINSTANCE_ERR_NO_VIDEO
                # omxplayer errors:
                if ret == 1:
                    self.errmsg = 'ret=={}: ' \
                        'omxplayer initialisation of instance[{}] ' \
                        'with video "{}" failed.'.format(ret, inst, filenam)
                elif ret == 2:
                    self.errmsg = 'ret=={}: ' \
                        'The video duration of instance[{}] ' \
                        'with video "{}" couln\'t be ' \
                        'evaluated.'.format(ret, inst, filenam)
                elif ret == 3:
                    self.errmsg = 'ret=={}: ' \
                        'Another omxplayer instance[{}] is already ' \
                        'running.'.format(ret, inst)
                # file access errors:
                elif ret == 10:
                    self.errmsg = 'ret=={}: ' \
                        'No video filename was given, ' \
                        'e.g. due to empty video list.'.format(ret)
                elif ret == 11:
                    self.errmsg = 'ret=={}: ' \
                        'File "{}" not found.'.format(ret, filenam)
                elif ret == 12:
                    self.errmsg = 'ret=={}: ' \
                        'File "{}" is a directory.'.format(ret, filenam)
                elif ret == 13:
                    self.errmsg = 'ret=={}: ' \
                        'Read permission denied to file ' \
                        '"{}".'.format(ret, filenam)
                else:
                    self.errmsg = 'ret=={}: ' \
                        'Unknown error at initialisation of instance[{}] ' \
                        'with video "{}".'.format(ret, inst, filenam)
        return inst

    def shorten_duration(self, inst):
        ## original from self.state_prepare_cntdn_video()
        #self.pl[inst_playing].duration = \
        #    self.pl[inst_playing].omxplayer.position() \
        #    + self.pl[inst_playing].fadetime_end \
        #    + self.timeslot
        if self.pl[inst].playback_status == 'Playing' or \
           self.pl[inst].playback_status == 'Paused':
            try:
                self.pl[inst].duration = \
                              self.pl[inst].omxplayer.position() \
                              + self.pl[inst].fadetime_end \
                              + self.timeslot
            except Exception:
                # Don't mind if it doesn't work 
                # due to some rare error conditions(?)
                # caused by bad timing(?) of buzzer pressure.
                pass

    def manage_players(self):
        self.pl[self.manage_instance].updt_playback_status()
        # Delete finished omxplayer instance: 
        if self.pl[self.manage_instance].playback_status == 'Stopped' or \
           self.pl[self.manage_instance].playback_status[0:9] == 'Exception':
            print_verbose('--- unload omxplayer instance @self.manage_players() '
                          '---',
                          VERBOSE_SHOW_INSTANCES) # Debug!
            self.show_omxinstances() # Debug!
            print_verbose('unloading omxplayer instance[{}]'
                              ' ({})'.format(self.manage_instance, 
                              self.pl[self.manage_instance].playback_status),
                          VERBOSE_STATE)
            self.pl[self.manage_instance].unload_omxplayer()
            self.show_omxinstances() # Debug!
            print_verbose('', VERBOSE_SHOW_INSTANCES) # Debug!
            # Enable buzzer if CNTDN video has been completely
            # finished and unloaded:
            if type(self.pl[self.manage_instance].gpio_pin) \
               == gpiozero.output_devices.LED:
                self.buzzer_enabled = 10 # True in 5 * self.timeslot (counter)
                print_verbose('   buzzer re-enabled because '
                              'countdown video sequence has been ended.',
                          VERBOSE_GPIO)
                # remove gpio_pin as marker of the CNTDN video:
                self.pl[self.manage_instance].gpio_pin = None
                self.pl[self.manage_instance].gpio_on = 0
                self.pl[self.manage_instance].gpio_off = 0

        
        # Check if position > shortened duration
        # due to requested CNTDN video sequence (i.e. pressure of buzzer):
        if self.pl[self.manage_instance].playback_status == 'Playing':
            if self.pl[self.manage_instance].position \
               > (self.pl[self.manage_instance].duration + 2 * self.timeslot):
                   self.pl[self.manage_instance].omxplayer.quit()
        

        # Video fading:
        self.pl[self.manage_instance].fade()

        self.manage_instance += 1
        if self.manage_instance >= len(self.pl):
            self.manage_instance = 0

    #### Common states ####
    def state_error(self):
        self.state = STATE_EXIT

    #### video states ####
    def state_prepare_cntdn_video(self):
        if False == \
           self.pl[OMXINSTANCE_VIDEO1].is_fading or \
           self.pl[OMXINSTANCE_VIDEO2].is_fading: # "not fading" condition:
            # To replace the file of a waiting ('Paused') omxplayer instance
            # there must be one instance 'Paused' and the other one 'Playing':
            inst_paused = -1
            inst_playing = -1
            inst_none = 0 # count how many instances are 'omxplayer is None'
            for inst in range(OMXINSTANCE_VIDEO1, OMXINSTANCE_VIDEO2 + 1):
                playback_status = self.pl[inst].playback_status
                if playback_status == 'Paused':
                    inst_paused = inst
                    inst_paused_playback_status = playback_status
                if playback_status == 'Playing':    
                    inst_playing = inst
                if playback_status == 'None':
                    inst_none += 1
    
            if inst_paused >= 0 and inst_playing >= 0:
                print_verbose('::: prepare countdown video '
                              '@self.state_prepare_cntdn_video() :::',
                              VERBOSE_SHOW_INSTANCES) # Debug!
                self.show_omxinstances() # Debug!
    
                ######## Handle 'Paused' omxplayer instance ########
                print_verbose('changing paused omxplayer instance[{}] from '
                                'idle to countdown video sequence.'.format(
                                inst_paused), 
                                VERBOSE_STATE)
                
                # Due to some weird behaviour of the omxplayer and/or
                # https://github.com/willprice/python-omxplayer-wrapper v0.3.3
                # a simple unload doesn't work.
                # see https://github.com/willprice/python-omxplayer-wrapper/issues/176#issuecomment-586520583
                #self.pl[inst_paused].unload_omxplayer()
                
                # Workaround -- a so-called Würgaround in Denglish language :-)
                # 1st: Make the waiting (paused) idle video sequence invisible:
                self.pl[inst_paused].omxplayer.set_alpha(0)
                # 2nd: Start playback of waiting idle video sequence:
                self.pl[inst_paused].omxplayer.play()
                # 3rd: Replace video file via .load() method:
                video = self.random_video(+1)
                self.random_video(-1, STATE_SELECT_IDLE_VIDEO) #keep idle order
                # todo: update default parameters for CNTDN
                self.pl[inst_paused].gpio_pin = self.gpio_triggerpin
                self.pl[inst_paused].gpio_on = self.cfg.gpio_on_cntdn
                self.pl[inst_paused].gpio_off = self.cfg.gpio_off_cntdn
                # todo: load video-specific meta file
                print_verbose('file to exchange: "{}"'.format(
                        video[VID_FILENAM]),
                    VERBOSE_DEBUG) # todo: try-catch wrong filename!
                # Catch some well-known long-lasting error conditions:
                ret = 0
                if video[VID_FILENAM] is None:
                    # No video filename was given, e.g. due to empty video list:
                    ret = 10
                elif not os.path.exists(video[VID_FILENAM]):
                    # Given filename doesn't exist:
                    ret = 11
                elif os.path.isdir(video[VID_FILENAM]):
                #elif os.path.ismount(filenam) or os.path.isdir(filenam):
                    # Given filename is a (mount point) directory:
                    ret = 12
                elif not os.access(video[VID_FILENAM], os.R_OK):
                    # Read permission denied to filenam:
                    ret = 13
                if ret != 0:
                    # An error occurred when selecting the CNTDN video sequence
                    if ret == 10:
                        self.errmsg = 'ret=={}: ' \
                            'No countdown video filename was given ' \
                            'due to empty countdown video list.'.format(
                                ret)
                    elif ret == 11:
                        self.errmsg = 'ret=={}: ' \
                            'Countdown video file "{}" not found.'.format(
                                ret,
                                video[VID_FILENAM])
                    elif ret == 12:
                        self.errmsg = 'ret=={}: ' \
                            'Countdown video file "{}" is a directory.'.format(
                                ret,
                                video[VID_FILENAM])
                    elif ret == 13:
                        self.errmsg = 'ret=={}: ' \
                            'Read permission denied to countdown video file ' \
                            '"{}".'.format(
                                ret,
                                video[VID_FILENAM])
                    else:
                        self.errmsg = 'ret=={}: ' \
                            'Unknown error at initialisation of countdown ' \
                            'video instance[{}] with file "{}".'.format(
                                ret,
                                inst_paused,
                                video[VID_FILENAM])
                    self.state = STATE_ERROR
                else: # The video file seems to be (almost) OK :-)
                    self.pl[inst_paused].omxplayer.load(video[VID_FILENAM],
                                                        True)
                    # 4th: really important!
                    #   Adjust inst.duration to length of CNTDN video sequence!
                    self.pl[inst_paused].duration = \
                         self.pl[inst_paused].omxplayer.duration()
                    # 5th: Set next state:
                    #   skip STATE_SELECT_CNTDN_VIDEO because it was done here:
                    if inst_paused == OMXINSTANCE_VIDEO1:
                        self.state = STATE_START_IDLE1_VIDEO
                    elif inst_paused == OMXINSTANCE_VIDEO2:
                        self.state = STATE_START_IDLE2_VIDEO
                    
                    ######## Handle 'Playing' omxplayer instance ########
                    print_verbose('shorten playing idle omxplayer ' \
                                    'instance[{}] due to requested start ' \
                                    'of countdown video.'.format(
                                        inst_playing), 
                                        VERBOSE_STATE)
                    
                    print_verbose('original OMXINSTANCE_VIDEO[{}] before '
                                  'start of countdown video:\n'
                                  '  fadetime_start=={}\n'
                                  '  fadetime_end=={}\n'
                                  '  position=={}\n'
                                  '  duration=={}'.format(inst_playing,
                                        self.pl[inst_playing].fadetime_start,
                                        self.pl[inst_playing].fadetime_end,
                                        self.pl[inst_playing].position,
                                        self.pl[inst_playing].duration),
                                  VERBOSE_DEBUG)
                    # Initiate now fading of idle video sequence
                    # due to requested CNTDN:
                    
                    # Exit from eventually fading-in:
                    self.pl[inst_playing].fadetime_start = 0
                    # Adjust the fade-out time of the running idle video
                    # sequence to the defined fade-out time of the planned
                    # CNTDN video sequence:
                    self.pl[inst_playing].fadetime_end = \
                         self.cfg.fadetime_end_cntdn # todo!
                    # Shorten the duration of the running idle video sequence
                    # to "now" + fade_out time of CNTDN video sequence:
                    self.shorten_duration(inst_playing)
                    print_verbose('shorten OMXINSTANCE_VIDEO[{}] due to '
                                  'start of countdown video:\n'
                                  '  fadetime_start=={}\n'
                                  '  fadetime_end=={}\n'
                                  '  position=={}\n'
                                  '  duration=={}'.format(inst_playing,
                                        self.pl[inst_playing].fadetime_start,
                                        self.pl[inst_playing].fadetime_end,
                                        self.pl[inst_playing].position,
                                        self.pl[inst_playing].duration),
                                  VERBOSE_DEBUG)
            elif inst_none >= 1:
                self.state = STATE_SELECT_CNTDN_VIDEO

    def state_select_idle_video(self):
        if False == \
           self.pl[OMXINSTANCE_VIDEO1].is_fading or \
           self.pl[OMXINSTANCE_VIDEO2].is_fading: # "not fading" condition:
                # The method self.random_video() selects the appropriate
                # video sequence by regarding the current state, as there are:
                #    STATE_SELECT_CNTDN_VIDEO
                #    STATE_SELECT_APPL_VIDEO
                #    STATE_SELECT_IDLE_VIDEO
                video = self.random_video(+1)
                # todo: load video-specific meta file
                inst = self.select_video(video[VID_FILENAM])
                if inst == OMXINSTANCE_NONE:
                    # Do nothing if there is no free omxplayer instance.
                    # Even don't touch the state of the state machine.
                    # But restore the previous video to keep the given order:
                    self.random_video(-1) 
                elif inst == OMXINSTANCE_VIDEO1:
                    if self.state == STATE_SELECT_CNTDN_VIDEO:
                        # shorten the other instance!
                        self.shorten_duration(OMXINSTANCE_VIDEO2)
                    self.state = STATE_START_IDLE1_VIDEO
                elif inst == OMXINSTANCE_VIDEO2:
                    if self.state == STATE_SELECT_CNTDN_VIDEO:
                        # shorten the other instance!
                        self.shorten_duration(OMXINSTANCE_VIDEO1)
                    self.state = STATE_START_IDLE2_VIDEO
                else: # OMXINSTANCE_ERR_NO_VIDEO
                    # self.errmsg is already set from self.select_video(...)
                    self.exitcode = 1
                    self.state = STATE_ERROR
            
    def state_start_idle_video(self, inst_waiting):
        inst_running = OMXINSTANCE_VIDEO1 \
                       if inst_waiting != OMXINSTANCE_VIDEO1 \
                       else OMXINSTANCE_VIDEO2
        # is the waiting video ...?
        if self.pl[inst_waiting].playback_status == 'None':
            pass
        # is the current video fading out yet?
        if (self.pl[inst_running].duration \
            - self.pl[inst_running].position \
            <= self.pl[inst_running].fadetime_end \
               + 3 * self.timeslot) \
           or \
           (self.pl[inst_running].playback_status == 'None'):
                if inst_waiting == OMXINSTANCE_VIDEO1:
                    self.state = STATE_PLAY_IDLE1_VIDEO
                elif inst_waiting == OMXINSTANCE_VIDEO2:
                    self.state = STATE_PLAY_IDLE2_VIDEO
        else:
            # do nothing!
            pass

    def state_play_idle_video(self, inst):
        if not self.pl[inst].omxplayer is None:
            self.pl[inst].omxplayer.set_position(0)
            self.pl[inst].set_alpha(self.pl[inst].alpha_start)
            self.pl[inst].omxplayer.play()
        if type(self.pl[inst].gpio_pin) == gpiozero.output_devices.LED:
            # select an applause video sequence after a countdown:
            self.state = STATE_SELECT_APPL_VIDEO
        else:
            self.state = STATE_SELECT_IDLE_VIDEO


    #### Loop of the state machine ####    
    def run(self):
        last_state = STATE_EXIT

        last_buzzer = None
        buzzer_debounce = 0
        
        last_exitbtn = None
        exitbtn_debounce = 0
        
        last_warnmsg = ''
        last_errmsg = ''
        
        while self.state:
            time.sleep(self.timeslot)
            self.manage_players()

            # Print current state of the state machine:
            if self.state != last_state:
                print_verbose('STATE=={:2}: "{}" '.format(self.state,
                                                          self.state_name()),
                              VERBOSE_STATE)
            else:
                print_verbose('.',
                              VERBOSE_STATE_PROGRESS,
                              newline=False)
            last_state = self.state
            
            # Check for buzzer button
            # and ignore it if it has been already pressed:
            if self.buzzer_enabled == 0:
                buzzer = self.gpio_buzzer.is_pressed
                if buzzer == last_buzzer:
                    buzzer_debounce += 1
                else:
                    buzzer_debounce = 0
                last_buzzer = buzzer
                if buzzer == True and buzzer_debounce == 2:
                    print_verbose('<= buzzer has been tied to GND',
                                  VERBOSE_GPIO)
                    self.buzzer_enabled = -1 # False
                    print_verbose('   buzzer disabled',
                                  VERBOSE_GPIO)
                    self.state = STATE_PREPARE_CNTDN_VIDEO
            elif self.buzzer_enabled > 0: # decrement internal countdown
                self.buzzer_enabled -= 1
            
            # Check for exit button:
            exitbtn = self.gpio_exitbtn.is_pressed
            if exitbtn == last_exitbtn:
                exitbtn_debounce += 1
            else:
                exitbtn_debounce = 0
            last_exitbtn = exitbtn
            if exitbtn == True and exitbtn_debounce == 2:
                print_verbose('<= exitpin has been tied to GND'
                              + ' (debounced) ',
                              VERBOSE_GPIO)
                self.state = STATE_EXIT # exit the state machine loop


            # Check the current state:
            if self.state == STATE_ERROR:
                self.state_error()
            elif self.state == STATE_PREPARE_CNTDN_VIDEO:
                self.state_prepare_cntdn_video()
            elif self.state == STATE_SELECT_APPL_VIDEO or \
                 self.state == STATE_SELECT_IDLE_VIDEO or \
                 self.state == STATE_SELECT_CNTDN_VIDEO:
                self.state_select_idle_video()
            elif self.state == STATE_START_IDLE1_VIDEO:
                self.state_start_idle_video(OMXINSTANCE_VIDEO1)
            elif self.state == STATE_START_IDLE2_VIDEO:
                self.state_start_idle_video(OMXINSTANCE_VIDEO2)
            elif self.state == STATE_PLAY_IDLE1_VIDEO:
                self.state_play_idle_video(OMXINSTANCE_VIDEO1)
            elif self.state == STATE_PLAY_IDLE2_VIDEO:
                self.state_play_idle_video(OMXINSTANCE_VIDEO2)
                
            # print occurred warnings and errors:
            if self.warnmsg != last_warnmsg:
                if self.warnmsg != '':
                    print_verbose(self.warnmsg, VERBOSE_WARNING)
                last_warnmsg = self.warnmsg
            if self.errmsg != last_errmsg:
                if self.errmsg != '':
                    print_verbose(self.errmsg, VERBOSE_ERROR)
                last_errmsg = self.errmsg

        # cleanup all omxplayer instances
        for pl in self.pl:
            pl.unload_omxplayer()
        if gl_verbosity >= VERBOSE_STATE:
            print()


if __name__ == '__main__':
    random.seed()
    statemachine = StateMachine()
    statemachine.run()
    sys.exit(statemachine.exitcode)
#EOF
