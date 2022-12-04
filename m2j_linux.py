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
import m2j
from m2j import *
import collections
import re
import evdev
from evdev import UInput, AbsInfo, ecodes

logger = logging.getLogger(__name__)

def code2ecode(code):
  return code

def ecode2code(code):
  return code


class EvdevJoystick:
  def __init__(self, limits, buttons=None, name=None, phys=None, immediateSyn=True, nativeLimit=32767):
    self.nativeLimit_ = nativeLimit
    self.immediateSyn_ = immediateSyn
    self.dirty_ = False
    self.js_ = None
    self.limits_ = limits
    self.axes_ = {}

    cap = {}
    axesData = []
    for a,l in limits.items():
      value = (l[1] + l[0])/2
      self.axes_[a] = value
      axesData.append((code2ecode(a), AbsInfo(value=value, min=-self.nativeLimit_, max=self.nativeLimit_, fuzz=0, flat=0, resolution=0)))
    cap[ecodes.EV_ABS] = axesData

    if buttons is not None:
      cap[ecodes.EV_KEY] = [code2ecode(b) for b in buttons]
    self.buttons_ = { b:False for b in buttons } if buttons is not None else {}

    if name is None:
      name='virtual-joystick'
    self.js_ = UInput(cap, name=name, version=0x3, phys=phys)

    logger.debug("{} created".format(self))

  def __del__(self):
    if self.js_ is not None:
      self.js_.close()
    logger.debug("{} destroyed".format(self))

  def move_axis(self, axis, v, relative):
    if relative:
      return self.move_axis_by(axis, v)
    else:
      return self.move_axis_to(axis, v)

  def move_axis_by(self, axis, v):
    desired = self.get_axis_value(axis)+v
    actual = self.move_axis_to(axis, desired)
    return v - (actual - desired)

  def move_axis_to(self, axis, v):
    if axis not in self.axes_:
      raise RuntimeError("Axis not supported: {}".format(axis))
    l = self.limits_.get(axis, (0.0, 0.0,))
    v = clamp(v, *l)
    self.axes_[axis] = v
    nv = lerp(v, l[0], l[1], -self.nativeLimit_, self.nativeLimit_)
    nv = int(nv)
    #logger.debug("{}: Moving axis {} to {}, native {}".format(self, typecode2name(codes.EV_ABS, axis), v, nv))
    self.js_.write(ecodes.EV_ABS, code2ecode(axis), nv)
    if self.immediateSyn_ == True:
      self.js_.syn()
    else:
      self.dirty_ = True
    return v

  def get_axis_value(self, axis):
    return self.axes_.get(axis, 0.0)

  def get_limits(self, axis):
    return self.limits_.get(axis, [0.0, 0.0])

  def get_supported_axes(self):
    return self.axes_.keys()

  def set_button_state(self, button, state):
    if button not in self.buttons_:
      raise RuntimeError("Button not supported: {}".format(button))
    self.buttons_[button] = state
    self.js_.write(ecodes.EV_KEY, code2ecode(button), state)
    if self.immediateSyn_ == True:
      self.js_.syn()
    else:
      self.dirty_ = True

  def get_button_state(self, button):
    if button not in self.buttons_:
      raise RuntimeError("Button not supported: {}".format(button))
    return self.buttons_[button]

  def get_supported_buttons(self):
    return self.buttons_.keys()

  def update(self, tick, ts):
    if self.immediateSyn_ == False and self.dirty_ == True:
      self.js_.syn()
      self.dirty_ = False


def translate_evdev_event(evdevEvent, source):
  return None if evdevEvent is None else InputEvent(ecode2code(evdevEvent.type), ecode2code(evdevEvent.code), evdevEvent.value, evdevEvent.timestamp(), source)


