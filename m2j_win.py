#!/usr/bin/python

#Mouse to joystick emulator for Windows

#Dependencies:

import sys
sys.path.append(".")
import gc
import getopt
import traceback
import logging
import m2j
from m2j import *

import win32con
import sys
from ctypes import *
from ctypes.wintypes import *

import win32file

logger = logging.getLogger(__name__)


#PPJoystick
FILE_DEVICE_UNKNOWN = 0x00000022
METHOD_BUFFERED = 0
FILE_ANY_ACCESS = 0
def CTL_CODE(DeviceType,Function,Method,Access):
  return (((DeviceType) << 16) | ((Access) << 14) | ((Function) << 2) | (Method))

class PPJoystick:
  def move_axis(self, axis, value, relative):
    if axis not in self.get_supported_axes():
      raise RuntimeError("Axis not supported: {}".format(axis))
    v = value if relative == False else self.get_axis_value(axis)+value
    v = clamp(v, *self.get_limits(axis))
    self.a_[axis] = v
    #logger.debug("{}: setting axis {} to {}".format(self, typecode2name(codes.EV_ABS, axis), v))
    self.dirty_ = True

  def get_axis_value(self, axis):
    if axis not in self.get_supported_axes():
      raise RuntimeError("Axis not supported: {}".format(axis))
    return self.a_[axis]

  def get_limits(self, axis):
    if axis not in self.get_supported_axes():
      raise RuntimeError("Axis not supported: {}".format(axis))
    return self.limits_[axis]

  def get_supported_axes(self):
    return self.axes_[:self.numAxes_]

  def set_button_state(self, button, state):
    n = button - 256
    if n < 0 or n >= self.numButtons_:
      raise RuntimeError("Button not supported: {}".format(button))
    self.d_[n] = state
    self.dirty_ = True

  def get_button_state(self, button):
    n = button - 256
    if n < 0 or n >= self.numButtons_:
      raise RuntimeError("Button not supported: {}".format(button))
    return self.d_[n]

  def update(self):
    if not self.dirty_:
      return
    data = self.make_data_()
    #logger.debug("{}.update(): data: {}".format(self, struct.unpack(self.fmt_, data)))
    try:
      win32file.DeviceIoControl(self.devHandle_, self.IOCTL_PPORTJOY_SET_STATE, data, 0, None)
    except Exception as e:
      logger.error("DeviceIoControl error: {}".format(e))
    self.dirty_ = False

  def __init__(self, i, numAxes=8, numButtons=16, limits=None, factors=None):
    self.numAxes_, self.numButtons_ = numAxes, numButtons

    self.limits_ = {}
    for axis in self.get_supported_axes():
      self.limits_[axis] = (-1.0, 1.0) if (limits is None or axis not in limits) else limits[axis]

    self.factors_ = factors if factors is not None else {}

    devName = self.PPJOY_IOCTL_DEVNAME_PREFIX + str(i)
    try:
      self.devHandle_ = win32file.CreateFile(devName, win32file.GENERIC_WRITE, win32file.FILE_SHARE_WRITE, None, win32file.OPEN_EXISTING, 0, None);
    except Exception as e:
      raise RuntimeError("CreateFile failed with error code 0x{:x} trying to open {} device ({})".format(windll.kernel32.GetLastError(), devName, e))
    """
    typedef struct
    {
     unsigned long	Signature;				/* Signature to identify packet to PPJoy IOCTL */
     char			NumAnalog;				/* Num of analog values we pass */
     long			Analog[NUM_ANALOG];		/* Analog values */
     char			NumDigital;				/* Num of digital values we pass */
     char			Digital[NUM_DIGITAL];	/* Digital values */
    }	JOYSTICK_STATE;
    """
    #Have to explicitly specify little-endiannes
    self.fmt_ = "<Lb{:d}lb{:d}b".format(self.NUM_ANALOG, self.NUM_DIGITAL)
    self.dataSize_ = struct.calcsize(self.fmt_)
    self.a_ = {axis : 0.0 for axis in self.axes_}
    self.d_ = [0 for i in range(self.NUM_DIGITAL)]
    self.dirty_ = True

  def __del__(self):
    if hasattr(self, "devHandle_"):
      win32file.CloseHandle(self.devHandle_)

  def make_data_(self):
    analog = tuple(lerp(self.factors_.get(axis, 1.0)*self.a_[axis], self.limits_[axis][0], self.limits_[axis][1], self.PPJOY_AXIS_MIN, self.PPJOY_AXIS_MAX) for axis in self.axes_)
    digital = tuple(d for d in self.d_)
    data = struct.pack(self.fmt_, *((self.JOYSTICK_STATE_V1, self.numAxes_,) + analog + (self.numButtons_,) + digital))
    return data

  JOYSTICK_STATE_V1 = 0x53544143
  PPJOY_IOCTL_DEVNAME_PREFIX = "\\\\.\\PPJoyIOCTL"
  NUM_ANALOG = 8
  NUM_DIGITAL = 16
  PPJOY_AXIS_MIN = 1
  PPJOY_AXIS_MAX = 32767
  IOCTL_PPORTJOY_SET_STATE = CTL_CODE(FILE_DEVICE_UNKNOWN, 0x0, METHOD_BUFFERED, FILE_ANY_ACCESS)
  axes_ = (codes.ABS_X, codes.ABS_Y, codes.ABS_Z, codes.ABS_RX, codes.ABS_RY, codes.ABS_RZ, codes.ABS_THROTTLE, codes.ABS_RUDDER)


@make_reporting_joystick
def parsePPJoystickOutput(cfg, state):
  limits = cfg.get("limits")
  if limits is not None:
    limits = {name2code(n) : v for n,v in limits.items()}
  factors = cfg.get("factors")
  if factors is not None:
    factors = {name2code(n) : v for n,v in factors.items()}
  j = PPJoystick(i=cfg["id"], numAxes=cfg.get("numAxes", 8), numButtons=cfg.get("numButtons", 16), limits=limits, factors=factors)
  state["settings"]["updated"].append(lambda tick, ts : j.update())
  return j


#Raw input device manager
MAX_PATH = 255
WM_INPUT = 255
WNDPROC = WINFUNCTYPE(c_long, c_int, c_uint, c_int, c_int)

RIDI_DEVICENAME = 0x20000007
RIDI_DEVICEINFO = 0x2000000b

