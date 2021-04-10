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
import os      # getpid(): Get current process id
import sys     # argv[], exitcode
#from omxplayer.player import OMXPlayer
import omxplayer.player
import gpiozero


OMXINSTANCE_ERR_WRONG_STATE = -3 # No video selected due to wrong state in StateMachine.select_video(...)
OMXINSTANCE_ERR_NO_VIDEO = -2 # No video defined for idle/applause
OMXINSTANCE_NONE = -1 # No free omxplayer instance
OMXINSTANCE_VIDEO1 = 0
OMXINSTANCE_VIDEO2 = 1
OMXLAYER = [52, 51, 53]

VID_INDEX = 0
VID_FILENAM = 1
CMDLINPAR_IDLE_FADETIME_START = 0.5 #1.75
CMDLINPAR_IDLE_FADETIME_END = 0.5 #1.75
CMDLINPAR_IDLE_ALPHA_START = 0
CMDLINPAR_IDLE_ALPHA_PLAY = 255
CMDLINPAR_IDLE_ALPHA_END = 0
CMDLINPAR_CNTDN_FADETIME_START = 0.5 #1.75
CMDLINPAR_CNTDN_FADETIME_END = 0.5 #1.75
CMDLINPAR_CNTDN_ALPHA_START = 0
CMDLINPAR_CNTDN_ALPHA_PLAY = 255
CMDLINPAR_CNTDN_ALPHA_END = 0


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
VERBOSE_STATE = 3
VERBOSE_STATE_PROGRESS = 4
VERBOSE_GPIO = 5
VERBOSE_VIDEOINFO = 6
#VERBOSE_ACTION = 7
#VERBOSE_DETAIL = 8

VERBOSE_SHOW_INSTANCES = 10
VERBOSE_DEBUG = 9
VERBOSITY = VERBOSE_DEBUG # todo: CMDLIN_PARAM

