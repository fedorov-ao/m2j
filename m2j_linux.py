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
import traceback
import m2j
from m2j import *
import collections
import re
import evdev
from evdev import UInput, AbsInfo, ecodes

logger = logging.getLogger("m2j_linux")

def code2ecode(code):
  return code

def ecode2code(code):
  return code


class ExternalEvdevJoystick:
  def __init__(self, js, limits, immediateSyn):
    self.js_ = js
    self.dirty_ = False

    self.immediateSyn_ = immediateSyn
    self.limits_ = limits
    self.nlimits_ = {}
    self.axes_ = {}
    self.buttons_ = {}

    cap = self.js_.capabilities(absinfo=True)
    for nativeAxis,absInfo in cap.get(ecodes.EV_ABS, ()):
      tcAxis = TypeCode(codes.EV_ABS, ecode2code(nativeAxis))
      nl = (absInfo.min, absInfo.max,)
      self.nlimits_[tcAxis] = nl
      l = self.limits_.get(tcAxis)
      value = lerp(absInfo.value, l[0], l[1], nl[0], nl[1])
      self.axes_[tcAxis] = value

    #TODO Determine actual button state
    for nativeButton in cap.get(ecodes.EV_KEY, ()):
      self.buttons_[ecode2code(nativeButton)] = False

    logger.debug("{} created".format(self))

  def __del__(self):
    logger.debug("{} destroyed".format(self))

  def move_axis(self, tcAxis, v, relative):
    if relative:
      return self.move_axis_by(tcAxis, v)
    else:
      return self.move_axis_to(tcAxis, v)

  def move_axis_by(self, tcAxis, v):
    desired = self.get_axis_value(tcAxis)+v
    actual = self.move_axis_to(tcAxis, desired)
    return v - (actual - desired)

  def move_axis_to(self, tcAxis, v):
    if tcAxis not in self.axes_:
      raise RuntimeError("Axis not supported: {}".format(tcAxis))
    l = self.limits_.get(tcAxis, (0.0, 0.0,))
    v = clamp(v, *l)
    self.axes_[tcAxis] = v
    nl = self.nlimits_.get(tcAxis, (0.0, 0.0,))
    nv = lerp(v, l[0], l[1], nl[0], nl[1])
    nv = int(nv)
    #logger.debug("{}: Moving axis {} to {}, native {}".format(self, typecode2name(codes.EV_ABS, axis), v, nv))
    self.js_.write(ecodes.EV_ABS, code2ecode(tcAxis.code), nv)
    if self.immediateSyn_ == True:
      self.syn()
    else:
      self.dirty_ = True
    return v

  def get_axis_value(self, tcAxis):
    return self.axes_.get(tcAxis, 0.0)

  def get_limits(self, tcAxis):
    return self.limits_.get(tcAxis, [0.0, 0.0])

  def get_supported_axes(self):
    return self.axes_.keys()

  def set_button_state(self, button, state):
    if button not in self.buttons_:
      raise RuntimeError("Button not supported: {}".format(button))
    self.buttons_[button] = state
    self.js_.write(ecodes.EV_KEY, code2ecode(button), state)
    if self.immediateSyn_ == True:
      self.syn()
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
      self.syn()
      self.dirty_ = False

  def syn(self):
    self.js_.write(ecodes.EV_SYN, ecodes.SYN_REPORT, 0)


class EvdevJoystick2(ExternalEvdevJoystick):
  def __init__(self, limits, buttons=None, name=None, phys=None, immediateSyn=True, nativeLimit=32767):
    cap = {}
    axesData = []
    for tca,l in limits.items():
      value = (l[1] + l[0])/2
      value = lerp(value, l[0], l[1], -nativeLimit, nativeLimit)
      axesData.append((code2ecode(tca.code), AbsInfo(value=value, min=-nativeLimit, max=nativeLimit, fuzz=0, flat=0, resolution=0)))
    cap[ecodes.EV_ABS] = axesData

    if buttons is not None:
      cap[ecodes.EV_KEY] = [code2ecode(b) for b in buttons]

    if name is None:
      name='virtual-joystick'

    numTries = 0
    while (True):
      try:
        self.js_ = UInput(cap, name=name, version=0x3, phys=phys)
        #Determine whether device has been opened
        self.js_.capabilities(absinfo=True)
        break
      except evdev.uinput.UInputError:
        logger.warning("Could not open evdev device {} on try {}".format(name, numTries+1))
        numTries += 1
        if numTries == 10:
          raise
        time.sleep(0.5)

    ExternalEvdevJoystick.__init__(self, js=self.js_, limits=limits, immediateSyn=immediateSyn)

    logger.debug("{} created".format(self))

  def __del__(self):
    if self.js_ is not None:
      self.js_.close()
    logger.debug("{} destroyed".format(self))


