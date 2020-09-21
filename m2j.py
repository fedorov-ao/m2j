#!/usr/bin/python

#Mouse to joystick emulator common functionality

import sys
import math
import time
import socket
import struct
import bisect
import logging
import json
import traceback
import weakref
import re

logger = logging.getLogger(__name__)

def sign(v):
  return -1 if v < 0 else 1 if v > 0 else 0


def slopes(seq, op):
  r = []
  for i in range(0, len(seq)-1):
    x0,x1 = seq[i],seq[i+1]
    y0,y1 = op(x0),op(x1)
    dy = y1-y0
    dx = x1-x0
    k = 0 if dx==0 else dy/dx
    r.append(k)
  return r


def clamp(v, lo, hi):
  return lo if v < lo else hi if v > hi else v


def merge_dicts(destination, source):
  """https://stackoverflow.com/questions/20656135/python-deep-merge-dictionary-data"""
  for key, value in source.items():
    if isinstance(value, dict):
      # get node or create one
      node = destination.setdefault(key, {})
      merge_dicts(node, value)
    else:
      destination[key] = value
  return destination


EV_BCAST = -1
BC_INIT = 0

codesDict = { 'ABS_BRAKE':10, 'ABS_CNT':64, 'ABS_DISTANCE':25, 'ABS_GAS':9, 'ABS_HAT0X':16, 'ABS_HAT0Y':17, 'ABS_HAT1X':18, 'ABS_HAT1Y':19, 'ABS_HAT2X':20, 'ABS_HAT2Y':21, 'ABS_HAT3X':22, 'ABS_HAT3Y':23, 'ABS_MAX':63, 'ABS_MISC':40, 'ABS_MT_BLOB_ID':56, 'ABS_MT_DISTANCE':59, 'ABS_MT_ORIENTATION':52, 'ABS_MT_POSITION_X':53, 'ABS_MT_POSITION_Y':54, 'ABS_MT_PRESSURE':58, 'ABS_MT_SLOT':47, 'ABS_MT_TOOL_TYPE':55, 'ABS_MT_TOOL_X':60, 'ABS_MT_TOOL_Y':61, 'ABS_MT_TOUCH_MAJOR':48, 'ABS_MT_TOUCH_MINOR':49, 'ABS_MT_TRACKING_ID':57, 'ABS_MT_WIDTH_MAJOR':50, 'ABS_MT_WIDTH_MINOR':51, 'ABS_PRESSURE':24, 'ABS_RESERVED':46, 'ABS_RUDDER':7, 'ABS_RX':3, 'ABS_RY':4, 'ABS_RZ':5, 'ABS_THROTTLE':6, 'ABS_TILT_X':26, 'ABS_TILT_Y':27, 'ABS_TOOL_WIDTH':28, 'ABS_VOLUME':32, 'ABS_WHEEL':8, 'ABS_X':0, 'ABS_Y':1, 'ABS_Z':2, 'BTN_0':256, 'BTN_1':257, 'BTN_2':258, 'BTN_3':259, 'BTN_4':260, 'BTN_5':261, 'BTN_6':262, 'BTN_7':263, 'BTN_8':264, 'BTN_9':265, 'BTN_A':304, 'BTN_B':305, 'BTN_BACK':278, 'BTN_BASE':294, 'BTN_BASE2':295, 'BTN_BASE3':296, 'BTN_BASE4':297, 'BTN_BASE5':298, 'BTN_BASE6':299, 'BTN_C':306, 'BTN_DEAD':303, 'BTN_DIGI':320, 'BTN_DPAD_DOWN':545, 'BTN_DPAD_LEFT':546, 'BTN_DPAD_RIGHT':547, 'BTN_DPAD_UP':544, 'BTN_EAST':305, 'BTN_EXTRA':276, 'BTN_FORWARD':277, 'BTN_GAMEPAD':304, 'BTN_GEAR_DOWN':336, 'BTN_GEAR_UP':337, 'BTN_JOYSTICK':288, 'BTN_LEFT':272, 'BTN_MIDDLE':274, 'BTN_MISC':256, 'BTN_MODE':316, 'BTN_MOUSE':272, 'BTN_NORTH':307, 'BTN_PINKIE':293, 'BTN_RIGHT':273, 'BTN_SELECT':314, 'BTN_SIDE':275, 'BTN_SOUTH':304, 'BTN_START':315, 'BTN_STYLUS':331, 'BTN_STYLUS2':332, 'BTN_STYLUS3':329, 'BTN_TASK':279, 'BTN_THUMB':289, 'BTN_THUMB2':290, 'BTN_THUMBL':317, 'BTN_THUMBR':318, 'BTN_TL':310, 'BTN_TL2':312, 'BTN_TOOL_AIRBRUSH':324, 'BTN_TOOL_BRUSH':322, 'BTN_TOOL_DOUBLETAP':333, 'BTN_TOOL_FINGER':325, 'BTN_TOOL_LENS':327, 'BTN_TOOL_MOUSE':326, 'BTN_TOOL_PEN':320, 'BTN_TOOL_PENCIL':323, 'BTN_TOOL_QUADTAP':335, 'BTN_TOOL_QUINTTAP':328, 'BTN_TOOL_RUBBER':321, 'BTN_TOOL_TRIPLETAP':334, 'BTN_TOP':291, 'BTN_TOP2':292, 'BTN_TOUCH':330, 'BTN_TR':311, 'BTN_TR2':313, 'BTN_TRIGGER':288, 'BTN_TRIGGER_HAPPY':704, 'BTN_TRIGGER_HAPPY1':704, 'BTN_TRIGGER_HAPPY10':713, 'BTN_TRIGGER_HAPPY11':714, 'BTN_TRIGGER_HAPPY12':715, 'BTN_TRIGGER_HAPPY13':716, 'BTN_TRIGGER_HAPPY14':717, 'BTN_TRIGGER_HAPPY15':718, 'BTN_TRIGGER_HAPPY16':719, 'BTN_TRIGGER_HAPPY17':720, 'BTN_TRIGGER_HAPPY18':721, 'BTN_TRIGGER_HAPPY19':722, 'BTN_TRIGGER_HAPPY2':705, 'BTN_TRIGGER_HAPPY20':723, 'BTN_TRIGGER_HAPPY21':724, 'BTN_TRIGGER_HAPPY22':725, 'BTN_TRIGGER_HAPPY23':726, 'BTN_TRIGGER_HAPPY24':727, 'BTN_TRIGGER_HAPPY25':728, 'BTN_TRIGGER_HAPPY26':729, 'BTN_TRIGGER_HAPPY27':730, 'BTN_TRIGGER_HAPPY28':731, 'BTN_TRIGGER_HAPPY29':732, 'BTN_TRIGGER_HAPPY3':706, 'BTN_TRIGGER_HAPPY30':733, 'BTN_TRIGGER_HAPPY31':734, 'BTN_TRIGGER_HAPPY32':735, 'BTN_TRIGGER_HAPPY33':736, 'BTN_TRIGGER_HAPPY34':737, 'BTN_TRIGGER_HAPPY35':738, 'BTN_TRIGGER_HAPPY36':739, 'BTN_TRIGGER_HAPPY37':740, 'BTN_TRIGGER_HAPPY38':741, 'BTN_TRIGGER_HAPPY39':742, 'BTN_TRIGGER_HAPPY4':707, 'BTN_TRIGGER_HAPPY40':743, 'BTN_TRIGGER_HAPPY5':708, 'BTN_TRIGGER_HAPPY6':709, 'BTN_TRIGGER_HAPPY7':710, 'BTN_TRIGGER_HAPPY8':711, 'BTN_TRIGGER_HAPPY9':712, 'BTN_WEST':308, 'BTN_WHEEL':336, 'BTN_X':307, 'BTN_Y':308, 'BTN_Z':309, 'EV_ABS':3, 'EV_CNT':32, 'EV_FF':21, 'EV_FF_STATUS':23, 'EV_KEY':1, 'EV_LED':17, 'EV_MAX':31, 'EV_MSC':4, 'EV_PWR':22, 'EV_REL':2, 'EV_REP':20, 'EV_SND':18, 'EV_SW':5, 'EV_SYN':0, 'EV_UINPUT':257, 'EV_VERSION':65537, 'KEY_0':11, 'KEY_1':2, 'KEY_102ND':86, 'KEY_10CHANNELSDOWN':441, 'KEY_10CHANNELSUP':440, 'KEY_2':3, 'KEY_3':4, 'KEY_3D_MODE':623, 'KEY_4':5, 'KEY_5':6, 'KEY_6':7, 'KEY_7':8, 'KEY_8':9, 'KEY_9':10, 'KEY_A':30, 'KEY_AB':406, 'KEY_ADDRESSBOOK':429, 'KEY_AGAIN':129, 'KEY_ALS_TOGGLE':560, 'KEY_ALTERASE':222, 'KEY_ANGLE':371, 'KEY_APOSTROPHE':40, 'KEY_APPSELECT':580, 'KEY_ARCHIVE':361, 'KEY_ASSISTANT':583, 'KEY_ATTENDANT_OFF':540, 'KEY_ATTENDANT_ON':539, 'KEY_ATTENDANT_TOGGLE':541, 'KEY_AUDIO':392, 'KEY_AUDIO_DESC':622, 'KEY_AUX':390, 'KEY_B':48, 'KEY_BACK':158, 'KEY_BACKSLASH':43, 'KEY_BACKSPACE':14, 'KEY_BASSBOOST':209, 'KEY_BATTERY':236, 'KEY_BLUE':401, 'KEY_BLUETOOTH':237, 'KEY_BOOKMARKS':156, 'KEY_BREAK':411, 'KEY_BRIGHTNESSDOWN':224, 'KEY_BRIGHTNESSUP':225, 'KEY_BRIGHTNESS_AUTO':244, 'KEY_BRIGHTNESS_CYCLE':243, 'KEY_BRIGHTNESS_MAX':593, 'KEY_BRIGHTNESS_MIN':592, 'KEY_BRIGHTNESS_TOGGLE':431, 'KEY_BRIGHTNESS_ZERO':244, 'KEY_BRL_DOT1':497, 'KEY_BRL_DOT10':506, 'KEY_BRL_DOT2':498, 'KEY_BRL_DOT3':499, 'KEY_BRL_DOT4':500, 'KEY_BRL_DOT5':501, 'KEY_BRL_DOT6':502, 'KEY_BRL_DOT7':503, 'KEY_BRL_DOT8':504, 'KEY_BRL_DOT9':505, 'KEY_BUTTONCONFIG':576, 'KEY_C':46, 'KEY_CALC':140, 'KEY_CALENDAR':397, 'KEY_CAMERA':212, 'KEY_CAMERA_DOWN':536, 'KEY_CAMERA_FOCUS':528, 'KEY_CAMERA_LEFT':537, 'KEY_CAMERA_RIGHT':538, 'KEY_CAMERA_UP':535, 'KEY_CAMERA_ZOOMIN':533, 'KEY_CAMERA_ZOOMOUT':534, 'KEY_CANCEL':223, 'KEY_CAPSLOCK':58, 'KEY_CD':383, 'KEY_CHANNEL':363, 'KEY_CHANNELDOWN':403, 'KEY_CHANNELUP':402, 'KEY_CHAT':216, 'KEY_CLEAR':355, 'KEY_CLOSE':206, 'KEY_CLOSECD':160, 'KEY_CNT':768, 'KEY_COFFEE':152, 'KEY_COMMA':51, 'KEY_COMPOSE':127, 'KEY_COMPUTER':157, 'KEY_CONFIG':171, 'KEY_CONNECT':218, 'KEY_CONTEXT_MENU':438, 'KEY_CONTROLPANEL':579, 'KEY_COPY':133, 'KEY_CUT':137, 'KEY_CYCLEWINDOWS':154, 'KEY_D':32, 'KEY_DASHBOARD':204, 'KEY_DATA':631, 'KEY_DATABASE':426, 'KEY_DELETE':111, 'KEY_DELETEFILE':146, 'KEY_DEL_EOL':448, 'KEY_DEL_EOS':449, 'KEY_DEL_LINE':451, 'KEY_DIGITS':413, 'KEY_DIRECTION':153, 'KEY_DIRECTORY':394, 'KEY_DISPLAYTOGGLE':431, 'KEY_DISPLAY_OFF':245, 'KEY_DOCUMENTS':235, 'KEY_DOLLAR':434, 'KEY_DOT':52, 'KEY_DOWN':108, 'KEY_DVD':389, 'KEY_E':18, 'KEY_EDIT':176, 'KEY_EDITOR':422, 'KEY_EJECTCD':161, 'KEY_EJECTCLOSECD':162, 'KEY_EMAIL':215, 'KEY_END':107, 'KEY_ENTER':28, 'KEY_EPG':365, 'KEY_EQUAL':13, 'KEY_ESC':1, 'KEY_EURO':435, 'KEY_EXIT':174, 'KEY_F':33, 'KEY_F1':59, 'KEY_F10':68, 'KEY_F11':87, 'KEY_F12':88, 'KEY_F13':183, 'KEY_F14':184, 'KEY_F15':185, 'KEY_F16':186, 'KEY_F17':187, 'KEY_F18':188, 'KEY_F19':189, 'KEY_F2':60, 'KEY_F20':190, 'KEY_F21':191, 'KEY_F22':192, 'KEY_F23':193, 'KEY_F24':194, 'KEY_F3':61, 'KEY_F4':62, 'KEY_F5':63, 'KEY_F6':64, 'KEY_F7':65, 'KEY_F8':66, 'KEY_F9':67, 'KEY_FASTFORWARD':208, 'KEY_FASTREVERSE':629, 'KEY_FAVORITES':364, 'KEY_FILE':144, 'KEY_FINANCE':219, 'KEY_FIND':136, 'KEY_FIRST':404, 'KEY_FN':464, 'KEY_FN_1':478, 'KEY_FN_2':479, 'KEY_FN_B':484, 'KEY_FN_D':480, 'KEY_FN_E':481, 'KEY_FN_ESC':465, 'KEY_FN_F':482, 'KEY_FN_F1':466, 'KEY_FN_F10':475, 'KEY_FN_F11':476, 'KEY_FN_F12':477, 'KEY_FN_F2':467, 'KEY_FN_F3':468, 'KEY_FN_F4':469, 'KEY_FN_F5':470, 'KEY_FN_F6':471, 'KEY_FN_F7':472, 'KEY_FN_F8':473, 'KEY_FN_F9':474, 'KEY_FN_S':483, 'KEY_FORWARD':159, 'KEY_FORWARDMAIL':233, 'KEY_FRAMEBACK':436, 'KEY_FRAMEFORWARD':437, 'KEY_FRONT':132, 'KEY_G':34, 'KEY_GAMES':417, 'KEY_GOTO':354, 'KEY_GRAPHICSEDITOR':424, 'KEY_GRAVE':41, 'KEY_GREEN':399, 'KEY_H':35, 'KEY_HANGEUL':122, 'KEY_HANGUEL':122, 'KEY_HANJA':123, 'KEY_HELP':138, 'KEY_HENKAN':92, 'KEY_HIRAGANA':91, 'KEY_HOME':102, 'KEY_HOMEPAGE':172, 'KEY_HP':211, 'KEY_I':23, 'KEY_IMAGES':442, 'KEY_INFO':358, 'KEY_INSERT':110, 'KEY_INS_LINE':450, 'KEY_ISO':170, 'KEY_J':36, 'KEY_JOURNAL':578, 'KEY_K':37, 'KEY_KATAKANA':90, 'KEY_KATAKANAHIRAGANA':93, 'KEY_KBDILLUMDOWN':229, 'KEY_KBDILLUMTOGGLE':228, 'KEY_KBDILLUMUP':230, 'KEY_KBDINPUTASSIST_ACCEPT':612, 'KEY_KBDINPUTASSIST_CANCEL':613, 'KEY_KBDINPUTASSIST_NEXT':609, 'KEY_KBDINPUTASSIST_NEXTGROUP':611, 'KEY_KBDINPUTASSIST_PREV':608, 'KEY_KBDINPUTASSIST_PREVGROUP':610, 'KEY_KEYBOARD':374, 'KEY_KP0':82, 'KEY_KP1':79, 'KEY_KP2':80, 'KEY_KP3':81, 'KEY_KP4':75, 'KEY_KP5':76, 'KEY_KP6':77, 'KEY_KP7':71, 'KEY_KP8':72, 'KEY_KP9':73, 'KEY_KPASTERISK':55, 'KEY_KPCOMMA':121, 'KEY_KPDOT':83, 'KEY_KPENTER':96, 'KEY_KPEQUAL':117, 'KEY_KPJPCOMMA':95, 'KEY_KPLEFTPAREN':179, 'KEY_KPMINUS':74, 'KEY_KPPLUS':78, 'KEY_KPPLUSMINUS':118, 'KEY_KPRIGHTPAREN':180, 'KEY_KPSLASH':98, 'KEY_L':38, 'KEY_LANGUAGE':368, 'KEY_LAST':405, 'KEY_LEFT':105, 'KEY_LEFTALT':56, 'KEY_LEFTBRACE':26, 'KEY_LEFTCTRL':29, 'KEY_LEFTMETA':125, 'KEY_LEFTSHIFT':42, 'KEY_LEFT_DOWN':617, 'KEY_LEFT_UP':616, 'KEY_LIGHTS_TOGGLE':542, 'KEY_LINEFEED':101, 'KEY_LIST':395, 'KEY_LOGOFF':433, 'KEY_M':50, 'KEY_MACRO':112, 'KEY_MAIL':155, 'KEY_MAX':767, 'KEY_MEDIA':226, 'KEY_MEDIA_REPEAT':439, 'KEY_MEDIA_TOP_MENU':619, 'KEY_MEMO':396, 'KEY_MENU':139, 'KEY_MESSENGER':430, 'KEY_MHP':367, 'KEY_MICMUTE':248, 'KEY_MINUS':12, 'KEY_MIN_INTERESTING':113, 'KEY_MODE':373, 'KEY_MOVE':175, 'KEY_MP3':391, 'KEY_MSDOS':151, 'KEY_MUHENKAN':94, 'KEY_MUTE':113, 'KEY_N':49, 'KEY_NEW':181, 'KEY_NEWS':427, 'KEY_NEXT':407, 'KEY_NEXTSONG':163, 'KEY_NEXT_FAVORITE':624, 'KEY_NUMERIC_0':512, 'KEY_NUMERIC_1':513, 'KEY_NUMERIC_11':620, 'KEY_NUMERIC_12':621, 'KEY_NUMERIC_2':514, 'KEY_NUMERIC_3':515, 'KEY_NUMERIC_4':516, 'KEY_NUMERIC_5':517, 'KEY_NUMERIC_6':518, 'KEY_NUMERIC_7':519, 'KEY_NUMERIC_8':520, 'KEY_NUMERIC_9':521, 'KEY_NUMERIC_A':524, 'KEY_NUMERIC_B':525, 'KEY_NUMERIC_C':526, 'KEY_NUMERIC_D':527, 'KEY_NUMERIC_POUND':523, 'KEY_NUMERIC_STAR':522, 'KEY_NUMLOCK':69, 'KEY_O':24, 'KEY_OK':352, 'KEY_ONSCREEN_KEYBOARD':632, 'KEY_OPEN':134, 'KEY_OPTION':357, 'KEY_P':25, 'KEY_PAGEDOWN':109, 'KEY_PAGEUP':104, 'KEY_PASTE':135, 'KEY_PAUSE':119, 'KEY_PAUSECD':201, 'KEY_PAUSE_RECORD':626, 'KEY_PC':376, 'KEY_PHONE':169, 'KEY_PLAY':207, 'KEY_PLAYCD':200, 'KEY_PLAYER':387, 'KEY_PLAYPAUSE':164, 'KEY_POWER':116, 'KEY_POWER2':356, 'KEY_PRESENTATION':425, 'KEY_PREVIOUS':412, 'KEY_PREVIOUSSONG':165, 'KEY_PRINT':210, 'KEY_PROG1':148, 'KEY_PROG2':149, 'KEY_PROG3':202, 'KEY_PROG4':203, 'KEY_PROGRAM':362, 'KEY_PROPS':130, 'KEY_PVR':366, 'KEY_Q':16, 'KEY_QUESTION':214, 'KEY_R':19, 'KEY_RADIO':385, 'KEY_RECORD':167, 'KEY_RED':398, 'KEY_REDO':182, 'KEY_REFRESH':173, 'KEY_REPLY':232, 'KEY_RESERVED':0, 'KEY_RESTART':408, 'KEY_REWIND':168, 'KEY_RFKILL':247, 'KEY_RIGHT':106, 'KEY_RIGHTALT':100, 'KEY_RIGHTBRACE':27, 'KEY_RIGHTCTRL':97, 'KEY_RIGHTMETA':126, 'KEY_RIGHTSHIFT':54, 'KEY_RIGHT_DOWN':615, 'KEY_RIGHT_UP':614, 'KEY_RO':89, 'KEY_ROOT_MENU':618, 'KEY_ROTATE_DISPLAY':153, 'KEY_S':31, 'KEY_SAT':381, 'KEY_SAT2':382, 'KEY_SAVE':234, 'KEY_SCALE':120, 'KEY_SCREEN':375, 'KEY_SCREENLOCK':152, 'KEY_SCREENSAVER':581, 'KEY_SCROLLDOWN':178, 'KEY_SCROLLLOCK':70, 'KEY_SCROLLUP':177, 'KEY_SEARCH':217, 'KEY_SELECT':353, 'KEY_SEMICOLON':39, 'KEY_SEND':231, 'KEY_SENDFILE':145, 'KEY_SETUP':141, 'KEY_SHOP':221, 'KEY_SHUFFLE':410, 'KEY_SLASH':53, 'KEY_SLEEP':142, 'KEY_SLOW':409, 'KEY_SLOWREVERSE':630, 'KEY_SOUND':213, 'KEY_SPACE':57, 'KEY_SPELLCHECK':432, 'KEY_SPORT':220, 'KEY_SPREADSHEET':423, 'KEY_STOP':128, 'KEY_STOPCD':166, 'KEY_STOP_RECORD':625, 'KEY_SUBTITLE':370, 'KEY_SUSPEND':205, 'KEY_SWITCHVIDEOMODE':227, 'KEY_SYSRQ':99, 'KEY_T':20, 'KEY_TAB':15, 'KEY_TAPE':384, 'KEY_TASKMANAGER':577, 'KEY_TEEN':414, 'KEY_TEXT':388, 'KEY_TIME':359, 'KEY_TITLE':369, 'KEY_TOUCHPAD_OFF':532, 'KEY_TOUCHPAD_ON':531, 'KEY_TOUCHPAD_TOGGLE':530, 'KEY_TUNER':386, 'KEY_TV':377, 'KEY_TV2':378, 'KEY_TWEN':415, 'KEY_U':22, 'KEY_UNDO':131, 'KEY_UNKNOWN':240, 'KEY_UNMUTE':628, 'KEY_UP':103, 'KEY_UWB':239, 'KEY_V':47, 'KEY_VCR':379, 'KEY_VCR2':380, 'KEY_VENDOR':360, 'KEY_VIDEO':393, 'KEY_VIDEOPHONE':416, 'KEY_VIDEO_NEXT':241, 'KEY_VIDEO_PREV':242, 'KEY_VOD':627, 'KEY_VOICECOMMAND':582, 'KEY_VOICEMAIL':428, 'KEY_VOLUMEDOWN':114, 'KEY_VOLUMEUP':115, 'KEY_W':17, 'KEY_WAKEUP':143, 'KEY_WIMAX':246, 'KEY_WLAN':238, 'KEY_WORDPROCESSOR':421, 'KEY_WPS_BUTTON':529, 'KEY_WWAN':246, 'KEY_WWW':150, 'KEY_X':45, 'KEY_XFER':147, 'KEY_Y':21, 'KEY_YELLOW':400, 'KEY_YEN':124, 'KEY_Z':44, 'KEY_ZENKAKUHANKAKU':85, 'KEY_ZOOM':372, 'KEY_ZOOMIN':418, 'KEY_ZOOMOUT':419, 'KEY_ZOOMRESET':420, 'REL_CNT':16, 'REL_DIAL':7, 'REL_HWHEEL':6, 'REL_MAX':15, 'REL_MISC':9, 'REL_RX':3, 'REL_RY':4, 'REL_RZ':5, 'REL_WHEEL':8, 'REL_X':0, 'REL_Y':1, 'REL_Z':2, }
codes = type("codes", (object,), codesDict)