RIDEV_INPUTSINK = 0x00000100
RIDEV_EXINPUTSINK = 0x00001000
RIDEV_CAPTUREMOUSE = 0x00000200

RID_INPUT = 0x10000003

RIM_TYPEMOUSE = 0
RIM_TYPEKEYBOARD = 1
RIM_TYPEHID = 2

def rimtype2str(t):
  return "mouse" if t == RIM_TYPEMOUSE else "keyboard" if t == RIM_TYPEKEYBOARD else "hid" if t == RIM_TYPEHID else ""

RI_MOUSE_LEFT_BUTTON_DOWN = 0x0001
RI_MOUSE_LEFT_BUTTON_UP = 0x0002
RI_MOUSE_RIGHT_BUTTON_DOWN = 0x0004
RI_MOUSE_RIGHT_BUTTON_UP = 0x0008
RI_MOUSE_MIDDLE_BUTTON_DOWN = 0x0010
RI_MOUSE_MIDDLE_BUTTON_UP = 0x0020
RI_MOUSE_BUTTON_4_DOWN = 0x0040
RI_MOUSE_BUTTON_4_UP = 0x0080
RI_MOUSE_BUTTON_5_DOWN = 0x0100
RI_MOUSE_BUTTON_5_UP = 0x0200
RI_MOUSE_WHEEL = 0x0400

RI_MOUSE_BUTTON_1_DOWN = RI_MOUSE_LEFT_BUTTON_DOWN
RI_MOUSE_BUTTON_1_UP = RI_MOUSE_LEFT_BUTTON_UP
RI_MOUSE_BUTTON_2_DOWN = RI_MOUSE_RIGHT_BUTTON_DOWN
RI_MOUSE_BUTTON_2_UP = RI_MOUSE_RIGHT_BUTTON_UP
RI_MOUSE_BUTTON_3_DOWN = RI_MOUSE_MIDDLE_BUTTON_DOWN
RI_MOUSE_BUTTON_3_UP = RI_MOUSE_MIDDLE_BUTTON_UP

MOUSE_MOVE_RELATIVE = 0
MOUSE_MOVE_ABSOLUTE = 1
MOUSE_VIRTUAL_DESKTOP = 0x02
MOUSE_ATTRIBUTES_CHANGED = 0x04
MOUSE_MOVE_NOCOALESCE = 0x08

RI_KEY_MAKE = 0
RI_KEY_BREAK = 1
RI_KEY_E0 = 2
RI_KEY_E1 = 4
RI_KEY_TERMSRV_SET_LED = 8
RI_KEY_TERMSRV_SHADOW = 0x10

HID_USAGE_PAGE_GENERIC = 0x01
HID_USAGE_PAGE_GAME = 0x05
HID_USAGE_PAGE_LED = 0x08
HID_USAGE_PAGE_BUTTON = 0x09

HID_USAGE_GENERIC_POINTER = 0x01
HID_USAGE_GENERIC_MOUSE = 0x02
HID_USAGE_GENERIC_JOYSTICK = 0x04
HID_USAGE_GENERIC_GAMEPAD = 0x05
HID_USAGE_GENERIC_KEYBOARD = 0x06
HID_USAGE_GENERIC_KEYPAD = 0x07
HID_USAGE_GENERIC_MULTI_AXIS_CONTROLLER = 0x08

VK_LBUTTON = 0x01
VK_RBUTTON = 0x02
VK_CANCEL = 0x03
VK_MBUTTON = 0x04
VK_XBUTTON1 = 0x05
VK_XBUTTON2 = 0x06
VK_BACK = 0x08
VK_TAB = 0x09
VK_CLEAR = 0x0C
VK_RETURN = 0x0D
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_PAUSE = 0x13
VK_CAPITAL = 0x14
VK_KANA = 0x15
VK_HANGEUL = 0x15
VK_HANGUL = 0x15
VK_JUNJA = 0x17
VK_FINAL = 0x18
VK_HANJA = 0x19
VK_KANJI = 0x19
VK_ESCAPE = 0x1B
VK_CONVERT = 0x1C
VK_NONCONVERT = 0x1D
VK_ACCEPT = 0x1E
VK_MODECHANGE = 0x1F
VK_SPACE = 0x20
VK_PRIOR = 0x21
VK_NEXT = 0x22
VK_END = 0x23
VK_HOME = 0x24
VK_LEFT = 0x25
VK_UP = 0x26
VK_RIGHT = 0x27
VK_DOWN = 0x28
VK_SELECT = 0x29
VK_PRINT = 0x2A
VK_EXECUTE = 0x2B
VK_SNAPSHOT = 0x2C
VK_INSERT = 0x2D
VK_DELETE = 0x2E
VK_HELP = 0x2F

