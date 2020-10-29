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
    elif isinstance(value, list):
      node = destination.get(key, [])
      node += value
      destination[key] = node
    else:
      destination[key] = value
  return destination


EV_BCAST = -1
BC_INIT = 0

codesDict = { 'ABS_BRAKE':10, 'ABS_CNT':64, 'ABS_DISTANCE':25, 'ABS_GAS':9, 'ABS_HAT0X':16, 'ABS_HAT0Y':17, 'ABS_HAT1X':18, 'ABS_HAT1Y':19, 'ABS_HAT2X':20, 'ABS_HAT2Y':21, 'ABS_HAT3X':22, 'ABS_HAT3Y':23, 'ABS_MAX':63, 'ABS_MISC':40, 'ABS_MT_BLOB_ID':56, 'ABS_MT_DISTANCE':59, 'ABS_MT_ORIENTATION':52, 'ABS_MT_POSITION_X':53, 'ABS_MT_POSITION_Y':54, 'ABS_MT_PRESSURE':58, 'ABS_MT_SLOT':47, 'ABS_MT_TOOL_TYPE':55, 'ABS_MT_TOOL_X':60, 'ABS_MT_TOOL_Y':61, 'ABS_MT_TOUCH_MAJOR':48, 'ABS_MT_TOUCH_MINOR':49, 'ABS_MT_TRACKING_ID':57, 'ABS_MT_WIDTH_MAJOR':50, 'ABS_MT_WIDTH_MINOR':51, 'ABS_PRESSURE':24, 'ABS_RESERVED':46, 'ABS_RUDDER':7, 'ABS_RX':3, 'ABS_RY':4, 'ABS_RZ':5, 'ABS_THROTTLE':6, 'ABS_TILT_X':26, 'ABS_TILT_Y':27, 'ABS_TOOL_WIDTH':28, 'ABS_VOLUME':32, 'ABS_WHEEL':8, 'ABS_X':0, 'ABS_Y':1, 'ABS_Z':2, 'BTN_0':256, 'BTN_1':257, 'BTN_2':258, 'BTN_3':259, 'BTN_4':260, 'BTN_5':261, 'BTN_6':262, 'BTN_7':263, 'BTN_8':264, 'BTN_9':265, 'BTN_A':304, 'BTN_B':305, 'BTN_BACK':278, 'BTN_BASE':294, 'BTN_BASE2':295, 'BTN_BASE3':296, 'BTN_BASE4':297, 'BTN_BASE5':298, 'BTN_BASE6':299, 'BTN_C':306, 'BTN_DEAD':303, 'BTN_DIGI':320, 'BTN_DPAD_DOWN':545, 'BTN_DPAD_LEFT':546, 'BTN_DPAD_RIGHT':547, 'BTN_DPAD_UP':544, 'BTN_EAST':305, 'BTN_EXTRA':276, 'BTN_FORWARD':277, 'BTN_GAMEPAD':304, 'BTN_GEAR_DOWN':336, 'BTN_GEAR_UP':337, 'BTN_JOYSTICK':288, 'BTN_LEFT':272, 'BTN_MIDDLE':274, 'BTN_MISC':256, 'BTN_MODE':316, 'BTN_MOUSE':272, 'BTN_NORTH':307, 'BTN_PINKIE':293, 'BTN_RIGHT':273, 'BTN_SELECT':314, 'BTN_SIDE':275, 'BTN_SOUTH':304, 'BTN_START':315, 'BTN_STYLUS':331, 'BTN_STYLUS2':332, 'BTN_STYLUS3':329, 'BTN_TASK':279, 'BTN_THUMB':289, 'BTN_THUMB2':290, 'BTN_THUMBL':317, 'BTN_THUMBR':318, 'BTN_TL':310, 'BTN_TL2':312, 'BTN_TOOL_AIRBRUSH':324, 'BTN_TOOL_BRUSH':322, 'BTN_TOOL_DOUBLETAP':333, 'BTN_TOOL_FINGER':325, 'BTN_TOOL_LENS':327, 'BTN_TOOL_MOUSE':326, 'BTN_TOOL_PEN':320, 'BTN_TOOL_PENCIL':323, 'BTN_TOOL_QUADTAP':335, 'BTN_TOOL_QUINTTAP':328, 'BTN_TOOL_RUBBER':321, 'BTN_TOOL_TRIPLETAP':334, 'BTN_TOP':291, 'BTN_TOP2':292, 'BTN_TOUCH':330, 'BTN_TR':311, 'BTN_TR2':313, 'BTN_TRIGGER':288, 'BTN_TRIGGER_HAPPY':704, 'BTN_TRIGGER_HAPPY1':704, 'BTN_TRIGGER_HAPPY10':713, 'BTN_TRIGGER_HAPPY11':714, 'BTN_TRIGGER_HAPPY12':715, 'BTN_TRIGGER_HAPPY13':716, 'BTN_TRIGGER_HAPPY14':717, 'BTN_TRIGGER_HAPPY15':718, 'BTN_TRIGGER_HAPPY16':719, 'BTN_TRIGGER_HAPPY17':720, 'BTN_TRIGGER_HAPPY18':721, 'BTN_TRIGGER_HAPPY19':722, 'BTN_TRIGGER_HAPPY2':705, 'BTN_TRIGGER_HAPPY20':723, 'BTN_TRIGGER_HAPPY21':724, 'BTN_TRIGGER_HAPPY22':725, 'BTN_TRIGGER_HAPPY23':726, 'BTN_TRIGGER_HAPPY24':727, 'BTN_TRIGGER_HAPPY25':728, 'BTN_TRIGGER_HAPPY26':729, 'BTN_TRIGGER_HAPPY27':730, 'BTN_TRIGGER_HAPPY28':731, 'BTN_TRIGGER_HAPPY29':732, 'BTN_TRIGGER_HAPPY3':706, 'BTN_TRIGGER_HAPPY30':733, 'BTN_TRIGGER_HAPPY31':734, 'BTN_TRIGGER_HAPPY32':735, 'BTN_TRIGGER_HAPPY33':736, 'BTN_TRIGGER_HAPPY34':737, 'BTN_TRIGGER_HAPPY35':738, 'BTN_TRIGGER_HAPPY36':739, 'BTN_TRIGGER_HAPPY37':740, 'BTN_TRIGGER_HAPPY38':741, 'BTN_TRIGGER_HAPPY39':742, 'BTN_TRIGGER_HAPPY4':707, 'BTN_TRIGGER_HAPPY40':743, 'BTN_TRIGGER_HAPPY5':708, 'BTN_TRIGGER_HAPPY6':709, 'BTN_TRIGGER_HAPPY7':710, 'BTN_TRIGGER_HAPPY8':711, 'BTN_TRIGGER_HAPPY9':712, 'BTN_WEST':308, 'BTN_WHEEL':336, 'BTN_X':307, 'BTN_Y':308, 'BTN_Z':309, 'EV_ABS':3, 'EV_CNT':32, 'EV_FF':21, 'EV_FF_STATUS':23, 'EV_KEY':1, 'EV_LED':17, 'EV_MAX':31, 'EV_MSC':4, 'EV_PWR':22, 'EV_REL':2, 'EV_REP':20, 'EV_SND':18, 'EV_SW':5, 'EV_SYN':0, 'EV_UINPUT':257, 'EV_VERSION':65537, 'KEY_0':11, 'KEY_1':2, 'KEY_102ND':86, 'KEY_10CHANNELSDOWN':441, 'KEY_10CHANNELSUP':440, 'KEY_2':3, 'KEY_3':4, 'KEY_3D_MODE':623, 'KEY_4':5, 'KEY_5':6, 'KEY_6':7, 'KEY_7':8, 'KEY_8':9, 'KEY_9':10, 'KEY_A':30, 'KEY_AB':406, 'KEY_ADDRESSBOOK':429, 'KEY_AGAIN':129, 'KEY_ALS_TOGGLE':560, 'KEY_ALTERASE':222, 'KEY_ANGLE':371, 'KEY_APOSTROPHE':40, 'KEY_APPSELECT':580, 'KEY_ARCHIVE':361, 'KEY_ASSISTANT':583, 'KEY_ATTENDANT_OFF':540, 'KEY_ATTENDANT_ON':539, 'KEY_ATTENDANT_TOGGLE':541, 'KEY_AUDIO':392, 'KEY_AUDIO_DESC':622, 'KEY_AUX':390, 'KEY_B':48, 'KEY_BACK':158, 'KEY_BACKSLASH':43, 'KEY_BACKSPACE':14, 'KEY_BASSBOOST':209, 'KEY_BATTERY':236, 'KEY_BLUE':401, 'KEY_BLUETOOTH':237, 'KEY_BOOKMARKS':156, 'KEY_BREAK':411, 'KEY_BRIGHTNESSDOWN':224, 'KEY_BRIGHTNESSUP':225, 'KEY_BRIGHTNESS_AUTO':244, 'KEY_BRIGHTNESS_CYCLE':243, 'KEY_BRIGHTNESS_MAX':593, 'KEY_BRIGHTNESS_MIN':592, 'KEY_BRIGHTNESS_TOGGLE':431, 'KEY_BRIGHTNESS_ZERO':244, 'KEY_BRL_DOT1':497, 'KEY_BRL_DOT10':506, 'KEY_BRL_DOT2':498, 'KEY_BRL_DOT3':499, 'KEY_BRL_DOT4':500, 'KEY_BRL_DOT5':501, 'KEY_BRL_DOT6':502, 'KEY_BRL_DOT7':503, 'KEY_BRL_DOT8':504, 'KEY_BRL_DOT9':505, 'KEY_BUTTONCONFIG':576, 'KEY_C':46, 'KEY_CALC':140, 'KEY_CALENDAR':397, 'KEY_CAMERA':212, 'KEY_CAMERA_DOWN':536, 'KEY_CAMERA_FOCUS':528, 'KEY_CAMERA_LEFT':537, 'KEY_CAMERA_RIGHT':538, 'KEY_CAMERA_UP':535, 'KEY_CAMERA_ZOOMIN':533, 'KEY_CAMERA_ZOOMOUT':534, 'KEY_CANCEL':223, 'KEY_CAPSLOCK':58, 'KEY_CD':383, 'KEY_CHANNEL':363, 'KEY_CHANNELDOWN':403, 'KEY_CHANNELUP':402, 'KEY_CHAT':216, 'KEY_CLEAR':355, 'KEY_CLOSE':206, 'KEY_CLOSECD':160, 'KEY_CNT':768, 'KEY_COFFEE':152, 'KEY_COMMA':51, 'KEY_COMPOSE':127, 'KEY_COMPUTER':157, 'KEY_CONFIG':171, 'KEY_CONNECT':218, 'KEY_CONTEXT_MENU':438, 'KEY_CONTROLPANEL':579, 'KEY_COPY':133, 'KEY_CUT':137, 'KEY_CYCLEWINDOWS':154, 'KEY_D':32, 'KEY_DASHBOARD':204, 'KEY_DATA':631, 'KEY_DATABASE':426, 'KEY_DELETE':111, 'KEY_DELETEFILE':146, 'KEY_DEL_EOL':448, 'KEY_DEL_EOS':449, 'KEY_DEL_LINE':451, 'KEY_DIGITS':413, 'KEY_DIRECTION':153, 'KEY_DIRECTORY':394, 'KEY_DISPLAYTOGGLE':431, 'KEY_DISPLAY_OFF':245, 'KEY_DOCUMENTS':235, 'KEY_DOLLAR':434, 'KEY_DOT':52, 'KEY_DOWN':108, 'KEY_DVD':389, 'KEY_E':18, 'KEY_EDIT':176, 'KEY_EDITOR':422, 'KEY_EJECTCD':161, 'KEY_EJECTCLOSECD':162, 'KEY_EMAIL':215, 'KEY_END':107, 'KEY_ENTER':28, 'KEY_EPG':365, 'KEY_EQUAL':13, 'KEY_ESC':1, 'KEY_EURO':435, 'KEY_EXIT':174, 'KEY_F':33, 'KEY_F1':59, 'KEY_F10':68, 'KEY_F11':87, 'KEY_F12':88, 'KEY_F13':183, 'KEY_F14':184, 'KEY_F15':185, 'KEY_F16':186, 'KEY_F17':187, 'KEY_F18':188, 'KEY_F19':189, 'KEY_F2':60, 'KEY_F20':190, 'KEY_F21':191, 'KEY_F22':192, 'KEY_F23':193, 'KEY_F24':194, 'KEY_F3':61, 'KEY_F4':62, 'KEY_F5':63, 'KEY_F6':64, 'KEY_F7':65, 'KEY_F8':66, 'KEY_F9':67, 'KEY_FASTFORWARD':208, 'KEY_FASTREVERSE':629, 'KEY_FAVORITES':364, 'KEY_FILE':144, 'KEY_FINANCE':219, 'KEY_FIND':136, 'KEY_FIRST':404, 'KEY_FN':464, 'KEY_FN_1':478, 'KEY_FN_2':479, 'KEY_FN_B':484, 'KEY_FN_D':480, 'KEY_FN_E':481, 'KEY_FN_ESC':465, 'KEY_FN_F':482, 'KEY_FN_F1':466, 'KEY_FN_F10':475, 'KEY_FN_F11':476, 'KEY_FN_F12':477, 'KEY_FN_F2':467, 'KEY_FN_F3':468, 'KEY_FN_F4':469, 'KEY_FN_F5':470, 'KEY_FN_F6':471, 'KEY_FN_F7':472, 'KEY_FN_F8':473, 'KEY_FN_F9':474, 'KEY_FN_S':483, 'KEY_FORWARD':159, 'KEY_FORWARDMAIL':233, 'KEY_FRAMEBACK':436, 'KEY_FRAMEFORWARD':437, 'KEY_FRONT':132, 'KEY_G':34, 'KEY_GAMES':417, 'KEY_GOTO':354, 'KEY_GRAPHICSEDITOR':424, 'KEY_GRAVE':41, 'KEY_GREEN':399, 'KEY_H':35, 'KEY_HANGEUL':122, 'KEY_HANGUEL':122, 'KEY_HANJA':123, 'KEY_HELP':138, 'KEY_HENKAN':92, 'KEY_HIRAGANA':91, 'KEY_HOME':102, 'KEY_HOMEPAGE':172, 'KEY_HP':211, 'KEY_I':23, 'KEY_IMAGES':442, 'KEY_INFO':358, 'KEY_INSERT':110, 'KEY_INS_LINE':450, 'KEY_ISO':170, 'KEY_J':36, 'KEY_JOURNAL':578, 'KEY_K':37, 'KEY_KATAKANA':90, 'KEY_KATAKANAHIRAGANA':93, 'KEY_KBDILLUMDOWN':229, 'KEY_KBDILLUMTOGGLE':228, 'KEY_KBDILLUMUP':230, 'KEY_KBDINPUTASSIST_ACCEPT':612, 'KEY_KBDINPUTASSIST_CANCEL':613, 'KEY_KBDINPUTASSIST_NEXT':609, 'KEY_KBDINPUTASSIST_NEXTGROUP':611, 'KEY_KBDINPUTASSIST_PREV':608, 'KEY_KBDINPUTASSIST_PREVGROUP':610, 'KEY_KEYBOARD':374, 'KEY_KP0':82, 'KEY_KP1':79, 'KEY_KP2':80, 'KEY_KP3':81, 'KEY_KP4':75, 'KEY_KP5':76, 'KEY_KP6':77, 'KEY_KP7':71, 'KEY_KP8':72, 'KEY_KP9':73, 'KEY_KPASTERISK':55, 'KEY_KPCOMMA':121, 'KEY_KPDOT':83, 'KEY_KPENTER':96, 'KEY_KPEQUAL':117, 'KEY_KPJPCOMMA':95, 'KEY_KPLEFTPAREN':179, 'KEY_KPMINUS':74, 'KEY_KPPLUS':78, 'KEY_KPPLUSMINUS':118, 'KEY_KPRIGHTPAREN':180, 'KEY_KPSLASH':98, 'KEY_L':38, 'KEY_LANGUAGE':368, 'KEY_LAST':405, 'KEY_LEFT':105, 'KEY_LEFTALT':56, 'KEY_LEFTBRACE':26, 'KEY_LEFTCTRL':29, 'KEY_LEFTMETA':125, 'KEY_LEFTSHIFT':42, 'KEY_LEFT_DOWN':617, 'KEY_LEFT_UP':616, 'KEY_LIGHTS_TOGGLE':542, 'KEY_LINEFEED':101, 'KEY_LIST':395, 'KEY_LOGOFF':433, 'KEY_M':50, 'KEY_MACRO':112, 'KEY_MAIL':155, 'KEY_MAX':767, 'KEY_MEDIA':226, 'KEY_MEDIA_REPEAT':439, 'KEY_MEDIA_TOP_MENU':619, 'KEY_MEMO':396, 'KEY_MENU':139, 'KEY_MESSENGER':430, 'KEY_MHP':367, 'KEY_MICMUTE':248, 'KEY_MINUS':12, 'KEY_MIN_INTERESTING':113, 'KEY_MODE':373, 'KEY_MOVE':175, 'KEY_MP3':391, 'KEY_MSDOS':151, 'KEY_MUHENKAN':94, 'KEY_MUTE':113, 'KEY_N':49, 'KEY_NEW':181, 'KEY_NEWS':427, 'KEY_NEXT':407, 'KEY_NEXTSONG':163, 'KEY_NEXT_FAVORITE':624, 'KEY_NUMERIC_0':512, 'KEY_NUMERIC_1':513, 'KEY_NUMERIC_11':620, 'KEY_NUMERIC_12':621, 'KEY_NUMERIC_2':514, 'KEY_NUMERIC_3':515, 'KEY_NUMERIC_4':516, 'KEY_NUMERIC_5':517, 'KEY_NUMERIC_6':518, 'KEY_NUMERIC_7':519, 'KEY_NUMERIC_8':520, 'KEY_NUMERIC_9':521, 'KEY_NUMERIC_A':524, 'KEY_NUMERIC_B':525, 'KEY_NUMERIC_C':526, 'KEY_NUMERIC_D':527, 'KEY_NUMERIC_POUND':523, 'KEY_NUMERIC_STAR':522, 'KEY_NUMLOCK':69, 'KEY_O':24, 'KEY_OK':352, 'KEY_ONSCREEN_KEYBOARD':632, 'KEY_OPEN':134, 'KEY_OPTION':357, 'KEY_P':25, 'KEY_PAGEDOWN':109, 'KEY_PAGEUP':104, 'KEY_PASTE':135, 'KEY_PAUSE':119, 'KEY_PAUSECD':201, 'KEY_PAUSE_RECORD':626, 'KEY_PC':376, 'KEY_PHONE':169, 'KEY_PLAY':207, 'KEY_PLAYCD':200, 'KEY_PLAYER':387, 'KEY_PLAYPAUSE':164, 'KEY_POWER':116, 'KEY_POWER2':356, 'KEY_PRESENTATION':425, 'KEY_PREVIOUS':412, 'KEY_PREVIOUSSONG':165, 'KEY_PRINT':210, 'KEY_PROG1':148, 'KEY_PROG2':149, 'KEY_PROG3':202, 'KEY_PROG4':203, 'KEY_PROGRAM':362, 'KEY_PROPS':130, 'KEY_PVR':366, 'KEY_Q':16, 'KEY_QUESTION':214, 'KEY_R':19, 'KEY_RADIO':385, 'KEY_RECORD':167, 'KEY_RED':398, 'KEY_REDO':182, 'KEY_REFRESH':173, 'KEY_REPLY':232, 'KEY_RESERVED':0, 'KEY_RESTART':408, 'KEY_REWIND':168, 'KEY_RFKILL':247, 'KEY_RIGHT':106, 'KEY_RIGHTALT':100, 'KEY_RIGHTBRACE':27, 'KEY_RIGHTCTRL':97, 'KEY_RIGHTMETA':126, 'KEY_RIGHTSHIFT':54, 'KEY_RIGHT_DOWN':615, 'KEY_RIGHT_UP':614, 'KEY_RO':89, 'KEY_ROOT_MENU':618, 'KEY_ROTATE_DISPLAY':153, 'KEY_S':31, 'KEY_SAT':381, 'KEY_SAT2':382, 'KEY_SAVE':234, 'KEY_SCALE':120, 'KEY_SCREEN':375, 'KEY_SCREENLOCK':152, 'KEY_SCREENSAVER':581, 'KEY_SCROLLDOWN':178, 'KEY_SCROLLLOCK':70, 'KEY_SCROLLUP':177, 'KEY_SEARCH':217, 'KEY_SELECT':353, 'KEY_SEMICOLON':39, 'KEY_SEND':231, 'KEY_SENDFILE':145, 'KEY_SETUP':141, 'KEY_SHOP':221, 'KEY_SHUFFLE':410, 'KEY_SLASH':53, 'KEY_SLEEP':142, 'KEY_SLOW':409, 'KEY_SLOWREVERSE':630, 'KEY_SOUND':213, 'KEY_SPACE':57, 'KEY_SPELLCHECK':432, 'KEY_SPORT':220, 'KEY_SPREADSHEET':423, 'KEY_STOP':128, 'KEY_STOPCD':166, 'KEY_STOP_RECORD':625, 'KEY_SUBTITLE':370, 'KEY_SUSPEND':205, 'KEY_SWITCHVIDEOMODE':227, 'KEY_SYSRQ':99, 'KEY_T':20, 'KEY_TAB':15, 'KEY_TAPE':384, 'KEY_TASKMANAGER':577, 'KEY_TEEN':414, 'KEY_TEXT':388, 'KEY_TIME':359, 'KEY_TITLE':369, 'KEY_TOUCHPAD_OFF':532, 'KEY_TOUCHPAD_ON':531, 'KEY_TOUCHPAD_TOGGLE':530, 'KEY_TUNER':386, 'KEY_TV':377, 'KEY_TV2':378, 'KEY_TWEN':415, 'KEY_U':22, 'KEY_UNDO':131, 'KEY_UNKNOWN':240, 'KEY_UNMUTE':628, 'KEY_UP':103, 'KEY_UWB':239, 'KEY_V':47, 'KEY_VCR':379, 'KEY_VCR2':380, 'KEY_VENDOR':360, 'KEY_VIDEO':393, 'KEY_VIDEOPHONE':416, 'KEY_VIDEO_NEXT':241, 'KEY_VIDEO_PREV':242, 'KEY_VOD':627, 'KEY_VOICECOMMAND':582, 'KEY_VOICEMAIL':428, 'KEY_VOLUMEDOWN':114, 'KEY_VOLUMEUP':115, 'KEY_W':17, 'KEY_WAKEUP':143, 'KEY_WIMAX':246, 'KEY_WLAN':238, 'KEY_WORDPROCESSOR':421, 'KEY_WPS_BUTTON':529, 'KEY_WWAN':246, 'KEY_WWW':150, 'KEY_X':45, 'KEY_XFER':147, 'KEY_Y':21, 'KEY_YELLOW':400, 'KEY_YEN':124, 'KEY_Z':44, 'KEY_ZENKAKUHANKAKU':85, 'KEY_ZOOM':372, 'KEY_ZOOMIN':418, 'KEY_ZOOMOUT':419, 'KEY_ZOOMRESET':420, 'REL_CNT':16, 'REL_DIAL':7, 'REL_HWHEEL':6, 'REL_MAX':15, 'REL_MISC':9, 'REL_RX':3, 'REL_RY':4, 'REL_RZ':5, 'REL_WHEEL':8, 'REL_X':0, 'REL_Y':1, 'REL_Z':2, }
codes = type("codes", (object,), codesDict)