nameToAxis = {"x":codes.ABS_X, "y":codes.ABS_Y, "z":codes.ABS_Z, "rx":codes.ABS_RX, "ry":codes.ABS_RY, "rz":codes.ABS_RZ, "rudder":codes.ABS_RUDDER, "throttle":codes.ABS_THROTTLE}
axisToName = {p[1]:p[0] for p in nameToAxis.items()}

nameToRelativeAxis = {"x":codes.REL_X, "y":codes.REL_Y, "z":codes.ABS_Z, "wheel":codes.REL_WHEEL}
relativeAxisToName = {p[1]:p[0] for p in nameToRelativeAxis.items()}


class ReloadException(Exception):
  pass

class CompositeJoystick:
  def move_axis(self, axis, v, relative):
    for c in self.children_:
      c.move_axis(axis, v, relative)

  def get_axis(self, axis):
    #TODO Come up with something better
    if len(self.children_):
      return self.children_[0].get_axis(axis)
    else:
      return 0.0

  def get_limits(self, axis):
    #TODO Come up with something better
    if len(self.children_):
      return self.children_[0].get_limits(axis)
    else:
      return (0.0, 0.0)

  def __init__(self, children):
    self.children_ = children


class Event(object):
  def __str__(self):
    return "type: {}, code: {}, value: {}, timestamp: {}".format(self.type, self.code, self.value, self.timestamp) 

  def __init__(self, type, code, value, timestamp=None):
    if timestamp is None:
      timestamp = time.time()
    self.type, self.code, self.value, self.timestamp = type, code, value, timestamp


class InputEvent(Event):
  def __str__(self):
    #TODO check whether it works in FreePie
    return super(InputEvent, self).__str__() + ", source: {}, modifiers: {}".format(self.source, self.modifiers)

  def __init__(self, type, code, value, timestamp, source, modifiers = None):
    super(InputEvent, self).__init__(type, code, value, timestamp)
    self.source = source 
    self.modifiers = () if modifiers is None else modifiers

  
class EventSource:
  def run_once(self):
    events =[]
    event = None
    for d in self.devices_:
      event = d.read_one()
      while event is not None:
        events.append(event)
        event = d.read_one()
    events.sort(key = lambda e : e.timestamp)
    for event in events:
      self.sink_(event)

  def run_loop(self):
    while True:
      t = time.time()
      self.run_once()
      t = time.time() - t
      time.sleep(max(self.step_ - t, 0))

  def __init__(self, devices, sink, step):
    self.devices_, self.sink_, self.step_ = devices, sink, step
    logger.debug("{} created".format(self))

  def __del__(self):
    logger.debug("{} destroyed".format(self))


def print_sink(event):
  print event
 

class MoveAxis:
  def __call__(self, event):
    assert(self.curve_ is not None)
    assert(self.j_ is not None)

    if event.type in (codes.EV_REL, codes.EV_ABS):  
      self.j_.move_axis(self.axis_, self.curve_.calc(event.value, event.timestamp), self.relative_)
      return True
    else:
      return False

  def __init__(self, j, axis, curve, relative):
    if curve is None:
      raise ArgumentError("Curve is None")
    if j is None:
      raise ArgumentError("Joystick is None")
    self.j_, self.axis_, self.curve_, self.relative_ = j, axis, curve, relative


