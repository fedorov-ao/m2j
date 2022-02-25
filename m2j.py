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
import collections
import zlib

logger = logging.getLogger(__name__)

class KeyError2(KeyError):
  def __init__(self, key, keys):
    KeyError.__init__(self, key)
    self.key, self.keys = key, keys
  def __str__(self):
    return "{} not in {}".format(self.key, self.keys)


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


def lerp(fv, fb, fe, tb, te):
  #tv = a*fv + b
  a = (te - tb) / (fe - fb)
  b = te - a*fe
  return a*fv + b


def merge_dicts(destination, source):
  """https://stackoverflow.com/questions/20656135/python-deep-merge-dictionary-data"""
  for key, value in source.items():
    if isinstance(value, collections.OrderedDict):
      # get node or create one
      node = destination.setdefault(key, collections.OrderedDict())
      merge_dicts(node, value)
    elif isinstance(value, dict):
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


def str2(v):
  ps = {
    collections.OrderedDict : ( "{{", "}}" ),
    dict : ( "{", "}" ),
    list : ( "[", "]" ),
    tuple : ( "(", ")" ),
    str : ( '"', '"' ),
    unicode : ( '"', '"' )
  }
  s = str()
  if type(v) in (dict, collections.OrderedDict):
    for a,b in v.items():
      s += str2(a) + " : " + str2(b) + ", "
    s = s[:-2]
  elif type(v) in (tuple, list):
    for a in v:
      s += str2(a) + ", "
    s = s[:-2]
  else:
    s = str(v)
  tv = type(v)
  if tv in ps:
    p = ps[tv]
    s = p[0] + s + p[1]
  return s


def truncate(cfg, l=30, ellipsis=True):
  return str2(cfg)[:l] + "..." if ellipsis else ""


  levelName = settings["config"].get("logLevel", "NOTSET").upper()
  nameToLevel = {
    logging.getLevelName(l).upper():l for l in (logging.CRITICAL, logging.ERROR, logging.WARNING, logging.INFO, logging.DEBUG, logging.NOTSET)
  }


class CfgStack:
  def push(self, k, v):
    p = None
    if k in self.cfg_:
      p = (self.RESTORE, k, self.cfg_[k])
    else:
      p = (self.DELETE, k)
    self.stack_.append(p)
    self.cfg_[k] = v

  def pop(self):
    p = self.stack_.pop()
    if p[0] == self.RESTORE:
      self.cfg_[p[1]] = p[2]
    else:
      del self.cfg_[p[1]]

  def pop_all(self):
    while (len(self.stack_)):
      self.pop()

  def __init__(self, cfg):
    self.cfg_, self.stack_ = cfg, []

  RESTORE = 0
  DELETE = 1


def get_nested(d, name):
  if len(name) != 0:
    tokens = name.split(".")
    for t in tokens:
      nd = d.get(t)
      if nd is None:
        path = str(".".join(tokens[:tokens.index(t)]))
        token = ".".join((path, str(t))) if len(path) != 0 else str(t)
        keys = [".".join((path, str(k))) if len(path) != 0 else str(k) for k in d.keys()]
        raise KeyError2(token, keys)
      d = nd
    if d is not None:
      return d
  #Fallback
  return None


def get_nested_d(d, name, dfault = None):
  if len(name) != 0:
    tokens = name.split(".")
    for t in tokens:
      nd = d.get(t)
      if nd is None:
        return dfault
      d = nd
    if d is not None:
      return d
  #Fallback
  return dfault


def get_nested_from_sections_d(d, sectNames, name, dfault = None):
  sects = (get_nested_d(d, sectName, {}) for sectName in sectNames)
  r = None
  for s in sects:
    r = get_nested_d(s, name, None)
    if r is not None:
      break
  return dfault if r is None else r


def get_nested_from_stack_d(stack, name, dfault = None):
  r = None
  for s in stack:
    r = get_nested_d(s, name, None)
    if r is not None:
      break
  return dfault if r is None else r


def get_arg2(name, state):
  args = state.get("args")
  if args is not None:
    r = get_nested_from_stack_d(args, name, None)
    if r is None:
      raise RuntimeError("No such arg: {}".format(str2(name)))
    else:
      return r
  else:
    raise RuntimeError("No args were specified, so cannot get arg: {}".format(str2(name)))


def get_argobj(value, state):
  #logger.debug("get_argobj(): value: {}".format(str2(value)))
  if type(value) in (dict, collections.OrderedDict):
    objName = get_nested_d(value, "obj", None)
    if objName is not None:
      return get_object(objName, state)
    argName = get_nested_d(value, "arg", None)
    if argName is not None:
      return get_arg2(argName, state)
  elif type(value) in (str, unicode):
    pa, po = "arg:", "obj:"
    lpa, lpo = len(pa), len(po)
    if value[:lpo] == po:
      objName = value[lpo:]
      return get_object(objName, state)
    elif value[:lpa] == pa:
      argName = value[lpa:]
      return get_arg2(argName, state)
  #Fallback, not in else block!
  return None


def get_arg(value, state):
  r = get_argobj(value, state)
  return value if r is None else r


def resolve_args(args, state):
  r = collections.OrderedDict()
  for n,a in args.items():
    r[n] = get_arg(a, state)
  return r


def push_args(args, state):
  state.setdefault("args", [])
  state["args"].append(resolve_args(args, state))


def pop_args(state):
  assert "args" in state
  state["args"].pop()


def get_object(name, state):
  objects = state["objects"]
  obj = get_nested_from_stack_d(objects, name, None)
  if obj is None:
    allObjects = [str2(objs.keys()) for objs in objects]
    raise RuntimeError("Object {} was not created (available objects are: {}).".format(str2(name), allObjects))
  return obj


def make_objects(objectsCfg, state):
  assert "objects" in state
  objects = collections.OrderedDict()
  state["objects"].append(objects)
  parser = state["parser"]
  for k,v in objectsCfg.items():
    for n in ("curve", "op"):
      if n in v:
        objects[k] = parser(n, v, state)
        #break is needed to avoid executing the "else" block
        break
    else:
      objects[k] = parser("sink", v, state)


def calc_hash(s):
  return None if s is None else zlib.adler32(s)

g_hash2source = {}

def register_source(source):
  """Input event source __init__() should call this with the name of source."""
  h = calc_hash(source)
  g_hash2source[h] = source


class Derivatives:
  def update(self, f, x):
    df, dx = f - self.f_, x - self.x_
    self.f_, self.x_ = f, x
    if dx == 0.0 and df != 0.0:
      raise RuntimeError("Argument delta is 0")
    for i in range(len(self.ds_)):
      d = df / dx
      delta = d - self.ds_[i]
      self.ds_[i] = d
      df = delta

  def get(self, i):
    return self.ds_[i-1]

  def order(self):
    return len(self.ds_)

  def reset(self, f=0.0, x=0.0):
    self.f_, self.x_ = f, x
    for i in range(len(self.ds_)):
      self.ds_[i] = 0.0

  def __init__(self, order):
    self.f_, self.x_ = 0.0, 0.0
    self.ds_ = [0.0 for i in range(order)]


class LogLevels:
  l2n = ((logging.CRITICAL, "CRITICAL"), (logging.ERROR, "ERROR"), (logging.WARNING, "WARNING"), (logging.INFO, "INFO"), (logging.DEBUG, "DEBUG"), (logging.NOTSET, "NOTSET"))
  levelToName = { l:n for l,n in l2n }
  nameToLevel = { n:l for l,n in l2n }

def loglevel2name(l):
  return LogLevels.levelToName.get(l, "NOTSET")

def name2loglevel(n):
  return LogLevels.nameToLevel.get(n.upper(), logging.NOTSET)


codesDict = { 'EV_BCT':-1, 'EV_CUSTOM':-2, 'BCT_INIT':0, 'ABS_BRAKE':10, 'ABS_CNT':64, 'ABS_DISTANCE':25, 'ABS_GAS':9, 'ABS_HAT0X':16, 'ABS_HAT0Y':17, 'ABS_HAT1X':18, 'ABS_HAT1Y':19, 'ABS_HAT2X':20, 'ABS_HAT2Y':21, 'ABS_HAT3X':22, 'ABS_HAT3Y':23, 'ABS_MAX':63, 'ABS_MISC':40, 'ABS_MT_BLOB_ID':56, 'ABS_MT_DISTANCE':59, 'ABS_MT_ORIENTATION':52, 'ABS_MT_POSITION_X':53, 'ABS_MT_POSITION_Y':54, 'ABS_MT_PRESSURE':58, 'ABS_MT_SLOT':47, 'ABS_MT_TOOL_TYPE':55, 'ABS_MT_TOOL_X':60, 'ABS_MT_TOOL_Y':61, 'ABS_MT_TOUCH_MAJOR':48, 'ABS_MT_TOUCH_MINOR':49, 'ABS_MT_TRACKING_ID':57, 'ABS_MT_WIDTH_MAJOR':50, 'ABS_MT_WIDTH_MINOR':51, 'ABS_PRESSURE':24, 'ABS_RESERVED':46, 'ABS_RUDDER':7, 'ABS_RX':3, 'ABS_RY':4, 'ABS_RZ':5, 'ABS_THROTTLE':6, 'ABS_TILT_X':26, 'ABS_TILT_Y':27, 'ABS_TOOL_WIDTH':28, 'ABS_VOLUME':32, 'ABS_WHEEL':8, 'ABS_X':0, 'ABS_Y':1, 'ABS_Z':2, 'BTN_0':256, 'BTN_1':257, 'BTN_2':258, 'BTN_3':259, 'BTN_4':260, 'BTN_5':261, 'BTN_6':262, 'BTN_7':263, 'BTN_8':264, 'BTN_9':265, 'BTN_A':304, 'BTN_B':305, 'BTN_BACK':278, 'BTN_BASE':294, 'BTN_BASE2':295, 'BTN_BASE3':296, 'BTN_BASE4':297, 'BTN_BASE5':298, 'BTN_BASE6':299, 'BTN_C':306, 'BTN_DEAD':303, 'BTN_DIGI':320, 'BTN_DPAD_DOWN':545, 'BTN_DPAD_LEFT':546, 'BTN_DPAD_RIGHT':547, 'BTN_DPAD_UP':544, 'BTN_EAST':305, 'BTN_EXTRA':276, 'BTN_FORWARD':277, 'BTN_GAMEPAD':304, 'BTN_GEAR_DOWN':336, 'BTN_GEAR_UP':337, 'BTN_JOYSTICK':288, 'BTN_LEFT':272, 'BTN_MIDDLE':274, 'BTN_MISC':256, 'BTN_MODE':316, 'BTN_MOUSE':272, 'BTN_NORTH':307, 'BTN_PINKIE':293, 'BTN_RIGHT':273, 'BTN_SELECT':314, 'BTN_SIDE':275, 'BTN_SOUTH':304, 'BTN_START':315, 'BTN_STYLUS':331, 'BTN_STYLUS2':332, 'BTN_STYLUS3':329, 'BTN_TASK':279, 'BTN_THUMB':289, 'BTN_THUMB2':290, 'BTN_THUMBL':317, 'BTN_THUMBR':318, 'BTN_TL':310, 'BTN_TL2':312, 'BTN_TOOL_AIRBRUSH':324, 'BTN_TOOL_BRUSH':322, 'BTN_TOOL_DOUBLETAP':333, 'BTN_TOOL_FINGER':325, 'BTN_TOOL_LENS':327, 'BTN_TOOL_MOUSE':326, 'BTN_TOOL_PEN':320, 'BTN_TOOL_PENCIL':323, 'BTN_TOOL_QUADTAP':335, 'BTN_TOOL_QUINTTAP':328, 'BTN_TOOL_RUBBER':321, 'BTN_TOOL_TRIPLETAP':334, 'BTN_TOP':291, 'BTN_TOP2':292, 'BTN_TOUCH':330, 'BTN_TR':311, 'BTN_TR2':313, 'BTN_TRIGGER':288, 'BTN_TRIGGER_HAPPY':704, 'BTN_TRIGGER_HAPPY1':704, 'BTN_TRIGGER_HAPPY10':713, 'BTN_TRIGGER_HAPPY11':714, 'BTN_TRIGGER_HAPPY12':715, 'BTN_TRIGGER_HAPPY13':716, 'BTN_TRIGGER_HAPPY14':717, 'BTN_TRIGGER_HAPPY15':718, 'BTN_TRIGGER_HAPPY16':719, 'BTN_TRIGGER_HAPPY17':720, 'BTN_TRIGGER_HAPPY18':721, 'BTN_TRIGGER_HAPPY19':722, 'BTN_TRIGGER_HAPPY2':705, 'BTN_TRIGGER_HAPPY20':723, 'BTN_TRIGGER_HAPPY21':724, 'BTN_TRIGGER_HAPPY22':725, 'BTN_TRIGGER_HAPPY23':726, 'BTN_TRIGGER_HAPPY24':727, 'BTN_TRIGGER_HAPPY25':728, 'BTN_TRIGGER_HAPPY26':729, 'BTN_TRIGGER_HAPPY27':730, 'BTN_TRIGGER_HAPPY28':731, 'BTN_TRIGGER_HAPPY29':732, 'BTN_TRIGGER_HAPPY3':706, 'BTN_TRIGGER_HAPPY30':733, 'BTN_TRIGGER_HAPPY31':734, 'BTN_TRIGGER_HAPPY32':735, 'BTN_TRIGGER_HAPPY33':736, 'BTN_TRIGGER_HAPPY34':737, 'BTN_TRIGGER_HAPPY35':738, 'BTN_TRIGGER_HAPPY36':739, 'BTN_TRIGGER_HAPPY37':740, 'BTN_TRIGGER_HAPPY38':741, 'BTN_TRIGGER_HAPPY39':742, 'BTN_TRIGGER_HAPPY4':707, 'BTN_TRIGGER_HAPPY40':743, 'BTN_TRIGGER_HAPPY5':708, 'BTN_TRIGGER_HAPPY6':709, 'BTN_TRIGGER_HAPPY7':710, 'BTN_TRIGGER_HAPPY8':711, 'BTN_TRIGGER_HAPPY9':712, 'BTN_WEST':308, 'BTN_WHEEL':336, 'BTN_X':307, 'BTN_Y':308, 'BTN_Z':309, 'EV_ABS':3, 'EV_CNT':32, 'EV_FF':21, 'EV_FF_STATUS':23, 'EV_KEY':1, 'EV_LED':17, 'EV_MAX':31, 'EV_MSC':4, 'EV_PWR':22, 'EV_REL':2, 'EV_REP':20, 'EV_SND':18, 'EV_SW':5, 'EV_SYN':0, 'EV_UINPUT':257, 'EV_VERSION':65537, 'KEY_0':11, 'KEY_1':2, 'KEY_102ND':86, 'KEY_10CHANNELSDOWN':441, 'KEY_10CHANNELSUP':440, 'KEY_2':3, 'KEY_3':4, 'KEY_3D_MODE':623, 'KEY_4':5, 'KEY_5':6, 'KEY_6':7, 'KEY_7':8, 'KEY_8':9, 'KEY_9':10, 'KEY_A':30, 'KEY_AB':406, 'KEY_ADDRESSBOOK':429, 'KEY_AGAIN':129, 'KEY_ALS_TOGGLE':560, 'KEY_ALTERASE':222, 'KEY_ANGLE':371, 'KEY_APOSTROPHE':40, 'KEY_APPSELECT':580, 'KEY_ARCHIVE':361, 'KEY_ASSISTANT':583, 'KEY_ATTENDANT_OFF':540, 'KEY_ATTENDANT_ON':539, 'KEY_ATTENDANT_TOGGLE':541, 'KEY_AUDIO':392, 'KEY_AUDIO_DESC':622, 'KEY_AUX':390, 'KEY_B':48, 'KEY_BACK':158, 'KEY_BACKSLASH':43, 'KEY_BACKSPACE':14, 'KEY_BASSBOOST':209, 'KEY_BATTERY':236, 'KEY_BLUE':401, 'KEY_BLUETOOTH':237, 'KEY_BOOKMARKS':156, 'KEY_BREAK':411, 'KEY_BRIGHTNESSDOWN':224, 'KEY_BRIGHTNESSUP':225, 'KEY_BRIGHTNESS_AUTO':244, 'KEY_BRIGHTNESS_CYCLE':243, 'KEY_BRIGHTNESS_MAX':593, 'KEY_BRIGHTNESS_MIN':592, 'KEY_BRIGHTNESS_TOGGLE':431, 'KEY_BRIGHTNESS_ZERO':244, 'KEY_BRL_DOT1':497, 'KEY_BRL_DOT10':506, 'KEY_BRL_DOT2':498, 'KEY_BRL_DOT3':499, 'KEY_BRL_DOT4':500, 'KEY_BRL_DOT5':501, 'KEY_BRL_DOT6':502, 'KEY_BRL_DOT7':503, 'KEY_BRL_DOT8':504, 'KEY_BRL_DOT9':505, 'KEY_BUTTONCONFIG':576, 'KEY_C':46, 'KEY_CALC':140, 'KEY_CALENDAR':397, 'KEY_CAMERA':212, 'KEY_CAMERA_DOWN':536, 'KEY_CAMERA_FOCUS':528, 'KEY_CAMERA_LEFT':537, 'KEY_CAMERA_RIGHT':538, 'KEY_CAMERA_UP':535, 'KEY_CAMERA_ZOOMIN':533, 'KEY_CAMERA_ZOOMOUT':534, 'KEY_CANCEL':223, 'KEY_CAPSLOCK':58, 'KEY_CD':383, 'KEY_CHANNEL':363, 'KEY_CHANNELDOWN':403, 'KEY_CHANNELUP':402, 'KEY_CHAT':216, 'KEY_CLEAR':355, 'KEY_CLOSE':206, 'KEY_CLOSECD':160, 'KEY_CNT':768, 'KEY_COFFEE':152, 'KEY_COMMA':51, 'KEY_COMPOSE':127, 'KEY_COMPUTER':157, 'KEY_CONFIG':171, 'KEY_CONNECT':218, 'KEY_CONTEXT_MENU':438, 'KEY_CONTROLPANEL':579, 'KEY_COPY':133, 'KEY_CUT':137, 'KEY_CYCLEWINDOWS':154, 'KEY_D':32, 'KEY_DASHBOARD':204, 'KEY_DATA':631, 'KEY_DATABASE':426, 'KEY_DELETE':111, 'KEY_DELETEFILE':146, 'KEY_DEL_EOL':448, 'KEY_DEL_EOS':449, 'KEY_DEL_LINE':451, 'KEY_DIGITS':413, 'KEY_DIRECTION':153, 'KEY_DIRECTORY':394, 'KEY_DISPLAYTOGGLE':431, 'KEY_DISPLAY_OFF':245, 'KEY_DOCUMENTS':235, 'KEY_DOLLAR':434, 'KEY_DOT':52, 'KEY_DOWN':108, 'KEY_DVD':389, 'KEY_E':18, 'KEY_EDIT':176, 'KEY_EDITOR':422, 'KEY_EJECTCD':161, 'KEY_EJECTCLOSECD':162, 'KEY_EMAIL':215, 'KEY_END':107, 'KEY_ENTER':28, 'KEY_EPG':365, 'KEY_EQUAL':13, 'KEY_ESC':1, 'KEY_EURO':435, 'KEY_EXIT':174, 'KEY_F':33, 'KEY_F1':59, 'KEY_F10':68, 'KEY_F11':87, 'KEY_F12':88, 'KEY_F13':183, 'KEY_F14':184, 'KEY_F15':185, 'KEY_F16':186, 'KEY_F17':187, 'KEY_F18':188, 'KEY_F19':189, 'KEY_F2':60, 'KEY_F20':190, 'KEY_F21':191, 'KEY_F22':192, 'KEY_F23':193, 'KEY_F24':194, 'KEY_F3':61, 'KEY_F4':62, 'KEY_F5':63, 'KEY_F6':64, 'KEY_F7':65, 'KEY_F8':66, 'KEY_F9':67, 'KEY_FASTFORWARD':208, 'KEY_FASTREVERSE':629, 'KEY_FAVORITES':364, 'KEY_FILE':144, 'KEY_FINANCE':219, 'KEY_FIND':136, 'KEY_FIRST':404, 'KEY_FN':464, 'KEY_FN_1':478, 'KEY_FN_2':479, 'KEY_FN_B':484, 'KEY_FN_D':480, 'KEY_FN_E':481, 'KEY_FN_ESC':465, 'KEY_FN_F':482, 'KEY_FN_F1':466, 'KEY_FN_F10':475, 'KEY_FN_F11':476, 'KEY_FN_F12':477, 'KEY_FN_F2':467, 'KEY_FN_F3':468, 'KEY_FN_F4':469, 'KEY_FN_F5':470, 'KEY_FN_F6':471, 'KEY_FN_F7':472, 'KEY_FN_F8':473, 'KEY_FN_F9':474, 'KEY_FN_S':483, 'KEY_FORWARD':159, 'KEY_FORWARDMAIL':233, 'KEY_FRAMEBACK':436, 'KEY_FRAMEFORWARD':437, 'KEY_FRONT':132, 'KEY_G':34, 'KEY_GAMES':417, 'KEY_GOTO':354, 'KEY_GRAPHICSEDITOR':424, 'KEY_GRAVE':41, 'KEY_GREEN':399, 'KEY_H':35, 'KEY_HANGEUL':122, 'KEY_HANGUEL':122, 'KEY_HANJA':123, 'KEY_HELP':138, 'KEY_HENKAN':92, 'KEY_HIRAGANA':91, 'KEY_HOME':102, 'KEY_HOMEPAGE':172, 'KEY_HP':211, 'KEY_I':23, 'KEY_IMAGES':442, 'KEY_INFO':358, 'KEY_INSERT':110, 'KEY_INS_LINE':450, 'KEY_ISO':170, 'KEY_J':36, 'KEY_JOURNAL':578, 'KEY_K':37, 'KEY_KATAKANA':90, 'KEY_KATAKANAHIRAGANA':93, 'KEY_KBDILLUMDOWN':229, 'KEY_KBDILLUMTOGGLE':228, 'KEY_KBDILLUMUP':230, 'KEY_KBDINPUTASSIST_ACCEPT':612, 'KEY_KBDINPUTASSIST_CANCEL':613, 'KEY_KBDINPUTASSIST_NEXT':609, 'KEY_KBDINPUTASSIST_NEXTGROUP':611, 'KEY_KBDINPUTASSIST_PREV':608, 'KEY_KBDINPUTASSIST_PREVGROUP':610, 'KEY_KEYBOARD':374, 'KEY_KP0':82, 'KEY_KP1':79, 'KEY_KP2':80, 'KEY_KP3':81, 'KEY_KP4':75, 'KEY_KP5':76, 'KEY_KP6':77, 'KEY_KP7':71, 'KEY_KP8':72, 'KEY_KP9':73, 'KEY_KPASTERISK':55, 'KEY_KPCOMMA':121, 'KEY_KPDOT':83, 'KEY_KPENTER':96, 'KEY_KPEQUAL':117, 'KEY_KPJPCOMMA':95, 'KEY_KPLEFTPAREN':179, 'KEY_KPMINUS':74, 'KEY_KPPLUS':78, 'KEY_KPPLUSMINUS':118, 'KEY_KPRIGHTPAREN':180, 'KEY_KPSLASH':98, 'KEY_L':38, 'KEY_LANGUAGE':368, 'KEY_LAST':405, 'KEY_LEFT':105, 'KEY_LEFTALT':56, 'KEY_LEFTBRACE':26, 'KEY_LEFTCTRL':29, 'KEY_LEFTMETA':125, 'KEY_LEFTSHIFT':42, 'KEY_LEFT_DOWN':617, 'KEY_LEFT_UP':616, 'KEY_LIGHTS_TOGGLE':542, 'KEY_LINEFEED':101, 'KEY_LIST':395, 'KEY_LOGOFF':433, 'KEY_M':50, 'KEY_MACRO':112, 'KEY_MAIL':155, 'KEY_MAX':767, 'KEY_MEDIA':226, 'KEY_MEDIA_REPEAT':439, 'KEY_MEDIA_TOP_MENU':619, 'KEY_MEMO':396, 'KEY_MENU':139, 'KEY_MESSENGER':430, 'KEY_MHP':367, 'KEY_MICMUTE':248, 'KEY_MINUS':12, 'KEY_MIN_INTERESTING':113, 'KEY_MODE':373, 'KEY_MOVE':175, 'KEY_MP3':391, 'KEY_MSDOS':151, 'KEY_MUHENKAN':94, 'KEY_MUTE':113, 'KEY_N':49, 'KEY_NEW':181, 'KEY_NEWS':427, 'KEY_NEXT':407, 'KEY_NEXTSONG':163, 'KEY_NEXT_FAVORITE':624, 'KEY_NUMERIC_0':512, 'KEY_NUMERIC_1':513, 'KEY_NUMERIC_11':620, 'KEY_NUMERIC_12':621, 'KEY_NUMERIC_2':514, 'KEY_NUMERIC_3':515, 'KEY_NUMERIC_4':516, 'KEY_NUMERIC_5':517, 'KEY_NUMERIC_6':518, 'KEY_NUMERIC_7':519, 'KEY_NUMERIC_8':520, 'KEY_NUMERIC_9':521, 'KEY_NUMERIC_A':524, 'KEY_NUMERIC_B':525, 'KEY_NUMERIC_C':526, 'KEY_NUMERIC_D':527, 'KEY_NUMERIC_POUND':523, 'KEY_NUMERIC_STAR':522, 'KEY_NUMLOCK':69, 'KEY_O':24, 'KEY_OK':352, 'KEY_ONSCREEN_KEYBOARD':632, 'KEY_OPEN':134, 'KEY_OPTION':357, 'KEY_P':25, 'KEY_PAGEDOWN':109, 'KEY_PAGEUP':104, 'KEY_PASTE':135, 'KEY_PAUSE':119, 'KEY_PAUSECD':201, 'KEY_PAUSE_RECORD':626, 'KEY_PC':376, 'KEY_PHONE':169, 'KEY_PLAY':207, 'KEY_PLAYCD':200, 'KEY_PLAYER':387, 'KEY_PLAYPAUSE':164, 'KEY_POWER':116, 'KEY_POWER2':356, 'KEY_PRESENTATION':425, 'KEY_PREVIOUS':412, 'KEY_PREVIOUSSONG':165, 'KEY_PRINT':210, 'KEY_PROG1':148, 'KEY_PROG2':149, 'KEY_PROG3':202, 'KEY_PROG4':203, 'KEY_PROGRAM':362, 'KEY_PROPS':130, 'KEY_PVR':366, 'KEY_Q':16, 'KEY_QUESTION':214, 'KEY_R':19, 'KEY_RADIO':385, 'KEY_RECORD':167, 'KEY_RED':398, 'KEY_REDO':182, 'KEY_REFRESH':173, 'KEY_REPLY':232, 'KEY_RESERVED':0, 'KEY_RESTART':408, 'KEY_REWIND':168, 'KEY_RFKILL':247, 'KEY_RIGHT':106, 'KEY_RIGHTALT':100, 'KEY_RIGHTBRACE':27, 'KEY_RIGHTCTRL':97, 'KEY_RIGHTMETA':126, 'KEY_RIGHTSHIFT':54, 'KEY_RIGHT_DOWN':615, 'KEY_RIGHT_UP':614, 'KEY_RO':89, 'KEY_ROOT_MENU':618, 'KEY_ROTATE_DISPLAY':153, 'KEY_S':31, 'KEY_SAT':381, 'KEY_SAT2':382, 'KEY_SAVE':234, 'KEY_SCALE':120, 'KEY_SCREEN':375, 'KEY_SCREENLOCK':152, 'KEY_SCREENSAVER':581, 'KEY_SCROLLDOWN':178, 'KEY_SCROLLLOCK':70, 'KEY_SCROLLUP':177, 'KEY_SEARCH':217, 'KEY_SELECT':353, 'KEY_SEMICOLON':39, 'KEY_SEND':231, 'KEY_SENDFILE':145, 'KEY_SETUP':141, 'KEY_SHOP':221, 'KEY_SHUFFLE':410, 'KEY_SLASH':53, 'KEY_SLEEP':142, 'KEY_SLOW':409, 'KEY_SLOWREVERSE':630, 'KEY_SOUND':213, 'KEY_SPACE':57, 'KEY_SPELLCHECK':432, 'KEY_SPORT':220, 'KEY_SPREADSHEET':423, 'KEY_STOP':128, 'KEY_STOPCD':166, 'KEY_STOP_RECORD':625, 'KEY_SUBTITLE':370, 'KEY_SUSPEND':205, 'KEY_SWITCHVIDEOMODE':227, 'KEY_SYSRQ':99, 'KEY_T':20, 'KEY_TAB':15, 'KEY_TAPE':384, 'KEY_TASKMANAGER':577, 'KEY_TEEN':414, 'KEY_TEXT':388, 'KEY_TIME':359, 'KEY_TITLE':369, 'KEY_TOUCHPAD_OFF':532, 'KEY_TOUCHPAD_ON':531, 'KEY_TOUCHPAD_TOGGLE':530, 'KEY_TUNER':386, 'KEY_TV':377, 'KEY_TV2':378, 'KEY_TWEN':415, 'KEY_U':22, 'KEY_UNDO':131, 'KEY_UNKNOWN':240, 'KEY_UNMUTE':628, 'KEY_UP':103, 'KEY_UWB':239, 'KEY_V':47, 'KEY_VCR':379, 'KEY_VCR2':380, 'KEY_VENDOR':360, 'KEY_VIDEO':393, 'KEY_VIDEOPHONE':416, 'KEY_VIDEO_NEXT':241, 'KEY_VIDEO_PREV':242, 'KEY_VOD':627, 'KEY_VOICECOMMAND':582, 'KEY_VOICEMAIL':428, 'KEY_VOLUMEDOWN':114, 'KEY_VOLUMEUP':115, 'KEY_W':17, 'KEY_WAKEUP':143, 'KEY_WIMAX':246, 'KEY_WLAN':238, 'KEY_WORDPROCESSOR':421, 'KEY_WPS_BUTTON':529, 'KEY_WWAN':246, 'KEY_WWW':150, 'KEY_X':45, 'KEY_XFER':147, 'KEY_Y':21, 'KEY_YELLOW':400, 'KEY_YEN':124, 'KEY_Z':44, 'KEY_ZENKAKUHANKAKU':85, 'KEY_ZOOM':372, 'KEY_ZOOMIN':418, 'KEY_ZOOMOUT':419, 'KEY_ZOOMRESET':420, 'REL_CNT':16, 'REL_DIAL':7, 'REL_HWHEEL':6, 'REL_MAX':15, 'REL_MISC':9, 'REL_RX':3, 'REL_RY':4, 'REL_RZ':5, 'REL_WHEEL':8, 'REL_X':0, 'REL_Y':1, 'REL_Z':2, }
codes = type("codes", (object,), codesDict)

