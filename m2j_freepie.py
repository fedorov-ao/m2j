import sys
sys.path.append(".")

import time
import ctypes
from ctypes import wintypes, windll

import m2j
from m2j import *

g_w2nKeyMapping = {
  codes.KEY_SCROLLLOCK : Key.ScrollLock,
  codes.KEY_RIGHTSHIFT : Key.RightShift,
  codes.KEY_LEFTSHIFT : Key.LeftShift,
  codes.KEY_RIGHTCTRL : Key.RightControl,
  codes.KEY_LEFTCTRL : Key.LeftControl,
  codes.KEY_RIGHTALT : Key.RightAlt,
  codes.KEY_LEFTALT : Key.LeftAlt,
  codes.BTN_LEFT : 0,
  codes.BTN_RIGHT : 1,
  codes.BTN_MIDDLE : 2,
  codes.BTN_SIDE : 3,
  codes.BTN_EXTRA : 4,
  codes.BTN_0 : 0,
  codes.BTN_1 : 1,
}

def w2n_key(k):
  """Wrapper-to-native key conversion"""
  return g_w2nKeyMapping.get(k, None)

g_w2nAxisMapping = {
  codes.ABS_X : AxisTypes.X,
  codes.ABS_Y : AxisTypes.Y,
  codes.ABS_Z : AxisTypes.ZAxis,
  codes.ABS_RX : AxisTypes.ZRotation,
  codes.ABS_RY : AxisTypes.Slider,
  codes.ABS_RZ : AxisTypes.XRotation,
  codes.ABS_THROTTLE : AxisTypes.YRotation,
  codes.ABS_RUDDER : AxisTypes.Dial
}

def w2n_axis(a):
  """Wrapper-to-native key conversion"""
  return g_w2nAxisMapping.get(a, None)

class PollingKeyDevice:
  def read_one(self):
    if (len(self.events_) == 0):
      return None
    else:
      return self.events_.pop()

  def update(self):
    value = None
    for i in xrange(len(self.keys_)):
      wKey = self.keys_[i]
      s, prev = self.get_key_value_(wKey), self.states_[i]
      if s != prev:
        if s and not prev:
          #pressed
          value = 1
        elif not s and prev:
          #released
          value = 0
        self.states_[i] = s

        self.append_event_(codes.EV_KEY, wKey, value)

  def append_event_(self, t, code, value):
    self.events_.append(InputEvent(t, code, value, time.time(), self.id_))

  def __init__(self, id, keys, get_key_value):
    self.id_ = id
    self.keys_ = keys
    self.get_key_value_ = get_key_value

    self.events_ = []
    self.states_ = [0 for i in xrange(len(self.keys_))]


class PollingAxisDevice:
  def read_one(self):
    if (len(self.events_) == 0):
      return None
    else:
      return self.events_.pop()

  def update(self):
    value = None
    for i in xrange(len(self.axes_)):
      ad = self.axes_[i]
      value = self.get_axis_value_(ad[1])
      if value != 0.0:
        self.append_event_(ad[0], ad[1], value)

  def append_event_(self, t, code, value):
    self.events_.append(InputEvent(t, code, value, time.time(), self.id_))

  def __init__(self, id, axes, get_axis_value):
    self.id_ = id
    self.axes_ = axes
    self.get_axis_value_ = get_axis_value

    self.events_ = []

def mouseAxisReporter(wAxis):
  v = 0.0
  if wAxis == codes.REL_X: v = mouse.deltaX
  elif wAxis == codes.REL_Y: v = mouse.deltaY
  elif wAxis == codes.REL_WHEEL: v = mouse.wheel
  return v

def keyboardKeyReporter(wKey):
  return keyboard.getKeyDown(w2n_key(wKey))

class CompositePollingDevice:
  def read_one(self):
    event = None
    while self.i_ != len(self.children_):
      event = self.children_[self.i_].read_one()
      if event is None:
        self.i_ += 1
      else:
        break
    return event

  def update(self):
    for c in self.children_:
      c.update()
    self.i_ = 0

  def add(self, child):
    self.children_.append(child)
    self.i_ = 0

  def __init__(self):
    self.children_ = []
    self.i_ = 0


