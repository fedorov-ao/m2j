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
import Tkinter as tk
import getopt
import playsound
import threading

logger = logging.getLogger("m2j")

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
  if lo > hi:
    lo,hi = hi,lo
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


def str2(v, length=0):
  def str2_w(v):
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
  s = str2_w(v)
  if length > 0:
    rep = "..."
    ls = len(s)
    if ls > length:
      ls = (length - len(rep))/2
      s = s[:ls] + rep + s[-ls:]
  return s


def truncate(cfg, l=30, ellipsis=True):
  return str2(cfg)[:l] + "..." if ellipsis else ""


  levelName = main.get("config").get("logLevel", "NOTSET").upper()
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


def set_nested(d, name, value, sep = "."):
  tokens = name.split(sep)
  dd = d
  for t in tokens[:-1]:
    dd = dd.setdefault(t, collections.OrderedDict())
  dd[tokens[-1]] = value
  return value


def get_nested(d, name, sep = "."):
  try:
    if len(name) != 0:
      tokens = name.split(sep)
      for t in tokens:
        nd = d.get(t)
        if nd is None:
          path = str(sep.join(tokens[:tokens.index(t)]))
          token = sep.join((path, str(t))) if len(path) != 0 else str(t)
          keys = [sep.join((path, str(k))) if len(path) != 0 else str(k) for k in d.keys()]
          raise KeyError2(token, keys)
        d = nd
      if d is not None:
        return d
    #Fallback
    return None
  except:
    logger.error("get_nested(): Error while getting '{}' from '{}'".format(name, str2(d, 100)))
    raise


def get_nested_d(d, name, dfault = None, sep = "."):
  r = dfault
  if len(name) != 0:
    tokens = name.split(sep)
    for t in tokens:
      if hasattr(d, "get") == False:
        d = None
        break
      d = d.get(t)
    if d is not None:
      r = d
  #Fallback
  return r


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


class ArgNotFoundError(RuntimeError):
  def __init__(self, argName):
    self.argName = argName

  def __str__(self):
    return "Argument '{}' was not found".format(self.argName)


class ObjNotFoundError(RuntimeError):
  def __init__(self, objName):
    self.objName = objName

  def __str__(self):
    return "Object '{}' was not found".format(self.objName)


class ParserState:
  def push(self, n, v):
    self.stacks_.setdefault(n, [])
    self.stacks_[n].append(v)

  def pop(self, n):
    assert n in self.stacks_
    stack = self.stacks_[n]
    assert len(stack) > 0
    stack.pop()

  def at(self, n, i):
    stack = self.stacks_.get(n)
    return None if (stack is None or len(stack) == 0 or len(stack) <= i) else stack[-(1+i)]

  def set(self, n, v):
    self.values_[n] = v

  def setdefault(self, n, v):
    return self.values_.setdefault(n, v)

  def get(self, n, dfault=None):
    return self.values_.get(n, dfault)

  def get_obj(self, name, **kwargs):
    nameSep = kwargs.get("nameSep", ":")
    memberSep = kwargs.get("memberSep", ".") 
    objectName = name.split(nameSep)
    objects, i = None, 0
    while True:
      sink = self.at("sinks", i)
      if sink is None:
        break
      assert isinstance(sink, HeadSink)
      objects = sink.get("objects", None)
      if objects is not None:
        obj = objects.get(objectName[0])
        if obj is not None:
          break
      i += 1
    if objects is None or obj is None:
      raise ObjNotFoundError(name)
    if len(objectName) > 1:
      for s in objectName[1].split(memberSep):
        obj = obj.get(s)
        if obj is None:
          raise RuntimeError("Cannot get '{}': '{}' is missing".format(objectName[1], s))
    return self.get_var_or_value_(obj, **kwargs)

  def make_objs(self, cfg, cb):
    parser = self.get("parser")
    #logger.debug("Constructing objects from '{}'".format(str2(cfg)))
    for k,v in cfg.items():
      o = None
      #logger.debug("Constructing object '{}' from '{}'".format(k, str2(v)))
      #Sink components ("sc" parser) should not be created as individual objects, because they depend on each other.
      if type(v) not in (dict, collections.OrderedDict):
        raise RuntimeError("Object specification must be a JSON object, got {}".format(str2(v)))
      n = v.get("class", None)
      if n is not None:
        o = parser(n, v, self)
      else:
        for n in ("literal", "func", "curve", "action", "et", "output", "var"):
          if n in v:
            o = parser(n, v, self)
            #break is needed to avoid executing the "else" block
            break
        else:
          o = parser("sink", v, self)
      if o is None:
        raise RuntimeError("Could not create object from: {}".format(str2(v)))
      cb(k, o)

  def get_arg(self, name, **kwargs):
    r = None
    args = self.stacks_.get("args")
    if args is not None:
      r = get_nested_from_stack_d(args, name, None)
      if r is None:
        raise ArgNotFoundError(name)
    else:
      raise RuntimeError("No args were specified, so cannot get arg: {}".format(str2(name)))
    return self.get_var_or_value_(r, **kwargs)

  def resolve_args(self, args):
    #logger.debug("Resolving args '{}'".format(str2(args)))
    r = collections.OrderedDict()
    for n,a in args.items():
      r[n] = self.deref(a, asValue=False)
      #logger.debug("arg '{}': '{}' -> '{}'".format(n, str2(a), r[n]))
    return r

  def push_args(self, cfg):
    argsCfg = self.resolve_d(cfg, "args", {})
    self.push("args", self.resolve_args(argsCfg))

  def pop_args(self):
    self.pop("args")

  def get_var(self, varName, **kwargs):
    varManager = self.get("main").get("varManager")
    var = varManager.get_var(varName)
    return self.get_var_or_value_(var, **kwargs)

  def deref(self, refOrValue, dfault=None, **kwargs):
    def make_mapping(cfg):
      mapping = None
      mappingCfg = self.resolve_d(refOrValue, "mapping", None)
      if mappingCfg is not None:
        mapping = {}
        for k,v in mappingCfg.items():
          k = self.deref(k)
          v = self.deref(v)
          mapping[k] = v
        def op(v):
          if v in mapping:
            return mapping[v]
          else:
            raise RuntimeError("{} not found in mapping".format(v))
          #logger.debug("Created mapping {} from {}".format(op, str2(mappingCfg)))
        return op
      else:
        return None
    prefix, suffix, mapping = None, None, None
    r = refOrValue
    if type(refOrValue) in (dict, collections.OrderedDict):
      for p in ("obj", "arg", "var"):
        suffix = get_nested_d(refOrValue, p, None)
        if suffix is not None:
          prefix = p
          if prefix == "var":
            mapping = make_mapping(refOrValue)
          break
    elif type(refOrValue) in (str, unicode):
      refOrValueRe = re.compile("(.*?)(obj|arg|var):([^ +*/&|]*)(.*?)")
      refOrValueMatch = refOrValueRe.match(refOrValue)
      if refOrValueMatch is not None:
        prefix, suffix = refOrValueMatch.group(2), refOrValueMatch.group(3)
        g1, g4 = refOrValueMatch.group(1), refOrValueMatch.group(4)
        if len(g1) or len(g4):
          expr = "{}v{}".format(g1, g4)
          compiledExpr = compile(expr, "", "eval")
          def op(v):
            globs = { "v" : v }
            #logger.debug("{}: evaluating {} with {}".format(self, expr, str2(globs)))
            return eval(compiledExpr, globs)
          mapping = op
          #logger.debug("Created mapping {} with expression '{}' from '{}'".format(mapping, expr, refOrValue))
    if prefix is not None:
      suffix = self.deref(suffix, **kwargs)
      setter = kwargs.get("setter")
      asValue = kwargs.get("asValue", True)
      if prefix == "obj":
        r = self.get_obj(suffix, setter=setter, mapping=mapping, asValue=asValue)
      elif prefix == "arg":
        try:
          r = self.get_arg(suffix, setter=setter, mapping=mapping, asValue=asValue)
        except ArgNotFoundError as e:
          #logger.debug("{}".format(e))
          r = dfault
      elif prefix == "var":
        r = self.get_var(suffix, setter=setter, mapping=mapping, asValue=asValue)
      else:
        raise RuntimeError("Unknown prefix: '{}'".format(prefix))
    #logger.debug("Dereferenced '{}' to '{}'".format(str2(refOrValue), str2(r)))
    #This return statement must be at deref() scope, not in nested blocks!
    return r

  def resolve_d(self, d, name, dfault=None, **kwargs):
    v = get_nested_d(d, name, dfault)
    return self.deref(v, dfault, **kwargs)

  def resolve(self, d, name, **kwargs):
    r = self.resolve_d(d, name, None, **kwargs)
    if r is None:
      #TODO Use more appropriate exception
      raise RuntimeError("Cannot get '{}' from '{}'".format(name, str2(d, 100)))
    return r

  def get_axis_by_full_name(self, fnAxis):
    return self.get("main").get_axis_by_full_name(fnAxis)

  def get_full_name_by_axis(self, axis):
    return self.get("main").get_full_name_by_axis(axis)

  def add_curve(self, fnAxis, curve):
    axisCurves = self.at("curves", 0).setdefault(fnAxis, [])
    axisCurves.append(curve)

  def __init__(self, main):
    self.values_ = {}
    self.values_["main"] = main
    self.values_["parser"] = main.get("parser")
    self.stacks_ = {}

  def get_var_or_value_(self, varOrValue, **kwargs):
    r = varOrValue
    mapping = kwargs.get("mapping")
    isBaseVar = isinstance(varOrValue, BaseVar)
    if isBaseVar == True:
      setter, asValue = kwargs.get("setter"), kwargs.get("asValue", True)
      if mapping is not None:
        r = MappingVar(r, mapping)
      if setter is not None:
        r.add_callback(setter)
      if asValue == True:
        r = r.get()
    else:
      if mapping is not None:
        r = mapping(r)
    return r

class SourceRegister:
  def register_source(self, name):
    """Input event source __init__() should call this with the name of source."""
    hsh = self.hash_
    self.hash_ += 1
    self.sources_[hsh] = name
    self.hashes_[name] = hsh
    return hsh

  def get_name(self, hsh):
    if hsh is None:
      return None
    r = self.sources_.get(hsh, None)
    if r is None:
      raise RuntimeError("Source with hash {} not registered".format(hsh))
    return r

  def get_hash(self, name):
    if name is None:
      return None
    r = self.hashes_.get(name, None)
    if r is None:
      if self.addMissing_:
        r = self.register_source(name)
      else:
        raise RuntimeError("Source with name {} not registered".format(name))
    return r

  def __init__(self, addMissing=True):
    self.sources_, self.hashes_, self.addMissing_ = dict(), dict(), addMissing
    self.hash_ = 0

g_sr = SourceRegister(addMissing=True)

def register_source(source):
  """Input event source __init__() should call this with the name of source."""
  return g_sr.register_source(source)

def get_source_name(hsh):
  return g_sr.get_name(hsh)

def get_source_hash(name):
  return g_sr.get_hash(name)

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


codesDict = { 'EV_BCT':-1, 'EV_CUSTOM':-2, 'BCT_INIT':0, 'BCT_VALUE':1, 'ABS_ANY':-1, 'REL_ANY':-1, 'KEY_ANY':-1, 'BTN_ANY':-1, 'ABS_BRAKE':10, 'ABS_CNT':64, 'ABS_DISTANCE':25, 'ABS_GAS':9, 'ABS_HAT0X':16, 'ABS_HAT0Y':17, 'ABS_HAT1X':18, 'ABS_HAT1Y':19, 'ABS_HAT2X':20, 'ABS_HAT2Y':21, 'ABS_HAT3X':22, 'ABS_HAT3Y':23, 'ABS_MAX':63, 'ABS_MISC':40, 'ABS_MT_BLOB_ID':56, 'ABS_MT_DISTANCE':59, 'ABS_MT_ORIENTATION':52, 'ABS_MT_POSITION_X':53, 'ABS_MT_POSITION_Y':54, 'ABS_MT_PRESSURE':58, 'ABS_MT_SLOT':47, 'ABS_MT_TOOL_TYPE':55, 'ABS_MT_TOOL_X':60, 'ABS_MT_TOOL_Y':61, 'ABS_MT_TOUCH_MAJOR':48, 'ABS_MT_TOUCH_MINOR':49, 'ABS_MT_TRACKING_ID':57, 'ABS_MT_WIDTH_MAJOR':50, 'ABS_MT_WIDTH_MINOR':51, 'ABS_PRESSURE':24, 'ABS_RESERVED':46, 'ABS_RUDDER':7, 'ABS_RX':3, 'ABS_RY':4, 'ABS_RZ':5, 'ABS_THROTTLE':6, 'ABS_TILT_X':26, 'ABS_TILT_Y':27, 'ABS_TOOL_WIDTH':28, 'ABS_VOLUME':32, 'ABS_WHEEL':8, 'ABS_X':0, 'ABS_Y':1, 'ABS_Z':2, 'BTN_0':256, 'BTN_1':257, 'BTN_2':258, 'BTN_3':259, 'BTN_4':260, 'BTN_5':261, 'BTN_6':262, 'BTN_7':263, 'BTN_8':264, 'BTN_9':265, 'BTN_10':266, 'BTN_11':267, 'BTN_12':268, 'BTN_13':269, 'BTN_14':270, 'BTN_15':271, 'BTN_16':272, 'BTN_17':273, 'BTN_18':274, 'BTN_19':275, 'BTN_20':276, 'BTN_21':277, 'BTN_22':278, 'BTN_23':279, 'BTN_24':280, 'BTN_25':281, 'BTN_26':282, 'BTN_27':283, 'BTN_28':284, 'BTN_29':285, 'BTN_30':286, 'BTN_31':287, 'BTN_A':304, 'BTN_B':305, 'BTN_BACK':278, 'BTN_BASE':294, 'BTN_BASE2':295, 'BTN_BASE3':296, 'BTN_BASE4':297, 'BTN_BASE5':298, 'BTN_BASE6':299, 'BTN_C':306, 'BTN_DEAD':303, 'BTN_DIGI':320, 'BTN_DPAD_DOWN':545, 'BTN_DPAD_LEFT':546, 'BTN_DPAD_RIGHT':547, 'BTN_DPAD_UP':544, 'BTN_EAST':305, 'BTN_EXTRA':276, 'BTN_FORWARD':277, 'BTN_GAMEPAD':304, 'BTN_GEAR_DOWN':336, 'BTN_GEAR_UP':337, 'BTN_JOYSTICK':288, 'BTN_LEFT':272, 'BTN_MIDDLE':274, 'BTN_MISC':256, 'BTN_MODE':316, 'BTN_MOUSE':272, 'BTN_NORTH':307, 'BTN_PINKIE':293, 'BTN_RIGHT':273, 'BTN_SELECT':314, 'BTN_SIDE':275, 'BTN_SOUTH':304, 'BTN_START':315, 'BTN_STYLUS':331, 'BTN_STYLUS2':332, 'BTN_STYLUS3':329, 'BTN_TASK':279, 'BTN_THUMB':289, 'BTN_THUMB2':290, 'BTN_THUMBL':317, 'BTN_THUMBR':318, 'BTN_TL':310, 'BTN_TL2':312, 'BTN_TOOL_AIRBRUSH':324, 'BTN_TOOL_BRUSH':322, 'BTN_TOOL_DOUBLETAP':333, 'BTN_TOOL_FINGER':325, 'BTN_TOOL_LENS':327, 'BTN_TOOL_MOUSE':326, 'BTN_TOOL_PEN':320, 'BTN_TOOL_PENCIL':323, 'BTN_TOOL_QUADTAP':335, 'BTN_TOOL_QUINTTAP':328, 'BTN_TOOL_RUBBER':321, 'BTN_TOOL_TRIPLETAP':334, 'BTN_TOP':291, 'BTN_TOP2':292, 'BTN_TOUCH':330, 'BTN_TR':311, 'BTN_TR2':313, 'BTN_TRIGGER':288, 'BTN_TRIGGER_HAPPY':704, 'BTN_TRIGGER_HAPPY1':704, 'BTN_TRIGGER_HAPPY10':713, 'BTN_TRIGGER_HAPPY11':714, 'BTN_TRIGGER_HAPPY12':715, 'BTN_TRIGGER_HAPPY13':716, 'BTN_TRIGGER_HAPPY14':717, 'BTN_TRIGGER_HAPPY15':718, 'BTN_TRIGGER_HAPPY16':719, 'BTN_TRIGGER_HAPPY17':720, 'BTN_TRIGGER_HAPPY18':721, 'BTN_TRIGGER_HAPPY19':722, 'BTN_TRIGGER_HAPPY2':705, 'BTN_TRIGGER_HAPPY20':723, 'BTN_TRIGGER_HAPPY21':724, 'BTN_TRIGGER_HAPPY22':725, 'BTN_TRIGGER_HAPPY23':726, 'BTN_TRIGGER_HAPPY24':727, 'BTN_TRIGGER_HAPPY25':728, 'BTN_TRIGGER_HAPPY26':729, 'BTN_TRIGGER_HAPPY27':730, 'BTN_TRIGGER_HAPPY28':731, 'BTN_TRIGGER_HAPPY29':732, 'BTN_TRIGGER_HAPPY3':706, 'BTN_TRIGGER_HAPPY30':733, 'BTN_TRIGGER_HAPPY31':734, 'BTN_TRIGGER_HAPPY32':735, 'BTN_TRIGGER_HAPPY33':736, 'BTN_TRIGGER_HAPPY34':737, 'BTN_TRIGGER_HAPPY35':738, 'BTN_TRIGGER_HAPPY36':739, 'BTN_TRIGGER_HAPPY37':740, 'BTN_TRIGGER_HAPPY38':741, 'BTN_TRIGGER_HAPPY39':742, 'BTN_TRIGGER_HAPPY4':707, 'BTN_TRIGGER_HAPPY40':743, 'BTN_TRIGGER_HAPPY5':708, 'BTN_TRIGGER_HAPPY6':709, 'BTN_TRIGGER_HAPPY7':710, 'BTN_TRIGGER_HAPPY8':711, 'BTN_TRIGGER_HAPPY9':712, 'BTN_WEST':308, 'BTN_WHEEL':336, 'BTN_X':307, 'BTN_Y':308, 'BTN_Z':309, 'EV_ABS':3, 'EV_CNT':32, 'EV_FF':21, 'EV_FF_STATUS':23, 'EV_KEY':1, 'EV_LED':17, 'EV_MAX':31, 'EV_MSC':4, 'EV_PWR':22, 'EV_REL':2, 'EV_REP':20, 'EV_SND':18, 'EV_SW':5, 'EV_SYN':0, 'EV_UINPUT':257, 'EV_VERSION':65537, 'KEY_0':11, 'KEY_1':2, 'KEY_102ND':86, 'KEY_10CHANNELSDOWN':441, 'KEY_10CHANNELSUP':440, 'KEY_2':3, 'KEY_3':4, 'KEY_3D_MODE':623, 'KEY_4':5, 'KEY_5':6, 'KEY_6':7, 'KEY_7':8, 'KEY_8':9, 'KEY_9':10, 'KEY_A':30, 'KEY_AB':406, 'KEY_ADDRESSBOOK':429, 'KEY_AGAIN':129, 'KEY_ALS_TOGGLE':560, 'KEY_ALTERASE':222, 'KEY_ANGLE':371, 'KEY_APOSTROPHE':40, 'KEY_APPSELECT':580, 'KEY_ARCHIVE':361, 'KEY_ASSISTANT':583, 'KEY_ATTENDANT_OFF':540, 'KEY_ATTENDANT_ON':539, 'KEY_ATTENDANT_TOGGLE':541, 'KEY_AUDIO':392, 'KEY_AUDIO_DESC':622, 'KEY_AUX':390, 'KEY_B':48, 'KEY_BACK':158, 'KEY_BACKSLASH':43, 'KEY_BACKSPACE':14, 'KEY_BASSBOOST':209, 'KEY_BATTERY':236, 'KEY_BLUE':401, 'KEY_BLUETOOTH':237, 'KEY_BOOKMARKS':156, 'KEY_BREAK':411, 'KEY_BRIGHTNESSDOWN':224, 'KEY_BRIGHTNESSUP':225, 'KEY_BRIGHTNESS_AUTO':244, 'KEY_BRIGHTNESS_CYCLE':243, 'KEY_BRIGHTNESS_MAX':593, 'KEY_BRIGHTNESS_MIN':592, 'KEY_BRIGHTNESS_TOGGLE':431, 'KEY_BRIGHTNESS_ZERO':244, 'KEY_BRL_DOT1':497, 'KEY_BRL_DOT10':506, 'KEY_BRL_DOT2':498, 'KEY_BRL_DOT3':499, 'KEY_BRL_DOT4':500, 'KEY_BRL_DOT5':501, 'KEY_BRL_DOT6':502, 'KEY_BRL_DOT7':503, 'KEY_BRL_DOT8':504, 'KEY_BRL_DOT9':505, 'KEY_BUTTONCONFIG':576, 'KEY_C':46, 'KEY_CALC':140, 'KEY_CALENDAR':397, 'KEY_CAMERA':212, 'KEY_CAMERA_DOWN':536, 'KEY_CAMERA_FOCUS':528, 'KEY_CAMERA_LEFT':537, 'KEY_CAMERA_RIGHT':538, 'KEY_CAMERA_UP':535, 'KEY_CAMERA_ZOOMIN':533, 'KEY_CAMERA_ZOOMOUT':534, 'KEY_CANCEL':223, 'KEY_CAPSLOCK':58, 'KEY_CD':383, 'KEY_CHANNEL':363, 'KEY_CHANNELDOWN':403, 'KEY_CHANNELUP':402, 'KEY_CHAT':216, 'KEY_CLEAR':355, 'KEY_CLOSE':206, 'KEY_CLOSECD':160, 'KEY_CNT':768, 'KEY_COFFEE':152, 'KEY_COMMA':51, 'KEY_COMPOSE':127, 'KEY_COMPUTER':157, 'KEY_CONFIG':171, 'KEY_CONNECT':218, 'KEY_CONTEXT_MENU':438, 'KEY_CONTROLPANEL':579, 'KEY_COPY':133, 'KEY_CUT':137, 'KEY_CYCLEWINDOWS':154, 'KEY_D':32, 'KEY_DASHBOARD':204, 'KEY_DATA':631, 'KEY_DATABASE':426, 'KEY_DELETE':111, 'KEY_DELETEFILE':146, 'KEY_DEL_EOL':448, 'KEY_DEL_EOS':449, 'KEY_DEL_LINE':451, 'KEY_DIGITS':413, 'KEY_DIRECTION':153, 'KEY_DIRECTORY':394, 'KEY_DISPLAYTOGGLE':431, 'KEY_DISPLAY_OFF':245, 'KEY_DOCUMENTS':235, 'KEY_DOLLAR':434, 'KEY_DOT':52, 'KEY_DOWN':108, 'KEY_DVD':389, 'KEY_E':18, 'KEY_EDIT':176, 'KEY_EDITOR':422, 'KEY_EJECTCD':161, 'KEY_EJECTCLOSECD':162, 'KEY_EMAIL':215, 'KEY_END':107, 'KEY_ENTER':28, 'KEY_EPG':365, 'KEY_EQUAL':13, 'KEY_ESC':1, 'KEY_EURO':435, 'KEY_EXIT':174, 'KEY_F':33, 'KEY_F1':59, 'KEY_F10':68, 'KEY_F11':87, 'KEY_F12':88, 'KEY_F13':183, 'KEY_F14':184, 'KEY_F15':185, 'KEY_F16':186, 'KEY_F17':187, 'KEY_F18':188, 'KEY_F19':189, 'KEY_F2':60, 'KEY_F20':190, 'KEY_F21':191, 'KEY_F22':192, 'KEY_F23':193, 'KEY_F24':194, 'KEY_F3':61, 'KEY_F4':62, 'KEY_F5':63, 'KEY_F6':64, 'KEY_F7':65, 'KEY_F8':66, 'KEY_F9':67, 'KEY_FASTFORWARD':208, 'KEY_FASTREVERSE':629, 'KEY_FAVORITES':364, 'KEY_FILE':144, 'KEY_FINANCE':219, 'KEY_FIND':136, 'KEY_FIRST':404, 'KEY_FN':464, 'KEY_FN_1':478, 'KEY_FN_2':479, 'KEY_FN_B':484, 'KEY_FN_D':480, 'KEY_FN_E':481, 'KEY_FN_ESC':465, 'KEY_FN_F':482, 'KEY_FN_F1':466, 'KEY_FN_F10':475, 'KEY_FN_F11':476, 'KEY_FN_F12':477, 'KEY_FN_F2':467, 'KEY_FN_F3':468, 'KEY_FN_F4':469, 'KEY_FN_F5':470, 'KEY_FN_F6':471, 'KEY_FN_F7':472, 'KEY_FN_F8':473, 'KEY_FN_F9':474, 'KEY_FN_S':483, 'KEY_FORWARD':159, 'KEY_FORWARDMAIL':233, 'KEY_FRAMEBACK':436, 'KEY_FRAMEFORWARD':437, 'KEY_FRONT':132, 'KEY_G':34, 'KEY_GAMES':417, 'KEY_GOTO':354, 'KEY_GRAPHICSEDITOR':424, 'KEY_GRAVE':41, 'KEY_GREEN':399, 'KEY_H':35, 'KEY_HANGEUL':122, 'KEY_HANGUEL':122, 'KEY_HANJA':123, 'KEY_HELP':138, 'KEY_HENKAN':92, 'KEY_HIRAGANA':91, 'KEY_HOME':102, 'KEY_HOMEPAGE':172, 'KEY_HP':211, 'KEY_I':23, 'KEY_IMAGES':442, 'KEY_INFO':358, 'KEY_INSERT':110, 'KEY_INS_LINE':450, 'KEY_ISO':170, 'KEY_J':36, 'KEY_JOURNAL':578, 'KEY_K':37, 'KEY_KATAKANA':90, 'KEY_KATAKANAHIRAGANA':93, 'KEY_KBDILLUMDOWN':229, 'KEY_KBDILLUMTOGGLE':228, 'KEY_KBDILLUMUP':230, 'KEY_KBDINPUTASSIST_ACCEPT':612, 'KEY_KBDINPUTASSIST_CANCEL':613, 'KEY_KBDINPUTASSIST_NEXT':609, 'KEY_KBDINPUTASSIST_NEXTGROUP':611, 'KEY_KBDINPUTASSIST_PREV':608, 'KEY_KBDINPUTASSIST_PREVGROUP':610, 'KEY_KEYBOARD':374, 'KEY_KP0':82, 'KEY_KP1':79, 'KEY_KP2':80, 'KEY_KP3':81, 'KEY_KP4':75, 'KEY_KP5':76, 'KEY_KP6':77, 'KEY_KP7':71, 'KEY_KP8':72, 'KEY_KP9':73, 'KEY_KPASTERISK':55, 'KEY_KPCOMMA':121, 'KEY_KPDOT':83, 'KEY_KPENTER':96, 'KEY_KPEQUAL':117, 'KEY_KPJPCOMMA':95, 'KEY_KPLEFTPAREN':179, 'KEY_KPMINUS':74, 'KEY_KPPLUS':78, 'KEY_KPPLUSMINUS':118, 'KEY_KPRIGHTPAREN':180, 'KEY_KPSLASH':98, 'KEY_L':38, 'KEY_LANGUAGE':368, 'KEY_LAST':405, 'KEY_LEFT':105, 'KEY_LEFTALT':56, 'KEY_LEFTBRACE':26, 'KEY_LEFTCTRL':29, 'KEY_LEFTMETA':125, 'KEY_LEFTSHIFT':42, 'KEY_LEFT_DOWN':617, 'KEY_LEFT_UP':616, 'KEY_LIGHTS_TOGGLE':542, 'KEY_LINEFEED':101, 'KEY_LIST':395, 'KEY_LOGOFF':433, 'KEY_M':50, 'KEY_MACRO':112, 'KEY_MAIL':155, 'KEY_MAX':767, 'KEY_MEDIA':226, 'KEY_MEDIA_REPEAT':439, 'KEY_MEDIA_TOP_MENU':619, 'KEY_MEMO':396, 'KEY_MENU':139, 'KEY_MESSENGER':430, 'KEY_MHP':367, 'KEY_MICMUTE':248, 'KEY_MINUS':12, 'KEY_MIN_INTERESTING':113, 'KEY_MODE':373, 'KEY_MOVE':175, 'KEY_MP3':391, 'KEY_MSDOS':151, 'KEY_MUHENKAN':94, 'KEY_MUTE':113, 'KEY_N':49, 'KEY_NEW':181, 'KEY_NEWS':427, 'KEY_NEXT':407, 'KEY_NEXTSONG':163, 'KEY_NEXT_FAVORITE':624, 'KEY_NUMERIC_0':512, 'KEY_NUMERIC_1':513, 'KEY_NUMERIC_11':620, 'KEY_NUMERIC_12':621, 'KEY_NUMERIC_2':514, 'KEY_NUMERIC_3':515, 'KEY_NUMERIC_4':516, 'KEY_NUMERIC_5':517, 'KEY_NUMERIC_6':518, 'KEY_NUMERIC_7':519, 'KEY_NUMERIC_8':520, 'KEY_NUMERIC_9':521, 'KEY_NUMERIC_A':524, 'KEY_NUMERIC_B':525, 'KEY_NUMERIC_C':526, 'KEY_NUMERIC_D':527, 'KEY_NUMERIC_POUND':523, 'KEY_NUMERIC_STAR':522, 'KEY_NUMLOCK':69, 'KEY_O':24, 'KEY_OK':352, 'KEY_ONSCREEN_KEYBOARD':632, 'KEY_OPEN':134, 'KEY_OPTION':357, 'KEY_P':25, 'KEY_PAGEDOWN':109, 'KEY_PAGEUP':104, 'KEY_PASTE':135, 'KEY_PAUSE':119, 'KEY_PAUSECD':201, 'KEY_PAUSE_RECORD':626, 'KEY_PC':376, 'KEY_PHONE':169, 'KEY_PLAY':207, 'KEY_PLAYCD':200, 'KEY_PLAYER':387, 'KEY_PLAYPAUSE':164, 'KEY_POWER':116, 'KEY_POWER2':356, 'KEY_PRESENTATION':425, 'KEY_PREVIOUS':412, 'KEY_PREVIOUSSONG':165, 'KEY_PRINT':210, 'KEY_PROG1':148, 'KEY_PROG2':149, 'KEY_PROG3':202, 'KEY_PROG4':203, 'KEY_PROGRAM':362, 'KEY_PROPS':130, 'KEY_PVR':366, 'KEY_Q':16, 'KEY_QUESTION':214, 'KEY_R':19, 'KEY_RADIO':385, 'KEY_RECORD':167, 'KEY_RED':398, 'KEY_REDO':182, 'KEY_REFRESH':173, 'KEY_REPLY':232, 'KEY_RESERVED':0, 'KEY_RESTART':408, 'KEY_REWIND':168, 'KEY_RFKILL':247, 'KEY_RIGHT':106, 'KEY_RIGHTALT':100, 'KEY_RIGHTBRACE':27, 'KEY_RIGHTCTRL':97, 'KEY_RIGHTMETA':126, 'KEY_RIGHTSHIFT':54, 'KEY_RIGHT_DOWN':615, 'KEY_RIGHT_UP':614, 'KEY_RO':89, 'KEY_ROOT_MENU':618, 'KEY_ROTATE_DISPLAY':153, 'KEY_S':31, 'KEY_SAT':381, 'KEY_SAT2':382, 'KEY_SAVE':234, 'KEY_SCALE':120, 'KEY_SCREEN':375, 'KEY_SCREENLOCK':152, 'KEY_SCREENSAVER':581, 'KEY_SCROLLDOWN':178, 'KEY_SCROLLLOCK':70, 'KEY_SCROLLUP':177, 'KEY_SEARCH':217, 'KEY_SELECT':353, 'KEY_SEMICOLON':39, 'KEY_SEND':231, 'KEY_SENDFILE':145, 'KEY_SETUP':141, 'KEY_SHOP':221, 'KEY_SHUFFLE':410, 'KEY_SLASH':53, 'KEY_SLEEP':142, 'KEY_SLOW':409, 'KEY_SLOWREVERSE':630, 'KEY_SOUND':213, 'KEY_SPACE':57, 'KEY_SPELLCHECK':432, 'KEY_SPORT':220, 'KEY_SPREADSHEET':423, 'KEY_STOP':128, 'KEY_STOPCD':166, 'KEY_STOP_RECORD':625, 'KEY_SUBTITLE':370, 'KEY_SUSPEND':205, 'KEY_SWITCHVIDEOMODE':227, 'KEY_SYSRQ':99, 'KEY_T':20, 'KEY_TAB':15, 'KEY_TAPE':384, 'KEY_TASKMANAGER':577, 'KEY_TEEN':414, 'KEY_TEXT':388, 'KEY_TIME':359, 'KEY_TITLE':369, 'KEY_TOUCHPAD_OFF':532, 'KEY_TOUCHPAD_ON':531, 'KEY_TOUCHPAD_TOGGLE':530, 'KEY_TUNER':386, 'KEY_TV':377, 'KEY_TV2':378, 'KEY_TWEN':415, 'KEY_U':22, 'KEY_UNDO':131, 'KEY_UNKNOWN':240, 'KEY_UNMUTE':628, 'KEY_UP':103, 'KEY_UWB':239, 'KEY_V':47, 'KEY_VCR':379, 'KEY_VCR2':380, 'KEY_VENDOR':360, 'KEY_VIDEO':393, 'KEY_VIDEOPHONE':416, 'KEY_VIDEO_NEXT':241, 'KEY_VIDEO_PREV':242, 'KEY_VOD':627, 'KEY_VOICECOMMAND':582, 'KEY_VOICEMAIL':428, 'KEY_VOLUMEDOWN':114, 'KEY_VOLUMEUP':115, 'KEY_W':17, 'KEY_WAKEUP':143, 'KEY_WIMAX':246, 'KEY_WLAN':238, 'KEY_WORDPROCESSOR':421, 'KEY_WPS_BUTTON':529, 'KEY_WWAN':246, 'KEY_WWW':150, 'KEY_X':45, 'KEY_XFER':147, 'KEY_Y':21, 'KEY_YELLOW':400, 'KEY_YEN':124, 'KEY_Z':44, 'KEY_ZENKAKUHANKAKU':85, 'KEY_ZOOM':372, 'KEY_ZOOMIN':418, 'KEY_ZOOMOUT':419, 'KEY_ZOOMRESET':420, 'REL_CNT':16, 'REL_DIAL':7, 'REL_HWHEEL':6, 'REL_MAX':15, 'REL_MISC':9, 'REL_RX':3, 'REL_RY':4, 'REL_RZ':5, 'REL_WHEEL':8, 'REL_X':0, 'REL_Y':1, 'REL_Z':2, }
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