class EvdevDevice:
  def read_one(self):
    if not self.is_ready_():
      return
    try:
      evdevEvent = self.dev_.read_one()
      while (evdevEvent is not None) and (evdevEvent.type == 0):
        evdevEvent = self.dev_.read_one()
      event = translate_evdev_event(evdevEvent, self.sourceHash_)
      if event is None:
        if self.numEvents_ != 0:
          #logger.debug("{}: {} got {} events".format(self, self.sourceName_, self.numEvents_))
          self.numEvents_ = 0
      else:
        #logger.debug("{}: {} read event: {}".format(self, self.sourceName_, event))
        self.numEvents_ += 1
      return event
    except IOError as e:
      self.numEvents_ = 0
      self.dev_ = None
      logger.error("{}: device is not ready: {}".format(self.sourceName_, e))

  def swallow(self, s):
    if not self.is_ready_():
      return
    if s:
      self.dev_.grab()
    else:
      self.dev_.ungrab()

  def __init__(self, dev, source, recreateOp=lambda : None):
    self.dev_, self.sourceName_, self.recreateOp_ = dev, source, recreateOp
    self.sourceHash_ = calc_hash(source)
    register_source(source)
    self.numEvents_ = 0

  def is_ready_(self):
    if self.dev_ is not None:
      return True
    dev = self.recreateOp_()
    if dev is not None:
      self.dev_ = dev
      logger.info("{}: device is ready".format(self.sourceName_))
      return True
    else:
      return False


def calc_device_hash(device):
    caps = device.capabilities(verbose=False, absinfo=False)
    info = tuple((k, tuple(i for i in v),) for k,v in caps.items())
    info = (device.name, info,)
    return hash(info)


def make_evdev_devices(inputsData):
  """{source : identifier (name, path, hash, phys)} -> {source : native evdev device}"""
  Info = collections.namedtuple("Info", "path name phys hash")
  DeviceInfo = collections.namedtuple("DeviceInfo", "device info")
  identifierRe = re.compile("([^:]*):(.*)")
  devices = [evdev.InputDevice(fn) for fn in evdev.list_devices()]
  deviceInfos = [DeviceInfo(device, Info(device.path, device.name.strip(" "), device.phys, "{:X}".format(calc_device_hash(device)))) for device in devices]

  def find_device(identifier):
    m = identifierRe.match(identifier)
    deviceInfo = None
    for di in deviceInfos:
      if m is None:
        if identifier in di.info:
          deviceInfo = di
          break
      else:
        d = di.info._asdict()
        if d.get(m.group(1)) == m.group(2):
          deviceInfo = di
          break
    return  deviceInfo.device if deviceInfo else None

  idType = type(inputsData)
  if idType in (str, unicode):
    return find_device(inputsData)
  elif idType in (dict, collections.OrderedDict):
    r = {}
    for source,identifier in inputsData.items():
      r[source] = find_device(identifier)
    return r
  else:
    raise RuntimeError("make_evdev_devices(): bad inputsData type: {} (can be string or dict)".format(idType))


def init_inputs(inputsData, makeDevice=lambda native,source,recreateOp : EvdevDevice(native, source, recreateOp)):
  """
  Initializes input devices.
  Input device can be designated by path, name, phys or hash which are printed by print_devices(). 
  """
  def make_recreate(identifier, **kwargs):
    deviceUpdatePeriod = kwargs.get("deviceUpdatePeriod", 0)
    ts = [None]
    def op():
      t = time.time()
      if ts[0] is None:
        ts[0] = t
      else:
        dt = t - ts[0]
        if dt < deviceUpdatePeriod:
          return None
        else:
          ts[0] = t
      return make_evdev_devices(identifier)
    return op
  r = {}
  natives = make_evdev_devices(inputsData)
  for source,native in natives.items():
    identifier = inputsData[source]
    r[source] = makeDevice(native, source, recreateOp=make_recreate(inputsData[source], deviceUpdatePeriod=2))
    if native:
      logger.info("Found device {} ({})".format(source, identifier))
    else:
      logger.warning("Device {} ({}) not found".format(source, identifier))
  return r