def name2code(name):
  r = codesDict.get(name)
  if r is None:
    raise RuntimeError("Bad name: {}".format(str2(name)))
  return r


def name2type(name):
  p2t = {
    "REL" : codes.EV_REL,
    "ABS" : codes.EV_ABS,
    "BTN" : codes.EV_KEY,
    "KEY" : codes.EV_KEY,
    "BCT" : codes.EV_BCT,
  }
  prefix = name[:3]
  return p2t.get(prefix)


def type2names(type):
  t2ps = {
    codes.EV_SYN : ("SYN",),
    codes.EV_REL : ("REL",),
    codes.EV_ABS : ("ABS",),
    codes.EV_KEY : ("BTN", "KEY",),
    codes.EV_BCT : ("BCT",)
  }
  return t2ps.get(type, ())


typeCode2Name = {
  t : {
    c : n for n,c in codesDict.items() if name2type(n) == t
  }
  for t in set((name2type(n) for n in codesDict.keys())) if t is not None
}


def typecode2name(type, code):
  return typeCode2Name.get(type, {}).get(code, "")


SplitName = collections.namedtuple("SplitName", "state source shash type code")

def split_full_name2(s, sep="."):
  state = True
  if s[0] == "+":
    s = s[1:]
  elif s[0] == "-":
    r.state = False
    s = s[1:]
  i = s.find(sep)
  source = None if i == -1 else s[:i]
  shash = None if source is None else calc_hash(source)
  name = s if i == -1 else s[i+1:]
  code = name2code(name)
  type = name2type(name)
  return SplitName(state=state, source=source, shash=shash, type=type, code=code)


SourceName = collections.namedtuple("SourceName", "source name")
SourceCode = collections.namedtuple("SourceCode", "source code")
SourceCodeState = collections.namedtuple("SourceCodeState", "source code state")
SourceTypeCode = collections.namedtuple("SourceTypeCode", "source type code")
SourceTypeCodeState = collections.namedtuple("SourceTypeCodeState", "source type code state")

def fn2sn(s, sep="."):
  """
  Splits full name into source and name.
  'mouse.REL_X' -> ('mouse', 'REL_X')
  'REL_X' -> (None, 'REL_X')
  """
  i = s.find(sep)
  return SourceName(None, s) if i == -1 else SourceName(s[:i], s[i+1:])


def fn2sc(s, sep="."):
  """
  Splits full name into source and code.
  'mouse.REL_X' -> ('mouse', codes.REL_X)
  'REL_X' -> (None, codes.REL_X)
  """
  r = fn2sn(s, sep)
  return SourceCode(source=r.source, code=name2code(r.name))


def fn2hc(s, sep="."):
  """
  Splits full name into source hash and code.
  'mouse.REL_X' -> (calc_hash('mouse'), codes.REL_X)
  'REL_X' -> (None, codes.REL_X)
  """
  r = fn2sc(s, sep)
  h = calc_hash(r.source)
  return SourceCode(source=h, code=r.code)


def fn2stc(s, sep="."):
  """
  Splits full name into source, type and code.
  'mouse.REL_X' -> ('mouse', codes.EV_REL, codes.REL_X)
  'REL_X' -> (None, codes.EV_REL, codes.REL_X)
  """
  r = fn2sn(s, sep)
  return SourceTypeCode(source=r.source, type=name2type(r.name), code=name2code(r.name))


def fn2htc(s, sep="."):
  """
  Splits full name into source hash, type and code.
  'mouse.REL_X' -> (calc_hash('mouse'), codes.EV_REL, codes.REL_X)
  'REL_X' -> (None, codes.EV_REL, codes.REL_X)
  """
  r = fn2stc(s, sep)
  h = calc_hash(r.source)
  return SourceTypeCode(source=h, type=r.type, code=r.code)


def stc2fn(source, type, code, sep="."):
  """
  Joins source, type and code into full name.
  'mouse', codes.EV_REL, codes.REL_X -> 'mouse.REL_X'
  None, codes.EV_REL, codes.REL_X -> 'REL_X'
  """
  tcn = typecode2name(type, code)
  if source is not None:
    tcn = sep.join((source, tcn))
  return tcn


def htc2fn(sourceHash, type, code, sep="."):
  """
  Joins source hash, type and code into full name.
  calc_hash('mouse'), codes.EV_REL, codes.REL_X -> 'mouse.REL_X'
  None, codes.EV_REL, codes.REL_X -> 'REL_X'
  """
  s = None if sourceHash is None else str(g_hash2source.get(sourceHash))
  return stc2fn(s, type, code, sep)


def fn2sne(s, sep="."):
  """
  Splits full name into source, name and state.
  'mouse.REL_X' -> ('mouse', 'REL_X', True)
  'REL_X' -> (None, 'REL_X', True)
  '+mouse.REL_X' -> ('mouse', 'REL_X', True)
  '+REL_X' -> (None, 'REL_X', True)
  '-mouse.REL_X' -> ('mouse', 'REL_X', False)
  '-REL_X' -> (None, 'REL_X', False)
  """
  state = True
  if s[0] == "+":
    s = s[1:]
  elif s[0] == "-":
    state = False
    s = s[1:]
  i = s.find(sep)
  return SourceNameState(source=None, name=s, state=state) if i == -1 else SourceNameState(source=s[:i], name=s[i+1:], state=state)


def fn2sce(s, sep="."):
  """
  Splits full name into source, code and state.
  'mouse.REL_X' -> ('mouse', codes.REL_X, True)
  'REL_X' -> (None, codes.REL_X, True)
  '+mouse.REL_X' -> ('mouse', codes.REL_X, True)
  '+REL_X' -> (None, codes.REL_X, True)
  '-mouse.REL_X' -> ('mouse', codes.REL_X, False)
  '-REL_X' -> (None, codes.REL_X, False)
  """
  r = fn2sne(s, sep)
  return SourceCodeState(source=r.source, code=name2code(r.name), state=r.state)


def fn2hce(s, sep="."):
  """
  Splits full name into source hash, code and state.
  'mouse.REL_X' -> ('mouse', codes.REL_X, True)
  'REL_X' -> (None, codes.REL_X, True)
  '+mouse.REL_X' -> ('mouse', codes.REL_X, True)
  '+REL_X' -> (None, codes.REL_X, True)
  '-mouse.REL_X' -> ('mouse', codes.REL_X, False)
  '-REL_X' -> (None, codes.REL_X, False)
  """
  r = fn2sce(s, sep)
  h = calc_hash(r.source)
  return SourceCodeState(source=h, code=r.code, state=r.state)


def fn2stce(s, sep="."):
  """
  Splits full name into source, type, code and state.
  'mouse.REL_X' -> ('mouse', codes.EV_REL, codes.REL_X, True)
  'REL_X' -> (None, codes.EV_REL, codes.REL_X, True)
  '+mouse.REL_X' -> ('mouse', codes.EV_REL, codes.REL_X, True)
  '+REL_X' -> (None, codes.EV_REL, codes.REL_X, True)
  '-mouse.REL_X' -> ('mouse', codes.EV_REL, codes.REL_X, False)
  '-REL_X' -> (None, codes.EV_REL, codes.REL_X, False)
  """
  r = fn2sne(s, sep)
  return SourceTypeCodeState(source=r.source, type=name2type(r.name), code=name2code(r.name), state=r.state)


def fn2htce(s, sep="."):
  """
  Splits full name into source hash, type, code and state.
  'mouse.REL_X' -> (calc_hash('mouse'), codes.EV_REL, codes.REL_X, True)
  'REL_X' -> (None, codes.EV_REL, codes.REL_X, True)
  '+mouse.REL_X' -> (calc_hash('mouse'), codes.EV_REL, codes.REL_X, True)
  '+REL_X' -> (None, codes.EV_REL, codes.REL_X, True)
  '-mouse.REL_X' -> (calc_hash('mouse'), codes.EV_REL, codes.REL_X, False)
  '-REL_X' -> (None, codes.EV_REL, codes.REL_X, False)
  """
  r = fn2stce(s, sep)
  return SourceTypeCodeState(source=calc_hash(r.source), type=r.type, code=r.code, state=r.state)


class ModifierDesc:
  def __init__(self, source, code, state):
      self.source, self.code, self.state = source, code, state

def parse_modifier_desc(s, sep="."):
  t = split_full_name2(s, sep)
  return ModifierDesc(source=t.shash, code=t.code, state=t.state)


class ReloadException(Exception):
  pass


class NullJoystick:
  """Placeholder joystick class."""
  def __init__(self, values=None, limits=None):
    self.v_ = {}
    if values is not None:
      for a,v in values.items():
        self.v_[a] = v
    self.limits_ = {}
    if limits is not None:
      for a,l in limits.items():
        self.limits_[a] = l
    logger.debug("{} created".format(self))

  def __del__(self):
    logger.debug("{} destroyed".format(self))

  def move_axis(self, axis, v, relative):
    if relative:
      self.move_axis_by(axis, v)
    else:
      self.move_axis_to(axis, v)

  def move_axis_by(self, axis, v):
    self.move_axis_to(axis, self.get_axis_value(axis)+v)

  def move_axis_to(self, axis, v):
    self.v_[axis] = clamp(v, *self.get_limits(axis))

  def get_axis_value(self, axis):
    return self.v_.get(axis, 0.0)

  def get_limits(self, axis):
    return self.limits_.get(axis, (-float("inf"), float("inf")))

  def get_supported_axes(self):
    return self.v_.keys()

  def set_button_state(self, button, state):
    pass


class CompositeJoystick:
  def move_axis(self, axis, v, relative):
    value = self.get_axis_value(axis) + v if relative else v
    limits = self.get_limits(axis)
    value = clamp(value, *limits)
    for c in self.children_:
      if axis in c.get_supported_axes():
        c.move_axis(axis, value, relative=False)

  def get_axis_value(self, axis):
    for c in self.children_:
      if axis in c.get_supported_axes():
        return c.get_axis_value(axis)
    else:
      return 0.0

  def get_limits(self, axis):
    l = [-float("inf"), float("inf")]
    for c in self.children_:
      if axis in c.get_supported_axes():
        cl = list(c.get_limits(axis))
        if cl[0] > cl[1] : cl[0], cl[1] = cl[1], cl[0]
        l[0], l[1] = max(l[0], cl[0]), min(l[1], cl[1])
        if l[0] >= l[1]:
          return [0.0, 0.0]
    return l

  def get_supported_axes(self):
    axes = set()
    for c in self.children_:
      axes.update(set(c.get_supported_axes()))
    return list(axes)

  def __init__(self, children):
    self.children_ = children


class Event(object):
  def __str__(self):
    fmt = "type: {} ({}), code: {} (0x{:X}, {}), value: {}, timestamp: {}"
    return fmt.format(self.type, "/".join(type2names(self.type)), self.code, self.code, typecode2name(self.type, self.code), self.value, self.timestamp)

  __slots__ = ("type", "code", "value", "timestamp", )
  def __init__(self, type, code, value, timestamp=None):
    if timestamp is None:
      timestamp = time.time()
    self.type, self.code, self.value, self.timestamp = type, code, value, timestamp


class InputEvent(Event):
  def __str__(self):
    #Had to reference members of parent class directly, because FreePie does not handle super() well
    fmt = ", source: {} ({}), modifiers: {}"
    modifiers = [((s, m), htc2fn(s, codes.EV_KEY, m)) for s,m in self.modifiers]
    return Event.__str__(self) + fmt.format(self.source, g_hash2source.get(self.source, ""), modifiers)
    #these do not work in FreePie
    #return super(InputEvent, self).__str__() + ", source: {}, modifiers: {}".format(self.source, self.modifiers)
    #return super(InputEvent, Event).__str__() + ", source: {}, modifiers: {}".format(self.source, self.modifiers)
    #return super().__str__() + ", source: {}, modifiers: {}".format(self.source, self.modifiers)
    #return Event.__str__(self) + ", source: {}, modifiers: {}".format(self.source, self.modifiers)
    #return "source: {}, modifiers: {}".format(self.source, self.modifiers)

  __slots__ = ("source", "modifiers",)
  def __init__(self, t, code, value, timestamp, source, modifiers=None):
    #Had to reference members of parent class directly, because FreePie does not handle super() well
    #This does not work in FreePie
    #super().__init__(t, code, value, timestamp)
    self.type, self.code, self.value, self.timestamp = t, code, value, timestamp
    self.source = source
    self.modifiers = [] if modifiers is None else modifiers


class ClickEvent(InputEvent):
  def __str__(self):
    return InputEvent.__str__(self) + ", num_clicks: {}".format(self.num_clicks)

  __slots__ = ("num_clicks",)
  def __init__(self, t=None, code=None, timestamp=None, source=None, modifiers=None, num_clicks=0):
    InputEvent.__init__(self, t, code, 3, timestamp, source, modifiers)
    self.num_clicks = num_clicks

  @classmethod
  def from_event(cls, event, numClicks):
    ce = ClickEvent()
    ce.type, ce.code, ce.value, ce.timestamp, ce.source, ce.modifiers = event.type, event.code, 3, event.timestamp, event.source, event.modifiers
    ce.num_clicks = numClicks
    return ce


class EventCompressorDevice:
  """Compresses movement events along each relative axis into one event per such axis.
     Other events are unchanged and passed to the caller immediately.
     Sends compressed events after underlying device is exhausted (returns None from read_one())
     in an unspecified order.
     Assumes there are no  modifiers in relative axis movement events."""
  def read_one(self):
    while True:
      event = self.next_.read_one()
      if event is None:
        if len(self.events_) != 0:
          axisId, event = self.events_.items()[0]
          del self.events_[axisId]
        break
      elif event.type == codes.EV_REL:
        k = (event.source, event.code)
        e = self.events_.get(k)
        if e is None:
          self.events_[k] = event
        else:
          e.value += event.value
          e.timestamp = event.timestamp
      else:
        break
    return event

  def swallow(self, s):
    self.next_.swallow(s)

  def __init__(self, next):
    self.next_ = next
    self.events_ = {}


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
      c(dt, ct)
    dt = time.time() - ct
    sleepTime = max(self.step_ - dt, 0)
    if sleepTime != 0:
      time.sleep(sleepTime)

  def run(self):
    self.t_ = time.time()
    while (True):
      self.run_once()

  def __init__(self, callbacks, step):
    self.callbacks_, self.step_ = callbacks, step
    self.t_ = None


def If(cnd, o):
  def op(event):
    if cnd():
      o(event)
    return True
  return op


def Call(*ops):
  def op(event):
    for o in ops:
      o(event)
    return True
  return op


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


def SetButtonState(output, button, state):
  def op(event):
    output.set_button_state(button, state)
    #logger.debug("Setting {} key {} (0x{:X}) to {}".format(output, typecode2name(codes.EV_KEY, button), button, state))
  return op