class TypeCode2Name:
  def get(self, t, dfault):
    return self.tc2n_.get(t, dfault)

  def __init__(self, codesDict):
    self.tc2n_ = {}
    for n,c in codesDict.items():
      codeToNames = self.tc2n_.setdefault(name2type(n), {})
      names = codeToNames.setdefault(c, [])
      names.append(n)

typeCode2Name = TypeCode2Name(codesDict)

def tc2ns(t, c):
  global typeCode2Name
  dfault = [""]
  codeToNames = typeCode2Name.get(t, None)
  if codeToNames is None:
    return dfault
  return codeToNames.get(c, dfault)


SplitName = collections.namedtuple("SplitName", "state source shash type code")

def split_full_name2(s, state, sep="."):
  st = True
  if s[0] == "+":
    s = s[1:]
  elif s[0] == "-":
    st = False
    s = s[1:]
  if state is not None:
    s = state.deref(s)
  i = s.find(sep)
  source = None if i == -1 else s[:i]
  shash = None if source is None else get_source_hash(source)
  name = s if i == -1 else s[i+1:]
  code = name2code(name)
  type = name2type(name)
  return SplitName(state=st, source=source, shash=shash, type=type, code=code)


SourceName = collections.namedtuple("SourceName", "source name")
SourceCode = collections.namedtuple("SourceCode", "source code")
SourceNameState = collections.namedtuple("SourceNameState", "source name state")
SourceCodeState = collections.namedtuple("SourceCodeState", "source code state")
TypeCode = collections.namedtuple("TypeCode", "type code")
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
  'mouse.REL_X' -> (get_source_hash('mouse'), codes.REL_X)
  'REL_X' -> (None, codes.REL_X)
  """
  r = fn2sc(s, sep)
  h = get_source_hash(r.source)
  return SourceCode(source=h, code=r.code)


def fn2tc(s, sep="."):
  """
  Splits full name into type and code.
  'mouse.REL_X' -> TypeCode(codes.EV_REL, codes.REL_X)
  'REL_X' -> TypeCode(codes.EV_REL, codes.REL_X)
  """
  r = fn2sn(s, sep)
  return TypeCode(type=name2type(r.name), code=name2code(r.name))


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
  'mouse.REL_X' -> (get_source_hash('mouse'), codes.EV_REL, codes.REL_X)
  'REL_X' -> (None, codes.EV_REL, codes.REL_X)
  """
  r = fn2stc(s, sep)
  h = get_source_hash(r.source)
  return SourceTypeCode(source=h, type=r.type, code=r.code)


def stc2fn(source, type, code, sep=".", nameSep="/"):
  """
  Joins source, type and code into full name.
  'mouse', codes.EV_REL, codes.REL_X -> 'mouse.REL_X'
  None, codes.EV_REL, codes.REL_X -> 'REL_X'
  """
  tcn = tc2ns(type, code)
  if source is not None:
    tcn = (sep.join((source, t)) for t in tcn)
    tcn = nameSep.join(tcn)
  return tcn


def htc2fn(sourceHash, type, code, sep=".", nameSep="/"):
  """
  Joins source hash, type and code into full name.
  get_source_hash('mouse'), codes.EV_REL, codes.REL_X -> 'mouse.REL_X'
  None, codes.EV_REL, codes.REL_X -> 'REL_X'
  """
  s = None if sourceHash is None else str(get_source_name(sourceHash))
  return stc2fn(s, type, code, sep, nameSep)


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
  h = get_source_hash(r.source)
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
  'mouse.REL_X' -> (get_source_hash('mouse'), codes.EV_REL, codes.REL_X, True)
  'REL_X' -> (None, codes.EV_REL, codes.REL_X, True)
  '+mouse.REL_X' -> (get_source_hash('mouse'), codes.EV_REL, codes.REL_X, True)
  '+REL_X' -> (None, codes.EV_REL, codes.REL_X, True)
  '-mouse.REL_X' -> (get_source_hash('mouse'), codes.EV_REL, codes.REL_X, False)
  '-REL_X' -> (None, codes.EV_REL, codes.REL_X, False)
  """
  r = fn2stce(s, sep)
  return SourceTypeCodeState(source=get_source_hash(r.source), type=r.type, code=r.code, state=r.state)


def parse_modifier_desc(s, state, sep="."):
  t = split_full_name2(s, state, sep)
  return SourceCodeState(source=t.shash, code=t.code, state=t.state)


class ReloadException:
  pass


class ExitException:
  pass


class NullJoystick:
  """Placeholder joystick class."""
  def __init__(self, values=None, limits=None, buttons=None):
    self.v_ = {}
    if values is not None:
      for a,v in values.items():
        self.v_[a] = v
    self.limits_ = {}
    if limits is not None:
      for tca,l in limits.items():
        self.limits_[tca] = l
    self.b_ = {}
    if buttons is not None:
      for b,s in buttons.limits():
        self.b_[b] = s
    #logger.debug("{} created".format(self))

  def __del__(self):
    #logger.debug("{} destroyed".format(self))
    pass

  def move_axis(self, tcAxis, v, relative):
    if relative:
      return self.move_axis_by(tcAxis, v)
    else:
      return self.move_axis_to(tcAxis, v)

  def move_axis_by(self, tcAxis, v):
    desired = self.get_axis_value(tcAxis)+v
    actual = self.move_axis_to(tcAxis, desired)
    return v - (desired - actual)

  def move_axis_to(self, tcAxis, v):
    limits = self.get_limits(tcAxis)
    v = clamp(v, *limits)
    if tcAxis in self.v_:
      self.v_[tcAxis] = v
      return v
    else:
      return 0.0

  def get_axis_value(self, tcAxis):
    return self.v_.get(tcAxis, 0.0)

  def get_limits(self, tcAxis):
    return self.limits_.get(tcAxis, (-float("inf"), float("inf")))

  def get_supported_axes(self):
    return self.v_.keys()

  def set_button_state(self, button, state):
    if button in self.b_:
      self.b_[button] = state

  def get_button_state(self, button):
    return self.b_.get(button, False)

  def get_supported_buttons(self):
    return self.b_.keys()


class CompositeJoystick:
  def move_axis(self, tcAxis, v, relative):
    if tcAxis not in self.get_supported_axes():
      return 0.0 if relative else v
    desired = self.get_axis_value(tcAxis) + v if relative else v
    limits = self.get_limits(tcAxis)
    actual = clamp(desired, *limits)
    children = self.a2c_[tcAxis] if self.checkChild_ else self.children_
    for c in children:
      c.move_axis(tcAxis, actual, relative=False)
    self.axes_[tcAxis] = actual
    return v - (desired - actual) if relative else actual

  def get_axis_value(self, tcAxis):
    return self.axes_.get(tcAxis, 0.0)

  def get_limits(self, tcAxis):
    return self.limits_.get(tcAxis, [0.0, 0.0])

  def get_supported_axes(self):
    return self.axes_.keys()

  def set_button_state(self, button, state):
    children = self.b2c_[button] if self.checkChild_ else self.children_
    for c in children:
      c.set_button_state(button, state)
    self.buttons_[button] = state

  def get_button_state(self, button):
    return self.buttons_.get(button, False)

  def get_supported_buttons(self):
    return self.buttons_.keys()

  def __init__(self, children, checkChild=True, union=True):
    self.children_ = children
    self.checkChild_, self.union_ = checkChild, union
    self.axes_, self.limits_, self.buttons_ = {}, {}, {}
    self.a2c_, self.b2c_ = {}, {}
    self.update_()

  def update_(self):
    #finding supported axes and buttons
    axes, buttons = set(), set()
    op = set.update if self.union_ else set.intersection_update
    for c in self.children_:
      op(axes, set(c.get_supported_axes()))
      op(buttons, set(c.get_supported_buttons()))
    #setting limits and initial values
    for tcAxis in axes:
      #limits
      l = [-float("inf"), float("inf")]
      for c in self.children_:
        if tcAxis in c.get_supported_axes():
          cl = list(c.get_limits(tcAxis))
          if cl[0] > cl[1] : cl[0], cl[1] = cl[1], cl[0]
          l[0], l[1] = max(l[0], cl[0]), min(l[1], cl[1])
          if l[0] >= l[1]:
            l = [0.0, 0.0]
      self.limits_[tcAxis] = l
      #values and axis-to-children mapping
      v = 0.0
      v = clamp(v, *l)
      self.axes_[tcAxis] = v
      a2c = []
      self.a2c_[tcAxis] = a2c
      for c in self.children_:
        if tcAxis in c.get_supported_axes():
          a2c.append(c)
          c.move_axis(tcAxis, v, relative=False)
    #buttons and button-to-children mapping
    v = False
    for button in buttons:
      self.buttons_[button] = v
      b2c = []
      self.b2c_[button] = b2c
      for c in self.children_:
        if button in c.get_supported_buttons():
          b2c.append(c)
          c.set_button_state(button, v)


class Event(object):
  def __str__(self):
    fmt = "type: {} ({}), code: {} (0x{:X}, {}), value: {}, timestamp: {}"
    return fmt.format(self.type, "/".join(type2names(self.type)), self.code, self.code, stc2fn(None, self.type, self.code), str2(self.value), self.timestamp)

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
    return Event.__str__(self) + fmt.format(self.source, get_source_name(self.source), modifiers)
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
  """
  def read_one(self):
    while True:
      event = self.next_.read_one()
      if event is None:
        if len(self.events_) != 0:
          k, event = self.events_.items()[0]
          del self.events_[k]
        break
      elif event.type == codes.EV_REL:
        k = (event.source, event.code, None if event.modifiers is None else tuple(m for m in event.modifiers))
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
    for d in self.devices_.values():
      try:
        event = d.read_one()
        while event is not None:
          events.append(event)
          event = d.read_one()
      except RuntimeError as e:
        logger.error(e)
        continue
    events.sort(key = lambda e : e.timestamp)
    if self.sink_ is not None:
      for event in events:
        #logger.debug("{}: Sending event: {}".format(self, event))
        self.sink_(event)

  def set_sink(self, sink):
    self.sink_ = sink

  def swallow(self, name, s):
    if name is None:
      for n,d in self.devices_.items():
        d.swallow(s)
    else:
      self.devices_.get(name).swallow(s)

  def __init__(self, devices, sink=None):
    self.devices_, self.sink_ = devices, sink
    #logger.debug("{} created".format(self))

  def __del__(self):
    #logger.debug("{} destroyed".format(self))
    pass


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


class MoveCurve:
  def __call__(self, event):
    if self.curve_ is not None and event.type in (codes.EV_REL,):
      self.curve_.move_by(event.value*self.factor_, event.timestamp)
      return True
    else:
      return False

  def set_factor(self, factor):
    self.factor_ = factor

  def __init__(self, curve, factor=1.0):
    self.curve_, self.factor_ = curve, factor


class SetJoystickAxis:
  def __init__(self, joystick, tcAxis, value):
    self.js_, self.axis_, self.value_ = joystick, tcAxis, value
    #logger.debug("{} created".format(self))

  def __del__(self):
    #logger.debug("{} destroyed".format(self))
    pass

  def __call__(self, event):
    self.js_.move_axis(self.axis_, self.value_, False)
    return True


def SetJoystickAxes(joystick, axesAndValues):
  def op(event):
    for tcAxis, value in axesAndValues:
      joystick.move_axis(tcAxis, value, False)
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


class MoveAxis:
  def __call__(self, event):
    if self.axis_ is not None:
      value = self.value_
      if self.stopAt_ is not None:
        current = self.axis_.get()
        proposed = current + value if self.relative_ == True else value
        selected = None
        for v in self.stopAt_:
          if v == current:
            continue
          if clamp(v, current, proposed) == v:
            if selected is None or (abs(v - current) < absSelectedDelta):
              selected = v
              absSelectedDelta = abs(selected - current)
        if selected is not None:
          value = selected - current if self.relative_ == True else selected
      self.axis_.move(value, self.relative_)
    return True

  def set_value(self, value):
    self.value_ = value

  def __init__(self, axis, value, relative=False, stopAt=None):
    self.axis_, self.value_, self.relative_, self.stopAt_ = axis, value, relative, stopAt


def MoveAxes(axesAndValues):
  def moveAxesOp(event):
    for axis,value,relative in axesAndValues:
      axis.move(value, relative)
  return moveAxesOp


def MoveAxisByEvent(axis):
  def op(event):
    if axis is not None:
      relative = None
      if event.type == codes.EV_REL:
        relative = True
      elif event.type == codes.EV_ABS:
        relative = False
      if relative is not None:
        axis.move(event.value, relative)
        return True
    return False
  return op


def SetButtonState(output, button, state):
  def op(event):
    output.set_button_state(button, state)
    #logger.debug("Setting {} key {} (0x{:X}) to {}".format(output, stc2fn(None, codes.EV_KEY, button), button, state))
    return True
  return op


class ClickSink:
  def __call__(self, event):
    numClicks = 0
    if event.type == codes.EV_KEY:
      numClicks = self.update_keys(event)

    r = False
    if self.next_:
      r = self.next_(event)
      if numClicks != 0:
        clickEvent = ClickEvent.from_event(event, numClicks)
        rc = self.next_(clickEvent)
        r = r or rc
    return r

  #returns number of clicks
  def update_keys(self, event):
    if event.type == codes.EV_KEY:
      #logger.debug("{} {}".format(event.code, event.value))
      self.keys_.setdefault(event.code, [event.value, event.timestamp, 0])
      keyData = self.keys_[event.code]
      prevValue, prevTimestamp, prevNumClicks = keyData
      dt = event.timestamp - prevTimestamp
      r = 0
      if event.value == 0 and prevValue == 1 and dt <= self.clickTime_:
        keyData[2] += 1
        r = keyData[2]
      elif event.value == 1 and prevValue == 0 and dt > self.clickTime_:
        keyData[2] = 0
      keyData[0] = event.value
      keyData[1] = event.timestamp
      return r
    else:
      return 0

  def set_next(self, next):
    self.next_ = next
    return next

  def __init__(self, clickTime):
    self.next_, self.keys_, self.clickTime_ = None, {}, clickTime
    #logger.debug("{} created".format(self))

  def __del__(self):
    #logger.debug("{} destroyed".format(self))
    pass


class HoldEvent(InputEvent):
  def __init__(self, k, value, timestamp, source, modifiers, heldTime):
    InputEvent.__init__(self, codes.EV_KEY, k, value, timestamp, source, modifiers)
    self.heldTime = heldTime


class HoldSink:
  KeyDesc = collections.namedtuple("KeyDesc", "source code modifiers")
  HT = collections.namedtuple("HT", "keyDesc period value num")

  def __call__(self, event):
    if event.type == codes.EV_BCT and event.code == codes.BCT_INIT and event.value == 0:
      self.clear()
    elif event.type == codes.EV_KEY:
      if event.value == 0:
        for i in range(len(self.keyData_)):
          kd = self.keyData_[i]
          #ignore modifiers to correctly process key release if the key is modifier itself
          keyDesc = HoldSink.KeyDesc(event.source, event.code, None)
          if self.match_(kd.keyDesc, keyDesc):
            self.keyData_[i] = None
        self.cleanup_()
      elif event.value == 1:
        class KD:
          pass
        keyDesc = HoldSink.KeyDesc(event.source, event.code, tuple(m for m in event.modifiers))
        found = False
        for kd in self.keyData_:
          if kd.keyDesc == keyDesc:
            found = True
            break
        if found == False:
          for ht in self.holdTimes_:
            if self.match_(keyDesc, ht.keyDesc):
              kd = KD()
              kd.keyDesc, kd.ht, kd.initial, kd.timestamp, kd.num = keyDesc, ht, event.timestamp, event.timestamp, ht.num
              self.keyData_.append(kd)
    return self.next_(event) if self.next_ else False

  def update(self, tick, timestamp):
    for i in range(len(self.keyData_)):
      kd = self.keyData_[i]
      currentHoldTime = timestamp - kd.timestamp
      if currentHoldTime >= kd.ht.period:
        if self.next_ is not None:
          heldTime = timestamp - kd.initial
          ht = kd.ht
          keyDesc = kd.keyDesc
          modifiers = None if keyDesc.modifiers is None else list(keyDesc.modifiers)
          event = HoldEvent(keyDesc.code, ht.value, timestamp, keyDesc.source, modifiers, heldTime)
          #logger.debug("{}: {}".format(self, event))
          self.next_(event)
        if kd.num > 0:
          kd.num = kd.num - 1
          if kd.num == 0:
            self.keyData_[i] = None
    self.cleanup_()

  def add(self, source, code, modifiers, period, value, num):
    modifiers = tuple(m for m in modifiers) if modifiers is not None else None
    keyDesc = HoldSink.KeyDesc(source, code, modifiers)
    ht = HoldSink.HT(keyDesc, period, value, num)
    self.holdTimes_.append(ht)

  def set_next(self, next):
    self.next_ = next
    return next

  def clear(self):
    self.keyData_ = []

  def __init__(self):
    self.next_, self.keyData_, self.holdTimes_ = None, [], []
    #logger.debug("{} created".format(self))

  def __del__(self):
    #logger.debug("{} destroyed".format(self))
    pass

  def match_(self, keyDesc, ht):
    return (ht.source is None or (ht.source == keyDesc.source)) and (ht.code is None or (ht.code == keyDesc.code)) and (ht.modifiers is None or (ht.modifiers == keyDesc.modifiers))

  def cleanup_(self):
    while True:
      try:
        self.keyData_.remove(None)
      except ValueError:
        break


Modifier = collections.namedtuple("Modifier", "source code")

def cmp_modifiers(eventModifier, referenceModifier):
  r = False
  if eventModifier.code == referenceModifier.code:
    if referenceModifier.source is not None:
      r = eventModifier.source == referenceModifier.source
    else:
      r = True
  return r

class ModifierSink:
  APPEND = 0
  OVERWRITE = 1

  def __call__(self, event):
    if event.type == codes.EV_BCT and event.code == codes.BCT_INIT and event.value == 0:
      self.clear()
    elif event.type == codes.EV_KEY:
      if self.addedModifiers_ is not None:
        em = Modifier(source=event.source, code=event.code)
        #logger.debug("{}.__call__(): got: {}".format(self, eventModifier))
        for am in self.addedModifiers_:
          #logger.debug("{}.__call__(): checking against: {}".format(self, referenceModifier))
          if cmp_modifiers(em, am):
            #logger.debug("{}.__call__(): {} matched {}".format(self, eventModifier, referenceModifier))
            if event.value == 1 and em not in self.currentModifiers_:
              self.currentModifiers_.append(em)
            elif event.value == 0 and em in self.currentModifiers_:
              self.currentModifiers_.remove(em)
          else:
            #logger.debug("{}.__call__(): {} mismatched {}".format(self, eventModifier, referenceModifier))
            pass

    if self.next_:
      eventWithModifiers = event.type in (codes.EV_KEY, codes.EV_REL, codes.EV_ABS)
      if not eventWithModifiers:
        return self.next_(event)
      else:
        oldModifiers = None
        try:
          assert type(event.modifiers) is list
          if self.saveModifiers_:
            oldModifiers = [m for m in event.modifiers]
          if self.mode_ == self.APPEND:
            for rm in self.removedModifiers_:
              for em in event.modifiers:
                if cmp_modifiers(em, rm):
                  event.modifiers.remove(em)
            for m in self.currentModifiers_:
              if m not in event.modifiers:
                event.modifiers.append(m)
          elif self.mode_ == self.OVERWRITE:
            event.modifiers = [m for m in self.currentModifiers_]
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
    self.currentModifiers_ = []

  def __init__(self, next = None, modifierDescs = None, saveModifiers = True, mode = 0):
    #logger.debug("{}.__init__(): tracked modifiers: {}".format(self, [(s, stc2fn(None, codes.EV_KEY, m)) for s,m in modifiers]))
    self.currentModifiers_, self.next_, self.addedModifiers_, self.removedModifiers_, self.saveModifiers_, self.mode_ = [], next, [], [], saveModifiers, mode
    if modifierDescs is not None:
      for md in modifierDescs:
        if md.state == True:
          self.addedModifiers_.append(Modifier(md.source, md.code))
        elif md.state == False:
          self.removedModifiers_.append(Modifier(md.source, md.code))


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
  gSens_ = {}

  def __call__(self, event):
    oldValue = None
    try:
      if event.type in (codes.EV_REL, codes.EV_ABS):
        if self.sens_ is not None:
          keys = self.keyOp_(event)
          sens = self.sens_.get(keys[0])
          if sens is None:
            sens = self.sens_.get(keys[1], 1.0)
          oldValue = event.value
          event.value *= sens
      return self.next_(event) if self.next_ is not None else False
    finally:
      if oldValue is not None:
        event.value = oldValue

  def set_next(self, next):
    self.next_ = next
    return next

  def set_sens(self, sc, s):
    sens = self.sens_.get(sc, None)
    if sens is None:
      logger.debug("No sens preinitialized for {}".format(htc2fn(*sc)))
    self.sens_[sc] = s

  def get_sens(self, sc):
    sens = self.sens_.get(sc, 0.0)
    return sens

  def get_name(self):
    return "" if self.name_ is None else self.name_

  def set_name(self, name):
    self.name_ = name

  def __init__(self, sens, keyOp = lambda event : (SourceTypeCode(source=event.source, type=event.type, code=event.code), SourceTypeCode(source=None, type=event.type, code=event.code)), name = None):
    self.next_, self.sens_, self.keyOp_, self.name_ = None, sens, keyOp, name


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


class MappingSink:
  def __call__(self, event):
    frm = SourceTypeCode(event.source, event.type, event.code)
    to = self.mapping_.get(frm, None)
    if to is not None:
      event.source, event.type, event.code = to.source, to.type, to.code
    try:
      if self.next_ is not None:
        return self.next_(event)
    finally:
      if to is not None:
        event.source, event.type, event.code = frm.source, frm.type, frm.code

  def set_next(self, next):
    self.next_ = next
    return next

  def __init__(self, mapping):
    assert type(mapping) in (dict, collections.OrderedDict)
    self.mapping_ = mapping


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


class AttrsEventTest:
  __slots__ = ("attrs_", "cmp_",)
  def __call__(self, event):
    for attrName, attrValue in self.attrs_:
      eventValue = getattr(event, attrName, None)
      if eventValue is None:
        #logger.debug("{}: Event [{}] does not have attribute '{}'".format(self, event, attrName))
        return False
      if not self.cmp_(attrName, eventValue, attrValue):
        #logger.debug("{}: Mismatch while matching attrs {} with event [{}] at attr '{}' (got {}, needed {})".format(self, c.attrs, event, attrName, eventValue, attrValue))
        return False
    return True
  def __init__(self, attrs, cmp):
    self.attrs_, self.cmp_ = attrs, cmp


class PropTestsEventTest:
  __slots__ = ("pd_",)

  def __call__(self, event):
    for propName, propTest in self.pd_:
      eventValue = getattr(event, propName, None)
      if eventValue is None:
        return False
      if not propTest(eventValue):
        return False
    return True

  def __init__(self, pd):
    self.pd_ = pd