VK_LWIN = 0x5B
VK_RWIN = 0x5C
VK_APPS = 0x5D
VK_SLEEP = 0x5F
VK_NUMPAD0 = 0x60
VK_NUMPAD1 = 0x61
VK_NUMPAD2 = 0x62
VK_NUMPAD3 = 0x63
VK_NUMPAD4 = 0x64
VK_NUMPAD5 = 0x65
VK_NUMPAD6 = 0x66
VK_NUMPAD7 = 0x67
VK_NUMPAD8 = 0x68
VK_NUMPAD9 = 0x69
VK_MULTIPLY = 0x6A
VK_ADD = 0x6B
VK_SEPARATOR = 0x6C
VK_SUBTRACT = 0x6D
VK_DECIMAL = 0x6E
VK_DIVIDE = 0x6F
VK_F1 = 0x70
VK_F2 = 0x71
VK_F3 = 0x72
VK_F4 = 0x73
VK_F5 = 0x74
VK_F6 = 0x75
VK_F7 = 0x76
VK_F8 = 0x77
VK_F9 = 0x78
VK_F10 = 0x79
VK_F11 = 0x7A
VK_F12 = 0x7B
VK_F13 = 0x7C
VK_F14 = 0x7D
VK_F15 = 0x7E
VK_F16 = 0x7F
VK_F17 = 0x80
VK_F18 = 0x81
VK_F19 = 0x82
VK_F20 = 0x83
VK_F21 = 0x84
VK_F22 = 0x85
VK_F23 = 0x86
VK_F24 = 0x87
VK_NUMLOCK = 0x90
VK_SCROLL = 0x91
VK_OEM_NEC_EQUAL = 0x92
VK_OEM_FJ_JISHO = 0x92
VK_OEM_FJ_MASSHOU = 0x93
VK_OEM_FJ_TOUROKU = 0x94
VK_OEM_FJ_LOYA = 0x95
VK_OEM_FJ_ROYA = 0x96
VK_LSHIFT = 0xA0
VK_RSHIFT = 0xA1
VK_LCONTROL = 0xA2
VK_RCONTROL = 0xA3
VK_LMENU = 0xA4
VK_RMENU = 0xA5
VK_BROWSER_BACK = 0xA6
VK_BROWSER_FORWARD = 0xA7
VK_BROWSER_REFRESH = 0xA8
VK_BROWSER_STOP = 0xA9
VK_BROWSER_SEARCH = 0xAA
VK_BROWSER_FAVORITES = 0xAB
VK_BROWSER_HOME = 0xAC
VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_STOP = 0xB2
VK_MEDIA_PLAY_PAUSE = 0xB3
VK_LAUNCH_MAIL = 0xB4
VK_LAUNCH_MEDIA_SELECT = 0xB5
VK_LAUNCH_APP1 = 0xB6
VK_LAUNCH_APP2 = 0xB7
VK_OEM_1 = 0xBA
VK_OEM_PLUS = 0xBB
VK_OEM_COMMA = 0xBC
VK_OEM_MINUS = 0xBD
VK_OEM_PERIOD = 0xBE
VK_OEM_2 = 0xBF
VK_OEM_3 = 0xC0
VK_OEM_4 = 0xDB
VK_OEM_5 = 0xDC
VK_OEM_6 = 0xDD
VK_OEM_7 = 0xDE
VK_OEM_8 = 0xDF
VK_OEM_AX = 0xE1
VK_OEM_102 = 0xE2
VK_ICO_HELP = 0xE3
VK_ICO_00 = 0xE4
VK_PROCESSKEY = 0xE5
VK_ICO_CLEAR = 0xE6
VK_PACKET = 0xE7
VK_OEM_RESET = 0xE9
VK_OEM_JUMP = 0xEA
VK_OEM_PA1 = 0xEB
VK_OEM_PA2 = 0xEC
VK_OEM_PA3 = 0xED
VK_OEM_WSCTRL = 0xEE
VK_OEM_CUSEL = 0xEF
VK_OEM_ATTN = 0xF0
VK_OEM_FINISH = 0xF1
VK_OEM_COPY = 0xF2
VK_OEM_AUTO = 0xF3
VK_OEM_ENLW = 0xF4
VK_OEM_BACKTAB = 0xF5
VK_ATTN = 0xF6
VK_CRSEL = 0xF7
VK_EXSEL = 0xF8
VK_EREOF = 0xF9
VK_PLAY = 0xFA
VK_ZOOM = 0xFB
VK_NONAME = 0xFC
VK_PA1 = 0xFD
VK_OEM_CLEAR = 0xFE


#TODO Implement
g_vkey2codeDict = {
  VK_PLAY : codes.KEY_PLAY, VK_F21 : codes.KEY_F21, VK_PAUSE : codes.KEY_PAUSE, VK_HOME : codes.KEY_HOME, VK_HELP : codes.KEY_HELP, VK_HANGEUL : codes.KEY_HANGEUL, VK_SELECT : codes.KEY_SELECT, VK_RIGHT : codes.KEY_RIGHT, VK_HANJA : codes.KEY_HANJA, VK_TAB : codes.KEY_TAB, VK_F9 : codes.KEY_F9, VK_F8 : codes.KEY_F8, VK_F3 : codes.KEY_F3, VK_F2 : codes.KEY_F2, VK_F1 : codes.KEY_F1, VK_F7 : codes.KEY_F7, VK_F6 : codes.KEY_F6, VK_F5 : codes.KEY_F5, VK_F4 : codes.KEY_F4, VK_F22 : codes.KEY_F22, VK_F23 : codes.KEY_F23, VK_ZOOM : codes.KEY_ZOOM, VK_CANCEL : codes.KEY_CANCEL, VK_DELETE : codes.KEY_DELETE, VK_SPACE : codes.KEY_SPACE, VK_F24 : codes.KEY_F24, VK_NUMLOCK : codes.KEY_NUMLOCK, VK_END : codes.KEY_END, VK_PRINT : codes.KEY_PRINT, VK_CLEAR : codes.KEY_CLEAR, VK_MENU : codes.KEY_MENU, VK_LEFT : codes.KEY_LEFT, VK_BACK : codes.KEY_BACK, VK_INSERT : codes.KEY_INSERT, VK_UP : codes.KEY_UP, VK_NEXT : codes.KEY_NEXT, VK_F10 : codes.KEY_F10, VK_F20 : codes.KEY_F20, VK_SLEEP : codes.KEY_SLEEP, VK_F19 : codes.KEY_F19, VK_F18 : codes.KEY_F18, VK_F13 : codes.KEY_F13, VK_F12 : codes.KEY_F12, VK_F11 : codes.KEY_F11, VK_DOWN : codes.KEY_DOWN, VK_F17 : codes.KEY_F17, VK_F16 : codes.KEY_F16, VK_F15 : codes.KEY_F15, VK_F14 : codes.KEY_F14, VK_SCROLL : codes.KEY_SCROLLLOCK,
  VK_SHIFT : codes.KEY_RIGHTSHIFT, VK_CONTROL : codes.KEY_RIGHTCTRL, VK_MENU : codes.KEY_RIGHTALT,
  VK_APPS : codes.KEY_APPSELECT,
  0x41 : codes.KEY_A, 0x42 : codes.KEY_B, 0x43 : codes.KEY_C, 0x44 : codes.KEY_D, 0x45 : codes.KEY_E, 0x46 : codes.KEY_F, 0x47 : codes.KEY_G, 0x48 : codes.KEY_H, 0x49 : codes.KEY_I, 0x4a : codes.KEY_J, 0x4b : codes.KEY_K, 0x4c : codes.KEY_L, 0x4d : codes.KEY_M, 0x4e : codes.KEY_N, 0x4f : codes.KEY_O, 0x50 : codes.KEY_P, 0x51 : codes.KEY_Q, 0x52 : codes.KEY_R, 0x53 : codes.KEY_S, 0x54 : codes.KEY_T, 0x55 : codes.KEY_U, 0x56 : codes.KEY_V, 0x57 : codes.KEY_W, 0x58 : codes.KEY_X, 0x59 : codes.KEY_Y, 0x5a : codes.KEY_Z, }