def name2code(name):
  return codesDict[name]


def split_full_name(s, sep="."):
  """
  'mouse.REL_X' -> ('mouse', 'REL_X')
  'REL_X' -> (None, 'REL_X')
  """
  i = s.find(sep)
  return (None, s) if i == -1 else (s[:i], s[i+1:])


def split_full_name_code(s, sep="."):
  """
  'mouse.REL_X' -> ('mouse', codes.REL_X)
  'REL_X' -> (None, codes.REL_X)
  """
  r = split_full_name(s, sep)
  return (r[0], name2code(r[1]))


class ReloadException(Exception):
  pass

class CompositeJoystick:
  def move_axis(self, axis, v, relative):
    for c in self.children_:
      c.move_axis(axis, v, relative)

  #TODO Come up with something better
  def get_axis(self, axis):
    if len(self.children_):
      return self.children_[0].get_axis(axis)
    else:
      return 0.0

  #TODO Come up with something better
  def get_limits(self, axis):
    if len(self.children_):
      return self.children_[0].get_limits(axis)
    else:
      return (0.0, 0.0)

  #TODO Come up with something better
  def get_supported_axes(self):
    if len(self.children_):
      return self.children_[0].get_supported_axes()
    else:
      return []

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
    #Had to reference members of parent class directly, because FreePie does not handle super() well
    return "type: {}, code: {}, value: {}, timestamp: {}, source: {}, modifiers: {}".format(self.type, self.code, self.value, self.timestamp, self.source, self.modifiers) 
    #these do not work in FreePie
    #return super(InputEvent, self).__str__() + ", source: {}, modifiers: {}".format(self.source, self.modifiers)
    #return super(InputEvent, Event).__str__() + ", source: {}, modifiers: {}".format(self.source, self.modifiers)
    #return super().__str__() + ", source: {}, modifiers: {}".format(self.source, self.modifiers)
    #return Event.__str__(self) + ", source: {}, modifiers: {}".format(self.source, self.modifiers)
    #return "source: {}, modifiers: {}".format(self.source, self.modifiers)

  def __init__(self, t, code, value, timestamp, source, modifiers = None):
    #Had to reference members of parent class directly, because FreePie does not handle super() well
    #This does not work in FreePie
    #super().__init__(t, code, value, timestamp)
    self.type, self.code, self.value, self.timestamp = t, code, value, timestamp
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
      #logger.debug("{}: Sending event: {}".format(self, event))
      self.sink_(event)

  def __init__(self, devices, sink):
    self.devices_, self.sink_ = devices, sink
    logger.debug("{} created".format(self))

  def __del__(self):
    logger.debug("{} destroyed".format(self))


class Loop:
  def run_once(self):
    if self.t_ == None:
      self.t_ = time.time()
    ct = time.time()
    dt = ct - self.t_
    self.t_ = ct
    for c in self.callbacks_:
      c(dt)
    time.sleep(max(self.step_ - (time.time() - ct), 0))
      
  def run(self):
    self.t_ = time.time()
    while (True):
      self.run_once()

  def __init__(self, callbacks, step):
    self.callbacks_, self.step_ = callbacks, step
    self.t_ = None


class MoveJoystickAxis:
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
      self.curve_.move_by(event.value, event.timestamp)
      return True
    else:
      return False

  def __init__(self, curve):
    self.curve_ = curve


class SetJoystickAxis:
  def __init__(self, joystick, axis, value):
    self.js_, self.axis_, self.value_ = joystick, axis, value
    logger.debug("{} created".format(self))

  def __del__(self):
    logger.debug("{} destroyed".format(self))
  
  def __call__(self, event):
    self.js_.move_axis(self.axis_, self.value_, False) 
    return True


def SetJoystickAxes(joystick, axesAndValues):
  def op(event):
    for axis, value in axesAndValues:
      joystick.move_axis(axis, value, False) 
    return True
  return op


def SetCurveAxis(curve, value):
  def op(event):
    curve.get_axis().move(value, False) 
    return True
  def noneOp(event):
    return False
  return op if curve is not None else noneOp


def SetCurveAxis2(curve, value, relative=False, reset=False):
  def op(event):
    curve.move_axis(value, relative, reset)
    return True
  def noneOp(event):
    return False
  return op if curve is not None else noneOp


def SetCurvesAxes(*curvesAndValues):
  def op(event):
    for curve, value in curvesAndValues:
      if curve is not None: 
        curve.get_axis().move(value, False) 
    return True
  return op


def SetCurvesAxes2(curvesData):
  def op(event):
    for curve, value, relative, reset in curvesData:
      if curve is not None: 
        curve.move_axis(value, relative, reset) 
    return True
  return op
  
  
def ResetCurve(curve):
  def op(event):
    curve.reset()
    return True
  def noneOp(event):
    return False
  return op if curve is not None else noneOp


def ResetCurves(curves):
  def op(event):
    for curve in curves:
      if curve is not None: 
        #logger.debug("Resetting curve: {}".format(curve))
        curve.reset()
    return True
  return op


def MoveAxis(axis, value, relative=False):
  def op(event):
    if axis is not None:
      axis.move(value, relative)
    return True
  return op 


def MoveAxes(axesAndValues):
  def moveAxesOp(event):
    for axis,value,relative in axesAndValues:
      axis.move(value, relative) 
  return moveAxesOp


def SetButtonState(joystick, button, state):
  def op(event):
    joystick.set_button_state(button, state) 
    #logger.debug(button, state)
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
      #logger.debug("{} {}".format(event.code, event.value))
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
      p = (event.source, event.code)
      if self.modifiers_ is not None: 
        for m in self.modifiers_:
          if p == m or (m[0] is None and p[1] == m[1]):
            if event.value == 1 and p not in self.m_:
              self.m_.append(p)
            elif event.value == 0 and p in self.m_:
              self.m_.remove(p)

    if self.next_ and event.type in (codes.EV_KEY, codes.EV_REL, codes.EV_ABS):
      event.modifiers = self.m_ 

    #logger.debug("{}: passing event {} to {}".format(self, event, self.next_))
    return self.next_(event)

  def set_next(self, next):
    self.next_ = next
    return next

  def clear(self):
    self.m_ = []

  def __init__(self, next = None, modifiers = None):
    self.m_, self.next_, self.modifiers_ = [], next, modifiers


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


class ScaleSink2:
  def __call__(self, event):
    if event.type in (codes.EV_REL, codes.EV_ABS):
      if self.sens_ is not None:
        keys = self.keyOp_(event)
        event.value *= self.sens_.get(keys[0], self.sens_.get(keys[1], 1.0))
    return self.next_(event) if self.next_ is not None else False

  def set_next(self, next):
    self.next_ = next
    return next

  def __init__(self, sens, keyOp = lambda event : ((event.source, event.code), (None, event.code))):
    self.next_, self.sens_, self.keyOp_ = None, sens, keyOp


class BindSink:
  def __call__(self, event):
    #logger.debug("{}: processing {})".format(self, event))
    if self.dirty_ == True:
      self.children_.sort(key=lambda c : c[1])
      self.dirty_ = False

    if len(self.children_) == 0:
      return False

    assert(self.cmp_)
    level, processed = self.children_[0][1], False
    for c in self.children_:
      if c[1] > level:
        if processed == True:
          return True
        else:
          level = c[1]
      for attrName, attrValue in c[0]:
         if hasattr(event, attrName):
            eventValue = getattr(event, attrName)
            if not self.cmp_(attrName, eventValue, attrValue):
              #logger.debug("{}: Mismatch while matching {} at {} (got {}, needed {})".format(self, c[0], attrName, eventValue, attrValue))
              break
         else:
          break
      else:
        #logger.debug("{}: {} matched".format(self, c[0]))
        if c[2] is not None: 
          #logger.debug("Processing event {}".format(str(event)))
          for cc in c[2]:
            #logger.debug("Sending event {} to {}".format(str(event), cc))
            processed = cc(event) or processed
    return processed

  def add(self, attrs, child, level = 0):
    #logger.debug("{}: Adding child {} to {} for level {}".format(self, child, attrs, level))
    assert(child is not None)
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
          r.append(("code", name2code(inpt)))
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
          modifiers.append((source, name2code(inpt)))
    if modifiers is not None:
      r.append(("modifiers", modifiers))
    #logger.debug("ED3.parse(): {} -> {}".format(s, r)) 
    return r


class StateSink:
 def __call__(self, event):
   #logger.debug("{}: passing event: {}, state: {}, next: {}".format(self, event, self.state_, self.next_))
   if (self.state_ == True) and (self.next_ is not None):
     self.next_(event)

 def set_state(self, state):
   #logger.debug("{}: setting state to {}".format(self, state))
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
    return True
  return op
    
    
class ModeSink:
  def __call__(self, event):
    child = self.children_.get(self.mode_, None)
    if child is not None:
      return child(event)
    else:
      return False

  def set_mode(self, mode):
    #logger.debug("{}: Setting mode: {}".format(self, mode))
    if mode not in self.children_:
      #logger.debug("{}: No such mode: {}".format(self, mode))
      return False
    self.set_active_child_state_(False)
    self.mode_ = mode
    self.set_active_child_state_(True)

  def get_mode(self):
    return self.mode_

  def add(self, mode, child):
    #logger.debug("{}: Adding child {} to  mode {}".format(self, child, mode))
    self.children_[mode] = child
    return child

  def set_active_child_state_(self, state):
    if self.mode_ in self.children_:
      child = self.children_.get(self.mode_, None)
      if child is not None:
        #logger.debug("{}: Notifying child {} about setting state to {}".format(self, child, state))
        child(Event(EV_BCAST, BC_INIT, 1 if state == True else 0, time.time()))
    
  def __init__(self):
    self.children_, self.mode_ = {}, None


class CycleMode:
  def __call__(self, event):
    self.i += 1
    if self.i >= len(self.modes):
      self.i = 0
    self.modeSink.set_mode(self.modes[self.i])
    return True

  def __init__(self, modeSink, modes):
    self.i, self.modeSink, self.modes = 0, modeSink, modes


class SetMode:
  def __call__(self, event):
    self.modeSink.set_mode(self.mode)
    return True
    
  def __init__(self, modeSink, mode):
    self.modeSink, self.mode = modeSink, mode

class MSMMSavePolicy:
   NOOP = 0
   SAVE = 1
   CLEAR = 2
   CLEAR_AND_SAVE = 3
  

def nameToMSMMSavePolicy(name):
  d = { 
    "noop" : MSMMSavePolicy.NOOP, 
    "save" : MSMMSavePolicy.SAVE, 
    "clear" : MSMMSavePolicy.CLEAR, 
    "clearAndSave" : MSMMSavePolicy.CLEAR_AND_SAVE
  }
  return d[name]


class ModeSinkModeManager:
  def save(self):
    self.mode_.append(self.sink_.get_mode())

  def restore(self):
    if len(self.mode_):
      self.sink_.set_mode(self.mode_.pop())

  def clear(self):
    self.mode_ = []

  def set(self, mode, save):
    self.save_(save)
    self.sink_.set_mode(mode)

  def cycle(self, modes, save):
    self.save_(save)
    m = self.sink_.get_mode()
    if m in modes:
      i = modes.index(m)+1
      if i >= len(modes): i = 0
      m = modes[i]
    else:
      m = modes[0]
    self.sink_.set_mode(m)

  def __init__(self, sink):
    self.sink_, self.mode_ = sink, []

  def make_save(self):
    def op(event):
      self.save()
      return True
    return op
  def make_restore(self):
    def op(event):
      self.restore()
      return True
    return op
  def make_clear(self):
    def op(event):
      self.clear()
      return True
    return op
  def make_set(self, mode, save):
    def op(event):
      self.set(mode, save)
      return True
    return op
  def make_cycle(self, modes, save):
    def op(event):
      self.cycle(modes, save)
      return True
    return op

  def save_(self, save):
    if save == MSMMSavePolicy.NOOP:
      pass
    elif save == MSMMSavePolicy.SAVE:
      self.save()
    elif save == MSMMSavePolicy.CLEAR:
      self.clear()
    elif save == MSMMSavePolicy.CLEAR_AND_SAVE:
      self.clear()
      self.save()
    else:
      assert(False)