class ClickSink:
  def __call__(self, event):
    if self.next_:
      self.next_(event)

    numClicks = 0
    if event.type == codes.EV_KEY:
      numClicks = self.update_keys(event)
      if self.next_ and numClicks != 0:
        clickEvent = ClickEvent.from_event(event, numClicks)
        self.next_(clickEvent)

  #returns number of clicks
  def update_keys(self, event):
    if event.type == codes.EV_KEY:
      #logger.debug("{} {}".format(event.code, event.value))
      self.keys_.setdefault(event.code, [event.value, event.timestamp, 0])
      keyData = self.keys_[event.code]
      prevValue, prevTimestamp, prevNumClicks = keyData
      dt = event.timestamp - prevTimestamp
      if event.value == 0 and prevValue > 0 and dt <= self.clickTime_:
        keyData[2] += 1
      elif event.value > 0 and prevValue == 0 and dt > self.clickTime_:
        keyData[2] = 0
      keyData[0] = event.value
      keyData[1] = event.timestamp
      return keyData[2]
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


class HoldSink:
  class D:
    pass

  def __call__(self, event):
    if event.type == codes.EV_KEY:
      if event.value == 0:
        if event.code in self.keys_:
          del self.keys_[event.code]
      elif event.value == 1:
        d = HoldSink.D()
        d.source, d.timestamp, d.modifiers = event.source, event.timestamp, [m for m in event.modifiers]
        self.keys_[event.code] = d
    if self.next_:
      self.next_(event)

  def update(self, tick, timestamp):
    for k,d in self.keys_.items():
      if d.timestamp is not None and timestamp - d.timestamp >= self.holdTime_:
        if self.next_:
          event = InputEvent(codes.EV_KEY, k, self.value_, timestamp, d.source, d.modifiers)
          self.next_(event)
        self.keys_[k].timestamp = None if self.fireOnce_ else timestamp

  def set_next(self, next):
    self.next_ = next
    return next

  def __init__(self, holdTime, value, fireOnce):
    self.next_, self.keys_, self.holdTime_, self.value_, self.fireOnce_ = None, {}, holdTime, value, fireOnce
    logger.debug("{} created".format(self))

  def __del__(self):
    logger.debug("{} destroyed".format(self))


class ModifierSink:
  APPEND = 0
  OVERWRITE = 1

  def __call__(self, event):
    if event.type == codes.EV_KEY:
      if self.modifiers_ is not None:
        p = (event.source, event.code)
        #logger.debug("{}.__call__(): got: {}".format(self, p))
        for m in self.modifiers_:
          #logger.debug("{}.__call__(): checking against: {}".format(self, m))
          if p == m or (m[0] is None and p[1] == m[1]):
            #logger.debug("{}.__call__(): {} matched {}".format(self, p, m))
            if event.value == 1 and p not in self.m_:
              self.m_.append(p)
            elif event.value == 0 and p in self.m_:
              self.m_.remove(p)
          else:
            #logger.debug("{}.__call__(): {} mismatched {}".format(self, p, m))
            pass

    if self.next_:
      oldModifiers = None
      try:
        if event.type in (codes.EV_KEY, codes.EV_REL, codes.EV_ABS):
          assert type(event.modifiers) is list
          if self.saveModifiers_:
            oldModifiers = [m for m in event.modifiers]
          if self.mode_ == self.APPEND:
            for m in self.m_:
              if m not in event.modifiers:
                event.modifiers.append(m)
          elif self.mode_ == self.OVERWRITE:
            event.modifiers = [m for m in self.m_]
          else:
            raise RuntimeError("Bad mode: {}".format(self.mode_))
        return self.next_(event)
      finally:
        if self.saveModifiers_:
          event.modifiers = oldModifiers
    else:
      return False

  def set_next(self, next):
    self.next_ = next
    return next

  def clear(self):
    self.m_ = []

  def __init__(self, next = None, modifiers = None, saveModifiers = True, mode = 0):
    #logger.debug("{}.__init__(): tracked modifiers: {}".format(self, [(s, typecode2name(codes.EV_KEY, m)) for s,m in modifiers]))
    self.m_, self.next_, self.modifiers_, self.saveModifiers_, self.mode_ = [], next, modifiers, saveModifiers, mode


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
        scale = self.sens_.get(keys[0])
        if scale is None:
          scale = self.sens_.get(keys[1], 1.0)
        event.value *= scale
    return self.next_(event) if self.next_ is not None else False

  def set_next(self, next):
    self.next_ = next
    return next

  def __init__(self, sens, keyOp = lambda event : (SourceCode(source=event.source, code=event.code), SourceCode(source=None, code=event.code))):
    self.next_, self.sens_, self.keyOp_ = None, sens, keyOp


class SensSetSink:
  def __call__(self, event):
    if event.type in (codes.EV_REL, codes.EV_ABS):
      if self.currentSet_ is not None:
        keys = self.keyOp_(event)
        scale = self.currentSet_.get(keys[0])
        if scale is None:
          scale = self.currentSet_.get(keys[1], 1.0)
        event.value *= scale
    return self.next_(event) if self.next_ is not None else False

  def set_next(self, next):
    self.next_ = next
    return next

  def set_set(self, idx):
    idx = clamp(idx, 0, len(self.sensSets_)-1)
    self.currentSet_ = self.sensSets_[idx]
    self.print_set_()

  def set_next_set(self):
    if self.sensSets_ is None or len(self.sensSets_) == 0:
      logger.warning("No sensitivity sets")
      return
    l = len(self.sensSets_)
    idx = self.sensSets_.index(self.currentSet_)
    idx = 0 if idx == -1 else min(idx+1, l-1)
    self.currentSet_ = self.sensSets_[idx]
    self.print_set_()

  def set_prev_set(self):
    if self.sensSets_ is None or len(self.sensSets_) == 0:
      logger.warning("No sensitivity sets")
      return
    l = len(self.sensSets_)
    idx = self.sensSets_.index(self.currentSet_)
    idx = 0 if idx == -1 else max(idx-1, 0)
    self.currentSet_ = self.sensSets_[idx]
    self.print_set_()

  def __init__(self, sensSets, keyOp = lambda event : (SourceTypeCode(event.source, event.type, event.code), SourceTypeCode(None, event.type, event.code)), initial=0, makeName=lambda k : stc2fn(*k)):
    self.next_, self.sensSets_, self.keyOp_, self.makeName_ = None, sensSets, keyOp, makeName
    self.currentSet_ = None if sensSets is None or len(sensSets) == 0 else sensSets[initial]

  def print_set_(self):
    items = self.currentSet_.items()
    items.reverse()
    s = ""
    for i in items:
      s += "{}: {}, ".format(self.makeName_(i[0]), i[1])
    s = s[:-2]
    logger.info("Setting sensitivity set: {}".format(s))


class CalibratingSink:
  def __call__(self, event):
    if self.mode_ == 0:
      return self.process_event_(event)
    elif self.mode_ == 1:
      return self.gather_data_(event)

  def set_next(self, next):
    self.next_ = next
    return next

  def toggle(self):
    if self.mode_ == 0:
      logger.info("Calibration started")
      self.sens_ = {}
      self.mode_ = 1
    elif self.mode_ == 1:
      self.calibrate_()
      self.mode_ = 0
      logger.info("Calibration finished")

  def reset(self):
    self.sens_ = {}
    logger.info("Calibration reset")

  def __init__(self, makeName=lambda k : stc2fn(*k)):
    self.next_, self.sens_, self.mode_ = None, {}, 0
    self.makeName_ = makeName

  def process_event_(self, event):
    if self.next_ is not None:
      if event.type in (codes.EV_REL, codes.EV_ABS):
        sens = self.sens_.get((event.type, event.source, event.code), 1.0)
        event.value *= sens
      return self.next_(event)
    else:
      return False

  def gather_data_(self, event):
    if event.type in (codes.EV_REL, codes.EV_ABS):
      k = (event.source, event.type, event.code)
      d = self.sens_.get(k, None)
      if d is None:
        class Data:
          pass
        d = Data()
        d.curr, d.min, d.max = 0.0, 0.0, 0.0
        self.sens_[k] = d
      if event.type == codes.EV_REL:
        d.curr += event.value
      elif event.type == codes.EV_ABS:
        d.curr = event.value
      if d.curr < d.min: d.min = d.curr
      elif d.curr > d.max: d.max = d.curr
    s = ""
    for k,d in self.sens_.items():
      s += "{}: ({:+.3f}, {:+.3f}, {:+.3f}); ".format(self.makeName_(k), d.min, d.curr, d.max)
    if len(s):
      logger.info(s[:-2])
    return self.next_(event) if self.next_ is not None else False

  def calibrate_(self):
    for k,d in self.sens_.items():
      delta = d.max - d.min
      if delta == 0.0: delta = 2.0
      s = 2.0 / delta
      self.sens_[k] = s
      #logger.debug("{}: min:{}, max:{}, delta:{}".format(stc2fn(k[1], k[0], k[2]), d.min, d.max, delta))
      logger.info("Sensitivity for {} is now {:+.5f}".format(self.makeName_(k), s))


class BindSink:
  class ChildrenInfo:
    __slots__ = ("attrs", "level", "children",)
    def __init__(self, attrs, level, children):
      self.attrs, self.level, self.children = attrs, level, [cc for cc in children]

  def __call__(self, event):
    #logger.debug("{}: processing {})".format(self, event))
    self.update_()

    if len(self.children_) == 0:
      return False

    assert(self.cmp_)
    level, processed = self.children_[0].level, False
    for c in self.children_:
      if c.level > level:
        if processed == True:
          return True
        else:
          level = c.level
      for attrName, attrValue in c.attrs:
        eventValue = getattr(event, attrName, None)
        if eventValue is None:
          #logger.debug("{}: Event [{}] does not have attribute '{}'".format(self, event, attrName))
          break
        if not self.cmp_(attrName, eventValue, attrValue):
          #logger.debug("{}: Mismatch while matching attrs {} with event [{}] at attr '{}' (got {}, needed {})".format(self, c.attrs, event, attrName, eventValue, attrValue))
          break
      else:
        #logger.debug("{}: Event [{}] matched attrs {}".format(self, event, c.attrs))
        if c.children is not None:
          #logger.debug("Processing event {}".format(str(event)))
          for cc in c.children:
            #logger.debug("Sending event {} to {}".format(str(event), cc))
            processed = cc(event) or processed

    return processed

  def add(self, attrs, child, level = 0):
    #logger.debug("{}: Adding child {} to {} for level {}".format(self, child, attrs, level))
    assert(child is not None)
    c = next((x for x in self.children_ if level == x.level and attrs == x.attrs), None)
    if c is not None:
      c.children.append(child)
    else:
      self.children_.append(self.ChildrenInfo(attrs, level, [child]))
    self.dirty_ = True
    return child

  def add_several(self, attrs, childSeq, level = 0):
    for a in attrs:
      c = next((x for x in self.children_ if level == x.level and a == x.attrs), None)
      if c is not None:
        assert(isinstance(c.children, list))
        c.children += childSeq
      else:
        self.children_.append(ChildrenInfo(a, level, childSeq))
    self.dirty_ = True
    return childSeq

  def clear(self):
    del self.children_[:]

  __slots__ = ("children_", "cmp_", "sortEDs_", "dirty_",)
  def __init__(self, cmp = lambda a, b, c : b == c, children = None, sortEDs = True):
    if children is None:
      children = []
    self.children_ = children
    self.cmp_ = cmp
    self.sortEDs_ = sortEDs
    self.dirty_ = True
    logger.debug("{} created".format(self))

  def __del__(self):
    logger.debug("{} destroyed".format(self))

  def update_(self):
    if self.dirty_ == True:
      self.children_.sort(key=lambda c : c.level)
      if self.sortEDs_ == True:
        attrFreq = {}
        for c in self.children_:
          for attrName, attrValue in c.attrs:
            attrFreq.setdefault(attrName, set())
            if type(attrValue) not in (list, dict, collections.OrderedDict):
              attrFreq[attrName].add(attrValue)
        for k,v in attrFreq.items():
          attrFreq[k] = len(v)
        for c in self.children_:
          if type(c.attrs) is not list:
            c.attrs = [a for a in c.attrs]
          c.attrs.sort(key=lambda a : attrFreq[a[0]], reverse=True)
        #logger.debug("{}: level: {}, attrFreq: {}, sorted attrs: {}".format(self, c.level, attrFreq, c.attrs))
      self.dirty_ = False


class PropTest:
  def __call__(self, v):
    return True


class EqPropTest(PropTest):
  def __call__(self, v):
    return self.v_ == v

  def __init__(self, v):
    self.v_ = v


class CmpPropTest(PropTest):
  def __call__(self, v):
    return self.cmp_(v, self.v_)

  def __init__(self, v, compare):
    self.v_, self.cmp_ = v, compare


def cmp_modifiers(eventValue, attrValue):
  r = False
  if attrValue is None:
    r = eventValue is None
  elif eventValue is None:
    r = False
  elif len(attrValue) == 0:
    r = len(eventValue) == 0
  elif len(attrValue) == len(eventValue):
    r = True
    for m in attrValue:
      found = False
      for n in eventValue:
        assert(len(n) == 2)
        found = (True if m.source is None else m.source == n[0]) and (m.code == n[1])
        if found:
          break
      if m.state == False:
         found = not found
      r = r and found
      if not r:
          break
  return r


class ModifiersPropTest(PropTest):
  def __call__(self, v):
    return cmp_modifiers(v, self.v_)

  def __init__(self, v):
    self.v_ = v


class CmpWithModifiers:
  fi = float("inf")
  def __call__(self, name, eventValue, attrValue):
    if isinstance(attrValue, PropTest):
      return attrValue(eventValue)
    elif name == "value" and abs(attrValue) == self.fi:
      return sign(attrValue) == sign(eventValue)
    elif name == "source":
      return (attrValue is None) or (eventValue == attrValue)
    elif name == "modifiers":
      return cmp_modifiers(eventValue, attrValue)
    else:
      return eventValue == attrValue


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
    return (("type", codes.EV_BCT),)

  @staticmethod
  def init(i):
    return (("type", codes.EV_BCT), ("code", codes.BCT_INIT), ("value", i))

  @staticmethod
  def any():
    return ()


class StateSink:
 def __call__(self, event):
   #logger.debug("{}: processing event: {}, state: {}, next: {}".format(self, event, self.state_, self.next_))
   if (self.state_ == True) and (self.next_ is not None):
     self.next_(event)

 def set_state(self, state):
   #logger.debug("{}: setting state to {}".format(self, state))
   self.state_ = state
   if self.next_:
     self.next_(Event(codes.EV_BCT, codes.BCT_INIT, 1 if state == True else 0, time.time()))

 def get_state(self):
   return self.state_

 def set_next(self, next):
   #logger.debug("{}: setting next to {}".format(self, next))
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


def ToggleState(stateSink):
  def op(event):
    stateSink.set_state(not stateSink.get_state())
    #logger.debug("{} state is {}".format(stateSink, stateSink.get_state()))
    return True
  return op


class FilterSink:
  def __call__(self, event):
   #logger.debug("{}: processing event: {}, state: {}, next: {}".format(self, event, self.state_, self.next_))
   if self.next_ is not None and self.op_(event) == True:
     self.next_(event)

  def set_next(self, next):
   #logger.debug("{}: setting next to {}".format(self, next))
   self.next_ = next
   return next

  def set_op(self, op):
    self.op_ = op

  def __init__(self, op=lambda event: True, next=None):
   self.op_, self.next_ = op, next


class SourceFilterOp:
  def __call__(self, event):
    return not (not self.state_ and getattr(event, "source", None) in self.sources_)

  def set_state(self, state):
   self.state_ = state

  def get_state(self):
   return self.state_

  def __init__(self, sources, state=True):
    self.sources_, self.state_ = [calc_hash(s) for s in sources], state


class ModeSink:
  def __call__(self, event):
    #if event.type == codes.EV_BCT and event.code == codes.BCT_INIT:
    #  logger.debug("{}: Recieved init event: {}".format(self, event.value))
    child = self.children_.get(self.mode_, None)
    if child is not None:
      return child(event)
    else:
      return False

  def set_mode(self, mode):
    if mode == self.mode_:
      return True
    logger.info("{}: Setting mode: {}".format(self.name_, mode))
    #logger.debug("{}({}): Setting mode: {}".format(self.name_, self, mode))
    if mode not in self.children_:
      logger.warning("{}: No such mode: {}".format(self.name_, mode))
      return False
    self.set_active_child_state_(False)
    self.mode_ = mode
    self.set_active_child_state_(True)
    return True

  def get_mode(self):
    return self.mode_

  def add(self, mode, child):
    #logger.debug("{}: Adding child {} to  mode {}".format(self, child, mode))
    if child is None:
      raise RuntimeError("Child is None")
    self.children_[mode] = child
    child(Event(codes.EV_BCT, codes.BCT_INIT, 1 if mode == self.mode_ else 0, time.time()))
    return child

  def set_active_child_state_(self, state):
    if self.mode_ in self.children_:
      child = self.children_.get(self.mode_, None)
      if child is not None:
        #logger.debug("{}: Notifying child {} about setting state to {}".format(self, child, state))
        child(Event(codes.EV_BCT, codes.BCT_INIT, 1 if state == True else 0, time.time()))

  def __init__(self, name=""):
    self.children_, self.mode_, self.name_ = {}, None, name


class CycleMode:
  def __call__(self, event):
    assert(len(self.modes))
    i = self.i
    if i == len(self.modes) - 1:
      if self.loop == True:
        i = 0
    else:
      i += 1
    if i != self.i:
      self.i = i
      self.modeSink.set_mode(self.modes[self.i])
    return True

  def __init__(self, modeSink, modes, loop=True):
    self.i, self.modeSink, self.modes, self.loop = 0, modeSink, modes, loop


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

  def add(self, mode, current):
    if current is None or self.sink_.get_mode() == current:
      self.mode_.append(mode)
      self.sink_.set_mode(mode)

  def remove(self, mode, current):
    if current is None or self.sink_.get_mode() == current:
      for i in range(len(self.mode_)-1, -1, -1):
        if self.mode_[i] == mode:
          self.mode_.pop(i)
          break;
      self.set_top_mode_()

  def swap(self, f, t, current):
    if current is None or self.sink_.get_mode() == current:
      for i in range(len(self.mode_)-1, -1, -1):
        if self.mode_[i] == f:
          self.mode_[i] = t
          break;
      self.set_top_mode_()

  def cycle_swap(self, modes, current):
    if current is None or self.sink_.get_mode() == current:
      lm = len(modes)
      for i in range(len(self.mode_)-1, -1, -1):
        for j in range(0, lm):
          if self.mode_[i] == modes[j]:
            j = j+1 if j < lm-1 else 0
            self.mode_[i] = modes[j]
            self.set_top_mode_()
            return

  def clear(self):
    self.mode_ = []

  def set(self, mode, save):
    self.save_(save)
    self.sink_.set_mode(mode)

  def cycle(self, modes, step, loop, save):
    self.save_(save)
    m = self.sink_.get_mode()
    assert(len(modes))
    if m in modes:
      lm = len(modes)
      i = modes.index(m)
      i += sign(step)*(abs(step) % lm)
      if i >= lm:
        i = i - lm if loop == True else lm - 1
      elif i < 0:
        i = i + lm if loop == True else 0
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
  def make_add(self, mode, current=None):
    def op(event):
      self.add(mode, current)
      return True
    return op
  def make_remove(self, mode, current=None):
    def op(event):
      self.remove(mode, current)
      return True
    return op
  def make_swap(self, f, t, current=None):
    def op(event):
      self.swap(f, t, current)
      return True
    return op
  def make_cycle_swap(self, modes, current=None):
    def op(event):
      self.cycle_swap(modes, current)
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
  def make_cycle(self, modes, step, loop, save):
    def op(event):
      self.cycle(modes, step, loop, save)
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

  def set_top_mode_(self):
    if len(self.mode_):
      m = self.mode_[-1]
      if m != self.sink_.get_mode():
        self.sink_.set_mode(m)


class MultiCurveSink:
  def __call__(self, event):
    if event.type in (codes.EV_REL,):
      k = (event.source, event.code)
      self.events_.setdefault(k, [])
      #Have to store selected properties of event but not reference to event itself,
      #because event properties might be modified before update() is called
      self.events_[k].append((event.value, event.timestamp))

  def update(self, tick, timestamp):
    keys = self.op_(self.events_, timestamp)
    for k in keys:
      for e in self.events_.get(k, ()):
        self.curves_[k].move_by(e[0], e[1])
    for k in self.events_.keys():
      self.events_[k] = []

  def __init__(self, curves, op):
    self.op_, self.curves_, self.events_ = op, curves, {}


class MCSCmpOp:
  def __call__(self, events, timestamp):
    if len(events) == 0:
      return ()
    selected, distance = None, 0.0
    for i,q in events.items():
      d = 0.0
      for e in q:
        d += abs(e[0])
      if self.cmp_(d, distance):
        selected, distance = i, d
    return () if selected is None else (selected,)

  def __init__(self, cmp):
    self.cmp_ = cmp


class MCSThresholdOp:
  def __call__(self, events, timestamp):
    if len(events) == 0:
      return ()
    candidate, cd = None, 0.0
    #Finding axis that has moved the most (the candidate to switch to) and the current distance the candidate has moved
    for i,q in events.items():
      #Ensuring that all axes that have moved will be in distances_
      self.distances_.setdefault(i, 0.0)
      d = 0.0
      for e in q:
        d += abs(e[0])
      if d > cd:
        candidate, cd = i, d
    #Adding current distance of candidate to it's total distance and subtracting this distance from total distances of other axes
    for j in self.distances_.keys():
      if j == candidate:
        #If candidate's total distance has reached threshold, make candidate a selected axis and clamp it's total distance
        self.distances_[j] += cd
        threshold = self.thresholds_.get(j, float("inf"))
        if self.distances_[j] >= threshold:
          if self.selected_ != j:
            #logger.debug("Selecting {} over {}; dist:{}; thr:{}".format(j, self.selected_, self.distances_[j], self.thresholds_[j]))
            self.selected_ = j
            for k in self.distances_.keys():
              self.distances_[k] = 0.0
            break
          self.distances_[j] = threshold
      else:
        #When subtracting from total distances of other axes, clamp to 0
        self.distances_[j] -= cd
        self.distances_[j] = max(self.distances_[j], 0.0)
    #logger.debug("{} {} {} {}".format(candidate, cd, self.distances_, self.selected_))
    return () if self.selected_ is None else (self.selected_,)

  def __init__(self, thresholds):
    self.thresholds_, self.distances_, self.selected_ = thresholds, {}, None


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
      c = self.coeffs_[i]
      if c == 0.0:
        continue
      r += c*v**i
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
    return self.j_.get_axis_value(self.a_)

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
    #logger.debug(("{}: {} -> {}".format(self, old, new)))
    dirty = False
    for c in self.listeners_:
      if c() is None:
        #logger.debug("{}: Listener {} has been removed".format(self, c))
        dirty = True
        continue
      c().on_move_axis(self, old, new)
    if dirty:
      self.cleanup_()

  def get(self):
    return self.next_.get()

  def limits(self):
    return self.next_.limits()

  def add_listener(self, listener):
    #logger.debug("{}: Adding listener {}".format(self, listener))
    self.listeners_.append(weakref.ref(listener))

  def remove_listener(self, listener):
    try:
      self.listeners_.remove(listener)
    except ValueError:
      raise RuntimeError("Listener {} not registered".format(listener))

  def __init__(self, next):
    assert(next is not None)
    self.next_, self.listeners_ = next, []
    #logger.debug("{}: Created".format(self))

  def __del__(self):
  #logger.debug("{}: Deleted".format(self))
    pass

  def cleanup_(self):
    i = 0
    while i < len(self.listeners_):
      if self.listeners_[i]() is None:
        self.listeners_.pop(i)
        continue
      else:
        i += 1