#Does not work
class MouseBlocker:
  user32 = ctypes.windll.user32
  kernel32 = ctypes.windll.kernel32
  wintypes = ctypes.wintypes

  WH_MOUSE_LL=14

  def swallow(self, s):
    if s != self.s_:
      if s == True:
        assert(self.hookId_ is None)
        self.hookId_ = self.user32.SetWindowsHookExA(self.WH_MOUSE_LL, self.hook_, self.kernel32.GetModuleHandleA(None), 0)
        if not self.hookId_:
          raise OSError("Failed to install mouse hook")
      else:
        assert(self.hookId_ is not None)
        b = self.user32.UnhookWindowsHookEx(self.hookId_)
        if not b:
          raise OSError("Failed to remove mouse hook")
        self.hookId_ = None
    self.s_ = s

  def hook(nCode, wParam, lParam):
    return self.user32.CallNextHookEx(None, nCode, wParam, lParam)

  def __init__(self):
    self.s_ = False
    self.hookId_ = None
    CMPFUNC = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p))
    self.hook_ = CMPFUNC(self.hook)


class CursorBlocker:
  """Blocks mouse cursor movement by confining it in 1x1 rectangle at current cursor pos.
     Does not block mouse buttons.
  """
  user32 = ctypes.windll.user32
  kernel32 = ctypes.windll.kernel32
  wintypes = ctypes.wintypes

  def swallow(self, s):
    if s != self.s_:
      self.s_ = s
      if s == True:
        if not self.user32.GetClipCursor(ctypes.byref(self.r_)):
          raise Exception("Failed to retrieve current cursor clip rectangle")
        p = wintypes.POINT()
        if not self.user32.GetCursorPos(ctypes.byref(p)):
          raise Exception("Failed to get current cursor position")
        r = wintypes.RECT(p.x, p.y, p.x+1, p.y+1)
        if not self.user32.ClipCursor(ctypes.byref(r)):
          raise Exception("Failed to set current cursor clip rectangle")
      else:
        if not self.user32.ClipCursor(ctypes.byref(self.r_)):
          raise Exception("Failed to restore current cursor clip rectangle")

  def __init__(self):
    self.s_, self.r_ = False, wintypes.RECT()


class FreePIEMouse2:
  def read_one(self):
    return self.be_.read_one()

  def update(self):
    self.be_.update()

  def swallow(self, s):
    if self.blocker_ is not None:
        self.blocker_.swallow(s)

  def __init__(self, axisDevice, keyDevice, blocker):
    self.be_ = CompositePollingDevice()
    self.be_.add(axisDevice)
    self.be_.add(keyDevice)
    self.blocker_ = blocker


class FreePIEMouse:
  def read_one(self):
    if (len(self.events_) == 0):
      return None
    else:
      return self.events_.pop()

  def swallow(self, s):
    pass

  def update(self):
    dx, dy, dw = mouse.deltaX, mouse.deltaY, mouse.wheel
    diagnostics.watch(dw)
    if dx !=0:
      self.append_event_(codes.EV_REL, codes.REL_X, dx)
    if dy !=0:
      self.append_event_(codes.EV_REL, codes.REL_Y, dy)
    if dw != 0:
      self.append_event_(codes.EV_REL, codes.REL_WHEEL, dw)

  def append_event_(self, t, code, value):
    self.events_.append(InputEvent(t, code, value, time.time(), self.source_))

  def __init__(self, source):
    self.source_ = source
    self.events_ = []