def vkey2code(vkey):
  r = g_vkey2codeDict.get(vkey, None)
  rStr = "0x{:x} ({})".format(r, typecode2name(codes.EV_KEY, r)) if r is not None else "None"
  #logger.debug("vkey2code(): 0x{:x} -> {}".format(vkey, rStr))
  return r


g_mc2c = [
  #E0
  { 0x37 : codes.KEY_PRINT, 0x46 : codes.KEY_PAUSE, 0x52 : codes.KEY_INSERT, 0x47 : codes.KEY_HOME, 0x49 : codes.KEY_PAGEUP, 0x53 : codes.KEY_DELETE, 0x4f : codes.KEY_END, 0x51 : codes.KEY_PAGEDOWN, 0x4d : codes.KEY_RIGHT, 0x4b : codes.KEY_LEFT, 0x50 : codes.KEY_DOWN, 0x48 : codes.KEY_UP, 0x35 : codes.KEY_KPSLASH, 0x1c : codes.KEY_KPENTER, 0x5d : codes.KEY_COMPOSE, 0x5e : codes.KEY_POWER, 0x1d : codes.KEY_RIGHTCTRL, 0x38 : codes.KEY_RIGHTALT, },
  #E1
  { 0x45 : codes.KEY_NUMLOCK, },
  #other
  #0x60 should not be used, but WINE reports CAPSLOCK by this code
  { 0x60: codes.KEY_CAPSLOCK, 0x69 : codes.KEY_COMPOSE, 0x45 : codes.KEY_PAUSE, }
]

def makecode2code(mc, flags):
  lb = mc & 0xFF
  group = 0 if (flags & RI_KEY_E0) else 1 if (flags & RI_KEY_E1) else 2
  return g_mc2c[group].get(lb, lb)


DIK_ESCAPE = 0x01
DIK_1 = 0x02
DIK_2 = 0x03
DIK_3 = 0x04
DIK_4 = 0x05
DIK_5 = 0x06
DIK_6 = 0x07
DIK_7 = 0x08
DIK_8 = 0x09
DIK_9 = 0x0A
DIK_0 = 0x0B
DIK_MINUS = 0x0C
DIK_EQUALS = 0x0D
DIK_BACK = 0x0E
DIK_TAB = 0x0F
DIK_Q = 0x10
DIK_W = 0x11
DIK_E = 0x12
DIK_R = 0x13
DIK_T = 0x14
DIK_Y = 0x15
DIK_U = 0x16
DIK_I = 0x17
DIK_O = 0x18
DIK_P = 0x19
DIK_LBRACKET = 0x1A
DIK_RBRACKET = 0x1B
DIK_RETURN = 0x1C
DIK_LCONTROL = 0x1D
DIK_A = 0x1E
DIK_S = 0x1F
DIK_D = 0x20
DIK_F = 0x21
DIK_G = 0x22
DIK_H = 0x23
DIK_J = 0x24
DIK_K = 0x25
DIK_L = 0x26
DIK_SEMICOLON = 0x27
DIK_APOSTROPHE = 0x28
DIK_GRAVE = 0x29
DIK_LSHIFT = 0x2A
DIK_BACKSLASH = 0x2B
DIK_Z = 0x2C
DIK_X = 0x2D
DIK_C = 0x2E
DIK_V = 0x2F
DIK_B = 0x30
DIK_N = 0x31
DIK_M = 0x32
DIK_COMMA = 0x33
DIK_PERIOD = 0x34
DIK_SLASH = 0x35
DIK_RSHIFT = 0x36
DIK_MULTIPLY = 0x37
DIK_LMENU = 0x38
DIK_SPACE = 0x39
DIK_CAPITAL = 0x3A
DIK_F1 = 0x3B
DIK_F2 = 0x3C
DIK_F3 = 0x3D
DIK_F4 = 0x3E
DIK_F5 = 0x3F
DIK_F6 = 0x40
DIK_F7 = 0x41
DIK_F8 = 0x42
DIK_F9 = 0x43
DIK_F10 = 0x44
DIK_NUMLOCK = 0x45
DIK_SCROLL = 0x46
DIK_NUMPAD7 = 0x47
DIK_NUMPAD8 = 0x48
DIK_NUMPAD9 = 0x49
DIK_SUBTRACT = 0x4A
DIK_NUMPAD4 = 0x4B
DIK_NUMPAD5 = 0x4C
DIK_NUMPAD6 = 0x4D
DIK_ADD = 0x4E
DIK_NUMPAD1 = 0x4F
DIK_NUMPAD2 = 0x50
DIK_NUMPAD3 = 0x51
DIK_NUMPAD0 = 0x52
DIK_DECIMAL = 0x53
DIK_OEM_102 = 0x56
DIK_F11 = 0x57
DIK_F12 = 0x58
DIK_F13 = 0x64
DIK_F14 = 0x65
DIK_F15 = 0x66
DIK_KANA = 0x70
DIK_ABNT_C1 = 0x73
DIK_CONVERT = 0x79
DIK_NOCONVERT = 0x7B
DIK_YEN = 0x7D
DIK_ABNT_C2 = 0x7E
DIK_NUMPADEQUALS = 0x8D
DIK_CIRCUMFLEX = 0x90
DIK_AT = 0x91
DIK_COLON = 0x92
DIK_UNDERLINE = 0x93
DIK_KANJI = 0x94
DIK_STOP = 0x95
DIK_AX = 0x96
DIK_UNLABELED = 0x97
DIK_NEXTTRACK = 0x99
DIK_NUMPADENTER = 0x9C
DIK_RCONTROL = 0x9D
DIK_MUTE = 0xA0
DIK_CALCULATOR = 0xA1
DIK_PLAYPAUSE = 0xA2
DIK_MEDIASTOP = 0xA4
DIK_VOLUMEDOWN = 0xAE
DIK_VOLUMEUP = 0xB0
DIK_WEBHOME = 0xB2
DIK_NUMPADCOMMA = 0xB3
DIK_DIVIDE = 0xB5
DIK_SYSRQ = 0xB7
DIK_RMENU = 0xB8
DIK_PAUSE = 0xC5
DIK_HOME = 0xC7
DIK_UP = 0xC8
DIK_PRIOR = 0xC9
DIK_LEFT = 0xCB
DIK_RIGHT = 0xCD
DIK_END = 0xCF
DIK_DOWN = 0xD0
DIK_NEXT = 0xD1
DIK_INSERT = 0xD2
DIK_DELETE = 0xD3
DIK_LWIN = 0xDB
DIK_RWIN = 0xDC
DIK_APPS = 0xDD
DIK_POWER = 0xDE
DIK_SLEEP = 0xDF
DIK_WAKE = 0xE3
DIK_WEBSEARCH = 0xE5
DIK_WEBFAVORITES = 0xE6
DIK_WEBREFRESH = 0xE7
DIK_WEBSTOP = 0xE8
DIK_WEBFORWARD = 0xE9
DIK_WEBBACK = 0xEA
DIK_MYCOMPUTER = 0xEB
DIK_MAIL = 0xEC
DIK_MEDIASELECT = 0xED