class RateSettingAxis:
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


class NoopCurve:
  def move_by(self, x, timestamp):
    return self.value_

  def reset(self):
    pass

  def on_move_axis(self, axis, old, new):
    pass

  def get_value(self):
    return self.value_

  def __init__(self, value):
    self.value_ = value


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
    delta = sensitivity * self.deltaOp_.calc(x, timestamp)
    value = clamp(value + delta, *self.axis_.limits())
    delta = value - baseValue
    self.move_axis_(value=delta, relative=True)
    #logger.debug( "{}: x:{: .3f}, base value:{: .3f}, sensitivity:{: .3f}, value delta:{: .3f}, new value:{: .3f}".format(self, x, baseValue, sensitivity, delta, value))
    #logger.debug("{}: x:{: .3f}, t:{}, dv:{: .3f}".format(self, x, timestamp, delta))
    return delta

  def reset(self):
    #logger.debug("{}: resetting".format(self))
    self.s_, self.busy_, self.dirty_  = 0, False, False
    assert(self.valueOp_ is not None)
    self.valueOp_.reset()
    assert(self.deltaOp_ is not None)
    self.deltaOp_.reset()

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
  ADJUST = 3


class PointMovingCurve:
  def move_by(self, x, timestamp):
    if self.dirty_:
      self.after_move_axis_()
      self.dirty_ = False
      #logger.debug("{}: someone has moved axis, new point center: {}".format(self, self.point_.get_center()))
    #Setting new point center if x movement direction has changed
    s = sign(x)
    center, value = self.point_.get_center(), self.getValueOp_(self.next_)
    if self.ts_ == None: self.ts_ = timestamp
    if s != 0:
      if (self.s_ != 0 and self.s_ != s) or ((timestamp - self.ts_) > self.resetTime_):
        c = value if center is None else self.centerOp_(value, center)
        #logger.debug("{}: new point center: {} (was: {})".format(self, c, center))
        self.point_.set_center(c)
      self.s_, self.ts_ = s, timestamp
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
    self.s_, self.ts_, self.busy_, self.dirty_, self.delta_ = 0, None, False, False, 0.0
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
    self.delta_ += new - old
    self.next_.on_move_axis(axis, old, new)

  def __init__(self, next, point, getValueOp, centerOp=lambda new,old : 0.5*old+0.5*new, resetDistance=float("inf"), onReset=PointMovingCurveResetPolicy.DONT_TOUCH, onMove=PointMovingCurveResetPolicy.DONT_TOUCH, resetTime = float("inf")):
    assert(next is not None)
    assert(point is not None)
    assert(getValueOp is not None)
    assert(centerOp is not None)
    self.next_, self.point_, self.getValueOp_, self.centerOp_, self.resetDistance_, self.onReset_, self.onMove_ = next, point, getValueOp, centerOp, resetDistance, onReset, onMove
    self.resetTime_ = resetTime
    self.s_, self.ts_, self.busy_, self.dirty_, self.delta_ = 0, None, False, False, 0.0

  def after_move_axis_(self):
    #self.s_, self.busy_, self.dirty_ = 0, False, False
    self.busy_, self.dirty_ = False, False
    if self.onMove_ == PointMovingCurveResetPolicy.ADJUST:
      c = self.point_.get_center()
      if c is not None:
        self.point_.set_center(c + self.delta_)
        self.delta_ = 0.0
    else:
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
    #TODO Add self.deltaOp_(x, timestamp) that will modify x (i.e. based on accumulated x)
    #Will need to reset it
    #Take this op and ops it uses from parseCombinedCurve
    pos = clamp(self.pos_ + x, *self.posLimits_)
    if pos == self.pos_:
      return
    self.pos_ = pos
    #TODO Split op_ into 2 ops with calc() and reset():
    #valueOp_ that calculates value from pos, and
    #posOp_ that does the opposite
    #Mb remname them to outputOp_ and inputOp_
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


#TODO Extract binary search-based calc_pos into separate op that does not rely on point
#Use precomputed array of positions and values (input and output values), sorted by the latter, for looking up initial input value bounds
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


class InputBasedCurve2:
  def move_by(self, x, timestamp):
    assert(self.deltaOp_)
    assert(self.inputOp_)
    assert(self.outputOp_)
    assert(self.axis_)
    if self.dirty_:
      self.reset_(axisMoved=True)
    delta = self.deltaOp_.calc(x, timestamp)
    inputValue = clamp(self.inputValue_ + delta, *self.inputValueLimits_)
    if inputValue == self.inputValue_:
      return
    self.inputValue_ = inputValue
    outputValue = self.outputOp_.calc(self.inputValue_)
    if self.cb_:
      class Data:
        pass
      data = Data()
      data.curve, data.x, data.ts, data.delta, data.iv, data.ov = self, x, timestamp, delta, inputValue, outputValue
      self.cb_(data)
    try:
      self.busy_ = True
      self.axis_.move(outputValue, False)
      newOutputValue = self.axis_.get()
      if newOutputValue != outputValue:
        self.inputValue_ = self.inputOp_.calc(newOutputValue)
    finally:
      self.busy_ = False

  def reset(self):
    self.reset_(axisMoved=False)

  def get_axis(self):
    return self.axis_

  def on_move_axis(self, axis, old, new):
    #logger.debug("{}: on_move_axis({}, {}, {})".format(self, axis, old, new))
    assert(axis == self.axis_)
    if self.busy_ or self.dirty_: return
    self.dirty_ = True

  def get_input_value(self):
    return self.inputValue_

  def __init__(self, axis, inputOp, outputOp, deltaOp, inputValueLimits=(-1.0, 1.0), cb=None, resetOpsOnAxisMove=True):
    self.axis_, self.inputOp_, self.outputOp_, self.deltaOp_, self.inputValueLimits_, self.cb_, self.resetOpsOnAxisMove_ = \
      axis, inputOp, outputOp, deltaOp, inputValueLimits, cb, resetOpsOnAxisMove
    assert(self.deltaOp_)
    assert(self.inputOp_)
    assert(self.outputOp_)
    assert(self.axis_)
    self.inputValue_ = self.inputOp_.calc(self.axis_.get())
    self.busy_, self.dirty_ = False, False

  def reset_(self, axisMoved):
    assert(self.deltaOp_)
    assert(self.inputOp_)
    assert(self.outputOp_)
    assert(self.axis_)
    #logger.debug("{}: resetting".format(self))
    if not axisMoved or (axisMoved and self.resetOpsOnAxisMove_):
      #logger.debug("{}: resetting ops".format(self))
      self.inputOp_.reset()
      self.outputOp_.reset()
      self.deltaOp_.reset()
      if self.cb_:
        self.cb_(None)
    self.inputValue_ = self.inputOp_.calc(self.axis_.get())
    self.busy_, self.dirty_ = False, False


class InputBasedCurve2PrintCB:
  def __call__(self, data):
    if data is None:
      logger.info("{}: resetting".format(self.name_))
      self.deltaDerivatives_.reset()
      self.ivDerivatives_.reset()
      self.ovDerivatives_.reset()
      self.td_, self.tx_ = 0.0, 0.0
    elif data.x != 0:
      self.td_ += data.delta
      self.tx_ += data.x
      self.deltaDerivatives_.update(self.td_, self.tx_)
      self.ivDerivatives_.update(data.iv, self.tx_)
      self.ovDerivatives_.update(data.ov, self.tx_)
      s = "{}: ts:{:+.3f}; x:{:+.3f}; tx:{:+.3f}; delta:{:+.3f}; td:{:+.3f}; ".format(self.name_, data.ts, data.x, self.tx_, data.delta, self.td_)
      for i in range(1, self.deltaDerivatives_.order()+1):
        s += "d({}):{:+.3f}; ".format(i, self.deltaDerivatives_.get(i))
      s += "iv:{:+.3f}; ".format(data.iv)
      for i in range(1, self.ivDerivatives_.order()+1):
        s += "d({}):{:+.3f}; ".format(i, self.ivDerivatives_.get(i))
      s += "ov:{:+.3f}; ".format(data.ov)
      for i in range(1, self.ovDerivatives_.order()+1):
        s += "d({}):{:+.3f}; ".format(i, self.ovDerivatives_.get(i))
      s = s[:-2]
      logger.info(s)

  def __init__(self, name, deltaOrder, ivOrder, ovOrder):
    self.name_, self.tx_, self.td_ = name, 0.0, 0.0
    self.deltaDerivatives_ = Derivatives(deltaOrder)
    self.ivDerivatives_ = Derivatives(ivOrder)
    self.ovDerivatives_ = Derivatives(ovOrder)


class IterativeInputOp:
  def calc(self, outputValue, inputValueLimits):
    """inputValueLimits[0] can be < or > inputValueLimits[1]"""
    assert(self.outputOp_ is not None)
    bInputValue, eInputValue = inputValueLimits
    #Determine how beginning output value compares to end output value
    #If outputRelation is True, then output function is increasing from the self.cmp_ point of view, otherwise it is decreasing
    outputRelation = self.cmp_(self.outputOp_.calc(bInputValue), self.outputOp_.calc(eInputValue))
    i, delta = 0, 0.0
    while i <= self.numSteps_:
      i += 1
      mInputValue = 0.5*bInputValue + 0.5*eInputValue
      mOutputValue = self.outputOp_.calc(mInputValue)
      delta = abs(outputValue - mOutputValue)
      if delta < self.eps_:
        break
      elif outputRelation ^ self.cmp_(outputValue, mOutputValue):
        #If given outputValue compares to middle output value differently,
        #than beginning output value compares to end output value,
        #look in the second half, else in first
        bInputValue = mInputValue
      else:
        eInputValue = mInputValue
    #logger.debug("{}: Found root {} for value {} in {} steps; delta: {}; limits: {}".format(self, mInputValue, outputValue, i, delta, inputValueLimits))
    return mInputValue

  def reset(self):
    pass

  def __init__(self, outputOp, cmp=lambda a,b: a < b, eps=0.01, numSteps=100):
    assert(outputOp is not None)
    self.outputOp_, self.cmp_, self.eps_, self.numSteps_ = outputOp, cmp, eps, numSteps


class LookupInputOp:
  def calc(self, outputValue, inputValueLimits):
    assert(self.nextOp_ is not None)
    ie = bisect.bisect_right(self.ovs_, outputValue)
    limits = None
    if ie == 0 or ie == len(self.ivs_):
      limits = inputValueLimits
    else:
      if not (self.ovs_[ie-1] <= outputValue) or not (self.ovs_[ie] >= outputValue):
        raise RuntimeError("{}: Wrong interval [{}, {}] for value {}".format(self, self.ovs_[ie-1], self.ovs_[ie], outputValue))
      limits = (self.ivs_[ie-1], self.ivs_[ie])
    found = self.nextOp_.calc(outputValue, limits)
    return found

  def reset(self):
    self.nextOp_.reset()

  def __init__(self, nextOp, ovs, ivLimits):
    assert(nextOp is not None)
    assert(ivLimits[0] < ivLimits[1])
    ovs.sort()
    self.nextOp_, self.ovs_ = nextOp, ovs
    self.ivs_ = [nextOp.calc(ov, ivLimits) for ov in ovs]


class LimitedOpToOp:
  def calc(self, value):
    return self.op_.calc(value, self.limits_)

  def reset(self):
    self.op_.reset()

  def __init__(self, op, limits):
    self.op_, self.limits_ = op, limits


class LookupOp:
  def calc(self, outputValue):
    ie, ivLimits, ovPrev = bisect.bisect_right(self.ovs_, outputValue), None, None
    
    if ie == 0:
      iv = self.ivs_[0]
      while True:
        iv -= self.s_*self.inputStep_
        ov = self.outputOp_.calc(iv)
        if ov == ovPrev:
          break
        else:
          ovPrev = ov
        self.ivs_.insert(0, iv)
        self.ovs_.insert(0, ov)  
        #logger.debug("{}: outputValue {:0.3f}: inserting iv: {:0.3f}, ov: {:0.3f}".format(self, outputValue, iv, ov))
        if ov <= outputValue:
          ie = 1
          break
    elif ie == len(self.ivs_):
      iv = self.ivs_[ie-1]
      while True:
        iv += self.s_*self.inputStep_
        ov = self.outputOp_.calc(iv)
        if ov == ovPrev:
          break
        else:
          ovPrev = ov
        self.ivs_.append(iv)
        self.ovs_.append(ov)
        #logger.debug("{}: outputValue {:0.3f}: inserting iv: {:0.3f}, ov: {:0.3f}".format(self, outputValue, iv, ov))
        if ov >= outputValue:
          ie = len(self.ivs_)-1
          break

    if not (self.ovs_[ie-1] <= outputValue) or not (self.ovs_[ie] >= outputValue):
      raise RuntimeError("{}: Wrong interval [{}, {}] for value {}".format(self, self.ovs_[ie-1], self.ovs_[ie], outputValue))
    ivLimits = (self.ivs_[ie-1], self.ivs_[ie])
    inputValue = self.inputOp_.calc(outputValue, ivLimits)
    #logger.debug("{}: found inputValue {:0.3f} for outputValue {:0.3f}".format(self, inputValue, outputValue))
    return inputValue

  def reset(self):
    self.inputOp_.reset()
    self.outputOp_.reset()

  def __init__(self, inputOp, outputOp, inputStep):
    self.inputOp_, self.outputOp_, self.inputStep_ = inputOp, outputOp, inputStep
    self.ivs_, self.ovs_ = [], []
    iv = (0.0, self.inputStep_)
    ov = tuple((self.outputOp_.calc(ivv) for ivv in iv))
    self.s_ = sign(iv[1]-iv[0])*sign(ov[1]-ov[0])
    self.ivs_.append(iv[0])
    self.ovs_.append(ov[0])
    i1 = 1 if self.s_ > 0 else 0
    self.ivs_.insert(i1, iv[1])
    self.ovs_.insert(i1, ov[1])


class ApproxOp:
  def calc(self, value):
    return self.approx_(value)
  def reset(self):
    pass
  def __init__(self, approx):
    self.approx_ = approx


#delta ops
class OpToDeltaOp:
  def calc(self, value, timestamp):
    return self.op_.calc(value)
  def reset(self):
    self.op_.reset()
  def __init__(self, op):
    self.op_ = op


class ApproxDeltaOp:
  def calcOutput(self, value, timestamp):
    return self.approx_(value)
  def reset(self):
    pass
  def __init__(self, approx):
    self.approx_ = approx


class CombineDeltaOp:
  def calc(self, x, timestamp):
    r = None
    for op in self.ops_:
      r = op.calc(x, timestamp) if r is None else self.combine_(r, op.calc(x, timestamp))
    return r
  def reset(self):
    #logger.info("{}: resetting".format(self))
    for op in self.ops_:
      op.reset()
  def __init__(self, combine, ops):
    self.combine_, self.ops_ = combine, ops
    self.reset()


class XDeltaOp:
  def calc(self, x, timestamp):
    return x
  def reset(self):
    pass


class AccumulateDeltaOp:
  def calc(self, x, timestamp):
    for op in self.ops_:
      self.distance_ = op.calc(self.distance_, x, timestamp)
    self.distance_ += x
    return self.approx_(self.distance_) if self.approx_ is not None else self.distance_
  def reset(self):
    #logger.debug("{}: resetting".format(self))
    self.distance_ = 0.0
    for op in self.ops_:
      op.reset()
  def add_op(self, op):
    self.ops_.append(op)
  def __init__(self, approx, ops=None):
    self.approx_ = approx
    self.ops_ = [] if ops is None else ops
    self.reset()


class DeadzoneDeltaOp:
  def calc(self, x, timestamp):
    """Returns 0 while inside deadzone radius, x otherwise."""
    s = sign(x)
    if self.s_ != s:
      self.s_, self.sd_ = s, 0.0
    self.sd_ += abs(x)
    if self.sd_ > self.deadzone_:
      return self.next_.calc(x, timestamp)
    else:
      return 0.0
  def reset(self):
    #logger.debug("{}: resetting".format(self))
    self.s_, self.sd_ = 0, 0.0
    self.next_.reset()
  def __init__(self, next, deadzone=0.0):
    self.sd_, self.s_, self.next_, self.deadzone_ = 0.0, 0, next, deadzone


#distance-delta ops
class SignDistanceDeltaOp:
  def calc(self, distance, x, timestamp):
    """distance is absolute, x is relative."""
    r = 1.0
    s = sign(x)
    if self.s_ == 0:
      self.s_ = s
    elif self.s_ != s:
      self.sd_ += abs(x)
      if self.sd_ > self.deadzone_:
        #logger.debug("{}: leaved deadzone, changing sign from {} to {}".format(self, self.s_, s))
        self.sd_, self.s_, r = 0.0, s, 0.0
    elif self.sd_ != 0.0:
      self.sd_ = 0.0
    return r * (distance if self.next_ is None else self.next_.calc(distance, x, timestamp))
  def reset(self):
    #logger.debug("{}: resetting".format(self))
    self.s_, self.sd_ = 0, 0.0
    if self.next_:
      self.next_.reset()
  def __init__(self, deadzone=0.0, next=None):
    self.next_, self.deadzone_ = next, deadzone
    self.sd_, self.s_ = 0.0, 0


class TimeDistanceDeltaOp:
  def calc(self, distance, x, timestamp):
    """distance is absolute, x is relative."""
    assert(self.resetTime_ > 0.0)
    r = 1.0
    if self.timestamp_ is None:
      self.timestamp_ = timestamp
    dt = timestamp - self.timestamp_
    self.timestamp_ = timestamp
    if dt > self.holdTime_:
      r = clamp(1.0 - (dt - self.holdTime_) / self.resetTime_, 0.0, 1.0)
    #logger.debug("{}.calc(): r:{:.3f}".format(self, r))
    return r * (distance if self.next_ is None else self.next_.calc(distance, x, timestamp))
  def reset(self):
    self.timestamp_ = None
    if self.next_:
      self.next_.reset()
  def __init__(self, resetTime, holdTime, next=None):
    self.resetTime_, self.holdTime_, self.next_ = resetTime, holdTime, next
    self.timestamp_ = None


#Chain curves
class AccumulateRelChainCurve:
  def move_by(self, x, timestamp):
    """x is relative."""
    self.update_()
    value = self.valueDDOp_.calc(self.value_, x, timestamp)
    delta = self.deltaDOp_.calc(x, timestamp)
    self.value_ = self.combine_(value, delta)
    newValue = self.next_.move(self.value_, timestamp)
    if newValue != self.value_:
      self.value_ = newValue
    #logger.debug("{}: value_:{:+.3f}".format(self, self.value_))
    return self.value_

  def reset(self):
    self.valueDDOp_.reset()
    self.deltaDOp_.reset()
    self.inputOp_.reset()
    self.next_.reset()
    self.value_ = self.inputOp_.calc(self.next_.get_value())
    self.dirty_ = False

  def on_move_axis(self, axis, old, new):
    #logger.debug("{}.on_move_axis({}, {:+0.3f}, {:+0.3f})".format(self, axis, old, new))
    self.dirty_ = True
    self.next_.on_move_axis(axis, old, new)

  def get_value(self):
    self.update_()
    return self.value_

  def set_next(self, next):
    self.next_ = next

  def __init__(self, next, valueDDOp, deltaDOp, combine, inputOp):
    self.next_, self.valueDDOp_, self.deltaDOp_, self.combine_, self.inputOp_ = next, valueDDOp, deltaDOp, combine, inputOp
    self.value_, self.dirty_ = 0.0, False

  def update_(self):
    if self.dirty_ == True:
      self.value_ = self.inputOp_.calc(self.next_.get_value())
      #logger.debug("{}.update_(): recalculated value_: {:+0.3f}".format(self, self.value_))
      self.dirty_ = False


class TransformAbsChainCurve:
  def move(self, x, timestamp):
    self.update_()
    outputValue = self.outputOp_.calc(x)
    newOutputValue = self.next_.move(outputValue, timestamp)
    #logger.debug("{}: x:{:+.3f}, ov:{:+.3f}, nov:{:+.3f}".format(self, x, outputValue, newOutputValue))
    if newOutputValue != outputValue:
      #logger.debug("{}: nov != ov".format(self))
      self.value_ = self.inputOp_.calc(newOutputValue)
    else:
      self.value_ = x
    #logger.debug("{}: value_:{:+.3f}".format(self, self.value_))
    return self.value_

  def reset(self):
    self.inputOp_.reset()
    self.outputOp_.reset()
    self.next_.reset()
    self.value_ = self.inputOp_.calc(self.next_.get_value())
    self.dirty_ = False

  def on_move_axis(self, axis, old, new):
    self.dirty_ = True
    self.next_.on_move_axis(axis, old, new)

  def get_value(self):
    self.update_()
    return self.value_

  def set_next(self, next):
    self.next_ = next

  def __init__(self, next, inputOp, outputOp):
    self.next_, self.inputOp_, self.outputOp_ = next, inputOp, outputOp
    self.value_, self.dirty_ = 0.0, False

  def update_(self):
    if self.dirty_ == True:
      self.value_ = self.inputOp_.calc(self.next_.get_value())
      #logger.debug("{}.update_(): recalculated value_: {:+0.3f}".format(self, self.value_))
      self.dirty_ = False


class AxisAbsChainCurve:
  """Acturally moves axis. Is meant to be at the bottom of chain."""
  def move(self, x, timestamp):
    self.axis_.move(x, relative=False)
    #logger.debug("{}: x:{:+.3f}, v:{:+.3f}".format(self, x, self.axis_.get()))
    return self.axis_.get()

  def reset(self):
    pass

  def on_move_axis(self, axis, old, new):
    pass

  def get_value(self):
    return self.axis_.get()

  def set_next(self, next):
    self.next_ = next

  def __init__(self, axis):
    self.axis_ = axis