class BindSink:
  class ChildInfo:
    __slots__ = ("child", "name",)
    def __init__(self, child, name=None):
      self.child, self.name = child, name
  class ChildrenInfo:
    __slots__ = ("op", "level", "children",)
    def __init__(self, op, level, children):
      self.op, self.level, self.children = op, level, [cc for cc in children]
    def __str__(self):
      return "<op:{}; level:{}; children:{}>".format(self.op, self.level, self.children)

  def __call__(self, event):
    #logger.debug("{}: processing {})".format(self, event))
    self.update_()
    if len(self.children_) == 0:
      return False
    level, processed = self.children_[0].level, False
    for c in self.children_:
      if c.level > level:
        if processed == True:
          break
        else:
          level = c.level
      if c.op is None or c.op(event) == True:
        #logger.debug("{}: Event [{}] matched attrs {}".format(self, event, c.attrs))
        for ci in c.children:
          #logger.debug("Sending event {} to {}".format(str(event), cc))
          processed = ci.child(event) or processed
    return processed

  def add(self, op, child, level=0, name=None):
    #logger.debug("{}: Adding child {} to {} for level {}".format(self, child, attrsOrOp, level))
    assert(child is not None)
    for ci in self.children_:
      if op == ci.op:
        ci.children.append(self.ChildInfo(child, name))
        break
    else:
      self.children_.append(self.ChildrenInfo(op, level, [self.ChildInfo(child, name)]))
    self.dirty_ = True
    return child

  def clear(self):
    del self.children_[:]

  def get(self, name):
    """Returns binding proxy that returns ed op on .get("on") and output action or sink on .get("do").
       Since ed can be chared among several outputs, changing given ed will affect other bindings!
    """
    class BindingProxy:
      def get(self, propName):
        return self.m_.get(propName, None)
      __slots__ = ("m_",)
      def __init__(self, i, o):
        self.m_ = {"on" : i, "do" : o}
    for childrenInfo in self.children_:
      for childInfo in childrenInfo.children:
        if childInfo.name == name:
          return BindingProxy(childrenInfo.op, childInfo.child)
    return None

  __slots__ = ("children_", "dirty_")
  def __init__(self):
    self.children_ = []
    self.dirty_ = False
    #logger.debug("{} created".format(self))

  def __del__(self):
    #logger.debug("{} destroyed".format(self))
    pass

  def update_(self):
    if self.dirty_ == True:
      self.children_.sort(key=lambda c : c.level)
      self.dirty_ = False


class PropTest:
  def __call__(self, v):
    return True


class EqPropTest(PropTest):
  def __call__(self, v):
    return self.v_ == v

  def __str__(self):
    return "EqPropTest({})".format(self.v_)

  def __repr__(self):
    return str(self)

  def __init__(self, v):
    self.v_ = v


class EqInPropTest(PropTest):
  def __call__(self, v):
    return v in self.v_ if type(self.v_) in (list, tuple) else self.v_ == v

  def __str__(self):
    return "EqInPropTest({})".format(self.v_)

  def __repr__(self):
    return str(self)

  def __init__(self, v):
    self.v_ = v


class ItemEqPropTest(PropTest):
  def __call__(self, v):
    return self.v_ == v[self.i_]

  def __str__(self):
    return "ItemEqPropTest({}, {})".format(self.v_, self.i_)

  def __repr__(self):
    return str(self)

  def __init__(self, v, i):
    self.v_, self.i_ = v, i


class CmpPropTest(PropTest):
  def __call__(self, v):
    return self.cmp_(v, self.v_)

  def __init__(self, v, compare):
    self.v_, self.cmp_ = v, compare


def cmp_modifiers_with_descs(eventModifiers, attrModifierDescs):
  """
  Returns False if some event modifiers were unmatched, else True.
  KEY_ANY matches all keys (from given source if source is specified),
  so it should be specified last in modifier descs.
  """
  r = False
  if attrModifierDescs is None:
    r = eventModifiers is None
  elif len(attrModifierDescs) == 0:
    r = eventModifiers is None or len(eventModifiers) == 0
  else:
    r, numMatches = True, 0
    for am in attrModifierDescs:
      found = am.code == codes.KEY_ANY
      #checking for eventModifiers None-ness here ensures that result would be True
      #if eventModifiers is None and attrModifierDescs requires a modifier to be missing
      if eventModifiers is not None:
        for em in eventModifiers:
          sourceFound = am.source is None or am.source == em.source
          codeFound = am.code == codes.KEY_ANY or am.code == em.code
          found = sourceFound and codeFound
          if found:
            break
      if am.state == False:
        found = not found
      r = r and found
      if not r:
        break
      else:
        numMatches += 1
    r = r and (numMatches >= len(eventModifiers))
  return r


class ModifiersPropTest(PropTest):
  def __call__(self, v):
    return cmp_modifiers_with_descs(v, self.v_)

  def __init__(self, v):
    self.v_ = v


class ET:
  @staticmethod
  def move(axis, modifiers = None):
    r = (("type", EqPropTest(codes.EV_REL)), ("code", EqPropTest(axis)))
    if modifiers is not None:
      r = r + (("modifiers", ModifiersPropTest(modifiers)),)
    return PropTestsEventTest(r)

  @staticmethod
  def move_to(axis, modifiers = None):
    r = (("type", EqPropTest(codes.EV_ABS)), ("code", EqPropTest(axis)))
    if modifiers is not None:
      r = r + (("modifiers", ModifiersPropTest(modifiers)),)
    return PropTestsEventTest(r)

  @staticmethod
  def press(key, modifiers = None):
    r  = (("type", EqPropTest(codes.EV_KEY)), ("code", EqPropTest(key)), ("value", EqPropTest(1)))
    if modifiers is not None:
      r = r + (("modifiers", ModifiersPropTest(modifiers)),)
    return PropTestsEventTest(r)

  @staticmethod
  def release(key, modifiers = None):
    r = (("type", EqPropTest(codes.EV_KEY)), ("code", EqPropTest(key)), ("value", EqPropTest(0)))
    if modifiers is not None:
      r = r + (("modifiers", ModifiersPropTest(modifiers)),)
    return PropTestsEventTest(r)

  @staticmethod
  def click(key, modifiers = None):
    r = (("type", EqPropTest(codes.EV_KEY)), ("code", EqPropTest(key)), ("value", EqPropTest(3)), ("num_clicks", EqPropTest(1)))
    if modifiers is not None:
      r = r + (("modifiers", ModifiersPropTest(modifiers)),)
    return PropTestsEventTest(r)

  @staticmethod
  def doubleclick(key, modifiers = None):
    r = (("type", EqPropTest(codes.EV_KEY)), ("code", EqPropTest(key)), ("value", EqPropTest(3)), ("num_clicks", EqPropTest(2)))
    if modifiers is not None:
      r = r + (("modifiers", ModifiersPropTest(modifiers)),)
    return PropTestsEventTest(r)

  @staticmethod
  def multiclick(key, n, modifiers = None):
    r = (("type", EqPropTest(codes.EV_KEY)), ("code", EqPropTest(key)), ("value", EqPropTest(3)), ("num_clicks", EqPropTest(n)))
    if modifiers is not None:
      r = r + (("modifiers", ModifiersPropTest(modifiers)),)
    return PropTestsEventTest(r)

  @staticmethod
  def bcast():
    r = (("type", EqPropTest(codes.EV_BCT)),)
    return PropTestsEventTest(r)

  @staticmethod
  def init(i):
    r = (("type", EqPropTest(codes.EV_BCT)), ("code", EqPropTest(codes.BCT_INIT)), ("value", EqPropTest(i)))
    return PropTestsEventTest(r)

  @staticmethod
  def any():
    r = ()
    return PropTestsEventTest(r)


class StateSink:
 def __call__(self, event):
   #logger.debug("{}: processing event: {}, state: {}, next: {}".format(self, event, self.state_, self.next_))
   if (self.state_ == True) and (self.next_ is not None):
     return self.next_(event)
   else:
     return False

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
     return self.next_(event)
   else:
     return False

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
    self.sources_, self.state_ = [get_source_hash(s) for s in sources], state


class ModeInitEvent(Event):
  def __str__(self):
    return Event.__str__(self) + ", other: {}".format(self.other)

  def __init__(self, state, timestamp=None, other=None):
    if timestamp is None:
      timestamp = time.time()
    Event.__init__(self, codes.EV_BCT, codes.BCT_INIT, state, timestamp)
    self.other = other


class ModeSink:
  def __call__(self, event):
    #if event.type == codes.EV_BCT and event.code == codes.BCT_INIT:
    #  logger.debug("{}: Recieved init event: {}".format(self, event.value))
    child = self.children_.get(self.mode_, None)
    if child is not None:
      return child(event)
    else:
      return False

  def set_mode(self, mode, report=True):
    if mode == self.mode_:
      return True
    if report:
      self.reportModeSwitchCb_(self.name_, self.mode_, mode)
    #logger.debug("{}({}): Setting mode: {}".format(self.name_, self, mode))
    if mode not in self.children_:
      logger.warning("{}: No such mode: {}".format(self.name_, mode))
      return False
    self.set_active_child_state_(0, mode)
    old = self.mode_
    self.mode_ = mode
    self.set_active_child_state_(1, old)
    return True

  def get_mode(self):
    return self.mode_

  def add(self, mode, child):
    #logger.debug("{}: Adding child {} to  mode {}".format(self, child, mode))
    if child is None:
      raise RuntimeError("Child is None")
    self.children_[mode] = child
    return child

  def get(self, modeName):
    return self.children_.get(modeName, None)

  def set_active_child_state_(self, state, other):
    if self.mode_ in self.children_:
      child = self.children_.get(self.mode_, None)
      if child is not None:
        #logger.debug("{}: Notifying child {} about setting state to {}".format(self, child, state))
        child(ModeInitEvent(state=state, other=other))

  def __init__(self, name="", reportModeSwitchCb=None):
    self.children_, self.mode_, self.name_ = {}, None, name
    if reportModeSwitchCb is None:
      def smc(name, old, new):
        logger.info("{}: Setting mode: {}".format(name, str2(new)))
      reportModeSwitchCb = smc
    self.reportModeSwitchCb_ = reportModeSwitchCb


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

  def restore(self, report=True):
    if len(self.mode_):
      self.sink_.set_mode(self.mode_.pop(), report)

  def add(self, mode, current, report=True):
    if current is None or self.sink_.get_mode() in current:
      self.mode_.append(mode)
      self.sink_.set_mode(mode, report)
      return True
    else:
      return False

  def remove(self, mode, current, report=True):
    if current is None or self.sink_.get_mode() in current:
      for i in range(len(self.mode_)-1, -1, -1):
        if self.mode_[i] == mode:
          self.mode_.pop(i)
          break;
      self.set_top_mode_(report)
      return True
    else:
      return False

  def swap(self, f, t, current, report=True):
    if current is None or self.sink_.get_mode() in current:
      for i in range(len(self.mode_)-1, -1, -1):
        if self.mode_[i] == f:
          self.mode_[i] = t
          break;
      self.set_top_mode_(report)
      return True
    else:
      return False

  def cycle_swap(self, modes, current, report=True):
    if current is None or self.sink_.get_mode() in current:
      lm = len(modes)
      for i in range(len(self.mode_)-1, -1, -1):
        for j in range(0, lm):
          if self.mode_[i] == modes[j]:
            j = j+1 if j < lm-1 else 0
            self.mode_[i] = modes[j]
            self.set_top_mode_(report)
            return True
    return False

  def clear(self):
    self.mode_ = []
    return True

  def set(self, mode, save, current, report=True):
    if current is None or self.sink_.get_mode() in current:
      self.save_(save)
      self.sink_.set_mode(mode, report)
      return True
    else:
      return False

  def cycle(self, modes, step, loop, save, report=True):
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
    self.sink_.set_mode(m, report)
    return True

  def __init__(self, sink):
    self.sink_, self.mode_ = sink, []

  def make_save(self):
    def op(event):
      return self.save()
    return op
  def make_restore(self, report=True):
    def op(event):
      return self.restore(report)
    return op
  def make_add(self, mode, current=None, report=True):
    current = self.make_current_(current)
    def op(event):
      return self.add(mode, current, report)
    return op
  def make_remove(self, mode, current=None, report=True):
    current = self.make_current_(current)
    def op(event):
      return self.remove(mode, current, report)
    return op
  def make_swap(self, f, t, current=None, report=True):
    current = self.make_current_(current)
    def op(event):
      return self.swap(f, t, current, report)
    return op
  def make_cycle_swap(self, modes, current=None, report=True):
    current = self.make_current_(current)
    def op(event):
      return self.cycle_swap(modes, current, report)
    return op
  def make_clear(self):
    def op(event):
      return self.clear()
    return op
  def make_set(self, mode, save, current, report=True):
    current = self.make_current_(current)
    def op(event):
      return self.set(mode, save, current, report)
    return op
  def make_cycle(self, modes, step, loop, save, report=True):
    def op(event):
      return self.cycle(modes, step, loop, save, report)
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

  def set_top_mode_(self, report):
    if len(self.mode_):
      m = self.mode_[-1]
      if m != self.sink_.get_mode():
        self.sink_.set_mode(m, report)

  def make_current_(self, current):
    if current is not None and type(current) not in (tuple, list):
      return [current]
    else:
      return current


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


class ValueEvent(Event):
  def __str__(self):
    return "{}, name:{}".format(Event.__str__(self), self.name)

  def __init__(self, name, value, timestamp=None):
    if timestamp is None:
      timestamp = time.time()
    Event.__init__(self, codes.EV_BCT, codes.BCT_VALUE, value, timestamp)
    self.name = name


class ValuesSink:
  def __call__(self, event):
    if self.next_ is not None:
      return self.next_(event)

  def set_value(self, name, value):
    self.values_[name] = value
    self.emit_event_(name)

  def get_value(self, name):
    return self.values_[name]

  def set_value_item(self, name, item, value):
    self.values_[name][item] = value
    self.emit_event_(name)

  def get_value_item(self, name, item):
    return self.values_[name][item]

  def set_next(self, nxt):
    self.next_ = nxt

  def __init__(self, nxt=None):
    self.values_, self.next_ = {}, nxt

  def emit_event_(self, name):
    if self.next_ is not None:
      event = ValueEvent(name, self.values_[name])
      self.next_(event)


#Funcs
class ConstantFunc:
  def __call__(self, x):
    if self.tracker_ is not None:
      self.tracker_({ "caller" : self, "x" : x, "y" : self.value_ })
    return self.value_

  def __init__(self, value, tracker=None):
    self.value_ = value
    self.tracker_ = tracker


class PolynomialFunc:
  def __call__(self, x):
    x += self.off_
    y = 0.0
    for p,k in self.coeffs_.items():
      if k == 0.0:
        continue
      y += k*x**p
    if self.tracker_ is not None:
      self.tracker_({ "caller" : self, "x" : x, "y" : y })
    return y

  def set_coeffs(self, coeffs):
    self.coeffs_ = coeffs

  def __init__(self, coeffs, off=0.0, tracker=None):
    self.coeffs_, self.off_, self.tracker_ = coeffs, off, tracker


class SegmentFunc:
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
    if self.tracker_ is not None:
      self.tracker_({ "caller" : self, "x" : x, "y" : y, "x0" : self.x_[i], "x1" : self.x_[j], "y0" : self.y_[i], "y1" : self.y_[j] })
    return y

  def __init__(self, data, factor=1.0, clampLeft=False, clampRight=False, tracker=None):
    temp = [(float(d[0]), float(d[1])) for d in data if len(d) == 2]
    temp.sort(key = lambda d : d[0])
    if len(temp) == 0:
      self.x_, self.y_ = (), ()
    else:
      self.x_, self.y_ = zip(*temp)
    self.factor_ = factor
    self.clampLeft_, self.clampRight_ = clampLeft, clampRight
    self.tracker_ = tracker


class SigmoidFunc:
  """https://en.wikipedia.org/wiki/Logistic_function"""
  def __call__(self, x):
    ert = math.e**(self.r_ * (x - self.s_))
    y =  (self.k_ * self.p0_ * ert) / (self.k_ + self.p0_ * (ert - 1.0))
    if self.tracker_ is not None:
      self.tracker_({ "caller" : self, "x" : x, "y" : y })
    return y

  def __init__(self, k, p0, r, s, tracker=None):
    self.k_, self.p0_, self.r_, self.s_ = k, p0, r, s
    self.tracker_ = tracker


def calc_bezier(points, t):
  """Uses points as scratch space."""
  for n in xrange(len(points)-1, 0, -1):
    for i in xrange(0, n):
      p0, p1 = points[i], points[i+1]
      points[i] = [t*p1v + (1.0-t)*p0v for p1v,p0v in zip(p1,p0)]
  return points[0]


class BezierFunc:
  def __call__(self, x):
    l, r = self.points_[0][0], self.points_[len(self.points_)-1][0]
    x = clamp(x, l, r)
    #TODO Is this correct?
    t = (x - l) / (r - l)
    points = [p for p in self.points_]
    #logger.debug("{}: points: {}, t: {}".format(self, points, t))
    y = calc_bezier(points, t)[1]
    #logger.debug("{}: result: {: .3f}".format(self, y))
    if self.tracker_ is not None:
      self.tracker_({ "caller" : self, "x" : x, "y" : y })
    return y

  def __init__(self, points, tracker=None):
    self.points_ = tuple((p[0],p[1]) for p in points)
    self.tracker_ = tracker


class SegmentedBezierFunc:
  def __call__(self, x):
    keys = [p["c"][0] for p in self.points_]
    i = bisect.bisect_left(keys, x)-1
    l = len(self.points_)
    i = clamp(i, 0, max(l-2, 0))
    j = clamp(i+1, 0, max(l-1, 0))

    leftPoints, rightPoints = self.points_[i], self.points_[j]
    l, r = leftPoints["c"][0], rightPoints["c"][0]
    x = clamp(x, l, r)
    #TODO Is this correct?
    t = (x - l) / (r - l)

    points = []
    points.append(leftPoints["c"])
    if "r" in leftPoints : points.append(leftPoints["r"])
    if "l" in rightPoints : points.append(rightPoints["l"])
    points.append(rightPoints["c"])

    #logger.debug("{}: points: {}".format(self, points))
    y = calc_bezier(points, t)[1]
    #logger.debug("{}: t: {: .3f}, result: {: .3f}".format(self, t, y))
    if self.tracker_ is not None:
      self.tracker_({ "caller" : self, "x" : x, "y" : y })
    return y

  def __init__(self, points, tracker=None):
    self.points_ = tuple(p for p in points)
    self.tracker_ = tracker


class WeightedFunc:
  def __call__(self, x):
    def f(x):
      return self.weight_*x**self.degree_ + (1.0 - self.weight_)*x
    fDB = f(self.deadband_)
    y = (f(x) - sign(x)*fDB)/(1.0 - fDB) if abs(x) > self.deadband_ else 0.0
    if self.tracker_ is not None:
      self.tracker_({ "caller" : self, "x" : x, "y" : y })
    return y

  def __init__(self, degree, weight, deadband, tracker):
    self.degree_, self.weight_, self.deadband_, self.tracker_ = degree, weight, deadband, tracker


class GainTracker:
  def __call__(self, values):
    x = values["x"]
    dx = values["x"] - self.x_
    self.x_ = x
    y = values["y"]
    dy = values["y"] - self.y_
    self.y_ = y
    gain = 0.0 if dx == 0.0 else dy/dx
    values["gain"] = gain
    if self.next_ is not None:
      self.next_(values)

  def set_next(self, next):
    self.next_ = next

  def __init__(self, next):
    self.next_ = next
    self.x_, self.y_ = 0.0, 0.0


#Axes
class JoystickAxis:
  def move(self, v, relative):
    assert(self.j_)
    return self.j_.move_axis(self.tcAxis_, v, relative)

  def get(self):
    assert(self.j_)
    return self.j_.get_axis_value(self.tcAxis_)

  def limits(self):
    assert(self.j_)
    return self.j_.get_limits(self.tcAxis_)

  def __init__(self, j, tcAxis):
    assert(j)
    if tcAxis not in j.get_supported_axes():
      raise RuntimeError("Axis '{}' is not supported by {}".format(tc2ns(*tcAxis)[0], j))
    self.j_, self.tcAxis_ = j, tcAxis


class JoystickButtonAxis:
  def move(self, v, relative):
    assert(self.j_)
    self.v_ = clamp(self.v_ + v if relative else v, *self.limits())
    self.j_.set_button_state(self.b_, int(self.v_))
    return self.v_

  def get(self):
    assert(self.j_)
    return self.v_

  def limits(self):
    assert(self.j_)
    return (0, 1)

  def __init__(self, j, b):
    assert(j)
    self.j_, self.b_, self.v_ = j, b, 0.0


class ReportingAxis:
  def move(self, v, relative):
    old = self.next_.get()
    r = self.next_.move(v, relative)
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
    return r

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
    #logger.debug("{} created".format(self))

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
    desired = self.v_+v if relative is True else v
    actual = clamp(desired, self.limits_[0], self.limits_[1])
    return v - (desired - actual) if relative else actual

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


#Curves
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

  def __init__(self, axis, inputOp, outputOp, deltaOp, inputValueLimits=(-1.0, 1.0), resetOpsOnAxisMove=True):
    self.axis_, self.inputOp_, self.outputOp_, self.deltaOp_, self.inputValueLimits_, self.resetOpsOnAxisMove_ = \
      axis, inputOp, outputOp, deltaOp, inputValueLimits, resetOpsOnAxisMove
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
    self.inputValue_ = self.inputOp_.calc(self.axis_.get())
    self.busy_, self.dirty_ = False, False


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
    ie = self.fill_(outputValue)
    ob, oe = self.ovs_[ie-1], self.ovs_[ie]
    if not (ob <= outputValue and outputValue <= oe):
      raise RuntimeError("Wrong interval [{}, {}] for value {} (ie: {}; ivs: {}; ovs: {})".format(ob, oe, outputValue, ie, self.ivs_, self.ovs_))
    ivLimits = (self.ivs_[ie-1], self.ivs_[ie])
    inputValue = self.inputOp_.calc(outputValue, ivLimits)
    #logger.debug("{}: found inputValue {:0.3f} for outputValue {:0.3f} (ivLimits: {}; ivs: {}; ovs: {})".format(self, inputValue, outputValue, ivLimits, self.ivs_, self.ovs_))
    return inputValue

  def reset(self):
    self.inputOp_.reset()
    self.outputOp_.reset()

  def __init__(self, inputOp, outputOp, inputStep, inputLimits, expandLimits=False):
    self.inputOp_, self.outputOp_, self.inputStep_, self.inputLimits_, self.expandLimits_ = inputOp, outputOp, inputStep, list(inputLimits), expandLimits
    if self.inputLimits_[0] > self.inputLimits_[1]:
      self.inputLimits_[0], self.inputLimits_[1] = self.inputLimits_[1], self.inputLimits_[0]
    self.ivs_, self.ovs_ = [], []
    ivp = self.inputLimits_[0]
    ovp = self.outputOp_.calc(ivp)
    s = 0
    iv = ivp
    while iv == clamp(iv, *self.inputLimits_):
      iv = ivp + self.inputStep_
      ov = self.outputOp_.calc(iv)
      ts = sign(iv-ivp)*sign(ov-ovp)
      if ts != 0:
        if s == 0:
          s = ts
        elif s != ts:
          raise RuntimeError("Function must be either increasing or decreasing")
      ivp, ovp = iv, ov
    if s == 0:
      raise RuntimeError("Cannot determine whether function is increasing or decreasing")
    self.s_ = s
    self.fill_(0.0)

  def fill_(self, outputValue):
    ie = bisect.bisect_right(self.ovs_, outputValue)
    if ie <= 0:
      iv = self.ivs_[0] if len(self.ivs_) else 0.0
      while True:
        self.check_iv_(iv)
        iv -= self.s_*self.inputStep_
        ov = self.outputOp_.calc(iv)
        if len(self.ovs_) and (ov == self.ovs_[0]):
          continue
        self.ivs_.insert(0, iv)
        self.ovs_.insert(0, ov)  
        #logger.debug("{}: outputValue {:0.3f}: inserting iv: {:0.3f}, ov: {:0.3f}".format(self, outputValue, iv, ov))
        if ov <= outputValue:
          break
      ie = 1
    elif ie >= len(self.ivs_):
      iv = self.ivs_[-1] if len(self.ivs_) else 0.0
      while True:
        self.check_iv_(iv)
        iv += self.s_*self.inputStep_
        ov = self.outputOp_.calc(iv)
        if len(self.ovs_) and (ov == self.ovs_[-1]):
          continue
        self.ivs_.append(iv)
        self.ovs_.append(ov)
        #logger.info("{}: outputValue {:0.3f}: inserting iv: {:0.3f}, ov: {:0.3f}".format(self, outputValue, iv, ov))
        if ov >= outputValue:
          break
      ie = len(self.ivs_)-1
    return ie

  def check_iv_(self, iv):
    if iv == clamp(iv, *self.inputLimits_):
      return
    if self.expandLimits_:
      if iv < self.inputLimits_[0]:
        self.inputLimits_[0] = iv
      elif iv > self.inputLimits_[-1]:
        self.inputLimits_[-1] = iv
      else:
        assert(False)
    else:
      raise RuntimeError("Requested input value {} is out of input limits {}".format(iv, self.inputLimits_))


class FuncOp:
  def calc(self, value):
    return self.func_(value)
  def reset(self):
    pass
  def __init__(self, func):
    self.func_ = func


#delta ops
class OpToDeltaOp:
  def calc(self, value, timestamp):
    return self.op_.calc(value)
  def reset(self):
    self.op_.reset()
  def __init__(self, op):
    self.op_ = op


class FuncDeltaOp:
  def calcOutput(self, value, timestamp):
    return self.func_(value)
  def reset(self):
    pass
  def __init__(self, func):
    self.func_ = func


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


class ReturnDeltaOp:
  def calc(self, delta, timestamp):
    return delta
  def reset(self):
    pass


class AccumulateDeltaOp:
  def calc(self, x, timestamp):
    for op in self.ops_:
      self.distance_ = op.calc(self.distance_, x, timestamp)
    self.distance_ += x
    return self.func_(self.distance_) if self.func_ is not None else self.distance_
  def reset(self):
    #logger.debug("{}: resetting".format(self))
    self.distance_ = 0.0
    for op in self.ops_:
      op.reset()
  def add_op(self, op):
    self.ops_.append(op)
  def __init__(self, func, ops=None):
    self.func_ = func
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
  def calc(self, distance, delta, timestamp):
    """
    Returns 0.0 if delta has changed sign and locally accumulated distance has exceeded the deadzone.
    Otherwise returns distance passed as parameter.
    distance is absolute, delta is relative.
    """
    factor = 1.0
    s = sign(delta)
    if self.s_ == 0:
      self.s_ = s
    elif self.s_ != s:
      self.localDistance_ += abs(delta)
      if self.localDistance_ > self.deadzone_:
        #logger.debug("{}: leaved deadzone, changing sign from {} to {}".format(self, self.s_, s))
        self.localDistance_, self.s_, factor = 0.0, s, 0.0
    elif self.localDistance_ != 0.0:
      self.localDistance_ = 0.0
    r = distance if self.next_ is None else self.next_.calc(distance, delta, timestamp)
    return factor * r
  def reset(self):
    #logger.debug("{}: resetting".format(self))
    self.s_, self.localDistance_ = 0, 0.0
    if self.next_:
      self.next_.reset()
  def __init__(self, deadzone=0.0, next=None):
    self.next_, self.deadzone_ = next, deadzone
    self.localDistance_, self.s_ = 0.0, 0


class TimeDistanceDeltaOp:
  def calc(self, distance, delta, timestamp):
    """
    Returns distance that is modified based on time passed since last timestamp.
    distance is absolute, delta is relative.
    """
    assert(self.resetTime_ > 0.0)
    assert(self.holdTime_ >= 0.0)
    factor = 1.0
    if self.timestamp_ is None:
      self.timestamp_ = timestamp
    dt = timestamp - self.timestamp_
    self.timestamp_ = timestamp
    if dt > self.holdTime_:
      factor = clamp(1.0 - (dt - self.holdTime_) / self.resetTime_, 0.0, 1.0)
    #logger.debug("{}.calc(): r:{:.3f}".format(self, r))
    r = distance if self.next_ is None else self.next_.calc(distance, delta, timestamp)
    return factor * r
  def reset(self):
    self.timestamp_ = None
    if self.next_:
      self.next_.reset()
  def __init__(self, resetTime, holdTime, next=None):
    if resetTime <= 0:
      raise RuntimeError("Bad reset time: {}".format(resetTime))
    if holdTime < 0:
      raise RuntimeError("Bad hold time: {}".format(holdTime))
    self.resetTime_, self.holdTime_, self.next_ = resetTime, holdTime, next
    self.timestamp_ = None


class ExtDistanceDeltaOp:
  def calc(self, distance, delta, timestamp):
    """
    Asks next for distance and then returns value 
    calculated by op based on distance, delta, timestamp and dt.
    distance is absolute, delta is relative.
    """
    if self.timestamp_ is None:
      self.timestamp_ = timestamp
    dt = timestamp - self.timestamp_
    self.timestamp_ = timestamp
    if self.next_ is not None:
      distance = self.next_.calc(distance, delta, timestamp)
    return self.op_(distance, delta, timestamp, dt)
  def reset(self):
    self.timestamp_ = None
    if self.next_:
      self.next_.reset()
  def __init__(self, next, op):
    """
    op is supposed to be stateless.
    """
    self.next_, self.op_ = next, op
    self.timestamp_ = None


