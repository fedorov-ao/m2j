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

logger = logging.getLogger(__name__)


class NullJoystick:
  """Temporory placeholder joystick class."""
  def __init__(self):
    self.coords = {}
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
    self.coords[axis] = v

  def get_axis_value(self, axis):
    return self.coords.get(axis, 0.0)

  def get_limits(self, axis):
    return (-float("inf"), float("inf"))

  def get_supported_axes(self):
    return self.coords.keys()

  def set_button_state(self, button, state):
    pass
  

def parsePPJoystickOutput(cfg, state):
  return NullJoystick()

MAX_PATH = 255
WM_INPUT = 255
WNDPROC = WINFUNCTYPE(c_long, c_int, c_uint, c_int, c_int)

RIDI_DEVICENAME = 0x20000007
RIDI_DEVICEINFO = 0x2000000b

RIDEV_INPUTSINK = 0x00000100
RIDEV_EXINPUTSINK = 0x00001000
RIDEV_CAPTUREMOUSE = 0x00000200

RID_INPUT = 0x10000003
RIM_TYPEMOUSE = 0x00000000
RIM_TYPEKEYBOARD = 0x00000001

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


def ErrorIfZero(handle):
    if handle == 0:
        raise WinError()
    else:
        return handle


#TODO Implement
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
    wndclass.lpszClassName = "RawInputDeviceManagerClass"
    # Register Window Class
    if not windll.user32.RegisterClassA(byref(wndclass)):
        raise WinError()
    #Need to store reference to wndclass or DestroyWindow will fail!
    self.wndclass = wndclass
    # Create Window
    hwnd = CreateWindowEx(
      0, wndclass.lpszClassName, "RawInputDeviceManager",
      win32con.WS_OVERLAPPEDWINDOW, win32con.CW_USEDEFAULT, win32con.CW_USEDEFAULT, win32con.CW_USEDEFAULT, win32con.CW_USEDEFAULT,
      win32con.HWND_MESSAGE if useMessageWindow else win32con.NULL,
      win32con.NULL, wndclass.hInstance, win32con.NULL)
    if not useMessageWindow:
      windll.user32.ShowWindow(c_int(hwnd), c_int(win32con.SW_SHOWNORMAL))
      windll.user32.UpdateWindow(c_int(hwnd))
    #TODO Check for error
    self.hwnd = hwnd
    
    #TODO Listen to other types of devices
    numRid = 2
    Rid = (numRid * RAWINPUTDEVICE)()
    Rid[0].usUsagePage = HID_USAGE_PAGE_GENERIC
    Rid[0].usUsage = HID_USAGE_GENERIC_MOUSE
    Rid[0].dwFlags = RIDEV_INPUTSINK
    Rid[0].hwndTarget = hwnd
    Rid[1].usUsagePage = HID_USAGE_PAGE_GENERIC
    Rid[1].usUsage = HID_USAGE_GENERIC_KEYBOARD
    Rid[1].dwFlags = RIDEV_INPUTSINK
    Rid[1].hwndTarget = hwnd
    #TODO Check for error
    r = windll.user32.RegisterRawInputDevices(Rid, numRid, sizeof(RAWINPUTDEVICE))
    
    self.devs_ = {}
    
  def __del__(self):
    self.stop()

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
    msg = MSG()
    pMsg = pointer(msg)
    NULL = c_int(win32con.NULL)
    PM_REMOVE = 1
    while windll.user32.PeekMessageA(pMsg, self.hwnd, 0, 0, PM_REMOVE) != 0:
        windll.user32.DispatchMessageA(pMsg)    
    
  def track_device(self, name, source):
    devices = self.get_devices()
    for d in devices:
      if d.name == name:
        self.devs_[d.handle] = source
        return
    raise RuntimeError("Device {} not found".format(name))
    
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
    else:
      class DeviceInfo:
        pass
      devices = []
      for i in range(r):
        ridl = rawInputDeviceList[i]
        #Get required device name string length
        pName = 0
        szName = c_uint(0)
        r = windll.user32.GetRawInputDeviceInfoA(ridl.hDevice, RIDI_DEVICENAME, pName, byref(szName))
        if r == c_uint(-1):
          raise RuntimError("Error getting device name string length")
        else:
          pName = create_string_buffer(szName.value)
          r = windll.user32.GetRawInputDeviceInfoA(ridl.hDevice, RIDI_DEVICENAME, pName, byref(szName))
          if r == c_uint(-1):
            raise RuntimError("Error getting device name")
          else:
            di = DeviceInfo()
            di.handle, di.type, di.name = ridl.hDevice, ridl.dwType, pName.value
            devices.append(di)
      return devices
      
  #TODO Implement
  def wnd_proc(self, hwnd, message, wParam, lParam):
    if message == win32con.WM_DESTROY:
      windll.user32.PostQuitMessage(0)
    elif message == WM_INPUT:
      raw = RAWINPUT()
      dwSize = c_uint(sizeof(RAWINPUT))
      if windll.user32.GetRawInputData(lParam, RID_INPUT, byref(raw), byref(dwSize), sizeof(RAWINPUTHEADER)) > 0:
        if raw.header.hDevice in self.devs_:
          hd = raw.header.hDevice
          source = self.devs_[hd]
          if raw.header.dwType == RIM_TYPEMOUSE:
            #self.raw_mouse_events.append((raw.header.hDevice, raw.mouse.usFlags, raw.mouse.ulButtons, raw.mouse._u1._s2.usButtonFlags, raw.mouse._u1._s2.usButtonData, raw.mouse.ulRawButtons, raw.mouse.lLastX, raw.mouse.lLastY, raw.mouse.ulExtraInformation))
            logger.debug("{}: Got mouse event".format(self))
            self.sink_(self.make_mouse_event_(raw, source))
          elif raw.header.dwType == RIM_TYPEKEYBOARD:
            #self.raw_keyboard_events.append((raw.header.hDevice, raw.keyboard.MakeCode, raw.keyboard.Flags, raw.keyboard.VKey, raw.keyboard.Message, raw.keyboard.ExtraInformation))
            logger.debug("{}: Got keyboard event".format(self))
            self.sink_(self.make_kbd_event_(raw, source))
    return windll.user32.DefWindowProcA(c_int(hwnd), c_int(message), c_int(wParam), c_int(lParam))
  
  #TODO Implement
  def make_mouse_event_(self, raw, source):
    return InputEvent(0, 0, 0, time.time(), source)
  
  #TODO Implement
  def make_kbd_event_(self, raw, source):
    return InputEvent(0, 0, 0, time.time(), source)


def print_devices():
  devices = RawInputEventSource().get_devices()
  for d in devices:
    print "name: {}\nhandle: {}\ntype:\n{}\n".format(d.name, d.handle, d.type)


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
      source = RawInputEventSource(useMessageWindow=False)
      for s,n in config["inputs"].items():
        source.track_device(n, s)
      source.set_sink(sink)
      settings["source"] = source

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