DIK_BACKSPACE = DIK_BACK
DIK_NUMPADSTAR = DIK_MULTIPLY
DIK_LALT = DIK_LMENU
DIK_CAPSLOCK = DIK_CAPITAL
DIK_NUMPADMINUS = DIK_SUBTRACT
DIK_NUMPADPLUS = DIK_ADD
DIK_NUMPADPERIOD = DIK_DECIMAL
DIK_NUMPADSLASH = DIK_DIVIDE
DIK_RALT = DIK_RMENU
DIK_UPARROW = DIK_UP
DIK_PGUP = DIK_PRIOR
DIK_LEFTARROW = DIK_LEFT
DIK_RIGHTARROW = DIK_RIGHT
DIK_DOWNARROW = DIK_DOWN
DIK_PGDN = DIK_NEXT


def dik2code(dik):
  return dik


INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
INPUT_HARDWARE = 2


KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_SCANCODE = 0x0008


MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_XDOWN = 0x0080
MOUSEEVENTF_XUP = 0x0100
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x01000
MOUSEEVENTF_MOVE_NOCOALESCE = 0x2000
MOUSEEVENTF_VIRTUALDESK = 0x4000
MOUSEEVENTF_ABSOLUTE = 0x8000


class MOUSEINPUT(Structure):
  _fields_ = [
    ("dx", LONG),
    ("dy", LONG),
    ("mouseData", DWORD),
    ("dwFlags", DWORD),
    ("time", DWORD),
    ("dwExtraInfo", POINTER(ULONG)),
  ]


class KEYBDINPUT(Structure):
  _fields_ = [
    ("wVk", WORD),
    ("wScan", WORD),
    ("dwFlags", DWORD),
    ("time", DWORD),
    ("dwExtraInfo", POINTER(ULONG)),
  ]


class HARDWAREINPUT(Structure):
  _fields_ = [
    ("uMsg", DWORD),
    ("wParamL", WORD),
    ("wParamH", WORD),
  ]


class INPUT(Structure):
  class _U1(Union):
    _fields_ = [
      ("mi", MOUSEINPUT),
      ("ki", KEYBDINPUT),
      ("hi", HARDWAREINPUT),
    ]
  _fields_ = [
    ("type", DWORD),
    ("_u1", _U1)
  ]
  _anonymous_ = ("_u1", )


class DirectInputKeyboard:
  def set_key_state(self, key, state):
    #logger.debug("{}: Setting key {} (0x{:X}) to {}".format(self, typecode2name(codes.EV_KEY, key), key, state))
    extra = ULONG(0)
    inpt = INPUT()
    inpt.type = INPUT_KEYBOARD
    inpt.ki.wVk = 0
    inpt.ki.wScan = key
    inpt.ki.dwFlags = KEYEVENTF_SCANCODE | (KEYEVENTF_KEYUP if state == 0 else 0)
    inpt.ki.time = 0
    inpt.ki.dwExtraInfo = pointer(extra)
    if windll.user32.SendInput(1, byref(inpt), sizeof(inpt)) != 1:
      raise WinError()

  def set_button_state(self, key, state):
    return self.set_key_state(key, state)


def parseDirectInputKeyboardOutput(cfg, state):
  return DirectInputKeyboard()


class WNDCLASS(Structure):
    _fields_ = [('style', c_uint),
                ('lpfnWndProc', WNDPROC),
                ('cbClsExtra', c_int),
                ('cbWndExtra', c_int),
                ('hInstance', c_int),
                ('hIcon', c_int),
                ('hCursor', c_int),
                ('hbrBackground', c_int),
                ('lpszMenuName', c_char_p),
                ('lpszClassName', c_char_p)]


class RECT(Structure):
    _fields_ = [('left', c_long),
                ('top', c_long),
                ('right', c_long),
                ('bottom', c_long)]


class PAINTSTRUCT(Structure):
    _fields_ = [('hdc', c_int),
                ('fErase', c_int),
                ('rcPaint', RECT),
                ('fRestore', c_int),
                ('fIncUpdate', c_int),
                ('rgbReserved', c_char * 32)]


class POINT(Structure):
    _fields_ = [('x', c_long),
                ('y', c_long)]


class MSG(Structure):
    _fields_ = [('hwnd', c_int),
                ('message', c_uint),
                ('wParam', c_int),
                ('lParam', c_int),
                ('time', c_int),
                ('pt', POINT)]


class RAWINPUTDEVICE(Structure):
    _fields_ = [
        ("usUsagePage", c_ushort),
        ("usUsage", c_ushort),
        ("dwFlags", DWORD),
        ("hwndTarget", HWND),
    ]


class RAWINPUTDEVICELIST(Structure):
    _fields_ = [
        ("hDevice", HANDLE),
        ("dwType", DWORD)
    ]


class RAWINPUTHEADER(Structure):
    _fields_ = [
        ("dwType", DWORD),
        ("dwSize", DWORD),
        ("hDevice", HANDLE),
        ("wParam", WPARAM),
    ]


class RAWMOUSE(Structure):
    class _U1(Union):
        class _S2(Structure):
            _fields_ = [
                ("usButtonFlags", c_ushort),
                ("usButtonData", c_ushort),
            ]
        _fields_ = [
            ("ulButtons", ULONG),
            ("_s2", _S2),
        ]

    _fields_ = [
        ("usFlags", c_ushort),
        ("_u1", _U1),
        ("ulRawButtons", ULONG),
        ("lLastX", LONG),
        ("lLastY", LONG),
        ("ulExtraInformation", ULONG),
    ]
    _anonymous_ = ("_u1", )