class PowerApproximator:
  def __call__(self, v):
    return sign(v)*self.k*abs(v)**self.n

  def __init__(self, k, n):
    self.k, self.n = k, n


class ConstantApproximator:
  def __call__(self, v):
    return self.value_

  def __init__(self, value):
    self.value_ = value


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


def calc_bezier(points, t):
  """Uses points as scratch space."""
  for n in xrange(len(points)-1, 0, -1):
    for i in xrange(0, n):
      p0, p1 = points[i], points[i+1]
      points[i] = [t*p1v + (1.0-t)*p0v for p1v,p0v in zip(p1,p0)]
  return points[0]


class BezierApproximator:
  def __call__(self, x):
    l, r = self.points_[0][0], self.points_[len(self.points_)-1][0]
    x = clamp(x, l, r)
    t = (x - l) / (r - l)
    points = [p for p in self.points_]
    #logger.debug("{}: points: {}, t: {}".format(self, points, t))
    r = calc_bezier(points, t)[1]
    #logger.debug("{}: result: {: .3f}".format(self, r))
    return r

  def __init__(self, points):
    self.points_ = [(p[0],p[1]) for p in points]


class SegmentedBezierApproximator:
  def __call__(self, x):
    keys = [p["c"][0] for p in self.points_]
    i = bisect.bisect_left(keys, x)-1
    l = len(self.points_)
    i = clamp(i, 0, max(l-2, 0))
    j = clamp(i+1, 0, max(l-1, 0))

    leftPoints, rightPoints = self.points_[i], self.points_[j]
    l, r = leftPoints["c"][0], rightPoints["c"][0]
    x = clamp(x, l, r)
    t = (x - l) / (r - l)

    points = []
    points.append(leftPoints["c"])
    if "r" in leftPoints : points.append(leftPoints["r"])
    if "l" in rightPoints : points.append(rightPoints["l"])
    points.append(rightPoints["c"])

    #logger.debug("{}: points: {}".format(self, points))
    r = calc_bezier(points, t)[1]
    #logger.debug("{}: t: {: .3f}, result: {: .3f}".format(self, t, r))
    return r

  def __init__(self, points):
    self.points_ = [p for p in points]


class JoystickAxis:
  def move(self, v, relative):
    assert(self.j_)
    return self.j_.move_axis(self.a_, v, relative)

  def get(self):
    assert(self.j_)
    return self.j_.get_axis(self.a_)

  def limits(self):
    assert(self.j_)
    return self.j_.get_limits(self.a_)

  def __init__(self, j, a):
    assert(j)
    self.j_, self.a_ = j, a


class ReportingAxis:
  def move(self, v, relative):
    old = self.next_.get()
    self.next_.move(v, relative)
    new = self.next_.get()
    for c in self.listeners_:
      if c() is None: continue
      c().on_move_axis(self, old, new)
    #TODO Implement cleanup

  def get(self):
    return self.next_.get()

  def limits(self):
    return self.next_.limits()

  def add_listener(self, listener):
    self.listeners_.append(weakref.ref(listener))

  #TODO Implement remove_listener()

  def __init__(self, next):
    assert(next is not None)
    self.next_, self.listeners_ = next, []


class SecondOrderAxis:
  def move(self, v, relative):
    #logger.debug("{}: moving to {} {}".format(self, v, "relative" if relative else "absolute"))
    self.v_ = clamp(self.v_+v if relative is True else v, self.limits_[0], self.limits_[1])

  def get(self):
    return self.v_

  def limits(self):
    return self.limits_

  def update(self, tick):
    if self.next_ is None or self.v_ == 0.0:
      return 
    delta = self.deltaOp_(self.v_, tick)
    valueBeforeMove = self.next_.get()
    self.next_.move(delta, relative=True)
    if self.next_.get() == valueBeforeMove: 
      self.v_ = 0.0

  def set_next(self, next):
    self.next_ = next

  def __init__(self, next, deltaOp, limits):
    self.next_, self.deltaOp_, self.limits_ = next, deltaOp, limits
    self.v_ = 0.0

  
class Point:
  def calc(self, x):
    r = None if (x is None or self.center_ is None) else self.op_(x - self.center_)
    def prn(fmt, v):
      return "None" if v is None else fmt.format(v)
    #logger.debug("{}: center:{}, x:{: .3f}, result:{}".format(self, prn("{: .3f}", self.center_), x, prn("{: .3f}", r)))
    return r

  def get_center(self):
    return self.center_

  def set_center(self, center):
    self.center_ = center
    
  def reset(self):
    pass

  def __init__(self, op, center=None):
    self.op_ = op
    self.center_ = center


class OutputBasedCurve:
  def move_by(self, x, timestamp):
    assert(self.axis_ is not None)
    assert(self.valueOp_ is not None)
    assert(self.deltaOp_ is not None)
    #self.valueOp_ typically returns sensitivity based on current self.value_
    #self.deltaOp_ typically multiplies sensitivity by x (input delta) to produce output delta
    if self.dirty_:
      self.reset()
      self.dirty_ = False
    if x == 0:
      return 0.0
    value = self.axis_.get()
    baseValue = value
    sensitivity = self.valueOp_.calc(baseValue)
    if sensitivity is None:
      raise ArithmeticError("Cannot compute value, sensitivity is None")
    delta = self.deltaOp_(x, sensitivity)
    value = clamp(value + delta, *self.axis_.limits())
    delta = value - baseValue
    self.move_axis_(value=value, relative=False)
    #logger.debug( "{}: x:{: .3f}, base value:{: .3f}, sensitivity:{: .3f}, value delta:{: .3f}, new value:{: .3f}".format(self, x, baseValue, sensitivity, delta, value))
    return delta

  def reset(self):
    #logger.debug("{}: resetting".format(self))
    self.s_, self.busy_, self.dirty_  = 0, False, False
    assert(self.valueOp_ is not None)
    self.valueOp_.reset()
    #TODO Should also call self.deltaOp_?

  def get_axis(self):
    return self.axis_

  def on_move_axis(self, axis, old, new):
    assert(axis == self.axis_)
    if self.busy_ or self.dirty_: return
    self.dirty_ = True

  def __init__(self, deltaOp, valueOp, axis):
    assert(deltaOp is not None)
    assert(valueOp is not None)
    assert(axis is not None)
    self.deltaOp_, self.valueOp_, self.axis_ = deltaOp, valueOp, axis
    self.s_, self.busy_, self.dirty_  = 0, False, False

  def move_axis_(self, value, relative):
    try:
      self.busy_ = True
      self.axis_.move(value, relative)
    except:
      raise
    finally:
      self.busy_ = False


class PointMovingCurveResetPolicy:
  DONT_TOUCH = 0
  SET_TO_NONE = 1
  SET_TO_CURRENT = 2


class PointMovingCurve:
  def move_by(self, x, timestamp):
    if self.dirty_:
      self.after_move_axis_()
      self.dirty_ = False
      #logger.debug("{}: someone has moved axis, new point center: {}".format(self, self.point_.get_center()))
    #Setting new point center if x movement direction has changed
    s = sign(x)
    center, value = self.point_.get_center(), self.getValueOp_(self.next_)
    if s != 0:
      if self.s_ != 0 and self.s_ != s:
        c = value if center is None else self.centerOp_(value, center)
        #logger.debug("{}: sign has changed; new point center: {} (was: {})".format(self, c, center))
        self.point_.set_center(c)
      self.s_ = s
    r = None
    try:
      self.busy_ = True
      r = self.next_.move_by(x, timestamp)
    except:
      raise
    finally:
      self.busy_ = False 
    #logger.debug( "{}: point center:{}, value before move:{}, value after move:{}".format(self, self.point_.get_center(), value, self.getValueOp_(self.next_)))
    if center is not None:
      resetDistanceReached = abs(value - center) > self.resetDistance_
      cannotMove = r == 0.0
      if resetDistanceReached or cannotMove:
        self.point_.set_center(None)
        #logger.debug( "{}: {}; new point center: {} (was: {})".format( self, "reset distance reached" if resetDistanceReached else "cannot move", self.point_.get_center(), center))
    return r

  def reset(self):
    self.s_, self.busy_, self.dirty_ = 0, False, False
    #Need to disable controlled point by setting point center to None before resetting next_ curve
    #Will produce inconsistent results otherwise
    v = None
    if self.onReset_ in (PointMovingCurveResetPolicy.SET_TO_NONE, PointMovingCurveResetPolicy.SET_TO_CURRENT):
      self.point_.set_center(v)
    self.next_.reset()
    if self.onReset_ == PointMovingCurveResetPolicy.SET_TO_CURRENT:
      v = self.getValueOp_(self.next_)
      self.point_.set_center(v)
    #logger.debug("{}: direct reset, new point center: {}".format(self, v))

  def get_axis(self):
    return self.next_.get_axis()

  def on_move_axis(self, axis, old, new):
    #logger.debug("{}: on_move_axis({}, {}, {})".format(self, axis, old, new))
    if self.busy_ or self.dirty_: 
      #logger.debug("{}: on_move_axis(): {}{}".format(self, "busy " if self.busy_ else "", "dirty" if self.dirty_ else ""))
      return
    self.dirty_ = True
    self.next_.on_move_axis(axis, old, new)

  def __init__(self, next, point, getValueOp, centerOp=lambda new,old : 0.5*old+0.5*new, resetDistance=float("inf"), onReset=PointMovingCurveResetPolicy.DONT_TOUCH, onMove=PointMovingCurveResetPolicy.DONT_TOUCH):
    assert(next is not None)
    assert(point is not None)
    assert(getValueOp is not None)
    assert(centerOp is not None)
    self.next_, self.point_, self.getValueOp_, self.centerOp_, self.resetDistance_, self.onReset_, self.onMove_ = next, point, getValueOp, centerOp, resetDistance, onReset, onMove
    self.s_, self.busy_, self.dirty_ = 0, False, False

  def after_move_axis_(self):
    self.s_, self.busy_, self.dirty_ = 0, False, False
    if self.onMove_ in (PointMovingCurveResetPolicy.SET_TO_NONE, PointMovingCurveResetPolicy.SET_TO_CURRENT):
      self.point_.set_center(None)
    if self.onMove_ == PointMovingCurveResetPolicy.SET_TO_CURRENT:
      v = self.getValueOp_(self.next_)
      self.point_.set_center(v)
      

tuple2str = lambda t : "None" if t is None else "({: .3f}, {: .3f})".format(t[0], t[1]) 
float2str = lambda f : "None" if f is None else "{: .3f}".format(f) 


class ValuePointOp:
  def calc(self, value):
    #left and right will reference data of selected points
    #a point can be placed at center (or center can be None, then point is considiered inactive)
    #a point can compute some result based on passed value
    left, right = None, None
    #vp is the point being currently examined
    for vp in self.vps_:
      #Examined point data in form of (result, center)
      #It is possible to first select points based on their centers, 
      #but since points might change their state (i.e. centers) while computing result in calc(), result is computed first for each point considered
      #Computed result can also be None, which will mean that the point is inactive and should be skipped
      r = vp.calc(value)
      c = vp.get_center()
      p = (r, c)
      #logger.debug("{}: vp: {}, p: {}".format(self, vp, p))
      #Skipping inactive point
      if p[0] is None:
        continue
      delta = value - p[1]
      s = sign(delta)
      delta = abs(delta)
      #logger.debug("{}: value: {}, s: {}".format(self, value, s))
      pd = (p[0], delta) #pd in (result, delta)
      if s == 1 and (left is None or delta < left[1]): 
          left = pd
      elif s == -1 and (right is None or delta < right[1]): 
          right = pd
      else:
        #if delta sign is 0, so the center of the point considered is exactly at value,
        #first try to assign 
        if left is None: left = pd
        elif right is None: right = pd
        else:
          if left[1] < right[1]: right = pd
          else: left = pd

    r = None
    if left is None and right is None:
      r = None
    elif left is not None and right is not None:
      r = self.interpolateOp_(left, right)
    else:
      r = (left if right is None else right)[0]
    #logger.debug("{}: left: {}, right: {}, result: {}".format(self, tuple2str(left), tuple2str(right), float2str(r)))
    return r

  def reset(self):
    for vp in self.vps_:
      vp.reset()

  def __init__(self, vps, interpolateOp):
    self.vps_, self.interpolateOp_ = vps, interpolateOp


class SimpleValuePointOp:
  def calc(self, value):
    rc = []
    for vp in self.vps_:
      r = vp.calc(value)
      if r is None: continue
      c = vp.get_center()
      if c is None: continue
      rc.append((r,c))
    result = None
    l = len(rc)
    if l == 0:
      result = None
    elif l == 1:
      result = rc[0][0]
    else:
      rc = [(r,abs(value-c)) for r,c in rc]
      result = self.interpolateOp_(*rc)
    #logger.debug("{}: rc: {}, result: {}".format(self, ["({: .3f} {: .3f})".format(*r) if r is not None else "None" for r in rc], float2str(result)))
    return result

  def reset(self):
    for vp in self.vps_:
      vp.reset()

  def __init__(self, vps, interpolateOp):
    self.vps_, self.interpolateOp_ = vps, interpolateOp 


def interpolate_op(left, right):
  leftDelta, rightDelta = left[1], right[1] #absolute values of deltas
  if leftDelta == 0.0 and rightDelta == 0.0:
    leftDelta, rightDelta = 0.5, 0.5
  totalDelta = leftDelta + rightDelta
  #interpolating (sort of)
  #left value is multiplied by right fraction of deltas sum and vice versa
  r = rightDelta/totalDelta*left[0] + leftDelta/totalDelta*right[0] 
  return r


def get_min_op(left, right):
  return min(left[0], right[0])


def multiply_op(left, right):
  return left[0]*right[0]


class InputBasedCurve:
  def move_by(self, x, timestamp):
    if self.dirty_:
      self.reset()
      self.dirty_ = False
    pos = clamp(self.pos_ + x, *self.posLimits_)
    if pos == self.pos_:
      return
    self.pos_ = pos
    value = self.op_.calc_value(self.pos_)
    self.move_axis_(value, relative=False)

  def reset(self):
    #logger.debug("{}: resetting".format(self))
    self.op_.reset()
    #TODO Check that it does not break something
    self.pos_ = self.op_.calc_pos(self.axis_.get())
    #TODO Needed?
    self.busy_, self.dirty_ = False, False

  def get_axis(self):
    return self.axis_

  def on_move_axis(self, axis, old, new):
    if self.busy_ or self.dirty_: return
    assert(axis == self.axis_)
    assert(new == self.axis_.get())
    self.dirty_ = True

  def get_pos(self):
    return self.pos_

  def __init__(self, op, axis, posLimits=(-1.0, 1.0)):
    self.op_, self.axis_, self.posLimits_ = op, axis, posLimits
    self.pos_ = self.op_.calc_pos(self.axis_.get())
    self.busy_, self.dirty_ = False, False

  def move_axis_(self, value, relative):
    try:
      self.busy_ = True
      self.axis_.move(value, relative)
    except:
      raise
    finally:
      self.busy_ = False


class IterativeCenterOp:
  """For PointMovingCurve"""
  def __call__(self, pos, center):
    assert(self.point_ is not None)
    assert(self.op_ is not None)
    currentValue = self.op_.calc_value(pos)
    b,e = (pos,center) if pos < center else (center,pos)
    for c in xrange(100):
      middle = 0.5*b + 0.5*e
      self.point_.set_center(middle)
      value = self.op_.calc_value(pos)
      if abs(currentValue - value) < self.eps_:
        #logger.debug("{}: old mp center: {: .3f}; new mp center: {: .3f}; value: {: .3f}; iterations: {}".format(self, center, middle, value, c+1))
        return middle
      elif currentValue < value:
        e = middle
      else:
        b = middle
    return middle

  def __init__(self, point, op, eps=0.01):
    assert(point is not None)
    assert(op is not None)
    self.point_, self.op_, self.eps_ = point, op, eps


class FMPosInterpolateOp:
  def calc_value(self, pos):
    assert(self.fp_ is not None)
    if self.mp_ is None:
      return self.fp_.calc(pos)
    fixedValueAtPos, movingValueAtPos = self.fp_.calc(pos), self.mp_.calc(pos)
    #logger.debug("{}: pos:{: .3f}, moving value at pos:{}, moving center:{}".format(self, pos, movingValueAtPos, self.mp_.get_center()))
    if movingValueAtPos is None:
      #logger.debug("{}: movingValueAtPos is None, f:{}".format(self, fixedValueAtPos))
      return fixedValueAtPos
    movingCenter = self.mp_.get_center()
    assert(movingCenter is not None) #since movingValueAtPos is not None, movingCenter cannot be None
    fixedValueAtMovingCenter = self.fp_.calc(movingCenter)
    movingValueAtPos += fixedValueAtMovingCenter
    deltaPos, deltaFC = pos - movingCenter, self.fp_.get_center() - movingCenter
    interpolationDistance = self.interpolationDistance_
    if sign(deltaPos) == sign(deltaFC):
      interpolationDistance = min(interpolationDistance, abs(deltaFC))
    deltaPos = abs(deltaPos)
    if deltaPos == 0.0 or deltaPos > interpolationDistance:
      #logger.debug("{}: {}, f:{: .3f}".format(self, "deltaPos == 0.0" if deltaPos == 0.0 else "deltaPos > interpolationDistance" if deltaPos > interpolationDistance else "unknown", fixedValueAtPos))
      return fixedValueAtPos
    fixedSlope, movingSlope = abs(fixedValueAtPos-fixedValueAtMovingCenter)/deltaPos, abs(movingValueAtPos-fixedValueAtMovingCenter)/deltaPos
    if fixedSlope < movingSlope:
      #logger.debug("{}: fixedSlope < movingSlope, f:{: .3f}".format(self, fixedValueAtPos))
      return fixedValueAtPos
    distanceFraction = (deltaPos / interpolationDistance)**self.factor_
    value = fixedValueAtPos*distanceFraction + movingValueAtPos*(1.0-distanceFraction) 
    #logger.debug("{}: pos:{: .3f}, f:{: .3f}, m:{: .3f}, interpolated:{: .3f}".format(self, pos, fixedValueAtPos, movingValueAtPos, value))
    return value

  def calc_pos(self, value):
    b,e = self.posLimits_
    m = 0.0
    for c in xrange(100):
      m = 0.5*b + 0.5*e
      v = self.calc_value(m)
      #logger.debug("{}: target:{: .3f}, v:{: .3f}, b:{: .3f}, m:{: .3f}, e:{: .3f}".format(self, value, v, b, m, e))
      if abs(v - value) < self.eps_: break
      elif v < value: b = m
      else: e = m
    #logger.debug("{}: value:{: .3f}, result:{: .3f}".format(self, value, m))
    return m

  def reset(self):
    #TODO Temp
    if False:
      #logger.debug("{}: mp center: {}".format(self, self.mp_.get_center()))
      p = self.posLimits_[0]
      while p < self.posLimits_[1]:
        #logger.debug("{}: p:{: .3f} v:{: .3f}".format(self, p, self.calc_value(p)))
        p += 0.1

  def __init__(self, fp, mp, interpolationDistance, factor, posLimits, eps):
    self.fp_, self.mp_, self.interpolationDistance_, self.factor_, self.posLimits_, self.eps_ = fp, mp, interpolationDistance, factor, posLimits, eps

    