class DistanceDeltaFromDeltaOp:
  def calc(self, distance, delta, timestamp):
    """distance is absolute, delta is relative."""
    return self.next_.calc(delta, timestamp)
  def reset(self):
    self.next_.reset()
  def __init__(self, next):
    self.next_ = next


#Chain curves
class AccumulateRelChainCurve:
  """
  Computes value by accumulating input deltas and passes this value to next (absolute) curve.
  """
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
    self.reset_self_()
    self.next_.reset()
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

  def __init__(self, next, valueDDOp, deltaDOp, combine, inputOp, resetOnMoveAxis):
    self.next_, self.valueDDOp_, self.deltaDOp_, self.combine_, self.inputOp_, self.resetOnMoveAxis_ = next, valueDDOp, deltaDOp, combine, inputOp, resetOnMoveAxis
    self.value_, self.dirty_ = 0.0, False

  def reset_self_(self):
    self.valueDDOp_.reset()
    self.deltaDOp_.reset()
    self.inputOp_.reset()
    self.value_ = 0.0

  def update_(self):
    if self.dirty_ == True:
      if self.resetOnMoveAxis_ == True:
        self.reset_self_()
      self.value_ = self.inputOp_.calc(self.next_.get_value())
      #logger.debug("{}.update_(): recalculated value_: {:+0.3f}".format(self, self.value_))
      self.dirty_ = False


class DeltaRelChainCurve:
  def move_by(self, x, timestamp):
    """x is relative."""
    self.update_()
    self.value_ = self.valueDDOp_.calc(self.value_, x, timestamp)
    self.value_ = self.combineValue_(self.value_, x)
    factor = self.outputOp_.calc(self.value_)
    delta = self.deltaDDOp_.calc(self.value_, x, timestamp)
    delta = self.combineDelta_(delta, factor)
    self.next_.move_by(delta, timestamp)
    return self.value_

  def reset(self):
    self.valueDDOp_.reset()
    self.deltaDDOp_.reset()
    self.outputOp_.reset()
    self.next_.reset()
    self.value_ = 0.0
    self.dirty_ = False

  def on_move_axis(self, axis, old, new):
    self.dirty_ = True
    self.next_.on_move_axis(axis, old, new)

  def get_value(self):
    self.update_()
    return self.value_

  def set_next(self, next):
    self.next_ = next

  def __init__(self, next, valueDDOp, deltaDDOp, outputOp, combineValue, combineDelta, resetOnMoveAxis):
    self.next_, self.valueDDOp_, self.deltaDDOp_, self.outputOp_, self.resetOnMoveAxis_ = next, valueDDOp, deltaDDOp, outputOp, resetOnMoveAxis
    self.combineValue_, self.combineDelta_ = combineValue, combineDelta
    self.value_, self.dirty_ = 0.0, False

  def reset_self_(self):
    self.valueDDOp_.reset()
    self.deltaDDOp_.reset()
    self.outputOp_.reset()
    self.value_ = 0.0

  def update_(self):
    if self.dirty_ == True:
      if self.resetOnMoveAxis_ == True:
        self.reset_self_()
      self.dirty_ = False


class FullDeltaRelChainCurve:
  def move_by(self, x, timestamp):
    """x is relative."""
    #adjust stored input value (i.e. set to 0.0 if delta has changed sign, or on timeout)
    #  if input value was adjusted, compute new stored output value
    #adjust input delta (for sens etc.)
    #add input delta to stored input value
    #compute new output value
    #compute new output delta by subtracting stored output value from new output value
    #set store output value to new output value
    #return output delta
    assert(self.next_ is not None)
    self.update_()
    inputValue = self.inputValueDDOp_.calc(self.inputValue_, x, timestamp)
    if inputValue != self.inputValue_:
      self.outputValue_ = self.outputValueOp_.calc(inputValue)
    self.inputValue_ = inputValue
    inputDelta = self.inputDeltaDDOp_.calc(self.inputValue_, x, timestamp)
    self.inputValue_ += inputDelta
    outputValue = self.outputValueOp_.calc(inputValue)
    outputDelta = outputValue - self.outputValue_
    self.outputValue_ = outputValue
    self.next_.move_by(outputDelta, timestamp)
    return outputDelta

  def reset(self):
    assert(self.next_ is not None)
    self.next_.reset()
    self.reset_self_()

  def on_move_axis(self, axis, old, new):
    self.dirty_ = True
    self.next_.on_move_axis(axis, old, new)

  def get_value(self):
    self.update_()
    return self.inputValue_

  def set_next(self, next):
    self.next_ = next

  def __init__(self, next, inputValueDDOp, inputDeltaDDOp, outputValueOp, resetOnMoveAxis):
    """
    next: Next curve (relative).
    inputValueDDOp: Adjusts input value based on current input value, input delta and timestamp. Is reset on call to reset(), so can have state.
    inputDeltaDDOp: Adjusts input delta based on current input value, input delta and timestamp. Is reset on call to reset(), so can have state.
    outputValueOp: Computes output value from input value. Is not reset on call to reset(), so supposed to be stateless.
    resetOnMoveAxis: If True, curve will be reset after call to on_move_axis().
    """
    self.next_, self.inputValueDDOp_, self.outputValueOp_, self.inputDeltaDDOp_ = next, inputValueDDOp, outputValueOp, inputDeltaDDOp
    self.resetOnMoveAxis_ = resetOnMoveAxis
    self.inputValue_ = 0.0
    self.outputValue_ = self.outputValueOp_.calc(self.inputValue_)
    self.dirty_ = False

  def reset_self_(self):
    self.inputValue_ = 0.0
    self.outputValue_ = self.outputValueOp_.calc(self.inputValue_)
    self.inputValueDDOp_.reset()
    self.inputDeltaDDOp_.reset()
    self.dirty_ = False

  def update_(self):
    if self.dirty_ == True:
      if self.resetOnMoveAxis_ == True:
        self.reset_self_()
      self.dirty = False


class RelToAbsChainCurve:
  """
  Gets value from next (absolute) curve, adds delta and passes new value to next curve.
  Is stateless.
  """
  def move_by(self, x, timestamp):
    """x is relative."""
    nextValue = self.next_.get_value()
    nextValue += x
    self.next_.move(nextValue, timestamp)
    return self.next_.get_value()

  def reset(self):
    self.next_.reset()

  def on_move_axis(self, axis, old, new):
    self.next_.on_move_axis(axis, old, new)

  def get_value(self):
    return self.next_.get_value()

  def set_next(self, next):
    self.next_ = next

  def __init__(self, next):
    self.next_ = next


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


class AxisChainCurve:
  """Moves axis. Is meant to be at the bottom of chain."""
  def move_by(self, x, timestamp):
    self.axis_.move(x, relative=True)
    #logger.debug("{}: x:{:+.3f}, v:{:+.3f}".format(self, x, self.axis_.get()))
    return self.axis_.get()

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

  def __init__(self, axis):
    self.axis_ = axis


class AxisTrackerChainCurve:
  """Prevents endless recursion on moving axis.
     Is meant to be at the top of chain.
     Subscribe as axis listener."""
  def move_by(self, x, timestamp):
    """x is relative."""
    self.busy_ = True
    v = None
    try:
      v = self.next_.move_by(x, timestamp)
    finally:
      self.busy_ = False
    return v

  def move(self, x, timestamp):
    """x is absolute."""
    self.busy_ = True
    v = None
    try:
      v = self.next_.move(x, timestamp)
    finally:
      self.busy_ = False
    return v

  def reset(self):
    self.busy_ = False
    self.next_.reset()

  def on_move_axis(self, axis, old, new):
    if self.busy_ == True:
      return
    self.next_.on_move_axis(axis, old, new)

  def get_value(self):
    return self.next_.get_value()

  def set_next(self, next):
    self.next_ = next

  def __init__(self, next):
    self.next_ = next
    self.busy_ = False


class OffsetAbsChainCurve:
  def move(self, x, timestamp):
    """x is absolute."""
    #logger.debug("{}: x:{:+.3f}".format(self, x))
    if self.value_ is not None:
      self.offset_ += (self.next_.get_value() - self.value_)
      self.value_ = None
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
    self.next_.reset()
    self.s_, self.sx_, self.state_, self.x_, self.offset_ = 0, 0, 0, 0.0, self.next_.get_value()
    self.value_ = None

  def on_move_axis(self, axis, old, new):
    if self.value_ is None:
      self.value_ = self.next_.get_value()
    self.next_.on_move_axis(axis, old, new)
    #logger.debug("{}.on_move_axis(): offset_:{:+.3f}, x_:{:+.3f}".format(self, self.offset_, self.x_))

  def get_value(self):
    return self.x_

  def set_next(self, next):
    self.next_ = next

  def __init__(self, next):
    self.s_, self.sx_, self.state_, self.x_, self.offset_ = 0, 0, 0, 0.0, 0.0
    self.value_ = None
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
class AxisLinker:
  """Directly links positions of 2 axes using func and offset.
     If controlled axis is moved externally by delta, adds this delta to offset.
     When resetting axes, reset controlling axis first, then controlled.
  """
  def reset(self):
    self.offset_ = self.controlledAxis_.get() - self.func_(self.controllingAxis_.get())

  def set_state(self, state):
    if state == True:
      self.reset()
    self.state_ = state

  def set_func(self, func):
    self.func_ = func
    self.reset()

  def get_func(self):
    return self.func_

  def set_offset(self, offset):
    self.offset_ = offset

  def get_offset(self):
    return self.offset_

  def on_move_axis(self, axis, old, new):
    if self.state_ == False:
      return
    if not self.busy_ and axis == self.controlledAxis_:
      #logger.debug("{} : Controlled axis has moved to {}".format(self, new))
      if self.old_ is None:
        self.old_ = old
    elif axis == self.controllingAxis_:
      if self.old_ is not None:
        self.offset_ += self.controlledAxis_.get() - self.old_
        self.old_ = None
      cv = self.func_(new)
      try:
        self.busy_= True
        #logger.debug("{} : Moving controlled axis to {}".format(self, cv+self.offset_))
        desired = cv + self.offset_
        actual = self.controlledAxis_.move(desired, relative=False)
        if actual != desired:
          self.offset_ -= (desired - actual)
      finally:
        self.busy_= False

  def __init__(self, controllingAxis, controlledAxis, func):
    self.controllingAxis_, self.controlledAxis_, self.func_ = controllingAxis, controlledAxis, func
    self.old_, self.offset_, self.busy_, self.state_  = None, 0.0, False, False
    #logger.debug("{} created".format(self))

  def __del__(self):
    #logger.debug("{} destroyed".format(self))
    pass


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
    #logger.debug("{} created".format(self))

  def __del__(self):
    #logger.debug("{} destroyed".format(self))
    pass

  def set_mode_(self, mode):
    for d in self.devices_:
      try:
        #logger.debug("{}: setting swallow state {} to {}".format(self, self.mode_, d))
        d.swallow(mode)
      except IOError as e:
        #logger.debug("{}: got IOError ({}), but that was expected".format(self, e))
        continue


class SwallowSource:
  def __call__(self, event):
    for name,mode in self.deviceNamesAndModes_:
      try:
        #logger.debug("{}: setting swallow state {} to {}".format(self, self.mode_, d))
        self.source_.swallow(name, mode)
      except IOError as e:
        #logger.debug("{}: got IOError ({}), but that was expected".format(self, e))
        continue
    return True

  def __init__(self, source, deviceNamesAndModes):
    self.source_, self.deviceNamesAndModes_ = source, deviceNamesAndModes
    #logger.debug("{} created".format(self))

  def __del__(self):
    #logger.debug("{} destroyed".format(self))
    pass


class Opentrack:
  """Opentrack head movement emulator. Don't forget to call send()!"""

  def move_axis(self, tcAxis, v, relative = True):
    if tcAxis not in self.axes_:
      return 0.0
    desired = self.v_.get(tcAxis, 0.0)+v if relative else v
    actual = clamp(desired, *self.get_limits(tcAxis))
    self.v_[axis] = actual
    self.dirty_ = True
    return v - (desired - actual) if relative else actual

  def get_axis_value(self, tcAxis):
    return self.v_.get(tcAxis, 0.0)

  def get_limits(self, tcAxis):
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

  axes_ = tuple(TypeCode(codes.EV_ABS, c) for c in (codes.ABS_X, codes.ABS_Y, codes.ABS_Z, codes.ABS_RX, codes.ABS_RY, codes.ABS_RZ))


class UdpJoystick:
  """Generic joystick that sends axes positions over UDP. Don't forget to call send()!"""

  def move_axis(self, tcAxis, v, relative = True):
    if tcAxis not in self.tcAxes_:
      return 0.0 if relative else v
    desired = self.v_.get(tcAxis, 0.0)+v if relative else v
    actual = clamp(v, *self.get_limits(tcAxis))
    self.v_[tcAxis] = actual
    self.dirty_ = True
    return v - (desired - actual) if relative else actual

  def get_axis_value(self, tcAxis):
    return self.v_.get(tcAxis, 0.0)

  def get_limits(self, tcAxis):
    return self.limits_.get(tcAxis, (0.0, 0.0))

  def set_limits(self, tcAxis, limits):
    self.limits_[tcAxis] = limits
    self.v_[tcAxis] = clamp(self.v_.get(tcAxis, 0.0), *limits)
    self.dirty_ = True

  def get_supported_axes(self):
    return self.tcAxes_

  def set_button_state(self, button, state):
    if button not in self.buttons_:
      return
    self.b_[button] = state
    self.dirty_ = True

  def get_button_state(self, button):
    return self.b_.get(button, False)

  def get_supported_buttons(self):
    return self.buttons_

  def send(self):
    if self.dirty_ == True:
      self.dirty_ = False
      packet = self.make_packet_(axes=self.v_, buttons=self.b_)
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
    for tcAxis in self.tcAxes_:
      v = 0.0
      self.move_axis(tcAxis, v, False)
    self.b_ = {}
    for b in self.buttons_:
      self.set_button_state(b, False)

  tcAxes_ = tuple(TypeCode(codes.EV_ABS, c) for c in (codes.ABS_X, codes.ABS_Y, codes.ABS_Z, codes.ABS_RY, codes.ABS_RX, codes.ABS_RZ))
  buttons_ = tuple(b for b in range (codes.BTN_0, codes.BTN_15+1))


#TODO Needs verifying
def make_opentrack_packet(**kwargs):
  d = (
    (codes.ABS_X, -100.0),
    (codes.ABS_Y, -100.0),
    (codes.ABS_Z, 100.0),
    (codes.ABS_RX, 1.0),
    (codes.ABS_RY, -1.0),
    (codes.ABS_RZ, 1.0)
  )
  v = kwargs["axes"]
  values = (dd[1]*v.get(TypeCode(codes.EV_ABS, dd[0]), 0.0) for dd in d)
  packet = struct.pack("<dddddd", *values)
  return packet


def make_il2_packet(**kwargs):
  #https://github.com/uglyDwarf/linuxtrack/blob/1f405ea1a3a478163afb1704072480cf7a2955c2/src/ltr_pipe.c#L919
  #r = snprintf(buf, sizeof(buf), "R/11\\%f\\%f\\%f", d->h, -d->p, d->r);
  d = (
    (codes.ABS_RX, -1.0),
    (codes.ABS_RY, 1.0),
    (codes.ABS_RZ, 1.0)
  )
  v = kwargs["axes"]
  values = [dd[1]*v.get(TypeCode(codes.EV_ABS, dd[0]), 0.0) for dd in d]
  result = "R/11\\{:f}\\{:f}\\{:f}".format(*values)
  return result


def make_il2_6dof_packet(**kwargs):
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
  v = kwargs["axes"]
  values = (dd[1]*v.get(TypeCode(codes.EV_ABS, dd[0]), 0.0) for dd in d)
  result = "R/11\\{:f}\\{:f}\\{:f}\\{:f}\\{:f}\\{:f}".format(*values)
  return result


class JoystickPoseManager:
  """Sets joystick axes to preset values and also can update preset values from joystick"""

  def set_pose(self, i, l):
    self.poses_[i] = [[p[0], p[1]] for p in l]

  def update_pose(self, i):
    #logger.debug("update_pose({})".format(i))
    pose = self.poses_.get(i, None)
    if pose is None:
      #logger.debug("{}: no pose {}".format(self, i))
      return False
    else:
      for j in xrange(len(pose)):
        pose[j][1] = self.joystick_.get_axis_value(pose[j][0])
      return True

  def pose_to(self, i):
    #logger.debug("pose_to({})".format(i))
    pose = self.poses_.get(i, None)
    if pose is None:
      #logger.debug("{}: no pose {}".format(self, i))
      return False
    else:
      for p in pose:
        self.joystick_.move_axis(p[0], p[1], self.relative_)
      return True

  def __init__(self, joystick, relative):
    self.poses_, self.joystick_, self.relative_ = dict(), joystick, relative


class AxisPoseManager:
  """Axis-based pose manager"""
  def set_pose(self, i, l):
    self.poses_[i] = [[p[0], p[1]] for p in l]

  def get_pose(self, i):
    return self.poses_.get(i, None)

  def has_pose(self, i):
    return i in self.poses_

  def get_poses(self):
    return self.poses_

  def update_pose(self, i):
    #logger.debug("{}: updating pose {}".format(self, i))
    pose = self.poses_.get(i, None)
    if pose is None:
      #logger.debug("{}: no pose {}".format(self, i))
      return False
    else:
      for p in pose:
        p[1] = p[0].get()
      return True

  def update_poses(self, poses):
    r = False
    for p in poses:
      r = self.update_pose(p) or r
    return r

  #TODO Remove
  def pose_to(self, i):
    return self.apply_pose(i)

  def apply_pose(self, i):
    #logger.debug("{}: poseping to {}".format(self, i))
    pose = self.poses_.get(i, None)
    if pose is None:
      #logger.debug("{}: no pose {}".format(self, i))
      return False
    else:
      for p in pose:
        p[0].move(p[1], False)
      return True

  def apply_poses(self, poses):
    r = False
    for p in poses:
      r = self.apply_pose(p) or r
    return r

  def merge_pose(self, frm, to):
    f = self.poses_.get(frm)
    if f is None:
      return False
    t = self.poses_.get(to, [])
    r = []
    for i in range(len(f)):
      for j in range(len(t)):
        if f[i][0] == t[j][0]:
          t[j][1] = f[i][1]
          break
      else:
       r.append([f[i][0], f[i][1]])
    t.extend(r)
    return True

  def __init__(self):
    self.poses_ = dict()


#TODO Remove
def PoseTo(poseManager, pose):
  def op(event):
    return poseManager.pose_to(pose)
  return op


def UpdatePose(poseManager, pose):
  def op(event):
    return poseManager.update_pose(pose)
  return op


def MergePose(poseManager, frm, to):
  def op(event):
    return poseManager.merge_pose(frm, to)
  return op


class PoseTracker:
  def inc(self, pose):
    if pose not in self.poses_:
      self.poses_[pose] = 0
    if self.poses_[pose] == 0:
      self.sm_.update_pose(pose)
    self.poses_[pose] += 1

  def dec(self, pose):
    if pose not in self.poses_:
      self.poses_[pose] = 0
    if self.poses_[pose] == 1:
      self.sm_.pose_to(pose)
    if self.poses_[pose] >= 1:
      self.poses_[pose] -= 1

  def reset(self, pose):
    self.poses_[pose] = 0

  def __init__(self, sm):
    self.poses_, self.sm_ = dict(), sm


class MappingJoystick:
  """Forwards calls to contained joysticks with axis mapping"""
  def move_axis(self, tcAxis, value, relative):
    if tcAxis not in self.adata_:
      return 0.0 if relative else value
    d = self.adata_[tcAxis]
    return d.toJoystick.move_axis(d.tcToAxis, d.factor*value, relative)

  def get_axis_value(self, tcAxis):
    if tcAxis not in self.adata_:
      return 0.0
    d = self.adata_[tcAxis]
    value = d.toJoystick.get_axis_value(d.tcToAxis)
    return d.factor*value

  def get_limits(self, tcAxis):
    d = self.adata_[tcAxis]
    return (d.factor*l for l in d.toJoystick.get_limits(d.tcToAxis))

  def get_supported_axes(self):
    return self.adata_.keys()

  def set_button_state(self, button, state):
    if button not in self.bdata_:
      return
    d = self.bdata_[button]
    d.toJoystick.set_button_state(d.toButton, state if d.negate == False else not state)

  def get_button_state(self, button):
    d = self.bdata_.get(button, None)
    if d is None:
      return None
    state = d.toJoystick.set_button_state(t.toButton)
    return state if d.negate == False else not state

  def get_supported_buttons(self):
    return self.bdata_.keys()

  def add_axis(self, tcFromAxis, tcToJoystick, toAxis, factor=1.0):
    class D:
      pass
    d = D()
    d.toJoystick, d.tcToAxis, d.factor = toJoystick, tcToAxis, factor
    self.adata_[tcFromAxis] = d

  def add_button(self, fromButton, toJoystick, toButton, negate=False):
    class D:
      pass
    d = D()
    d.toJoystick, d.toButton, d.negate = toJoysitick, toAxis, negate
    self.bdata_[fromButton] = d

  def __init__(self):
    self.adata_, self.bdata_ = {}, {}


class NodeJoystick(object):
  def move_axis(self, tcAxis, value, relative):
    if self.next_ is not None:
      return self.next_.move_axis(tcAxis, value, relative)

  def get_axis_value(self, tcAxis):
    return self.next_.get_axis_value(tcAxis) if self.next_ else 0

  def get_limits(self, tcAxis):
    return self.next_.get_limits(tcAxis) if self.next_ else (0.0, 0.0)

  def get_supported_axes(self):
    return self.next_.get_supported_axes() if self.next_ is not None else ()

  def set_button_state(self, button, state):
    self.next_.set_button_state(button, state)

  def get_button_state(self, button):
    return self.next_.get_button_state(button)

  def get_supported_buttons(self):
    return self.next_.get_supported_buttons()

  def set_next(self, next):
    self.next_ = next
    return next

  def __init__(self, next=None):
    self.next_ = next


class RateLimititngJoystick:
  def move_axis(self, tcAxis, value, relative):
    if self.next_ is None or tcAxis not in self.v_:
      return 0.0 if relative else value
    else:
      desired = self.v_[tcAxis]+value if relative else value
      actual = clamp(desired, *self.get_limits(tcAxis))
      self.v_[tcAxis] = actual
      return value - (desired - actual) if relative else actual

  def get_axis_value(self, tcAxis):
    return self.v_.get(tcAxis, 0.0)

  def get_limits(self, tcAxis):
    return self.next_.get_limits(tcAxis) if self.next_ is not None else (0.0, 0.0)

  def get_supported_axes(self):
    return self.next_.get_supported_axes() if self.next_ is not None else ()

  def set_button_state(self, button, state):
    if self.next_ is not None:
      self.next_.set_button_state(button, state)

  def get_button_state(self, button):
    return self.next_.get_button_state(button) if self.next_ is not None else False

  def get_supported_buttons(self):
    return self.next_.get_supported_buttons() if self.next_ is not None else ()

  def set_next(self, next):
    self.next_ = next
    if self.next_ is not None:
      self.v_ = {tcAxis:self.next_.get_axis_value(tcAxis) for tcAxis in self.next_.get_supported_axes()}
    return next

  def update(self, tick):
    if self.next_ is not None:
      for tcAxis,value in self.v_.items():
        current = self.next_.get_axis_value(tcAxis)
        delta = value - current
        if delta != 0.0:
          if tcAxis in self.rates_:
            value = current + sign(delta)*min(abs(delta), self.rates_[tcAxis]*tick)
            delta = value - current
          self.next_.move_axis(tcAxis, delta, True)

  def __init__(self, next, rates):
    self.next_, self.rates_ = next, rates
    self.v_ = {}
    self.set_next(next)


class RateSettingJoystick:
  def move_axis(self, tcAxis, value, relative):
    if self.next_ is None or tcAxis not in self.v_:
      return 0.0 if relative else value
    else:
      desired = self.v_[tcAxis]+value if relative else value
      actual = clamp(desired, *self.get_limits(tcAxis))
      self.v_[tcAxis] = actual
      return value - (desired - actual) if relative else actual

  def get_axis_value(self, tcAxis):
    return self.v_.get(tcAxis, 0.0)

  def get_limits(self, tcAxis):
    return self.limits_.get(tcAxis, (0.0, 0.0))

  def set_limits(self, tcAxis, limits):
    self.limits_[tcAxis] = limits

  def get_supported_axes(self):
    return self.next_.get_supported_axes() if self.next_ else ()

  def set_button_state(self, button, state):
    if self.next_ is not None:
      self.next_.set_button_state(button, state)

  def get_button_state(self, button):
    return self.next_.get_button_state(button) if self.next_ is not None else False

  def get_supported_buttons(self):
    return self.next_.get_supported_buttons() if self.next_ is not None else ()

  def set_next(self, next):
    self.next_ = next
    if self.next_ is not None:
      self.v_ = {tcAxis : clamp(0.0, *self.get_limits(tcAxis)) for tcAxis in self.next_.get_supported_axes()}
    return next

  def update(self, tick, timestamp):
    if self.next_ is None:
      return
    for tcAxis,value in self.v_.items():
      rateOp = self.rateOps_.get(tcAxis, None)
      if rateOp is None:
        continue
      rate = rateOp.calc(value, timestamp)
      delta = rate*tick
      self.next_.move_axis(tcAxis, delta, relative=True)

  def __init__(self, next, rateOps, limits=None):
    assert(next is not None)
    self.next_, self.rateOps_, self.limits_ = next, rateOps, {} if limits is None else limits
    self.v_ = {}
    self.set_next(next)


class NotifyingJoystick(NodeJoystick):
  def move_axis(self, tcAxis, value, relative):
    r = super(NotifyingJoystick, self).move_axis(tcAxis, value, relative)
    if not relative and self.sink_() is not None:
      self.sink_()(Event(tcAxis.type, tcAxis.code, value, time.time()))
    return r

  def set_sink(self, sink):
    self.sink_ = weakref.ref(sink)
    return sink

  def __init__(self, sink=None, next=None):
    super(NotifyingJoystick, self).__init__(next)
    if sink is not None: self.sink_ = weakref.ref(sink)


class MetricsJoystick:
  def move_axis(self, tcAxis, value, relative):
    if tcAxis not in self.data_:
      self.data_[tcAxis] = [0.0, None, 0.0]
    if relative:
      self.data_[tcAxis][0] += value
    else:
      self.data_[tcAxis][0] = value
    return value

  def get_axis_value(self, tcAxis):
    return self.data_.get(tcAxis, 0.0)[0]

  def get_limits(self, tcAxis):
    return (-1.0, 1.0)

  def set_button_state(self, button, state):
    pass

  def get_button_state(self, button):
    return False

  def get_supported_buttons(self):
    return ()

  def check(self):
    for tcAxis,d in self.data_.items():
      if d[1] is None:
        continue
      error = abs(d[0] - d[1])
      d[2] = 0.5*error + 0.5*d[2]
      print("{}: {: .3f} {: .3f}".format(stc2fn(None, tcAxis.type, tcAxis.code), error, d[2]))

  def reset(self):
    for a in self.data_:
      d = self.data_[a]
      if d[1] is None:
        continue
      d[0],d[2] = d[1],0.0

  def set_target(self, tcAxis, target):
    if tcAxis not in self.data_:
      self.data_[tcAxis] = [0.0, None, 0.0]
    self.data_[tcAxis][1] = target

  def __init__(self):
    self.data_ = dict()


class ReportingJoystickAxis:
  def move(self, v, relative):
    return self.joystick_.move_axis(self.tcAxis_, v, relative)

  def get(self):
    return self.joystick_.get_axis_value(self.tcAxis_)

  def limits(self):
    return self.joystick_.get_limits(self.tcAxis_)

  def add_listener(self, listener):
    self.listeners_.append(weakref.ref(listener))
    #logger.debug("{}: Adding listener: {}, number of listeners: {}".format(self, listener, len(self.listeners_)))

  def remove_listener(self, listener):
    try:
      self.listeners_.remove(listener)
      #logger.debug("{}: Removing listener: {}, number of listeners: {}".format(self, listener, len(self.listeners_)))
    except ValueError:
      raise RuntimeError("Listener {} not registered".format(listener))

  def remove_all_listeners(self):
    self.listeners_ = []
    #logger.debug("{}: Removing all listeners, number of listeners: {}".format(self, len(self.listeners_)))

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

  def __init__(self, joystick, tcAxis):
    if tcAxis not in joystick.get_supported_axes():
      raise RuntimeError("Axis '{}' is not supported by {}".format(tc2ns(*tcAxis)[0], joystick))
    self.joystick_, self.tcAxis_, self.listeners_ = joystick, tcAxis, []
    #logger.debug("{} created".format(self))

  def __del__(self):
    #logger.debug("{} destroyed".format(self))
    pass

  def cleanup_(self):
    i = 0
    while i < len(self.listeners_):
      if self.listeners_[i]() is None:
        self.listeners_.pop(i)
      else:
        i += 1
    #logger.debug("{}: listeners after cleanup {}".format(self, self.listeners_))