class RAWKEYBOARD(Structure):
    _fields_ = [
        ("MakeCode", c_ushort),
        ("Flags", c_ushort),
        ("Reserved", c_ushort),
        ("VKey", c_ushort),
        ("Message", UINT),
        ("ExtraInformation", ULONG),
    ]


class RAWHID(Structure):
    _fields_ = [
        ("dwSizeHid", DWORD),
        ("dwCount", DWORD),
        ("bRawData", BYTE),
    ]


class RAWINPUT(Structure):
    class _U1(Union):
        _fields_ = [
            ("mouse", RAWMOUSE),
            ("keyboard", RAWKEYBOARD),
            ("hid", RAWHID),
        ]

    _fields_ = [
        ("header", RAWINPUTHEADER),
        ("_u1", _U1),
        ("hDevice", HANDLE),
        ("wParam", WPARAM),
    ]
    _anonymous_ = ("_u1", )


class RID_DEVICE_INFO_MOUSE(Structure):
    _fields_ = [
        ("dwId", DWORD),
        ("dwNumberOfButtons", DWORD),
        ("dwSampleRate", DWORD),
        ("fHasHorizontalWheel", BOOL),
    ]


class RID_DEVICE_INFO_KEYBOARD(Structure):
    _fields_ = [
      ("dwType", DWORD),
      ("dwSubType", DWORD),
      ("dwKeyboardMode", DWORD),
      ("dwNumberOfFunctionKeys", DWORD),
      ("dwNumberOfIndicators", DWORD),
      ("dwNumberOfKeysTotal", DWORD),
    ]


class RID_DEVICE_INFO_HID(Structure):
    _fields_ = [
        ("dwVendorId", DWORD ),
        ("dwProductId", DWORD ),
        ("dwVersionNumber", DWORD ),
        ("usUsagePage", USHORT),
        ("usUsage", USHORT),
    ]


class RID_DEVICE_INFO(Structure):
    class _U1(Union):
        _fields_ = [
            ("mouse", RID_DEVICE_INFO_MOUSE),
            ("keyboard", RID_DEVICE_INFO_KEYBOARD),
            ("hid", RID_DEVICE_INFO_HID),
        ]
    _fields_ = [
        ("cbSize", DWORD),
        ("dwType", DWORD),
        ("_u1", _U1)
    ]
    _anonymous_ = ("_u1", )


def ErrorIfZero(handle):
    if handle == 0:
        raise WinError()
    else:
        return handle