class OutputDeltaLinkingCurve:
  """Links controlled and and controlling axes.
     Takes controlling axis value delta, calculates controlled axis value delta using op and moves controlled axis by this delta.
     Can specify radius - controlled axis value is not changed if total controlled axis value delta will exceed this radius.
     Subscribe to controlled axis when initializing: if controlled axis is moved externally, total delta is adjusted.
  """
  def move_by(self, x, timestamp):
    #Even if x and timestamp are not used, controlled axis is moved in move_by() and not it on_move_axis(), 
    #because move_by() is called only when the mode this curve is part of is enabled, 
    #and on_move_axis() is called regardless of modes
    v = self.controllingAxis_.get()
    d = v - self.v_
    self.v_ = v
    sens = self.sensOp_(self.tcd_)
    cd = self.deltaOp_(d, sens)
    if abs(self.tcd_ + cd) < self.radius_:
      self.tcd_ += cd
      self.busy_ = True
      self.controlledAxis_.move(cd, relative=True)
      self.busy_ = False

  def reset(self):
    self.v_ = self.controllingAxis_.get()
    self.tcd_, self.busy_ = 0.0, False

  def on_move_axis(self, axis, old, new):
    if not self.busy_ and axis == self.controlledAxis_:
      tcd = self.tcd_ + (new - old)
      self.tcd_ = clamp(tcd, -self.radius_, self.radius_)

  def __init__(self, controllingAxis, controlledAxis, sensOp, deltaOp, radius = float("inf")):
    self.controllingAxis_, self.controlledAxis_, self.sensOp_, self.deltaOp_, self.radius_ = controllingAxis, controlledAxis, sensOp, deltaOp, radius
    self.v_, self.tcd_, self.busy_ = 0.0, 0.0, False


class InputDeltaLinkingCurve:
  def move_by(self, x, timestamp):
    def r(s):
      self.sd_, self.td_, self.s_ = 0.0, 0.0, s
      self.cv_ = self.controlledAxis_.get()

    v = self.controllingAxis_.get()
    d = v - self.v_
    self.v_ = v

    if self.threshold_ is not None:
      s = sign(d)
      if self.s_ == 0:
        self.s_ = s
      elif self.s_ != s:
        self.sd_ += abs(d)
        if self.sd_ > self.threshold_:
          r(s)
      elif self.sd_ != 0.0:
        self.sd_ = 0.0

    self.td_ += d
    atd = abs(self.td_)
    if atd < self.radius_:
      cd = self.op_(self.td_)
      self.busy_= True
      self.controlledAxis_.move(cd + self.cv_, relative=False)
      self.busy_= False

  def reset(self):
    self.v_ = self.controllingAxis_.get()
    self.cv_ = self.controlledAxis_.get()
    self.s_, self.td_, self.sd_ = 0, 0.0, 0.0

  def on_move_axis(self, axis, old, new):
    if not self.busy_ and axis == self.controlledAxis_:
      self.cv_ += new - old

  def __init__(self, controllingAxis, controlledAxis, op, radius = float("inf"), threshold = 0.0):
    self.controllingAxis_, self.controlledAxis_, self.op_, self.radius_, self.threshold_ = controllingAxis, controlledAxis, op, radius, threshold
    self.v_, self.s_, self.td_, self.sd_, self.cv_, self.busy_  = 0.0, 0, 0.0, 0.0, 0.0, False


class InputLinkingCurve:
  def move_by(self, x, timestamp):
    v = self.controllingAxis_.get()
    cv = self.op_(v)
    self.busy_= True
    self.controlledAxis_.move(cv + self.offset_, relative=False)
    self.busy_= False

  def reset(self):
    self.offset_ = self.controlledAxis_.get() - self.op_(self.controllingAxis_.get())

  def on_move_axis(self, axis, old, new):
    if not self.busy_ and axis == self.controlledAxis_:
      self.offset_ += new - old

  def __init__(self, controllingAxis, controlledAxis, op):
    self.controllingAxis_, self.controlledAxis_, self.op_ = controllingAxis, controlledAxis, op
    self.offset_, self.busy_  = 0.0, False


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


class SwallowDevices:
  def __call__(self, event):
    self.set_mode_(self.mode_)
    return True

  def __init__(self, devices, mode):
    self.mode_, self.devices_ = mode, devices
    logger.debug("{} created".format(self))

  def __del__(self):
    logger.debug("{} destroyed".format(self))

  def set_mode_(self, mode):
    for d in self.devices_:
      try:
        #logger.debug("{}: setting swallow state {} to {}".format(self, self.mode_, d))
        d.swallow(mode)
      except IOError as e:
        #logger.debug("{}: got IOError ({}), but that was expected".format(self, e))
        continue


class Opentrack:
  """Opentrack head movement emulator. Don't forget to call send()!"""

  def move_axis(self, axis, v, relative = True):
    if axis not in self.axes_:
      return
    v = self.v_.get(axis, 0.0)+v if relative else v 
    self.v_[axis] = clamp(v, *self.get_limits(axis))
    self.dirty_ = True

  def get_axis(self, axis):
    return self.v_.get(axis, 0.0)

  def get_limits(self, axis):
    return (-1.0, 1.0)

  def get_supported_axes(self):
    return self.axes_

  def send(self):
    if self.dirty_ == True:
      self.dirty_ = False
      x, y, z = (self.v_[x] for x in self.axes_[0:3])
      yaw, pitch, roll = 180.0*self.v_[self.axes_[3]], 90.0*self.v_[self.axes_[4]], 90.0*self.v_[self.axes_[5]] 
      packet = struct.pack("dddddd", x, y, z, yaw, pitch, roll)
      self.socket_.sendto(packet, (self.ip_, self.port_))

  def __init__(self, ip, port):
    self.dirty_ = False
    self.socket_ = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    self.ip_, self.port_ = ip, port
    self.v_ = {a:0.0 for a in self.axes_}

  axes_ = (codes.ABS_X, codes.ABS_Y, codes.ABS_Z, codes.ABS_RX, codes.ABS_RY, codes.ABS_RZ)


class UdpJoystick:
  """Generick joystick that sends axes positions over UDP. Don't forget to call send()!"""

  def move_axis(self, axis, v, relative = True):
    if axis not in self.axes_:
      return
    v = self.v_.get(axis, 0.0)+v if relative else v 
    self.v_[axis] = clamp(v, *self.get_limits(axis))
    self.dirty_ = True

  def get_axis(self, axis):
    return self.v_.get(axis, 0.0)

  def get_limits(self, axis):
    return (-1.0, 1.0)

  def get_supported_axes(self):
    return self.axes_

  def send(self):
    if self.dirty_ == True:
      self.dirty_ = False
      packet = self.make_packet_(self.v_)
      self.socket_.sendto(packet, (self.ip_, self.port_))

  def __init__(self, ip, port, make_packet):
    self.dirty_ = False
    self.socket_ = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    self.ip_, self.port_ = ip, port
    self.make_packet_ = make_packet
    self.v_ = {a:0.0 for a in self.axes_}

  axes_ = (codes.ABS_X, codes.ABS_Y, codes.ABS_Z, codes.ABS_RY, codes.ABS_RX, codes.ABS_RZ)


#TODO Needs verifying
def make_opentrack_packet(v):
  d = (
    (codes.ABS_X, 1.0),
    (codes.ABS_Y, -1.0),
    (codes.ABS_Z, 1.0),
    (codes.ABS_RX, 180.0),
    (codes.ABS_RY, -90.0),
    (codes.ABS_RZ, 90.0)
  )
  values = (dd[1]*v.get(dd[0], 0.0) for dd in d)
  packet = struct.pack("<dddddd", *values)
  return packet


def make_il2_packet(v):
  #https://github.com/uglyDwarf/linuxtrack/blob/1f405ea1a3a478163afb1704072480cf7a2955c2/src/ltr_pipe.c#L919
  #r = snprintf(buf, sizeof(buf), "R/11\\%f\\%f\\%f", d->h, -d->p, d->r);
  d = (
    (codes.ABS_RX, -90.0),
    (codes.ABS_RY, 90.0),
    (codes.ABS_RZ, 180.0)
  )
  values = (dd[1]*v.get(dd[0], 0.0) for dd in d)
  return "R/11\\{:f}\\{:f}\\{:f}".format(*values)


def make_il2_6dof_packet(v):
  #https://github.com/uglyDwarf/linuxtrack/blob/1f405ea1a3a478163afb1704072480cf7a2955c2/src/ltr_pipe.c#L938
  #r = snprintf(buf, sizeof(buf), "R/11\\%f\\%f\\%f\\%f\\%f\\%f", d->h, -d->p, d->r, -d->z/300, -d->x/1000, d->y/1000);
  d = (
    (codes.ABS_RX, -90.0),
    (codes.ABS_RY, 90.0),
    (codes.ABS_RZ, 180.0),
    (codes.ABS_Z, 0.5),
    (codes.ABS_X, -0.5),
    (codes.ABS_Y, -0.5)
  )
  values = (dd[1]*v.get(dd[0], 0.0) for dd in d)
  return "R/11\\{:f}\\{:f}\\{:f}\\{:f}\\{:f}\\{:f}".format(*values)


class JoystickSnapManager:
  """Sets joystick axes to preset values and also can update preset values from joystick"""

  def set_snap(self, i, l):
    self.snaps_[i] = [[p[0], p[1]] for p in l]

  def update_snap(self, i):
    #logger.debug("update_snap({})".format(i))
    snap = self.snaps_.get(i, None)
    if snap is None:
      logger.debug("{}: no snap {}".format(self, i))
      return False
    else:
      for j in xrange(len(snap)):
        snap[j][1] = self.joystick_.get_axis(snap[j][0])
      return True
       
  def snap_to(self, i):
    #logger.debug("snap_to({})".format(i))
    snap = self.snaps_.get(i, None)
    if snap is None:
      logger.debug("{}: no snap {}".format(self, i))
      return False
    else:
      for p in snap:
        self.joystick_.move_axis(p[0], p[1], self.relative_)
      return True

  def __init__(self, joystick, relative):
    self.snaps_, self.joystick_, self.relative_ = dict(), joystick, relative


class AxisSnapManager:
  """Axis-based snap manager"""
  def set_snap(self, i, l):
    self.snaps_[i] = [[p[0], p[1]] for p in l]

  def update_snap(self, i):
    #logger.debug("{}: updating snap {}".format(self, i))
    snap = self.snaps_.get(i, None)
    if snap is None:
      logger.debug("{}: no snap {}".format(self, i))
      return False
    else:
      for p in snap:
        p[1] = p[0].get()
      return True
       
  def snap_to(self, i):
    #logger.debug("{}: snapping to {}".format(self, i))
    snap = self.snaps_.get(i, None)
    if snap is None:
      logger.debug("{}: no snap {}".format(self, i))
      return False
    else:
      for p in snap:
        p[0].move(p[1], False)
      return True

  def has_snap(self, i):
    return i in self.snaps_

  def __init__(self):
    self.snaps_ = dict()


def SnapTo(snapManager, snap):
  def op(event):
    return snapManager.snap_to(snap)
  return op


def UpdateSnap(snapManager, snap):
  def op(event):
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


class ElasticJoystic:
  def move_axis(self, axis, value, relative):
    if self.next_ is not None:
      self.v_[axis] = clamp(self.v_[axis]+value if relative else value, *self.get_limits(axis))

  def get_axis(self, axis):
    return self.v_[axis]

  def get_limits(self, axis):
    return self.next_.get_limits(axis) if self.next_ else (0.0, 0.0)

  def get_supported_axes(self):
    return self.next_.get_supported_axes() if self.next_ else ()

  def set_button_state(self, button, state):
    self.next_.set_button_state(button, state)

  def set_next(self, next):
    self.next_ = next
    return next

  def update(self, tick):
    if self.next_ is None: return
    for axisId,value in self.v_.items():
      current = self.next_.get_axis(axisId)
      delta = value - current
      if delta != 0.0:
        if axisId in self.speed_:  
          value = current + sign(delta)*min(abs(delta), self.speed_[axisId]*tick)
        self.next_.move_axis(axisId, value, False)

  def __init__(self, next, speed):
    assert(next is not None)
    self.next_, self.speed_ = next, speed
    self.v_ = {axisId:self.next_.get_axis(axisId) for axisId in self.next_.get_supported_axes()}
  

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
      print("{}: {: .3f} {: .3f}".format(self.axisToName[a], error, d[2]))
        
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

  axisToName = {p[1]:p[0] for p in {"x":codes.ABS_X, "y":codes.ABS_Y, "z":codes.ABS_Z, "rx":codes.ABS_RX, "ry":codes.ABS_RY, "rz":codes.ABS_RZ, "rudder":codes.ABS_RUDDER, "throttle":codes.ABS_THROTTLE}.items()}


def make_curve_makers():
  curves = {}

  def make_config_curves(settings):
    def parseAxis(cfg, state):
      curve = cfg.get("curve", None)
      if curve is None:
        raise Exception("{}.{}.{}: Curve type not set".format(state["set"], state["mode"], state["axis"]))
      state["curve"] = curve
      return state["parser"]("curve", cfg, state)
          
    def parseAxes(cfg, state):
      r = {}
      for axisName,axisData in cfg.items():
        state["axis"] = name2code(axisName)
        r[name2code(axisName)] = parseAxis(axisData, state)
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
          inputSourceAndAxisId = split_full_name_code(inputSourceAndAxisName, ".")
          r[inputSourceAndAxisId] = float(inputAxisData)
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

    config = settings["config"]
    configCurves = config["configCurves"]
    logger.info("Using '{}' curves from config".format(configCurves))
    sets = config["layouts"].get(configCurves, None)
    if sets is None:
      raise Exception("'{}' curves not found in config".format(configCurves))
    else:
      try:
        def make_path(state):
          r = str(state.get("curves", ""))
          for n in ("set", "mode", "group", "output", "axis"):
            r += "." + str(state.get(n, ""))
          return r
        state = {"settings" : settings, "curves" : configCurves, "parser" : settings["parser"]}
        r = parseSets(sets, state)
      except Exception as e:
        path = make_path(state)
        logger.debug("Error while parsing {}: {}".format(path, e))
        raise ParseError(path, e)
    return r

  curves["config"] = make_config_curves

  return curves

curveMakers = make_curve_makers()

def init_main_sink(settings, make_next):
  #logger.debug("init_main_sink()")
  cmpOp = CmpWithModifiers()
  config = settings["config"]

  clickSink = ClickSink(config.get("clickTime", 0.5))
  defaultModifiers = [ (None, m) for m in 
    (codes.KEY_LEFTSHIFT, codes.KEY_RIGHTSHIFT, codes.KEY_LEFTCTRL, codes.KEY_RIGHTCTRL, codes.KEY_LEFTALT, codes.KEY_RIGHTALT)
  ]
  modifiers = config.get("modifiers", None)
  modifiers = [split_full_name_code(m) for m in modifiers] if modifiers is not None else defaultModifiers
  modifierSink = clickSink.set_next(ModifierSink(modifiers=modifiers))

  sens = config.get("sens", None)
  if sens is not None:
    sensSet = config.get("sensSet", None)
    if sensSet not in sens:
      raise Exception("Invalid sensitivity set: {}".format(sensSet))
    sens = sens[sensSet]
    sens = {split_full_name_code(s[0]):s[1] for s in sens.items()}
  scaleSink = modifierSink.set_next(ScaleSink2(sens))

  mainSink = scaleSink.set_next(BindSink(cmpOp))
  stateSink = mainSink.add((), StateSink(), 1)

  toggleKey = config.get("toggleKey", codes.KEY_SCROLLLOCK)
  mainSink.add(ED.doubleclick(toggleKey), ToggleSink(stateSink), 0)

  def rld(e):
    settings["initState"] = stateSink.get_state()
    raise ReloadException()
  mainSink.add(ED.click(toggleKey, [(None, codes.KEY_RIGHTSHIFT)]), rld, 0)
  mainSink.add(ED.click(toggleKey, [(None, codes.KEY_LEFTSHIFT)]), rld, 0)

  grabSink = stateSink.set_next(BindSink(cmpOp))
  grabbed = [settings["inputs"][g] for g in config.get("grabbed", ())]
  grabSink.add(ED.init(1), SwallowDevices(grabbed, True), 0)
  grabSink.add(ED.init(0), SwallowDevices(grabbed, False), 0)

  def print_enabled(event):
    logger.info("Emulation enabled")
  def print_disabled(event):
    logger.info("Emulation disabled")
  grabSink.add(ED.init(1), print_enabled, 0)
  grabSink.add(ED.init(0), print_disabled, 0)

  #make_next() may need axes, so initializing them here
  #TODO Init only selected speed axes
  allAxes = {}
  settings["axes"] = allAxes
  for oName,o in settings["outputs"].items():
    if oName not in allAxes: allAxes[oName] = {}
    soName = oName+"_s"
    if soName not in allAxes: allAxes[soName] = {}
    for axisId in o.get_supported_axes():
      valueAxis = ReportingAxis(JoystickAxis(o, axisId))
      allAxes[oName][axisId] = valueAxis
      deltaOp = lambda v,tick : v*tick
      limits = (-1.0, 1.0)
      speedAxis = SecondOrderAxis(valueAxis, deltaOp, limits)
      def make_update_op(speedAxis):
        def op(tick):
          speedAxis.update(tick)
        return op
      settings["updated"].append(make_update_op(speedAxis))
      allAxes[soName][axisId] = ReportingAxis(speedAxis)

  grabSink.add(ED.any(), make_next(settings), 1)
  if "initState" not in settings: settings["initState"] = False
  stateSink.set_state(settings["initState"])
  logger.info("Initialization successfull")
      
  return clickSink