class ReportingJoystick(NodeJoystick):
  def move_axis(self, tcAxis, value, relative):
    old = self.get_axis_value(tcAxis)
    r = NodeJoystick.move_axis(self, tcAxis, value, relative)
    new = self.get_axis_value(tcAxis)
    dirty = False
    for a in self.axes_.get(tcAxis, ()):
      aa = a()
      if aa is not None:
        aa.on_move(old, new)
      else:
        dirty = True
    if dirty:
      self.cleanup_()
    return r

  def make_axis(self, tcAxis):
    a = ReportingJoystickAxis(self, tcAxis)
    self.axes_.setdefault(tcAxis, [])
    self.axes_[tcAxis].append(weakref.ref(a))
    return a

  def __init__(self, next):
    super(ReportingJoystick, self).__init__(next)
    self.axes_ = {}

  def cleanup_(self):
    for tcAxis, axes in self.axes_.items():
      i = 0
      while i < len(axes):
        if axes[i]() is None:
          axes.pop(i)
        else:
          i += 1
    #logger.debug("{}: axes after cleanup {}".format(self, self.axes_))


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
  tcPosAxes_ = tuple(TypeCode(codes.EV_ABS, c) for c in (codes.ABS_X, codes.ABS_Y, codes.ABS_Z))
  tcAngleAxes_ = tuple(TypeCode(codes.EV_ABS, c) for c in (codes.ABS_RX, codes.ABS_RY, codes.ABS_RZ))

  def move_axis(self, tcAxis, value, relative):
    """Sets view angles and position.
       ABS_RX, ABS_RY and ABS_RZ are angles that represent yaw, pitch and roll angles of view ((0,0,0) is forward).
       ABS_X, ABS_Y and ABS_Z are position axes that repersent x, y and z positions of view ((0,0,0) is center).
         If relative is True, value is treated as relative amount of movement along a local axis, rotated by view angles.
         If relative is False, value is treated as absolute position along a local axis.
       This class needs to know about angles, so set them via object of this class.
       Using with curves that set absolute positions may produce unexpected and undesired results.
    """
    if self.next_ is None:
      return 0.0 if relative else value

    if tcAxis in self.tcPosAxes_:
      self.update_dirs_()

      point = None

      #Get offset in global cs
      offset = [self.next_.get_axis_value(tca) for tca in self.tcPosAxes_]

      #If relative - add to current pos in global cs
      iAxis = self.tcPosAxes_.index(tcAxis)
      if relative:
        #Convert to global cs
        point = vec_mul(self.dirs_[iAxis], value)
        point = vec_add(point, offset)
      else:
        #Convert offset to local cs, replace the value for given axis, and convert back to global cs
        t = self.global_to_local_(offset)
        t[iAxis] = value
        point = self.local_to_global_(t)

      #Clamp to sphere in global cs
      clamped = clamp_to_sphere(point, self.r_)
      if self.stick_ and point != clamped:
        return 0.0 if relative else value

      #Clamp to limits of next sink and move, both in global cs
      for ia in range(len(self.tcPosAxes_)):
        tca = self.tcPosAxes_[ia]
        limits = self.next_.get_limits(tca)
        c, o = clamped[ia], offset[ia]
        c = clamp(c, *limits)
        if relative:
          self.next_.move_axis(tca, c-o, relative=True)
        else:
          self.next_.move_axis(tca, c, relative=False)

      self.limitsDirty_ = True
      return value
    elif tcAxis in self.tcAngleAxes_:
      self.dirsDirty_ = True
    return self.next_.move_axis(tcAxis, value, relative)


  def get_axis_value(self, tcAxis):
    """Returns local axis value."""
    if self.next_ is None:
      return 0.0
    elif tcAxis in self.tcPosAxes_:
      self.update_dirs_()
      gp = [self.next_.get_axis_value(tca) for tca in self.tcPosAxes_]
      l = 0.0
      d = self.dirs_[self.tcPosAxes_.index(tcAxis)]
      for i in range(len(gp)):
        l += gp[i]*d[i]
      return l
    else:
      return self.next_.get_axis_value(tcAxis)


  def get_limits(self, tcAxis):
    """Returns relative, local limits for position axes, calls next sink for other."""
    self.update_limits_()
    if self.next_ is None:
      return (0.0, 0.0)
    elif tcAxis in self.tcPosAxes_:
      ia = self.tcPosAxes_.index(tcAxis)
      return self.limits_[ia]
    else:
      return self.next_.get_limits(tcAxis)

  def get_supported_axes(self):
    return self.next_.get_supported_axes() if self.next_ is not None else ()

  def set_button_state(self, button, state):
    if self.next_ is not None:
      self.next_.set_button_state(button, state)

  def get_button_state(self, button):
    return self.next_.get_button_state(button) if self.next_ is not None else False

  def get_supported_buttons(self):
    return self.next_.get_supported_buttons() if self.next_ is not None else ()

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
      dYaw, dPitch, dRoll = (tca for tca in (self.next_.get_axis_value(tcAxis) for tcAxis in self.tcAngleAxes_))
      #Angles should be negated for correct calculation
      #Can instead negate sines or adjust signs in dirs_ calculation
      rYaw, rPitch, rRoll = (-math.radians(a) for a in (dYaw, dPitch, dRoll))
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
      gp = [self.next_.get_axis_value(tca) for tca in self.tcPosAxes_]
      intersections = [None for i in range(len(self.tcPosAxes_))]
      for ort in self.tcPosAxes_:
        iort = self.tcPosAxes_.index(ort)
        intersections[iort] = calc_sphere_intersection_points(gp, self.dirs_[iort], self.r_)

      #Finding limits in global cs
      limits = []
      #TODO for icoord in len(self.tcPosAxes_) ?
      for coord in self.tcPosAxes_:
        icoord = self.tcPosAxes_.index(coord)
        mn, mx = 0.0, 0.0
        for ip in intersections:
          if ip is None:
            continue
          assert(len(ip) == 2)
          for i in ip:
            assert(len(i) == len(self.tcPosAxes_))
            v = i[icoord]
            mn, mx = min(mn, v), max(mx, v)
        limits.append((mn, mx))

      #Clamping to limits of next in global cs
      #TODO for ia in len(self.tcPosAxes_) ?
      if self.next_ is not None:
        for tca in self.tcPosAxes_:
          ia = self.tcPosAxes_.index(tca)
          nextLimits = self.next_.get_limits(tca)
          assert(len(nextLimits) == 2)
          assert(nextLimits[0] <= nextLimits[1])
          limits[ia] = [clamp(l, *nextLimits) for l in limits[ia]]

      #Converting limits to local cs
      gpmin, gpmax = [l[0] for l in limits], [l[1] for l in limits]
      assert(len(gpmin) == len(self.tcPosAxes_))
      assert(len(gpmax) == len(self.tcPosAxes_))
      lpmin, lpmax = self.global_to_local_(gpmin), self.global_to_local_(gpmax)
      #TODO for icoord in len(self.tcPosAxes_) ?
      for coord in self.tcPosAxes_:
        icoord = self.tcPosAxes_.index(coord)
        n, x = lpmin[icoord], lpmax[icoord]
        n, x = min(n, x), max(n, x)
        self.limits_[icoord] = (n, x)

      self.limitsDirty_ = False


  def global_to_local_(self, gp):
    lp = [0.0 for i in range(len(gp))]
    #TODO for ia in len(self.tcPosAxes_) ?
    for tca in self.tcPosAxes_:
      ia = self.tcPosAxes_.index(tca)
      for j in range(len(self.dirs_)):
        lp[j] += gp[ia]*self.dirs_[j][ia]
    #logger.debug("global_to_local(): dirs{}; gp:{}; lp:{}".format(self.dirs_, gp, lp))
    return lp


  def local_to_global_(self, lp):
    gp = [0.0 for i in range(len(lp))]
    #TODO for ia in len(self.tcPosAxes_) ?
    for tca in self.tcPosAxes_:
      ia = self.tcPosAxes_.index(a)
      for j in range(len(self.dirs_)):
        gp[ia] += lp[ia]*self.dirs_[j][ia]
    #logger.debug("local_to_global(): dirs{}; lp:{}; gp:{}".format(self.dirs_, lp, gp))
    return gp


class AxisAccumulator:
  def __call__(self, e):
    if self.state_ and e.type == codes.EV_REL:
      tcAxis = TypeCode(e.type, e.code)
      v = self.values_.get(tcAxis, 0.0)
      v += e.value * self.scales_.get(tcAxis, 1.0)
      v = clamp(v, *self.get_limits(tcAxis))
      self.values_[tcAxis] = v
    return False

  def get_axis_value(self, tcAxis):
    return self.values_.get(tcAxis, 0.0)

  def get_limits(self, tcAxis):
    return (-1.0, 1.0)

  def get_supported_axes(self):
    return self.values_.keys()

  def reset(self):
    for k in self.values_.keys():
      self.values_[k] = 0.0

  def set_state(self, s):
    self.state_ = s

  def get_state(self):
    return self.state_

  def __init__(self, scales=None, state=False):
    self.scales_ = {}
    self.values_ = {}
    if scales is not None:
      for i,v in scales.items():
        self.scales_[i] = v
        self.values_[i] = 0.0
    self.state_ = state


class Info:
  class Marker:
    def update(self):
      canvas = self.a_.canvas_
      cw, ch = canvas.winfo_width(), canvas.winfo_height()
      for shape in self.shapes_:
        sc = canvas.coords(shape)
        sw, sh = sc[2] - sc[0], sc[3] - sc[1]
        sx = 0.5*(self.vpx_() + 1)
        sx = sx*cw + (0.5 - sx)*self.size_[0] - 0.5*sw
        sy = 0.5*(self.vpy_() + 1)
        sy = sy*ch + (0.5 - sy)*self.size_[1] - 0.5*sh
        dx, dy = sx - sc[0], sy - sc[1]
        x0, y0, x1, y1 = sx, sy, sc[2] + dx, sc[3] + dy
        canvas.coords(shape, x0, y0, x1, y1)
    def __init__(self, area, vpx, vpy, shapes, size):
      self.a_, self.vpx_, self.vpy_, self.shapes_, self.size_ = area, vpx, vpy, shapes, size
  class AxesArea:
    def add_marker(self, vpx, vpy, shapeType, **kwargs):
      def make_vp(vp, scale=None):
        if type(vp) in (str, unicode):
          s = vp[0]
          sm = 1.0
          if s in ("+", "-"):
            vp = vp[1:]
            sm = 1.0 if s == "+" else -1.0
          outputName, tAxis, cAxis = fn2stc(vp)
          tcAxis = TypeCode(tAxis, cAxis)
          if self.get_output_ is None:
            raise RuntimeError("Outputs locator is not set")
          output = self.get_output_(outputName)
          if output is None:
            raise RuntimeError("Cannot get output '{}'".format(outputName))
          if scale is None:
            limits = output.get_limits(tcAxis)
            scale = 0.0 if limits[0] == limits[1] else 2.0 / abs(limits[1] - limits[0])
          scale *= sm
          return lambda : scale*output.get_axis_value(tcAxis)
        elif type(vp) in (int, float):
          return lambda : vp
        else:
          return vp
      sx, sy = kwargs.get("sx", None), kwargs.get("sy", None)
      vpx, vpy = make_vp(vpx, sx), make_vp(vpy, sy)
      size = kwargs.get("size", (11, 11))
      shapes = self.create_shapes_(shapeType, **kwargs)
      marker = Info.Marker(self, vpx, vpy, shapes, size)
      marker.update()
      self.markers_.append(marker)
      return marker
    def update(self):
      for marker in self.markers_:
        marker.update()
    def __init__(self, window, layout, r, c, **kwargs):
      frame = tk.Frame(window)
      frame.pack_propagate(True)
      frame.grid(row=r, column=c, rowspan=kwargs.get("rs", 1), columnspan=kwargs.get("cs", 1))
      frame.grid_configure(sticky=kwargs.get("sticky", "nsew"))
      window.grid_rowconfigure(r, weight=kwargs.get("rw", 1))
      window.grid_columnconfigure(c, weight=kwargs.get("cw", 1))
      name = kwargs.get("name", None)
      if name is not None:
        nameLabel = tk.Label(frame, text=name)
        nameLabel.pack()
      canvas = tk.Canvas(frame, bg=kwargs.get("canvasBg", "black"))
      self.canvas_ = canvas
      canvasSize = kwargs.get("canvasSize", (200, 20))
      fill = "both"
      if layout == "box":
        canvas["width"], canvas["height"] = canvasSize[0], canvasSize[0]
        fill = "both"
      elif layout == "h":
        canvas["width"], canvas["height"] = canvasSize[0], canvasSize[1]
        fill = "x"
      elif layout == "v":
        canvas["width"], canvas["height"] = canvasSize[1], canvasSize[0]
        fill = "y"
      self.add_grid_(layout, color=kwargs.get("gridColor", "white"), width=kwargs.get("gridWidth", 1))
      canvas.pack()
      canvas.pack_configure(expand=True, fill=fill)
      self.markers_ = []
      self.get_output_ = kwargs.get("getOutput", None)
    def create_shapes_(self, shapeType, **kwargs):
      size = kwargs.get("size", (11, 11))
      color = kwargs.get("color", "white")
      width = kwargs.get("width", 1)
      canvas = self.canvas_
      if shapeType == "oval":
        return [canvas.create_oval(0,0,size[0],size[1], fill=color)]
      elif shapeType == "rect":
        return [canvas.create_rectangle(0,0,size[0],size[1], fill=color)]
      elif shapeType == "cross":
        return [
          canvas.create_line(0,0.5*size[1],size[0],0.5*size[1], fill=color, width=width),
          canvas.create_line(0.5*size[0],0,0.5*size[0],size[1], fill=color, width=width),
        ]
      elif shapeType == "hline":
        return [canvas.create_line(0,0,size[0],0, fill=color, width=width)]
      elif shapeType == "vline":
        return [canvas.create_line(0,0,0,size[1], fill=color, width=width)]
      else:
        raise RuntimeError("Unknown shape type: '{}'".format(shapeType))
    def add_grid_(self, layout, **kwargs):
      width = kwargs.get("width", 1)
      color = kwargs.get("color", "white")
      canvas = self.canvas_
      if layout == "box":
        cw, ch = canvas.winfo_width(), canvas.winfo_height()
        vline = canvas.create_line(0.5*cw, 0.0, 0.5*cw, ch, fill=color, width=width),
        hline = canvas.create_line(0.0, 0.5*ch, cw, 0.5*ch, fill=color, width=width)
        def resize_lines(event):
          canvas.coords(vline, 0.5*event.width, 0.0, 0.5*event.width, event.height)
          canvas.coords(hline, 0.0, 0.5*event.height, event.width, 0.5*event.height)
        canvas.bind("<Configure>", resize_lines)
  class EntriesArea:
    def add(self, **kwargs):
      child = kwargs["child"]
      child.grid(in_=self.frame_, row=self.r_, column=self.c_, rowspan=1, columnspan=1)
      if self.layout_ == "v":
        self.r_ += 1
        if self.r_ == self.dim_:
          self.r_ = 0
          self.c_ += 1
      elif self.layout_ == "h":
        self.c_ += 1
        if self.c_ == self.dim_:
          self.c_ = 0
          self.r_ += 1
      else:
        assert(False)
      self.children_.append(child)
      self.update()
    def update(self):
      for child in self.children_:
        child.update()
    def __init__(self, **kwargs):
      window = kwargs["window"]
      frame = tk.Frame(window)
      frame.pack_propagate(True)
      row=kwargs["r"]
      column=kwargs["c"]
      frame.grid(row=row, column=column, rowspan=kwargs.get("rs", 1), columnspan=kwargs.get("cs", 1))
      frame.grid_configure(sticky=kwargs.get("sticky", "nsew"))
      window.grid_rowconfigure(row, weight=kwargs.get("rw", 1))
      window.grid_columnconfigure(column, weight=kwargs.get("cw", 1))
      name = kwargs.get("name", None)
      if name is not None:
        nameLabel = tk.Label(frame, text=name)
        nameLabel.pack()
      contentsFrame = tk.Frame(frame)
      contentsFrame.pack()
      contentsFrame.pack_configure(expand=True, fill="both")
      self.frame_ = contentsFrame
      self.children_ = []
      self.dim_ = kwargs.get("dim", 8)
      self.layout_ = kwargs.get("layout", "v")
      if self.layout_ not in ("h", "v"):
        raise RuntimeError("Bad layout: '{}'".format(self.layout_))
      self.r_, self.c_ = 0, 0
  class Button:
    def grid(self, **kwargs):
      self.label_.grid(**kwargs)
    def update(self):
      state = self.getButtonState_()
      if state != self.state_:
        self.state_ = state
        styleName = "pressed" if state == True else "released"
        style = self.style_[styleName]
        for p in (("foreground", "fg"), ("background", "bg")):
          self.label_[p[0]] = style[p[1]]
    def __init__(self, **kwargs):
      self.label_ = tk.Label(master=kwargs.get("master", None), text=kwargs["name"])
      self.getButtonState_ = kwargs["getButtonState"]
      self.style_ = kwargs["style"]
      self.state_ = None
      self.update()
  class ButtonsArea(EntriesArea):
    class GetButtonState:
      def __call__(self):
        return self.output_.get_button_state(self.buttonID_)
      def __init__(self, output, buttonID):
        self.output_, self.buttonID_ = output, buttonID
    def add_buttons_from(self, output, **kwargs):
      output = self.get_output_(output) if type(output) in (str, unicode) else output
      if output is None:
        return
      buttonIDs = output.get_supported_buttons()
      for buttonID in buttonIDs:
        name = str(buttonID - codes.BTN_0)
        getButtonState = self.GetButtonState(output, buttonID)
        button = Info.Button(master=self.frame_, name=name, getButtonState=getButtonState, style=self.style_)
        self.add(child=button)
    def __init__(self, **kwargs):
      Info.EntriesArea.__init__(self, **kwargs)
      self.style_ = kwargs.get("style", {"released" : {"fg" : "black", "bg" : None}, "pressed" : {"fg" : "red", "bg" : None}})
      self.get_output_ = kwargs["getOutput"]
      source = kwargs.get("source", None)
      if source is not None:
        self.add_buttons_from(source, **kwargs)
  class AxisValue:
    def grid(self, **kwargs):
      self.frame_.grid(**kwargs)
    def update(self):
      value = self.getAxisValue_()
      self.valueLabel_["text"] = "{:+.3f}".format(value)
    def __init__(self, **kwargs):
      self.frame_ = tk.Frame(master=kwargs.get("master", None))
      self.frame_.grid(sticky="nsew")
      self.nameLabel_ = tk.Label(master=self.frame_, text=kwargs["name"])
      self.nameLabel_.pack(side="left")
      self.valueLabel_ = tk.Label(master=self.frame_)
      self.valueLabel_.pack(side="right")
      self.getAxisValue_ = kwargs["getAxisValue"]
      self.update()
  class AxesValuesArea(EntriesArea):
    class GetAxisValue:
      def __call__(self):
        return self.output_.get_axis_value(self.tcAxis_)
      def __init__(self, output, tcAxis):
        self.output_, self.tcAxis_ = output, tcAxis
    def add_axes_from(self, output, **kwargs):
      output = self.get_output_(output) if type(output) in (str, unicode) else output
      if output is None:
        return
      tcAxiss = output.get_supported_axes()
      tcAxiss.sort(key=lambda tc : tc.code)
      for tcAxis in tcAxiss:
        namesList=tc2ns(*tcAxis)
        name=namesList[0][4:]
        getAxisValue = self.GetAxisValue(output, tcAxis)
        axisValue = Info.AxisValue(master=self.frame_, name=name, getAxisValue=getAxisValue)
        self.add(child=axisValue)
    def __init__(self, **kwargs):
      Info.EntriesArea.__init__(self, **kwargs)
      self.get_output_ = kwargs["getOutput"]
      source = kwargs.get("source", None)
      if source is not None:
        self.add_axes_from(source, **kwargs)
  class ValueArea:
    def update(self):
      v = self.var_.get()
      msg = "{}: ".format(self.name_)
      if v is not None:
        try:
          msg += self.fmt_.format(**v)
        except Exception as e:
          msg = "Cannot format ({})".format(e)
      self.valueLabel_["text"] = msg
    def __init__(self, **kwargs):
      self.valueLabel_ = tk.Label(master=kwargs.get("master", None))
      self.valueLabel_.grid(row=kwargs["r"], column=kwargs["c"], rowspan=kwargs.get("rs", 1), columnspan=kwargs.get("cs", 1), sticky=kwargs.get("sticky", "nsew"))
      self.name_ = kwargs["name"]
      self.var_ = kwargs["var"]
      self.fmt_ = kwargs["fmt"]
      self.update()

  def add_area(self, **kwargs):
    kwargs["getOutput"] = self.get_output_
    area = None
    r, c = kwargs["r"], kwargs["c"]
    t = kwargs["type"]
    if t == "axes":
      layout = kwargs["layout"]
      area = self.AxesArea(window=self.w_, **kwargs)
    elif t == "buttons":
      area = self.ButtonsArea(window=self.w_, **kwargs)
    elif t == "axesValues":
      area = self.AxesValuesArea(window=self.w_, **kwargs)
    elif t == "value":
      area = self.ValueArea(master=self.w_, **kwargs)
    else:
      logger.warning("Unknown area type: {}".format(t))
    self.areas_.append(area)
    return area
  def set_state(self, s):
    if self.state_ == s:
      return
    else:
      self.state_ = s
    if s == True:
      self.w_.deiconify()
    elif s == False:
      self.w_.withdraw()
  def get_state(self):
    return self.state_
  def update(self):
    if self.state_:
      for area in self.areas_:
        area.update()
      self.w_.update()
  def __init__(self, **kwargs):
    self.state_, self.areas_ = False, []
    self.get_output_ = kwargs.get("getOutput")
    self.w_ = tk.Tk()
    self.w_.title(kwargs.get("title", ""))
    self.w_.propagate(True)
    self.w_.grid_propagate(True)
    self.w_.withdraw()


def init_info(**kwargs):
  def parse_area(areaCfg, info, state):
    main = kwargs.get("main")
    areaType = state.resolve(areaCfg, "type")
    if areaType == "value":
      valueName = state.resolve(areaCfg, "value")
      var = main.get("valueManager").get_var(valueName)
      areaCfg["var"] = var
    area = info.add_area(**areaCfg)
    if areaType == "axes":
      for markerCfg in state.resolve_d(areaCfg, "markers", ()):
        area.add_marker(**markerCfg)
  state = kwargs["state"]
  main = kwargs.get("main")
  outputs = main.get("outputs")
  getOutput = lambda name : outputs.get(name, None)

  infoCfg = kwargs["cfg"]
  f = state.resolve_d(infoCfg, "format", 1)
  title = state.resolve_d(infoCfg, "title", "")
  info = Info(title=title, getOutput=getOutput)
  areas = state.resolve_d(infoCfg, "areas", ())
  if f == 1:
    for areaCfg in areas:
      parse_area(areaCfg, info, state)
  elif f == 2:
    r, c = 0, 0
    for row in areas:
      for col in row:
        col["r"], col["c"] = r, c
        parse_area(col, info, state)
        c += state.resolve_d(col, "cs", 1)
      c = 0
      r += 1
  else:
    raise RuntimeError("Unknown format: {}".format(f))

  main.get("updated").append(lambda tick,ts : info.update())

  return info


def init_main_sink(state, make_next):
  #logger.debug("init_main_sink()")
  main = state.get("main")
  config = main.get("config")

  headSink = HeadSink()
  state.push("sinks", headSink)
  topSink = bottomSink = headSink
  mappingSink = state.get("parser").get("sc").get("mapping")(config, state)
  if mappingSink is not None:
    bottomSink.set_next(mappingSink)
    bottomSink = mappingSink
  defaultModifierDescs = [
    SourceCodeState(None, m, True) for m in
    (codes.KEY_LEFTSHIFT, codes.KEY_RIGHTSHIFT, codes.KEY_LEFTCTRL, codes.KEY_RIGHTCTRL, codes.KEY_LEFTALT, codes.KEY_RIGHTALT)
  ]
  modifiers = state.resolve_d(config, "modifiers", None)
  modifierDescs = defaultModifierDescs if modifiers is None else [parse_modifier_desc(m, None) for m in modifiers]
  modifierSink = ModifierSink(modifierDescs=modifierDescs, saveModifiers=False, mode=ModifierSink.OVERWRITE)
  bottomSink.set_next(modifierSink)
  clickSink = modifierSink.set_next(ClickSink(state.resolve_d(config, "clickTime", 0.5)))
  holdDataCfg = state.resolve_d(config, "holds", [])
  holdSink = clickSink.set_next(HoldSink())
  for hd in holdDataCfg:
    keyFullName = state.resolve_d(hd, "key", None)
    keySource, keyCode = fn2hc(keyFullName) if keyFullName is not None else (None, None)
    modifiers = state.resolve_d(hd, "modifiers", None)
    if modifiers is not None:
      modifiers = (parse_modifier_desc(m, state) for m in modifiers)
    num = state.resolve_d(hd, "num", -1)
    holdSink.add(keySource, keyCode, modifiers, state.resolve_d(hd, "period"), state.resolve_d(hd, "value"), num)
  main.get("updated").append(lambda tick,ts : holdSink.update(tick, ts))

  sensSetsCfg = state.resolve_d(config, "sens", None)
  sens = {}
  if sensSetsCfg is not None:
    sensSet = state.resolve_d(config, "sensSet", None)
    if sensSet not in sensSetsCfg:
      raise Exception("Invalid sensitivity set: {}".format(sensSet))
    sens = state.resolve(sensSetsCfg, sensSet)
    for s in sens.items():
      sens[fn2htc(state.deref(s[0]))] = state.deref(s[1])
  scaleSink = holdSink.set_next(ScaleSink2(sens))

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

  stateSink = StateSink()
  toggler = Toggler(stateSink)

  released = state.resolve_d(config, "released", [])
  for i in range(len(released)):
    released[i] = state.deref(released[i])
  sourceFilterOp = SourceFilterOp(released)
  filterSink = stateSink.set_next(FilterSink(sourceFilterOp))
  namesOfReleasedStr = ", ".join(released)

  def print_ungrabbed(event):
    logger.info("{} ungrabbed".format(namesOfReleasedStr))
  def print_grabbed(event):
    logger.info("{} grabbed".format(namesOfReleasedStr))

  info = init_info(cfg=state.resolve_d(config, "info", {}), main=main, state=state)

  enabled = [True]
  actionParser = main.get("parser").get("action")

  def parseToggle(cfg, state):
    return toggler.make_toggle()
  actionParser.add("toggle", parseToggle)

  def parseReload(cfg, state):
    def op(e):
      main.set("state", stateSink.get_state())
      raise ReloadException()
    return op
  actionParser.add("reload", parseReload)

  def parseExit(cfg, state):
    def op(e):
      raise ExitException()
    return op
  actionParser.add("exit", parseExit)

  def parseEnable(cfg, state):
    callbacks = (SetState(sourceFilterOp, True), SwallowSource(main.get("source"), [(n,True) for n in released]),  print_grabbed,)
    def op(event):
      if stateSink.get_state() and not enabled[0]:
        for cb in callbacks:
          cb(event)
        enabled[0] = True
    return op
  actionParser.add("enable", parseEnable)

  def parseDisable(cfg, state):
    callbacks2 = (SetState(sourceFilterOp, False), SwallowSource(main.get("source"), [(n,False) for n in released]),  print_ungrabbed,)
    def op(event):
      if stateSink.get_state() and enabled[0]:
        for cb in callbacks2:
          cb(event)
        enabled[0] = False
    return op
  actionParser.add("disable", parseDisable)

  def parseGrab(cfg, state):
    inputs = get_nested_d(cfg, "inputs", None)
    inputs = released if inputs is None else [state.deref(i) for i in inputs]
    return SwallowSource(main.get("source"), [(n,True) for n in inputs])
  actionParser.add("grab", parseGrab)

  def parseUngrab(cfg, state):
    inputs = get_nested_d(cfg, "inputs", None)
    inputs = released if inputs is None else [state.deref(i) for i in inputs]
    return SwallowSource(main.get("source"), [(n,False) for n in inputs])
  actionParser.add("ungrab", parseUngrab)

  def parseShowInfo(cfg, state):
    def op(e):
      info.set_state(True)
    return op
  actionParser.add("showInfo", parseShowInfo)

  def parseHideInfo(cfg, state):
    def op(e):
      info.set_state(False)
    return op
  actionParser.add("hideInfo", parseHideInfo)

  def parseToggleInfo(cfg, state):
    def op(e):
      info.set_state(not info.get_state())
    return op
  actionParser.add("toggleInfo", parseToggleInfo)

  bindSink = main.get("parser").get("sc").get("binds")(config, state)
  bindSink.add(None, stateSink, 1)
  scaleSink.set_next(bindSink)

  grabbed = state.resolve_d(config, "grabbed", [])
  for i in range(len(grabbed)):
    grabbed[i] = state.deref(grabbed[i])
  namesOfGrabbedStr = ", ".join(grabbed)

  def print_enabled(event):
    logger.info("Emulation enabled; {} grabbed".format(namesOfGrabbedStr))
  def print_disabled(event):
    logger.info("Emulation disabled; {} ungrabbed".format(namesOfGrabbedStr))

  grabSink = filterSink.set_next(BindSink())
  grabSink.add(ET.init(1), Call(SwallowSource(main.get("source"), [(n,True) for n in grabbed]), print_enabled), 0)
  grabSink.add(ET.init(0), Call(SwallowSource(main.get("source"), [(n,False) for n in grabbed]), print_disabled), 0)

  #axes are created on demand by get_axis_by_full_name
  #remove listeners from axes if reinitializing
  for oName, oAxes in main.get("axes").items():
    for tcAxis, axis in oAxes.items():
      axis.remove_all_listeners()

  grabSink.add(None, make_next(state), 1)
  if main.get("reloading") == False:
    main.set("state", state.resolve_d(config, "initialState", False))
  stateSink.set_state(main.get("state"))
  toggler.s_ = stateSink.get_state()
  logger.info("Initialization successfull")

  return topSink


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
      logger.warning("Cannot load config file {} ({})".format(configName, str2(e)))
  return cfg