class MoveCurve:
  def __call__(self, event):
    if self.curve_ is not None and event.type in (codes.EV_REL,):  
      try:
        self.curve_.move_by(event.value, event.timestamp)
      except Exception as e:
        logger.error("{}: exception in curve ({})".format(self, e))
        return False
      return True
    else:
      return False

  def __init__(self, curve):
    self.curve_ = curve


class SetAxis:
  def __init__(self, joystick, axis, value):
    self.js_, self.axis_, self.value_ = joystick, axis, value
    logger.debug("{} created".format(self))

  def __del__(self):
    logger.debug("{} destroyed".format(self))
  
  def __call__(self, event):
    self.js_.move_axis(self.axis_, self.value_, False) 


def SetAxes(joystick, axesAndValues):
  def op(event):
    for axis, value in axesAndValues:
      joystick.move_axis(axis, value, False) 
  return op


def SetCurveAxis(curve, value):
  def op(event):
    curve.get_axis().move(value, False) 
  def noneOp(event):
    pass
  return op if curve is not None else noneOp


def SetCurveAxis2(curve, value, relative=False, reset=False):
  def op(event):
    curve.move_axis(value, relative, reset)
  def noneOp(event):
    pass
  return op if curve is not None else noneOp


def SetCurvesAxes(*curvesAndValues):
  def op(event):
    for curve, value in curvesAndValues:
      if curve is not None: 
        curve.get_axis().move(value, False) 
  return op


def SetCurvesAxes2(curvesData):
  def op(event):
    for curve, value, relative, reset in curvesData:
      if curve is not None: 
        curve.move_axis(value, relative, reset) 
  return op
  
  
def ResetCurve(curve):
  def op(event):
    curve.reset()
  def noneOp(event):
    pass
  return op if curve is not None else noneOp


def ResetCurves(curves):
  def op(event):
    for curve in curves:
      if curve is not None: 
        curve.reset()
  return op


def SetButtonState(joystick, button, state):
  def op(event):
    joystick.set_button_state(button, state) 
    logger.debug(button, state)
  return op


class ClickSink:
  def __call__(self, event):
    if self.next_: 
      self.next_(event)

    numClicks = 0
    if event.type == codes.EV_KEY:
      numClicks = self.update_keys(event)
      if numClicks != 0:
        clickEvent = event
        clickEvent.value = 3
        clickEvent.num_clicks = numClicks
        if self.next_: 
          self.next_(clickEvent)

  #returns number of clicks
  def update_keys(self, event):
    if event.type == codes.EV_KEY:
      logger.debug("{} {}".format(event.code, event.value))
      if event.code in self.keys_:
        prevValue, prevTimestamp, prevNumClicks = self.keys_[event.code]
        dt = event.timestamp - prevTimestamp
        if event.value == 0 and prevValue > 0 and dt <= self.clickTime_:
          self.keys_[event.code][2] += 1
        elif event.value > 0 and prevValue == 0 and dt > self.clickTime_:
          self.keys_[event.code][2] = 0
        self.keys_[event.code][0] = event.value
        self.keys_[event.code][1] = event.timestamp
      else:
        self.keys_[event.code] = [event.value, event.timestamp, 0]
      return self.keys_[event.code][2]
    else:
      return 0

  def set_next(self, next):
    self.next_ = next
    return next

  def __init__(self, clickTime):
    self.next_, self.keys_, self.clickTime_ = None, {}, clickTime
    logger.debug("{} created".format(self))

  def __del__(self):
    logger.debug("{} destroyed".format(self))


class ModifierSink:
  def __call__(self, event):
    if event.type == codes.EV_KEY:
      if event.code in self.modifiers_:
        if event.value == 1 and event.code not in self.m_:
          self.m_.append(event.code)
        elif event.value == 0 and event.code in self.m_:
          self.m_.remove(event.code)

    if self.next_ and event.type in (codes.EV_KEY, codes.EV_REL, codes.EV_ABS):
      event.modifiers = self.m_ 
      self.next_(event)

  def set_next(self, next):
    self.next_ = next
    return next

  def __init__(self, next = None, modifiers = None):
    defmod = (codes.KEY_LEFTSHIFT, codes.KEY_RIGHTSHIFT, codes.KEY_LEFTCTRL, codes.KEY_RIGHTCTRL, codes.KEY_LEFTALT, codes.KEY_RIGHTALT)
    self.m_, self.next_, self.modifiers_ = [], next, defmod if modifiers is None else modifiers


class ModifierSink2:
  def __call__(self, event):
    if event.type == codes.EV_KEY:
      p = (event.source, event.code)
      if p in self.modifiers_:
        if event.value == 1 and p not in self.m_:
          self.m_.append(p)
        elif event.value == 0 and p in self.m_:
          self.m_.remove(p)

    if self.next_ and event.type in (codes.EV_KEY, codes.EV_REL, codes.EV_ABS):
      event.modifiers = self.m_ 
      self.next_(event)

  def set_next(self, next):
    self.next_ = next
    return next

  def __init__(self, next = None, source = None, modifiers = None):
    defMod = [codes.KEY_LEFTSHIFT, codes.KEY_RIGHTSHIFT, codes.KEY_LEFTCTRL, codes.KEY_RIGHTCTRL, codes.KEY_LEFTALT, codes.KEY_RIGHTALT]
    self.m_, self.next_, self.modifiers_ = [], next, [(source,m) for m in defMod] if modifiers is None else modifiers


class ScaleSink:
  def __call__(self, event):
    if event.type == codes.EV_REL:
      event.value *= 1.0 if self.sens_ is None else self.sens_.get(event.code, 1.0)
    return self.next_(event) if self.next_ is not None else False

  def set_next(self, next):
    self.next_ = next
    return next

  def __init__(self, sens):
    self.next_, self.sens_ = None, sens


#TODO Figure out how to match events from any source
class ScaleSink2:
  def __call__(self, event):
    if event.type in (codes.EV_REL, codes.EV_ABS):
      event.value *= 1.0 if self.sens_ is None else self.sens_.get(self.keyOp_(event), 1.0)
    return self.next_(event) if self.next_ is not None else False

  def set_next(self, next):
    self.next_ = next
    return next

  def __init__(self, sens, keyOp = lambda event : event.code):
    self.next_, self.sens_, self.keyOp_ = None, sens, keyOp


class Binding:
  def __call__(self, event):
    if self.dirty_ == True:
      self.children_.sort(key=lambda c : c[1])
      self.dirty_ = False

    if len(self.children_) == 0:
      return

    assert(self.cmp_)
    level, processed = self.children_[0][1], False
    for c in self.children_:
      if c[1] > level:
        if processed == True:
          return
        else:
          level = c[1]
      for attrName, attrValue in c[0]:
         if hasattr(event, attrName):
            if not self.cmp_(attrName, getattr(event, attrName), attrValue):
              break
         else:
          break
      else:
        if c[2] is not None: 
          #logger.debug("Processing event {}".format(str(event)))
          for cc in c[2]:
            #logger.debug("Sending event {} to {}".format(str(event), cc))
            processed = cc(event) or processed

  def add(self, attrs, child, level = 0):
    logger.debug("{}: Adding child {} to {} for level {}".format(self, child, attrs, level))
    c = next((x for x in self.children_ if level == x[1] and attrs == x[0]), None)
    if c is not None:
      c[2].append(child)
    else:
      self.children_.append([attrs, level, [child]])
    self.dirty_ = True
    return child

  def add_several(self, attrs, childSeq, level = 0):
    for a in attrs:
      c = next((x for x in self.children_ if level == x[1] and a == x[0]), None)
      if c is not None:
        assert(isinstance(c[2], list))
        c[2] += childSeq
      else:
        self.children_.append([a, level, [cc for cc in childSeq]])
    self.dirty_ = True
    return childSeq

  def clear(self):
    del self.children_[:]

  def __init__(self, cmp = lambda a, b, c : b == c, children = None):
    if children is None:
      children = []
    self.children_ = children 
    self.cmp_ = cmp
    self.dirty_ = True
    logger.debug("{} created".format(self))

  def __del__(self):
    logger.debug("{} destroyed".format(self))


class CmpWithModifiers:
  def __call__(self, name, eventValue, attrValue):
    r = True
    if name == "modifiers":
      if attrValue is None:
        r = eventValue is None
      elif eventValue is None:
        r = False
      elif len(attrValue) != len(eventValue):
        r = False
      else:
        r = True
        for m in attrValue:
          r = r and (m in eventValue)
    else:
      r = eventValue == attrValue
    return r


class CmpWithModifiers2:
  def __call__(self, name, eventValue, attrValue):
    r = True
    if name == "modifiers":
      if attrValue is None:
        r = eventValue is None
      elif eventValue is None:
        r = False
      elif len(attrValue) == 0 and len(eventValue) == 0:
        r = True
      elif len(attrValue) != len(eventValue):
        r = False
      else:
        r = True
        for m in attrValue:
          found = False
          for n in eventValue:
            assert(len(m) == 2)
            assert(len(n) == 2)
            found = (m[1] == n[1]) if m[0] is None else (m == n)
            if found: break
          r = r and found
          if not r: break
    else:
      r = eventValue == attrValue
    return r


class ED:
  @staticmethod
  def move(axis, modifiers = None):
    r = (("type", codes.EV_REL), ("code", axis))
    if modifiers is not None:
      r = r + (("modifiers", modifiers),)
    return r

  @staticmethod
  def move_to(axis, modifiers = None):
    r = (("type", codes.EV_ABS), ("code", axis))
    if modifiers is not None:
      r = r + (("modifiers", modifiers),)
    return r

  @staticmethod
  def press(key, modifiers = None):
    r  = (("type", codes.EV_KEY), ("code", key), ("value", 1))
    if modifiers is not None:
      r = r + (("modifiers", modifiers),)
    return r

  @staticmethod
  def release(key, modifiers = None):
    r = (("type", codes.EV_KEY), ("code", key), ("value", 0))
    if modifiers is not None:
      r = r + (("modifiers", modifiers),)
    return r

  @staticmethod
  def click(key, modifiers = None):
    r = (("type", codes.EV_KEY), ("code", key), ("value", 3), ("num_clicks", 1))
    if modifiers is not None:
      r = r + (("modifiers", modifiers),)
    return r

  @staticmethod
  def doubleclick(key, modifiers = None):
    r = (("type", codes.EV_KEY), ("code", key), ("value", 3), ("num_clicks", 2))
    if modifiers is not None:
      r = r + (("modifiers", modifiers),)
    return r

  @staticmethod
  def multiclick(key, n, modifiers = None):
    r = (("type", codes.EV_KEY), ("code", key), ("value", 3), ("num_clicks", n))
    if modifiers is not None:
      r = r + (("modifiers", modifiers),)
    return r

  @staticmethod
  def bcast():
    return (("type", EV_BCAST),)

  @staticmethod
  def init(i):
    return (("type", EV_BCAST), ("code", BC_INIT), ("value", i))

  @staticmethod
  def any():
    return ()


class ED2:
  @staticmethod
  def move(source, axis, modifiers = None):
    r = (("source", source), ("type", codes.EV_REL), ("code", axis))
    if modifiers is not None:
      r = r + (("modifiers", modifiers),)
    return r

  @staticmethod
  def move_to(source, axis, modifiers = None):
    r = (("source", source), ("type", codes.EV_ABS), ("code", axis))
    if modifiers is not None:
      r = r + (("modifiers", modifiers),)
    return r

  @staticmethod
  def press(source, key, modifiers = None):
    r  = (("source", source), ("type", codes.EV_KEY), ("code", key), ("value", 1))
    if modifiers is not None:
      r = r + (("modifiers", modifiers),)
    return r

  @staticmethod
  def release(source, key, modifiers = None):
    r = (("source", source), ("type", codes.EV_KEY), ("code", key), ("value", 0))
    if modifiers is not None:
      r = r + (("modifiers", modifiers),)
    return r

  @staticmethod
  def click(source, key, modifiers = None):
    r = (("source", source), ("type", codes.EV_KEY), ("code", key), ("value", 3), ("num_clicks", 1))
    if modifiers is not None:
      r = r + (("modifiers", modifiers),)
    return r

  @staticmethod
  def doubleclick(source, key, modifiers = None):
    r = (("source", source), ("type", codes.EV_KEY), ("code", key), ("value", 3), ("num_clicks", 2))
    if modifiers is not None:
      r = r + (("modifiers", modifiers),)
    return r

  @staticmethod
  def multiclick(source, key, n, modifiers = None):
    r = (("source", source), ("type", codes.EV_KEY), ("code", key), ("value", 3), ("num_clicks", n))
    if modifiers is not None:
      r = r + (("modifiers", modifiers),)
    return r

  @staticmethod
  def bcast():
    return (("type", EV_BCAST),)

  @staticmethod
  def init(i):
    return (("type", EV_BCAST), ("code", BC_INIT), ("value", i))

  @staticmethod
  def any():
    return ()


class ED3:
  inputActionRe = re.compile("([^ ]*) *\( *([^\., ]*?)\.?([^\., ]*) *,? *([^\., ]*) *\)")
  sourceRe = re.compile("(.*)\.(.*)")

  @staticmethod
  def parse(s):
    tokens = s.split("+")
    r, modifiers = [], None
    for t in tokens:
      m = ED3.inputActionRe.match(t)
      if m is not None:
        action, source, inpt, num  = m.groups()
        if action == "any":
          pass
        elif action == "init":
          r += [("type", EV_BCAST), ("code", BC_INIT), ("value", int(inpt))]
        else:
          if source != "":
            r.append(("source", source))
          r.append(("code", codesDict[inpt]))
          if action == "press":
            r += [("type", codes.EV_KEY), ("value", 1)]
          elif action == "release":
            r += [("type", codes.EV_KEY), ("value", 0)]
          elif action == "click":
            r += [("type", codes.EV_KEY), ("value", 3), ("num_clicks", 1)]
          elif action == "doubleclick":
            r += [("type", codes.EV_KEY), ("value", 3), ("num_clicks", 2)]
          elif action == "multiclick":
            r += [("type", codes.EV_KEY), ("value", 3), ("num_clicks", int(num))]
          elif action == "move":
            r += [("type", codes.EV_REL)]
          elif action == "move_to":
            r += [("type", codes.EV_ABS)]
      else:
        if modifiers is None:
          modifiers = []
        if t != "":
          m2 = ED3.sourceRe.match(t)
          source, inpt = None, None
          if m2 is not None:
            source, inpt = m2.group(1), m2.group(2)
          else:
            inpt = t
          modifiers.append((source, codesDict[inpt]))
    if modifiers is not None:
      r.append(("modifiers", modifiers))
    logger.debug("ED3.parse(): {} -> {}".format(s, r)) 
    return r