def init_log_initial(level=logging.INFO, handler=logging.StreamHandler(sys.stdout), fmt="%(levelname)s:%(message)s"):
  root = logging.getLogger()
  root.setLevel(level)
  handler.setLevel(logging.NOTSET)
  handler.setFormatter(logging.Formatter(fmt))
  root.addHandler(handler)


def set_log_level(settings):
  levelName = settings["config"]["logLevel"].upper()
  nameToLevel = {
    logging.getLevelName(l).upper():l for l in (logging.CRITICAL, logging.ERROR, logging.WARNING, logging.INFO, logging.DEBUG, logging.NOTSET)
  }

  print("Setting log level to {}".format(levelName))
  level = nameToLevel.get(levelName, logging.NOTSET)
  root = logging.getLogger()
  root.setLevel(level)


class ConfigReadError(RuntimeError):
  def __init__(self, configName, e):
    self.configName, self.e = configName, e
  def __str__(self):
    return "Cannot read config file {} ({})".format(self.configName, self.e)


class ParseError(RuntimeError):
  def __init__(self, path, e):
    self.path, self.e = path, e
  def __str__(self):
    return "Cannot parse {} ({})".format(self.path, self.e)


def init_config(configFilesNames):
  cfg = {}
  for configName in configFilesNames:
    try:
      with open(configName, "r") as f:
        current = json.load(f)
        configs = current.get("configs", None)
        if configs is not None:
          parent = init_config(configs)
          merge_dicts(current, parent)
        merge_dicts(cfg, current)
    except (KeyError, ValueError, IOError) as e:
      raise ConfigReadError(configName, e)
  return cfg
                              

def init_config2(settings):
  config = settings["options"]
  if "configNames" in settings:
    externalConfig = init_config(settings["configNames"])
    merge_dicts(externalConfig, config)
    config = externalConfig
  settings["config"] = config


def add_scale_sink(sink, cfg):
  if "sens" in cfg:
    #cfg["sens"] is already in form {(e.source, e.code) : value}
    sensSink = ScaleSink2(cfg["sens"], lambda event : ((event.source, event.code), (None, event.code)))
    sensSink.set_next(sink)
    return sensSink 
  else:
    return sink

layout_initializers = {}

def init_layout_empty(settings): 
  return None

layout_initializers["empty"] = init_layout_empty


def init_layout_main(settings): 
  return init_main_sink(settings, lambda s : None)

layout_initializers["main"] = init_layout_empty


def init_base_joystick_snaps(axes):
  snaps = AxisSnapManager()
  snaps.set_snap("z", ((axes[codes.ABS_Z], 0.0),))
  snaps.set_snap("xy", ((axes[codes.ABS_X], 0.0), (axes[codes.ABS_Y], 0.0),))
  snaps.set_snap("xz", ((axes[codes.ABS_X], 0.0), (axes[codes.ABS_Z], 0.0),))
  snaps.set_snap("x", ((axes[codes.ABS_X], 0.0),))
  snaps.set_snap("zy", ((axes[codes.ABS_Z], 0.0), (axes[codes.ABS_Y], 0.0),))
  snaps.set_snap("rxry", ((axes[codes.ABS_RX], 0.0), (axes[codes.ABS_RY], 0.0),))
  return snaps


def init_base_head_snaps(axes):
  snaps = AxisSnapManager()
  zero = (
    (axes[codes.ABS_RX], 0.0), (axes[codes.ABS_RY], 0.0), (axes[codes.ABS_RZ], 0.0), (axes[codes.ABS_THROTTLE], 0.0),
  )
  snaps.set_snap("current", zero)
  fullForward = (
    (axes[codes.ABS_RX], 0.0), (axes[codes.ABS_RY], 0.0), (axes[codes.ABS_RZ], 0.0), (axes[codes.ABS_THROTTLE], -1.0),
  )
  snaps.set_snap("ff", fullForward)
  fullBackward = (
    (axes[codes.ABS_RX], 0.0), (axes[codes.ABS_RY], 0.15), (axes[codes.ABS_RZ], 0.0), (axes[codes.ABS_THROTTLE], 1.0),
  )
  snaps.set_snap("fb", fullBackward)
  zoomOut = ((axes[codes.ABS_THROTTLE], 1.0),)
  snaps.set_snap("zo", zoomOut)
  centerView = ((axes[codes.ABS_RX], 0.0), (axes[codes.ABS_RY], 0.0),)
  snaps.set_snap("cdir", centerView)
  centerViewPos = ((axes[codes.ABS_X], 0.0), (axes[codes.ABS_Y], 0.0), (axes[codes.ABS_Z], 0.0),)
  snaps.set_snap("cpos", centerViewPos)
  return snaps


def init_base_head(curves, snaps):
  cmpOp = CmpWithModifiers()
  headBindSink = BindSink(cmpOp)
  headModeSink = ModeSink()
  headBindSink.add(ED3.parse("any()"), headModeSink, 1)
  headBindSink.add(ED3.parse("press(mouse.BTN_EXTRA)"), SetMode(headModeSink, 1), 0)
  headBindSink.add(ED3.parse("release(mouse.BTN_EXTRA)"), SetMode(headModeSink, 0), 0)
  headBindSink.add(ED3.parse("init(0)"), UpdateSnap(snaps, "current"), 0)
  headBindSink.add(ED3.parse("init(1)"), SetMode(headModeSink, 0), 0)

  if 0 in curves:
    #logger.debug("Init mode 0")
    cs = curves[0]["curves"]["head"]
    ss = BindSink(cmpOp)
    ss.add(ED3.parse("move(mouse.REL_X)"), MoveCurve(cs.get(codes.ABS_RX, None)), 0)
    ss.add(ED3.parse("move(mouse.REL_Y)"), MoveCurve(cs.get(codes.ABS_RY, None)), 0)
    ss.add(ED3.parse("move(mouse.REL_WHEEL)"), MoveCurve(cs.get(codes.ABS_THROTTLE, None)), 0)
    ss.add(ED3.parse("click(mouse.BTN_MIDDLE)"), SnapTo(snaps, "zo"), 0)
    ss.add(ED3.parse("doubleclick(mouse.BTN_MIDDLE)"), SnapTo(snaps, "cdir"), 0)
    ss.add(ED3.parse("init(1)"), ResetCurves(cs.values()))
    ss = add_scale_sink(ss, curves[0])
    headModeSink.add(0, ss)

  if 1 in curves:
    #logger.debug("Init mode 1")
    cs = curves[1]["curves"]["head"]
    ss = BindSink(cmpOp)
    ss.add(ED3.parse("move(mouse.REL_X)"), MoveCurve(cs.get(codes.ABS_X, None)), 0)
    ss.add(ED3.parse("move(mouse.REL_Y)"), MoveCurve(cs.get(codes.ABS_Y, None)), 0)
    ss.add(ED3.parse("move(mouse.REL_WHEEL)"), MoveCurve(cs.get(codes.ABS_Z, None)), 0)
    ss.add(ED3.parse("doubleclick(mouse.BTN_MIDDLE)"), SnapTo(snaps, "cpos"), 0)
    ss.add(ED3.parse("init(1)"), ResetCurves(cs.values()))
    ss = add_scale_sink(ss, curves[1])
    headModeSink.add(1, ss)

  headModeSink.set_mode(0)
  return headBindSink


def init_layout_base(settings): 
  cmpOp = CmpWithModifiers()
  curveSet = settings["config"].get("curves", None)
  if curveSet is None:
    raise Exception("No curve set specified in settings")
  curveMaker = curveMakers.get(curveSet, None)
  if curveMaker is None:
     raise Exception("No curves for {}".format(curveSet))
  
  curves = curveMaker(settings)

  joySnaps = init_base_joystick_snaps(settings["axes"]["joystick"])
  headSnaps = init_base_head_snaps(settings["axes"]["head"])

  topBindSink = BindSink(cmpOp)
  topModeSink = ModeSink()
  topBindSink.add(ED3.parse("any()"), topModeSink, 1)
  topBindSink.add(ED3.parse("press(mouse.BTN_RIGHT)"), SetMode(topModeSink, 1), 0)
  topBindSink.add(ED3.parse("release(mouse.BTN_RIGHT)"), SetMode(topModeSink, 0), 0)

  joystickBindSink = BindSink(cmpOp)
  topModeSink.add(0, joystickBindSink)
  topModeSink.set_mode(0)

  joystickModeSink = joystickBindSink.add(ED3.parse("any()"), ModeSink(), 1)
  jmm = ModeSinkModeManager(joystickModeSink)
  joystickBindSink.add(ED3.parse("press(mouse.BTN_EXTRA)"), jmm.make_cycle([1,0], True), 0)
  joystickBindSink.add(ED3.parse("release(mouse.BTN_EXTRA)"), jmm.make_restore(), 0)
  joystickBindSink.add(ED3.parse("doubleclick(mouse.BTN_EXTRA)"), jmm.make_cycle([1,0], False), 0)
  joystickBindSink.add(ED3.parse("press(mouse.BTN_SIDE)"), jmm.make_set(2, True), 0)
  joystickBindSink.add(ED3.parse("release(mouse.BTN_SIDE)"), jmm.make_restore(), 0)
  joystickBindSink.add(ED3.parse("init(1)"), jmm.make_set(0, False), 0)
  joystickBindSink.add(ED3.parse("init(1)"), jmm.make_clear(), 0)

  if "primary" in curves:
    cj = curves["primary"]
    if 0 in cj:
      #logger.debug("Init mode 0")
      cs = cj[0]["curves"]["joystick"]

      ss = BindSink(cmpOp)
      ss.add(ED3.parse("move(mouse.REL_X)"), MoveCurve(cs.get(codes.ABS_X, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_Y)"), MoveCurve(cs.get(codes.ABS_Y, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_WHEEL)"), MoveCurve(cs.get(codes.ABS_Z, None)), 0)
      ss.add(ED3.parse("click(mouse.BTN_MIDDLE)"), SnapTo(joySnaps, "z"), 0)
      ss.add(ED3.parse("doubleclick(mouse.BTN_MIDDLE)"), SnapTo(joySnaps, "xy"), 0)
      ss.add(ED3.parse("release(mouse.BTN_LEFT)"), SnapTo(headSnaps, "current"), 0)
      ss.add(ED3.parse("init(1)"), ResetCurves(cs.values()))
      ss = add_scale_sink(ss, cj[0])
      joystickModeSink.add(0, ss)

    if 1 in cj:
      #logger.debug("Init mode 1")
      cs = cj[1]["curves"]["joystick"]

      ss = BindSink(cmpOp)
      ss.add(ED3.parse("move(mouse.REL_X)"), MoveCurve(cs.get(codes.ABS_RX, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_Y)"), MoveCurve(cs.get(codes.ABS_RY, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_WHEEL)"), MoveCurve(cs.get(codes.ABS_RUDDER, None)), 0)
      ss.add(ED3.parse("doubleclick(mouse.BTN_MIDDLE)"), SnapTo(joySnaps, "rxry"), 0)
      ss.add(ED3.parse("release(mouse.BTN_LEFT)"), SnapTo(headSnaps, "ff"), 0)
      ss.add(ED3.parse("init(1)"), ResetCurves(cs.values()))
      ss = add_scale_sink(ss, cj[1])
      joystickModeSink.add(1, ss)

    if 2 in cj:
      #logger.debug("Init mode 2")
      cs = cj[2]["curves"]["joystick"]

      ss = BindSink(cmpOp)
      ss.add(ED3.parse("move(mouse.REL_X)"), MoveCurve(cs.get(codes.ABS_X, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_Y)"), MoveCurve(cs.get(codes.ABS_Y, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_WHEEL)"), MoveCurve(cs.get(codes.ABS_THROTTLE, None)), 0)
      ss.add(ED3.parse("release(mouse.BTN_LEFT)"), SnapTo(headSnaps, "fb"), 0)
      ss.add(ED3.parse("init(1)"), ResetCurves(cs.values()))
      ss = add_scale_sink(ss, cj[2])
      joystickModeSink.add(2, ss)

    joystickModeSink.set_mode(0)

  headBindSink = BindSink(cmpOp)
  topModeSink.add(1, headBindSink)

  headModeSink = ModeSink()
  headBindSink.add(ED3.parse("any()"), headModeSink, 1)
  headBindSink.add(ED3.parse("press(mouse.BTN_EXTRA)"), SetMode(headModeSink, 1), 0)
  headBindSink.add(ED3.parse("release(mouse.BTN_EXTRA)"), SetMode(headModeSink, 0), 0)

  if "secondary" in curves:
    topModeSink.add(1, init_base_head(curves["secondary"], headSnaps))

  headModeSink.set_mode(0)

  return topBindSink

layout_initializers["base"] = init_layout_base


def init_layout_base3(settings):
  cmpOp = CmpWithModifiers()
  curveSet = settings["config"].get("curves", None)
  if curveSet is None:
    raise Exception("No curve set specified in settings")
  curveMaker = curveMakers.get(curveSet, None)
  if curveMaker is None:
    raise Exception("No curves for {}".format(curveSet))
  
  curves = curveMaker(settings)

  joySnaps = init_base_joystick_snaps(settings["axes"]["joystick"])
  headSnaps = init_base_head_snaps(settings["axes"]["head"])

  topBindSink = BindSink(cmpOp)
  topModeSink = ModeSink()
  topBindSink.add(ED3.parse("any()"), topModeSink, 1)
  topBindSink.add(ED3.parse("press(mouse.BTN_RIGHT)"), SetMode(topModeSink, 1), 0)
  topBindSink.add(ED3.parse("release(mouse.BTN_RIGHT)"), SetMode(topModeSink, 0), 0)

  joystickBindSink = BindSink(cmpOp)
  topModeSink.add(0, joystickBindSink)
  topModeSink.set_mode(0)

  joystickModeSink = joystickBindSink.add(ED3.parse("any()"), ModeSink(), 1)
  jmm = ModeSinkModeManager(joystickModeSink)
  joystickBindSink.add(ED3.parse("press(mouse.BTN_EXTRA)"), jmm.make_cycle([1,0], True), 0)
  joystickBindSink.add(ED3.parse("release(mouse.BTN_EXTRA)"), jmm.make_restore(), 0)
  joystickBindSink.add(ED3.parse("doubleclick(mouse.BTN_EXTRA)"), jmm.make_cycle([1,0], False), 0)
  joystickBindSink.add(ED3.parse("press(mouse.BTN_SIDE)"), jmm.make_set(2, True), 0)
  joystickBindSink.add(ED3.parse("release(mouse.BTN_SIDE)"), jmm.make_restore(), 0)
  joystickBindSink.add(ED3.parse("init(1)"), jmm.make_set(0, False), 0)
  joystickBindSink.add(ED3.parse("init(1)"), jmm.make_clear(), 0)

  if "primary" in curves:
    cj = curves["primary"]
    if 0 in cj:
      #logger.debug("Init mode 0")
      cs = cj[0]["curves"]["joystick"]

      ss = BindSink(cmpOp)
      ss.add(ED3.parse("move(mouse.REL_X)"), MoveCurve(cs.get(codes.ABS_X, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_Y)"), MoveCurve(cs.get(codes.ABS_Y, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_WHEEL)+"), MoveCurve(cs.get(codes.ABS_Z, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_WHEEL)+keyboard.KEY_RIGHTSHIFT"), MoveCurve(cs.get(codes.ABS_THROTTLE, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_WHEEL)+keyboard.KEY_LEFTSHIFT"), MoveCurve(cs.get(codes.ABS_THROTTLE, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_WHEEL)+keyboard.KEY_RIGHTCTRL"), MoveCurve(cs.get(codes.ABS_RUDDER, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_WHEEL)+keyboard.KEY_LEFTCTRL"), MoveCurve(cs.get(codes.ABS_RUDDER, None)), 0)
      ss.add(ED3.parse("click(mouse.BTN_MIDDLE)+"), SnapTo(joySnaps, "z"), 0)
      ss.add(ED3.parse("doubleclick(mouse.BTN_MIDDLE)+"), SnapTo(joySnaps, "xy"), 0)
      ss.add(ED3.parse("release(mouse.BTN_LEFT)"), SnapTo(headSnaps, "current"), 0)
      #This reset is needed to set the center of the moving point of curves to current values of corresponding axes
      ss.add(ED3.parse("init(1)"), ResetCurves(cs.values()))
      ss = add_scale_sink(ss, cj[0])
      joystickModeSink.add(0, ss)

    if 1 in cj:
      #logger.debug("Init mode 1")
      cs = cj[1]["curves"]["joystick"]

      ss = BindSink(cmpOp)
      ss.add(ED3.parse("move(mouse.REL_X)"), MoveCurve(cs.get(codes.ABS_Z, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_Y)"), MoveCurve(cs.get(codes.ABS_Y, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_WHEEL)+"), MoveCurve(cs.get(codes.ABS_X, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_WHEEL)+keyboard.KEY_RIGHTSHIFT"), MoveCurve(cs.get(codes.ABS_THROTTLE, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_WHEEL)+keyboard.KEY_LEFTSHIFT"), MoveCurve(cs.get(codes.ABS_THROTTLE, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_WHEEL)+keyboard.KEY_RIGHTCTRL"), MoveCurve(cs.get(codes.ABS_RUDDER, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_WHEEL)+keyboard.KEY_LEFTCTRL"), MoveCurve(cs.get(codes.ABS_RUDDER, None)), 0)
      ss.add(ED3.parse("click(mouse.BTN_MIDDLE)+"), SnapTo(joySnaps, "x"), 0)
      ss.add(ED3.parse("doubleclick(mouse.BTN_MIDDLE)+"), SnapTo(joySnaps, "zy"), 0)
      ss.add(ED3.parse("release(mouse.BTN_LEFT)"), SnapTo(headSnaps, "ff"), 0)
      ss.add(ED3.parse("init(1)"), ResetCurves(cs.values()))
      ss = add_scale_sink(ss, cj[1])
      joystickModeSink.add(1, ss)

    if 2 in cj:
      #logger.debug("Init mode 2")
      cs = cj[2]["curves"]["joystick"]

      ss = BindSink(cmpOp)
      ss.add(ED3.parse("move(mouse.REL_X)"), MoveCurve(cs.get(codes.ABS_RX, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_Y)"), MoveCurve(cs.get(codes.ABS_RY, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_WHEEL)"), MoveCurve(cs.get(codes.ABS_RZ, None)), 0)
      ss.add(ED3.parse("doubleclick(mouse.BTN_MIDDLE)"), SnapTo(joySnaps, "rxry"), 0)
      ss.add(ED3.parse("release(mouse.BTN_LEFT)"), SnapTo(headSnaps, "fb"), 0)
      ss.add(ED3.parse("init(1)"), ResetCurves(cs.values()))
      ss = add_scale_sink(ss, cj[2])
      joystickModeSink.add(2, ss)

    joystickModeSink.set_mode(0)

  if "secondary" in curves:
    topModeSink.add(1, init_base_head(curves["secondary"], headSnaps))

  return topBindSink