class AxisTrackerRelChainCurve:
  """Prevents endless recursion on moving axis.
     Is meant to be at the top of chain.
     Subscribe as axis listener."""
  def move_by(self, x, timestamp):
    """x is relative."""
    if self.dirty_ == True:
      self.reset()
    self.busy_ = True
    v = None
    try:
      v = self.next_.move_by(x, timestamp)
    finally:
      self.busy_ = False
    return v

  def reset(self):
    self.busy_, self.dirty_ = False, False
    self.next_.reset()

  def on_move_axis(self, axis, old, new):
    if self.busy_ == True:
      return
    if self.resetOnAxisMove_ == True:
      self.dirty_ = True
    self.next_.on_move_axis(axis, old, new)

  def get_value(self):
    return self.next_.get_value()

  def set_next(self, next):
    self.next_ = next

  def __init__(self, next, resetOnAxisMove):
    self.next_, self.resetOnAxisMove_ = next, resetOnAxisMove
    self.busy_, self.dirty_ = False, False


class OffsetAbsChainCurve:
  def move(self, x, timestamp):
    """x is absolute."""
    #logger.debug("{}: x:{:+.3f}".format(self, x))
    s = sign(x)
    if self.s_ != s:
      if self.s_ != 0:
        self.offset_ += self.x_
        #logger.debug("{}: new offset_: {}".format(self, self.offset_))
      self.s_ = s
    elif abs(x) < abs(self.x_):
      self.offset_ += self.x_ - x
      self.x_ = x
      return self.x_
    ox = x + self.offset_
    nox = self.next_.move(ox, timestamp)
    #logger.debug("{}: ox:{:+.3f}, nox:{:+.3f}".format(self, ox, nox))
    #nox can still be outside of next_ input limits, so have to store sign of x to be able to backtrack
    if nox == ox:
      #within limits
      if self.state_ == 1:
        self.sx_, self.state_ = 0, 0
      self.x_ = x
      #logger.debug("{}: within limits, x: {}, x_: {}".format(self, x, self.x_))
    else:
      #outside limits
      if self.state_ == 0:
        self.sx_, self.state_ = s, 1
      self.x_ = x if self.sx_ != s else (nox - self.offset_)
      #logger.debug("{}: outside limits, x: {}, x_: {}".format(self, x, self.x_))
    #logger.debug("{}.move(): offset_:{:+.3f}, x_:{:+.3f}".format(self, self.offset_, self.x_))
    return self.x_

  def reset(self):
    self.s_, self.sx_, self.state_, self.x_, self.offset_ = 0, 0, 0, 0.0, 0.0
    self.next_.reset()

  def on_move_axis(self, axis, old, new):
    self.offset_ += (new - old)
    #logger.debug("{}.on_move_axis(): offset_:{:+.3f}, x_:{:+.3f}".format(self, self.offset_, self.x_))
    self.next_.on_move_axis(axis, old, new)

  def get_value(self):
    return self.x_

  def set_next(self, next):
    self.next_ = next

  def __init__(self, next):
    self.s_, self.sx_, self.state_, self.x_, self.offset_ = 0, 0, 0, 0.0, 0.0
    self.next_ = next


class PrintRelChainCurve:
  def move_by(self, x, timestamp):
    """x is relative."""
    r = self.next_.move_by(x, timestamp)
    self.tx_ += x
    av = self.axis_.get()
    self.ds_.update(av, self.tx_)
    s = "{}: x:{:+.3f}; tx:{:+.3f}; av:{:+.3f}; ".format(self.name_, x, self.tx_, av)
    for i in range(1, self.ds_.order()+1):
      s += "d({}):{:+.3f}; ".format(i, self.ds_.get(i))
    s = s[:-2]
    logger.info(s)
    return r

  def reset(self):
    self.next_.reset()
    self.ds_.reset()
    self.tx_ = 0.0

  def on_move_axis(self, axis, old, new):
    self.next_.on_move_axis(axis, old, new)

  def get_value(self):
    return self.axis_.get()

  def set_next(self, next):
    self.next_ = next

  def __init__(self, next, axis, name, order):
    self.next_, self.axis_, self.name_ = next, axis, name
    self.tx_ = 0.0
    self.ds_ = Derivatives(order)


#linking curves
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
      try:
        self.busy_ = True
        self.controlledAxis_.move(cd, relative=True)
      except:
        raise
      finally:
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

    #reset only if moved in opposite direction for more than self.threshold_
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
      try:
        self.busy_= True
        self.controlledAxis_.move(cd + self.cv_, relative=False)
      except:
        raise
      finally:
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
  """Directly links positions of 2 axes using op and offset.
     If controlled axis is moved externally by delta, adds this delta to offset.
     On reset computes offset as difference between actual and expected positions of controlled axis.
  """
  def move_by(self, x, timestamp):
    """Call this by the same input that is assumed to affect controlling axis."""
    v = self.controllingAxis_.get()
    cv = self.op_(v)
    try:
      self.busy_= True
      self.controlledAxis_.move(cv + self.offset_, relative=False)
    except:
      raise
    finally:
      self.busy_= False

  def reset(self):
    self.offset_ = self.controlledAxis_.get() - self.op_(self.controllingAxis_.get())

  def on_move_axis(self, axis, old, new):
    if not self.busy_ and axis == self.controlledAxis_:
      self.offset_ += new - old

  def __init__(self, controllingAxis, controlledAxis, op):
    self.controllingAxis_, self.controlledAxis_, self.op_ = controllingAxis, controlledAxis, op
    self.offset_, self.busy_  = 0.0, False


class AxisLinker:
  """Directly links positions of 2 axes using op and offset.
     If controlled axis is moved externally by delta, adds this delta to offset.
     When resetting axes, reset controlling axis first, then controlled.
  """
  def reset(self):
    self.offset_ = self.controlledAxis_.get() - self.op_(self.controllingAxis_.get())

  def set_state(self, state):
    if state == True:
      self.reset()
    self.state_ = state

  def on_move_axis(self, axis, old, new):
    if self.state_:
      if not self.busy_ and axis == self.controlledAxis_:
        #logger.debug("{} : Controlled axis has moved to {}".format(self, new))
        self.offset_ += new - old
      elif axis == self.controllingAxis_:
        cv = self.op_(new)
        try:
          self.busy_= True
          #logger.debug("{} : Moving controlled axis to {}".format(self, cv+self.offset_))
          self.controlledAxis_.move(cv + self.offset_, relative=False)
        except:
          raise
        finally:
          self.busy_= False

  def __init__(self, controllingAxis, controlledAxis, op):
    self.controllingAxis_, self.controlledAxis_, self.op_ = controllingAxis, controlledAxis, op
    self.offset_, self.busy_, self.state_  = 0.0, False, False
    logger.debug("{}: Created".format(self))

  def __del__(self):
    logger.debug("{}: Deleted".format(self))


class SetAxisLinkerState:
  def __call__(self, event):
    if self.linker_ is not None and event.type == codes.EV_BCT and event.code == codes.BCT_INIT:
      self.linker_.set_state(event.value)
      return True
    else:
      return False

  def __init__(self, linker):
    self.linker_ = linker


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

  def get_axis_value(self, axis):
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

  def get_axis_value(self, axis):
    return self.v_.get(axis, 0.0)

  def get_limits(self, axis):
    return self.limits_.get(axis, (0.0, 0.0))

  def set_limits(self, axis, limits):
    self.limits_[axis] = limits
    self.v_[axis] = clamp(self.v_.get(axis, 0.0), *limits)
    self.dirty_ = True

  def get_supported_axes(self):
    return self.axes_

  def send(self):
    if self.dirty_ == True:
      self.dirty_ = False
      packet = self.make_packet_(self.v_)
      #Need to resend packet several times to make lateral head movement work correctly
      #UDP packets are lost? Even on local machine?
      for i in range(0, self.numPackets_):
        self.socket_.sendto(packet, (self.ip_, self.port_))

  def __init__(self, ip, port, make_packet, numPackets=1):
    self.dirty_ = False
    self.socket_ = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    self.ip_, self.port_, self.make_packet_, self.numPackets_ = ip, port, make_packet, numPackets
    self.limits_ = {}
    self.v_ = {}
    for a in self.axes_:
      v = 0.0
      self.v_[a] = v
      self.move_axis(a, v, False)

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
    (codes.ABS_RX, -1.0),
    (codes.ABS_RY, 1.0),
    (codes.ABS_RZ, 1.0)
  )
  values = [dd[1]*v.get(dd[0], 0.0) for dd in d]
  result = "R/11\\{:f}\\{:f}\\{:f}".format(*values)
  return result


def make_il2_6dof_packet(v):
  #https://github.com/uglyDwarf/linuxtrack/blob/1f405ea1a3a478163afb1704072480cf7a2955c2/src/ltr_pipe.c#L938
  #r = snprintf(buf, sizeof(buf), "R/11\\%f\\%f\\%f\\%f\\%f\\%f", d->h, -d->p, d->r, -d->z/300, -d->x/1000, d->y/1000);
  d = (
    (codes.ABS_RX, -1.0),
    (codes.ABS_RY, 1.0),
    (codes.ABS_RZ, 1.0),
    (codes.ABS_Z, -1.0),
    (codes.ABS_X, -1.0),
    (codes.ABS_Y, -1.0)
  )
  values = (dd[1]*v.get(dd[0], 0.0) for dd in d)
  result = "R/11\\{:f}\\{:f}\\{:f}\\{:f}\\{:f}\\{:f}".format(*values)
  return result


class JoystickSnapManager:
  """Sets joystick axes to preset values and also can update preset values from joystick"""

  def set_snap(self, i, l):
    self.snaps_[i] = [[p[0], p[1]] for p in l]

  def update_snap(self, i):
    #logger.debug("update_snap({})".format(i))
    snap = self.snaps_.get(i, None)
    if snap is None:
      #logger.debug("{}: no snap {}".format(self, i))
      return False
    else:
      for j in xrange(len(snap)):
        snap[j][1] = self.joystick_.get_axis_value(snap[j][0])
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


class SnapTracker:
  def inc(self, snap):
    if snap not in self.snaps_:
      self.snaps_[snap] = 0
    if self.snaps_[snap] == 0:
      self.sm_.update_snap(snap)
    self.snaps_[snap] += 1

  def dec(self, snap):
    if snap not in self.snaps_:
      self.snaps_[snap] = 0
    if self.snaps_[snap] == 1:
      self.sm_.snap_to(snap)
    if self.snaps_[snap] >= 1:
      self.snaps_[snap] -= 1

  def reset(self, snap):
    self.snaps_[snap] = 0

  def __init__(self, sm):
    self.snaps_, self.sm_ = dict(), sm


class MappingJoystick:
  """Forwards calls to contained joysticks with axis mapping"""

  def move_axis(self, axis, value, relative):
    d = self.data_[axis]
    d.toJoystick.move_axis(d.toAxis, d.factor*value, relative)

  def get_axis_value(self, axis):
    d = self.data_[axis]
    value = d.toJoystick.get_axis_value(d.toAxis)
    return d.factor*value

  def get_limits(self, axis):
    d = self.data_[axis]
    return (d.factor*l for l in d.toJoystick.get_limits(d.toAxis))

  def add(self, fromAxis, toJoystick, toAxis, factor=1.0):
    class D:
      pass
    d = D()
    d.toJoystick, d.toAxis, d.factor = toJoysitick, toAxis, factor
    self.data_[fromAxis] = d

  def __init__(self):
    self.data_ = dict()

class NodeJoystick(object):
  def move_axis(self, axis, value, relative):
    if self.next_ is not None:
      self.next_.move_axis(axis, value, relative)

  def get_axis_value(self, axis):
    return self.next_.get_axis_value(axis) if self.next_ else 0

  def get_limits(self, axis):
    return self.next_.get_limits(axis) if self.next_ else (0.0, 0.0)

  def get_supported_axes(self):
    return self.next_.get_supported_axes() if self.next_ is not None else ()

  def set_button_state(self, button, state):
    self.next_.set_button_state(button, state)

  def set_next(self, next):
    self.next_ = next
    return next

  def __init__(self, next=None):
    self.next_ = next


class RateLimititngJoystick:
  def move_axis(self, axis, value, relative):
    if self.next_ is not None:
      self.v_[axis] = clamp(self.v_[axis]+value if relative else value, *self.get_limits(axis))

  def get_axis_value(self, axis):
    return self.v_.get(axis, 0.0)

  def get_limits(self, axis):
    return self.next_.get_limits(axis) if self.next_ is not None else (0.0, 0.0)

  def get_supported_axes(self):
    return self.next_.get_supported_axes() if self.next_ is not None else ()

  def set_button_state(self, button, state):
    if self.next_ is not None:
      self.next_.set_button_state(button, state)

  def set_next(self, next):
    self.next_ = next
    if self.next_ is not None:
      self.v_ = {axisId:self.next_.get_axis_value(axisId) for axisId in self.next_.get_supported_axes()}
    return next

  def update(self, tick):
    if self.next_ is not None:
      for axisId,value in self.v_.items():
        current = self.next_.get_axis_value(axisId)
        delta = value - current
        if delta != 0.0:
          if axisId in self.rates_:
            value = current + sign(delta)*min(abs(delta), self.rates_[axisId]*tick)
            delta = value - current
          self.next_.move_axis(axisId, delta, True)

  def __init__(self, next, rates):
    self.next_, self.rates_ = next, rates
    self.set_next(next)


class RateSettingJoystick:
  def move_axis(self, axis, value, relative):
    if self.next_ is not None:
      self.v_[axis] = clamp(self.v_[axis]+value if relative else value, *self.get_limits(axis))

  def get_axis_value(self, axis):
    return self.v_[axis]

  def get_limits(self, axis):
    return self.limits_.get(axis, (0.0, 0.0))

  def set_limits(self, axis, limits):
    self.limits_[axis] = limits

  def get_supported_axes(self):
    return self.next_.get_supported_axes() if self.next_ else ()

  def set_next(self, next):
    self.next_ = next
    if self.next_ is not None:
      self.v_ = {axisId : clamp(0.0, *self.get_limits(axisId)) for axisId in self.next_.get_supported_axes()}
    return next

  def update(self, tick):
    if self.next_ is None:
      return
    for axisId,value in self.v_.items():
      if value == 0.0:
        continue
      rate = self.rates_.get(axisId, 0.0)
      if rate == 0.0:
        continue
      v = rate*value*tick
      self.next_.move_axis(axisId, v, relative=True)

  def __init__(self, next, rates, limits=None):
    assert(next is not None)
    self.next_, self.rates_, self.limits_ = next, rates, {} if limits is None else limits
    self.set_next(next)


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

  def get_axis_value(self, axis):
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


class ReportingJoystickAxis:
  def move(self, v, relative):
    self.joystick_.move_axis(self.axis_, v, relative)

  def get(self):
    return self.joystick_.get_axis_value(self.axis_)

  def limits(self):
    return self.joystick_.get_limits(self.axis_)

  def add_listener(self, listener):
    self.listeners_.append(weakref.ref(listener))
    logger.debug("{}: Adding listener: {}, number of listeners: {}".format(self, listener, len(self.listeners_)))

  def remove_listener(self, listener):
    try:
      self.listeners_.remove(listener)
      #logger.debug("{}: Removing listener: {}, number of listeners: {}".format(self, listener, len(self.listeners_)))
    except ValueError:
      raise RuntimeError("Listener {} not registered".format(listener))

  def remove_all_listeners(self):
    self.listeners_ = []
    logger.debug("{}: Removing all listeners, number of listeners: {}".format(self, len(self.listeners_)))

  def on_move(self, old, new):
    dirty = False
    for c in self.listeners_:
      cc = c()
      if cc is None:
        dirty = True
      else:
        #logger.debug("{}: moving listener {}, old: {:0.3f}, new: {:0.3f}".format(self, cc, old, new))
        cc.on_move_axis(self, old, new)
    if dirty:
      self.cleanup_()

  def __init__(self, joystick, axis):
    self.joystick_, self.axis_, self.listeners_ = joystick, axis, []
    logger.debug("{}: Created".format(self))

  def __del__(self):
    logger.debug("{}: Deleted".format(self))
    pass

  def cleanup_(self):
    i = 0
    while i < len(self.listeners_):
      if self.listeners_[i]() is None:
        self.listeners_.pop(i)
      else:
        i += 1
    logger.debug("{}: listeners after cleanup {}".format(self, self.listeners_))


class ReportingJoystick(NodeJoystick):
  def move_axis(self, axis, value, relative):
    old = self.get_axis_value(axis)
    NodeJoystick.move_axis(self, axis, value, relative)
    new = self.get_axis_value(axis)
    dirty = False
    for a in self.axes_.get(axis, ()):
      aa = a()
      if aa is not None:
        aa.on_move(old, new)
      else:
        dirty = True
    if dirty:
      self.cleanup_()

  def make_axis(self, axisId):
    a = ReportingJoystickAxis(self, axisId)
    self.axes_.setdefault(axisId, [])
    self.axes_[axisId].append(weakref.ref(a))
    return a

  def __init__(self, next):
    super(ReportingJoystick, self).__init__(next)
    self.axes_ = {}

  def cleanup_(self):
    for axisId, axes in self.axes_.items():
      i = 0
      while i < len(axes):
        if axes[i]() is None:
          axes.pop(i)
        else:
          i += 1
    logger.debug("{}: axes after cleanup {}".format(self, self.axes_))


def make_reporting_joystick(f):
  def op(*args, **kwargs):
    return ReportingJoystick(f(*args, **kwargs))
  return op


def calc_sphere_intersection_params(p, d, r):
  """Returns (t1, t2) such that points (position + direction*t1) and (postion + direction*t2) lie on sphere of radius r,
     where p is position and d is direction."""
  assert(len(p) == len(d))
  l = len(p)
  a, b, c = 0.0, 0.0, 0.0
  for i in range(l):
    a += d[i]**2.0
    b += p[i]*d[i]
    c += p[i]**2.0
  b, c = 2.0*b, c - r**2.0
  D = b**2.0 - 4.0*a*c
  if D < 0.0:
     return None
  else:
    sqrtD = D**0.5
    return (0.5*(-b + sqrtD)/a, 0.5*(-b - sqrtD)/a)


def calc_sphere_intersection_points(p, d, r):
  assert(len(p) == len(d))
  t = calc_sphere_intersection_params(p, d, r)
  if t is None:
    return None
  else:
    assert(len(t) == 2)
    return (tuple((pc + dc*t[0] for pc,dc in zip(p,d))), tuple((pc + dc*t[1] for pc,dc in zip(p,d))))


def clamp_to_sphere(point, radius):
  r2 = 0.0
  for coord in point:
    r2 += coord**2.0
  r2 = r2**0.5
  if r2 > radius:
    m = radius / r2
    return [m*coord for coord in point]
  else:
    return point


def vec_dot(v1, v2):
  assert(len(v1) == len(v2))
  r = 0.0
  for i in range(len(v1)):
    r += v1[i]*v2[i]
  return r


def vec_add(v1, v2):
  assert(len(v1) == len(v2))
  l = len(v1)
  r = [0.0 for i in range(l)]
  for i in range(l):
    r[i] = v1[i]+v2[i]
  return r


def vec_sub(v1, v2):
  assert(len(v1) == len(v2))
  l = len(v1)
  r = [0.0 for i in range(l)]
  for i in range(l):
    r[i] = v1[i]-v2[i]
  return r


def vec_mul(v, s):
  return [s*vv for vv in v]


def vec_copy(v):
  return [vv for vv in v]