class StateSink:
 def __call__(self, event):
   logger.debug("{}: got event: {}, state: {}, next: {}".format(self, event, self.state_, self.next_))
   if (self.state_ == True) and (self.next_ is not None):
     self.next_(event)

 def set_state(self, state):
   logger.debug("{}: setting state to {}".format(self, state))
   self.state_ = state
   if self.next_:
     self.next_(Event(EV_BCAST, BC_INIT, 1 if state == True else 0, time.time()))

 def get_state(self):
   return self.state_

 def set_next(self, next):
    self.next_ = next
    return next

 def __init__(self):
   self.next_ = None
   self.state_ = False


def SetState(stateSink, state):
  def op(event):
    stateSink.set_state(state)
  return op
    
    
class ModeSink:
  def __call__(self, event):
    child = self.children_.get(self.mode_, None)
    if child is not None:
      return child(event)

  def set_mode(self, mode):
    logger.debug("{}: Setting mode: {}".format(self, mode))
    if mode not in self.children_:
      logger.debug("{}: No such mode: {}".format(self, mode))
      return False
    self.set_active_child_state_(False)
    self.mode_ = mode
    self.set_active_child_state_(True)

  def get_mode(self):
    return self.mode_

  def add(self, mode, child):
    logger.debug("{}: Adding child {} to  mode {}".format(self, child, mode))
    self.children_[mode] = child
    return child

  def set_active_child_state_(self, state):
    if self.mode_ in self.children_:
      child = self.children_.get(self.mode_, None)
      if child is not None:
        logger.debug("{}: Notifying child {} about setting state to {}".format(self, child, state))
        child(Event(EV_BCAST, BC_INIT, 1 if state == True else 0, time.time()))
    
  def __init__(self):
    self.children_, self.mode_ = {}, None


class CycleMode:
  def __call__(self, event):
    self.i += 1
    if self.i >= len(self.modes):
      self.i = 0
    self.modeSink.set_mode(self.modes[self.i])
  def __init__(self, modeSink, modes):
    self.i, self.modeSink, self.modes = 0, modeSink, modes


class SetMode:
  def __call__(self, event):
    self.modeSink.set_mode(self.mode)
  def __init__(self, modeSink, mode):
    self.modeSink, self.mode = modeSink, mode


class ConstantCurve:
  def calc(self, v, t):
    return self.n
  def reset(self):
    pass
  def __init__(self, n):
    self.n = n


class ProportionalCurve:
  def calc(self, v, t):
    return self.k*v
  def reset(self):
    pass
  def __init__(self, k):
    self.k = k


class PowerCurve:
  def calc(self, v, t):
    return sign(v)*self.k*abs(v)**self.n
  def reset(self):
    pass
  def __init__(self, k, n):
    self.k, self.n = k, n


class PowerApproximator:
  def __call__(self, v):
    return sign(v)*self.k*abs(v)**self.n

  def __init__(self, k, n):
    self.k, self.n = k, n


class PolynomialApproximator:
  def __call__(self, v):
    v += self.off_
    r = 0.0
    for i in range(0, len(self.coeffs_)):
      r += self.coeffs_[i]*v**i
    return r

  def __init__(self, coeffs, off=0.0):
    self.coeffs_, self.off_ = coeffs, off

    
class SegmentApproximator:
  def __call__(self, x):
    if len(self.x_) == 0 or len(self.y_) == 0:
      return 0.0
    i = bisect.bisect_left(self.x_, x)-1
    i = clamp(i, 0, max(len(self.x_)-2, 0))
    j = clamp(i+1, 0, max(len(self.x_)-1, 0))
    dy, dx = self.y_[j] - self.y_[i], self.x_[j] - self.x_[i]
    if dx == 0.0:
      raise ArithmeticError("Zero argument delta")
    y = 0.0
    if x < self.x_[0] and self.clampLeft_:
      y = self.y_[0]
    elif x > self.x_[len(self.x_)-1] and self.clampRight_:
      y = self.y_[len(self.y_)-1]
    else:
      y = self.y_[i] + dy*((x - self.x_[i])/dx)**self.factor_
    return y

  def __init__(self, data, factor=1.0, clampLeft=False, clampRight=False):
    temp = [(float(d[0]), float(d[1])) for d in data if len(d) == 2]
    temp.sort(key = lambda d : d[0])
    if len(temp) == 0:
      self.x_, self.y_ = (), ()
    else:
      self.x_, self.y_ = zip(*temp)
    self.factor_ = factor
    self.clampLeft_, self.clampRight_ = clampLeft, clampRight


class SigmoidApproximator:
  def __call__(self, x):
    x = self.k_*x + self.b_
    ex = math.e**x
    return self.c_*ex/(ex + 1) + self.d_

  def __init__(self, k, b, c, d):
    self.k_, self.b_, self.c_, self.d_ = k, b, c, d


class DirectionBasedCurve:
  """Converts input to output based on coefficient that depends on previous input behaviour.
     Changes coefficient when input changes sign. Restores coefficient in steps if input does not change sign.
  """
  def calc(self, x, timestamp):
    s = sign(x)
    dirChanged = self.s_ != 0 and s != self.s_
    self.s_ = s

    if dirChanged:
      lowest = len(self.levels_) - 1
      self.level_ = lowest if self.dropToLowest_ else min(self.level_+1, lowest)
      self.distance_ = 0
    else:
      self.distance_ += abs(x)
      if self.distance_ > self.levels_[self.level_][0]:
        self.level_ = max(self.level_-1, 0)
        self.distance_ = 0

    k = self.levels_[self.level_][1]
    value = x*k

    logger.debug("level={} distance={: .3f} x={: .3f} k={: .3f} value={: .3f}".format(self.level_, self.distance_, x, k, value))

    return value

  def reset(self):
    self.s_, self.distance_, self.level_ = 0, 0, 0

  def __init__(self, levels, dropToLowest=False):
    """ levels = sequence of pairs (levelCoeff, levelDistance)
        levelCoeff - conversion coeff for given level
        levelDistance - distance input must travel before curve increases level 
    """
    self.s_, self.distance_, self.level_, self.levels_, self.dropToLowest_ = 0, 0, 0, levels, dropToLowest


class DirectionBasedCurve3:
  """Using approximator to compute sensitivity based on distance."""
  def calc(self, x, timestamp):
    s = sign(x)
    if self.s_ == 0:
      self.distance_ = -s*self.startingDistance_
    dirChanged = self.s_ != 0 and s != self.s_
    self.s_ = s

    if dirChanged:
      self.distance_ = self.distanceOp_(self.distance_)

    self.distance_ += x

    k = self.approx_(abs(self.distance_))
    delta = k*x
    logger.debug("{}: distance={: .3f} x={: .3f} k={: .3f} delta={: .3f}".format(self, self.distance_, x, k, delta))

    return delta

  def reset(self):
    self.s_ = 0

  def __init__(self, approx, distanceOp=lambda x : 0.0, startingDistance=0.0):
    self.distance_, self.s_, self.approx_, self.distanceOp_, self.startingDistance_ = startingDistance, 0, approx, distanceOp, startingDistance


class DistanceBasedCurve:
  def calc(self, x, timestamp):
    distance = self.distance_ + x
    value = sign(distance)*self.approx_(abs(distance))
    delta = 0.0
    if abs(value) < self.limit_:
      self.distance_ = distance
      delta = value - self.value_
      self.value_ = value

    logger.debug(self.distance_, self.value_)
    return delta

  def reset(self):
    self.distance_, self.value_ = 0.0, 0.0

  def __init__(self, approx, limit):
    """limit is output limit"""
    assert(approx)
    self.distance_, self.value_, self.approx_, self.limit_ = 0.0, 0.0, approx, limit


class FixedValuePoint:
  def __call__(self, value):
    return None if value is None else (self.op_(value - self.fixedValue_), self.fixedValue_)

  def __init__(self, op, fixedValue):
    self.op_ = op
    self.fixedValue_ = fixedValue


class MovingValuePoint:
  def __call__(self, value):
    if value is None:
      self.s_, self.tempValue_, self.value_ = 0, 0.0, None
      return None
    else:
      s = sign(value - self.tempValue_)
      logger.debug("{}: prev: {: .3f}; current: {: .3f}; s: {}".format(self, self.tempValue_, value, s))
      self.tempValue_ = value
      if self.s_ != 0 and s != self.s_:
        v = value if self.value_ is None else self.valueOp_(self.value_, value)
        logger.debug("{}: old reference value: {}; new reference value: {}".format(self, self.value_, v))
        self.value_ = v
      self.s_ = s
      return None if self.value_ is None else (self.deltaOp_(value - self.value_), self.value_)

  def __init__(self, deltaOp, valueOp = lambda old,new : 0.5*old+0.5*new):
    assert(deltaOp)
    assert(valueOp)
    self.deltaOp_, self.valueOp_ = deltaOp, valueOp
    self.s_, self.tempValue_, self.value_ = 0, 0.0, None


class ValuePointOp:
  def __call__(self, value):
    left, right = None, None
    for vp in self.vps_:
      p = vp(value) #p is (result, value)
      if p is None or value is None:
        continue
      delta = value - p[1]
      s = sign(delta)
      delta = abs(delta)
      if s == 1:
        if left is None or delta < left[1]: 
          left = (p[0], delta) #left and right are (result, delta)
      else:
        if right is None or delta < right[1]: 
          right = (p[0], delta)

    r = None
    if left is None and right is None:
      r = None
    elif left is not None and right is not None:
      leftDelta, rightDelta = left[1], right[1] #absolute values of deltas
      totalDelta = leftDelta + rightDelta
      #interpolating (sort of)
      #left value is multiplied by right fraction of deltas sum and vice versa
      r = rightDelta/totalDelta*left[0] + leftDelta/totalDelta*right[0] 
    else:
      r = (left if right is None else right)[0]
      logger.debug("{}: left: {}, right: {}, result: {}".format(self, left, right, r))
    return r

  def __init__(self, vps):
    self.vps_ = vps


class Axis:
  def move(self, v, relative):
    assert(self.j_)
    return self.j_.move_axis(self.a_, v, relative)

  def get(self):
    assert(self.j_)
    return self.j_.get_axis(self.a_)

  def limits(self):
    """Returns (-limit, limit)"""
    assert(self.j_)
    return self.j_.get_limits(self.a_)

  def __init__(self, j, a):
    assert(j)
    self.j_, self.a_ = j, a


class ValueOpDeltaAxisCurve:
  def move_by(self, x, timestamp):
    assert(self.axis_ is not None)
    assert(self.valueOp_ is not None)
    assert(self.deltaOp_ is not None)
    #self.valueOp_ typically returns sensitivity based on current self.value_
    #self.deltaOp_ typically multiplies sensitivity by x (input delta) to produce output delta
    value, limits = self.axis_.get(), self.axis_.limits()
    baseValue = value
    for xx in (0.01*x, 0.99*x):
      factor = self.valueOp_(value)
      if factor is None:
        raise ArithmeticError("Cannot compute value, factor is None")
      value += self.deltaOp_(xx, factor)
      value = clamp(value, *limits)
      logger.debug("{}: xx: {: .4f}; value: {: .4f}".format(self, xx, value))
    delta = value - baseValue
    self.axis_.move(delta, True)
    return delta

  def reset(self):
    logger.debug("{}: resetting".format(self))
    assert(self.valueOp_ is not None)
    self.valueOp_(None)
    #TODO Should also call self.deltaOp_?

  def get_axis(self):
    return self.axis_

  def move_axis(self, value, relative=True, reset=True):
    self.axis_.move(value, relative)
    if reset:
      self.reset()

  #TODO Not needed since can return axis?
  def set_value(self, value):
    """Sets value directly to axis and optionally resets itself."""
    assert(self.axis_ is not None)
    if value == clamp(value, *self.axis_.limits()):
      self.axis_.move(value, False)
    else:
      raise ArgumentError("Value {} out of limits {}".format(value, self.axis_.limits()))
    if self.shouldReset_:
      self.reset()

  def __init__(self, deltaOp, valueOp, axis, shouldReset=False):
    assert(deltaOp)
    assert(valueOp)
    assert(axis)
    self.deltaOp_, self.valueOp_, self.axis_, self.shouldReset_ = deltaOp, valueOp, axis, shouldReset


class SpeedBasedCurve:
  def calc(self, x, timestamp):
    assert(self.approx_ is not None)

    dt = timestamp - self.timestamp_
    self.timestamp_ = timestamp
    if dt == 0.0:
      return 0.0

    s = sign(x)
    dirChanged = s != self.s_
    self.s_ = s

    x = float(x)
    if self.symmetric_ == True:
      x = abs(x)
    else:
      s = 1

    speed = x/dt
    logger.debug(speed)
    if self.filter_:
      if dirChanged or dt > self.resetTime_:
        self.filter_.reset()
      speed = self.filter_.process(speed)
    k = self.approx_(speed)
    y = s*k*x
    logger.debug("{:+04.3f} {:0.3f} {:0.3f} {:0.3f}".format(x, speed, k, y))

    return y

  def reset(self):
    logger.debug("Resetting")
    if self.filter_:
      self.filter_.reset()

  def __init__(self, approx, filtr = None, resetTime = 2.0, symmetric = True):
    if approx is None:
      raise ArgumentError("Approximator is None")
    self.approx_ = approx
    self.filter_ = filtr
    self.resetTime_ = resetTime
    self.symmetric_ = symmetric
    self.timestamp_ = 0.0
    self.s_ = 0