class PPJoystick:
  def move_axis(self, axis, v, relative = True):
    if relative:
      v += self.v_[axis]
    v = clamp(v, -1.0, 1.0)
    self.v_[axis] = v

    self.ppj_.setAxis(w2n_axis(axis), v*self.scales_[axis])

  def get_axis_value(self, axis):
    return self.v_[axis]

  def get_limits(self, axis):
    return (-1.0, 1.0)

  def get_supported_axes(self):
    return self.v_.keys()

  def set_button_state(self, button, state):
    self.ppj_.setButton(w2n_key(button), state)

  def __init__(self, id, scales):
    self.ppj_ = ppJoy[id]
    self.scales_ = scales
    self.v_ = dict()
    for a in self.scales_.keys():
      self.v_[a] = 0.0

if starting:
  reload(m2j)
  global logger

  settings = {"options" : {}, "configNames" : [], "updated" : []}
  settings["options"] = {"layout" : "base8_cfg", "logLevel" : "DEBUG" }
  settings["configNames"] = ["curves.cfg", "m2j_freepie.cfg"]
  settings["parser"] = make_parser()

  init_config2(settings)

  class DiagnosticsStream:
    def write(self, s):
      diagnostics.debug(s.strip("\n"))
    def flush(self):
      pass
  init_log_initial(handler=logging.StreamHandler(DiagnosticsStream()))
  set_log_level(settings)
  logger = logging.getLogger(__name__)

  mouseAxisDevice = PollingAxisDevice(
    "mouse",
    ((codes.EV_REL, codes.REL_X), (codes.EV_REL, codes.REL_Y), (codes.EV_REL, codes.REL_WHEEL)),
    mouseAxisReporter
  )
  mouseKeyDevice = PollingKeyDevice(
    "mouse",
    (codes.BTN_LEFT, codes.BTN_RIGHT, codes.BTN_MIDDLE, codes.BTN_SIDE, codes.BTN_EXTRA),
    lambda wKey : mouse.getButton(w2n_key(wKey))
  )
  ms = FreePIEMouse2(mouseAxisDevice, mouseKeyDevice, CursorBlocker())
  #ms = FreePIEMouse2(mouseAxisDevice, mouseKeyDevice, None)
  kbd = PollingKeyDevice(
    "keyboard",
    (codes.KEY_SCROLLLOCK, codes.KEY_LEFTSHIFT, codes.KEY_RIGHTSHIFT, codes.KEY_LEFTCTRL, codes.KEY_RIGHTCTRL, codes.KEY_LEFTALT, codes.KEY_RIGHTALT),
    keyboardKeyReporter
  )
  settings["inputs"] = {"mouse" : ms, "keyboard" : kbd}

  joystick = PPJoystick(
    0,
    {codes.ABS_X : 999.0, codes.ABS_Y : 999.0, codes.ABS_Z : 999.0, codes.ABS_RX : 999.0, codes.ABS_RY : 999.0, codes.ABS_RZ : 999.0, codes.ABS_RUDDER : 999.0, codes.ABS_THROTTLE : 999.0,}
  )
  headJoystick = PPJoystick(
    1,
    {codes.ABS_X : 999.0, codes.ABS_Y : 999.0, codes.ABS_Z : 999.0, codes.ABS_RX : 999.0, codes.ABS_RY : 999.0, codes.ABS_RZ : 999.0, codes.ABS_RUDDER : 999.0, codes.ABS_THROTTLE : 999.0,}
  )
  headOpentrack = Opentrack("127.0.0.1", 5555)
  settings["updated"].append(lambda tick : headOpentrack.send())
  head = CompositeJoystick([headJoystick, headOpentrack])
  settings["outputs"] = {"joystick" : joystick, "head" : head}

  sink = init_main_sink(settings, init_layout_config)

  inputs = settings["inputs"].values()
  def run_inputs(tick):
    for i in inputs:
      i.update()
  source = EventSource(inputs, sink)
  def run_source(tick):
    source.run_once()
  updated = settings["updated"]
  def run_updated(tick):
    for u in updated:
      u(tick)

  callbacks = [run_inputs, run_source, run_updated]
  global g_loop
  g_loop = Loop(callbacks, 0.0)

g_loop.run_once()