def print_verbose(txt, verbosity, newline=True):
    if VERBOSITY >= verbosity:
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
        if self.omxplayer is None:
            # Create a new omxplayer instance:
            try:
                self.omxplayer = omxplayer.player.OMXPlayer(filenam, args,
                                                            bus_address_finder,
                                                            Connection,
                                                            dbus_name,
                                                            pause)
            except:
                ret = 1
            else:
                ret = 0
                self.last_alpha = 0
                try:
                    # store video sequence duration in the class property
                    # self.duration to get faster access on repeated calls:
                    self.duration = self.omxplayer.duration()
                    self.position = 0
                except:
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
                except:
                    pass
                try:
                    self.omxplayer.set_volume(alpha / 255)
                except:
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
        self.cmdlin_params = sys.argv[1:]
        self.exitcode = 0
        
        #self.videos_idle = ['/home/pi/Videos/Animationen_converted.mp4',
        #                    '/home/pi/Videos/Günter Grünwald - Saupreiß.mp4',
        #                    '/home/pi/Videos/Sprachprobleme im Biergarten.mp4',
        #                    '/home/pi/Videos/Der weiß-blaue Babystrampler.mp4',
        #                   ]        
        
        ## Test videos with durations from 0:03 to 0:22
        ## by www.studioschraut.de from vimeo:
        ## Download them from https://vimeo.com/studioschraut
        #self.videos_idle = ['/home/pi/Videos/01_CD Promo on Vimeo.mp4',
        #                    '/home/pi/Videos/02_WIDESCREEN SHOW Intro on Vimeo.mp4',
        #                    #'/home/pi/Videos/03_Messe on Vimeo.mp4',
        #                    '/home/pi/Videos/04_SFT SPOT TV Commercial on Vimeo.mp4',
        #                    '/home/pi/Videos/05_Play Vanilla TV Spot on Vimeo.mp4'#,
        #                    #'/home/pi/Videos/06_PCG PP Commercial on Vimeo.mp4'
        #                   ]
        self.videos_idle = ['/home/pi/ravidplay/videos/idle/Random_looping_start_sequence_1.mp4',
                            '/home/pi/ravidplay/videos/idle/Random_looping_start_sequence_2.mp4',
                            '/home/pi/ravidplay/videos/idle/Random_looping_start_sequence_3.mp4'
                           ]
        
        
        #self.videos_cntdn = ['/home/pi/Videos/Disturbed_LandOfConfusion16s.mp4']
        self.videos_cntdn = ['/home/pi/ravidplay/videos/cntdn/Random_emphasize_sequence_1.mp4',
                             '/home/pi/ravidplay/videos/cntdn/Random_emphasize_sequence_2.mp4',
                             '/home/pi/ravidplay/videos/cntdn/Random_emphasize_sequence_3.mp4'
                            ]
        
        
        
        #self.videos_appl = ['/home/pi/Videos/AlanWalker_Spectre15s.mp4']
        self.videos_appl = ['/home/pi/ravidplay/videos/appl/Random_event-based_sequence_1.mp4',
                            '/home/pi/ravidplay/videos/appl/Random_event-based_sequence_2.mp4',
                            '/home/pi/ravidplay/videos/appl/Random_event-based_sequence_3.mp4'
                           ]

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
        
        # Non-video properties:
        self.timeslot = 0.02 # todo: CMDLIN_PARAM
        
        self.randomindex_idle = 0  # -1 random selection 0 continuous selection
        self.randomindex_cntdn = 0 # -1 random selection 0 continuous selection
        self.randomindex_appl = 0  # -1 random selection 0 continuous selection
        
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
        if press_enter == True and VERBOSITY >= VERBOSE_SHOW_INSTANCES:
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
            if self.randomindex_idle < 0:
                # random selection:
                index = random.randint(0, len(self.videos_idle) - 1)
            else:
                # continuous selection:
                index = self.randomindex_idle
                filenam = self.videos_idle[index]
                self.randomindex_idle += order
                if self.randomindex_idle >= len(self.videos_idle):
                    self.randomindex_idle = 0
                if self.randomindex_idle < 0:
                    self.randomindex_idle = len(self.videos_idle) - 1
        elif state == STATE_SELECT_APPL_VIDEO:
            if self.randomindex_appl < 0:
                # random selection:
                index = random.randint(0, len(self.videos_appl) - 1)
            else:
                # continuous selection:
                index = self.randomindex_appl
                filenam = self.videos_appl[index]
                self.randomindex_appl += 1
                if self.randomindex_appl >= len(self.videos_appl):
                    self.randomindex_appl = 0
                if self.randomindex_appl < 0:
                    self.randomindex_appl = len(self.videos_appl) - 1
        elif state == STATE_SELECT_CNTDN_VIDEO or \
             state == STATE_PREPARE_CNTDN_VIDEO:
            if self.randomindex_cntdn < 0:
                # random selection:
                index = random.randint(0, len(self.videos_cntdn) - 1)
            else:
                # continuous selection:
                index = self.randomindex_cntdn
                filenam = self.videos_cntdn[index]
                self.randomindex_cntdn += 1
                if self.randomindex_cntdn >= len(self.videos_cntdn):
                    self.randomindex_cntdn = 0
                if self.randomindex_cntdn < 0:
                    self.randomindex_cntdn = len(self.videos_cntdn) - 1
        else: # invalid state of state machine
            index = -1
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
                self.pl[inst].fadetime_start = CMDLINPAR_IDLE_FADETIME_START
                self.pl[inst].fadetime_end = CMDLINPAR_IDLE_FADETIME_END
                self.pl[inst].alpha_start = CMDLINPAR_IDLE_ALPHA_START
                self.pl[inst].alpha_play = CMDLINPAR_IDLE_ALPHA_PLAY
                self.pl[inst].alpha_end = CMDLINPAR_IDLE_ALPHA_END
                self.pl[inst].last_alpha = 0
            elif self.state == STATE_SELECT_CNTDN_VIDEO:
                self.pl[inst].fadetime_start = CMDLINPAR_CNTDN_FADETIME_START
                self.pl[inst].fadetime_end = CMDLINPAR_CNTDN_FADETIME_END
                self.pl[inst].alpha_start = CMDLINPAR_CNTDN_ALPHA_START
                self.pl[inst].alpha_play = CMDLINPAR_CNTDN_ALPHA_PLAY
                self.pl[inst].alpha_end = CMDLINPAR_CNTDN_ALPHA_END
                self.pl[inst].last_alpha = 0
                
                # This is necessary if self.state_prepare_cntdn_video()
                # gave the responsibility to load a CNTDN video sequence
                # to self.state_select_idle_video(). This usually happens
                # when the buzzer is pressed during active fading between
                # two video sequences.
                # TODO: update default parameters for CNTDN
                self.pl[inst].gpio_pin = self.gpio_triggerpin
                self.pl[inst].gpio_on = 2
                self.pl[inst].gpio_off = 1                
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
                    ] + self.cmdlin_params,
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
            except:
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
                self.pl[inst_paused].gpio_on = 2
                self.pl[inst_paused].gpio_off = 1
                # todo: load video-specific meta file
                print_verbose('file to exchange: "{}"'.format(
                        video[VID_FILENAM]),
                    VERBOSE_DEBUG) # todo: try-catch wrong filename!
                self.pl[inst_paused].omxplayer.load(video[VID_FILENAM], True)
                # 4th: really important!
                #      Adjust inst.duration to length of CNTDN video sequence!
                self.pl[inst_paused].duration = \
                     self.pl[inst_paused].omxplayer.duration()
                # 5th: Set next state:
                #      skip STATE_SELECT_CNTDN_VIDEO because it was done here:
                if inst_paused == OMXINSTANCE_VIDEO1:
                    self.state = STATE_START_IDLE1_VIDEO
                elif inst_paused == OMXINSTANCE_VIDEO2:
                    self.state = STATE_START_IDLE2_VIDEO
    
                ######## Handle 'Playing' omxplayer instance ########
                print_verbose('shorten playing idle omxplayer instance[{}] due to '
                                'requested start of countdown video.'.format(
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
                # Initiate now fading of idle video sequ. due to requ. CNTDN:
                
                # Exit from eventually fading-in:
                self.pl[inst_playing].fadetime_start = 0
                # Adjust the fade-out time of the running idle video sequence
                # to the defined fade-out time of the planned CNTDN video
                # sequence:
                self.pl[inst_playing].fadetime_end = \
                     CMDLINPAR_CNTDN_FADETIME_END # todo!
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
        if VERBOSITY >= VERBOSE_STATE:
            print()


if __name__ == '__main__':
    random.seed()
    statemachine = StateMachine()
    statemachine.run()
    sys.exit(statemachine.exitcode)
#EOF