class EmaFilter:
  def process(self, v):
    if self.needInit_:
      self.needInit_ = False
      self.v_ = v
      return v
    else:
      self.v_ += self.a_*(v - self.v_)
      return self.v_

  def reset(self):
    self.needInit_ = True

  def __init__(self, a):
    self.a_ = a
    self.v_, self.needInit_ = 0.0, True


class DemaFilter:
  def process(self, v):
    if self.needInit_:
      self.needInit_ = False
      self.v_, self.t_  = v, 0.0
      return v
    else:
      self.v_ = self.a_*v + (1.0 - self.a_)*(self.v_ + self.t_)
      self.t_ = self.b_*(self.v_ - v) + (1.0 - self.b_)*self.t_
      return self.v_

  def reset(self):
    self.needInit_ = True

  def __init__(self, a, b):
    self.a_, self.b_  = a, b
    self.v_, self.t_, self.needInit_ = 0.0, 0.0,  True


class ToggleSink:
  def __call__(self, event):
    self.sink_.set_state(not self.sink_.get_state())
    return True
  def __init__(self, sink):
    self.sink_ = sink


class DeviceGrabberSink:
  def __call__(self, event):
    if self.state_:
      self.device_.swallow(False)
      self.state_ = False
    else:
      self.device_.swallow(True)
      self.state_ = True 
    return True

  def __init__(self, device):
    self.device_, self.state_ = device, False


class Opentrack:
  """Opentrack head movement emulator. Don't forget to call send()!"""

  def move_axis(self, axis, v, relative = True):
    if axis not in self.axes_:
      return
    v = self.v_[axis]+v if relative else v 
    self.v_[axis] = clamp(v, -1.0, 1.0)
    self.dirty_ = True

  def get_axis(self, axis):
    return self.v_[axis]

  def send(self):
    if self.dirty_ == True:
      self.dirty_ == False
      x, y, z = (self.v_[x] for x in self.axes_[0:3])
      yaw, pitch, roll = 180.0*self.v_[self.axes_[3]], 90.0*self.v_[self.axes_[4]], 90.0*self.v_[self.axes_[5]] 
      packet = struct.pack("dddddd", x, y, z, yaw, pitch, roll)
      self.socket_.sendto(packet, (self.ip_, self.port_))

  def __init__(self, ip, port):
    self.dirty_ = False
    self.socket_ = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    self.ip_, self.port_ = ip, port
    self.v_ = {a:0.0 for a in self.axes_}

  axes_ = (codes.ABS_X, codes.ABS_Y, codes.ABS_Z, codes.ABS_RY, codes.ABS_RX, codes.ABS_RZ)


class SnapManager:
  """Sets joystick axes to preset values and also can update preset values from joystick"""

  def set_snap(self, i, l):
    self.snaps_[i] = [[p[0], p[1]] for p in l]

  def update_snap(self, i):
    logger.debug("update_snap({})".format(i))
    snap = self.snaps_[i]
    for j in xrange(len(snap)):
      snap[j][1] = self.joystick_.get_axis(snap[j][0])
       
  def snap_to(self, i):
    logger.debug("snap_to({})".format(i))
    snap = self.snaps_[i]
    for p in snap:
      self.joystick_.move_axis(p[0], p[1], self.relative_)

  def __init__(self, joystick, relative):
    self.snaps_, self.joystick_, self.relative_ = dict(), joystick, relative


class AxisSnapManager:
  """Axis-based snap manager"""
  def set_snap(self, i, l):
    self.snaps_[i] = [[p[0], p[1]] for p in l]

  def update_snap(self, i):
    logger.debug("{}: updating snap {}".format(self, i))
    snap = self.snaps_.get(i, None)
    if snap is None:
      logger.debug("{}: no snap {}".format(self, i))
    else:
      for p in snap:
        p[1] = p[0].get()
       
  def snap_to(self, i):
    logger.debug("{}: snapping to {}".format(self, i))
    snap = self.snaps_.get(i, None)
    if snap is None:
      logger.debug("{}: no snap {}".format(self, i))
    else:
      for p in snap:
        p[0].move(p[1], self.relative_)

  def __init__(self, relative):
    self.snaps_, self.relative_ = dict(), relative


class CurveSnapManager:
  """Supports only non-relative snaps."""
  def set_snap(self, i, snapData):
    class Snap:
      pass
    self.snaps_[i] = []
    for sd in snapData:
      s = Snap()
      s.axisId, s.value, s.reset = sd
      self.snaps_[i].append(s)

  def update_snap(self, i):
    logger.debug("{}: updating snap {}".format(self, i))
    data = self.snaps_.get(i, None)
    if data is None:
      logger.debug("{}: no snap {}".format(self, i))
    else:
      for s in data:
        curve = self.curves_.get(s.axisId, None)
        if curve is None:
          logger.debug("{}: snap {}: no curve for axis {}".format(self, i, s.axisId))
          continue
        axis = curve.get_axis()
        if axis is None:
          logger.debug("{}: snap {}: no axis in curve for {}".format(self, i, s.axisId))
          continue
        s.value = axis.get()
       
  def snap_to(self, i):
    logger.debug("{}: snapping to {}".format(self, i))
    data = self.snaps_.get(i, None)
    if data is None:
      logger.debug("{}: no snap {}".format(self, i))
    else:
      for s in data:
        curve = self.curves_.get(s.axisId, None)
        if curve is None:
          logger.debug("{}: snap {}: no curve for axis {}".format(self, i, s.axisId))
          continue
        curve.move_axis(value=s.value, relative=False, reset=s.reset)

  def set_curve(self, axisId, curve):
    self.curves_[axisId] = curve

  def get_curve(self, axisId):
    return self.curves_.get(axisId, None)

  def __init__(self):
    self.snaps_, self.curves_ = dict(), dict()


def SetCurves(curveSnapManager, data):
  def op(event):
    for axisId, curve in data:
      curveSnapManager.set_curve(axisId, curve) 
  return op


def SnapTo(snapManager, snap):
  def op(e):
    return snapManager.snap_to(snap)
  return op


def UpdateSnap(snapManager, snap):
  def op(e):
    return snapManager.update_snap(snap)
  return op


class MappingJoystick:
  """Forwards calls to contained joysticks with axis mapping"""

  def move_axis(self, axis, value, relative):
    d = self.data_[axis]
    d[0].move_axis(d[1], value, relative)

  def get_axis(self, axis):
    d = self.data_[axis]
    return d[0].get_axis(d[1])

  def get_limits(self, axis):
    d = self.data_[axis]
    return d[0].get_limits(d[1])
    
  def add(self, axis, joystick, joyAxis):
    self.data_[axis] = (joysitick, joyAxis)

  def __init__(self, initData = None):
    self.data_ = dict()
    if initData is not None:
      for d in initData:
        self.data_[d[0]] = (d[1], d[2])


class NodeJoystick(object):
  def move_axis(self, axis, value, relative):
    if self.next_ is not None:
      self.next_.move_axis(axis, value, relative)

  def get_axis(self, axis):
    return self.next_.get_axis(axis) if self.next_ else 0

  def get_limits(self, axis):
    return self.next_.get_limits(axis) if self.next_ else (0.0, 0.0)

  def set_button_state(self, button, state):
    self.next_.set_button_state(button, state)

  def set_next(self, next):
    self.next_ = next
    return next

  def __init__(self, next=None):
    self.next_ = next


class NotifyingJoystick(NodeJoystick):
  def move_axis(self, axis, value, relative):
    super(NotifyingJoystick, self).move_axis(axis, value, relative)
    if not relative and self.sink_() is not None:
      self.sink_()(Event(codes.EV_ABS, axis, value, time.time()))

  def set_sink(self, sink):
    self.sink_ = weakref.ref(sink)
    return sink

  def __init__(self, sink=None, next=None):
    super(NotifyingJoystick, self).__init__(next)
    if sink is not None: self.sink_ = weakref.ref(sink)


class MetricsJoystick:
  def move_axis(self, axis, value, relative):
    if axis not in self.data_:
      self.data_[axis] = [0.0, None, 0.0]
    if relative:
      self.data_[axis][0] += value
    else:
      self.data_[axis][0] = value

  def get_axis(self, axis):
    return self.data_.get(axis, 0.0)[0]

  def get_limits(self, axis):
    return (-1.0, 1.0)

  def check(self):
    for a in self.data_:
      d = self.data_[a]
      if d[1] is None:
        continue
      error = abs(d[0] - d[1])
      d[2] = 0.5*error + 0.5*d[2]
      print("{}: {: .3f} {: .3f}".format(axisToName[a], error, d[2]))
        
  def reset(self):
    for a in self.data_:
      d = self.data_[a]
      if d[1] is None:
        continue
      d[0],d[2] = d[1],0.0
    
  def set_target(self, axis, target):
    if axis not in self.data_:
      self.data_[axis] = [0.0, None, 0.0]
    self.data_[axis][1] = target

  def __init__(self):
    self.data_ = dict()