layout_initializers["base3"] = init_layout_base3


def init_layout_base4(settings):
  cmpOp = CmpWithModifiers()
  curveSet = settings["config"].get("curves", None)
  if curveSet is None:
    raise Exception("No curve set specified in settings")
  curveMaker = curveMakers.get(curveSet, None)
  if curveMaker is None:
    raise Exception("No curves for {}".format(curveSet))
  
  curves = curveMaker(settings)

  joySnaps = init_base_joystick_snaps(settings["axes"]["joystick"])
  headSnaps = init_base_head_snaps(settings["axes"]["head"])

  topBindSink = BindSink(cmpOp)
  topModeSink = ModeSink()
  topBindSink.add(ED3.parse("any()"), topModeSink, 1)
  topBindSink.add(ED3.parse("press(mouse.BTN_RIGHT)"), SetMode(topModeSink, 1), 0)
  topBindSink.add(ED3.parse("release(mouse.BTN_RIGHT)"), SetMode(topModeSink, 0), 0)

  joystickBindSink = BindSink(cmpOp)
  topModeSink.add(0, joystickBindSink)
  topModeSink.set_mode(0)

  joystickModeSink = joystickBindSink.add(ED3.parse("any()"), ModeSink(), 1)

  jmm = ModeSinkModeManager(joystickModeSink)
  joystickBindSink.add(ED3.parse("press(mouse.BTN_EXTRA)"), jmm.make_cycle([1,0], True), 0)
  joystickBindSink.add(ED3.parse("release(mouse.BTN_EXTRA)"), jmm.make_restore(), 0)
  joystickBindSink.add(ED3.parse("doubleclick(mouse.BTN_EXTRA)"), jmm.make_cycle([1,0], False), 0)
  joystickBindSink.add(ED3.parse("press(mouse.BTN_SIDE)"), jmm.make_set(2, True), 0)
  joystickBindSink.add(ED3.parse("release(mouse.BTN_SIDE)"), jmm.make_restore(), 0)
  joystickBindSink.add(ED3.parse("init(1)"), jmm.make_set(0, False), 0)
  joystickBindSink.add(ED3.parse("init(1)"), jmm.make_clear(), 0)

  if "primary" in curves:
    cj = curves["primary"]
    if 0 in cj:
      #logger.debug("Init mode 0")
      cs = cj[0]["curves"]["joystick"]

      ss = BindSink(cmpOp)
      ss.add(ED3.parse("move(mouse.REL_X)"), MoveCurve(cs.get(codes.ABS_X, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_Y)"), MoveCurve(cs.get(codes.ABS_Y, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_WHEEL)"), MoveCurve(cs.get(codes.ABS_Z, None)), 0)
      ss.add(ED3.parse("click(mouse.BTN_MIDDLE)"), SnapTo(joySnaps, "z"), 0)
      ss.add(ED3.parse("doubleclick(mouse.BTN_MIDDLE)"), SnapTo(joySnaps, "xy"), 0)
      ss.add(ED3.parse("release(mouse.BTN_LEFT)"), SnapTo(headSnaps, "current"), 0)
      ss.add(ED3.parse("init(1)"), ResetCurves(cs.values()))
      ss = add_scale_sink(ss, cj[0])
      joystickModeSink.add(0, ss)

    if 1 in cj:
      #logger.debug("Init mode 1")
      cs = cj[1]["curves"]["joystick"]

      ss = BindSink(cmpOp)
      ss.add(ED3.parse("move(mouse.REL_X)"), MoveCurve(cs.get(codes.ABS_Z, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_Y)"), MoveCurve(cs.get(codes.ABS_Y, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_WHEEL)"), MoveCurve(cs.get(codes.ABS_X, None)), 0)
      ss.add(ED3.parse("click(mouse.BTN_MIDDLE)"), SnapTo(joySnaps, "x"), 0)
      ss.add(ED3.parse("doubleclick(mouse.BTN_MIDDLE)"), SnapTo(joySnaps, "zy"), 0)
      ss.add(ED3.parse("release(mouse.BTN_LEFT)"), SnapTo(headSnaps, "ff"), 0)
      ss.add(ED3.parse("init(1)"), ResetCurves(cs.values()))
      ss = add_scale_sink(ss, cj[1])
      joystickModeSink.add(1, ss)

    if 2 in cj:
      #logger.debug("Init mode 2")
      cs = cj[2]["curves"]["joystick"]

      ss = BindSink(cmpOp)
      ss.add(ED3.parse("move(mouse.REL_X)"), MoveCurve(cs.get(codes.ABS_X, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_Y)"), MoveCurve(cs.get(codes.ABS_Y, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_WHEEL)+"), MoveCurve(cs.get(codes.ABS_THROTTLE, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_WHEEL)+keyboard.KEY_RIGHTCTRL"), MoveCurve(cs.get(codes.ABS_RUDDER, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_WHEEL)+keyboard.KEY_LEFTCTRL"), MoveCurve(cs.get(codes.ABS_RUDDER, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_WHEEL)+keyboard.KEY_RIGHTSHIFT"), MoveCurve(cs.get(codes.ABS_RX, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_WHEEL)+keyboard.KEY_RIGHTALT"), MoveCurve(cs.get(codes.ABS_RY, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_WHEEL)+keyboard.KEY_LEFTALT"), MoveCurve(cs.get(codes.ABS_RY, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_WHEEL)+keyboard.KEY_LEFTSHIFT"), MoveCurve(cs.get(codes.ABS_RZ, None)), 0)
      ss.add(ED3.parse("doubleclick(mouse.BTN_MIDDLE)"), SnapTo(joySnaps, "xy"), 0)
      ss.add(ED3.parse("release(mouse.BTN_LEFT)"), SnapTo(headSnaps, "fb"), 0)
      ss.add(ED3.parse("init(1)"), ResetCurves(cs.values()))
      ss = add_scale_sink(ss, cj[2])
      joystickModeSink.add(2, ss)

    joystickModeSink.set_mode(0)

  if "secondary" in curves:
    topModeSink.add(1, init_base_head(curves["secondary"], headSnaps))

  return topBindSink

layout_initializers["base4"] = init_layout_base4


def init_layout_base41(settings):
  cmpOp = CmpWithModifiers()
  curveSet = settings["config"].get("curves", None)
  if curveSet is None:
    raise Exception("No curve set specified in settings")
  curveMaker = curveMakers.get(curveSet, None)
  if curveMaker is None:
    raise Exception("No curves for {}".format(curveSet))
  
  curves = curveMaker(settings)

  joySnaps = init_base_joystick_snaps(settings["axes"]["joystick"])
  headSnaps = init_base_head_snaps(settings["axes"]["head"])

  topBindSink = BindSink(cmpOp)
  topModeSink = ModeSink()
  topBindSink.add(ED3.parse("any()"), topModeSink, 1)
  topBindSink.add(ED3.parse("press(mouse.BTN_RIGHT)"), SetMode(topModeSink, 1), 0)
  topBindSink.add(ED3.parse("release(mouse.BTN_RIGHT)"), SetMode(topModeSink, 0), 0)

  joystickBindSink = BindSink(cmpOp)
  topModeSink.add(0, joystickBindSink)
  topModeSink.set_mode(0)

  joystickModeSink = joystickBindSink.add(ED3.parse("any()"), ModeSink(), 1)

  jmm = ModeSinkModeManager(joystickModeSink)
  joystickBindSink.add(ED3.parse("press(mouse.BTN_EXTRA)"), jmm.make_cycle([1,0], True), 0)
  joystickBindSink.add(ED3.parse("release(mouse.BTN_EXTRA)"), jmm.make_restore(), 0)
  joystickBindSink.add(ED3.parse("doubleclick(mouse.BTN_EXTRA)"), jmm.make_cycle([1,0], False), 0)
  joystickBindSink.add(ED3.parse("press(mouse.BTN_SIDE)"), jmm.make_set(2, True), 0)
  joystickBindSink.add(ED3.parse("release(mouse.BTN_SIDE)"), jmm.make_restore(), 0)
  joystickBindSink.add(ED3.parse("init(1)"), jmm.make_set(0, False), 0)
  joystickBindSink.add(ED3.parse("init(1)"), jmm.make_clear(), 0)

  if "primary" in curves:
    cj = curves["primary"]
    if 0 in cj:
      #logger.debug("Init mode 0")
      cs = cj[0]["curves"]["joystick"]

      ss = BindSink(cmpOp)
      ss.add(ED3.parse("move(mouse.REL_X)"), MoveCurve(cs.get(codes.ABS_X, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_Y)"), MoveCurve(cs.get(codes.ABS_Y, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_WHEEL)"), MoveCurve(cs.get(codes.ABS_Z, None)), 0)
      ss.add(ED3.parse("click(mouse.BTN_MIDDLE)"), SnapTo(joySnaps, "z"), 0)
      ss.add(ED3.parse("doubleclick(mouse.BTN_MIDDLE)"), SnapTo(joySnaps, "xy"), 0)
      ss.add(ED3.parse("release(mouse.BTN_LEFT)"), SnapTo(headSnaps, "current"), 0)
      ss.add(ED3.parse("init(1)"), ResetCurves(cs.values()))
      ss = add_scale_sink(ss, cj[0])
      joystickModeSink.add(0, ss)

    if 1 in cj:
      #logger.debug("Init mode 1")
      cs = cj[1]["curves"]["joystick"]

      ss = BindSink(cmpOp)
      ss.add(ED3.parse("move(mouse.REL_X)+"), MoveCurve(cs.get(codes.ABS_X, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_X)+"), MoveCurve(cs.get(codes.ABS_Z, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_X)+keyboard.KEY_RIGHTSHIFT"), MoveCurve(cs.get(codes.ABS_Z, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_Y)"), MoveCurve(cs.get(codes.ABS_Y, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_WHEEL)"), MoveCurve(cs.get(codes.ABS_Z, None)), 0)
      ss.add(ED3.parse("click(mouse.BTN_MIDDLE)"), SnapTo(joySnaps, "z"), 0)
      ss.add(ED3.parse("doubleclick(mouse.BTN_MIDDLE)"), SnapTo(joySnaps, "xy"), 0)
      ss.add(ED3.parse("release(mouse.BTN_LEFT)"), SnapTo(headSnaps, "ff"), 0)
      ss.add(ED3.parse("init(1)"), ResetCurves(cs.values()))
      ss = add_scale_sink(ss, cj[1])
      joystickModeSink.add(1, ss)

    if 2 in cj:
      #logger.debug("Init mode 2")
      cs = cj[2]["curves"]["joystick"]

      ss = BindSink(cmpOp)
      ss.add(ED3.parse("move(mouse.REL_X)"), MoveCurve(cs.get(codes.ABS_X, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_Y)"), MoveCurve(cs.get(codes.ABS_Y, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_WHEEL)+"), MoveCurve(cs.get(codes.ABS_THROTTLE, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_WHEEL)+keyboard.KEY_RIGHTCTRL"), MoveCurve(cs.get(codes.ABS_RUDDER, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_WHEEL)+keyboard.KEY_LEFTCTRL"), MoveCurve(cs.get(codes.ABS_RUDDER, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_WHEEL)+keyboard.KEY_RIGHTSHIFT"), MoveCurve(cs.get(codes.ABS_RX, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_WHEEL)+keyboard.KEY_RIGHTALT"), MoveCurve(cs.get(codes.ABS_RY, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_WHEEL)+keyboard.KEY_LEFTALT"), MoveCurve(cs.get(codes.ABS_RY, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_WHEEL)+keyboard.KEY_LEFTSHIFT"), MoveCurve(cs.get(codes.ABS_RZ, None)), 0)
      ss.add(ED3.parse("doubleclick(mouse.BTN_MIDDLE)"), SnapTo(joySnaps, "xy"), 0)
      ss.add(ED3.parse("release(mouse.BTN_LEFT)"), SnapTo(headSnaps, "fb"), 0)
      ss.add(ED3.parse("init(1)"), ResetCurves(cs.values()))
      ss = add_scale_sink(ss, cj[2])
      joystickModeSink.add(2, ss)

    joystickModeSink.set_mode(0)

  if "secondary" in curves:
    topModeSink.add(1, init_base_head(curves["secondary"], headSnaps))

  return topBindSink

layout_initializers["base41"] = init_layout_base41


def init_layout_base42(settings):
  cmpOp = CmpWithModifiers()
  curveSet = settings["config"].get("curves", None)
  if curveSet is None:
    raise Exception("No curve set specified in settings")
  curveMaker = curveMakers.get(curveSet, None)
  if curveMaker is None:
    raise Exception("No curves for {}".format(curveSet))
  
  curves = curveMaker(settings)

  joySnaps = init_base_joystick_snaps(settings["axes"]["joystick"])
  headSnaps = init_base_head_snaps(settings["axes"]["head"])

  topBindSink = BindSink(cmpOp)
  topModeSink = ModeSink()
  topBindSink.add(ED3.parse("any()"), topModeSink, 1)
  topBindSink.add(ED3.parse("press(mouse.BTN_RIGHT)"), SetMode(topModeSink, 1), 0)
  topBindSink.add(ED3.parse("release(mouse.BTN_RIGHT)"), SetMode(topModeSink, 0), 0)

  joystickBindSink = BindSink(cmpOp)
  topModeSink.add(0, joystickBindSink)
  topModeSink.set_mode(0)

  joystickModeSink = joystickBindSink.add(ED3.parse("any()"), ModeSink(), 1)

  jmm = ModeSinkModeManager(joystickModeSink)
  joystickBindSink.add(ED3.parse("press(mouse.BTN_EXTRA)"), jmm.make_cycle([1,0], True), 0)
  joystickBindSink.add(ED3.parse("release(mouse.BTN_EXTRA)"), jmm.make_restore(), 0)
  joystickBindSink.add(ED3.parse("doubleclick(mouse.BTN_EXTRA)"), jmm.make_cycle([1,0], False), 0)
  joystickBindSink.add(ED3.parse("press(mouse.BTN_SIDE)"), jmm.make_set(2, True), 0)
  joystickBindSink.add(ED3.parse("release(mouse.BTN_SIDE)"), jmm.make_restore(), 0)
  joystickBindSink.add(ED3.parse("init(1)"), jmm.make_set(0, False), 0)
  joystickBindSink.add(ED3.parse("init(1)"), jmm.make_clear(), 0)

  if "primary" in curves:
    cj = curves["primary"]
    if 0 in cj:
      #logger.debug("Init mode 0")
      cs = cj[0]["curves"]["joystick"]

      ss = BindSink(cmpOp)
      ss.add(ED3.parse("move(mouse.REL_X)"), MoveCurve(cs.get(codes.ABS_X, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_Y)"), MoveCurve(cs.get(codes.ABS_Y, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_WHEEL)"), MoveCurve(cs.get(codes.ABS_Z, None)), 0)
      ss.add(ED3.parse("click(mouse.BTN_MIDDLE)"), SnapTo(joySnaps, "z"), 0)
      ss.add(ED3.parse("doubleclick(mouse.BTN_MIDDLE)"), SnapTo(joySnaps, "xy"), 0)
      ss.add(ED3.parse("release(mouse.BTN_LEFT)"), SnapTo(headSnaps, "current"), 0)
      ss.add(ED3.parse("init(1)"), ResetCurves(cs.values()))
      ss = add_scale_sink(ss, cj[0])
      joystickModeSink.add(0, ss)

    if 1 in cj:
      #logger.debug("Init mode 1")
      cs = cj[1]["curves"]["joystick"]

      ss = BindSink(cmpOp)
      ss.add(ED3.parse("move(mouse.REL_X)"), MoveCurve(cs.get(codes.ABS_Z, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_Y)"), MoveCurve(cs.get(codes.ABS_Y, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_WHEEL)"), MoveCurve(cs.get(codes.ABS_X, None)), 0)
      ss.add(ED3.parse("click(mouse.BTN_MIDDLE)"), SnapTo(joySnaps, "x"), 0)
      ss.add(ED3.parse("doubleclick(mouse.BTN_MIDDLE)"), SnapTo(joySnaps, "zy"), 0)
      ss.add(ED3.parse("release(mouse.BTN_LEFT)"), SnapTo(headSnaps, "ff"), 0)
      ss.add(ED3.parse("init(1)"), ResetCurves(cs.values()))
      ss = add_scale_sink(ss, cj[1])
      joystickModeSink.add(1, ss)

    if 2 in cj:
      #logger.debug("Init mode 2")
      cs = cj[2]["curves"]["joystick"]

      ss = BindSink(cmpOp)
      ss.add(ED3.parse("move(mouse.REL_X)"), MoveCurve(cs.get(codes.ABS_X, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_X)"), MoveCurve(cs.get(codes.ABS_Z, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_Y)"), MoveCurve(cs.get(codes.ABS_Y, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_WHEEL)+"), MoveCurve(cs.get(codes.ABS_THROTTLE, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_WHEEL)+keyboard.KEY_RIGHTCTRL"), MoveCurve(cs.get(codes.ABS_RUDDER, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_WHEEL)+keyboard.KEY_LEFTCTRL"), MoveCurve(cs.get(codes.ABS_RUDDER, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_WHEEL)+keyboard.KEY_RIGHTSHIFT"), MoveCurve(cs.get(codes.ABS_RX, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_WHEEL)+keyboard.KEY_RIGHTALT"), MoveCurve(cs.get(codes.ABS_RY, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_WHEEL)+keyboard.KEY_LEFTALT"), MoveCurve(cs.get(codes.ABS_RY, None)), 0)
      ss.add(ED3.parse("move(mouse.REL_WHEEL)+keyboard.KEY_LEFTSHIFT"), MoveCurve(cs.get(codes.ABS_RZ, None)), 0)
      ss.add(ED3.parse("doubleclick(mouse.BTN_MIDDLE)"), SnapTo(joySnaps, "xy"), 0)
      ss.add(ED3.parse("doubleclick(mouse.BTN_MIDDLE)"), SnapTo(joySnaps, "z"), 0)
      ss.add(ED3.parse("release(mouse.BTN_LEFT)"), SnapTo(headSnaps, "fb"), 0)
      ss.add(ED3.parse("init(1)"), ResetCurves(cs.values()))
      ss = add_scale_sink(ss, cj[2])
      joystickModeSink.add(2, ss)

    joystickModeSink.set_mode(0)

  if "secondary" in curves:
    topModeSink.add(1, init_base_head(curves["secondary"], headSnaps))

  return topBindSink

