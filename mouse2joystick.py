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
  nativeLimit_ = 32767

  def __init__(self, limits, buttons=None, name=None, phys=None):
    axesData = []
    for a,l in limits.items():
      axesData.append((a, AbsInfo(value=0, min=-self.nativeLimit_, max=self.nativeLimit_, fuzz=0, flat=0, resolution=0)))
    cap = { ecodes.EV_ABS : axesData }
    if buttons: cap[ecodes.EV_KEY] = buttons
    self.js = None
    if name is None: name='virtual-joystick'
    self.js = UInput(cap, name=name, version=0x3, phys=phys)

    self.coords = {}
    for a,l in limits.items():
      self.coords[a] = (l[1] + l[0])/2

    self.limits = limits

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
    self.move_axis_to(axis, self.get_axis_value(axis)+v)

  def move_axis_to(self, axis, v):
    if axis not in self.coords:
      return
    v = clamp(v, *self.limits.get(axis, (0.0, 0.0)))
    self.coords[axis] = v
    maxAbsLimit = max((abs(l) for l in self.limits[axis]))
    v = int(v * self.nativeLimit_ / maxAbsLimit)
    #logger.debug("{}: Moving axis {} to {}".format(self, axis, v))
    self.js.write(ecodes.EV_ABS, code2ecode(axis), v)
    self.js.syn()

  def get_axis_value(self, axis):
    return self.coords.get(axis, 0.0)

  def get_limits(self, axis):
    return self.limits[axis]

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
    event = translate_evdev_event(self.dev_.read_one(), self.source_)
    #logger.debug("{}: read event: {}".format(self, event))
    return event

  def swallow(self, s):
    if s:
      self.dev_.grab()
    else:
      self.dev_.ungrab()

  def __init__(self, dev, source):
    self.dev_, self.source_ = dev, source


def init_inputs(names):
  devices = [evdev.InputDevice(fn) for fn in evdev.list_devices()]
  r = {}
  for s,n in names.items():
    for d in devices:
      if n in (d.path, d.name.strip(" "), d.phys):
        r[s] = EvdevDevice(d, s)
        logger.info("Found device {} ({})".format(s, n))
        break
    else:
      logger.warning("Device {} ({}) not found".format(s, n))
  return r


def print_devices():
  devices = [evdev.InputDevice(fn) for fn in evdev.list_devices()]
  for d in devices:
    caps = d.capabilities(verbose=True, absinfo=False)
    capsInfo = ""
    for k,v in caps.items():
      keyName = k[0]
      codeNames = ", ".join((str(i[0]) for i in v))
      capsInfo += " {}: {}\n".format(keyName, codeNames)
    print "name: {}\npath: {}\ncaps:\n{}fn: {}\ninfo: {}\nphys: {}\nuniq: {}\n".format(d.name, d.path, capsInfo, d.fn, d.info, d.phys, d.uniq)


def parseEvdevJoystickOutput(cfg, state):
  buttons = [code2ecode(name2code(buttonName)) for buttonName in cfg["buttons"]]
  limits = {code2ecode(name2code(a)):l for a,l in cfg.get("limits", {}).items()}
  return EvdevJoystick(limits, buttons, cfg.get("name", ""), cfg.get("phys", ""))


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
    try:
      init_config2(settings)
      config = settings["config"]

      settings["inputs"] = init_inputs(config["inputs"])

      sink = init_main_sink(settings, init_layout_config)
      updated = settings.get("updated", [])

      settings["source"] = EventSource(settings["inputs"].values(), sink)

    except Exception as e:
      logger.error(e)
      for l in traceback.format_exc().splitlines()[-11:]:
        logger.error(l)

  def unswallow_inputs(settings):
    for i in settings["inputs"].values():
      try:
        i.swallow(False)
      except IOError as e:
        logger.debug("got IOError ({}), but that was expected".format(e))
        continue

  def init_and_run(settings):
    oldUpdated = [o for o in settings["updated"]]
    init_source(settings)
    source = settings.get("source", None)
    if source is None:
      raise Exception("No valid state")
    updated = settings.get("updated", [])
    refreshRate = settings["config"].get("refreshRate", 100.0)
    step = 1.0 / refreshRate
    def run_source(tick, ts):
      source.run_once()
    def run_updated(tick, ts):
      for u in updated:
        u(tick, ts)
    callbacks = [run_source, run_updated]
    loop = Loop(callbacks, step)
    try:
      loop.run()
    finally:
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
    parser.get("output").add("evdev", parseEvdevJoystickOutput)

    init_config2(settings)
    set_log_level(settings)
    init_outputs(settings)

    while (True):
      try:
        r = init_and_run(settings)
      except ReloadException:
        logger.info("Reloading")
      finally:
        unswallow_inputs(settings)

  except KeyboardInterrupt:
    logger.info("Exiting normally")
    return 0
  except ConfigReadError as e:
    logger.error(e)
    return 1


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
    print "Uncaught exception: {} ({})".format(type(e), e)
    for l in traceback.format_exc().splitlines()[-11:]:
      print l
    exit(2)