def print_help():
  print "Usage: " + sys.argv[0] + " args"
  print "args are:\n\
  -h | --help : this message\n\
  -d fileName | --devices=fileName : print input devices to file fileName (- for stdout)\n\
  -p presetName | --preset=presetName : use preset presetName\n\
  -c configFileName | --config=configFileName : use config file configFileName\n\
  -v logLevel | --logLevel=logLevel : set log level to logLevel\n"


def print_devices(fname):
  """Prints input devices info."""
  r = []
  devices = [evdev.InputDevice(fn) for fn in evdev.list_devices()]
  for d in devices:
    caps = d.capabilities(verbose=True, absinfo=False)
    capsInfo = ""
    for k,v in caps.items():
      keyName = k[0]
      codeNames = ", ".join((str(i[0]) for i in v))
      capsInfo += " {}: {}\n".format(keyName, codeNames)
    r.append("name: {}\npath: {}\ncaps:\n{}fn: {}\ninfo: {}\nphys: {}\nuniq: {}\nhash: {:X}\n".format(d.name, d.path, capsInfo, d.fn, d.info, d.phys, d.uniq, calc_device_hash(d)))
  if fname == "-":
    for l in r:
      print l
  else:
    with open(fname, "w") as f:
      for l in r:
        f.write(l+"\n")


@make_reporting_joystick
def parseEvdevJoystickOutput(cfg, state):
  buttons = [code2ecode(name2code(buttonName)) for buttonName in cfg["buttons"]]
  limits = {code2ecode(name2code(a)):l for a,l in cfg.get("limits", {}).items()}
  immediateSyn=cfg.get("immediateSyn", True)
  nativeLimit=cfg.get("nativeLimit", 32767)
  j = EvdevJoystick(limits=limits, buttons=buttons, name=cfg.get("name", ""), phys=cfg.get("phys", ""), immediateSyn=immediateSyn, nativeLimit=nativeLimit)
  if immediateSyn == False:
    state["settings"]["updated"].append(lambda tick,ts : j.update(tick, ts))
  return j


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
      compressEvents = config.get("compressEvents", False)
      def makeDevice(native, source, recreateOp):
        dev = EvdevDevice(native, source, recreateOp)
        if compressEvents:
          dev = EventCompressorDevice(dev)
        return dev
      settings["inputs"] = init_inputs(config["inputs"], makeDevice)
      sink = init_main_sink(settings, init_preset_config)
      settings["source"] = EventSource(settings["inputs"].values(), sink)

  def set_inputs_state(settings, state):
    for i in settings["inputs"].values():
      try:
        i.swallow(state)
      except IOError as e:
        logger.debug("got IOError ({}), but that was expected".format(e))
        continue

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

  preinit_log()
  try:
    settings = {"options" : {}, "configNames" : [], "updated" : []}
    options = {}
    settings["options"] = options

    if (len(sys.argv)) == 1:
      print_help()
      return 0

    opts, args = getopt.getopt(sys.argv[1:], "hd:p:v:c:", ["help", "devices=", "preset=", "logLevel=", "config="])
    for o, a in opts:
      if o in ("-h", "--help"):
        print_help()
        return 0
      elif o in ("-d", "--devices"):
        print_devices(a)
        return 0
      if o in ("-p", "--preset"):
        options["preset"] = a
      elif o in ("-v", "--logLevel"):
        options["logLevel"] = a
      elif o in ("-c", "--config"):
        settings["configNames"].append(a)

    parser = make_parser()
    settings["parser"] = parser
    parser.get("output").add("evdev", parseEvdevJoystickOutput)

    settings["reloading"] = False
    init_config2(settings)
    init_log(settings)
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
      finally:
        set_inputs_state(settings, False)

  except KeyboardInterrupt:
    logger.info("Exiting normally")
    return 0
  except ExitException:
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