layout_initializers["base42"] = init_layout_base42


def init_layout_descent(settings):
  cmpOp = CmpWithModifiers()

  curveSet = settings["config"].get("curves", None)
  if curveSet is None:
    raise Exception("No curve set specified in settings")
  curveMaker = curveMakers.get(curveSet, None)
  if curveMaker is None:
    raise Exception("No curves for {}".format(curveSet))
  
  joystick = settings["outputs"]["joystick"]

  curves = curveMaker(settings)["primary"]
  axes = settings["axes"]["joystick"]

  joystickSink = BindSink(cmpOp)
  joystickSink.add(ED3.parse("press(mouse.BTN_LEFT)"), SetButtonState(joystick, codes.BTN_0, 1), 0)
  joystickSink.add(ED3.parse("release(mouse.BTN_LEFT)"), SetButtonState(joystick, codes.BTN_0, 0), 0)
  joystickSink.add(ED3.parse("press(mouse.BTN_RIGHT)"), SetButtonState(joystick, codes.BTN_1, 1), 0)
  joystickSink.add(ED3.parse("release(mouse.BTN_RIGHT)"), SetButtonState(joystick, codes.BTN_1, 0), 0)

  joystickModeSink = joystickSink.add(ED3.parse("any()"), ModeSink(), 1)
  jmm = ModeSinkModeManager(joystickModeSink)
  joystickSink.add(ED3.parse("press(mouse.BTN_EXTRA)"), jmm.make_cycle([1,0], MSMMSavePolicy.CLEAR_AND_SAVE), 0)
  joystickSink.add(ED3.parse("release(mouse.BTN_EXTRA)"), jmm.make_restore(), 0)
  joystickSink.add(ED3.parse("doubleclick(mouse.BTN_EXTRA)"), jmm.make_cycle([1,0], MSMMSavePolicy.CLEAR), 0)
  joystickSink.add(ED3.parse("press(mouse.BTN_SIDE)"), jmm.make_cycle([2,0], MSMMSavePolicy.CLEAR_AND_SAVE), 0)
  joystickSink.add(ED3.parse("release(mouse.BTN_SIDE)"), jmm.make_restore(), 0)
  joystickSink.add(ED3.parse("doubleclick(mouse.BTN_SIDE)"), jmm.make_cycle([2,0], MSMMSavePolicy.CLEAR), 0)
  joystickSink.add(ED3.parse("init(1)"), jmm.make_set(0, MSMMSavePolicy.NOOP), 0)
  joystickSink.add(ED3.parse("init(1)"), jmm.make_clear(), 0)

  if 0 in curves:
    #logger.debug("Init mode 0")
    cs = curves[0]["curves"]["joystick"]

    ss = BindSink(cmpOp)
    ss.add(ED3.parse("move(mouse.REL_X)"), MoveCurve(cs.get(codes.ABS_X, None)), 0)
    ss.add(ED3.parse("move(mouse.REL_Y)"), MoveCurve(cs.get(codes.ABS_Y, None)), 0)
    ss.add(ED3.parse("move(mouse.REL_WHEEL)"), MoveCurve(cs.get(codes.ABS_Z, None)), 0)
    ss.add(ED3.parse("click(mouse.BTN_MIDDLE)"), MoveAxis(axes.get(codes.ABS_Z, None), value=0.0, relative=False), 0)
    ss.add(ED3.parse("doubleclick(BTN_MIDDLE)"), MoveAxes([(axes.get(axisId, None), 0.0, False) for axisId in (codes.ABS_X, codes.ABS_Y)]), 0)
    ss.add(ED3.parse("init(0)"), MoveAxes([(axes.get(axisId, None), 0.0, False) for axisId in (codes.ABS_X, codes.ABS_Y, codes.ABS_Z)]))
    ss = add_scale_sink(ss, curves[0])
    joystickModeSink.add(0, ss)

  if 1 in curves:
    #logger.debug("Init mode 1")
    cs = curves[1]["curves"]["joystick"]

    ss = BindSink(cmpOp)
    ss.add(ED3.parse("move(mouse.REL_X)"), MoveCurve(cs.get(codes.ABS_Z, None)), 0)
    ss.add(ED3.parse("move(mouse.REL_Y)"), MoveCurve(cs.get(codes.ABS_Y, None)), 0)
    ss.add(ED3.parse("move(mouse.REL_WHEEL)"), MoveCurve(cs.get(codes.ABS_X, None)), 0)
    ss.add(ED3.parse("click(mouse.BTN_MIDDLE)"), MoveAxis(axes.get(codes.ABS_X, None), value=0.0, relative=False), 0)
    ss.add(ED3.parse("doubleclick(BTN_MIDDLE)"), MoveAxes([(axes.get(axisId, None), 0.0, False) for axisId in (codes.ABS_Z, codes.ABS_Y)]), 0)
    ss.add(ED3.parse("init(0)"), MoveAxes([(axes.get(axisId, None), 0.0, False) for axisId in (codes.ABS_X, codes.ABS_Y, codes.ABS_Z)]))
    ss = add_scale_sink(ss, curves[1])
    joystickModeSink.add(1, ss)

  if 2 in curves:
    #logger.debug("Init mode 2")
    cs = curves[2]["curves"]["joystick"]

    ss = BindSink(cmpOp)
    ss.add(ED3.parse("move(mouse.REL_X)"), MoveCurve(cs.get(codes.ABS_RX, None)), 0)
    ss.add(ED3.parse("move(mouse.REL_Y)"), MoveCurve(cs.get(codes.ABS_RY, None)), 0)
    ss.add(ED3.parse("move(mouse.REL_WHEEL)+"), MoveCurve(cs.get(codes.ABS_THROTTLE, None)), 0)
    ss.add(ED3.parse("click(mouse.BTN_MIDDLE)"), MoveAxis(axes.get(codes.ABS_THROTTLE, None), value=0.0, relative=False), 0)
    ss.add(ED3.parse("doubleclick(BTN_MIDDLE)"), MoveAxes([(axes.get(axisId, None), 0.0, False) for axisId in (codes.ABS_RX, codes.ABS_RY)]), 0)
    moveRudder = MoveCurve(cs.get(codes.ABS_RUDDER, None))
    ss.add(ED3.parse("move(mouse.REL_WHEEL)+keyboard.KEY_RIGHTSHIFT"), moveRudder, 0)
    ss.add(ED3.parse("move(mouse.REL_WHEEL)+keyboard.KEY_LEFTSHIFT"), moveRudder, 0)
    setRudder = SetCurveAxis2(cs.get(codes.ABS_RUDDER, None), value=0.0, relative=False, reset=True)
    ss.add(ED3.parse("click(mouse.BTN_MIDDLE)+keyboard.KEY_RIGHTSHIFT"), setRudder, 0)
    ss.add(ED3.parse("click(mouse.BTN_MIDDLE)+keyboard.KEY_LEFTSHIFT"), setRudder, 0)
    ss.add(ED3.parse("init(0)"), MoveAxes([(axes.get(axisId, None), 0.0, False) for axisId in (codes.ABS_RX, codes.ABS_RY)]))
    ss.add(ED3.parse("init(0)"), ResetCurves([cs.get(axisId, None) for axisId in (codes.ABS_RX, codes.ABS_RY, codes.ABS_THROTTLE, codes.ABS_RUDDER)]))
    ss = add_scale_sink(ss, curves[2])
    joystickModeSink.add(2, ss)

  joystickModeSink.set_mode(0)
    
  return joystickSink

layout_initializers["descent"] = init_layout_descent

def get_event_type(i):
  d = {"ABS" : codes.EV_ABS, "REL" : codes.EV_REL, "KEY" : codes.EV_KEY, "BTN" : codes.EV_KEY }
  return d.get(i[:3], None)

def init_layout_config(settings):
  config = settings["config"]
  layoutName = config["configCurves"]
  logger.info("Using '{}' layout from config".format(layoutName))
  cfg = config["layouts"].get(layoutName, None)
  if cfg is None:
    raise Exception("'{}' layout not found in config".format(layoutName))
  else:
    try:
      parser = settings["parser"]
      state = {"settings" : settings, "parser" : parser}
      r = parser("sink", cfg, state)
      return r
    except KeyError as e:
      logger.error("Error while initializing config layout '{}': cannot find key '{}'".format(layoutName, str(e)))
      raise
    except Exception as e:
      logger.error("Error while initializing config layout '{}': {}".format(layoutName, e))
      raise

layout_initializers["config"] = init_layout_config


def parse_list(cfg, state, vp):
  r = []
  for data in cfg:
    value = vp(data, state)
    r.append(value)
  return r


def parse_dict(cfg, state, kp, vp):
  r = {}
  for key,value in cfg.items():
    r[kp(key, state)] = vp(value, state)
  return r


class SelectParser:
  def __call__(self, key, cfg, state):
    if key not in self.parsers_:
      raise RuntimeError("Parser for '{}' not found, available parsers are: {}".format(key, self.parsers_.keys()))
    else:
      parser = self.parsers_[key]
      try:
        r = parser(cfg, state) 
        return r
      except Exception as e:
        logger.debug("{}, so cannot parse {}".format(e, cfg))
        raise

  def add(self, key, parser):
    self.parsers_[key] = parser

  def get(self, key):
    return self.parsers_.get(key, None)

  def __init__(self, parsers=None):
    self.parsers_ = {} if parsers is None else parsers


class IntrusiveSelectParser:
  """FreePie does not handle inheritance well, so this class is implemented via composition."""
  def __call__(self, cfg, state):
    key = self.keyOp_(cfg)
    logger.debug(cfg)
    return self.p_(key, cfg, state)

  def add(self, key, parser):
    self.p_.add(key, parser)

  def get(self, key):
    return self.p_.get(key)

  def __init__(self, keyOp, parsers=None):
    self.keyOp_ = keyOp
    self.p_ = SelectParser(parsers)