class RelativeHeadMovementJoystick:
  posAxes_ = (codes.ABS_X, codes.ABS_Y, codes.ABS_Z)
  angleAxes_ = (codes.ABS_RX, codes.ABS_RY, codes.ABS_RZ)

  def move_axis(self, axis, value, relative):
    """Sets view angles and position.
       ABS_RX, ABS_RY and ABS_RZ are angles that represent yaw, pitch and roll angles of view ((0,0,0) is forward).
       ABS_X, ABS_Y and ABS_Z are position axes that repersent x, y and z positions of view ((0,0,0) is center).
         If relative is True, value is treated as relative amount of movement along a local axis, rotated by view angles.
         If relative is False, value is treated as absolute position along a local axis.
       This class needs to know about angles, so set them via object of this class.
       Using with curves that set absolute positions may produce unexpected and undesired results.
    """
    if self.next_ is None:
      return

    if axis in self.posAxes_:
      self.update_dirs_()

      point = None

      #Get offset in global cs
      offset = [self.next_.get_axis_value(a) for a in self.posAxes_]

      #If relative - add to current pos in global cs
      if relative == True:
        #Convert to global cs
        point = vec_mul(self.dirs_[axis], value)
        point = vec_add(point, offset)
      else:
        #Convert offset to local cs, replace the value for given axis, and convert back to global cs
        t = self.global_to_local_(offset)
        t[self.posAxes_.index(axis)] = value
        point = self.local_to_global_(t)

      #Clamp to sphere in global cs
      clamped = clamp_to_sphere(point, self.r_)
      if self.stick_ and point != clamped:
        return

      #Clamp to limits of next sink and move, both in global cs
      for a in self.posAxes_:
        limits = self.next_.get_limits(a)
        ia = self.posAxes_.index(a)
        c, o = clamped[ia], offset[ia]
        c = clamp(c, *limits)
        if relative == True:
          self.next_.move_axis(a, c-o, relative=True)
        else:
          self.next_.move_axis(a, c, relative=False)

      self.limitsDirty_ = True
    else:
      if axis in self.angleAxes_:
        self.dirsDirty_ = True
      self.next_.move_axis(axis, value, relative)


  #TODO Unused
  def move_axes(self, data):
    """Moves axes as batch."""
    angleAxes = (codes.ABS_RX, codes.ABS_RY, codes.ABS_RZ)
    for axis in angleAxes:
      for a,v in data:
        if a == axis:
          self.next_.move_axis(a, v, False)

    self.update_dirs_()

    posAxes = (codes.ABS_X, codes.ABS_Y, codes.ABS_Z)
    gp = [self.next_.get_axis_value(a) for a in posAxes]
    lp = self.global_to_local_(gp)
    for axis in posAxes:
      for a,v in data:
        if a == axis:
          lp[posAxes.index(a)] = v
    ngp = self.local_to_global_(lp)
    for a in posAxes:
      self.next_.move_axis(a, ngp[axes.index(a)], False)

    for a,v in data:
      if a not in angleAxes and a not in posAxes:
        self.next_.move_axis(a, v)


  def get_axis_value(self, axis):
    """Returns local axis value."""
    if self.next_ is None:
      return 0.0
    elif axis in self.posAxes_:
      self.update_dirs_()
      gp = [self.next_.get_axis_value(a) for a in self.posAxes_]
      l = 0.0
      d = self.dirs_[self.posAxes_.index(axis)]
      for i in range(len(gp)):
        l += gp[i]*d[i]
      return l
    else:
      return self.next_.get_axis_value(axis)


  def get_limits(self, axis):
    """Returns relative, local limits for position axes, calls next sink for other."""
    self.update_limits_()
    if self.next_ is None:
      return (0.0, 0.0)
    elif axis in self.posAxes_:
      ia = self.posAxes_.index(axis)
      return self.limits_[ia]
    else:
      return self.next_.get_limits(axis)

  def get_supported_axes(self):
    return self.next_.get_supported_axes() if self.next_ is not None else ()

  def set_button_state(self, button, state):
    self.next_.set_button_state(button, state) if self.next_ is not None else None

  def set_next(self, next):
    self.next_ = next
    self.update_dirs_()
    self.update_limits_()
    return next

  def __init__(self, next=None, r=float("inf"), stick=True):
    self.next_, self.r_, self.stick_ = next, r, stick
    self.dirs_, self.limits_ = [0.0, 0.0, 0.0], [(), (), ()]
    self.dirsDirty_, self.limitsDirty_ = True, True

  def update_dirs_(self):
    if self.dirsDirty_ == True and self.next_ is not None:
      dYaw, dPitch, dRoll = (a for a in (self.next_.get_axis_value(axis) for axis in (codes.ABS_RX, codes.ABS_RY, codes.ABS_RZ)))
      rYaw, rPitch, rRoll = (math.radians(a) for a in (dYaw, dPitch, dRoll))
      #TODO Check
      rYaw = -rYaw
      sinYaw, sinPitch, sinRoll = (math.sin(a) for a in (rYaw, rPitch, rRoll))
      cosYaw, cosPitch, cosRoll = (math.cos(a) for a in (rYaw, rPitch, rRoll))

      #x - 0, y - 1, z - 2
      self.dirs_[0] = (cosRoll*cosYaw - sinRoll*sinPitch*sinYaw, -sinRoll*cosYaw - cosRoll*sinPitch*sinYaw, -cosPitch*sinYaw)
      self.dirs_[1] = (sinRoll*cosPitch, cosRoll*cosPitch, -sinPitch)
      self.dirs_[2] = (cosRoll*sinYaw + sinRoll*sinPitch*cosYaw, -sinRoll*sinYaw + cosRoll*sinPitch*cosYaw, cosPitch*cosYaw)

      self.dirsDirty_ = False
      self.limitsDirty_ = True


  def update_limits_(self):
    if self.limitsDirty_ == True and self.next_ is not None:
      self.update_dirs_()

      #Finding points where orts intersect clamping sphere in global cs
      gp = [self.next_.get_axis_value(a) for a in self.posAxes_]
      intersections = [None for i in range(len(self.posAxes_))] 
      for ort in self.posAxes_:
        iort = self.posAxes_.index(ort)
        intersections[iort] = calc_sphere_intersection_points(gp, self.dirs_[iort], self.r_)

      #Finding limits in global cs
      limits = []
      for coord in self.posAxes_:
        icoord = self.posAxes_.index(coord)
        mn, mx = 0.0, 0.0
        for ip in intersections:
          if ip is None:
            continue
          assert(len(ip) == 2)
          for i in ip:
            assert(len(i) == len(self.posAxes_))
            v = i[icoord]
            mn, mx = min(mn, v), max(mx, v)
        limits.append((mn, mx))

      #Clamping to limits of next in global cs
      if self.next_ is not None:
        for a in self.posAxes_:
          ia = self.posAxes_.index(a)
          nextLimits = self.next_.get_limits(a)
          assert(len(nextLimits) == 2)
          assert(nextLimits[0] <= nextLimits[1])
          limits[ia] = [clamp(l, *nextLimits) for l in limits[ia]]

      #Converting limits to local cs
      gpmin, gpmax = [l[0] for l in limits], [l[1] for l in limits]
      assert(len(gpmin) == len(self.posAxes_))
      assert(len(gpmax) == len(self.posAxes_))
      lpmin, lpmax = self.global_to_local_(gpmin), self.global_to_local_(gpmax)
      for coord in self.posAxes_:
        icoord = self.posAxes_.index(coord)
        n, x = lpmin[icoord], lpmax[icoord]
        n, x = min(n, x), max(n, x)
        self.limits_[icoord] = (n, x)

      self.limitsDirty_ = False


  def global_to_local_(self, gp):
    lp = [0.0 for i in range(len(gp))]
    for a in self.posAxes_:
      ia = self.posAxes_.index(a)
      for j in range(len(self.dirs_)):
        lp[j] += gp[ia]*self.dirs_[j][ia]
    #logger.debug("global_to_local(): dirs{}; gp:{}; lp:{}".format(self.dirs_, gp, lp))
    return lp


  def local_to_global_(self, lp):
    gp = [0.0 for i in range(len(lp))]
    for a in self.posAxes_:
      ia = self.posAxes_.index(a)
      for j in range(len(self.dirs_)):
        gp[ia] += lp[ia]*self.dirs_[j][ia]
    #logger.debug("local_to_global(): dirs{}; lp:{}; gp:{}".format(self.dirs_, lp, gp))
    return gp


def make_curve_makers():
  curves = {}

  def make_config_curves(settings):
    def parseAxis(cfg, state):
      curve = get_nested_d(cfg, "curve", None)
      if curve is None:
        #TODO axis not in state anymore
        raise Exception("{}.{}.{}: Curve type not set".format(state["set"], state["mode"], state["axis"]))
      state["curve"] = curve
      return state["parser"]("curve", cfg, state)

    def parseAxes(cfg, state):
      r = {}
      for axisName,axisData in cfg.items():
        #TODO axis not in state anymore
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
          t = split_full_name2(inputSourceAndAxisName, ".", code=True)
          inputSourceAndAxisId = (t.source, t.code)
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
        #make_objects() needs "objects" list to be in state, even if it is empty
        state = {"settings" : settings, "curves" : configCurves, "parser" : settings["parser"], "objects" : []}
        make_objects(get_nested_d(config, "objects", {}), state)
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
  holdSink = clickSink.set_next(HoldSink(config.get("holdTime", 0.75), 4, False))
  settings["updated"].append(lambda tick,ts : holdSink.update(tick, ts))
  longPressSink = holdSink.set_next(HoldSink(config.get("longPressTime", 0.75), 5, True))
  settings["updated"].append(lambda tick,ts : longPressSink.update(tick, ts))
  defaultModifiers = [ (None, m) for m in
    (codes.KEY_LEFTSHIFT, codes.KEY_RIGHTSHIFT, codes.KEY_LEFTCTRL, codes.KEY_RIGHTCTRL, codes.KEY_LEFTALT, codes.KEY_RIGHTALT)
  ]
  modifiers = config.get("modifiers", None)
  modifiers = [fn2hc(m) for m in modifiers] if modifiers is not None else defaultModifiers
  modifierSink = longPressSink.set_next(ModifierSink(modifiers=modifiers, saveModifiers=False, mode=ModifierSink.OVERWRITE))

  sens = config.get("sens", None)
  if sens is not None:
    sensSet = config.get("sensSet", None)
    if sensSet not in sens:
      raise Exception("Invalid sensitivity set: {}".format(sensSet))
    sens = sens[sensSet]
    sens = {fn2hc(s[0]):s[1] for s in sens.items()}
  scaleSink = modifierSink.set_next(ScaleSink2(sens))

  makeName=lambda k : htc2fn(*k)
  sensSets = config.get("sensSets", None)
  if sensSets is not None:
    def processSensSet(sensSet):
      l =[(fn2htc(k), v) for k,v in sensSet.items()]
      l.reverse()
      return collections.OrderedDict(l)
    sensSets = [processSensSet(sensSet) for sensSet in sensSets]
  sensSetSink = scaleSink.set_next(SensSetSink(sensSets, initial=config.get("sensSetsInitial", 0), makeName=makeName))

  calibratingSink = sensSetSink.set_next(CalibratingSink(makeName=makeName))

  mainSink = calibratingSink.set_next(BindSink(cmpOp))
  stateSink = mainSink.add((), StateSink(), 1)

  class Toggler:
    def make_toggle(self):
      def op(event):
        self.sink_.set_state(not self.sink_.get_state())
        self.s_ = not self.s_
      return op
    def make_set_state(self, state):
      def op(event):
        if self.s_:
          self.sink_.set_state(state)
      return op
    def __init__(self, sink):
      self.sink_, self.s_ = sink, False

  state = None
  toggler = Toggler(stateSink)
  edParser = settings["parser"].get("ed")
  toggleKey = config.get("toggleOn", None)
  if toggleKey is not None:
    toggleKey = edParser(toggleKey, state)
    mainSink.add(toggleKey, toggler.make_toggle(), 0)

  reloadKey = config.get("reloadOn", None)
  if reloadKey is not None:
    def rld(e):
      settings["initState"] = stateSink.get_state()
      raise ReloadException()
    reloadKey = edParser(reloadKey, state)
    mainSink.add(reloadKey, rld, 0)

  toggleCalibrationKey = config.get("toggleCalibrationOn", None)
  if toggleCalibrationKey is not None:
    def toggle_calibration(e):
      calibratingSink.toggle()
    toggleCalibrationKey = edParser(toggleCalibrationKey, state)
    mainSink.add(toggleCalibrationKey, toggle_calibration, 0)

  resetCalibrationKey = config.get("resetCalibrationOn", None)
  if resetCalibrationKey is not None:
    def reset_calibration(e):
      calibratingSink.reset()
    resetCalibrationKey = edParser(resetCalibrationKey, state)
    mainSink.add(resetCalibrationKey, reset_calibration, 0)

  def set_sens_set(e):
    if e.value < 0:
      sensSetSink.set_next_set()
    else:
      sensSetSink.set_prev_set()
  sensSetsChangeAction = config.get("changeSensSetOn", None)
  if sensSetsChangeAction is not None:
    sensSetsChangeAction = edParser(sensSetsChangeAction, state)
    mainSink.add(sensSetsChangeAction, set_sens_set)

  sensSetsNextAction = config.get("nextSensSetOn", None)
  if sensSetsNextAction is not None:
    sensSetsNextAction = edParser(sensSetsNextAction, state)
    mainSink.add(sensSetsNextAction, lambda e : sensSetSink.set_next_set())

  sensSetsPrevAction = config.get("prevSensSetOn", None)
  if sensSetsPrevAction is not None:
    sensSetsPrevAction = edParser(sensSetsPrevAction, state)
    mainSink.add(sensSetsPrevAction, lambda e : sensSetSink.set_prev_set())

  sensSetsResetAction = config.get("resetSensSetOn", None)
  if sensSetsResetAction is not None:
    sensSetsResetAction = edParser(sensSetsResetAction, state)
    initialSensSet = config.get("sensSetsInitial", 0)
    mainSink.add(sensSetsResetAction, lambda e : sensSetSink.set_set(initialSensSet))

  def names2inputs(names, settings):
    r = []
    inputs = settings.get("inputs", ())
    for d in names:
      if d in inputs:
        r.append(inputs[d])
    return r

  namesOfReleased = config.get("released", ())
  released = names2inputs(namesOfReleased, settings)
  sourceFilterOp = SourceFilterOp(namesOfReleased)
  filterSink = stateSink.set_next(FilterSink(sourceFilterOp))
  namesOfReleasedStr = ", ".join(namesOfReleased)

  def print_ungrabbed(event):
    logger.info("{} ungrabbed".format(namesOfReleasedStr))
  def print_grabbed(event):
    logger.info("{} grabbed".format(namesOfReleasedStr))

  onKey = config.get("enableOn", None)
  if onKey is not None:
    onKey = edParser(onKey, state)
    mainSink.add(onKey, If(lambda : stateSink.get_state(), Call(SetState(sourceFilterOp, True), SwallowDevices(released, True),  print_grabbed)), 0)

  offKey = config.get("disableOn", None)
  if offKey is not None:
    offKey = edParser(offKey, state)
    mainSink.add(offKey, If(lambda : stateSink.get_state(), Call(SetState(sourceFilterOp, False), SwallowDevices(released, False),  print_ungrabbed)), 0)

  namesOfGrabbed = config.get("grabbed", ())
  namesOfGrabbedStr = ", ".join(namesOfGrabbed)
  grabbed = names2inputs(namesOfGrabbed, settings)

  def print_enabled(event):
    logger.info("Emulation enabled; {} grabbed".format(namesOfGrabbedStr))
  def print_disabled(event):
    logger.info("Emulation disabled; {} ungrabbed".format(namesOfGrabbedStr))

  grabSink = filterSink.set_next(BindSink(cmpOp))
  grabSink.add(ED.init(1), Call(SwallowDevices(grabbed, True), print_enabled), 0)
  grabSink.add(ED.init(0), Call(SwallowDevices(grabbed, False), print_disabled), 0)

  #axes are created on demand by get_axis_by_full_name
  #remove listeners from axes if reinitializing
  for oName, oAxes in settings.get("axes", {}).items():
    for axisId, axis in oAxes.items():
      axis.remove_all_listeners()

  grabSink.add(ED.any(), make_next(settings), 1)
  settings.setdefault("initState", config.get("initState", False))
  stateSink.set_state(settings["initState"])
  toggler.s_ = stateSink.get_state()
  logger.info("Initialization successfull")

  return clickSink


def init_log_initial(level=logging.NOTSET, handler=logging.StreamHandler(sys.stdout), fmt="%(levelname)s:%(asctime)s:%(message)s"):
  root = logging.getLogger()
  root.setLevel(level)
  handler.setLevel(logging.NOTSET)
  handler.setFormatter(logging.Formatter(fmt))
  root.addHandler(handler)


def set_log_level(settings):
  levelName = settings["config"].get("logLevel", "NOTSET").upper()
  level = name2loglevel(levelName)
  root = logging.getLogger()
  root.setLevel(level)
  print("Setting log level to {}".format(loglevel2name(level)))


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
    logger.info("Merging {}".format(configName))
    try:
      with open(configName, "r") as f:
        current = json.load(f, object_pairs_hook = lambda l : collections.OrderedDict(l))
        configs = current.get("configs", None)
        if configs is not None:
          #Including config file overwrites included
          parent = init_config(configs)
          merge_dicts(parent, current)
          current = parent
        #Next config file overwrites previous
        merge_dicts(cfg, current)
    except (KeyError, ValueError, IOError) as e:
      raise ConfigReadError(configName, e)
  return cfg


def init_config2(settings):
  if "config" in settings and not settings["reloading"]:
    return
  config = settings["options"]
  if "configNames" in settings:
    externalConfig = init_config(settings["configNames"])
    merge_dicts(externalConfig, config)
    config = externalConfig
  settings["config"] = config
  logger.info("Configs loaded successfully")


def add_scale_sink(sink, cfg):
  if "sens" in cfg:
    #cfg["sens"] is already in form {(e.source, e.code) : value}
    sensSink = ScaleSink2(get_nested(cfg, "sens"), lambda event : ((event.source, event.code), (None, event.code)))
    sensSink.set_next(sink)
    return sensSink
  else:
    return sink


def init_layout_config(settings):
  config = settings["config"]
  layoutName = get_nested(config, "layout")
  logger.info("Using '{}' layout from config".format(layoutName))
  sectNames = ["layouts", "classes"]
  cfg = get_nested_from_sections_d(config, sectNames, layoutName, None)
  if cfg is None:
    raise Exception("'{}' layout not found in config".format(layoutName))
  else:
    try:
      parser = settings["parser"]
      #make_objects() needs "objects" list to be in state, even if it is empty
      state = {"settings" : settings, "parser" : parser, "objects" : []}
      make_objects(get_nested_d(config, "objects", {}), state)
      r = parser("sink", cfg, state)
      return r
    except KeyError2 as e:
      logger.error("Error while initializing config layout '{}': cannot find key '{}' in {}".format(layoutName, e.key, e.keys))
      raise
    except KeyError as e:
      logger.error("Error while initializing config layout '{}': cannot find key '{}'".format(layoutName, str(e)))
      raise
    except Exception as e:
      logger.error("Error while initializing config layout '{}': {}".format(layoutName, e))
      raise


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


def parse_dict_live(d, cfg, state, kp, vp, update):
  for key,value in cfg.items():
    k = kp(key, state)
    if k in d and not update:
      continue
    d[k] = vp(value, state)
  return d


def parse_dict_live_ordered(d, cfg, state, kp, vp, op, update):
  items = cfg.items()
  items.sort(key=op)
  for key,value in items:
    k = kp(key, state)
    if k in d and not update:
      continue
    d[k] = vp(value, state)
  return d


class SelectParser:
  def __call__(self, key, cfg, state):
    if key not in self.parsers_:
      raise KeyError("Parser for '{}' not found, available parsers are: {}".format(key, self.parsers_.keys()))
    else:
      parser = self.parsers_[key]
      try:
        r = parser(cfg, state)
        return r
      except Exception as e:
        #logger.error("Got exception: '{}', so cannot parse key '{}', cfg '{}".format(e, key, truncate(cfg, l=50)))
        raise
      except:
        #logger.error("Unknown exception while parsing key '{}', cfg '{}'".format(key, truncate(cfg, l=50)))
        raise

  def add(self, key, parser):
    self.parsers_[key] = parser

  def get(self, key, dfault=None):
    return self.parsers_.get(key, dfault)

  def has(self, key):
    return key in self.parsers_

  def __init__(self, parsers=None):
    self.parsers_ = {} if parsers is None else parsers


class IntrusiveSelectParser:
  """FreePie does not handle inheritance well, so this class is implemented via composition."""
  def __call__(self, cfg, state):
    key = self.keyOp_(cfg)
    return self.p_(key, cfg, state)

  def add(self, key, parser):
    self.p_.add(key, parser)

  def get(self, key, dfault=None):
    return self.p_.get(key, dfault)

  def has(self, key):
    return self.p_.has(key)

  def __init__(self, keyOp, parser=None):
    self.keyOp_ = keyOp
    self.p_ = SelectParser() if parser is None else parser


class ArgObjSelectParser:
  def __call__(self, key, cfg, state):
    #logger.debug("ArgObjSelectParser.(): state[\"objects\"]: {}".format(str2(state["objects"])))
    #logger.debug("ArgObjSelectParser.(): key: {}, cfg: {}".format(str2(key), str2(cfg)))
    r = get_argobj(key, state)
    return self.p_(key, cfg, state) if r is None else r

  def add(self, key, parser):
    self.p_.add(key, parser)

  def get(self, key, dfault=None):
    return self.p_.get(key, dfault)

  def has(self, key):
    return self.p_.has(key)

  def __init__(self, parser=None):
    self.p_ = SelectParser() if parser is None else parser


def get_axis_by_full_name(fullAxisName, state):
  outputName, axisName = fn2sn(fullAxisName)
  settings = state["settings"]
  if "axes" not in settings:
    settings["axes"] = {}
  allAxes = settings["axes"]
  if outputName not in allAxes:
    #raise RuntimeError("No axes were initialized for '{}' (while parsing '{}')".format(outputName, fullAxisName))
    allAxes[outputName] = {}
  outputAxes = allAxes[outputName]
  axisId = name2code(axisName)
  axis = None
  if axisId not in outputAxes:
    #raise RuntimeError("Axis was not initialized for '{}'".format(fullAxisName))
    outputs = settings["outputs"]
    o = outputs[outputName]
    isReportingJoystick = type(o) is ReportingJoystick
    axis = o.make_axis(axisId) if isReportingJoystick else ReportingAxis(JoystickAxis(o, axisId))
    outputAxes[axisId] = axis
  else:
    axis = outputAxes[axisId]
  return axis