class EvdevJoystick:
  class AxisData:
    def __init__(self, limits, nativeLimits=(-32767, 32767), value=0.0, fuzz=0, flat=0, resolution=0):
      self.limits, self.nativeLimits, self.value, self.fuzz, self.flat, self.resolution = limits, nativeLimits, value, fuzz, flat, resolution

  def __init__(self, axesDatum, buttons=None, name=None, phys=None, immediateSyn=True):
    self.immediateSyn_ = immediateSyn
    self.dirty_ = False
    self.js_ = None

    class TrimmedAxisData:
      def __init__(self, limits, nativeLimits, value):
        self.limits, self.nativeLimits, self.value = limits, nativeLimits, value

    self.axesDatum_ = {}
    cap = {}
    nativeAxesDatum = []

    for tcAxis,axisData in axesDatum.items():
      self.axesDatum_[tcAxis] = TrimmedAxisData(limits=axisData.limits, nativeLimits=axisData.nativeLimits, value=axisData.value)
      absInfo = AbsInfo(value=axisData.value, min=axisData.nativeLimits[0], max=axisData.nativeLimits[1], fuzz=axisData.fuzz, flat=axisData.flat, resolution=axisData.resolution)
      nativeAxesDatum.append((code2ecode(tcAxis.code), absInfo))
    cap[ecodes.EV_ABS] = nativeAxesDatum

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
    if logger is not None:
      logger.debug("{} destroyed".format(self))

  def move_axis(self, tcAxis, v, relative):
    if relative:
      return self.move_axis_by(tcAxis, v)
    else:
      return self.move_axis_to(tcAxis, v)

  def move_axis_by(self, tcAxis, v):
    desired = self.get_axis_value(tcAxis)+v
    actual = self.move_axis_to(tcAxis, desired)
    return v - (actual - desired)

  def move_axis_to(self, tcAxis, v):
    axisData = self.axesDatum_.get(tcAxis, None)
    if axisData is None:
      raise RuntimeError("Axis not supported: {}".format(tcAxis))
    limits, nativeLimits = axisData.limits, axisData.nativeLimits
    v = clamp(v, *limits)
    axisData.value = v
    nativeValue = lerp(v, limits[0], limits[1], nativeLimits[0], nativeLimits[1])
    nativeValue = int(nativeValue)
    #logger.debug("{}: Moving axis {} to {}, native {}".format(self, typecode2name(codes.EV_ABS, axis), v, nv))
    self.js_.write(ecodes.EV_ABS, code2ecode(tcAxis.code), nativeValue)
    if self.immediateSyn_ == True:
      self.js_.syn()
    else:
      self.dirty_ = True
    return v

  def get_axis_value(self, tcAxis):
    axisData = self.axesDatum_.get(tcAxis, None)
    return 0.0 if axisData is None else axisData.value

  def get_limits(self, tcAxis):
    axisData = self.axesDatum_.get(tcAxis, None)
    return [0.0, 0.0] if axisData is None else axisData.limits

  def get_supported_axes(self):
    return self.axesDatum_.keys()

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


def translate_evdev_event(evdevEvent, idev):
  return None if evdevEvent is None else InputEvent(ecode2code(evdevEvent.type), ecode2code(evdevEvent.code), evdevEvent.value, evdevEvent.timestamp(), idev)


class EvdevDevice:
  def read_one(self):
    if not self.is_ready_():
      return None
    try:
      evdevEvent = self.dev_.read_one()
      while (evdevEvent is not None) and (evdevEvent.type in (0, 4)):
        evdevEvent = self.dev_.read_one()
      event = translate_evdev_event(evdevEvent, self.idevHash_)
      if event is None:
        if self.numEvents_ != 0:
          #logger.debug("{}: {} got {} events".format(self, self.idevName_, self.numEvents_))
          self.numEvents_ = 0
      else:
        #logger.debug("{}: {} read event: {}".format(self, self.idevName_, event))
        self.numEvents_ += 1
      return event
    except IOError as e:
      self.numEvents_ = 0
      self.dev_ = None
      logger.error("{}: device is not ready: {}".format(self.idevName_, e))

  def swallow(self, s):
    self.state_ = s
    if not self.is_ready_():
      return
    try:
      if s:
        self.dev_.grab()
      else:
        self.dev_.ungrab()
    except IOError as e:
      #IOError is expected
      pass

  def __init__(self, dev, idev, recreateOp=lambda : None):
    self.dev_, self.idevName_, self.recreateOp_ = dev, idev, recreateOp
    self.idevHash_ = register_dev(idev)
    self.numEvents_ = 0
    self.state_ = False

  def is_ready_(self):
    if self.dev_ is not None:
      return True
    dev = self.recreateOp_()
    if dev is not None:
      self.dev_ = dev
      logger.info("{}: device is ready".format(self.idevName_))
      self.swallow(self.state_)
      return True
    else:
      return False


def calc_device_hash(device):
    caps = device.capabilities(verbose=False, absinfo=False)
    info = tuple((k, tuple(i for i in v),) for k,v in caps.items())
    info = (device.name, info,)
    return hash(info)


