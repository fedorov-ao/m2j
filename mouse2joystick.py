#!/usr/bin/python

#Mouse to joystick emulator for Linux

#Dependencies:
#Python evdev module and uinput
#Maybe need to "modprobe -i uinput"

#To run without sudo:
#Add user to group "input" and relogin
#Change "/dev/uinput" group to "input" and change group permissions of "/dev/uinput" to "rw"

import sys
sys.path.append(".")
import getopt
import traceback
import logging
import m2j
from m2j import *
import evdev
from evdev import UInput, AbsInfo, ecodes

logger = logging.getLogger(__name__)

def code2ecode(code):
  return code

def ecode2code(code):
  return code


class EvdevJoystick:
  def __init__(self, axes, limit, buttons=None):
    axesData = []
    for a in axes:
      axesData.append((a, AbsInfo(value=0, min=-limit, max=limit, fuzz=0, flat=0, resolution=0)))
    cap = { ecodes.EV_ABS : axesData }
    if buttons: cap[ecodes.EV_KEY] = buttons
    self.js = UInput(cap, name='virtual-joystick', version=0x3)

    self.coords = {}
    for a in axes:
      self.coords[a] = 0

    self.limit = limit

  def move_axis(self, axis, v, relative):
    if relative:
      self.move_axis_by(axis, v)
    else:
      self.move_axis_to(axis, v)

  def move_axis_by(self, axis, v):
    self.move_axis_to(axis, self.coords[axis]+v)

  def move_axis_to(self, axis, v):
    v = clamp(v, -1.0, 1.0)
    self.coords[axis] = v
    self.js.write(ecodes.EV_ABS, code2ecode(axis), int(v*self.limit))
    self.js.syn()

  def get_axis(self, axis):
    return self.coords[axis]

  def set_button_state(self, button, state):
    self.js.write(ecodes.EV_KEY, code2ecode(button), state)
    self.js.syn()


def translate_evdev_event(evdevEvent, source):
  return None if evdevEvent is None else InputEvent(ecode2code(evdevEvent.type), ecode2code(evdevEvent.code), evdevEvent.value, evdevEvent.timestamp(), source)


class EvdevDevice:
  def read_one(self):
    assert(self.dev_)
    return translate_evdev_event(self.dev_.read_one(), self.source_)

  def swallow(self, s):
    if s:
      self.dev_.grab()
    else:
      self.dev_.ungrab()

  def __init__(self, dev, source):
    self.dev_, self.source_ = dev, source


def find_devices(names):
  devices = [evdev.InputDevice(fn) for fn in evdev.list_devices()]
  r = []
  for n, s in names:
    for d in devices:
      if n == d.name:
        r.append(EvdevDevice(d, s))
  return r
  
  
def run():
  settings = {"layout" : "base", "curves" : "distance", "log_level" : "CRITICAL"}

  opts, args = getopt.getopt(sys.argv[1:], "l:c:o:", ["layout=", "curves=", "log_level="])
  for o, a in opts:
    if o in ("-l", "--layout"):
      settings["layout"] = a
    elif o in ("-c", "--curves"):
      settings["curves"] = a
    elif o in ("-o", "--log_level"):
      settings["log_level"] = a

  logLevelName = settings["log_level"].upper()
  nameToLevel = {logging.getLevelName(l).upper():l for l in (logging.CRITICAL, logging.ERROR, logging.WARNING, logging.INFO, logging.DEBUG, logging.NOTSET)}
  print("Setting log level to {}".format(logLevelName))
  logLevel = nameToLevel.get(logLevelName, logging.NOTSET)
  root = logging.getLogger()
  root.setLevel(logLevel)
  handler = logging.StreamHandler(sys.stdout)
  handler.setLevel(logLevel)
  handler.setFormatter(logging.Formatter("%(name)s:%(levelname)s:%(message)s"))
  root.addHandler(handler)

  names = (("B16_b_02 USB-PS/2 Optical Mouse", 0), ('HID 0461:4d04', 2), ("HID Keyboard Device", 1))
  devices = find_devices(names)

  axes = [codes.ABS_X, codes.ABS_Y, codes.ABS_Z, codes.ABS_RX, codes.ABS_RY, codes.ABS_RZ, codes.ABS_THROTTLE, codes.ABS_RUDDER]
  limit = 32767
  buttons = [codes.BTN_0, codes.BTN_1]
  joystick = EvdevJoystick(axes, limit, buttons)
  head = CompositeJoystick((EvdevJoystick(axes, limit), Opentrack("127.0.0.1", 5555)))
  
  settings["mouse"] = next((d for d in devices if d.source_ == 0), None)
  settings["mouse2"] = next((d for d in devices if d.source_ == 2), None)
  settings["joystick"] = joystick 
  settings["head"] = head

  settings["modes"] = {}
  settings["modes"]["head"] = {}
  settings["modes"]["head"]["curves"] = {}
  settings["modes"]["head"]["curves"]["zoom"] = DirectionBasedCurve2(((1.0,1.0), (0.5,0.75), (0.5,0.5), (0.5,0.25),))

  settings["sens"] = {codes.REL_X:0.005, codes.REL_Y:0.005, codes.REL_WHEEL:0.01,}


  initializer = sink_initializers.get(settings["layout"], None)
  if not initializer:
    raise Exception("Initialiser for {} not found".format(settings["layout"]))
  else:
    print("Initializing for {}, using {} curves".format(settings["layout"], settings["curves"]))

  sink = initializer(settings)

  step = 0.01
  source = EventSource(devices, sink, step)


  source.run_loop()
  return 0


def test():
  def get_callback(n):
    def callback(event):
      print "callback '{}' called with event {}".format(n, event)
    return callback

  class Event:
    def __init__(self, type, code, value):
      self.type, self.code, self.value = type, code, value

    def __str__(self):
      return "type: {}; code: {}; value: {}".format(self.type, self.code, self.value)

  data = [
    [[("type", codes.EV_REL), ("code", e.ABS_X)], get_callback("axis x")],
    [[("type", codes.EV_KEY), ("code", e.KEY_Z)], get_callback("key z")],
    [[("type", codes.EV_KEY), ("code", e.KEY_Z), ("value", 1)], get_callback("key z press")],
  ]
  sink = BindingSink(data)

  sink(Event(codes.EV_REL, e.ABS_X, 0))
  sink(Event(codes.EV_REL, e.ABS_X, 1))
  sink(Event(codes.EV_KEY, e.KEY_Z, 0))
  sink(Event(codes.EV_KEY, e.KEY_Z, 1))


def print_tech_data():
  #print evdev.codes.EV 
  constsList = []
  for d in (evdev.ecodes.EV, evdev.ecodes.ABS, evdev.ecodes.REL, evdev.ecodes.BTN, evdev.ecodes.KEY):
    for k, v in d.items():
      if isinstance(v, list):
        for vv in v:
          constsList.append((vv, k))
      else:
        constsList.append((v, k))
  constsList.sort(key=lambda x : x[0])
  print "{",
  for d in constsList:
    print "'{}':{},".format(*d),
  print "}"
  print dict(constsList)
    

if __name__ == "__main__":
  try:
    exit(run())
  except Exception as e:
    print("Exception: {} ({})".format(type(e), e))
    print(traceback.print_tb(sys.exc_info()[2]))
    exit(2)
  except KeyboardInterrupt:
    exit(0)