def make_parser():
  parser = ArgObjSelectParser()

  opParser = IntrusiveSelectParser(keyOp=lambda cfg : get_nested(cfg, "op"), parser=ArgObjSelectParser())
  parser.add("op", opParser)

  def make_symm_wrapper(wrapped, symm):
    if symm == 1:
      return lambda x : wrapped(abs(x))
    elif symm == 2:
      return lambda x : sign(x)*wrapped(abs(x))
    else:
      return wrapped

  def constant(cfg, state):
    return ConstantApproximator(get_arg(get_nested(cfg, "value"), state))
  opParser.add("constant", constant)

  def segment(cfg, state):
    def make_op(data, symmetric):
      approx = SegmentApproximator(data, 1.0, True, True)
      return make_symm_wrapper(approx, symmetric)
    return make_op(get_arg(get_nested(cfg, "points"), state), get_arg(get_nested_d(cfg, "symmetric", 0), state))
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
    return make_op(get_arg(get_nested(cfg, "coeffs"), state), get_arg(get_nested_d(cfg, "symmetric", 0), state))
  opParser.add("poly", poly)

  def bezier(cfg, state):
    def make_op(data, symmetric):
      approx = BezierApproximator(data)
      return make_symm_wrapper(approx, symmetric)
    return make_op(get_arg(get_nested(cfg, "points"), state), get_arg(get_nested_d(cfg, "symmetric", 0), state))
  opParser.add("bezier", bezier)

  def sbezier(cfg, state):
    def make_op(data, symmetric):
      approx = SegmentedBezierApproximator(data)
      return make_symm_wrapper(approx, symmetric)
    return make_op(get_arg(get_nested(cfg, "points"), state), get_arg(get_nested_d(cfg, "symmetric", 0), state))
  opParser.add("sbezier", sbezier)

  #Curves
  curveParser = IntrusiveSelectParser(keyOp=lambda cfg : get_nested(cfg, "curve"), parser=ArgObjSelectParser())
  parser.add("curve", curveParser)

  def add_curve_to_state(fullAxisName, curve, state):
      assert("curves" in state)
      axisCurves = state["curves"].setdefault(fullAxisName, [])
      axisCurves.append(curve)

  def parsePoints(cfg, state):
    """Helper"""
    pointParsers = {}
    def parseFixedPoint(cfg, state):
      p = Point(op=state["parser"]("op", cfg, state), center=get_nested_d(cfg, "center", 0.0))
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
      "dontTouch" : PointMovingCurveResetPolicy.DONT_TOUCH,
      "adjust" : PointMovingCurveResetPolicy.ADJUST
    }
    return d.get(cfg, PointMovingCurveResetPolicy.DONT_TOUCH)

  def parsePointsOutputBasedCurve(cfg, state):
    fullAxisName = get_arg(get_nested(cfg, "axis"), state)
    axis = get_axis_by_full_name(fullAxisName, state)
    points = parsePoints(get_nested(cfg, "points"), state)
    vpoName = get_nested_d(cfg, "vpo", None)
    ops = {
      "min" : get_min_op,
      "mul" : multiply_op,
      "interpolate" : interpolate_op
    }
    op = ops.get(vpoName, interpolate_op)
    vpo = SimpleValuePointOp(points.values(), op)
    class DeltaOp:
      def calc(self, x, timestamp):
        return x
      def reset(self):
        pass
    deltaOp = DeltaOp()
    curve = OutputBasedCurve(deltaOp, vpo, axis)

    if "moving" in points:
      point = points["moving"]
      pointCfg = get_nested(cfg, "points")["moving"]
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
      resetTime = pointCfg.get("resetTime", float("inf"))
      onReset = parseResetPolicy(pointCfg.get("onReset", "setToCurrent"), state)
      onMove = parseResetPolicy(pointCfg.get("onMove", "setToCurrent"), state)
      curve = PointMovingCurve(
        next=curve, point=point, getValueOp=getValueOp, centerOp=centerOp, resetDistance=resetDistance,
        onReset=onReset, onMove=onMove, resetTime=resetTime)

    axis.add_listener(curve)
    add_curve_to_state(fullAxisName, curve, state)
    return curve
  curveParser.add("pointsOut", parsePointsOutputBasedCurve)

  def parseFixedPointInputBasedCurve(cfg, state):
    fullAxisName = get_arg(get_nested(cfg, "axis"), state)
    axis = get_axis_by_full_name(fullAxisName, state)
    points = parsePoints(get_nested(cfg, "points"), state)
    fp = points["fixed"]
    interpolationDistance = get_nested_d(cfg, "interpolationDistance", 0.3)
    interpolationFactor = get_nested_d(cfg, "interpolationFactor", 1.0)
    posLimits = get_nested_d(cfg, "posLimits", (-1.1, 1.1))
    interpolateOp = FMPosInterpolateOp(fp=fp, mp=None, interpolationDistance=interpolationDistance, factor=interpolationFactor, posLimits=posLimits, eps=0.01)
    curve = InputBasedCurve(op=interpolateOp, axis=axis, posLimits=posLimits)
    axis.add_listener(curve)
    add_curve_to_state(fullAxisName, curve, state)
    return curve
  curveParser.add("fpointIn", parseFixedPointInputBasedCurve)

  def parsePointsInputBasedCurve(cfg, state):
    fullAxisName = get_arg(get_nested(cfg, "axis"), state)
    axis = get_axis_by_full_name(fullAxisName, state)
    points = parsePoints(get_nested(cfg, "points"), state)
    fp = points["fixed"]
    mp = points.get("moving", Point(op=lambda x : 0.0, center=None))
    interpolationDistance = get_nested_d(cfg, "interpolationDistance", 0.3)
    interpolationFactor = get_nested_d(cfg, "interpolationFactor", 1.0)
    resetDistance = 0.0 if "moving" not in get_nested(cfg, "points") else get_nested(cfg, "points")["moving"].get("resetDistance", 0.4)
    resetTime = float("inf") if "moving" not in get_nested(cfg, "points") else get_nested(cfg, "points")["moving"].get("resetTime", float("inf"))
    posLimits = get_nested_d(cfg, "posLimits", (-1.1, 1.1))
    interpolateOp = FMPosInterpolateOp(fp=fp, mp=mp, interpolationDistance=interpolationDistance, factor=interpolationFactor, posLimits=posLimits, eps=0.001)
    curve = InputBasedCurve(op=interpolateOp, axis=axis, posLimits=posLimits)
    def getValueOp(curve):
      return curve.get_pos()
    centerOp = IterativeCenterOp(point=mp, op=interpolateOp)
    onReset = parseResetPolicy(get_nested_d(cfg, "onReset", "setToCurrent"), state)
    onMove = parseResetPolicy(get_nested_d(cfg, "onMove", "setToCurrent"), state)
    curve = PointMovingCurve(
      next=curve, point=mp, getValueOp=getValueOp, centerOp=centerOp, resetDistance=resetDistance,
      onReset=onReset, onMove=onMove, resetTime=resetTime)
    axis.add_listener(curve)
    add_curve_to_state(fullAxisName, curve, state)
    return curve
  curveParser.add("pointsIn", parsePointsInputBasedCurve)

  def parseOutputDeltaLinkingCurve(cfg, state):
    fullControlledAxisName = get_arg(get_nested(cfg, "axis"), state)
    controlledAxis = get_axis_by_full_name(fullControlledAxisName, state)
    sensOp = state["parser"]("op", cfg, state)
    deltaOp = lambda delta, sens : delta*sens
    fullControllingAxisName = get_arg(get_nested(cfg, "controlling"), state)
    controllingAxis = get_axis_by_full_name(fullControllingAxisName, state)
    radius = get_nested_d(cfg, "radius", float("inf"))
    curve = OutputDeltaLinkingCurve(controllingAxis, controlledAxis, sensOp, deltaOp, radius)
    controlledAxis.add_listener(curve)
    controllingAxis.add_listener(curve)
    add_curve_to_state(fullControlledAxisName, curve, state)
    add_curve_to_state(fullControllingAxisName, curve, state)
    return curve
  curveParser.add("outDeltaLink", parseOutputDeltaLinkingCurve)

  def parseInputDeltaLinkingCurve(cfg, state):
    fullControlledAxisName = get_arg(get_nested(cfg, "axis"), state)
    controlledAxis = get_axis_by_full_name(fullControlledAxisName, state)
    op = state["parser"]("op", cfg, state)
    fullControllingAxisName = get_arg(get_nested(cfg, "controlling"), state)
    controllingAxis = get_axis_by_full_name(fullControllingAxisName, state)
    radius = get_nested_d(cfg, "radius", float("inf"))
    threshold = get_nested_d(cfg, "threshold", 0.0)
    threshold = None if threshold == "none" else float(threshold)
    curve = InputDeltaLinkingCurve(controllingAxis, controlledAxis, op, radius, threshold)
    controlledAxis.add_listener(curve)
    controllingAxis.add_listener(curve)
    add_curve_to_state(fullControlledAxisName, curve, state)
    add_curve_to_state(fullControllingAxisName, curve, state)
    return curve
  curveParser.add("inDeltaLink", parseInputDeltaLinkingCurve)

  def parseInputLinkingCurve(cfg, state):
    fullControlledAxisName = get_arg(get_nested(cfg, "axis"), state)
    controlledAxis = get_axis_by_full_name(fullControlledAxisName, state)
    op = state["parser"]("op", cfg, state)
    fullControllingAxisName = get_arg(get_nested(cfg, "controlling"), state)
    controllingAxis = get_axis_by_full_name(fullControllingAxisName, state)
    curve = InputLinkingCurve(controllingAxis, controlledAxis, op)
    controlledAxis.add_listener(curve)
    controllingAxis.add_listener(curve)
    add_curve_to_state(fullControlledAxisName, curve, state)
    add_curve_to_state(fullControllingAxisName, curve, state)
    return curve
  curveParser.add("inLink", parseInputLinkingCurve)

  def parseAxisLinker(cfg, state):
    fullControlledAxisName = get_arg(get_nested(cfg, "follower"), state)
    controlledAxis = get_axis_by_full_name(fullControlledAxisName, state)
    op = state["parser"]("op", cfg, state)
    fullControllingAxisName = get_arg(get_nested(cfg, "leader"), state)
    controllingAxis = get_axis_by_full_name(fullControllingAxisName, state)
    linker = AxisLinker(controllingAxis, controlledAxis, op)
    controlledAxis.add_listener(linker)
    controllingAxis.add_listener(linker)
    #FIXME Since there is no "axis" property in config node, it does not get added to state["curves"]
    add_curve_to_state(fullControlledAxisName, linker, state)
    add_curve_to_state(fullControllingAxisName, linker, state)
    return linker
  curveParser.add("linker", parseAxisLinker)

  def makeRefDeltaOp(cfg, state, sensOp):
    if "refFixed" not in cfg:
      return sensOp
    else:
      refAxis = get_axis_by_full_name(get_nested(cfg, "refAxis"), state)
      refApprox = state["parser"]("op", get_nested(cfg, "refFixed"), state)
      class RefDeltaOp:
        def calc(self, x, timestamp):
          return self.combine_(self.next_.calc(x, timestamp), self.approx_(self.axis_.get()))
        def reset(self):
          self.next_.reset()
        def __init__(self, combine, next, approx, axis):
          self.next_, self.combine_, self.approx_, self.axis_ = next, combine, approx, axis
      return RefDeltaOp(lambda a,b: a*b, sensOp, refApprox, refAxis)

  def makeIterativeInputOp(cfg, outputOp):
    inputOp = IterativeInputOp(outputOp=outputOp, eps=get_nested_d(cfg, "eps", 0.001), numSteps=get_nested_d(cfg, "numSteps", 100))
    inputStep = get_nested_d(cfg, "inputStep", 0.1)
    inputOp = LookupOp(inputOp, outputOp, inputStep)
    return inputOp

  def parseCombinedCurve(cfg, state):
    fullAxisName = get_arg(get_nested(cfg, "axis"), state)
    axis = get_axis_by_full_name(fullAxisName, state)
    movingCfg = get_nested(cfg, "moving")
    signDDOp = SignDistanceDeltaOp()
    timeDDOp = TimeDistanceDeltaOp(resetTime=movingCfg.get("resetTime", float("inf")), holdTime=movingCfg.get("holdTime", 0.0))
    deltaOp = CombineDeltaOp(
      combine=lambda x,s : x*s,
      ops=(XDeltaOp(), AccumulateDeltaOp(state["parser"]("op", movingCfg, state), ops=[signDDOp, timeDDOp]))
    )
    deltaOp = makeRefDeltaOp(cfg, state, deltaOp)
    deltaOp = DeadzoneDeltaOp(deltaOp, get_nested_d(cfg, "deadzone", 0.0))
    sensOp = ApproxOp(approx=state["parser"]("op", get_nested(cfg, "fixed"), state))
    curve = OutputBasedCurve(deltaOp=deltaOp, valueOp=sensOp, axis=axis)
    add_curve_to_state(fullAxisName, curve, state)
    return curve
  curveParser.add("combined", parseCombinedCurve)

  def parseInputBasedCurve2(cfg, state):
    fullAxisName = get_arg(get_nested(cfg, "axis"), state)
    axis = get_axis_by_full_name(fullAxisName, state)
    movingCfg = get_nested(cfg, "moving")
    signDDOp = SignDistanceDeltaOp()
    timeDDOp = TimeDistanceDeltaOp(resetTime=movingCfg.get("resetTime", float("inf")), holdTime=movingCfg.get("holdTime", 0.0))
    deltaOp = CombineDeltaOp(
      combine=lambda x,s : x*s,
      ops=(XDeltaOp(), AccumulateDeltaOp(state["parser"]("op", movingCfg, state), ops=[signDDOp, timeDDOp]))
    )
    outputOp = ApproxOp(approx=state["parser"]("op", get_nested(cfg, "fixed"), state))
    inputOp = makeIterativeInputOp(cfg, outputOp)
    #TODO Add ref axis like in parseCombinedCurve() ? Will need to implement special op.
    cb = None
    if get_nested_d(cfg, "print", 0) == 1:
      cb = InputBasedCurve2PrintCB(fullAxisName, get_nested_d(cfg, "deltaOrder", 3), get_nested_d(cfg, "ivOrder", 3), get_nested_d(cfg, "ovOrder", 3))
    deltaOp = makeRefDeltaOp(cfg, state, deltaOp)
    deltaOp = DeadzoneDeltaOp(deltaOp, get_nested_d(cfg, "deadzone", 0.0))
    resetOpsOnAxisMove = get_nested_d(cfg, "resetOpsOnAxisMove", True)
    ivLimits = get_nested_d(cfg, "inputLimits", (-1.0, 1.0))
    curve = InputBasedCurve2(axis=axis, inputOp=inputOp, outputOp=outputOp, deltaOp=deltaOp, inputValueLimits=ivLimits, cb=cb, resetOpsOnAxisMove=resetOpsOnAxisMove)
    axis.add_listener(curve)
    add_curve_to_state(fullAxisName, curve, state)
    return curve
  curveParser.add("input2", parseInputBasedCurve2)

  def parseOffsetCurve(cfg, state):
    fmax = 1000000.0
    #axis tracker
    resetOnAxisMove = get_nested_d(cfg, "resetOnAxisMove", True)
    top = AxisTrackerRelChainCurve(next=None, resetOnAxisMove=resetOnAxisMove)
    curve = top
    fullAxisName = get_arg(get_nested(cfg, "axis"), state)
    axis = get_axis_by_full_name(fullAxisName, state)
    axis.add_listener(curve)
    #print
    if get_arg(get_nested_d(cfg, "print", False), state) == True:
      printCurve = PrintRelChainCurve(None, axis, fullAxisName, get_nested_d(cfg, "avOrder", 3))
      top.set_next(printCurve)
      curve = printCurve
    #accumulate
    #Order of ops should not matter
    movingCfg = get_nested(cfg, "moving")
    valueDDOp = SignDistanceDeltaOp()
    valueDDOp = TimeDistanceDeltaOp(next=valueDDOp, resetTime=movingCfg.get("resetTime", float("inf")), holdTime=movingCfg.get("holdTime", 0.0))
    deltaDOp = XDeltaOp()
    deltaDOp = DeadzoneDeltaOp(deltaDOp, movingCfg.get("deadzone", 0.0))
    deltaDOp = makeRefDeltaOp(movingCfg, state, deltaDOp)
    combine = lambda a,b: a+b
    class ResetOp:
      def calc(self, value):
        return value
      def reset(self):
        pass
    inputOp = ResetOp()
    accumulateChainCurve = AccumulateRelChainCurve(next=None, valueDDOp=valueDDOp, deltaDOp=deltaDOp, combine=combine, inputOp=inputOp)
    curve.set_next(accumulateChainCurve)
    #transform accumulated
    movingOutputOp = ApproxOp(approx=state["parser"]("op", movingCfg, state))
    movingInputOp = makeIterativeInputOp(cfg, movingOutputOp)
    movingChainCurve = TransformAbsChainCurve(next=None, inputOp=movingInputOp, outputOp=movingOutputOp)
    accumulateChainCurve.set_next(movingChainCurve)
    #offset transformed
    offsetChainCurve = OffsetAbsChainCurve(next=None)
    movingChainCurve.set_next(offsetChainCurve)
    #transform offset
    fixedCfg = get_nested(cfg, "fixed")
    fixedOutputOp = ApproxOp(approx=state["parser"]("op", fixedCfg, state))
    fixedInputOp = makeIterativeInputOp(cfg, fixedOutputOp)
    fixedChainCurve = TransformAbsChainCurve(next=None, inputOp=fixedInputOp, outputOp=fixedOutputOp)
    offsetChainCurve.set_next(fixedChainCurve)
    #move axis
    axisChainCurve = AxisAbsChainCurve(axis=axis)
    fixedChainCurve.set_next(axisChainCurve)
    add_curve_to_state(fullAxisName, curve, state)
    return top
  curveParser.add("offset", parseOffsetCurve)

  def parsePresetCurve(cfg, state):
    config = state["settings"]["config"]
    presetName = get_arg(get_nested_d(cfg, "name", None), state)
    if presetName is None:
      raise RuntimeError("Preset name was not specified")
    presetCfg = get_nested_from_sections_d(config, ("presets", "classes"), presetName, None)
    if presetCfg is None:
      raise RuntimeError("Preset '{}' does not exist; available presets are: '{}'".format(presetName, [k.encode("utf-8") for k in presets.keys()]))
    #creating curve
    if "args" in cfg:
      push_args(get_nested_d(cfg, "args", {}), state)
      try:
        #logger.debug("{} -> {}".format(get_nested(cfg, "args"), args))
        return state["parser"]("curve", presetCfg, state)
      finally:
        pop_args(state)
    else:
      presetCfgStack = CfgStack(presetCfg)
      try:
        for n in ("axis", "controlling", "leader", "follower", "print"):
          if n in cfg:
            presetCfgStack.push(n, cfg[n])
        curve = state["parser"]("curve", presetCfg, state)
        return curve
      finally:
        presetCfgStack.pop_all()
  curveParser.add("preset", parsePresetCurve)

  def parseNoopCurve(cfg, state):
    fullAxisName = get_arg(get_nested(cfg, "axis"), state)
    #To init state
    get_axis_by_full_name(fullAxisName, state)
    curve = NoopCurve(value=get_arg(get_nested_d(cfg, "value", 0.0), state))
    add_curve_to_state(fullAxisName, curve, state)
    return curve
  curveParser.add("noop", parseNoopCurve)

  def parseBasesDecorator(wrapped):
    def worker(cfg, state):
      """Merges all base config definitions if they are specified."""
      bases = get_nested_d(cfg, "bases", None)
      if bases is None:
        return cfg
      else:
        sectNames = ["layouts", "classes"]
        config = state["settings"]["config"]
        full = {}
        for baseName in bases:
          logger.debug("Parsing base : {}".format(baseName))
          base = get_nested_from_sections_d(config, sectNames, baseName, None)
          if base is None:
            raise RuntimeError("No layout: {}".format(str2(base)))
          merge_dicts(full, worker(base, state))
        merge_dicts(full, cfg)
        del full["bases"]
        return full
    def parseBasesOp(cfg, state):
      expandedCfg = worker(cfg, state)
      #logger.debug("parseBasesOp():\n{}\n->\n{}".format(str2(cfg), str2(expandedCfg)))
      return wrapped(expandedCfg, state)
    return parseBasesOp

  def parseArgObjDecorator(wrapped):
    def parseArgObjOp(cfg, state):
      obj = get_argobj(cfg, state)
      if obj is not None:
        return obj
      else:
        return wrapped(cfg, state)
    return parseArgObjOp

  def parsePredefinedDecorator(names):
    def decorator(wrapped):
      def op(cfg, state):
        r = None
        for name in names:
          if name in cfg or get_nested_d(cfg, "type", "") == name:
            r = state["parser"](name, cfg, state)
            if r is not None:
              return r
        return wrapped(cfg, state)
      return op
    return decorator

  def parseExternal(propName, groupNames):
    @parseArgObjDecorator
    def parseExternalOp(cfg, state):
      config = state["settings"]["config"]
      name = cfg.get(propName, None)
      if name is None:
        name = get_nested(cfg, "name")
      logger.debug("Parsing {} '{}'".format(propName, name))
      cfg2 = get_nested_from_sections_d(config, groupNames, name, None)
      if cfg2 is None:
        raise RuntimeError("No class {}".format(str2(name)))
      push_args(get_nested_d(cfg, "args", {}), state)
      try:
        return state["parser"]("sink", cfg2, state)
      finally:
        pop_args(state)
    return parseExternalOp

  def sinkParserKeyOp(cfg):
    names = ["layout", "class"]
    if type(cfg) in (dict, collections.OrderedDict):
      for name in names:
        if name in cfg or get_nested_d(cfg, "type", "") == name:
          return name
    return "sink"

  sinkParser = IntrusiveSelectParser(keyOp=sinkParserKeyOp)
  parser.add("sink", sinkParser)
  sinkParser.add("layout", parseExternal("layout", ["layouts", "classes"]))
  sinkParser.add("class", parseExternal("class", ["classes", "layouts"]))

  class HeadSink:
    def __call__(self, event):
      #Can be actually called during init when next_ is not set yet
      if self.next_ is None:
        logger.debug("{}: next sink is not set".format(self))
      else:
        self.next_(event)

    def set_next(self, next):
        self.next_ = next

    def __init__(self, next=None):
        self.next_ = next

  @parseArgObjDecorator
  @parseBasesDecorator
  def parseSink(cfg, state):
    """Assembles sink components in certain order."""
    parser = state["parser"].get("sc")
    oldComponents = state.get("components", None)
    state["components"] = {}
    push_args(get_nested_d(cfg, "args", {}), state)
    oldCurves = state.get("curves", None)
    state["curves"] = {}
    make_objects(get_nested_d(cfg, "objects", {}), state)
    #logger.debug("parseSink(): state[\"objects\"]: {}".format(str2(state["objects"])))
    #Since python 2.7 does not support nonlocal variables, declaring 'sink' as list to allow parse_component() modify it
    sink = [None]
    def parse_component(name, op=None):
      if name in cfg:
        t = parser(name, cfg, state)
        if t is not None:
          state["components"][name] = t
          if op is not None:
            op(sink[0], t)
          sink[0] = t
    #TODO Currently unused. Remove?
    def make_action_wrapper(nextSink, actionSink):
      def op(event):
        assert(actionSink is not None)
        r = actionSink(event)
        if not r and nextSink is not None:
          r = nextSink(event)
        return r
      return op
    def set_next(next, sink):
      if next is not None:
        sink.set_next(next)
    def add(next, sink):
      if next is not None:
        #Next sink is added to level 0 so it will be able to process events that were processed by other binds.
        #This is useful in case like when a bind and a mode both need to process some axis event.
        sink.add(ED.any(), next, 0)
    try:
      #TODO Refactor
      if len(cfg) == 0:
        def noop(event):
          return False
        return noop
      try:
        headSink = HeadSink()
        state.setdefault("sinks", [])
        state["sinks"].append(headSink)
        if "modes" in cfg and "next" in cfg:
          raise RuntimeError("'next' and 'modes' components are mutually exclusive")
        parse_component("next", None)
        parse_component("modes", None)
        parse_component("state", set_next)
        #TODO Split: construct bind sink here and bindings after all other components
        parse_component("binds", add)
        #TODO rename to "action" and update configs
        #parse_component("type", make_action_wrapper)
        parse_component("sens", set_next)
        parse_component("modifiers", set_next)
        if sink[0] is None:
          logger.debug("Could not make sink out of '{}'".format(cfg))
          return None
        else:
          headSink.set_next(sink[0])
          return headSink
      finally:
        state["sinks"].pop()
    finally:
      if oldComponents is not None:
        state["components"] = oldComponents
      pop_args(state)
      objects = state["objects"]
      assert len(objects) != 0
      objects.pop()
      if oldCurves is not None:
        state["curves"] = oldCurves
  sinkParser.add("sink", parseSink)

  #Sink components
  scParser = SelectParser()
  parser.add("sc", scParser)

  def parseModifiers(cfg, state):
    modifiers = [fn2hc(m) for m in get_nested(cfg, "modifiers")]
    modifierSink = ModifierSink(next=None, modifiers=modifiers, saveModifiers=True, mode=ModifierSink.APPEND)
    #saves event modifiers (if present), sets new modifers and restores old ones after call if needed
    class Wrapper:
      def __call__(self, event):
        self.sink_(event)
        if event.type == codes.EV_BCT and event.code == codes.BCT_INIT and event.value == 0:
          self.sink_.clear()
      def set_next(self, next):
        self.sink_.set_next(next)
      def __init__(self, sink):
        self.sink_ = sink
    return Wrapper(modifierSink)
  scParser.add("modifiers", parseModifiers)

  def parseSens(cfg, state):
    sens = {fn2hc(fullAxisName):value for fullAxisName,value in get_nested(cfg, "sens").items()}
    keyOp = lambda event : ((event.source, event.code), (None, event.code))
    scaleSink = ScaleSink2(sens, keyOp)
    class Wrapper:
      def __call__(self, event):
        oldValue = event.value
        try:
          self.sink_(event)
        finally:
          event.value = oldValue
      def set_next(self, next):
        self.sink_.set_next(next)
      def __init__(self, sink):
        self.sink_ = sink
    return Wrapper(scaleSink)
  scParser.add("sens", parseSens)

  @parseBasesDecorator
  def parseMode(cfg, state):
    name=get_nested_d(cfg, "name", "")
    modeSink = ModeSink(name)
    for modeName,modeCfg in get_arg(get_nested(cfg, "modes"), state).items():
      logger.debug("{}: parsing mode:".format(name, modeName))
      child = state["parser"]("sink", modeCfg, state)
      modeSink.add(modeName, child)
    initialMode = get_arg(get_nested_d(cfg, "initialMode", None), state)
    if initialMode is not None:
      if not modeSink.set_mode(initialMode):
        logger.warning("Cannot set mode: {}".format(initialMode))
    msmm = ModeSinkModeManager(modeSink)
    msmm.save()
    state["components"]["msmm"] = msmm
    return modeSink
  scParser.add("modes", parseMode)

  def parseState(cfg, state):
    sink = StateSink()
    stateCfg = get_nested(cfg, "state")
    if "next" in stateCfg:
      next = state["parser"]("sink", stateCfg["next"], state)
      sink.set_next(next)
    if "initialState" in stateCfg:
      sink.set_state(stateCfg["initialState"])
    return sink
  scParser.add("state", parseState)

  def parseNext(cfg, state):
    parser = state["parser"]
    r = parser("sink", get_nested(cfg, "next"), state)
    if r is None:
      logger.debug("Sink parser could not parse '{}', so trying action parser".format(cfg))
      r = parser("action", get_nested(cfg, "next"), state)
    return r
  scParser.add("next", parseNext)

  #Actions
  #TODO Rename "type" to "action" and update configs
  actionParser = IntrusiveSelectParser(keyOp=lambda cfg : get_nested_d(cfg, "action", get_nested_d(cfg, "type")))
  parser.add("action", actionParser)

  actionParser.add("saveMode", lambda cfg, state : state["components"]["msmm"].make_save())
  actionParser.add("restoreMode", lambda cfg, state : state["components"]["msmm"].make_restore())
  actionParser.add("addMode", lambda cfg, state : state["components"]["msmm"].make_add(get_nested(cfg, "mode"), get_nested_d(cfg, "current")))
  actionParser.add("removeMode", lambda cfg, state : state["components"]["msmm"].make_remove(get_nested(cfg, "mode"), get_nested_d(cfg, "current")))
  actionParser.add("swapMode", lambda cfg, state : state["components"]["msmm"].make_swap(get_nested(cfg, "f"), get_nested(cfg, "t"), get_nested_d(cfg, "current")))
  actionParser.add("cycleSwapMode", lambda cfg, state : state["components"]["msmm"].make_cycle_swap(get_nested(cfg, "modes"), get_nested_d(cfg, "current")))
  actionParser.add("clearMode", lambda cfg, state : state["components"]["msmm"].make_clear())
  actionParser.add("setMode", lambda cfg, state : state["components"]["msmm"].make_set(get_nested(cfg, "mode"), nameToMSMMSavePolicy(get_nested_d(cfg, "savePolicy", "noop"))))
  actionParser.add("cycleMode", lambda cfg, state : state["components"]["msmm"].make_cycle(get_nested(cfg, "modes"), get_nested_d(cfg, "step", 1), get_nested_d(cfg, "loop", True), nameToMSMMSavePolicy(get_nested_d(cfg, "savePolicy", "noop"))))

  def parseSetState(cfg, state):
    s = get_nested(cfg, "state")
    #logger.debug("Components: {}".format(state["components"]))
    return SetState(state["components"]["state"], s)
  actionParser.add("setState", parseSetState)

  def parseToggleState(cfg, state):
    #logger.debug("Components: {}".format(state["components"]))
    return ToggleState(state["components"]["state"])
  actionParser.add("toggleState", parseToggleState)

  def parseMove(cfg, state):
    curve = state["parser"]("curve", cfg, state)
    return MoveCurve(curve)
  actionParser.add("move", parseMove)

  def parseMoveOneOf(cfg, state):
    axesData = get_nested(cfg, "axes")
    curves = {}
    for fullInputAxisName,curveCfg in axesData.items():
      curve = state["parser"]("curve", curveCfg, state)
      curves[fn2hc(get_arg(fullInputAxisName, state))] = curve
    op = None
    if get_nested(cfg, "op") == "min":
      op = MCSCmpOp(cmp = lambda new,old : new < old)
    elif get_nested(cfg, "op") == "max":
      op = MCSCmpOp(cmp = lambda new,old : new > old)
    elif get_nested(cfg, "op") == "thresholds":
      op = MCSThresholdOp(thresholds = {fn2hc(get_arg(fullInputAxisName, state)):get_arg(threshold, state) for fullInputAxisName,threshold in get_nested(cfg, "thresholds").items()})
    else:
      raise Exception("parseMoveOneOf(): Unknown op: {}".format(get_nested(cfg, "op")))
    mcs = MultiCurveSink(curves, op)
    state["settings"]["updated"].append(lambda tick,ts : mcs.update(tick, ts))
    return mcs
  actionParser.add("moveOneOf", parseMoveOneOf)

  def parseSetAxis(cfg, state):
    axis = get_axis_by_full_name(get_arg(get_nested(cfg, "axis"), state), state)
    value = float(get_arg(get_nested(cfg, "value"), state))
    r = MoveAxis(axis, value, False)
    return r
  actionParser.add("setAxis", parseSetAxis)

  def parseSetAxes(cfg, state):
    allAxes = state["settings"]["axes"]
    axesAndValues = get_nested(cfg, "axesAndValues")
    #logger.debug("parseSetAxes(): {}".format(axesAndValues))
    if type(axesAndValues) in (dict, collections.OrderedDict):
      axesAndValues = axesAndValues.items()
    assert(type(axesAndValues) is list)
    #logger.debug("parseSetAxes(): {}".format(axesAndValues))
    av = []
    for fullAxisName,value in axesAndValues:
      axis = get_axis_by_full_name(get_arg(fullAxisName, state), state)
      value = float(get_arg(value, state))
      av.append([axis, value, False])
      #logger.debug("parseSetAxes(): {}, {}, {}".format(fullAxisName, axis, value))
    #logger.debug("parseSetAxes(): {}".format(av))
    r = MoveAxes(av)
    return r
  actionParser.add("setAxes", parseSetAxes)

  def parseSetAxesRel(cfg, state):
    allAxes = state["settings"]["axes"]
    axesAndValues = get_nested(cfg, "axesAndValues")
    if type(axesAndValues) in (dict, collections.OrderedDict):
      axesAndValues = axesAndValues.items()
    av = []
    for fullAxisName,value in axesAndValues:
      axis = get_axis_by_full_name(get_arg(fullAxisName, state), state)
      value = float(get_arg(value, state))
      av.append([axis, value, True])
    r = MoveAxes(av)
    return r
  actionParser.add("setAxesRel", parseSetAxesRel)

  def parseSetKeyState_(cfg, state, s):
    output, key = fn2sn(get_arg(get_nested(cfg, "key"), state))
    output = state["settings"]["outputs"][output]
    key = name2code(key)
    return SetButtonState(output, key, s)

  def parseSetKeyState(cfg, state):
    s = int(get_arg(get_nested(cfg, "state"), state))
    return parseSetKeyState_(cfg, state, s)
  actionParser.add("setKeyState", parseSetKeyState)

  def parsePress(cfg, state):
    return parseSetKeyState_(cfg, state, 1)
  actionParser.add("press", parsePress)

  def parseRelease(cfg, state):
    return parseSetKeyState_(cfg, state, 0)
  actionParser.add("release", parseRelease)

  def parseClick(cfg, state):
    output, key = fn2sn(get_arg(get_nested(cfg, "key"), state))
    output = state["settings"]["outputs"][output]
    key = name2code(key)
    n = int(get_arg(get_nested_d(cfg, "numClicks", 1), state))
    def op(event):
      for i in range(n):
        for s in (1, 0):
          output.set_button_state(key, s)
    return op
  actionParser.add("click", parseClick)

  actionParser.add("setKeyState", parseSetKeyState)

  def parseResetCurves(cfg, state):
    curvesToReset = []
    allCurves = state.get("curves")
    assert(allCurves is not None)
    if "axes" in cfg:
      for fullAxisName in get_nested(cfg, "axes"):
        curves = allCurves.get(get_arg(fullAxisName, state), None)
        if curves is None:
          logger.warning("No curves were initialized for '{}' axis (encountered when parsing '{}')".format(fullAxisName, str2(cfg)))
        else:
          curvesToReset += curves
    elif "objects" in cfg:
      objects = state["objects"]
      for objectName in get_nested(cfg, "objects"):
        curve = get_nested_from_stack_d(objects, objectName, None)
        if curve is None:
          raise RuntimeError("Curve {} not found".format(str2(objectName)))
        curvesToReset.append(curve)
    else:
      raise RuntimeError("Must specify either 'axes' or 'objects' in {}".format(str2(cfg)))
    return ResetCurves(curvesToReset)
  actionParser.add("resetCurves", parseResetCurves)

  def createSnap_(cfg, state):
    state.setdefault("snapManager", AxisSnapManager())
    snapManager = state["snapManager"]
    state.setdefault("snapTracker", SnapTracker(snapManager))
    snapName = get_nested(cfg, "snap")
    if not snapManager.has_snap(snapName):
      snaps = state["settings"]["config"]["snaps"]
      fullAxesNamesAndValues = snaps[snapName]
      snap = []
      for fullAxisName,value in fullAxesNamesAndValues.items():
        axis = get_axis_by_full_name(fullAxisName, state)
        snap.append((axis, value))
      snapManager.set_snap(snapName, snap)

  def parseUpdateSnap(cfg, state):
    createSnap_(cfg, state)
    snapName = get_nested(cfg, "snap")
    snapManager = state["snapManager"]
    return UpdateSnap(snapManager, snapName)
  actionParser.add("updateSnap", parseUpdateSnap)

  def parseSnapTo(cfg, state):
    createSnap_(cfg, state)
    snapName = get_nested(cfg, "snap")
    snapManager = state["snapManager"]
    return SnapTo(snapManager, snapName)
  actionParser.add("snapTo", parseSnapTo)

  def parseIncSnapCount(cfg, state):
    createSnap_(cfg, state)
    snapName = get_nested(cfg, "snap")
    snapTracker = state["snapTracker"]
    return lambda e : snapTracker.inc(snapName)
  actionParser.add("incSnapCount", parseIncSnapCount)

  def parseDecSnapCount(cfg, state):
    createSnap_(cfg, state)
    snapName = get_nested(cfg, "snap")
    snapTracker = state["snapTracker"]
    return lambda e : snapTracker.dec(snapName)
  actionParser.add("decSnapCount", parseDecSnapCount)

  def parseResetSnapCount(cfg, state):
    createSnap_(cfg, state)
    snapName = get_nested(cfg, "snap")
    snapTracker = state["snapTracker"]
    return lambda e : snapTracker.reset(snapName)
  actionParser.add("resetSnapCount", parseResetSnapCount)

  def parseSetStateOnInit(cfg, state):
    linker = state["parser"]("curve", cfg, state)
    return SetAxisLinkerState(linker)
  actionParser.add("setStateOnInit", parseSetStateOnInit)

  def parseSetObjectState(cfg, state):
    obj = get_object(get_nested(cfg, "object"), state)
    return SetState(obj, get_nested(cfg, "state"))
  actionParser.add("setObjectState", parseSetObjectState)

  def parseEmitCustomEvent(cfg, state):
    sinks, code, value = state.get("sinks"), int(get_nested_d(cfg, "code", 0)), get_nested_d(cfg, "value")
    if sinks is None or len(sinks) == 0:
      raise RuntimeError("Not in a sink while parsing '{}'".format(cfg))
    sink = None
    if "object" in cfg:
      sink = get_object(get_nested(cfg, "object"), state)
    else:
      #depth == 0 - current component sink, depth == 1 - its parent
      sink = sinks[-(1+get_nested_d(cfg, "depth", 0))]
    if sink is None:
      raise RuntimeError("Sink is None, encountered while parsing '{}'".format(cfg))
    def callback(e):
      event = Event(codes.EV_CUSTOM, code, value)
      sink(event)
      return True
    return callback
  actionParser.add("emit", parseEmitCustomEvent)

  def parsePrint(cfg, state):
    message = get_nested(cfg, "message")
    def callback(e):
      print message
      return True
    return callback
  actionParser.add("print", parsePrint)

  def parsePrintEvent(cfg, state):
    def callback(e):
      print e
      return True
    return callback
  actionParser.add("printEvent", parsePrintEvent)

  #Event descriptors
  edParser = IntrusiveSelectParser(keyOp=lambda cfg : get_nested(cfg, "type"))
  parser.add("ed", edParser)

  def parseEdModifiers_(r, cfg, state):
    """Helper"""
    if "modifiers" in cfg:
      modifiers = [parse_modifier_desc(get_arg(m, state)) for m in get_arg(get_nested(cfg, "modifiers"), state)]
      r.append(("modifiers", ModifiersPropTest(modifiers)))
    return r

  def parseKey_(cfg, state, value):
    """Helper"""
    sourceHash, eventType, key = fn2htc(get_arg(get_nested(cfg, "key"), state))
    r = [("type", EqPropTest(eventType)), ("code", EqPropTest(key)), ("value", EqPropTest(value))]
    if sourceHash is not None:
      r.append(("source", EqPropTest(sourceHash)))
    return r

  def parseAny(cfg, state):
    return parseEdModifiers_([], cfg, state)
  edParser.add("any", parseAny)

  def parsePress(cfg, state):
    return parseEdModifiers_(parseKey_(cfg, state, 1), cfg, state)
  edParser.add("press", parsePress)

  def parseRelease(cfg, state):
    return parseEdModifiers_(parseKey_(cfg, state, 0), cfg, state)
  edParser.add("release", parseRelease)

  def parseClick(cfg, state):
    r = parseKey_(cfg, state, 3)
    r.append(("num_clicks", EqPropTest(1)))
    r = parseEdModifiers_(r, cfg, state)
    return r
  edParser.add("click", parseClick)

  def parseDoubleClick(cfg, state):
    r = parseKey_(cfg, state, 3)
    r.append(("num_clicks", EqPropTest(2)))
    r = parseEdModifiers_(r, cfg, state)
    return r
  edParser.add("doubleclick", parseDoubleClick)

  def parseMultiClick(cfg, state):
    r = parseKey_(cfg, state, 3)
    num = int(get_nested(cfg, "numClicks"))
    r.append(("num_clicks", EqPropTest(num)))
    r = parseEdModifiers_(r, cfg, state)
    return r
  edParser.add("multiclick", parseMultiClick)

  def parseHold(cfg, state):
    r = parseKey_(cfg, state, 4)
    r = parseEdModifiers_(r, cfg, state)
    return r
  edParser.add("hold", parseHold)

  def parseLongPress(cfg, state):
    r = parseKey_(cfg, state, 5)
    r = parseEdModifiers_(r, cfg, state)
    return r
  edParser.add("longPress", parseLongPress)

  def parseMove(cfg, state):
    sourceHash, eventType, axis = fn2htc(get_arg(get_nested(cfg, "axis"), state))
    r = [("type", EqPropTest(eventType)), ("code", EqPropTest(axis))]
    if sourceHash is not None:
      r.append(("source", EqPropTest(sourceHash)))
    value = get_nested_d(cfg, "value")
    if value is not None:
      op = None
      if value == "+":
        op = lambda eventValue, attrValue : cmp(eventValue, attrValue) > 0
        value = 0.0
      elif value == "-":
        op = lambda eventValue, attrValue : cmp(eventValue, attrValue) < 0
        value = 0.0
      else:
        op = lambda eventValue, attrValue : cmp(eventValue, attrValue) == 0
        value = float(value)
      r.append(("value", CmpPropTest(value, op)))
    r = parseEdModifiers_(r, cfg, state)
    return r
  edParser.add("move", parseMove)

  def parseInit(cfg, state):
    r = [("type", EqPropTest(codes.EV_BCT)), ("code", EqPropTest(codes.BCT_INIT))]
    eventName = get_nested_d(cfg, "event")
    if eventName is not None:
      value = 1 if eventName == "enter" else 0 if eventName == "leave" else None
      assert(value is not None)
      r.append(("value", EqPropTest(value)))
    return r
  edParser.add("init", parseInit)

  def parseEvent(cfg, state):
    code, value = get_nested(cfg, "code"), get_nested(cfg, "value")
    r = [("type", EqPropTest(codes.EV_CUSTOM)), ("code", EqPropTest(code)), ("value", EqPropTest(value))]
    return r
  edParser.add("event", parseEvent)

  def parseBinds(cfg, state):
    def parseInputsOutputs(cfg, state):
      def parseGroup(n1, n2, parser, cfg, state):
        cfgs = cfg[n2] if n2 in cfg else (cfg[n1],) if n1 in cfg else ()
        r, t = [], None
        for c in cfgs:
          try:
            t = parser(c, state)
          except RuntimeError as e:
            logger.warning("{} (encountered when parsing {} '{}')".format(e, n1, str2(c)))
            continue
          if t is None:
            logger.warning("Could not parse {} '{}')".format(n1, str2(c)))
            continue
          r.append(t)
        return r

      parser = state["settings"]["parser"]
      def actionParser(cfg, state):
        obj = get_argobj(cfg, state)
        if obj is not None:
          return obj
        try:
          return parser.get("action")(cfg, state)
        except KeyError:
          logger.debug("Action parser could not parse '{}', so trying sink parser".format(str2(cfg)))
          return parser.get("sink")(cfg, state)

      inputs = parseGroup("input", "inputs", parser.get("ed"), cfg, state)
      if len(inputs) == 0:
        logger.warning("No inputs were constructed (encountered when parsing '{}')".format(str2(cfg)))

      outputs = parseGroup("output", "outputs", actionParser, cfg, state)
      if len(outputs) == 0:
        logger.warning("No outputs were constructed (encountered when parsing '{}')".format(str2(cfg)))

      return ((i,o) for i in inputs for o in outputs)

    binds = get_nested_d(cfg, "binds", ())
    #logger.debug("binds: {}".format(binds))
    #sorting binds so actions that reset curves are initialized after these curves were actually initialized
    def bindsKey(b):
      def checkOutput(o):
        return 10 if type(o) in (dict, collections.OrderedDict) and o.get("action", o.get("type", None)) in ("resetCurve", "resetCurves") else 0
      r = 0
      if "output" in b:
        r = checkOutput(b["output"])
      elif "outputs" in b:
        for o in b["outputs"]:
          r = max(r, checkOutput(o))
      return r
    binds.sort(key=bindsKey)
    cmpOp = CmpWithModifiers()
    bindingSink = BindSink(cmpOp)
    for bind in binds:
      for i,o in parseInputsOutputs(bind, state):
        bindingSink.add(i, o, bind.get("level", 0))
    return bindingSink

  scParser.add("binds", parseBinds)

  outputParser = IntrusiveSelectParser(keyOp=lambda cfg : get_nested(cfg, "type"))
  parser.add("output", outputParser)

  @make_reporting_joystick
  def parseNullJoystickOutput(cfg, state):
    values = get_nested_d(cfg, "values")
    if values is not None:
      values = {name2code(n) : v for n,v in values.items()}
    limits = get_nested_d(cfg, "limits")
    if limits is not None:
      limits = {name2code(n) : v for n,v in limits.items()}
    j = NullJoystick(values=values, limits=limits)
    return j
  outputParser.add("null", parseNullJoystickOutput)

  def parseExternalOutput(cfg, state):
    settings, name = state["settings"], get_nested(cfg, "name")
    j = settings["outputs"].get(name, None)
    if j is None:
      j = state["parser"]("output", settings["config"]["outputs"][name], state)
      settings["outputs"][name] = j
    return j
  outputParser.add("external", parseExternalOutput)

  @make_reporting_joystick
  def parseRateLimitOutput(cfg, state):
    rates = {name2code(axisName):value for axisName,value in get_nested(cfg, "rates").items()}
    next = state["parser"]("output", get_nested(cfg, "next"), state)
    j = RateLimititngJoystick(next, rates)
    state["settings"]["updated"].append(lambda tick,ts : j.update(tick))
    return j
  outputParser.add("rateLimit", parseRateLimitOutput)

  @make_reporting_joystick
  def parseRateSettingOutput(cfg, state):
    rates = {name2code(axisName):value for axisName,value in get_nested(cfg, "rates").items()}
    limits = {name2code(axisName):value for axisName,value in get_nested(cfg, "limits").items()}
    next = state["parser"]("output", get_nested(cfg, "next"), state)
    j = RateSettingJoystick(next, rates, limits)
    state["settings"]["updated"].append(lambda tick,ts : j.update(tick))
    return j
  outputParser.add("rateSet", parseRateSettingOutput)

  @make_reporting_joystick
  def parseRelativeOutput(cfg, state):
    next = state["parser"]("output", get_nested(cfg, "next"), state)
    j = RelativeHeadMovementJoystick(next=next, r=get_nested_d(cfg, "clampRadius", float("inf")), stick=get_nested_d(cfg, "stick", True))
    return j
  outputParser.add("relative", parseRelativeOutput)

  @make_reporting_joystick
  def parseCompositeOutput(cfg, state):
    parser = state["parser"].get("output")
    children = parse_list(get_nested(cfg, "children"), state, parser)
    j = CompositeJoystick(children)
    return j
  outputParser.add("composite", parseCompositeOutput)

  @make_reporting_joystick
  def parseMappingOutput(cfg, state):
    outputs = state["settings"]["outputs"]
    j = MappingJoystick()
    for fromAxis,to in get_nested(cfg, "mapping").items():
      toJoystick, toAxis = fn2sc(to["to"])
      factor = to.get("factor", 1.0)
      j.add(name2code(fromAxis), toJoystick, toAxis, factor)
    return j
  outputParser.add("mapping", parseMappingOutput)

  @make_reporting_joystick
  def parseOpentrackOutput(cfg, state):
    j = Opentrack(get_nested(cfg, "ip"), int(get_nested(cfg, "port")))
    state["settings"]["updated"].append(lambda tick,ts : j.send())
    return j
  outputParser.add("opentrack", parseOpentrackOutput)

  @make_reporting_joystick
  def parseUdpJoystickOutput(cfg, state):
    packetMakers = {
      "il2" : make_il2_packet,
      "il2_6dof" : make_il2_6dof_packet,
      "opentrack" : make_opentrack_packet
    }
    j = UdpJoystick(get_nested(cfg, "ip"), int(get_nested(cfg, "port")), packetMakers[get_nested(cfg, "format")], int(get_nested_d(cfg, "numPackets", 1)))
    for a,l in get_nested_d(cfg, "limits", {}).items():
      j.set_limits(name2code(a), l)
    state["settings"]["updated"].append(lambda tick,ts : j.send())
    return j
  outputParser.add("udpJoystick", parseUdpJoystickOutput)

  return parser
