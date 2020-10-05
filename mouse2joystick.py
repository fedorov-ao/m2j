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
import gc
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
    self.js = None
    self.js = UInput(cap, name='virtual-joystick', version=0x3)

    self.coords = {}
    for a in axes:
      self.coords[a] = 0.0

    self.limit = limit

    logger.debug("{} created".format(self))

  def __del__(self):
    if self.js is not None: 
      self.js.close()
    logger.debug("{} destroyed".format(self))

  def move_axis(self, axis, v, relative):
    if relative:
      self.move_axis_by(axis, v)
    else:
      self.move_axis_to(axis, v)

  def move_axis_by(self, axis, v):
    self.move_axis_to(axis, self.get_axis(axis)+v)

  def move_axis_to(self, axis, v):
    if axis not in self.coords:
      return
    v = clamp(v, -1.0, 1.0)
    self.coords[axis] = v
    self.js.write(ecodes.EV_ABS, code2ecode(axis), int(v*self.limit))
    self.js.syn()

  def get_axis(self, axis):
    return self.coords.get(axis, 0.0)

  def get_limits(self, axis):
    return (-1.0, 1.0)

  def get_supported_axes(self):
    return self.coords.keys()

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
  r = {}
  for s,n in names.items():
    for d in devices:
      if n == d.name:
        r[s] = EvdevDevice(d, s)
  return r
  

def print_devices():
  devices = [evdev.InputDevice(fn) for fn in evdev.list_devices()]
  for d in devices:
    print "{} : {}; {}".format(d.name, [f for f,s in d.capabilities(verbose=True, absinfo=False).keys()], d.fn) 

  
def run():
  def init_joysticks(settings):
    axes = [codes.ABS_X, codes.ABS_Y, codes.ABS_Z, codes.ABS_RX, codes.ABS_RY, codes.ABS_RZ, codes.ABS_THROTTLE, codes.ABS_RUDDER]
    limit = 32767
    buttons = [codes.BTN_0, codes.BTN_1]

    if "outputs" not in settings: settings["outputs"] = {}
    outputs = settings["outputs"]
    if "joystick" in outputs: del outputs["joystick"]
    outputs["joystick"] = EvdevJoystick(axes, limit, buttons)
    if "head" in outputs: del outputs["head"]
    opentrack = Opentrack("127.0.0.1", 5555)
    if "updated" not in settings: settings["updated"] = []
    updated = settings["updated"]
    updated.append(lambda : opentrack.send())
    il2Head = UdpJoystick("127.0.0.1", 6543, make_il2_6dof_packet)
    updated.append(lambda : il2Head.send())
    outputs["head"] = CompositeJoystick((EvdevJoystick(axes, limit), opentrack, il2Head))

  def run2(settings):
    init_config2(settings)
    config = settings["config"]

    settings["inputs"] = find_devices(config["inputs"])

    initializer = layout_initializers.get(config["layout"], None)
    if not initializer:
      raise Exception("Initialiser for '{}' not found".format(config["layout"]))
    else:
      logger.info("Initializing for '{}' layout, using '{}' curves".format(config["layout"], config["curves"]))
    sink = init_main_sink(settings, initializer)

    step = 0.01
    source = EventSource(settings["inputs"].values(), sink, step)

    updated = settings.get("updated", [])
    try:
      while True:
        source.run_once(sleep=True)
        for u in updated: u()
    except ReloadException:
      return -1
    except KeyboardInterrupt:
      return 0

  settings = {"options" : {}, "configNames" : []}
  options = {}
  settings["options"] = options

  opts, args = getopt.getopt(sys.argv[1:], "pl:c:f:o:n:", ["print", "layout=", "curves=", "configCurves=", "logLevel=", "config="])
  for o, a in opts:
    if o in ("-p", "--print"):
      print_devices()
      return 0
    if o in ("-l", "--layout"):
      options["layout"] = a
    elif o in ("-c", "--curves"):
      options["curves"] = a
    elif o in ("-f", "--configCurves"):
      options["configCurves"] = a
    elif o in ("-o", "--logLevel"):
      options["logLevel"] = a
    elif o in ("-n", "--config"):
      settings["configNames"].append(a)

  init_config2(settings)
  init_log(settings)
  init_joysticks(settings)

  while (True):
    r = run2(settings)
    if r == -1: 
      logger.info("Reloading")
    else:
      logger.info("Exiting with code {}".format(r))
      return r


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