def make_curve_makers():
  def CurveAdapter(curveMaker):
    class AdaptingCurve:
      def move_by(self, x, timestamp):
        self.a_.move(self.c_.calc(x, timestamp), True)
      def reset(self):
        self.c_.reset()
      def set_value(self, value):
        self.a_.move(value, False)
        self.c_reset()
      def __init__(self, calcCurve, axis):
        self.c_, self.a_ = calcCurve, axis
      
    def op(data):
      curves = curveMaker(data)
      for mode in curves:
        md = curves[mode]
        for axis in md:
          md[axis] = AdaptingCurve(md[axis], data["axes"][axis])
      return curves

    return op

  curves = {}

  def make_speed_curves(data):
    resetTime = 0.5
    alpha = 0.5
    beta = 0.5
    stepData = [(0, 0.0), (100, 0.001), (1000, 0.005), (3000, 0.01), (5000, 0.01)]
    stepX = SpeedBasedCurve(SigmoidApproximator(12.0/3000, -6.0, 0.01), EmaFilter(alpha), resetTime)
    stepY = SpeedBasedCurve(SegmentApproximator(stepData), EmaFilter(alpha), resetTime)
    stepDataZ = [(0, 0.0), (10, 0.001), (20, 0.005), (50, 0.01), (100, 0.1), (200, 0.1)]
    stepZ = ProportionalCurve(0.001)
    curves = {codes.ABS_X:stepX, codes.ABS_Y:stepY, codes.ABS_Z:stepZ}
    return curves

  curves["speed"] = CurveAdapter(make_speed_curves)


  def make_dir_curves2(data):
    #dataX = [(0.0,0.2), (0.1,0.1), (0.3,0.1), (0.95,1.0), (1.0, 1.0)]
    #dataX = [(0.0,0.1), (0.2,0.1), (0.95,1.0), (1.0, 1.0)]
    #dataX = [(0.0,0.2), (0.5,0.0), (0.99,1.0), (1.0, 1.0)]
    #dataX = [(0.0,0.05), (0.1,0.05), (1.45,1.0), (1.5, 1.0)]
    def f():
      x = [0.1*x for x in range(0,11)]
      dataX = zip(x, slopes(x, lambda x : 0.5*x**2))
      dataX += [(1000,dataX[len(dataX)-1][1])]
      return dataX
    #dataX = f()
    dataX = [(0.0,0.0), (1.0,1.0)]
    factor = 1.0
    approxX = SegmentApproximator(dataX, factor, True, True)
    #distanceOp = lambda x : 0.1 
    distanceOp = lambda x : 0.8*x 
    startingDistance = 0.0
    #approxX = SigmoidApproximator(12.0, -8.0, 1.0, 0.0)
    curves = {
      0 : {
        codes.ABS_X : DirectionBasedCurve3(approxX, distanceOp, startingDistance), 
        codes.ABS_Y : DirectionBasedCurve3(approxX, distanceOp, startingDistance), 
        codes.ABS_Z : DirectionBasedCurve3(approxX, distanceOp),
        codes.ABS_RX : DirectionBasedCurve3(approxX, distanceOp, startingDistance), 
        codes.ABS_RY : DirectionBasedCurve3(approxX, distanceOp), 
      }
    }
    return curves

  curves["direction2"] = CurveAdapter(make_dir_curves2)


  def make_dir_curves4(data):
    approxX = SegmentApproximator(((0.0,0.0), (0.25,0.1), (0.5,0.1), (1.0,1.0)))
    approxZ = SegmentApproximator(((0.1*x,(0.1*x)**2) for x in range(0,8,1)))
    limit = 1.0
    curves = {
      codes.ABS_X : DirectionBasedCurve4(approxX, limit), 
      codes.ABS_Y : DirectionBasedCurve4(approxX, limit), 
      codes.ABS_Z : DirectionBasedCurve4(approxZ, limit),
    }
    return curves

  curves["direction4"] = CurveAdapter(make_dir_curves4)

  def make_dir_curves5(data):
    levels = ((1.0, 1.0), (0.5, 0.5), (0.5, 0.1))
    curves = {
      codes.ABS_X : DirectionBasedCurve(levels, False), 
      codes.ABS_Y : DirectionBasedCurve(levels, False), 
      codes.ABS_Z : DirectionBasedCurve(levels, False),
    }
    return curves

  curves["direction5"] = CurveAdapter(make_dir_curves5)

  def make_dir_curves6(data):
    #levelsX = ((1.0, 1.0), (0.5, 0.5), (0.5, 0.1))
    levelsX = ((1.0, 1.0), (0.5, 0.0),)
    levelsZ = ((1.0, 1.0), (0.5, 0.0),)
    factor = 1.0
    curves = {
      0 : {
        codes.ABS_X : DirectionBasedCurve2(levelsX, factor=factor), 
        codes.ABS_Y : DirectionBasedCurve2(levelsX, factor=factor), 
        codes.ABS_Z : DirectionBasedCurve2(levelsZ, factor=factor),
        codes.ABS_RX : DirectionBasedCurve2(levelsX, factor=factor), 
        codes.ABS_RY : DirectionBasedCurve2(levelsX, factor=factor), 
        codes.ABS_RUDDER : DirectionBasedCurve2(levelsZ, factor=factor),
      }
    }
    return curves

  curves["direction6"] = CurveAdapter(make_dir_curves6)
 

  def make_dist_curves(data):
    """Work ok"""
    approxX = PowerApproximator(0.25, 2.0)
    approxZ = PowerApproximator(0.25, 2.0)
    limit = 1.0
    curves = {
      0 : {
        codes.ABS_X : DistanceBasedCurve(approxX, limit), 
        codes.ABS_Y : DistanceBasedCurve(approxX, limit), 
        codes.ABS_Z : DistanceBasedCurve(approxZ, limit),
      },
      1 : {
        codes.ABS_Z : DistanceBasedCurve(approxX, limit), 
        codes.ABS_Y : DistanceBasedCurve(approxX, limit), 
        codes.ABS_X : DistanceBasedCurve(approxZ, limit),
      },
      2 : {
        codes.ABS_RX : DistanceBasedCurve(approxX, limit), 
        codes.ABS_RY : DistanceBasedCurve(approxX, limit), 
        codes.ABS_RUDDER : DistanceBasedCurve(approxZ, limit),
        codes.ABS_THROTTLE : DistanceBasedCurve(approxZ, limit),
      },
    }
    return curves

  curves["distance"] = CurveAdapter(make_dist_curves)


  def make_base_value_curves(data):
    """Work ok"""
    dj, dh = data["joystick"]["axes"], data["head"]["axes"]
    deltaOp = lambda x,value : x*value
    def SensitivityOp(data):
      """Symmetric"""
      approx = SegmentApproximator(data, 1.0, True, True)
      def op(value):
        return approx(abs(value))
      return op
    sensOp = SensitivityOp( ((0.05,0.10),(0.15,1.0)) )
    sensOpZ = SensitivityOp( ((0.05,0.5),(0.15,5.0)) )
    #valuePointOp = lambda value : clamp(5.0*abs(value), 0.15, 0.5)
    #These settings work
    #valuePointOp = lambda value : clamp(5.0*abs(value), 0.15, 1.0)
    curves = {
      "joystick" : {
        0 : {
          codes.ABS_X : ValueOpDeltaAxisCurve(deltaOp, ValuePointOp((FixedValuePoint(sensOp, 0.0), MovingValuePoint(sensOp),)), dj[codes.ABS_X]),
          codes.ABS_Y : ValueOpDeltaAxisCurve(deltaOp, ValuePointOp((FixedValuePoint(sensOp, 0.0), MovingValuePoint(sensOp),)), dj[codes.ABS_Y]),
          codes.ABS_Z : ValueOpDeltaAxisCurve(deltaOp, ValuePointOp((FixedValuePoint(sensOpZ, 0.0), MovingValuePoint(sensOpZ),)), dj[codes.ABS_Z]),
        },
        1 : {
          codes.ABS_RX : ValueOpDeltaAxisCurve(deltaOp, ValuePointOp((FixedValuePoint(sensOp, 0.0), MovingValuePoint(sensOp),)), dj[codes.ABS_RX]),
          codes.ABS_RY : ValueOpDeltaAxisCurve(deltaOp, ValuePointOp((FixedValuePoint(sensOp, 0.0), MovingValuePoint(sensOp),)), dj[codes.ABS_RY]),
          codes.ABS_RUDDER : ValueOpDeltaAxisCurve(deltaOp, ValuePointOp((FixedValuePoint(sensOpZ, 0.0), MovingValuePoint(sensOpZ),)), dj[codes.ABS_RUDDER]),
        },
        2 : {
          codes.ABS_X : ValueOpDeltaAxisCurve(deltaOp, ValuePointOp((FixedValuePoint(sensOp, 0.0), MovingValuePoint(sensOp),)), dj[codes.ABS_X]),
          codes.ABS_Y : ValueOpDeltaAxisCurve(deltaOp, ValuePointOp((FixedValuePoint(sensOp, 0.0), MovingValuePoint(sensOp),)), dj[codes.ABS_Y]),
          codes.ABS_THROTTLE : ValueOpDeltaAxisCurve(deltaOp, ValuePointOp((FixedValuePoint(sensOpZ, 0.0), MovingValuePoint(sensOpZ),)), dj[codes.ABS_THROTTLE]),
        },
      },
      "head" : {
        0 : {
          codes.ABS_RX : ValueOpDeltaAxisCurve(deltaOp, ValuePointOp((FixedValuePoint(sensOp, 0.0), MovingValuePoint(sensOp),)), dh[codes.ABS_RX]),
          codes.ABS_RY : ValueOpDeltaAxisCurve(deltaOp, ValuePointOp((FixedValuePoint(sensOp, 0.0), MovingValuePoint(sensOp),)), dh[codes.ABS_RY]),
          codes.ABS_THROTTLE : ValueOpDeltaAxisCurve(deltaOp, ValuePointOp((FixedValuePoint(sensOpZ, 0.0), MovingValuePoint(sensOpZ),)), dh[codes.ABS_THROTTLE]),
        },
        1 : {
          codes.ABS_X : ValueOpDeltaAxisCurve(deltaOp, ValuePointOp((FixedValuePoint(sensOp, 0.0), MovingValuePoint(sensOp),)), dh[codes.ABS_X]),
          codes.ABS_Y : ValueOpDeltaAxisCurve(deltaOp, ValuePointOp((FixedValuePoint(sensOp, 0.0), MovingValuePoint(sensOp),)), dh[codes.ABS_Y]),
          codes.ABS_Z : ValueOpDeltaAxisCurve(deltaOp, ValuePointOp((FixedValuePoint(sensOpZ, 0.0), MovingValuePoint(sensOpZ),)), dh[codes.ABS_Z]),
        },
      },
    }

    return curves

  curves["base_value"] = make_base_value_curves


  def make_config_curves(data):
    deltaOp = lambda x,value : x*value
    def SensitivityOp(data):
      """Symmetric"""
      approx = SegmentApproximator(data, 1.0, True, True)
      def op(value):
        return approx(abs(value))
      return op

    def parsePoints(cfg, state):
      pointParsers = {}

      def fixedPointParser(cfg, state):
        op = SensitivityOp(cfg["points"])
        return FixedValuePoint(op, cfg.get("value", 0.0))

      pointParsers["fixed"] = fixedPointParser

      def movingPointParser(cfg, state):
        op = SensitivityOp(cfg["points"])
        newRatio = clamp(cfg.get("newValueRatio", 0.5), 0.0, 1.0)
        def make_value_op(newRatio):
          oldRatio = 1.0 - newRatio 
          def op(old,new):
            return oldRatio*old+newRatio*new
          return op
        return MovingValuePoint(op, make_value_op(newRatio))

      pointParsers["moving"] = movingPointParser

      r = []
      for pd in cfg:
        t = pd["type"]
        state["point"] = t
        r.append(pointParsers[t](pd, state))
      return r

    def parseAxis(cfg, state):
      curveParsers = {}

      def parseValuePointsCurve(cfg, state):
        oName = state["output"]
        axisId = nameToAxis[state["axis"]]
        axis = state["axes"][oName][axisId]
        points = parsePoints(cfg["points"], state)
        return ValueOpDeltaAxisCurve(deltaOp, ValuePointOp(points), axis)

      curveParsers["valuePoints"] = parseValuePointsCurve

      curve,data = cfg.get("curve", None), cfg.get("data", None) 
      if curve is None:
        raise Exception("{}.{}.{}: Curve type not set".format(state["set"], state["mode"], state["axis"]))
      if data is None:
        raise Exception("{}.{}.{}: Curve data not set".format(state["set"], state["mode"], state["axis"]))
      state["curve"] = curve
      return curveParsers[curve](data, state)
          
    def parseAxes(cfg, state):
      r = {}
      for axisName,axisData in cfg.items():
        state["axis"] = axisName
        r[nameToAxis[axisName]] = parseAxis(axisData, state)
      return r

    def parseGroups(cfg, state):
      groupParsers = {}

      def parseCurvesGroup(cfg, state):
        r = {}
        for outputName,outputData in cfg.items():
          state["output"] = outputName
          r[outputName] = parseAxes(outputData, state)
        return r 

      groupParsers["curves"] = parseCurvesGroup

      def parseSensGroup(cfg, state):
        r = {}
        for inputSourceAndAxisName,inputAxisData in cfg.items():
          inputSourceName, inputAxisName = inputSourceAndAxisName.split(".")
          inputAxis = nameToRelativeAxis[inputAxisName]
          r[(inputSourceName, inputAxis)] = float(inputAxisData)
        return r 

      groupParsers["sens"] = parseSensGroup

      r = {}
      for groupName,groupData in cfg.items():
        state["group"] = groupName
        r[groupName] = groupParsers[groupName](groupData, state)
      return r

    def parseModes(cfg, state):
      r = {}
      for modeName,modeData in cfg.items():
        state["mode"] = modeName
        r[int(modeName)] = parseGroups(modeData, state)
      return r

    def parseSets(cfg, state):
      r = {}
      for setName,setData in cfg.items():
        state["set"] = str(setName)
        r[setName] = parseModes(setData, state)
      return r

    state = {"data" : data, "axes" : {}}
    for oName,o in data["outputs"].items():
      state["axes"][oName] = {axisId:Axis(o, axisId) for axisId in axisToName.keys()}
    settings = data["settings"]
    sets = settings["config"]["layouts"][settings["configCurveLayoutName"]]
    r = parseSets(sets, state)
    return r

  curves["config"] = make_config_curves

  return curves

curveMakers = make_curve_makers()


def init_main_sink(settings, make_next):
  logger.debug("init_main_sink()")
  clickSink = ClickSink(settings["config"].get("clickTime", 0.5))
  modifierSink = clickSink.set_next(ModifierSink2(source="keyboard"))
  sens = settings["config"].get("sens", None)
  if sens is not None:
    sensSet = settings["config"].get("sensSet", 0)
    if sensSet < 0 or sensSet >= len(sens):
      raise Exception("Invalid sensitivity set: {}".format(sensSet))
    sens = sens[sensSet]
    sens = {nameToRelativeAxis[s[0]]:s[1] for s in sens.items()}
  scaleSink = modifierSink.set_next(ScaleSink(sens))
  mainSink = scaleSink.set_next(Binding(CmpWithModifiers2()))
  stateSink = mainSink.add((), StateSink(), 1)
  toggleKey = settings.get("toggleKey", codes.KEY_SCROLLLOCK)
  def make_toggle(settings, stateSink):
    grabberSinks = []
    for g in settings["config"].get("grabbed", ()):
      dev = settings["inputs"][g]
      grabberSinks.append(DeviceGrabberSink(dev))
    toggleSink = ToggleSink(stateSink)
    def toggle(event):
      toggleSink(event)
      for s in grabberSinks: 
        s(event)
      logger.info("Emulation {}".format("enabled" if stateSink.get_state() == True else "disabled"))
    return toggle
  mainSink.add(ED.doubleclick(toggleKey), make_toggle(settings, stateSink), 0)
  def makeAndSetNext():
    try:
      stateSink.set_next(make_next(settings))
      logger.info("Sink initialized")
    except Exception as e:
      logger.error("Failed to make sink: {}".format(e))
      traceback.print_tb(sys.exc_info()[2])
  def rld(e):
    raise ReloadException()
  mainSink.add(ED.click(toggleKey, [(None, codes.KEY_RIGHTSHIFT)]), rld, 0)
  mainSink.add(ED.click(toggleKey, [(None, codes.KEY_LEFTSHIFT)]), rld, 0)
  makeAndSetNext()
  return clickSink


def init_mode_sink(binding, curves, resetOnMove=None, resetOnLeave=None, setOnLeave=None):
  sink = Binding(CmpWithModifiers())
  ms = sink.add(ED3.parse("any()"), StateSink(), 1)
  sink.add(ED.init(1), SetState(ms, True), 0)
  sink.add(ED.init(0), SetState(ms, False), 0)
  ms.set_next(binding)
  if resetOnMove is not None:
    for k in resetOnMove:
      binding.add(ED.move_to(k), ResetCurve(curves[k]))
  #Resetting axes controlled in this mode when leaving mode. May not be needed in other cases.
  #Resetting curves when leaving mode. May not be needed in other cases.
  if resetOnLeave is not None:
    for k in resetOnLeave:
      sink.add(ED.init(0), ResetCurve(curves[k]), 2)
  if setOnLeave is not None:
    for p in setOnLeave:
      sink.add(ED.init(0), SetCurveAxis(curves[p[0]], p[1]), 2)
  return sink


def init_log(settings, handler=None):
  logLevelName = settings["log_level"].upper()
  nameToLevel = {
    logging.getLevelName(l).upper():l for l in (logging.CRITICAL, logging.ERROR, logging.WARNING, logging.INFO, logging.DEBUG, logging.NOTSET)
  }

  print("Setting log level to {}".format(logLevelName))
  logLevel = nameToLevel.get(logLevelName, logging.NOTSET)
  root = logging.getLogger()
  root.setLevel(logLevel)
  if handler is None:
    handler = logging.StreamHandler(sys.stdout)
  handler.setLevel(logLevel)
  handler.setFormatter(logging.Formatter("%(name)s:%(levelname)s:%(message)s"))
  root.addHandler(handler)


def init_config(configFilesNames):
  cfg = {}
  for configName in configFilesNames:
    with open(configName, "r") as f:
      merge_dicts(cfg, json.load(f))
  return cfg
                              

sink_initializers = {}