class RawInputEventSource:
  def __init__(self, useMessageWindow=True):
    CreateWindowEx = windll.user32.CreateWindowExA
    CreateWindowEx.argtypes = [c_int, c_char_p, c_char_p, c_int, c_int, c_int, c_int, c_int, c_int, c_int, c_int, c_int]
    CreateWindowEx.restype = ErrorIfZero

    # Define Window Class
    wndclass = WNDCLASS()
    wndclass.style = win32con.CS_HREDRAW | win32con.CS_VREDRAW
    wndclass.lpfnWndProc = WNDPROC(lambda h, m, w, l: self.wnd_proc(h, m, w, l))
    wndclass.cbClsExtra = wndclass.cbWndExtra = 0
    wndclass.hInstance = windll.kernel32.GetModuleHandleA(c_int(win32con.NULL))
    wndclass.hIcon = windll.user32.LoadIconA(c_int(win32con.NULL), c_int(win32con.IDI_APPLICATION))
    wndclass.hCursor = windll.user32.LoadCursorA(c_int(win32con.NULL), c_int(win32con.IDC_ARROW))
    wndclass.hbrBackground = windll.gdi32.GetStockObject(c_int(win32con.WHITE_BRUSH))
    wndclass.lpszMenuName = None
    wndclass.lpszClassName = str(id(self))
    # Register Window Class
    if not windll.user32.RegisterClassA(byref(wndclass)):
        raise WinError()
    #Need to store reference to wndclass or DestroyWindow will fail!
    self.wndclass = wndclass
    # Create Window
    hwnd = CreateWindowEx(
      0, wndclass.lpszClassName, str(id(self)),
      win32con.WS_OVERLAPPEDWINDOW, win32con.CW_USEDEFAULT, win32con.CW_USEDEFAULT, win32con.CW_USEDEFAULT, win32con.CW_USEDEFAULT,
      win32con.HWND_MESSAGE if useMessageWindow else win32con.NULL,
      win32con.NULL, wndclass.hInstance, win32con.NULL)
    if not useMessageWindow:
      windll.user32.ShowWindow(c_int(hwnd), c_int(win32con.SW_SHOWNORMAL))
      windll.user32.UpdateWindow(c_int(hwnd))
    #TODO Check for error
    self.hwnd = hwnd

    self.devs_ = dict()
    self.upu_ = set()
    logger.debug("{}: created".format(self))

  def __del__(self):
    self.stop()
    logger.debug("{}: destroyed".format(self))

  def stop(self):
    if hasattr(self, "hwnd"):
      r = windll.user32.DestroyWindow(self.hwnd)
      if r == 0:
        e = windll.kernel32.GetLastError()
        raise RuntimError("Error destroying window 0x{:x}, error 0x{:x}".format(self.hwnd, e))
      else:
        del self.hwnd
    if hasattr(self, "wndclass"):
      r = windll.user32.UnregisterClassA(self.wndclass.lpszClassName, 0)
      if r == 0:
        e = windll.kernel32.GetLastError()
        raise RuntimError("Error unregistering window class {}, error 0x{:x}".format(self.wndclass.lpszClassName, e))
      else:
        del self.wndclass

  def run_once(self):
    #logger.debug("{}.run_once()".format(self))
    msg = MSG()
    PM_REMOVE = 1
    while windll.user32.PeekMessageA(byref(msg), self.hwnd, 0, 0, PM_REMOVE) != 0:
      if msg.message == WM_INPUT:
        #logger.debug("{}.run_once(): got WM_INPUT".format(self))
        raw = RAWINPUT()
        dwSize = c_uint(sizeof(RAWINPUT))
        if windll.user32.GetRawInputData(msg.lParam, RID_INPUT, byref(raw), byref(dwSize), sizeof(RAWINPUTHEADER)) > 0:
          if raw.header.hDevice in self.devs_:
            hd = raw.header.hDevice
            sourceHash = self.devs_[hd].hash
            events = None
            if raw.header.dwType == RIM_TYPEMOUSE:
              #self.raw_mouse_events.append((raw.header.hDevice, raw.mouse.usFlags, raw.mouse.ulButtons, raw.mouse._u1._s2.usButtonFlags, raw.mouse._u1._s2.usButtonData, raw.mouse.ulRawButtons, raw.mouse.lLastX, raw.mouse.lLastY, raw.mouse.ulExtraInformation))
              #logger.debug("{}: Got mouse event".format(self))
              events = self.make_mouse_event_(raw, sourceHash)
            elif raw.header.dwType == RIM_TYPEKEYBOARD:
              #self.raw_keyboard_events.append((raw.header.hDevice, raw.keyboard.MakeCode, raw.keyboard.Flags, raw.keyboard.VKey, raw.keyboard.Message, raw.keyboard.ExtraInformation))
              #logger.debug("{}: Got keyboard event".format(self))
              events = self.make_kbd_event_(raw, sourceHash)
            elif raw.header.dwType == RIM_TYPEHID:
              #logger.debug("{}: Got HID event".format(self))
              #TODO Process HID events
              pass
            if events is not None:
              for e in events:
                self.sink_(e)
      else:
        windll.user32.DispatchMessageA(byref(msg))

  def track_device(self, name, source):
    devices = self.get_devices()
    for d in devices:
      if d.name == name:
        p = (d.usagePage, d.usage)
        if p not in self.upu_:
          numRid = 1
          Rid = (numRid * RAWINPUTDEVICE)()
          Rid[0].usUsagePage = d.usagePage
          Rid[0].usUsage = d.usage
          Rid[0].dwFlags = RIDEV_INPUTSINK
          Rid[0].hwndTarget = self.hwnd
          if not windll.user32.RegisterRawInputDevices(Rid, numRid, sizeof(RAWINPUTDEVICE)):
            raise WinError()
          self.upu_.add(p)
        class DevInfo:
          pass
        di = DevInfo()
        di.source, di.hash = source, calc_hash(source)
        self.devs_[d.handle] = di
        InputEvent.add_source_hash(di.source, di.hash)
        logger.info("Found device {} ({}) (usage page: 0x{:x}, usage: 0x{:x})".format(name, source, d.usagePage, d.usage))
        return
    raise RuntimeError("Device {} ({}) not found".format(name, source))

  def set_sink(self, sink):
    self.sink_ = sink

  def get_devices(self):
    uiNumDevices = c_uint(0)
    r = windll.user32.GetRawInputDeviceList(0, byref(uiNumDevices), sizeof(RAWINPUTDEVICELIST))
    if r == c_uint(-1):
      raise RuntimError("Error getting device number")
    rawInputDeviceList = (uiNumDevices.value * RAWINPUTDEVICELIST)()
    r = windll.user32.GetRawInputDeviceList(rawInputDeviceList, byref(uiNumDevices), sizeof(RAWINPUTDEVICELIST))
    if r == c_uint(-1):
      raise RuntimError("Error listing devices")
    class DeviceInfo:
      def __str__(self):
        return "{} {} {} {} {}".format(di.handle, di.type, di.name, di.usagePage, di.usage)
    devices = []
    for i in range(r):
      ridl = rawInputDeviceList[i]
      #Get required device name string length
      pName = 0
      szName = c_uint(0)
      r = windll.user32.GetRawInputDeviceInfoA(ridl.hDevice, RIDI_DEVICENAME, pName, byref(szName))
      if r == c_uint(-1):
        raise RuntimError("Error getting device name string length")
      pName = create_string_buffer(szName.value)
      r = windll.user32.GetRawInputDeviceInfoA(ridl.hDevice, RIDI_DEVICENAME, pName, byref(szName))
      if r == c_uint(-1):
        raise RuntimError("Error getting device name")
      ridi = RID_DEVICE_INFO()
      szRidi = c_uint(sizeof(RID_DEVICE_INFO))
      r = windll.user32.GetRawInputDeviceInfoA(ridl.hDevice, RIDI_DEVICEINFO, byref(ridi), byref(szRidi))
      if r == c_uint(-1):
        raise RuntimError("Error getting device info")
      di = DeviceInfo()
      di.handle, di.type, di.name = ridl.hDevice, ridl.dwType, pName.value
      if ridl.dwType == RIM_TYPEMOUSE:
        di.usagePage, di.usage = HID_USAGE_PAGE_GENERIC, HID_USAGE_GENERIC_MOUSE
      elif ridl.dwType == RIM_TYPEKEYBOARD:
        di.usagePage, di.usage = HID_USAGE_PAGE_GENERIC, HID_USAGE_GENERIC_KEYBOARD
      elif ridl.dwType == RIM_TYPEHID:
        di.usagePage, di.usage = ridi.hid.usUsagePage, ridi.hid.usUsage
      else:
        raise RuntimeError("Unexpected device type: 0x{:x}".format(ridi.dwType))
      devices.append(di)
    return devices

  def wnd_proc(self, hwnd, message, wParam, lParam):
    if message == win32con.WM_DESTROY:
      windll.user32.PostQuitMessage(0)
    return windll.user32.DefWindowProcA(c_int(hwnd), c_int(message), c_int(wParam), c_int(lParam))

  def make_mouse_event_(self, raw, source):
    ts, events = time.time(), []
    mouse = raw.mouse
    usButtonFlags = mouse._u1._s2.usButtonFlags
    if mouse.usFlags & MOUSE_MOVE_RELATIVE == MOUSE_MOVE_RELATIVE:
      if mouse.lLastX != 0:
        events.append(InputEvent(codes.EV_REL, codes.REL_X, mouse.lLastX, ts, source))
      if mouse.lLastY != 0:
        events.append(InputEvent(codes.EV_REL, codes.REL_Y, mouse.lLastY, ts, source))
    elif mouse.usFlags & MOUSE_MOVE_ABSOLUTE == MOUSE_MOVE_ABSOLUTE:
      events.append(InputEvent(codes.EV_ABS, codes.REL_X, mouse.lLastX, ts, source))
      events.append(InputEvent(codes.EV_ABS, codes.REL_Y, mouse.lLastY, ts, source))
    if usButtonFlags & RI_MOUSE_WHEEL:
      #usButtonData is actually a signed value, and ctypes support only pointer casts,
      #so converting it this way
      delta = cast(pointer(USHORT(mouse._u1._s2.usButtonData)), POINTER(SHORT)).contents.value
      events.append(InputEvent(codes.EV_REL, codes.REL_WHEEL, delta, ts, source))
    codeMapping = (
      (RI_MOUSE_LEFT_BUTTON_DOWN, codes.BTN_LEFT, 1),
      (RI_MOUSE_LEFT_BUTTON_UP, codes.BTN_LEFT, 0),
      (RI_MOUSE_RIGHT_BUTTON_DOWN, codes.BTN_RIGHT, 1),
      (RI_MOUSE_RIGHT_BUTTON_UP, codes.BTN_RIGHT, 0),
      (RI_MOUSE_MIDDLE_BUTTON_DOWN, codes.BTN_MIDDLE, 1),
      (RI_MOUSE_MIDDLE_BUTTON_UP, codes.BTN_MIDDLE, 0),
      #TODO Check
      (RI_MOUSE_BUTTON_4_DOWN, codes.BTN_SIDE, 1),
      (RI_MOUSE_BUTTON_4_UP, codes.BTN_SIDE, 0),
      (RI_MOUSE_BUTTON_5_DOWN, codes.BTN_EXTRA, 1),
      (RI_MOUSE_BUTTON_5_UP, codes.BTN_EXTRA, 0)
    )
    for cm in codeMapping:
      if usButtonFlags & cm[0]:
        events.append(InputEvent(codes.EV_KEY, cm[1], cm[2], ts, source))
    return events

  def make_kbd_event_(self, raw, source):
    ts = time.time()
    v = 1 if (raw.keyboard.Flags & 1) == RI_KEY_MAKE else 0
    #logger.debug("raw.keyboard: MakeCode: 0x{:04x}, Flags: 0x{:04x}, Message: 0x{:04x}, VKey: 0x{:x}".format(raw.keyboard.MakeCode, raw.keyboard.Flags, raw.keyboard.Message, raw.keyboard.VKey))
    return (InputEvent(codes.EV_KEY, makecode2code(raw.keyboard.MakeCode, raw.keyboard.Flags), v, ts, source),)