def init_preset_config(state):
  main = state.get("main")
  config = main.get("config")
  presetName = state.resolve(config, "preset")
  logger.info("Using '{}' preset from config".format(presetName))
  presetsCfg = state.resolve_d(config, "presets", {})
  presetCfg = state.resolve_d(presetsCfg, presetName, None)
  if presetCfg is None:
    raise Exception("'{}' preset not found in config".format(presetName))
  else:
    try:
      parser = main.get("parser")
      r = parser("sink", presetCfg, state)
      return r
    except KeyError2 as e:
      logger.error("Error while initializing config preset '{}': cannot find key '{}' in {}".format(presetName, e.key, e.keys))
      raise
    except KeyError as e:
      logger.error("Error while initializing config preset '{}': cannot find key '{}'".format(presetName, str(e)))
      raise
    except Exception as e:
      logger.error("Error while initializing config preset '{}': {}".format(presetName, e))
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


class ParserError(RuntimeError):
  def __init__(self, cfg):
    self.cfg = cfg
  def __str__(self):
    return "Could not parse {}".format(str2(self.cfg))


class ParserNotFoundError(KeyError2):
  def __init__(self, requestetParser, availableParsers, cfg=None):
    KeyError2.__init__(self, requestetParser, availableParsers)
    self.cfg = cfg
  def __str__(self):
    return "Parser {} not found, available parsers are: {} (encountered when parsing: {})".format(self.key, self.keys, str2(self.cfg))


class SelectParser:
  def __call__(self, key, cfg, state):
    if key not in self.parsers_:
      raise ParserNotFoundError(key, self.parsers_.keys())
    else:
      parser = self.parsers_[key]
      try:
        r = parser(cfg, state)
        return r
      except Exception as e:
        #logger.error("Got exception: '{}', so cannot parse key '{}', cfg '{}".format(e, key, truncate(cfg, l=50)))
        raise
      except:
        #logger.error("Unknown exception when parsing key '{}', cfg '{}'".format(key, truncate(cfg, l=50)))
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
  def __call__(self, cfg, state):
    key = self.keyOp_(cfg, state)
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


class DerefSelectParser:
  def __call__(self, key, cfg, state):
    #logger.debug("DerefSelectParser.(): key: {}, cfg: {}".format(str2(key), str2(cfg)))
    r = state.deref(key)
    return self.p_(key, cfg, state) if r == key else r

  def add(self, key, parser):
    self.p_.add(key, parser)

  def get(self, key, dfault=None):
    return self.p_.get(key, dfault)

  def has(self, key):
    return self.p_.has(key)

  def __init__(self, parser=None):
    self.p_ = SelectParser() if parser is None else parser


class DerefParser:
  def __call__(self, cfg, state):
    r = state.deref(cfg)
    return self.p_(cfg, state) if r == cfg else r

  def add(self, key, parser):
    self.p_.add(key, parser)

  def get(self, key, dfault=None):
    return self.p_.get(key, dfault)

  def has(self, key):
    return self.p_.has(key)

  def __init__(self, parser):
    self.p_ = parser


class HeadSink:
  def __call__(self, event):
    #Can be actually called during init when next_ is not set yet
    if self.next_ is None:
      #logger.debug("{}: next sink is not set".format(self))
      return False
    else:
      return self.next_(event)

  def get_component(self, name, dfault=None):
    return self.components_.get(name, dfault)

  def set_component(self, name, component):
    self.components_[name] = component

  def remove_component(self, name):
    del self.components_[name]

  def get(self, name, dfault=None):
    return self.get_component(name, dfault)

  def set(self, name, component):
    self.set_component(name, component)

  def set_next(self, next):
      self.next_ = next

  def get_parent(self):
    return self.parent_

  def __init__(self, next=None, components=None, parent=None, objects=None):
    self.next_, self.components_, self.parent_, self.objects_ = next, components if components is not None else {}, parent, objects if objects is not None else {}


class ObjectsComponent:
  def get(self, k, sep = "."):
    o = get_nested_d(self.objects_, k, None, sep)
    return o

  def set(self, name, obj):
    self.objects_[name] = obj

  def __init__(self):
    self.objects_ = {}