def make_parser():
  parser = SelectParser()

  opParser = IntrusiveSelectParser(keyOp=lambda cfg : cfg["op"])
  parser.add("op", opParser)

  def make_symm_wrapper(wrapped, symm):
    if symm == 1:
      return lambda x : wrapped(abs(x))
    elif symm == 2:
      return lambda x : sign(x)*wrapped(abs(x))
    else:
      return wrapped

  def constant(cfg, state):
    return ConstantApproximator(cfg["value"])
  opParser.add("constant", constant)

  def segment(cfg, state):
    def make_op(data, symmetric):
      approx = SegmentApproximator(data, 1.0, True, True)
      return make_symm_wrapper(approx, symmetric)
    return make_op(cfg["points"], cfg.get("symmetric", 0))
  opParser.add("segment", segment)

  def poly(cfg, state):
    def make_op(data, symmetric):
      d = [(k,int(p)) for p,k in data.items()]
      def op(x):
        r = 0.0
        for k,p in d:
          r += k*x**p
        return r
      return make_symm_wrapper(op, symmetric)
    return make_op(cfg["coeffs"], cfg.get("symmetric", 0))
  opParser.add("poly", poly)
  
  def bezier(cfg, state):
    def make_op(data, symmetric):
      approx = BezierApproximator(data)
      return make_symm_wrapper(approx, symmetric)
    return make_op(cfg["points"], cfg.get("symmetric", 0))
  opParser.add("bezier", bezier)

  def sbezier(cfg, state):
    def make_op(data, symmetric):
      approx = SegmentedBezierApproximator(data)
      return make_symm_wrapper(approx, symmetric)
    return make_op(cfg["points"], cfg.get("symmetric", 0))
  opParser.add("sbezier", sbezier)

  curveParser = IntrusiveSelectParser(keyOp=lambda cfg : cfg["curve"])
  parser.add("curve", curveParser)

  def parsePoints(cfg, state):
    """Helper"""
    pointParsers = {}
    def parseFixedPoint(cfg, state):
      p = Point(op=state["parser"]("op", cfg, state), center=cfg.get("center", 0.0))
      return p
    pointParsers["fixed"] = parseFixedPoint
    def parseMovingPoint(cfg, state):
      p = Point(op=state["parser"]("op", cfg, state), center=None)
      return p
    pointParsers["moving"] = parseMovingPoint
    r = {}
    for n,d in cfg.items():
      state["point"] = n
      r[n] = pointParsers[n](d, state)
    return r

  def parseResetPolicy(cfg, state):
    """Helper"""
    d = {
      "setToCurrent" : PointMovingCurveResetPolicy.SET_TO_CURRENT,
      "setToNone" : PointMovingCurveResetPolicy.SET_TO_NONE,
      "dontTouch" : PointMovingCurveResetPolicy.DONT_TOUCH
    }
    return d.get(cfg, PointMovingCurveResetPolicy.DONT_TOUCH)

  def getAxis(fullAxisName, state):
    outputName, axisName = split_full_name(fullAxisName)
    allAxes = state["settings"]["axes"]
    if outputName not in allAxes:
      raise RuntimeError("No axes were initialized for '{}'".format(outputName, fullAxisName))
    outputAxes = allAxes[outputName]
    axisId = name2code(axisName)
    if axisId not in outputAxes:
      raise RuntimeError("Axis was not initialized for '{}'".format(fullAxisName))
    axis = outputAxes[axisId]
    return axis

  def parsePointsOutputBasedCurve(cfg, state):
    axis = getAxis(state["axis"], state)
    points = parsePoints(cfg["points"], state)
    vpoName = cfg.get("vpo", None)
    ops = {
      "min" : get_min_op,
      "mul" : multiply_op,
      "interpolate" : interpolate_op
    }
    op = ops.get(vpoName, interpolate_op)
    vpo = SimpleValuePointOp(points.values(), op)
    deltaOp = lambda x,value : x*value
    curve = OutputBasedCurve(deltaOp, vpo, axis)

    if "moving" in points:
      point = points["moving"]
      pointCfg = cfg["points"]["moving"]
      def getValueOp(curve): 
        return curve.get_axis().get()
      def make_center_op(newRatio, l):
        oldRatio = 1.0 - newRatio 
        def op(new,old):
          v = oldRatio*old+newRatio*new
          delta = v - new
          r = new + sign(delta)*clamp(abs(delta), 0.0, l)
          return r
        return op
      centerOp = None
      if "centerOp" in pointCfg:
        centerOpCfg = pointCfg["centerOp"]
        newRatio = clamp(centerOpCfg.get("newValueRatio", 0.5), 0.0, 1.0)
        centerOp = make_center_op(centerOpCfg.get("newValueRatio", 0.5), centerOpCfg.get("limit", float("inf")))
      else:
        newRatio = clamp(pointCfg.get("newValueRatio", 0.5), 0.0, 1.0)
        centerOp=make_center_op(newRatio, float("inf"))
      resetDistance = pointCfg.get("resetDistance", float("inf"))
      onReset = parseResetPolicy(pointCfg.get("onReset", "setToCurrent"), state)
      onMove = parseResetPolicy(pointCfg.get("onMove", "setToNone"), state)
      curve = PointMovingCurve(
        next=curve, point=point, getValueOp=getValueOp, centerOp=centerOp, resetDistance=resetDistance, onReset=onReset, onMove=onMove)

    axis.add_listener(curve)
    return curve
  curveParser.add("pointsOut", parsePointsOutputBasedCurve)

  def parseFixedPointInputBasedCurve(cfg, state):
    axis = getAxis(state["axis"], state)
    points = parsePoints(cfg["points"], state)
    fp = points["fixed"]
    interpolationDistance = cfg.get("interpolationDistance", 0.3)
    interpolationFactor = cfg.get("interpolationFactor", 1.0)
    posLimits = cfg.get("posLimits", (-1.1, 1.1))
    interpolateOp = FMPosInterpolateOp(fp=fp, mp=None, interpolationDistance=interpolationDistance, factor=interpolationFactor, posLimits=posLimits, eps=0.01)
    curve = InputBasedCurve(op=interpolateOp, axis=axis, posLimits=posLimits)
    axis.add_listener(curve)
    return curve
  curveParser.add("fpointIn", parseFixedPointInputBasedCurve)

  def parsePointsInputBasedCurve(cfg, state):
    axis = getAxis(state["axis"], state)
    points = parsePoints(cfg["points"], state)
    fp = points["fixed"]
    mp = points.get("moving", Point(op=lambda x : 0.0, center=None))
    interpolationDistance = cfg.get("interpolationDistance", 0.3)
    interpolationFactor = cfg.get("interpolationFactor", 1.0)
    resetDistance = 0.0 if "moving" not in cfg["points"] else cfg["points"]["moving"].get("resetDistance", 0.4)
    posLimits = cfg.get("posLimits", (-1.1, 1.1))
    interpolateOp = FMPosInterpolateOp(fp=fp, mp=mp, interpolationDistance=interpolationDistance, factor=interpolationFactor, posLimits=posLimits, eps=0.001)
    curve = InputBasedCurve(op=interpolateOp, axis=axis, posLimits=posLimits)
    def getValueOp(curve): 
      return curve.get_pos()
    centerOp = IterativeCenterOp(point=mp, op=interpolateOp) 
    onReset = parseResetPolicy(cfg.get("onReset", "setToCurrent"), state)
    onMove = parseResetPolicy(cfg.get("onMove", "setToNone"), state)
    curve = PointMovingCurve(
      next=curve, point=mp, getValueOp=getValueOp, centerOp=centerOp, resetDistance=resetDistance, onReset=onReset, onMove=onMove)
    axis.add_listener(curve)
    return curve
  curveParser.add("pointsIn", parsePointsInputBasedCurve)

  def parseOutputDeltaLinkingCurve(cfg, state):
    controlledAxis = getAxis(state["axis"], state)
    sensOp = state["parser"]("op", cfg, state)
    deltaOp = lambda delta, sens : delta*sens
    controllingAxis = getAxis(cfg["controlling"], state)
    radius = cfg.get("radius", float("inf"))
    curve = OutputDeltaLinkingCurve(controllingAxis, controlledAxis, sensOp, deltaOp, radius)
    controlledAxis.add_listener(curve)
    controllingAxis.add_listener(curve)
    return curve
  curveParser.add("outDeltaLink", parseOutputDeltaLinkingCurve)

  def parseInputDeltaLinkingCurve(cfg, state):
    controlledAxis = getAxis(state["axis"], state)
    op = state["parser"]("op", cfg, state)
    controllingAxis = getAxis(cfg["controlling"], state)
    radius = cfg.get("radius", float("inf"))
    threshold = cfg.get("threshold", 0.0)
    threshold = None if threshold == "none" else float(threshold)
    curve = InputDeltaLinkingCurve(controllingAxis, controlledAxis, op, radius, threshold)
    controlledAxis.add_listener(curve)
    controllingAxis.add_listener(curve)
    return curve
  curveParser.add("inDeltaLink", parseInputDeltaLinkingCurve)

  def parseInputLinkingCurve(cfg, state):
    controlledAxis = getAxis(state["axis"], state)
    op = state["parser"]("op", cfg, state)
    controllingAxis = getAxis(cfg["controlling"], state)
    curve = InputLinkingCurve(controllingAxis, controlledAxis, op)
    controlledAxis.add_listener(curve)
    controllingAxis.add_listener(curve)
    return curve
  curveParser.add("inLink", parseInputLinkingCurve)

  def parsePresetCurve(cfg, state):
    presets = state["settings"]["config"]["presets"]
    presetName = cfg["name"]
    presetCfg = presets[presetName]
    return state["parser"]("curve", presetCfg, state)
  curveParser.add("preset", parsePresetCurve)

  def parseBases_(wrapped):
    def parseBasesOp(cfg, state):
      """Merges all base config definitions if they are specified."""
      bases = cfg.get("bases", None)
      if bases is not None:
        layouts, full = state["settings"]["config"]["layouts"], {}
        for b in bases:
          merge_dicts(full, layouts[b])
        merge_dicts(full, cfg)
        cfg = full
      return wrapped(cfg, state)
    return parseBasesOp

  sinkParser = IntrusiveSelectParser(keyOp=lambda cfg : cfg["type"])
  parser.add("sink", sinkParser)

  def parseModifiers_(sink, cfg, state):
    """Adds modifier sink if 'modifiers' property is present."""
    if "modifiers" in cfg:
      modifiers = [split_full_name_code(m) for m in cfg["modifiers"]]
      modifierSink = ModifierSink(next=sink, modifiers=modifiers)
      #saves event modifiers (if present), sets new modifers and restores old ones after call if needed
      def parseModifiersWrapper(event):
        oldModifiers = event.modifiers if hasattr(event, "modifiers") else None
        event.modifiers = modifiers
        try:
          #logger.debug("parseModifiersWrapper(): passing event {} to {}".format(event, modifierSink))
          modifierSink(event)
          if event.type == EV_BCAST and event.code == BC_INIT and event.value == 0:
            modifierSink.clear()
        except:
          raise
        finally:
          if oldModifiers is not None: event.modifiers = oldModifiers
      return parseModifiersWrapper
    else:
      return sink

  def parseModifiers(cfg, state):
    """Creates modifiers sink."""
    nextCfg = cfg["next"]
    nextSink = state["parser"]("sink", nextCfg, state)
    return parseModifiers_(nextSink, cfg, state)
  sinkParser.add("modifiers", parseBases_(parseModifiers))

  def parseSens_(sink, cfg, state):
    """Adds modifier sink if 'modifiers' property is present."""
    if "sens" in cfg:
      sens = {split_full_name_code(fullAxisName):value for fullAxisName,value in cfg["sens"].items()}
      keyOp = lambda event : ((event.source, event.code), (None, event.code))
      scaleSink = ScaleSink2(sens, keyOp)
      scaleSink.set_next(sink)
      def wrapper(event):
        oldValue = event.value
        try:
          scaleSink(event)
        except:
          raise
        finally:
          event.value = oldValue
      return wrapper
    else:
      return sink

  def parseSens(cfg, state):
    """Creates sens sink."""
    nextCfg = cfg["next"]
    nextSink = state["parser"]("sink", nextCfg, state)
    return parseSens_(nextSink, cfg, state)
  sinkParser.add("sens", parseBases_(parseSens))

  def parseExtra_(sink, cfg, state):
    for f in (parseSens_, parseModifiers_):
      sink = f(sink, cfg, state)
    return sink

  def parseMode(cfg, state):
    """Creates mode sink."""
    modeSink = ModeSink()
    if "modes" in cfg:
      for modeName,modeCfg in cfg["modes"].items():
        child = state["parser"]("sink", modeCfg, state)
        modeSink.add(modeName, child)
    if "initialMode" in cfg:
      modeSink.set_mode(cfg["initialMode"])
    msmm = ModeSinkModeManager(modeSink)
    state["msmm"] = msmm
    bindingSink = parseBinding_(cfg, state)
    bindingSink.add(ED.any(), modeSink, 1)
    return parseExtra_(bindingSink, cfg, state)
  sinkParser.add("mode", parseBases_(parseMode))

  def parseState(cfg, state):
    """Creates state sink."""
    sink = StateSink()
    if "initialState" in cfg:
      sink.set_state(cfg["initialState"])
    nextCfg = cfg["next"]
    sink.set_next(state["parser"]("sink", nextCfg, state))
    state["sink"] = sink
    bindingSink = parseBinding_(cfg, state)
    bindingSink.add(ED.any(), sink, 1)
    return parseExtra_(bindingSink, cfg, state)
  sinkParser.add("state", parseBases_(parseState))

  sinkParser.add("saveMode", lambda cfg, state : state["msmm"].make_save())
  sinkParser.add("restoreMode", lambda cfg, state : state["msmm"].make_restore())
  sinkParser.add("clearMode", lambda cfg, state : state["msmm"].make_clear())
  sinkParser.add("setMode", lambda cfg, state : state["msmm"].make_set(cfg["mode"], nameToMSMMSavePolicy(cfg.get("savePolicy", "noop"))))
  sinkParser.add("cycleMode", lambda cfg, state : state["msmm"].make_cycle(cfg["modes"], nameToMSMMSavePolicy(cfg.get("savePolicy", "noop"))))

  def parseSetState(cfg, state):
    s = cfg["state"]
    return SetState(state["sink"], s)
  sinkParser.add("setState", parseSetState)

  def parseMove(cfg, state):
    fullAxisName = cfg["axis"]
    state["axis"] = fullAxisName
    curve = state["parser"]("curve", cfg, state)
    if "curves" not in state:
      state["curves"] = {}
    if fullAxisName not in state["curves"]:
      state["curves"][fullAxisName] = []
    state["curves"][fullAxisName].append(curve)
    return MoveCurve(curve)
  sinkParser.add("move", parseMove)

  def parseSetAxis(cfg, state):
    axis = getAxis(cfg["axis"], state)
    value = float(cfg["value"])
    r = MoveAxis(axis, value, False)
    return r
  sinkParser.add("setAxis", parseSetAxis)

  def parseSetAxes(cfg, state):
    axesAndValues = []
    allAxes = state["settings"]["axes"]
    for fullAxisName,value in cfg["axesAndValues"].items():
      axis = getAxis(fullAxisName, state)
      value = float(value)
      axesAndValues.append([axis, value, False])
    r = MoveAxes(axesAndValues)
    return r
  sinkParser.add("setAxes", parseSetAxes)

  def parseSetKeyState(cfg, state):
    output, key = split_full_name(cfg["key"])
    key = name2code(key)
    state = int(cfg["state"])
    return SetButtonState(output, key, state)
  sinkParser.add("setKeyState", parseSetKeyState)

  def parseResetCurves(cfg, state):
    #logger.debug("collected curves: {}".format(state["curves"]))
    allCurves = state.get("curves", None)
    if allCurves is None:
      raise Exception("No curves were initialized for any axis")
    curvesToReset = []
    for fullAxisName in cfg["axes"]:
      curves = allCurves.get(fullAxisName, None)
      if curves is None:
        logger.warning("No curves were initialized for '{}' axis (encountered when parsing '{}')".format(fullAxisName, cfg))
      else:
        curvesToReset += curves
    #logger.debug("selected curves: {}".format(curves))
    return ResetCurves(curvesToReset)
  sinkParser.add("resetCurves", parseResetCurves)

  def createSnap_(cfg, state):
    if "snapManager" not in state:
      state["snapManager"] = AxisSnapManager()
    snapManager = state["snapManager"]
    snapName = cfg["snap"]
    if not snapManager.has_snap(snapName): 
      snaps = state["settings"]["config"]["snaps"]
      fullAxesNamesAndValues = snaps[snapName]
      settings = state["settings"]
      allAxes = settings["axes"]
      snap = []
      for fullAxisName,value in fullAxesNamesAndValues.items():
        outputName, axisName = split_full_name(fullAxisName)
        axisId = name2code(axisName)
        axis = allAxes[outputName][axisId]
        snap.append((axis, value))
      snapManager.set_snap(snapName, snap)

  def parseUpdateSnap(cfg, state):
    createSnap_(cfg, state)
    snapName = cfg["snap"]
    snapManager = state["snapManager"]
    return UpdateSnap(snapManager, snapName)
  sinkParser.add("updateSnap", parseUpdateSnap)

  def parseSnapTo(cfg, state):
    createSnap_(cfg, state)
    snapName = cfg["snap"]
    snapManager = state["snapManager"]
    return SnapTo(snapManager, snapName)
  sinkParser.add("snapTo", parseSnapTo)

  edParser = IntrusiveSelectParser(keyOp=lambda cfg : cfg["type"])
  parser.add("ed", edParser)

  def parseEdModifiers_(r, cfg):
    """Helper"""
    if "modifiers" in cfg:
      modifiers = [split_full_name_code(m) for m in cfg["modifiers"]]
      r.append(("modifiers", modifiers)) 
    return r

  def parseKey_(cfg, state, value):
    """Helper"""
    source, key = split_full_name(cfg["key"])
    eventType = get_event_type(key)
    key = name2code(key)
    r = [("type", eventType), ("code", key), ("value", value)]
    if source is not None:
      r.append(("source", source))
    return r

  def parsePress(cfg, state):
    return parseEdModifiers_(parseKey_(cfg, state, 1), cfg)
  edParser.add("press", parsePress)

  def parseRelease(cfg, state):
    return parseEdModifiers_(parseKey_(cfg, state, 0), cfg)
  edParser.add("release", parseRelease)

  def parseClick(cfg, state):
    r = parseKey_(cfg, state, 3) 
    r.append(("num_clicks", 1))
    r = parseEdModifiers_(r, cfg)
    return r
  edParser.add("click", parseClick)

  def parseDoubleClick(cfg, state):
    r = parseKey_(cfg, state, 3) 
    r.append(("num_clicks", 2))
    r = parseEdModifiers_(r, cfg)
    return r
  edParser.add("doubleclick", parseDoubleClick)

  def parseMultiClick(cfg, state):
    r = parseKey_(cfg, state, 3) 
    num = int(cfg["numClicks"])
    r.append(("num_clicks", num))
    r = parseEdModifiers_(r, cfg)
    return r
  edParser.add("multiclick", parseMultiClick)

  def parseMove(cfg, state):
    source, axis = split_full_name(cfg["axis"])
    eventType = get_event_type(axis)
    axis = name2code(axis)
    r = [("type", eventType), ("code", axis)]
    if source is not None:
      r.append(("source", source))
    r = parseEdModifiers_(r, cfg)
    return r
  edParser.add("move", parseMove)

  def parseInit(cfg, state):
    eventName = cfg["event"]
    value = 1 if eventName == "enter" else 0 if eventName == "leave" else None
    assert(value is not None)
    r = [("type", EV_BCAST), ("code", BC_INIT), ("value", value)]
    return r
  edParser.add("init", parseInit)
        
  def parseBinding_(cfg, state):
    def parseInputsOutputs(cfg, state):
      def parseGroup(n1, n2, parser, cfg, state):
        cfgs = cfg[n2] if n2 in cfg else (cfg[n1],) if n1 in cfg else ()
        r = []
        for c in cfgs:
          try:
            r.append(parser(c, state))
          except RuntimeError as e:
            logger.warning("{} (encountered when parsing {} '{}')".format(e, n1, c))
            continue
        return r

      parser = state["settings"]["parser"]

      inputs = parseGroup("input", "inputs", parser.get("ed"), cfg, state)
      if len(inputs) == 0:
        logger.warning("No inputs were constructed (encountered when parsing '{}')".format(cfg))

      outputs = parseGroup("output", "outputs", parser.get("sink"), cfg, state)
      if len(outputs) == 0:
        logger.warning("No outputs were constructed (encountered when parsing '{}')".format(cfg))

      return ((i,o) for i in inputs for o in outputs)

    cmpOp = CmpWithModifiers()
    bindingSink = BindSink(cmpOp)
    state["curves"] = {}
    binds = cfg.get("binds", ())
    #logger.debug("binds: {}".format(binds))
    for bind in binds:
      for i,o in parseInputsOutputs(bind, state):
        bindingSink.add(i, o, 0)
    return bindingSink

  def parseBinding(cfg, state):
    return parseExtra_(parseBinding_(cfg, state), cfg, state)
  sinkParser.add("bind", parseBases_(parseBinding))

  def parseExternal_(groupName):
    def parseExternalOp(cfg, state):
      group = state["settings"]["config"][groupName]
      name = cfg["name"]
      cfg = group[name]
      sink = state["parser"]("sink", cfg, state)
      return sink
    return parseExternalOp

  parser.add("preset", parseBases_(parseExternal_("presets")))
  sinkParser.add("layout", parseBases_(parseExternal_("layouts")))

  outputParser = IntrusiveSelectParser(keyOp=lambda cfg : cfg["type"])
  parser.add("output", outputParser)

  def parseElasicOutput(cfg, state):
    speeds = {name2code(axisName):value for axisName,value in cfg["speeds"].items()}
    next = state["parser"]("output", cfg["next"], state)
    j = ElasticJoystic(next, speeds)
    state["settings"]["updated"].append(lambda tick : j.update(tick))
    return j
  outputParser.add("elastic", parseElasicOutput)
    
  def parseCompositeOutput(cfg, state):
    parser = state["parser"].get("output") 
    children = parse_list(cfg["children"], state, parser)
    return CompositeJoystick(children)
  outputParser.add("composite", parseCompositeOutput)

  def parseOpentrackOutput(cfg, state):
    opentrack = Opentrack(cfg["ip"], int(cfg["port"])) 
    state["settings"]["updated"].append(lambda tick : opentrack.send())
    return opentrack
  outputParser.add("opentrack", parseOpentrackOutput)

  def parseUdpJoystickOutput(cfg, state):
    packetMakers = {
      "il2" : make_il2_packet,
      "il2_6dof" : make_il2_6dof_packet,
      "opentrack" : make_opentrack_packet
    }
    j = UdpJoystick(cfg["ip"], int(cfg["port"]), packetMakers[cfg["format"]]) 
    state["settings"]["updated"].append(lambda tick : j.send())
    return j
  outputParser.add("udpJoystick", parseUdpJoystickOutput)

  return parser