def print_devices():
  devices = RawInputEventSource().get_devices()
  for d in devices:
    print "name: {}\nhandle: {}\ntype: {} ({})\n".format(d.name, d.handle, rimtype2str(d.type), d.type)


def run():
  def init_outputs(settings):
    nameParser = lambda key,state : key
    parser = settings["parser"]
    outputParser = parser.get("output")
    orderOp = lambda i : i[1].get("seq", 100000)
    cfg = settings["config"]["outputs"]
    state = {"settings" : settings, "parser" : parser}
    outputs = {}
    settings["outputs"] = outputs
    parse_dict_live_ordered(outputs, cfg, state=state, kp=nameParser, vp=outputParser, op=orderOp, update=False)

  def init_source(settings):
    config = settings["config"]
    sink = init_main_sink(settings, init_layout_config)
    source = RawInputEventSource(useMessageWindow=config.get("useMessageWindow", True))
    for s,n in config["inputs"].items():
      try:
        source.track_device(n, s)
      except RuntimeError as e:
        logger.warning(e)
    source.set_sink(sink)
    oldSource = settings.get("source")
    #settings["source"].stop()
    settings["source"] = source
    if oldSource:
      if hasattr(oldSource, "stop"):
        oldSource.stop()
      del oldSource

  def init_and_run(settings):
    oldUpdated = [v for v in settings.get("updated")]
    try:
      try:
        init_config2(settings)
        init_source(settings)
        refreshRate = settings["config"].get("refreshRate", 100.0)
        step = 1.0 / refreshRate
        source = settings["source"]
        assert(source is not None)
        def run_source(tick, ts):
          source.run_once()
        updated = settings.get("updated", [])
        def run_updated(tick, ts):
          for u in updated:
            u(tick, ts)
        callbacks = [run_source, run_updated]
        loop = Loop(callbacks, step)
        if "loop" in settings: del settings["loop"]
        settings["loop"] = loop
        settings["reloading"] = False
      except Exception as e:
        logger.error("Could not create or recreate loop; reason: '{}'".format(e))
        logger.error("===Traceback begin===")
        for l in traceback.format_exc().splitlines()[-21:]:
          logger.error(l)
        logger.error("===Traceback end===")
        if settings.get("loop") is not None:
          logger.error("Falling back to previous state.")
        else:
          raise Exception("No valid state to fall back to.")

      loop = settings["loop"]
      assert(loop is not None)
      loop.run()
    finally:
      if oldUpdated is not None:
        settings["updated"] = oldUpdated

  init_log_initial()
  try:
    settings = {"options" : {}, "configNames" : [], "updated" : []}
    options = {}
    settings["options"] = options

    opts, args = getopt.getopt(sys.argv[1:], "pl:v:c:", ["print", "layout=", "logLevel=", "config="])
    for o, a in opts:
      if o in ("-p", "--print"):
        print_devices()
        return 0
      if o in ("-l", "--layout"):
        options["layout"] = a
      elif o in ("-v", "--logLevel"):
        options["logLevel"] = a
      elif o in ("-c", "--config"):
        settings["configNames"].append(a)

    parser = make_parser()
    settings["parser"] = parser
    parser.get("output").add("ppjoy", parsePPJoystickOutput)
    parser.get("output").add("di_keyboard", parseDirectInputKeyboardOutput)

    settings["reloading"] = False
    init_config2(settings)
    set_log_level(settings)
    init_outputs(settings)

    while (True):
      try:
        r = init_and_run(settings)
      except ReloadException:
        logger.info("Reloading")
        settings["reloading"] = True
      except Exception as e:
        logger.error("Unexpected exception: {}".format(e))
        raise

  except KeyboardInterrupt:
    logger.info("Exiting normally")
    return 0
  except ConfigReadError as e:
    logger.error(e)
    return 1


if __name__ == "__main__":
  try:
    exit(run())
  except Exception as e:
    print "Uncaught exception: {} ({})".format(type(e), e)
    for l in traceback.format_exc().splitlines()[-11:]:
      print l
    exit(2)