def init_sinks_empty(settings): 
  return None

sink_initializers["empty"] = init_sinks_empty


def init_sinks_main(settings): 
  return init_main_sink(settings, lambda s : None)

sink_initializers["main"] = init_sinks_empty


def init_sinks_base(settings): 
  cmpOp = CmpWithModifiers2()
  curveSet = settings.get("curves", None)
  if curveSet is None:
    raise Exception("No curve set specified in settings")
  curveMaker = curveMakers.get(curveSet, None)
  if curveMaker is None:
    raise Exception("No curves for {}".format(curveSet))
  
  joystick = settings["outputs"]["joystick"]
  head = settings["outputs"]["head"]

  data = {
    "outputs" : { "joystick" : joystick, "head" : head },
    "settings" : settings,
  }

  curves = curveMaker(data)

  joySnaps = CurveSnapManager()
  joySnaps.set_snap(0, ((codes.ABS_Z, 0.0, True),))
  joySnaps.set_snap(1, ((codes.ABS_X, 0.0, True), (codes.ABS_Y, 0.0, True),))
  joySnaps.set_snap(3, ((codes.ABS_RX, 0.0, True), (codes.ABS_RY, 0.0, True),))

  headSnaps = SnapManager(head, False)
  zero = ((codes.ABS_X, 0), (codes.ABS_Y, 0), (codes.ABS_Z, 0.0), (codes.ABS_RX, 0), (codes.ABS_RY, 0), (codes.ABS_RZ, 0), (codes.ABS_THROTTLE, 0.0),)
  headSnaps.set_snap(0, zero)
  fullForward = ((codes.ABS_X, 0), (codes.ABS_Y, 0), (codes.ABS_Z, 1.0), (codes.ABS_RX, 0), (codes.ABS_RY, 0), (codes.ABS_RZ, 0), (codes.ABS_THROTTLE, 1.0),)
  headSnaps.set_snap(1, fullForward)
  fullBackward = ((codes.ABS_X, 0), (codes.ABS_Y, 0), (codes.ABS_Z, -1.0), (codes.ABS_RX, 0), (codes.ABS_RY, -0.15), (codes.ABS_RZ, 0), (codes.ABS_THROTTLE, -1.0),)
  headSnaps.set_snap(2, fullBackward)
  zoomOut = ((codes.ABS_THROTTLE, -1.0),)
  headSnaps.set_snap(3, zoomOut)
  centerView = ((codes.ABS_RX, 0.0), (codes.ABS_RY, 0.0),)
  headSnaps.set_snap(4, centerView)
  centerViewPos = ((codes.ABS_X, 0.0), (codes.ABS_Y, 0.0), (codes.ABS_Z, 0.0),)
  headSnaps.set_snap(5, centerViewPos)


  topBindingSink = Binding(cmpOp)
  topModeSink = ModeSink()
  topBindingSink.add(ED3.parse("any()"), topModeSink, 1)
  topBindingSink.add(ED3.parse("press(mouse.BTN_RIGHT)"), SetMode(topModeSink, 1), 0)
  topBindingSink.add(ED3.parse("release(mouse.BTN_RIGHT)"), SetMode(topModeSink, 0), 0)
  topBindingSink.add(ED3.parse("release(mouse.BTN_RIGHT)"), UpdateSnap(headSnaps, 0), 0)

  joystickBindingSink = Binding(cmpOp)
  topModeSink.add(0, joystickBindingSink)
  topModeSink.set_mode(0)

  joystickModeSink = joystickBindingSink.add(ED3.parse("any()"), ModeSink(), 1)
  oldMode =  []
  def save_mode(event):
    oldMode.append(joystickModeSink.get_mode())
  def restore_mode(event):
    if len(oldMode):
      joystickModeSink.set_mode(oldMode.pop())
  def clear_mode(event):
    oldMode = []
  joystickBindingSink.add(ED3.parse("press(mouse.BTN_EXTRA)"), save_mode, 0)
  joystickBindingSink.add(ED3.parse("press(mouse.BTN_EXTRA)"), SetMode(joystickModeSink, 1), 0)
  joystickBindingSink.add(ED3.parse("release(mouse.BTN_EXTRA)"), restore_mode, 0)
  joystickBindingSink.add(ED3.parse("press(mouse.BTN_SIDE)"), save_mode, 0)
  joystickBindingSink.add(ED3.parse("press(mouse.BTN_SIDE)"), SetMode(joystickModeSink, 2), 0)
  joystickBindingSink.add(ED3.parse("release(mouse.BTN_SIDE)"), restore_mode, 0)

  if "primary" in curves:
    cj = curves["primary"]
    if 0 in cj:
      logger.debug("Init mode 0")
      cs = cj[0]["curves"]["joystick"]

      ss = Binding(cmpOp)
      ss.add(ED3.parse("move(mouse.REL_X)"), MoveCurve(cs.get(codes.ABS_X, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_Y)"), MoveCurve(cs.get(codes.ABS_Y, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_WHEEL)"), MoveCurve(cs.get(codes.ABS_Z, None)), 0)
      ss.add(ED3.parse("click(mouse.BTN_MIDDLE)"), SnapTo(joySnaps, 0), 0)
      ss.add(ED3.parse("doubleclick(mouse.BTN_MIDDLE)"), SnapTo(joySnaps, 1), 0)
      ss.add(ED3.parse("click(mouse.BTN_LEFT)"), SnapTo(headSnaps, 0), 0)
      ss.add(ED3.parse("init(1)"), SetCurves(joySnaps, [(axisId, cs.get(axisId, None)) for axisId in (codes.ABS_X, codes.ABS_Y, codes.ABS_Z)]))
      joystickModeSink.add(0, ss)

    if 1 in cj:
      logger.debug("Init mode 1")
      cs = cj[1]["curves"]["joystick"]

      ss = Binding(cmpOp)
      ss.add(ED3.parse("move(mouse.REL_X)"), MoveCurve(cs.get(codes.ABS_RX, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_Y)"), MoveCurve(cs.get(codes.ABS_RY, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_WHEEL)"), MoveCurve(cs.get(codes.ABS_RUDDER, None)), 0)
      ss.add(ED3.parse("doubleclick(mouse.BTN_MIDDLE)"), SnapTo(joySnaps, 3), 0)
      ss.add(ED3.parse("click(mouse.BTN_LEFT)"), SnapTo(headSnaps, 1), 0)
      ss.add(ED3.parse("init(1)"), SetCurves(joySnaps, [(axisId, cs.get(axisId, None)) for axisId in (codes.ABS_RX, codes.ABS_RY, codes.ABS_RUDDER)]))
      joystickModeSink.add(1, ss)

    if 2 in cj:
      logger.debug("Init mode 2")
      cs = cj[2]["curves"]["joystick"]

      ss = Binding(cmpOp)
      ss.add(ED3.parse("move(mouse.REL_X)"), MoveCurve(cs.get(codes.ABS_X, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_Y)"), MoveCurve(cs.get(codes.ABS_Y, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_WHEEL)"), MoveCurve(cs.get(codes.ABS_THROTTLE, None)), 0)
      ss.add(ED3.parse("click(mouse.BTN_LEFT)"), SnapTo(headSnaps, 2), 0)
      ss.add(ED3.parse("init(1)"), SetCurves(joySnaps, [(axisId, cs.get(axisId, None)) for axisId in (codes.ABS_X, codes.ABS_Y, codes.ABS_THROTTLE)]))
      joystickModeSink.add(2, ss)

    joystickModeSink.set_mode(0)

  headBindingSink = Binding(cmpOp)
  topModeSink.add(1, headBindingSink)

  headModeSink = ModeSink()
  headBindingSink.add(ED3.parse("any()"), headModeSink, 1)
  headBindingSink.add(ED3.parse("press(mouse.BTN_EXTRA)"), SetMode(headModeSink, 1), 0)
  headBindingSink.add(ED3.parse("release(mouse.BTN_EXTRA)"), SetMode(headModeSink, 0), 0)

  if "secondary" in curves:
    cj = curves["secondary"]
    if 0 in cj:
      logger.debug("Init mode 0")
      cs = cj[0]["curves"]["head"]

      ss = Binding(cmpOp)
      ss.add(ED3.parse("move(mouse.REL_X)"), MoveCurve(cs.get(codes.ABS_RX, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_Y)"), MoveCurve(cs.get(codes.ABS_RY, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_WHEEL)"), MoveCurve(cs.get(codes.ABS_THROTTLE, None)), 0)
      ss.add(ED3.parse("click(mouse.BTN_MIDDLE)"), SnapTo(headSnaps, 3), 0)
      ss.add(ED3.parse("doubleclick(mouse.BTN_MIDDLE)"), SnapTo(headSnaps, 4), 0)
      headModeSink.add(0, ss)

    if 1 in cj:
      logger.debug("Init mode 1")
      cs = cj[1]["curves"]["head"]

      ss = Binding(cmpOp)
      ss.add(ED3.parse("move(mouse.REL_X)"), MoveCurve(cs.get(codes.ABS_X, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_Y)"), MoveCurve(cs.get(codes.ABS_Y, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_WHEEL)"), MoveCurve(cs.get(codes.ABS_Z, None)), 0)
      ss.add(ED3.parse("doubleclick(mouse.BTN_MIDDLE)"), SnapTo(headSnaps, 5), 0)
      headModeSink.add(1, ss)

  headModeSink.set_mode(0)

  return topBindingSink

sink_initializers["base"] = init_sinks_base