def make_parser():
  def make_double_deref_parser(keyOp):
    return DerefParser(parser=IntrusiveSelectParser(keyOp=keyOp, parser=DerefSelectParser()))

  def make_outer_deref_parser(keyOp):
    return DerefParser(parser=IntrusiveSelectParser(keyOp=keyOp, parser=SelectParser()))

  mainParser = SelectParser()

  def literalParser(cfg, state):
    return state.resolve(cfg, "literal")
  mainParser.add("literal", literalParser)

  funcParserKeyOp = lambda cfg,state : get_nested(cfg, "func")
  funcParser = make_double_deref_parser(keyOp=funcParserKeyOp)
  mainParser.add("func", funcParser)

  def make_symm_wrapper(wrapped, symm):
    if symm in (1, "x"):
      return lambda x : wrapped(abs(x))
    elif symm in (2, "xy"):
      return lambda x : sign(x)*wrapped(abs(x))
    else:
      return wrapped

  def make_tracker(cfg, state):
    tracker = None
    trackerCfg = state.resolve_d(cfg, "tracker", None)
    if trackerCfg is not None:
      tracker = state.get("parser")("tracker", trackerCfg, state)
      assert(tracker is not None)
    return tracker

  def constant(cfg, state):
    return ConstantFunc(state.resolve(cfg, "value"), make_tracker(cfg, state))
  funcParser.add("constant", constant)

  def segment(cfg, state):
    points = state.resolve(cfg, "points")
    factor = state.resolve_d(cfg, "factor", 1.0)
    clampLeft = state.resolve_d(cfg, "clampLeft", True)
    clampRight = state.resolve_d(cfg, "clampRight", True)
    func = SegmentFunc(points, factor, clampLeft, clampRight, make_tracker(cfg, state))
    symmetric = state.resolve_d(cfg, "symmetric", 0)
    return make_symm_wrapper(func, symmetric)
  funcParser.add("segment", segment)

  def poly(cfg, state):
    class CoeffsSetter:
      def __call__(self, coeffs):
        if self.func_ is not None:
          coeffs = {int(p) : k for p,k in coeffs.items()}
          self.func_.set_coeffs(coeffs)
      def set_func(self, func):
        self.func_ = func
      def __init__(self, func=None):
        self.func_ = func
    coeffsSetter = CoeffsSetter()
    coeffs = state.resolve(cfg, "coeffs", setter=coeffsSetter)
    if type(coeffs) not in (dict, collections.OrderedDict):
      raise RuntimeError("coeffs should be dict-like")
    coeffs = {int(p) : k for p,k in coeffs.items()}
    offset = state.resolve_d(cfg, "offset", 0.0)
    func = PolynomialFunc(coeffs, offset, make_tracker(cfg, state))
    coeffsSetter.set_func(func)
    symmetric = state.resolve_d(cfg, "symmetric", 0)
    return make_symm_wrapper(func, symmetric)
  funcParser.add("poly", poly)

  def sigmoid(cfg, state):
    k = state.resolve_d(cfg, "k", 1.0)
    p0 = state.resolve_d(cfg, "p0", 0.5)
    r = state.resolve_d(cfg, "r", 1.0)
    s = state.resolve_d(cfg, "s", 0.0)
    func = SigmoidFunc(k, p0, r, s, make_tracker(cfg, state))
    symmetric = state.resolve_d(cfg, "symmetric", 0)
    return make_symm_wrapper(func, symmetric)
  funcParser.add("sigmoid", sigmoid)

  def bezier(cfg, state):
    points = state.resolve(cfg, "points")
    func = BezierFunc(points, make_tracker(cfg, state))
    symmetric = state.resolve_d(cfg, "symmetric", 0)
    return make_symm_wrapper(func, symmetric)
  funcParser.add("bezier", bezier)

  def sbezier(cfg, state):
    points = state.resolve(cfg, "points")
    func = SegmentedBezierFunc(points, make_tracker(cfg, state))
    return make_symm_wrapper(func, state.resolve_d(cfg, "symmetric", 0))
  funcParser.add("sbezier", sbezier)

  def weighted(cfg, state):
    o = state.resolve(cfg, "degree")
    w = state.resolve(cfg, "weight")
    db = state.resolve_d(cfg, "deadband", 0.0)
    func = WeightedFunc(o, w, db, make_tracker(cfg, state))
    return make_symm_wrapper(func, state.resolve_d(cfg, "symmetric", 0))
  funcParser.add("weighted", weighted)

  def get_func(cfg, state, **kwargs):
    op = state.resolve(cfg, "func", **kwargs)
    if type(op) in (str, unicode):
      op = state.get("parser")("func", cfg, state)
    return op

  #Curves
  curveParserKeyOp=lambda cfg,state : get_nested(cfg, "curve")
  #needs to be double deref parser to process '"curve" : "obj:..."'
  curveParser = make_double_deref_parser(keyOp=curveParserKeyOp)
  mainParser.add("curve", curveParser)

  def parseAxisLinker(cfg, state):
    fnControlledAxis = state.resolve(cfg, "follower")
    controlledAxis = state.get_axis_by_full_name(fnControlledAxis)
    class FuncSetter:
      def __call__(self, func):
        self.axisLinker.set_func(func)
    funcSetter = FuncSetter()
    func = get_func(cfg, state, setter=funcSetter)
    fnControllingAxis = state.resolve(cfg, "leader")
    controllingAxis = state.get_axis_by_full_name(fnControllingAxis)
    linker = AxisLinker(controllingAxis, controlledAxis, func)
    funcSetter.axisLinker = linker
    controlledAxis.add_listener(linker)
    controllingAxis.add_listener(linker)
    #FIXME Since there is no "axis" property in config node, it does not get added to state["curves"]
    state.add_curve(fnControlledAxis, linker)
    state.add_curve(fnControllingAxis, linker)
    return linker
  curveParser.add("linker", parseAxisLinker)

  def makeSensModOp(cfg, state, sensOp, combine=lambda a,b: a*b):
    if "sensMod" not in cfg:
      return sensOp
    else:
      axis = state.get_axis_by_full_name(state.resolve(cfg, "sensMod.axis"))
      func = state.get("parser")("func", state.resolve(cfg, "sensMod.func"), state)
      class SensModOp:
        def calc(self, x, timestamp):
          return self.combine_(self.next_.calc(x, timestamp), self.func_(self.axis_.get()))
        def reset(self):
          self.next_.reset()
        def __init__(self, combine, next, func, axis):
          self.next_, self.combine_, self.func_, self.axis_ = next, combine, func, axis
      return SensModOp(combine, sensOp, func, axis)

  def makeIterativeInputOp(cfg, outputOp, state):
    inputOp = IterativeInputOp(outputOp=outputOp, eps=state.resolve_d(cfg, "eps", 0.001), numSteps=state.resolve_d(cfg, "numSteps", 100))
    inputLimits = state.resolve(cfg, "inputLimits")
    inputStep = state.resolve_d(cfg, "inputStep", 0.1)
    expandLimits = state.resolve_d(cfg, "expandLimits", False)
    inputOp = LookupOp(inputOp, outputOp, inputStep, inputLimits, expandLimits)
    #inputOp = LimitedOpToOp(inputOp, inputLimits)
    return inputOp

  def parseInputBasedCurve2(cfg, state):
    fnAxis = state.resolve(cfg, "axis")
    axis = state.get_axis_by_full_name(fnAxis)
    dynamicCfg = state.resolve(cfg, "dynamic")
    signDDOp = SignDistanceDeltaOp()
    timeDDOp = TimeDistanceDeltaOp(resetTime=dynamicCfg.get("resetTime", float("inf")), holdTime=dynamicCfg.get("holdTime", 0.0))
    deltaOp = CombineDeltaOp(
      combine=lambda x,s : x*s,
      ops=(ReturnDeltaOp(), AccumulateDeltaOp(state.get("parser")("func", dynamicCfg, state), ops=[signDDOp, timeDDOp]))
    )
    outputOp = FuncOp(func=state.get("parser")("func", state.resolve(cfg, "static"), state))
    inputOp = makeIterativeInputOp(cfg, outputOp, state)
    deltaOp = makeSensModOp(cfg, state, deltaOp)
    deltaOp = DeadzoneDeltaOp(deltaOp, state.resolve_d(cfg, "deadzone", 0.0))
    resetOpsOnAxisMove = state.resolve_d(cfg, "resetOpsOnAxisMove", True)
    ivLimits = state.resolve_d(cfg, "inputLimits", (-1.0, 1.0))
    curve = InputBasedCurve2(axis=axis, inputOp=inputOp, outputOp=outputOp, deltaOp=deltaOp, inputValueLimits=ivLimits, resetOpsOnAxisMove=resetOpsOnAxisMove)
    axis.add_listener(curve)
    state.add_curve(fnAxis, curve)
    return curve
  curveParser.add("input2", parseInputBasedCurve2)

  def parseOffsetCurve(cfg, state):
    #axis tracker
    top = AxisTrackerChainCurve(next=None)
    curve = top
    fnAxis = state.resolve(cfg, "axis")
    axis = state.get_axis_by_full_name(fnAxis)
    axis.add_listener(curve)
    #accumulate
    #Order of ops should not matter
    dynamicCfg = state.resolve(cfg, "dynamic")
    valueDDOp = SignDistanceDeltaOp()
    valueDDOp = TimeDistanceDeltaOp(next=valueDDOp, resetTime=dynamicCfg.get("resetTime", float("inf")), holdTime=dynamicCfg.get("holdTime", 0.0))
    deltaDOp = ReturnDeltaOp()
    deltaDOp = DeadzoneDeltaOp(deltaDOp, dynamicCfg.get("deadzone", 0.0))
    deltaDOp = makeSensModOp(dynamicCfg, state, deltaDOp)
    combine = lambda a,b: a+b
    class ResetOp:
      def calc(self, value):
        return value if self.value_ is None else self.value_
      def reset(self):
        pass
      def __init__(self, value=None):
        self.value_ = value
    resetOnMoveAxis = state.resolve_d(cfg, "resetOnMoveAxis", True)
    inputOp = ResetOp(0.0 if resetOnMoveAxis else None)
    accumulateChainCurve = AccumulateRelChainCurve(next=None, valueDDOp=valueDDOp, deltaDOp=deltaDOp, combine=combine, inputOp=inputOp, resetOnMoveAxis=resetOnMoveAxis)
    curve.set_next(accumulateChainCurve)
    #transform accumulated
    dynamicOutputOp = FuncOp(func=state.get("parser")("func", dynamicCfg, state))
    dynamicInputOp = makeIterativeInputOp(cfg, dynamicOutputOp, state)
    dymamicChainCurve = TransformAbsChainCurve(next=None, inputOp=dynamicInputOp, outputOp=dynamicOutputOp)
    accumulateChainCurve.set_next(dymamicChainCurve)
    #offset transformed
    offsetChainCurve = OffsetAbsChainCurve(next=None)
    dymamicChainCurve.set_next(offsetChainCurve)
    #transform offset
    staticCfg = state.resolve(cfg, "static")
    staticOutputOp = FuncOp(func=state.get("parser")("func", staticCfg, state))
    staticInputOp = makeIterativeInputOp(cfg, staticOutputOp, state)
    staticChainCurve = TransformAbsChainCurve(next=None, inputOp=staticInputOp, outputOp=staticOutputOp)
    offsetChainCurve.set_next(staticChainCurve)
    #move axis
    axisChainCurve = AxisChainCurve(axis=axis)
    staticChainCurve.set_next(axisChainCurve)
    state.add_curve(fnAxis, curve)
    return top
  curveParser.add("offset", parseOffsetCurve)

  def makeInputValueDDOp(cfg, state):
    inputValueDDOp = SignDistanceDeltaOp()
    resetFuncCfg = state.resolve_d(cfg, "resetFunc", None)
    if resetFuncCfg is not None:
      resetFunc = state.get("parser")("func", resetFuncCfg, state)
      def resetOp2(distance, delta, timestamp, dt):
        factor = resetFunc(dt)
        return factor*distance
      inputValueDDOp = ExtDistanceDeltaOp(next=inputValueDDOp, op=resetOp2)
    else:
      inputValueDDOp = TimeDistanceDeltaOp(next=inputValueDDOp, resetTime=cfg.get("resetTime", float("inf")), holdTime=cfg.get("holdTime", 0.0))
    return inputValueDDOp

  def makeInputDeltaDDOp(cfg, state):
    inputDeltaDOp = ReturnDeltaOp()
    inputDeltaDOp = DeadzoneDeltaOp(inputDeltaDOp, cfg.get("deadzone", 0.0))
    inputDeltaDOp = makeSensModOp(cfg, state, inputDeltaDOp)
    inputDeltaDDOp = DistanceDeltaFromDeltaOp(inputDeltaDOp)
    return inputDeltaDDOp

  def parseAccelCurve(cfg, state):
    #axis tracker
    top = AxisTrackerChainCurve(next=None)
    bottom = top
    fnAxis = state.resolve(cfg, "axis")
    axis = state.get_axis_by_full_name(fnAxis)
    axis.add_listener(top)
    #accelerate
    #Order of ops should not matter
    dynamicCfg = state.resolve_d(cfg, "dynamic", None)
    if dynamicCfg is not None:
      valueDDOp = makeInputValueDDOp(dynamicCfg, state)
      deltaDDOp = makeInputDeltaDDOp(dynamicCfg, state)
      dynamicOutputOp = FuncOp(func=state.get("parser")("func", dynamicCfg, state))
      combineValue = lambda value,x: value+x
      combineDelta = lambda delta,factor: delta*factor
      resetOnMoveAxis = state.resolve_d(cfg, "resetOnMoveAxis", True)
      accelChainCurve = DeltaRelChainCurve(next=None, valueDDOp=valueDDOp, deltaDDOp=deltaDDOp, outputOp=dynamicOutputOp, combineValue=combineValue, combineDelta=combineDelta, resetOnMoveAxis=resetOnMoveAxis)
      bottom.set_next(accelChainCurve)
      bottom = accelChainCurve
    #transform
    staticCfg = state.resolve_d(cfg, "static", None)
    if staticCfg is not None:
      relToAbsChainCurve = RelToAbsChainCurve(next=None)
      bottom.set_next(relToAbsChainCurve)
      staticOutputOp = FuncOp(func=state.get("parser")("func", staticCfg, state))
      staticInputOp = makeIterativeInputOp(cfg, staticOutputOp, state)
      staticChainCurve = TransformAbsChainCurve(next=None, inputOp=staticInputOp, outputOp=staticOutputOp)
      relToAbsChainCurve.set_next(staticChainCurve)
      bottom = staticChainCurve
    #move axis
    axisChainCurve = AxisChainCurve(axis=axis)
    bottom.set_next(axisChainCurve)
    state.add_curve(fnAxis, top)
    return top
  curveParser.add("accel", parseAccelCurve)

  def parseFullDeltaCurve(cfg, state):
    #axis tracker
    top = AxisTrackerChainCurve(next=None)
    bottom = top
    fnAxis = state.resolve(cfg, "axis")
    axis = state.get_axis_by_full_name(fnAxis)
    axis.add_listener(top)
    #accelerate
    #Order of ops should not matter
    dynamicCfg = state.resolve_d(cfg, "dynamic", None)
    if dynamicCfg is not None:
      inputValueDDOp = makeInputValueDDOp(dynamicCfg, state)
      inputDeltaDDOp = makeInputDeltaDDOp(dynamicCfg, state)
      dynamicOutputValueOp = FuncOp(func=state.get("parser")("func", dynamicCfg, state))
      resetOnMoveAxis = state.resolve_d(cfg, "resetOnMoveAxis", True)
      accelChainCurve = FullDeltaRelChainCurve(next=None, inputValueDDOp=inputValueDDOp, inputDeltaDDOp=inputDeltaDDOp, outputValueOp=dynamicOutputValueOp, resetOnMoveAxis=resetOnMoveAxis)
      bottom.set_next(accelChainCurve)
      bottom = accelChainCurve
    #accumulate and transform
    staticCfg = state.resolve_d(cfg, "static", None)
    if staticCfg is not None:
      #accumulate
      relToAbsChainCurve = RelToAbsChainCurve(next=None)
      bottom.set_next(relToAbsChainCurve)
      bottom = relToAbsChainCurve
      #transform
      staticOutputOp = FuncOp(func=state.get("parser")("func", staticCfg, state))
      staticInputOp = makeIterativeInputOp(cfg, staticOutputOp, state)
      staticChainCurve = TransformAbsChainCurve(next=None, inputOp=staticInputOp, outputOp=staticOutputOp)
      bottom.set_next(staticChainCurve)
      bottom = staticChainCurve
    #move axis
    axisChainCurve = AxisChainCurve(axis=axis)
    bottom.set_next(axisChainCurve)
    state.add_curve(fnAxis, top)
    return top
  curveParser.add("fulldelta", parseFullDeltaCurve)

  def parsePresetCurve(cfg, state):
    #logger.debug("parsePresetCurve(): cfg: '{}'".format(str2(cfg)))
    config = state.get("main").get("config")
    presetName = state.resolve_d(cfg, "name", None)
    if presetName is None:
      raise RuntimeError("Preset name was not specified")
    presetCfg = get_nested_from_sections_d(config, ("presets",), presetName, None)
    if presetCfg is None:
      presets = config.get("presets", collections.OrderedDict())
      raise RuntimeError("Preset '{}' does not exist; available presets are: '{}'".format(presetName, [k.encode("utf-8") for k in presets.keys()]))
    #creating curve
    if "args" in cfg:
      #logger.debug("parsePresetCurve(): args: '{}'".format(str2(argsCfg)))
      state.push_args(cfg)
      try:
        #logger.debug("{} -> {}".format(get_nested(cfg, "args"), args))
        return state.get("parser")("curve", presetCfg, state)
      finally:
        state.pop_args()
    else:
      presetCfgStack = CfgStack(presetCfg)
      try:
        for n in ("axis", "controlling", "leader", "follower"):
          if n in cfg:
            presetCfgStack.push(n, cfg[n])
        curve = state.get("parser")("curve", presetCfg, state)
        return curve
      finally:
        presetCfgStack.pop_all()
  curveParser.add("preset", parsePresetCurve)

  def parseNoopCurve(cfg, state):
    fnAxis = state.resolve(cfg, "axis")
    #To init state
    state.get_axis_by_full_name(fnAxis)
    curve = NoopCurve(value=state.resolve_d(cfg, "value", 0.0))
    state.add_curve(fnAxis, curve)
    return curve
  curveParser.add("noop", parseNoopCurve)

  def parseBasesDecorator(wrapped):
    def worker(cfg, state):
      """Merges all base config definitions if they are specified."""
      bases = state.resolve_d(cfg, "bases", None)
      if bases is None:
        return cfg
      else:
        sectNames = ("presets",)
        config = state.get("main").get("config")
        full = {}
        for baseName in bases:
          #logger.debug("Parsing base : {}".format(baseName))
          base = get_nested_from_sections_d(config, sectNames, baseName, None)
          if base is None:
            raise RuntimeError("No preset: {}".format(str2(base)))
          merge_dicts(full, worker(base, state))
        merge_dicts(full, cfg)
        del full["bases"]
        return full
    def parseBasesOp(cfg, state):
      expandedCfg = worker(cfg, state)
      #logger.debug("parseBasesOp():\n{}\n->\n{}".format(str2(cfg), str2(expandedCfg)))
      return wrapped(expandedCfg, state)
    return parseBasesOp

  def parseExternal(propName, groupNames):
    def parseExternalOp(cfg, state):
      config = state.get("main").get("config")
      name = cfg.get(propName, None)
      if name is None:
        name = state.resolve(cfg, "name")
      #logger.debug("Parsing {} '{}'".format(propName, name))
      #preset or class name can be specified by arg, so need to deref it here
      name = state.deref(name)
      externalCfg = get_nested_from_sections_d(config, groupNames, name, None)
      if externalCfg is None:
        raise RuntimeError("No class {}".format(str2(name)))
      state.push_args(cfg)
      try:
        return state.get("parser")("sink", externalCfg, state)
      finally:
        state.pop_args()
    return parseExternalOp

  def sinkParserKeyOp(cfg, state):
    names = ("preset",)
    if type(cfg) in (dict, collections.OrderedDict):
      for name in names:
        if name in cfg or get_nested_d(cfg, "type", "") == name:
          return name
    return "sink"

  sinkParser = make_outer_deref_parser(keyOp=sinkParserKeyOp)
  mainParser.add("sink", sinkParser)
  sinkParser.add("preset", parseExternal("preset", ("presets",)))

  @parseBasesDecorator
  def parseSink(cfg, state):
    """
    Constructs sink chain from components as specified in cfg.
    At the top of this chain is a HeadSink that stores all initialized components.
    Some of initialized components are then linked one after another.
    Each component is described by dedicated section in cfg. If a section is missing, components is not intialized.
    next and modes components are mutually exclusive.
    Init order: objects, (next or modes), state, sens, modifiers, binds
    Link order: modifiers, sens, binds, state, (next or modes)
    """
    parser = state.get("parser").get("sc")
    state.push_args(cfg)
    state.push("curves", {})
    #Init headsink
    parent = state.at("sinks", 0)
    headSink = HeadSink(parent=parent)
    state.push("sinks", headSink)
    #Since python 2.7 does not support nonlocal variables, declaring 'sink' as list to allow parse_component() modify it
    #logger.debug("parsing sink {}".format(cfg))
    def parse_component(name, set_component=None):
      #logger.debug("parsing component '{}'".format(name))
      if name in cfg:
        t = parser(name, cfg, state)
        if t is not None and set_component is not None:
          set_component(headSink, name, t)
    sink = [None]
    def link_component(name, op=None):
      #logger.debug("linking component '{}'".format(name))
      t = headSink.get_component(name, None)
      if t is not None:
        if op is not None:
          op(sink[0], t)
        sink[0] = t
    def set_next(next, sink):
      if next is not None:
        sink.set_next(next)
    def add_default_bind(next, sink):
      if next is not None:
        #By default next sink is added to level 0 so it will be able to process events that were processed by other binds.
        #This is useful in case like when a bind and a mode both need to process some axis event.
        defaultBindET = state.resolve_d(cfg, "defaultBind.on", None)
        if defaultBindET is not None:
          defaultBindET = state.get("parser")("et", defaultBindET, state)
        defaultBindLevel = state.resolve_d(cfg, "defaultBind.level", 0)
        sink.add(defaultBindET, next, defaultBindLevel)
    try:
      #TODO Refactor
      if len(cfg) == 0:
        def noop(event):
          return False
        return noop
      #Parse components
      if "modes" in cfg and "next" in cfg:
        raise RuntimeError("'next' and 'modes' components are mutually exclusive")
      def set_component(headSink, name, t):
        headSink.set_component(name, t)
      assert headSink is state.at("sinks", 0)
      parseOrder = (("objects", None), ("next", set_component), ("values", set_component), ("modes", None), ("state", set_component), ("sens", set_component), ("modifiers", set_component), ("binds", set_component), ("mapping", set_component) )
      for name,set_component in parseOrder:
        parse_component(name, set_component)
      #Link components
      #Linking is performed in reverse order - from "tail" to "head", with linking "tail" to "head"
      linkOrder = (("next", None), ("modes", None), ("state", set_next), ("binds", add_default_bind), ("values", set_next), ("sens", set_next), ("modifiers", set_next), ("mapping", set_next))
      assert headSink is state.at("sinks", 0)
      for p in linkOrder:
        link_component(p[0], p[1])
      #Check result
      if sink[0] is None:
        #logger.debug("Could not make sink out of '{}'".format(cfg))
        return None
      else:
        headSink.set_next(sink[0])
        return headSink
    finally:
      state.pop("sinks")
      state.pop_args()
      state.pop("curves")
  sinkParser.add("sink", parseSink)

  #Sink components
  #Sink components cfgs are supposed to be specified in sink cfg, they cannot be referenced as args or objs, so using regular SelectParser.
  scParser = SelectParser()
  mainParser.add("sc", scParser)

  def parseMapping(cfg, state):
    mappingCfg = cfg.get("mapping", None)
    if mappingCfg is not None:
      mapping = {}
      for frm,to in mappingCfg.items():
        mapping[fn2htc(frm)] = fn2htc(to)
      mappingSink = MappingSink(mapping)
      return mappingSink
    else:
      return None
  scParser.add("mapping", parseMapping)

  def parseObjects(cfg, state):
    objectsCfg = cfg.get("objects", None)
    if objectsCfg is not None:
      #logger.debug("parseObjects(): parsing objects from '{}'".format(str2(objectsCfg)))
      try:
        objectsComponent = ObjectsComponent()
        state.at("sinks", 0).set("objects", objectsComponent)
        state.make_objs(objectsCfg, lambda k,o : objectsComponent.set(k, o))
        return objectsComponent
      except RuntimeError as e:
        raise RuntimeError("{} (encountered when parsing objects cfg {})".format(e, str2(objectsCfg, 100)))
    else:
      return None
  scParser.add("objects", parseObjects)

  def parseModifiers(cfg, state):
    modifierDescs = [parse_modifier_desc(m, state) for m in state.resolve(cfg, "modifiers")]
    modifierSink = ModifierSink(next=None, modifierDescs=modifierDescs, saveModifiers=True, mode=ModifierSink.APPEND)
    return modifierSink
  scParser.add("modifiers", parseModifiers)

  def parseSens(cfg, state):
    class Setter:
      def __call__(self, v):
        self.scaleSink_.set_sens(self.key_, v)
      def __init__(self, scaleSink, key):
        self.scaleSink_, self.key_ = scaleSink, key
    try:
      name = state.resolve_d(cfg, "name", None)
      sens = state.resolve(cfg, "sens")
      scaleSink = ScaleSink2(sens={}, name=name)
      sens2 = {}
      for fnAxis,value in sens.items():
        key = fn2htc(fnAxis)
        setter = Setter(scaleSink, key)
        value = state.deref(value, setter=setter)
        scaleSink.set_sens(key, value)
      return scaleSink
    except RuntimeError as e:
      raise RuntimeError("'{}' (encountered when parsing '{}')".format(e, str2(sens)))
  scParser.add("sens", parseSens)

  @parseBasesDecorator
  def parseMode(cfg, state):
    class ModeSetter:
      def __call__(self, v):
        self.msmm_.set(v, self.save_, self.current_, self.report_)
      def __init__(self, msmm, save, current, report):
        self.msmm_, self.save_, self.current_, self.report_ = msmm, save, current, report
    name = state.resolve_d(cfg, "name", "")
    allowMissingModes = state.resolve_d(cfg, "allowMissingModes", False)
    headSink = state.at("sinks", 0)
    modeSink = ModeSink(name)
    msmm = ModeSinkModeManager(modeSink)
    headSink.set_component("msmm", msmm)
    headSink.set_component("modes", modeSink)
    try:
      for modeName,modeCfg in state.resolve(cfg, "modes").items():
        try:
          #logger.debug("{}: parsing mode:".format(name, modeName))
          child = state.get("parser")("sink", modeCfg, state)
          modeSink.add(modeName, child)
        except Exception as e:
          if allowMissingModes:
            logger.warning("Error parsing mode '{}' in '{}' ({})".format(modeName, name, e))
            continue
          else:
            raise
      savePolicy = nameToMSMMSavePolicy(state.resolve_d(cfg, "setter.save", "clearAndSave"))
      current = state.resolve_d(cfg, "setter.current", None)
      report = state.resolve_d(cfg, "setter.report", True)
      modeSetter = ModeSetter(msmm, savePolicy, current, report)
      mode = state.resolve_d(cfg, "mode", None, setter=modeSetter)
      if mode is not None:
        if not modeSink.set_mode(mode):
          logger.warning("Cannot set mode: {}".format(mode))
      #Saving initial mode in msmm afer modeSink was initialized
      msmm.save()
      return modeSink
    except:
      headSink.remove_component("msmm")
      headSink.remove_component("modes")
      raise
  scParser.add("modes", parseMode)

  def parseState(cfg, state):
    sink = StateSink()
    stateCfg = state.resolve(cfg, "state")
    if "next" in stateCfg:
      next = state.get("parser")("sink", stateCfg["next"], state)
      sink.set_next(next)
    if "initialState" in stateCfg:
      sink.set_state(stateCfg["initialState"])
    return sink
  scParser.add("state", parseState)

  def parseValues(cfg, state):
    sink = ValuesSink()
    cfg = state.resolve(cfg, "values")
    for name,value in cfg.items():
      sink.set_value(name, value)
    return sink
  scParser.add("values", parseValues)

  def parseNext(cfg, state):
    parser = state.get("parser")
    r = parser("sink", state.resolve(cfg, "next"), state)
    if r is None:
      #logger.debug("Sink parser could not parse '{}', so trying action parser".format(cfg))
      r = parser("action", state.resolve(cfg, "next"), state)
    return r
  scParser.add("next", parseNext)

  #Actions
  def get_sink(cfg, state):
    """Helper. Retrieves sink from sinks stack by depth or by object name.
       depth: 0 - current component sink, 1 - its parent, etc
    """
    sink = state.resolve_d(cfg, "sink", None)
    if sink is None:
      #logger.debug("Cannot get target sink by '{}'".format(sinkName))
      sink = state.at("sinks", state.resolve_d(cfg, "depth", 0))
    return sink

  def get_component(name, cfg, state):
    """Helper. Retrieves component by depth or by object name.
       depth: 0 - current component sink, 1 - its parent, etc
    """
    sink = get_sink(cfg, state)
    component = sink.get_component(name)
    if component is None:
      raise RuntimeError("No component '{}' in '{}', available components are: {}".format(name, sink, sink.components_.keys()))
    return component

  def actionParserKeyOp(cfg, state):
    key = get_nested_d(cfg, "action", None)
    if key is None:
      key = get_nested_d(cfg, "type", None)
    return key
  actionParser = make_double_deref_parser(keyOp=actionParserKeyOp)
  mainParser.add("action", actionParser)

  actionParser.add("saveMode", lambda cfg, state : get_component("msmm", cfg, state).make_save())
  actionParser.add("restoreMode", lambda cfg, state : get_component("msmm", cfg, state).make_restore(state.resolve_d(cfg, "report", True)))
  actionParser.add("addMode", lambda cfg, state : get_component("msmm", cfg, state).make_add(state.resolve(cfg, "mode"), state.resolve_d(cfg, "current"), get_nested_d(cfg, "report", True)))
  actionParser.add("removeMode", lambda cfg, state : get_component("msmm", cfg, state).make_remove(state.resolve(cfg, "mode"), state.resolve_d(cfg, "current"), get_nested_d(cfg, "report", True)))
  actionParser.add("swapMode", lambda cfg, state : get_component("msmm", cfg, state).make_swap(state.resolve(cfg, "f"), state.resolve(cfg, "t"), state.resolve_d(cfg, "current", None), state.resolve_d(cfg, "report", True)))
  actionParser.add("cycleSwapMode", lambda cfg, state : get_component("msmm", cfg, state).make_cycle_swap(state.resolve(cfg, "modes"), state.resolve_d(cfg, "current"), get_nested_d(cfg, "report", True)))
  actionParser.add("clearMode", lambda cfg, state : get_component("msmm", cfg, state).make_clear())
  actionParser.add("setMode", lambda cfg, state : get_component("msmm", cfg, state).make_set(state.resolve(cfg, "mode"), nameToMSMMSavePolicy(state.resolve_d(cfg, "savePolicy", "noop")), state.resolve_d(cfg, "current"), get_nested_d(cfg, "report", True)))
  actionParser.add("cycleMode", lambda cfg, state : get_component("msmm", cfg, state).make_cycle(state.resolve(cfg, "modes"), state.resolve_d(cfg, "step", 1), state.resolve_d(cfg, "loop", True), nameToMSMMSavePolicy(state.resolve_d(cfg, "savePolicy", "noop")), state.resolve_d(cfg, "report", True)))

  def parseSetState(cfg, state):
    s = state.resolve(cfg, "state")
    return SetState(get_component("state", cfg, state), s)
  actionParser.add("setState", parseSetState)

  def parseToggleState(cfg, state):
    return ToggleState(get_component("state", cfg, state))
  actionParser.add("toggleState", parseToggleState)

  def parseSetSens(cfg, state):
    try:
      htc = fn2htc(state.resolve(cfg, "axis"))
      value = state.resolve(cfg, "value")
      scaleSink = get_component("sens", cfg, state)
      def op(e):
        scaleSink.set_sens(htc, value)
        name = scaleSink.get_name()
        logger.info("{}: {} sens is now {}".format(name, htc2fn(htc.source, htc.type, htc.code), scaleSink.get_sens(htc)))
      return op
    except Exception as e:
      logger.error(e)
      raise
  actionParser.add("setSens", parseSetSens)

  def parseChangeSens(cfg, state):
    try:
      htc = fn2htc(state.resolve(cfg, "axis"))
      delta = state.resolve(cfg, "delta")
      scaleSink = get_component("sens", cfg, state)
      def op(e):
        sens = scaleSink.get_sens(htc)
        sens += delta
        scaleSink.set_sens(htc, sens)
        name = scaleSink.get_name()
        logger.info("{}: {} sens is now {}".format(name, htc2fn(htc.source, htc.type, htc.code), scaleSink.get_sens(htc)))
      return op
    except Exception as e:
      logger.error(e)
      raise
  actionParser.add("changeSens", parseChangeSens)

  def parseMove(cfg, state):
    class FactorSetter:
      def __call__(self, factor):
        self.mc_.set_factor(factor)
      def __init__(self, mc):
        self.mc_ = mc
    curve = state.get("parser")("curve", cfg, state)
    mc = MoveCurve(curve)
    factor = state.resolve_d(cfg, "factor", 1.0, setter=FactorSetter(mc))
    mc.set_factor(factor)
    return mc
  actionParser.add("move", parseMove)

  def parseMoveOneOf(cfg, state):
    axesData = state.resolve(cfg, "axes")
    curves = {}
    for fnInputAxis,curveCfg in axesData.items():
      curve = state.get("parser")("curve", curveCfg, state)
      curves[fn2hc(state.deref(fnInputAxis))] = curve
    op = None
    if state.resolve(cfg, "op") == "min":
      op = MCSCmpOp(cmp = lambda new,old : new < old)
    elif state.resolve(cfg, "op") == "max":
      op = MCSCmpOp(cmp = lambda new,old : new > old)
    elif state.resolve(cfg, "op") == "thresholds":
      op = MCSThresholdOp(thresholds = {fn2hc(state.deref(fnInputAxis)):state.deref(threshold) for fnInputAxis,threshold in state.resolve(cfg, "thresholds").items()})
    else:
      raise Exception("parseMoveOneOf(): Unknown op: {}".format(state.resolve(cfg, "op")))
    mcs = MultiCurveSink(curves, op)
    state.get("main").get("updated").append(lambda tick,ts : mcs.update(tick, ts))
    return mcs
  actionParser.add("moveOneOf", parseMoveOneOf)

  def parseSetAxis(cfg, state):
    axis = state.get_axis_by_full_name(state.resolve(cfg, "axis"))
    class ValueSetter:
      def __call__(self, value):
        if self.moveAxis_ is not None:
          self.moveAxis_.set_value(value)
      def set_move_axis(self, moveAxis):
        self.moveAxis_ = moveAxis
      def __init__(self, moveAxis=None):
        self.moveAxis_ = moveAxis
    valueSetter = ValueSetter()
    value = float(state.resolve(cfg, "value", setter=valueSetter))
    relative = state.resolve_d(cfg, "relative", False)
    stopAt = state.resolve_d(cfg, "stopAt", None)
    r = MoveAxis(axis, value, relative, stopAt)
    valueSetter.set_move_axis(r)
    return r
  actionParser.add("setAxis", parseSetAxis)

  def parseMoveAxisByEvent(cfg, state):
    axis = state.get_axis_by_full_name(state.resolve(cfg, "axis"))
    r = MoveAxisByEvent(axis)
    return r
  actionParser.add("moveAxisByEvent", parseMoveAxisByEvent)

  def parseSetAxes(cfg, state):
    axesAndValues = state.resolve(cfg, "axesAndValues")
    allRelative = state.resolve_d(cfg, "relative", False)
    #logger.debug("parseSetAxes(): {}".format(axesAndValues))
    assert(type(axesAndValues) in (dict, collections.OrderedDict))
    axesAndValues = axesAndValues.items()
    #logger.debug("parseSetAxes(): {}".format(axesAndValues))
    av = []
    for axisData in axesAndValues:
      fnAxis, value, relative = axisData[0], axisData[1], allRelative
      if type(value) in (tuple, list):
        assert(len(value) >= 2)
        value, relative = value[0], value[1]
      axis = state.get_axis_by_full_name(state.deref(fnAxis))
      value = float(state.deref(value))
      relative = state.deref(relative)
      av.append([axis, value, relative])
      #logger.debug("parseSetAxes(): {}, {}, {}".format(fnAxis, axis, value))
    #logger.debug("parseSetAxes(): {}".format(av))
    r = MoveAxes(av)
    return r
  actionParser.add("setAxes", parseSetAxes)

  def parseSetKeyState_(cfg, state, s):
    output, key = fn2sn(state.resolve(cfg, "key"))
    output = state.get("main").get("outputs")[output]
    key = name2code(key)
    return SetButtonState(output, key, s)

  def parseSetKeyState(cfg, state):
    s = int(state.resolve(cfg, "state"))
    return parseSetKeyState_(cfg, state, s)
  actionParser.add("setKeyState", parseSetKeyState)

  def parsePress(cfg, state):
    return parseSetKeyState_(cfg, state, 1)
  actionParser.add("press", parsePress)

  def parseRelease(cfg, state):
    return parseSetKeyState_(cfg, state, 0)
  actionParser.add("release", parseRelease)

  def parseClick(cfg, state):
    output, key = fn2sn(state.resolve(cfg, "key"))
    output = state.get("main").get("outputs")[output]
    key = name2code(key)
    numClicks = int(state.resolve_d(cfg, "numClicks", 1))
    delay = float(state.resolve_d(cfg, "delay", 0.0))
    class Clicker:
      def on_event(self, event):
        if self.delay_ == 0.0:
          for i in range(self.numClicks_):
            for s in (1, 0):
              self.output_.set_button_state(self.key_, s)
        else:
          self.timestamp_ = event.timestamp
          self.s_, self.i_ = 1, self.numClicks_
          self.output_.set_button_state(self.key_, self.s_)
        return True
      def on_update(self, tick, ts):
        if self.i_ == 0:
          return
        if ts - self.timestamp_ > self.delay_:
          self.timestamp_ = ts
          if self.s_ == 1:
            self.s_ = 0
            self.i_ -= 1
          else:
            self.s_ = 1
          self.output_.set_button_state(self.key_, self.s_)
      def __init__(self, output, key, numClicks, delay):
        self.output_, self.key_, self.numClicks_, self.delay_ = output, key, numClicks, delay
        self.timestamp_, self.i_ = None, 0
    clicker = Clicker(output, key, numClicks, delay)
    eventOp = lambda e : clicker.on_event(e)
    updateOp = lambda tick,ts : clicker.on_update(tick, ts)
    state.get("main").get("updated").append(updateOp)
    return eventOp
  actionParser.add("click", parseClick)

  def parseResetCurves(cfg, state):
    curvesToReset = []
    allCurves = state.at("curves", 0)
    assert(allCurves is not None)
    if "axes" in cfg:
      for fnAxis in state.resolve(cfg, "axes"):
        curves = allCurves.get(state.deref(fnAxis), None)
        if curves is None:
          logger.warning("No curves were initialized for '{}' axis (encountered when parsing '{}')".format(fnAxis, str2(cfg)))
        else:
          curvesToReset += curves
    elif "objects" in cfg:
      sink = state.at("sinks", 0)
      for objectName in state.resolve(cfg, "objects"):
        curve = state.get_obj(objectName)
        if curve is None:
          raise RuntimeError("Curve {} not found".format(str2(objectName)))
        curvesToReset.append(curve)
    else:
      raise RuntimeError("Must specify either 'axes' or 'objects' in {}".format(str2(cfg)))
    return ResetCurves(curvesToReset)
  actionParser.add("resetCurves", parseResetCurves)

  def parseSetFunc(cfg, state):
    curve, func = state.resolve(cfg, "curve"), state.resolve(cfg, "func")
    def worker(e):
      curve.set_func(func)
    return worker
  actionParser.add("setFunc", parseSetFunc)

  def parseCycleFuncs(cfg, state):
    curve = state.resolve(cfg, "curve")
    funcs = [state.deref(func) for func in state.resolve(cfg, "funcs")]
    step = state.resolve(cfg, "step")
    def worker(e):
      current = funcs.index(curve.get_func())
      n = clamp(current + step, 0, len(funcs) - 1)
      if n != current:
        curve.set_func(funcs[n])
        logger.info("Setting func {}".format(n))
    return worker
  actionParser.add("cycleFuncs", parseCycleFuncs)

  def parseUpdatePose(cfg, state):
    poseName = state.resolve(cfg, "pose")
    poseManager = state.get("main").get("poseManager")
    return UpdatePose(poseManager, poseName)
  actionParser.add("updatePose", parseUpdatePose)

  def parseUpdatePoses(cfg, state):
    poseNames = state.resolve(cfg, "poses")
    poseManager = state.get("main").get("poseManager")
    def op(event):
      return poseManager.update_poses(poseNames)
    return op
  actionParser.add("updatePoses", parseUpdatePoses)

  def parsePoseTo(cfg, state):
    poseName = state.resolve(cfg, "pose")
    poseManager = state.get("main").get("poseManager")
    return PoseTo(poseManager, poseName)
  actionParser.add("poseTo", parsePoseTo)

  def parseApplyPose(cfg, state):
    poseName = state.resolve(cfg, "pose")
    poseManager = state.get("main").get("poseManager")
    def op(event):
      return poseManager.apply_pose(poseName)
    return op
  actionParser.add("applyPose", parseApplyPose)

  def parseApplyPoses(cfg, state):
    poseNames = state.resolve(cfg, "poses")
    poseManager = state.get("main").get("poseManager")
    def op(event):
      return poseManager.apply_poses(poseNames)
    return op
  actionParser.add("applyPoses", parseApplyPoses)

  def parseMergePose(cfg, state):
    frmPoseName, toPoseName  = state.resolve(cfg, "from"), state.resolve(cfg, "to")
    poseManager = state.get("main").get("poseManager")
    return MergePose(poseManager, frmPoseName, toPoseName)
  actionParser.add("mergePose", parseMergePose)

  def parseIncPoseCount(cfg, state):
    poseName = state.resolve(cfg, "pose")
    poseTracker = state.get("main").get("poseTracker")
    return lambda e : poseTracker.inc(poseName)
  actionParser.add("incPoseCount", parseIncPoseCount)

  def parseDecPoseCount(cfg, state):
    poseName = state.resolve(cfg, "pose")
    poseTracker = state.get("main").get("poseTracker")
    return lambda e : poseTracker.dec(poseName)
  actionParser.add("decPoseCount", parseDecPoseCount)

  def parseResetPoseCount(cfg, state):
    poseName = state.resolve(cfg, "pose")
    poseTracker = state.get("main").get("poseTracker")
    return lambda e : poseTracker.reset(poseName)
  actionParser.add("resetPoseCount", parseResetPoseCount)

  def parseWritePoses(cfg, state):
    main = state.get("main")
    poseManager = main.get("poseManager")
    fileName = state.resolve(cfg, "file")
    update = state.resolve_d(cfg, "update", False)
    poseNamesToWrite = state.resolve_d(cfg, "poses", None)
    def op(e):
      posesToWrite = None
      if poseNamesToWrite is None:
        posesToWrite = poseManager.get_poses()
      else:
        posesToWrite = { poseName : poseManager.get_pose(poseName) for poseName in poseNamesToWrite }
      poseValuesToWrite = {}
      for poseName,pose in posesToWrite.items():
        poseValuesToWrite[poseName] = { main.get_full_name_by_axis(axis) : value for axis,value in pose }
      posesCfg = {"poses" : poseValuesToWrite}
      if update == True:
        try:
          with open(fileName, "r") as f:
            oldPosesCfg = json.load(f, object_pairs_hook = lambda l : collections.OrderedDict(l))
            merge_dicts(oldPosesCfg, posesCfg)
            posesCfg = oldPosesCfg
        except IOError as e:
          logger.debug("Cannot open poses file {}".format(fileName))
        except ValueError as e:
          logger.warning("Cannot decode poses file {}".format(fileName))
      with open(fileName, "w") as f:
        json.dump(posesCfg, f, indent=2)
      return True
    return op
  actionParser.add("writePoses", parseWritePoses)

  def parsePlaySound(cfg, state):
    main = state.get("main")
    soundPlayer = main.get("soundPlayer")
    soundName = state.resolve(cfg, "sound")
    soundFileName = state.get("main").get("sounds").get(soundName, None)
    if soundFileName is None:
      raise RuntimeError("Sound '{}' is not registered".format(soundName))
    def op(e):
      soundPlayer.queue(soundFileName)
    return op
  actionParser.add("playSound", parsePlaySound)

  def parsePrintVar(cfg, state):
    varName = state.resolve(cfg, "varName")
    level = name2loglevel(state.resolve_d(cfg, "level", "INFO"))
    key = state.resolve_d(cfg, "key", None)
    var = state.get("main").get("varManager").get_var(varName)
    def op(e):
      value = var.get()
      if key is not None and type(value) in (dict, collections.OrderedDict):
        value = value[key]
      logger.log(level, "{} is {}".format(varName, str2(value)))
      return True
    return op
  actionParser.add("printVar", parsePrintVar)

  def parseSetVar(cfg, state):
    varName = state.resolve(cfg, "varName")
    level = name2loglevel(state.resolve_d(cfg, "level", "INFO"))
    value = state.resolve(cfg, "value")
    key = state.resolve_d(cfg, "key", None)
    var = state.get("main").get("varManager").get_var(varName)
    def op(e):
      v = None
      if key is not None and type(value) in (dict, collections.OrderedDict):
        v = var.get()
        v[key] = value
      else:
        v = value
      var.set(v)
      logger.log(level, "{} is now {}".format(varName, str2(value)))
      return True
    return op
  actionParser.add("setVar", parseSetVar)

  def parseChangeVar(cfg, state):
    varName = state.resolve(cfg, "varName")
    delta = state.resolve(cfg, "delta")
    key = state.resolve_d(cfg, "key", None)
    var = state.get("main").get("varManager").get_var(varName)
    def op(e):
      value = var.get()
      v = None
      if key is not None and type(value) in (dict, collections.OrderedDict):
        v = value[key]
        v += delta
        value[key] = v
      else:
        value += delta
        v = value
      var.set(value)
      logger.info("{} is now {}".format(varName, str2(v)))
      return True
    return op
  actionParser.add("changeVar", parseChangeVar)

  def parseCycleVars(cfg, state):
    varName = state.resolve(cfg, "varName")
    var = state.get("main").get("varManager").get_var(varName)
    values = [state.deref(value) for value in state.resolve(cfg, "values")]
    step = state.resolve(cfg, "step")
    def op(e):
      current = values.index(var.get())
      n = clamp(current + step, 0, len(values) - 1)
      if n != current:
        v = values[n]
        var.set(v)
        logger.info("Setting var {} to {}".format(varName, v))
    return op
  actionParser.add("cycleVars", parseCycleVars)

  def parseWriteVars(cfg, state):
    def replace_var_with_value(cfg):
      r = collections.OrderedDict()
      for name,value in cfg.items():
        if type(value) in (dict, collections.OrderedDict):
          r[name] = replace_var_with_value(value)
        else:
          r[name] = value.get()
      return r
    fileName = state.resolve(cfg, "file")
    groupName = state.resolve_d(cfg, "group", None)
    def op(e):
      varsCfg = state.get("main").get("varManager").get_vars()
      if groupName is not None:
        varsCfg = { groupName : varsCfg.get(groupName) }
      varsCfg = replace_var_with_value(varsCfg)
      varsCfg = { "vars" : varsCfg }
      with open(fileName, "w") as f:
        json.dump(varsCfg, f, indent=2)
        logger.info("Vars written to {}".format(fileName))
      return True
    return op
  actionParser.add("writeVars", parseWriteVars)

  def parseSetStateOnInit(cfg, state):
    linker = state.get("parser")("curve", cfg, state)
    return SetAxisLinkerState(linker)
  actionParser.add("setStateOnInit", parseSetStateOnInit)

  def parseSetOffset(cfg, state):
    curve = state.resolve(cfg, "object")
    offset = state.resolve(cfg, "offset")
    def op(event):
      curve.set_offset(offset)
      return True
    return op
  actionParser.add("setOffset", parseSetOffset)

  def parseSetObjectState(cfg, state):
    obj = state.resolve(cfg, "object")
    if obj is None:
      raise RuntimeError("Cannot get object by '{}'".format(get_nested(cfg, "object")))
    return SetState(obj, state.resolve(cfg, "state"))
  actionParser.add("setObjectState", parseSetObjectState)

  def parseEmitCustomEvent(cfg, state):
    etype = state.resolve_d(cfg, "etype", None)
    etype = codes.EV_CUSTOM if etype is None else name2code(etype)
    code, value = int(state.resolve_d(cfg, "code", 0)), get_nested_d(cfg, "value")
    sink = get_sink(cfg, state)
    if sink is None:
      raise RuntimeError("Cannot find target sink")
    def callback(e):
      event = Event(etype, code, value)
      return sink(event)
    return callback
  actionParser.add("emit", parseEmitCustomEvent)

  def parseForwardEvent(cfg, state):
    sink = get_sink(cfg, state)
    if sink is None:
      raise RuntimeError("Cannot find target sink")
    def callback(e):
      return sink(e)
    return callback
  actionParser.add("forward", parseForwardEvent)

  def parseLog(cfg, state):
    message, level = state.resolve(cfg, "message"), state.resolve(cfg, "level")
    def callback(e):
      logger.log(name2loglevel(level), message)
      return True
    return callback
  actionParser.add("log", parseLog)

  def parseLogEvent(cfg, state):
    levelName = state.resolve_d(cfg, "level", "INFO")
    level = name2loglevel(levelName)
    def callback(e):
      logger.log(level, str2(e))
      return True
    return callback
  actionParser.add("logEvent", parseLogEvent)

  def parseSetValueItem(cfg, state):
    value = state.resolve(cfg, "name")
    i = state.resolve(cfg, "item")
    v = state.resolve(cfg, "value")
    values = get_component("values", cfg, state)
    def callback(e):
      values.set_value_item(value, i, v)
      return True
    return callback
  actionParser.add("setValueItem", parseSetValueItem)

  def parseSetValue(cfg, state):
    value = state.resolve(cfg, "name")
    v = state.resolve(cfg, "value")
    values = get_component("values", cfg, state)
    def callback(e):
      values.set_value(value, v)
      return True
    return callback
  actionParser.add("setValue", parseSetValue)

  #Event types
  def etParserKeyOp(cfg, state):
    key = get_nested_d(cfg, "et", None)
    if key is None:
      key = get_nested_d(cfg, "type", None)
    if key is None:
      raise RuntimeError("Was expecting either \"et\" or \"type\" keys in {}".format(str2(cfg)))
    return key
  etParser = make_double_deref_parser(keyOp=etParserKeyOp)
  mainParser.add("et", etParser)

  def make_et(f):
    def op(cfg, state):
      """Appends a list of modifierDescs to r if modifiers are specified in cfg."""
      r = f(cfg, state)
      modifiers = state.resolve_d(cfg, "modifiers", None)
      if modifiers is not None and modifiers != "any":
        modifiers = [parse_modifier_desc(m, state) for m in modifiers]
        r.append(("modifiers", ModifiersPropTest(modifiers)))
      return PropTestsEventTest(r)
    return op

  def parseKey_(cfg, state, value):
    """Helper"""
    sourceHash, eventType, key = fn2htc(state.resolve(cfg, "key"))
    r = [("type", EqPropTest(eventType)), ("code", EqPropTest(key)), ("value", EqPropTest(value))]
    if sourceHash is not None:
      r.append(("source", EqPropTest(sourceHash)))
    return r

  @make_et
  def parseAny(cfg, state):
    return []
  etParser.add("any", parseAny)

  @make_et
  def parsePress(cfg, state):
    return parseKey_(cfg, state, 1)
  etParser.add("press", parsePress)

  @make_et
  def parseRelease(cfg, state):
    return parseKey_(cfg, state, 0)
  etParser.add("release", parseRelease)

  @make_et
  def parseClick(cfg, state):
    r = parseKey_(cfg, state, 3)
    r.append(("num_clicks", EqPropTest(1)))
    return r
  etParser.add("click", parseClick)

  @make_et
  def parseDoubleClick(cfg, state):
    r = parseKey_(cfg, state, 3)
    r.append(("num_clicks", EqPropTest(2)))
    return r
  etParser.add("doubleclick", parseDoubleClick)

  @make_et
  def parseMultiClick(cfg, state):
    r = parseKey_(cfg, state, 3)
    num = int(state.resolve(cfg, "numClicks"))
    r.append(("num_clicks", EqPropTest(num)))
    return r
  etParser.add("multiclick", parseMultiClick)

  @make_et
  def parseHold(cfg, state):
    r = parseKey_(cfg, state, state.resolve_d(cfg, "value", 4))
    holdTime = state.resolve_d(cfg, "heldTime", None)
    if holdTime is not None:
      holdTime = float(holdTime)
      r.append(("heldTime", CmpPropTest(holdTime, lambda ev,v : ev >= v)))
    return r
  etParser.add("hold", parseHold)

  @make_et
  def parseMove(cfg, state):
    sourceHash, eventType, axis = fn2htc(state.resolve(cfg, "axis"))
    r = [("type", EqPropTest(eventType)), ("code", EqPropTest(axis))]
    if sourceHash is not None:
      r.append(("source", EqPropTest(sourceHash)))
    value = get_nested_d(cfg, "value")
    if value is not None:
      gt = lambda eventValue, attrValue : cmp(eventValue, attrValue) > 0
      lt = lambda eventValue, attrValue : cmp(eventValue, attrValue) < 0
      eq = lambda eventValue, attrValue : cmp(eventValue, attrValue) == 0
      op = None
      if value == "+":
        op = gt
        value = 0.0
      elif value == "-":
        op = lt
        value = 0.0
      elif value[0] == ">":
        op = gt
        value = float(value[1:])
      elif value[0] == "<":
        op = lt
        value = float(value[1:])
      else:
        op = eq
        value = float(value)
      r.append(("value", CmpPropTest(value, op)))
    return r
  etParser.add("move", parseMove)

  @make_et
  def parseInit(cfg, state):
    r = [("type", EqPropTest(codes.EV_BCT)), ("code", EqPropTest(codes.BCT_INIT))]
    eventName = state.resolve_d(cfg, "event")
    if eventName is not None:
      value = 1 if eventName == "enter" else 0 if eventName == "leave" else None
      assert(value is not None)
      r.append(("value", EqPropTest(value)))
    other = state.resolve_d(cfg, "other")
    if other is not None:
      r.append("other", EqInPropTest(other))
    return r
  etParser.add("init", parseInit)

  def parseValue(cfg, state):
    r = [("type", EqPropTest(codes.EV_BCT)), ("code", EqPropTest(codes.BCT_VALUE))]
    name = state.resolve_d(cfg, "name")
    if name is not None:
      r.append(("name", EqPropTest(name)))
    value = state.resolve_d(cfg, "value")
    if value is not None:
      item = state.resolve_d(cfg, "item")
      if item is not None:
        r.append(("value", ItemEqPropTest(value, item)))
      else:
        r.append(("value", EqPropTest(value)))
    return PropTestsEventTest(r)
  etParser.add("value", parseValue)

  @make_et
  def parseEvent(cfg, state):
    propValue = state.resolve_d(cfg, "etype", None)
    propValue = codes.EV_CUSTOM if propValue is None else name2code(propValue)
    r = [("type", EqPropTest(propValue))]
    def eq(ev, pv):
      return ev == pv
    def eq_dict(ev, pv):
      dicts = (dict, collections.OrderedDict,)
      if type(ev) in dicts and type(pv) in dicts:
        for n,v in pv.items():
          vv = ev.get(n, None)
          if not eq_dict(vv, v):
            return False
        return True
      else:
        return eq(ev, pv)
    for p in  (
      ("source", get_source_hash, eq),
      ("code", lambda x : name2code(x) if type(x) in (str, unicode) else x, eq),
      ("value", lambda x : x, eq_dict)
    ):
      propName, propOp = p[0], p[1]
      propValue = state.resolve_d(cfg, propName, None)
      if propValue is not None:
        propValue = propOp(propValue)
        r.append((propName, CmpPropTest(propValue, eq_dict)))
    return r
  etParser.add("event", parseEvent)

  def parseSequence(cfg, state):
    class SequenceTest:
      def __call__(self, event):
        for op in self.resetOn_:
          if op(event) == True:
            self.i_ = 0
            return False
        t = self.inputs_[self.i_](event)
        if t == True:
          self.i_ += 1
          if self.i_ == len(self.inputs_):
            self.i_ = 0
            return True
        return False
      __slots__ = ("inputs_", "resetOn_", "i_")
      def __init__(self, inputs, resetOn=[lambda event : False]):
        self.inputs_, self.resetOn_ = inputs, resetOn
        self.i_ = 0
    inputs = state.resolve(cfg, "ets")
    inputs = [etParser(inpt, state) for inpt in inputs]
    resetOn = state.resolve_d(cfg, "resetOn", [])
    resetOn = [etParser(rst, state) for rst in resetOn]
    return SequenceTest(inputs, resetOn)
  etParser.add("sequence", parseSequence)

  def parseBinds(cfg, state):
    def parseOnsDos(cfg, state):
      def parseGroup(name, parser, cfg, state):
        cfgs = cfg.get(name, None)
        tcfgs = type(cfgs)
        if tcfgs in (list, tuple):
          pass
        elif tcfgs in (dict, collections.OrderedDict):
          cfgs = (cfgs,)
        else:
          raise RuntimeError("'{}' in must be a dictionary or a list of dictionaries, got {} (encountered when parsing {})".format(name, tcfgs, str2(cfg, 100)))
        r, t = [], None
        for c in cfgs:
          try:
            t = parser(c, state)
          except RuntimeError as e:
            logger.warning("{} (encountered when parsing {} '{}')".format(e, name, str2(c, 100)))
            continue
          except Exception as e:
            logger.error("{} (encountered when parsing {} '{}')".format(e, name, str2(c, 200)))
            raise ParserError(c)
          if t is None:
            logger.warning("Could not parse {} '{}')".format(name, str2(c, 100)))
            continue
          r.append(t)
        return r

      def parseActionOrSink(cfg, state):
        mainParser = state.get("parser")
        try:
          return mainParser("action", cfg, state)
        except ParserNotFoundError:
          #logger.debug("Action parser could not parse '{}', so trying sink parser".format(str2(cfg)))
          return mainParser("sink", cfg, state)

      mainParser = state.get("parser")
      ons = parseGroup("on", mainParser.get("et"), cfg, state)
      if len(ons) == 0:
        logger.warning("No 'on' instances were constructed (encountered when parsing '{}')".format(str2(cfg, 100)))

      dos = parseGroup("do", parseActionOrSink, cfg, state)
      if len(dos) == 0:
        logger.warning("No 'do' instances were constructed (encountered when parsing '{}')".format(str2(cfg, 100)))

      return ((on,do) for on in ons for do in dos)

    binds = state.resolve_d(cfg, "binds", [])
    #logger.debug("binds: {}".format(binds))
    #sorting binds so actions that reset curves are initialized after these curves were actually initialized
    def bindsKey(b):
      def checkDo(o):
        if type(o) in (dict, collections.OrderedDict):
          actionName = o.get("action", o.get("type", None))
          if actionName in ("resetCurve", "resetCurves"):
            return 10
        else:
          return 0
      r = 0
      do = b.get("output", b.get("do", None))
      if type(do) is list:
        for d in do:
          r = max(r, checkDo(d))
      else:
        r = checkDo(do)
      return r
    binds.sort(key=bindsKey)
    bindingSink = BindSink()
    for bind in binds:
      for on,do in parseOnsDos(bind, state):
        bindingSink.add(on, do, state.resolve_d(bind, "level", 0), state.resolve_d(bind, "name", None))
    return bindingSink

  scParser.add("binds", parseBinds)

  def outputParserKeyOp(cfg, state):
    key = get_nested_d(cfg, "output", None)
    if key is None:
      key = get_nested_d(cfg, "type", None)
    if key is None:
      raise RuntimeError("Was expecting either \"output\" or \"type\" keys in {}".format(str2(cfg)))
    return key
  outputParser = make_double_deref_parser(keyOp=outputParserKeyOp)
  mainParser.add("output", outputParser)

  def get_or_make_output(name, state):
    main = state.get("main")
    outputs = main.get("outputs")
    config = main.get("config")
    j = outputs.get(name, None)
    if j is None:
      outputsCfg = state.resolve_d(config, "outputs", None)
      if outputsCfg is None:
        raise RuntimeError("Cannot find 'outputs' section in configs")
      outputCfg = state.resolve_d(outputsCfg, name, None)
      if outputCfg is None:
        raise RuntimeError("Cannot find section for output '{}' in configs".format(name))
      j = state.get("parser")("output", outputCfg, state)
      outputs[name] = j
    assert name in main.get("outputs")
    return j

  @make_reporting_joystick
  def parseNullJoystickOutput(cfg, state):
    values = get_nested_d(cfg, "values")
    if values is not None:
      values = {fn2tc(n) : v for n,v in values.items()}
    limits = get_nested_d(cfg, "limits")
    if limits is not None:
      limits = {fn2tc(n) : v for n,v in limits.items()}
    j = NullJoystick(values=values, limits=limits)
    return j
  outputParser.add("null", parseNullJoystickOutput)

  def parseExternalOutput(cfg, state):
    name = state.resolve(cfg, "name")
    return get_or_make_output(name, state)
  outputParser.add("external", parseExternalOutput)

  @make_reporting_joystick
  def parseRateLimitOutput(cfg, state):
    rates = {fn2tc(nAxis):value for nAxis,value in state.resolve(cfg, "rates").items()}
    next = state.get("parser")("output", state.resolve(cfg, "next"), state)
    j = RateLimititngJoystick(next, rates)
    state.get("main").get("updated").append(lambda tick,ts : j.update(tick))
    return j
  outputParser.add("rateLimit", parseRateLimitOutput)

  @make_reporting_joystick
  def parseRateSettingOutput(cfg, state):
    class TimeRateOp:
      def calc(self, value, timestamp):
        if value != self.value_ or self.timestamp_ is None:
          self.value_, self.timestamp_ = value, timestamp
        if self.next_ is not None:
          value = self.next_.calc(value, timestamp)
        dt = timestamp - self.timestamp_
        return value * self.func_(dt)
      def __init__(self, next, func):
        self.value_, self.timestamp_ = 0.0, None
        self.next_, self.func_ = next, func
    class AxisRateOp:
      def calc(self, value, timestamp):
        if self.next_ is not None:
          value = self.next_.calc(value, timestamp)
        return value * self.func_(self.axis_.get())
      def __init__(self, next, axis, func):
        self.next_, self.axis_, self.func_ = next, axis, func
    class ConstantRateOp:
      def calc(self, value, timestamp):
        return value * self.rate_
      def init(self, rate):
        self.rate_ = rate
    limits = {fn2tc(nAxis):value for nAxis,value in state.resolve(cfg, "limits").items()}
    next = state.get("parser")("output", state.resolve(cfg, "next"), state)
    rateOps = {}
    ratesCfg = state.resolve(cfg, "rates")
    for nAxis,rateOrCfg in ratesCfg.items():
      rateOp = None
      if type(rateOrCfg) in (int, float):
        rateOp = ConstantRateOp(rateOrCfg)
      else:
        for opCfg in rateOrCfg:
          t = state.resolve(opCfg, "type")
          if t == "time":
            func = state.get("parser")("func", state.resolve(opCfg, "func"), state)
            rateOp = TimeRateOp(rateOp, func)
          elif t == "axis":
            axis = state.get_axis_by_full_name(state.resolve(opCfg, "axis"))
            func = state.get("parser")("func", state.resolve(opCfg, "func"), state)
            rateOp = AxisRateOp(rateOp, axis, func)
          else:
            raise RuntimeError("Unknown op type : '{}'".format(t))
      tcAxis = fn2tc(nAxis)
      rateOps[tcAxis] = rateOp
    j = RateSettingJoystick(next, rateOps, limits)
    state.get("main").get("updated").append(lambda tick,ts : j.update(tick, ts))
    return j
  outputParser.add("rateSet", parseRateSettingOutput)

  @make_reporting_joystick
  def parseRelativeOutput(cfg, state):
    next = state.get("parser")("output", state.resolve(cfg, "next"), state)
    j = RelativeHeadMovementJoystick(next=next, r=state.resolve_d(cfg, "clampRadius", float("inf")), stick=state.resolve_d(cfg, "stick", True))
    return j
  outputParser.add("relative", parseRelativeOutput)

  @make_reporting_joystick
  def parseCompositeOutput(cfg, state):
    parser = state.get("parser").get("output")
    children = parse_list(state.resolve(cfg, "children"), state, parser)
    checkChild = state.resolve(cfg, "checkChild")
    union = state.resolve(cfg, "union")
    j = CompositeJoystick(children=children, checkChild=checkChild, union=union)
    return j
  outputParser.add("composite", parseCompositeOutput)

  @make_reporting_joystick
  def parseMappingOutput(cfg, state):
    outputs = state.get("main").get("outputs")
    j = MappingJoystick()
    for fromAxis,to in state.resolve_d(cfg, "axisMapping", {}).items():
      toJoystick, toAxis = fn2sc(state.resolve(to, "to"))
      toJoystick = get_or_make_output(toJoystick, state)
      factor = state.resolve_d(to, "factor", 1.0)
      j.add_axis(fn2tc(fromAxis), toJoystick, toAxis, factor)
    for fromButton,to in state.resolve_d(cfg, "buttonMapping", {}).items():
      toJoystick, toButton = fn2sc(state.resolve(to, "to"))
      toJoystick = get_or_make_output(toJoystick, state)
      negate = state.resolve_d(to, "negate", False)
      j.add_button(name2code(fromButton), toJoystick, toButton, negate)
    return j
  outputParser.add("mapping", parseMappingOutput)

  @make_reporting_joystick
  def parseOpentrackOutput(cfg, state):
    j = Opentrack(state.resolve(cfg, "ip"), int(state.resolve(cfg, "port")))
    state.get("main").get("updated").append(lambda tick,ts : j.send())
    return j
  outputParser.add("opentrack", parseOpentrackOutput)

  @make_reporting_joystick
  def parseUdpJoystickOutput(cfg, state):
    packetMakers = {
      "il2" : make_il2_packet,
      "il2_6dof" : make_il2_6dof_packet,
      "opentrack" : make_opentrack_packet
    }
    j = UdpJoystick(state.resolve(cfg, "ip"), int(state.resolve(cfg, "port")), packetMakers[state.resolve(cfg, "format")], int(state.resolve_d(cfg, "numPackets", 1)))
    for nAxis,l in state.resolve_d(cfg, "limits", {}).items():
      j.set_limits(fn2tc(nAxis), l)
    state.get("main").get("updated").append(lambda tick,ts : j.send())
    return j
  outputParser.add("udpJoystick", parseUdpJoystickOutput)

  def parsePose(cfg, state):
    main = state.get("main")
    pose = []
    for fnAxis,value in cfg.items():
      axis = main.get_axis_by_full_name(fnAxis)
      pose.append((axis, value))
    return pose
  mainParser.add("pose", parsePose)

  def parseVar(cfg, state):
    return state.deref(cfg, asValue=False)
  mainParser.add("var", parseVar)

  def parseNVar(cfg, state):
    return Var(cfg)
  mainParser.add("nvar", parseNVar)

  trackerParserKeyOp=lambda cfg,state : get_nested(cfg, "tracker")
  trackerParser = make_double_deref_parser(keyOp=trackerParserKeyOp)
  mainParser.add("tracker", trackerParser)

  def parseConsoleTracker(cfg, state):
    fmt = state.resolve(cfg, "fmt")
    level = name2loglevel(state.resolve_d(cfg, "level", "INFO"))
    def op(values):
      msg = fmt.format(values)
      logger.log(level, msg)
    return GainTracker(op)
  trackerParser.add("console", parseConsoleTracker)

  def parseValueTracker(cfg, state):
    valueName = state.resolve(cfg, "value")
    value = state.get("main").get("valueManager").get_var(valueName)
    if value is None:
      raise RuntimeError("No such value: '{}'".format(valueName))
    def op(values):
      value.set(values)
    return GainTracker(op)
  trackerParser.add("value", parseValueTracker)

  return mainParser