class NativeEvdevDeviceFactory:
  def make_device(self, identifier, update=False):
    if update:
      self.update()
    m = self.identifierRe_.match(identifier)
    found = None
    for di in self.deviceInfos_:
      if m is None:
        if identifier in di.info:
          found = di
          break
      else:
        devInfoDict = di.info._asdict()
        devIdType, devIdValue = m.group(1), m.group(2)
        if devInfoDict.get(devIdType) == devIdValue:
          found = di
          break
    return found.device if found else None

  def update(self):
    devices = (evdev.InputDevice(fn) for fn in evdev.list_devices())
    self.deviceInfos_ = [self.DeviceInfo_(device, self.Info_(device.path, device.name.strip(" "), device.phys, "{:X}".format(calc_device_hash(device)))) for device in devices]

  def __init__(self):
    self.update()

  Info_ = collections.namedtuple("Info", "path name phys hash")
  DeviceInfo_ = collections.namedtuple("DeviceInfo", "device info")
  identifierRe_ = re.compile("([^:]*):(.*)")


def init_idevs(idevsCfg, makeDevice=lambda native,idev,recreateOp : EvdevDevice(native, idev, recreateOp), deviceUpdatePeriod=2):
  """
  Initializes idev devices.
  Input device can be designated by path, name, phys or hash which are printed by print_devices(). 
  """
  nativeDevFactory = NativeEvdevDeviceFactory()
  def make_recreate_op(identifier, **kwargs):
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
      return nativeDevFactory.make_device(identifier, update=True)
    return op
  r = {}
  for idev,identifier in idevsCfg.items():
    nativeDevice = nativeDevFactory.make_device(identifier)
    recreateOp=make_recreate_op(identifier=identifier, deviceUpdatePeriod=deviceUpdatePeriod)
    r[idev] = makeDevice(nativeDevice, idev, recreateOp=recreateOp)
    if nativeDevice:
      logger.info("Found device {} ({})".format(idev, identifier))
    else:
      logger.warning("Device {} ({}) not found".format(idev, identifier))
  return r


@make_reporting_joystick
def parseEvdevJoystickOutput(cfg, state):
  buttons = None
  numButtons = cfg.get("numButtons", None)
  if numButtons is not None:
    buttons = [codes.BTN_0+i for i in range(numButtons)]
  else:
    buttonNames = cfg.get("buttons", None)
    if buttonNames is not None:
      buttons = [code2ecode(name2code(buttonName)) for buttonName in buttonNames]
    else:
      raise RuntimeError("Either 'buttons' or 'numButtons' must be specified")
  assert buttons is not None
  axesDatum = {}
  immediateSyn=cfg.get("immediateSyn", True)
  nativeLimit=cfg.get("nativeLimit", 32767)
  axesDatumCfg = cfg.get("axesDatum", None)
  if axesDatumCfg is not None:
    for axisName,axisDataCfg in axesDatumCfg.items():
      tcAxis = fn2tc(axisName)
      value = axisDataCfg.get("value", 0.0)
      limits = axisDataCfg.get("limits", (-1.0, 1.0))
      nativeLimits = axisDataCfg.get("nativeLimits", (-nativeLimit, nativeLimit))
      fuzz = axisDataCfg.get("fuzz", 0)
      flat = axisDataCfg.get("flat", 0)
      resolution = axisDataCfg.get("resolution", 0)
      axesDatum[tcAxis] = EvdevJoystick.AxisData(limits=limits, nativeLimits=nativeLimits, value=value, fuzz=fuzz, flat=flat, resolution=resolution)
  else:
    limits = {fn2tc(a):l for a,l in cfg.get("limits", {}).items()}
    #j = EvdevJoystick2(limits=limits, buttons=buttons, name=cfg.get("name", ""), phys=cfg.get("phys", ""), immediateSyn=immediateSyn, nativeLimit=nativeLimit)
    for tcAxis,limit in limits.items():
      axesDatum[tcAxis] = EvdevJoystick.AxisData(limits=limit, nativeLimits=(-nativeLimit, nativeLimit))
  j = EvdevJoystick(axesDatum=axesDatum, buttons=buttons, name=cfg.get("name", ""), phys=cfg.get("phys", ""), immediateSyn=immediateSyn)
  if immediateSyn == False:
    state.get("main").get("updated").append(lambda tick,ts : j.update(tick, ts))
  return j


def parseEvdevEventSource(cfg, state):
  config = state.get("main").get("config")
  compressEvents = config.get("compressSourceEvents", False)
  deviceUpdatePeriod = config.get("missingSourceUpdatePeriod", 2)
  def make_device(native, idev, recreateOp):
    dev = EvdevDevice(native, idev, recreateOp)
    if compressEvents:
      dev = EventCompressorDevice(dev)
    return dev
  idevs = init_idevs(config.get("idevs", {}), make_device, deviceUpdatePeriod)
  return EventSource(idevs, None)


def print_devices(fname, **kwargs):
  """Prints idev devices info."""
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
    main = Main(print_devices=print_devices)
    parser = main.get("parser")
    parser.get("odev").add("evdev", parseEvdevJoystickOutput)
    parser.add("source", parseEvdevEventSource)
    exit(main.run())
  except Exception as e:
    print "Uncaught exception: {} ({})".format(type(e), e)
    for l in traceback.format_exc().splitlines()[-11:]:
      print l
    exit(2)