def init_sinks_base3(settings):
  cmpOp = CmpWithModifiers2()
  curveSet = settings.get("curves", None)
  if curveSet is None:
    raise Exception("No curve set specified in settings")
  curveMaker = curveMakers.get(curveSet, None)
  if curveMaker is None:
    raise Exception("No curves for {}".format(curveSet))
  
  joystick = settings["outputs"]["joystick"]
  head = settings["outputs"]["head"]

  data = {
    "outputs" : { "joystick" : joystick, "head" : head },
    "settings" : settings,
  }

  curves = curveMaker(data)

  joySnaps = CurveSnapManager()
  joySnaps.set_snap("z", ((codes.ABS_Z, 0.0, True),))
  joySnaps.set_snap("xy", ((codes.ABS_X, 0.0, True), (codes.ABS_Y, 0.0, True),))
  joySnaps.set_snap("x", ((codes.ABS_X, 0.0, True),))
  joySnaps.set_snap("zy", ((codes.ABS_Z, 0.0, True), (codes.ABS_Y, 0.0, True),))
  joySnaps.set_snap("rxry", ((codes.ABS_RX, 0.0, True), (codes.ABS_RY, 0.0, True),))

  headSnaps = SnapManager(head, False)
  zero = ((codes.ABS_X, 0), (codes.ABS_Y, 0), (codes.ABS_Z, 0.0), (codes.ABS_RX, 0), (codes.ABS_RY, 0), (codes.ABS_RZ, 0), (codes.ABS_THROTTLE, 0.0),)
  headSnaps.set_snap(0, zero)
  fullForward = ((codes.ABS_X, 0), (codes.ABS_Y, 0), (codes.ABS_Z, 1.0), (codes.ABS_RX, 0), (codes.ABS_RY, 0), (codes.ABS_RZ, 0), (codes.ABS_THROTTLE, 1.0),)
  headSnaps.set_snap(1, fullForward)
  fullBackward = ((codes.ABS_X, 0), (codes.ABS_Y, 0), (codes.ABS_Z, -1.0), (codes.ABS_RX, 0), (codes.ABS_RY, -0.15), (codes.ABS_RZ, 0), (codes.ABS_THROTTLE, -1.0),)
  headSnaps.set_snap(2, fullBackward)
  zoomOut = ((codes.ABS_THROTTLE, -1.0),)
  headSnaps.set_snap(3, zoomOut)
  centerView = ((codes.ABS_RX, 0.0), (codes.ABS_RY, 0.0),)
  headSnaps.set_snap(4, centerView)
  centerViewPos = ((codes.ABS_X, 0.0), (codes.ABS_Y, 0.0), (codes.ABS_Z, 0.0),)
  headSnaps.set_snap(5, centerViewPos)


  topBindingSink = Binding(cmpOp)
  topModeSink = ModeSink()
  topBindingSink.add(ED3.parse("any()"), topModeSink, 1)
  topBindingSink.add(ED3.parse("press(mouse.BTN_RIGHT)"), SetMode(topModeSink, 1), 0)
  topBindingSink.add(ED3.parse("release(mouse.BTN_RIGHT)"), SetMode(topModeSink, 0), 0)
  topBindingSink.add(ED3.parse("release(mouse.BTN_RIGHT)"), UpdateSnap(headSnaps, 0), 0)

  joystickBindingSink = Binding(cmpOp)
  topModeSink.add(0, joystickBindingSink)
  topModeSink.set_mode(0)

  joystickModeSink = joystickBindingSink.add(ED3.parse("any()"), ModeSink(), 1)
  oldMode =  []
  def save_mode(event):
    oldMode.append(joystickModeSink.get_mode())
  def restore_mode(event):
    if len(oldMode):
      joystickModeSink.set_mode(oldMode.pop())
  def clear_mode(event):
    oldMode = []
  joystickBindingSink.add(ED3.parse("press(mouse.BTN_EXTRA)"), save_mode, 0)
  joystickBindingSink.add(ED3.parse("press(mouse.BTN_EXTRA)"), SetMode(joystickModeSink, 1), 0)
  joystickBindingSink.add(ED3.parse("release(mouse.BTN_EXTRA)"), restore_mode, 0)
  joystickBindingSink.add(ED3.parse("press(mouse.BTN_SIDE)"), save_mode, 0)
  joystickBindingSink.add(ED3.parse("press(mouse.BTN_SIDE)"), SetMode(joystickModeSink, 2), 0)
  joystickBindingSink.add(ED3.parse("release(mouse.BTN_SIDE)"), restore_mode, 0)

  if "primary" in curves:
    cj = curves["primary"]
    if 0 in cj:
      logger.debug("Init mode 0")
      cs = cj[0]["curves"]["joystick"]

      ss = Binding(cmpOp)
      ss.add(ED3.parse("move(mouse.REL_X)"), MoveCurve(cs.get(codes.ABS_X, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_Y)"), MoveCurve(cs.get(codes.ABS_Y, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_WHEEL)+"), MoveCurve(cs.get(codes.ABS_Z, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_WHEEL)+keyboard.KEY_RIGHTSHIFT"), MoveCurve(cs.get(codes.ABS_THROTTLE, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_WHEEL)+keyboard.KEY_LEFTSHIFT"), MoveCurve(cs.get(codes.ABS_THROTTLE, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_WHEEL)+keyboard.KEY_RIGHTCTRL"), MoveCurve(cs.get(codes.ABS_RUDDER, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_WHEEL)+keyboard.KEY_LEFTCTRL"), MoveCurve(cs.get(codes.ABS_RUDDER, None)), 0)
      ss.add(ED3.parse("click(mouse.BTN_MIDDLE)+"), SnapTo(joySnaps, "z"), 0)
      ss.add(ED3.parse("doubleclick(mouse.BTN_MIDDLE)"), SnapTo(joySnaps, "xy"), 0)
      ss.add(ED3.parse("click(mouse.BTN_LEFT)"), SnapTo(headSnaps, 0), 0)
      ss.add(ED3.parse("init(1)"), SetCurves(joySnaps, [(axisId, cs.get(axisId, None)) for axisId in (codes.ABS_X, codes.ABS_Y, codes.ABS_Z, codes.ABS_THROTTLE, codes.ABS_RUDDER)]))
      joystickModeSink.add(0, ss)

    if 1 in cj:
      logger.debug("Init mode 1")
      cs = cj[1]["curves"]["joystick"]

      ss = Binding(cmpOp)
      ss.add(ED3.parse("move(mouse.REL_X)"), MoveCurve(cs.get(codes.ABS_Z, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_Y)"), MoveCurve(cs.get(codes.ABS_Y, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_WHEEL+"), MoveCurve(cs.get(codes.ABS_X, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_WHEEL)+keyboard.KEY_RIGHTSHIFT"), MoveCurve(cs.get(codes.ABS_THROTTLE, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_WHEEL)+keyboard.KEY_LEFTSHIFT"), MoveCurve(cs.get(codes.ABS_THROTTLE, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_WHEEL)+keyboard.KEY_RIGHTCTRL"), MoveCurve(cs.get(codes.ABS_RUDDER, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_WHEEL)+keyboard.KEY_LEFTCTRL"), MoveCurve(cs.get(codes.ABS_RUDDER, None)), 0)
      ss.add(ED3.parse("click(mouse.BTN_MIDDLE)"), SnapTo(joySnaps, "x"), 0)
      ss.add(ED3.parse("doubleclick(mouse.BTN_MIDDLE)"), SnapTo(joySnaps, "zy"), 0)
      ss.add(ED3.parse("click(mouse.BTN_LEFT)"), SnapTo(headSnaps, 1), 0)
      ss.add(ED3.parse("init(1)"), SetCurves(joySnaps, [(axisId, cs.get(axisId, None)) for axisId in (codes.ABS_X, codes.ABS_Y, codes.ABS_Z, codes.ABS_THROTTLE, codes.ABS_RUDDER)]))
      joystickModeSink.add(1, ss)

    if 2 in cj:
      logger.debug("Init mode 2")
      cs = cj[2]["curves"]["joystick"]

      ss = Binding(cmpOp)
      ss.add(ED3.parse("move(mouse.REL_X)"), MoveCurve(cs.get(codes.ABS_RX, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_Y)"), MoveCurve(cs.get(codes.ABS_RY, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_WHEEL)"), MoveCurve(cs.get(codes.ABS_RZ, None)), 0)
      ss.add(ED3.parse("doubleclick(mouse.BTN_MIDDLE)"), SnapTo(joySnaps, "rxry"), 0)
      ss.add(ED3.parse("click(mouse.BTN_LEFT)"), SnapTo(headSnaps, 2), 0)
      ss.add(ED3.parse("init(1)"), SetCurves(joySnaps, [(axisId, cs.get(axisId, None)) for axisId in (codes.ABS_RX, codes.ABS_RY, codes.ABS_RZ)]))
      joystickModeSink.add(2, ss)

    joystickModeSink.set_mode(0)

  headBindingSink = Binding(cmpOp)
  topModeSink.add(1, headBindingSink)

  headModeSink = ModeSink()
  headBindingSink.add(ED3.parse("any()"), headModeSink, 1)
  headBindingSink.add(ED3.parse("press(mouse.BTN_EXTRA)"), SetMode(headModeSink, 1), 0)
  headBindingSink.add(ED3.parse("release(mouse.BTN_EXTRA)"), SetMode(headModeSink, 0), 0)

  if "secondary" in curves:
    cj = curves["secondary"]
    if 0 in cj:
      logger.debug("Init mode 0")
      cs = cj[0]["curves"]["head"]

      ss = Binding(cmpOp)
      ss.add(ED3.parse("move(mouse.REL_X)"), MoveCurve(cs.get(codes.ABS_RX, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_Y)"), MoveCurve(cs.get(codes.ABS_RY, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_WHEEL)"), MoveCurve(cs.get(codes.ABS_THROTTLE, None)), 0)
      ss.add(ED3.parse("click(mouse.BTN_MIDDLE)"), SnapTo(headSnaps, 3), 0)
      ss.add(ED3.parse("doubleclick(mouse.BTN_MIDDLE)"), SnapTo(headSnaps, 4), 0)
      headModeSink.add(0, ss)

    if 1 in cj:
      logger.debug("Init mode 1")
      cs = cj[1]["curves"]["head"]

      ss = Binding(cmpOp)
      ss.add(ED3.parse("move(mouse.REL_X)"), MoveCurve(cs.get(codes.ABS_X, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_Y)"), MoveCurve(cs.get(codes.ABS_Y, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_WHEEL)"), MoveCurve(cs.get(codes.ABS_Z, None)), 0)
      ss.add(ED3.parse("doubleclick(mouse.BTN_MIDDLE)"), SnapTo(headSnaps, 5), 0)
      headModeSink.add(1, ss)

  headModeSink.set_mode(0)

  return topBindingSink

sink_initializers["base3"] = init_sinks_base3


def init_sinks_descent(settings):
  cmpOp = CmpWithModifiers2()

  curveSet = settings.get("curves", None)
  if curveSet is None:
    raise Exception("No curve set specified in settings")
  curveMaker = curveMakers.get(curveSet, None)
  if curveMaker is None:
    raise Exception("No curves for {}".format(curveSet))
  
  joystick = settings["outputs"]["joystick"]

  data = {
    "outputs" : { "joystick" : joystick },
    "settings" : settings,
  }

  curves = curveMaker(data)["primary"]

  joystickSink = Binding(cmpOp)
  joystickSink.add(ED3.parse("press(mouse.BTN_LEFT)"), SetButtonState(joystick, codes.BTN_0, 1), 0)
  joystickSink.add(ED3.parse("release(mouse.BTN_LEFT)"), SetButtonState(joystick, codes.BTN_0, 0), 0)
  joystickSink.add(ED3.parse("press(mouse.BTN_RIGHT)"), SetButtonState(joystick, codes.BTN_1, 1), 0)
  joystickSink.add(ED3.parse("release(mouse.BTN_RIGHT)"), SetButtonState(joystick, codes.BTN_1, 0), 0)

  joystickModeSink = joystickSink.add(ED3.parse("any()"), ModeSink(), 1)
  oldMode =  []
  def save_mode(event):
    oldMode.append(joystickModeSink.get_mode())
  def restore_mode(event):
    if len(oldMode) >= 1 : joystickModeSink.set_mode(oldMode.pop())
  def clear_mode(event):
    oldMode = []
  joystickSink.add(ED3.parse("press(mouse.BTN_SIDE)"), save_mode, 0)
  joystickSink.add(ED3.parse("press(mouse.BTN_SIDE)"), SetMode(joystickModeSink, 2), 0)
  joystickSink.add(ED3.parse("release(mouse.BTN_SIDE)"), restore_mode, 0)

  #It is crucial to get current mode from modeSink itself
  cycleMode = lambda e : joystickModeSink.set_mode(0 if joystickModeSink.get_mode() == 1 else 1)
  joystickSink.add(ED3.parse("press(mouse.BTN_EXTRA)+"), save_mode, 0)
  joystickSink.add(ED3.parse("press(mouse.BTN_EXTRA)+"), cycleMode, 0)
  joystickSink.add(ED3.parse("release(mouse.BTN_EXTRA)"), restore_mode, 0)
  joystickSink.add(ED3.parse("doubleclick(mouse.BTN_EXTRA)+"), cycleMode, 0)

  if 0 in curves:
    logger.debug("Init mode 0")
    cs = curves[0]["curves"]["joystick"]

    ss = Binding(cmpOp)
    ss.add(ED3.parse("move(mouse.REL_X)"), MoveCurve(cs.get(codes.ABS_X, None)), 0)
    ss.add(ED3.parse("move(mouse.REL_Y)"), MoveCurve(cs.get(codes.ABS_Y, None)), 0)
    ss.add(ED3.parse("move(mouse.REL_WHEEL)"), MoveCurve(cs.get(codes.ABS_Z, None)), 0)
    ss.add(ED3.parse("click(mouse.BTN_MIDDLE)"), SetCurveAxis2(cs.get(codes.ABS_Z, None), value=0.0, relative=False, reset=True), 0)
    ss.add(ED3.parse("doubleclick(BTN_MIDDLE)"), SetCurvesAxes2([(cs.get(axisId, None), 0.0, False, True) for axisId in (codes.ABS_X, codes.ABS_Y)]), 0)
    ss.add(ED3.parse("init(0)"), SetCurvesAxes2([(cs.get(axisId, None), 0.0, False, True) for axisId in (codes.ABS_X, codes.ABS_Y, codes.ABS_Z)]))

    if "sens" in curves[0]:
      sensSink = ScaleSink2(curves[0]["sens"], lambda event : (event.source, event.code))
      sensSink.set_next(ss)
      ss = sensSink 
    joystickModeSink.add(0, ss)

  if 1 in curves:
    logger.debug("Init mode 1")
    cs = curves[1]["curves"]["joystick"]

    ss = Binding(cmpOp)
    ss.add(ED3.parse("move(mouse.REL_X)"), MoveCurve(cs.get(codes.ABS_Z, None)), 0)
    ss.add(ED3.parse("move(mouse.REL_Y)"), MoveCurve(cs.get(codes.ABS_Y, None)), 0)
    ss.add(ED3.parse("move(mouse.REL_WHEEL)"), MoveCurve(cs.get(codes.ABS_X, None)), 0)
    ss.add(ED3.parse("click(mouse.BTN_MIDDLE)"), SetCurveAxis2(cs.get(codes.ABS_X, None), value=0.0, relative=False, reset=True), 0)
    ss.add(ED3.parse("doubleclick(mouse.BTN_MIDDLE)"), SetCurvesAxes2([(cs.get(axisId, None), 0.0, False, True) for axisId in (codes.ABS_Z, codes.ABS_Y)]), 0)
    ss.add(ED3.parse("init(0)"), SetCurvesAxes2([(cs.get(axisId, None), 0.0, False, True) for axisId in (codes.ABS_X, codes.ABS_Y, codes.ABS_Z)]))
    joystickModeSink.add(1, ss)

  if 2 in curves:
    logger.debug("Init mode 2")
    cs = curves[2]["curves"]["joystick"]

    ss = Binding(cmpOp)
    ss.add(ED3.parse("move(mouse.REL_X)"), MoveCurve(cs.get(codes.ABS_RX, None)), 0)
    ss.add(ED3.parse("move(mouse.REL_Y)"), MoveCurve(cs.get(codes.ABS_RY, None)), 0)
    ss.add(ED3.parse("move(mouse.REL_WHEEL)+"), MoveCurve(cs.get(codes.ABS_THROTTLE, None)), 0)
    ss.add(ED3.parse("click(mouse.BTN_MIDDLE)+"), SetCurveAxis2(cs.get(codes.ABS_THROTTLE, None), value=0.0, relative=False, reset=True), 0)
    ss.add(ED3.parse("doubleclick(mouse.BTN_MIDDLE)+"), SetCurvesAxes2([(cs.get(axisId, None), 0.0, False, True) for axisId in (codes.ABS_RX, codes.ABS_RY)]), 0)
    moveRudder = MoveCurve(cs.get(codes.ABS_RUDDER, None))
    ss.add(ED3.parse("move(mouse.REL_WHEEL)+keyboard.KEY_RIGHTSHIFT"), moveRudder, 0)
    ss.add(ED3.parse("move(mouse.REL_WHEEL)+keyboard.KEY_LEFTSHIFT"), moveRudder, 0)
    setRudder = SetCurveAxis2(cs.get(codes.ABS_RUDDER, None), value=0.0, relative=False, reset=True)
    ss.add(ED3.parse("click(mouse.BTN_MIDDLE)+keyboard.KEY_RIGHTSHIFT"), setRudder, 0)
    ss.add(ED3.parse("click(mouse.BTN_MIDDLE)+keyboard.KEY_LEFTSHIFT"), setRudder, 0)
    ss.add(ED3.parse("init(0)"), SetCurvesAxes2([(cs.get(axisId, None), 0.0, False, True) for axisId in (codes.ABS_RX, codes.ABS_RY)]))
    ss.add(ED3.parse("init(0)"), ResetCurves([cs.get(axisId, None) for axisId in (codes.ABS_RX, codes.ABS_RY, codes.ABS_THROTTLE, codes.ABS_RUDDER)]))
    joystickModeSink.add(2, ss)

  joystickModeSink.set_mode(0)
    
  return joystickSink

sink_initializers["descent"] = init_sinks_descent