class SoundPlayer:
  def queue(self, soundFileName):
    with self.cv_:
      self.q_.append(soundFileName)
      self.cv_.notify_all()

  def __call__(self):
    while True:
      soundFileName = None
      with self.cv_:
        while len(self.q_) == 0 and not self.quit_:
          self.cv_.wait()
        if self.quit_:
          return
        else:
          soundFileName = self.q_[0]
          del self.q_[0]
      playsound.playsound(soundFileName, True)

  def __init__(self):
    self.q_ = []
    self.quit_ = False
    self.cv_ = threading.Condition(threading.RLock())
    self.thread_ = threading.Thread(target=self)
    self.thread_.start()

  def quit(self):
    with self.cv_:
      self.quit_ = True
      self.cv_.notify_all()
    self.thread_.join()


class BaseVar:
  def get(self):
    pass

  def add_callback(self, callback):
    pass


class MappingVar(BaseVar):
  def get(self):
    return self.map_(self.var_.get())

  def __call__(self, v):
    mv = self.map_(v)
    for cb in self.callbacks_:
      cb(mv)

  def add_callback(self, callback):
    self.callbacks_.append(callback)

  def __init__(self, var, mapping):
    self.callbacks_ = []
    self.var_, self.mapping_ = var, mapping
    self.var_.add_callback(self)
    #logger.debug("{} created for var {} and mapping {}".format(self, var, mapping))

  def map_(self, v):
    if self.mapping_ is None:
      return v
    else:
      return self.mapping_(v)


class Var(BaseVar):
  def get(self):
    return self.value_

  def set(self, value):
    if self.validate_ is not None:
      self.validate_(value)
    self.value_ = value
    for cb in self.callbacks_:
      cb(value)

  def add_callback(self, callback):
    self.callbacks_.append(callback)

  def __init__(self, value, validate=None):
    self.value_ = value
    self.validate_ = validate
    self.callbacks_ = []


class VarManager:
  def get_var(self, varName):
    var = get_nested_d(self.vars_, varName, None)
    if var is None:
      if self.make_var_ is not None:
        var = self.make_var_()
        set_nested(self.vars_, varName, var)
        assert(get_nested(self.vars_, varName) == var)
      else:
        raise RuntimeError("Var '{}' was not registered".format(varName))
    return var

  def get_vars(self):
    return self.vars_

  def add_var(self, varName, var):
    set_nested(self.vars_, varName, var)

  def __init__(self, make_var = None):
    self.vars_ = collections.OrderedDict()
    self.make_var_ = make_var


class Main:
  def print_help(self):
    print "Usage: " + sys.argv[0] + " args"
    print "args are:\n\
    -h | --help : this message\n\
    -d fileName | --devices=fileName : print input devices to file fileName (- for stdout)\n\
    -p presetName | --preset=presetName : use preset presetName\n\
    -c configFileName | --config=configFileName : use config file configFileName\n\
    -v logLevel | --logLevel=logLevel : set log level to logLevel\n"

  def add_logging_handler(self, logger, handler, level=logging.NOTSET, fmt="%(levelname)s:%(asctime)s:%(message)s", datefmt="%H:%M:%S"):
    if handler is None:
      return
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(fmt=fmt, datefmt=datefmt))
    logger.addHandler(handler)

  def preinit_log(self, level=logging.NOTSET, handler=logging.StreamHandler(sys.stdout), fmt="%(levelname)s:%(asctime)s:%(message)s", datefmt="%H:%M:%S"):
    root = logging.getLogger()
    root.setLevel(level)
    self.add_logging_handler(root, handler, level, fmt, datefmt)

  def init_log(self, state):
    config = self.get("config")
    logLevelName = state.resolve_d(config, "logLevel", "NOTSET").upper()
    logLevel = name2loglevel(logLevelName)
    root = logging.getLogger()
    root.setLevel(logLevel)
    print("Setting global log level to {}".format(logLevelName))
    def parse_logger(logger, config, state):
      childrenCfg = state.resolve_d(config, "children", {})
      for childName,childCfg in childrenCfg.items():
        child = logger.getChild(childName)
        parse_logger(child, childCfg, state)
      for handlerCfg in state.resolve_d(config, "handlers", ()):
        t = state.resolve(handlerCfg, "type")
        name = state.resolve(handlerCfg, "name")
        stream = None
        if t == "stream":
          streams = { "stdout" : sys.stdout, "stderr" : sys.stderr }
          stream = streams.get(name, None)
        elif t == "file":
          stream = open(name, "w")
        if stream is None:
          raise RuntimeError("Cannot create log handler '{}' of type '{}'".format(name, t))
        fmt = state.resolve_d(handlerCfg, "fmt", "%(levelname)s:%(asctime)s:%(message)s")
        datefmt = state.resolve_d(handlerCfg, "datefmt", "%T")
        levelName = state.resolve_d(handlerCfg, "level", "NOTSET").upper()
        level = name2loglevel(levelName)
        handler = logging.StreamHandler(stream)
        self.add_logging_handler(logger, handler, level, fmt, datefmt)
    parse_logger(root, state.resolve_d(config, "logs", {}), state)

  def init_config2(self):
    if self.get("config") is not None and self.get("reloading") == False:
      return
    config = self.options_
    configNames = self.options_.get("configNames", None)
    if configNames is not None:
      externalConfig = init_config(configNames)
      merge_dicts(externalConfig, config)
      config = externalConfig
    self.set("config", config)
    logger.info("Configs loaded successfully")
    self.set("numTraceLines", config.get("numTraceLines", 0))

  def init_outputs(self, state):
    nameParser = lambda key,state : key
    parser = self.get("parser")
    outputParser = parser.get("output")
    orderOp = lambda i : state.resolve_d(i[1], "seq", 100000)
    cfg = state.resolve(self.get("config"), "outputs")
    state = ParserState(self)
    parse_dict_live_ordered(self.get("outputs"), cfg, state=state, kp=nameParser, vp=outputParser, op=orderOp, update=False)

  def init_sounds(self, state):
    soundsCfg = state.resolve_d(self.get("config"), "sounds", {})
    sounds = self.get("sounds")
    for soundName,soundFileName in soundsCfg.items():
      sounds[soundName] = state.deref(soundFileName)

  def init_vars(self, state):
    parser = state.get("main").get("parser")
    varsCfg = self.get("config").get("vars", {})
    varManager = self.get("varManager")
    def add_nested_vars(cfg, tokens):
      sep = "."
      for name,cfg2 in cfg.items():
        tokens.append(name)
        isDict = type(cfg2) in (dict, collections.OrderedDict)
        isValueDict = True if isDict and cfg2.get("_value") else False
        if isValueDict:
          del cfg2["_value"]
        if not isDict or isValueDict:
          varManager.add_var(sep.join(tokens), parser("nvar", cfg2, state))
        else:
          add_nested_vars(cfg2, tokens)
        tokens.pop()
    tokens = []
    add_nested_vars(varsCfg, tokens)

  def init_poses(self, state):
    poseManager = self.get("poseManager")
    poseParser = self.get("parser").get("pose")
    posesCfg = self.get("config").get("poses")
    if posesCfg is not None:
      for poseName,poseCfg in posesCfg.items():
        pose = poseParser(poseCfg, state)
        poseManager.set_pose(poseName, pose)

  def init_source(self, state):
    #TODO Use dedicated config section for source?
    self.set("source", self.get("parser")("source", self.get("config"), state))
    sink = init_main_sink(state, init_preset_config)
    self.get("source").set_sink(sink)

  def init_loop(self, state):
    refreshRate = state.resolve_d(self.get("config"), "refreshRate", 100.0)
    step = 1.0 / refreshRate
    source = self.get("source")
    assert(source is not None)
    def run_source(tick, ts):
      source.run_once()
    updated = self.get("updated")
    def run_updated(tick, ts):
      for u in updated:
        u(tick, ts)
    callbacks = [run_source, run_updated]
    loop = Loop(callbacks, step)
    if self.loop_ is not None:
      del self.loop_
    self.loop_ = loop

  def reinit_or_fallback(self):
    try:
      self.init_config2()
      state = ParserState(self)
      self.init_vars(state)
      self.init_poses(state)
      self.init_source(state)
      self.init_loop(state)
      self.set("reloading", False)
    except Exception as e:
      logger.error("Could not create or recreate loop; reason: '{}'".format(e))
      numTraceLines = self.props_["numTraceLines"]
      if numTraceLines > 0:
        logger.error("===Traceback begin===")
        for l in traceback.format_exc().splitlines()[-numTraceLines:]:
          logger.error(l)
        logger.error("===Traceback end===")
      if self.loop_ is not None:
        logger.error("Falling back to previous state.")
      else:
        raise Exception("No valid state to fall back to.")

  def reinit_and_run(self):
    oldUpdated = [v for v in self.get("updated")]
    try:
      self.reinit_or_fallback()
      assert(self.loop_ is not None)
      self.loop_.run()
    finally:
      self.set("updated", oldUpdated)

  def preinit(self):
    self.preinit_log()
    if (len(sys.argv)) == 1:
      self.print_help()
      raise ExitException

    devicesFileName, escapeDeviceName = None, False

    opts, args = getopt.getopt(sys.argv[1:], "hd:ep:v:c:", ["help", "devices=", "escape", "preset=", "logLevel=", "config="])
    for o, a in opts:
      if o in ("-h", "--help"):
        self.print_help()
        raise ExitException
      elif o in ("-d", "--devices"):
        devicesFileName = a
      elif o in ("-e", "--escape"):
        escapeDeviceName = True
      if o in ("-p", "--preset"):
        self.options_["preset"] = a
      elif o in ("-v", "--logLevel"):
        self.options_["logLevel"] = a
      elif o in ("-c", "--config"):
        cns = self.options_.setdefault("configNames", [])
        cns.append(a)

    if devicesFileName is not None:
        self.print_devices_(devicesFileName, escape=escapeDeviceName)
        raise ExitException

    self.set("reloading", False)
    self.init_config2()
    state = ParserState(self)
    self.init_log(state)
    self.init_outputs(state)
    self.init_sounds(state)

  def run(self):
    try:
      self.preinit()
      while (True):
        try:
          r = self.reinit_and_run()
        except ReloadException:
          logger.info("Reloading")
          self.set("reloading", True)
        except Exception as e:
          logger.error("Unexpected exception: {}".format(e))
          raise
        finally:
          self.get("source").swallow(None, False)

    except KeyboardInterrupt:
      logger.info("Exiting normally")
      return 0
    except ExitException:
      logger.info("Exiting normally")
      return 0
    except ConfigReadError as e:
      logger.error(e)
      return 1
    finally:
      self.get("soundPlayer").quit()


  def get(self, propName):
    if propName not in self.props_:
      raise RuntimeError("Property '{}' not registered".format(propName))
    return self.props_.get(propName)

  def set(self, propName, propValue):
    if propName not in self.props_:
      raise RuntimeError("Property '{}' not registered".format(propName))
    self.props_[propName] = propValue

  def get_axis_by_full_name(self, fnAxis):
    allAxes = self.get("axes")
    outputName, tAxis, cAxis = fn2stc(fnAxis)
    tcAxis = TypeCode(tAxis, cAxis)
    outputAxes = allAxes.setdefault(outputName, {})
    axis = None
    if tcAxis not in outputAxes:
      #raise RuntimeError("Axis was not initialized for '{}'".format(fnAxis))
      outputs = self.get("outputs")
      o = outputs.get(outputName)
      if o is None:
        raise RuntimeError("Cannot find axis '{}' because output '{}' is missing".format(fnAxis, outputName))
      if tcAxis not in o.get_supported_axes():
        raise RuntimeError("Axis '{}' is not supported by '{}'".format(tc2ns(*tcAxis)[0], outputName))
      axis = None
      if tAxis == codes.EV_KEY:
        cButton = cAxis
        axis = ReportingAxis(JoystickButtonAxis(o, cButton))
      else:
        isReportingJoystick = type(o) is ReportingJoystick
        axis = o.make_axis(tcAxis) if isReportingJoystick else ReportingAxis(JoystickAxis(o, tcAxis))
      outputAxes[tcAxis] = axis
      self.get("axesToNames")[axis] = fnAxis
    else:
      axis = outputAxes[tcAxis]
    return axis

  def get_full_name_by_axis(self, axis):
    return self.get("axesToNames").get(axis, None)

  def __init__(self, parser=make_parser(), print_devices=lambda a:None):
    self.loop_ = None
    self.print_devices_ = print_devices
    self.options_ = {}
    self.props_ = {}
    self.props_["reloading"] = False
    self.props_["source"] = None
    self.props_["config"] = None
    self.props_["parser"] = parser
    self.props_["updated"] = []
    self.props_["axes"] = {}
    self.props_["axesToNames"] = {}
    self.props_["outputs"] = {}
    self.props_["sounds"] = {}
    self.props_["state"] = False
    self.props_["numTraceLines"] = 0
    self.props_["soundPlayer"] = SoundPlayer()
    self.props_["varManager"] = VarManager()
    self.props_["valueManager"] = VarManager(make_var = lambda : Var(None))
    poseManager = AxisPoseManager()
    self.props_["poseManager"] = poseManager
    self.props_["poseTracker"] = PoseTracker(poseManager)
