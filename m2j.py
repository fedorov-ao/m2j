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


def get_func_name():
  import sys
  return sys._getframe().f_back.f_code.co_name


def log_loc(obj=None):
  import sys
  funcName = sys._getframe().f_back.f_code.co_name
  objInfo = "" if obj is None else "{}(@0x{:x}).".format(obj.__class__.__name__, id(obj))
  return "{}{}()".format(objInfo, funcName)


g_loggers = []

def get_logger(logger, name):
  l = logger.getChild(name)
  global g_loggers
  g_loggers.append(l)
  return l

def set_loggers_level(level):
  logging.getLogger().setLevel(level)
  global g_loggers
  for logger in g_loggers:
    logger.setLevel(level)

logger = get_logger(logging.getLogger(), "m2j")


def sign(v):
  return -1 if v < 0 else 1 if v > 0 else 0


def copysign(v, x):
  return None if v is None or x is None else sign(x) * v


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


def select_nearest(b, e, values, selectExactMatch=True):
  """
  Selects a value from values that is nearest to b and lies in [b; e].
  If selectExactMatch == False, value that is equal to b is not matched.
  """
  if values is None or len(values) == 0:
    return None
  selected, selectedDelta = None, float("inf")
  for v in values:
    if v == b:
      if selectExactMatch == True:
        return v
      else:
        continue
    if clamp(v, b, e) == v:
      vDelta = abs(v - b)
      if vDelta < selectedDelta:
        selected, selectedDelta = v, vDelta
  return selected


def is_inside_bbox(x, y, bbox):
  x0, y0, x1, y1 = bbox
  return x >= x0 and x <= x1 and y >= y0 and y <= y1


def is_dict_type(a):
  return type(a) in (dict, collections.OrderedDict,)


def is_str_type(a):
  return type(a) in (str, unicode,)


def is_list_type(a):
  return type(a) in (tuple, list,)


def merge_dicts(destination, source, should_overwrite=None):
  """https://stackoverflow.com/questions/20656135/python-deep-merge-dictionary-data"""
  for key, sourceValue in source.items():
    if is_dict_type(sourceValue):
      destinationValue = destination.setdefault(key, sourceValue.__class__())
      if should_overwrite is not None and should_overwrite(key, destinationValue, sourceValue) == True:
        destination[key] = sourceValue
      else:
        #print "merging {} with {}".format(str2(destinationValue), str2(sourceValue))
        merge_dicts(destinationValue, sourceValue, should_overwrite)
    elif is_list_type(sourceValue):
      destinationValue = destination.get(key, [])
      if should_overwrite is not None and should_overwrite(key, destinationValue, sourceValue) == True:
        destination[key] = sourceValue
      else:
        destinationValue += sourceValue
        destination[key] = destinationValue
    else:
      destination[key] = sourceValue
  return destination


def filter_dict(d, keys, getter=lambda d,f : d.get(f), setter=None):
  """
  Filters dictionary, returning a new one of the same type.
  Parameters:
    d - dictionary to be mapped
    keys - list of keys to include in returned dictionary
    getter - retrieves elements by fromKey from d
  keys that are not in d are skipped.
  """
  if setter is None:
    def setter_(d, k, v):
      d[k] = v
    setter = setter_
  r = d.__class__()
  for key in keys:
    v = getter(d, key)
    if v is not None:
      setter(r, key, v)
  return r


def exclude_from_dict(d, *args):
  return d.__class__(kv for kv in d.items() if kv[0] not in args)


def map_dict(d, keys, getter=lambda d,f : d.get(f)):
  """
  Maps dictionary, returning a new one of the same type.
  Parameters:
    d - dictionary to be mapped
    keys - dictionary of format {fromKey:toKey}
    getter - retrieves elements by fromKey from d
  keys that are not in d are skipped.
  """
  r = d.__class__()
  for keyFrom,keyTo in keys.items():
    v = getter(d, keyFrom)
    if v is not None:
      r[keyTo] = v
  return r


def map_dict_d(d, keysAndDefaults, getter=lambda d,f,dfault : d.get(f, dfault)):
  """
  Maps dictionary, returning a new one of the same type.
  Supports default values.
  Parameters:
    d - dictionary to be mapped
    keysAndDefaults - dictionary of format {fromKey:(toKey,dfaultIfNoToKey)}
    getter - retrieves elements by fromKey from d, should return dfault if fromKey is not in d
  """
  r = d.__class__()
  for keyFrom,pair in keysAndDefaults.items():
    keyTo, dfault = pair[0], pair[1]
    r[keyTo] = getter(d, keyFrom, dfault)
  return r


def map_dict_ex(d, keysAndDefaults, getter=lambda d,k : d.get(k), setter=lambda d,k,v : d.__setitem__(k,v)):
  r = d.__class__()
  for kd in keysAndDefaults:
    keyFrom, keyTo, dfault = None, None, None
    if is_list_type(kd):
      if len(kd) == 2:
        keyFrom, keyTo = kd
      elif len(kd) == 3:
        keyFrom, keyTo, dfault = kd
      else:
        raise KeyError(kd)
    else:
      keyFrom = keyTo = kd
    v = None
    if keyFrom in d:
      v = getter(d, keyFrom)
    elif dfault is not None:
      v = dfault
    if v is not None:
      setter(r, keyTo, v)
  return r


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
    if is_dict_type(v):
      for a,b in v.items():
        s += str2(a) + " : " + str2(b) + ", "
      s = s[:-2]
    elif is_list_type(v):
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
  def check_type(d, name):
    if not is_dict_type(d) and not is_list_type(d):
      raise ValueError("{} is not a dictionary or list, but a {}".format(name, type(d)))
  tokens = None
  if is_str_type(name):
    tokens = name.split(sep)
  elif is_list_type(name):
    tokens = name
  else:
    raise ValueError("{} is not str or list".format(name))
  currSeq = d
  for token in tokens[:-1]:
    check_type(currSeq, token)
    currSeq = currSeq.setdefault(token, currSeq.__class__())
  token = tokens[-1]
  check_type(currSeq, token)
  currSeq[token] = value
  return d


def set_nested_strict(seq, name, value, sep = "."):
  def check_type(seq, name):
    if type(seq) not in (list, dict, collections.OrderedDict):
      raise ValueError("{}: invalid type".format(name))
  tokens = None
  if is_str_type(name):
    tokens = name.split(sep)
  elif is_list_type(name):
    tokens = name
  else:
    raise ValueError("{} is not str or list".format(name))
  currSeq, token = seq, None
  try:
    for token in tokens[:-1]:
      check_type(currSeq, token)
      if type(currSeq) in (dict, collections.OrderedDict):
        currSeq = currSeq[token]
      elif type(currSeq) in (list,):
        token = int(token)
        currSeq = currSeq[token]
    token = tokens[-1]
    check_type(currSeq, token)
    if type(currSeq) in (list,):
      token = int(token)
    cls = currSeq[token].__class__
    currSeq[token] = cls(value)
    return seq
  except (KeyError, IndexError) as e:
    raise KeyError(token)


def get_nested(d, name, sep = "."):
  tokens = None
  if is_str_type(name):
    if len(name) == 0:
      return None
    tokens = name.split(sep)
  elif is_list_type(name):
    tokens = name
  else:
    raise ValueError("{} is not str or list".format(name))
  for t in tokens:
    if not is_dict_type(d):
      raise ValueError("{} is not dict".format(d))
    nd = d.get(t)
    if nd is None:
      path = str(sep.join(tokens[:tokens.index(t)]))
      token = sep.join((path, str(t))) if len(path) != 0 else str(t)
      keys = [sep.join((path, str(k))) if len(path) != 0 else str(k) for k in d.keys()]
      raise KeyErrorEx(token, keys)
    d = nd
  return d


def get_nested_ex(d, name, state, sep = "."):
  try:
    return get_nested(d, name, sep)
  except KeyErrorEx as e:
    raise ParseError(d, state.get_path(d), e)


def get_nested_d(d, name, dfault = None, sep = "."):
  tokens = None
  if is_str_type(name):
    if len(name) == 0:
      return None
    elif name.find(sep) == -1:
      pass
    else:
      tokens = name.split(sep)
  elif is_list_type(name):
    tokens = name
  else:
    raise ValueError("{} is not str or list".format(name))
  r = dfault
  def get(d, name):
    return d.get(name) if hasattr(d, "get") == True else None
  if tokens is None:
    d = get(d, name)
  else:
    for t in tokens:
      d = get(d, t)
      if d is None:
        break
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


def v2p_fill(seq, v2p, parent):
  class CI:
    def __init__(self, parent, key):
      self.parent, self.key = parent, key
  def is_seq(v):
    return is_dict_type(v) or is_list_type(v)
  ts = type(seq)
  kvs = enumerate(seq) if ts in (list, tuple) else seq.items() if ts in (dict, collections.OrderedDict) else ()
  for key,value in kvs:
    ci = CI(parent, key)
    v2p[id(value)] = ci
    if is_seq(value):
      v2p_fill(value, v2p, ci)


def v2p_make(seq):
  v2p = {}
  v2p_fill(seq, v2p, None)
  return v2p


def v2p_path(v, v2p):
  ci = v2p.get(id(v))
  p = []
  while ci is not None:
    p.append(ci.key)
    ci = ci.parent
  p.reverse()
  return p


def v2p_path2str(path, sep="."):
  return sep + sep.join(str(v) for v in path)


def remove_value_tag(d):
  r = d.__class__()
  for k,v in d.items():
    if k != "_value":
      r[k] = v
  return r


def add_value_tag(d):
  r = d.__class__()
  for k,v in d.items():
    r[k] = v
  r["_value"] = True
  return r


def has_value_tag(d):
  return is_dict_type(d) and "_value" in d


def clear_value_tag(d):
  return remove_value_tag(d) if has_value_tag(d) else d


import pymatrix27

def fill_ols_matrix(matrix, samples, degree, scratch=None, get_sample=None):
  '''
  Fill lsq matrix.
  Argumets:
    matrix - output parameter. row-based matrix (m[i][j] is item in row i and column j)
    samples - sequence of sample value pairs ((x, y))
    degree - degree of polynomial
    scratch - list used as scratch space. Can be None, if not len(samples) == len(scratch)
  '''
  if get_sample is None:
    def gs(samples, i, k):
      return samples[i][k]
    get_sample = gs
  #i is row, j is column
  sentinel = degree + 1
  n = len(samples)
  if scratch is None:
    scratch = [get_sample(samples, i, 0) for i in range(n)]
  else:
    ls = len(scratch)
    if ls < n:
      raise ValueError("scrath space and samples have unequal length({} and {})".format(ls, n))
    for i in range(n):
      scratch[i] = get_sample(samples, i, 0)
  scratchPow = [1]
  def scratchUp():
    for i in range(n):
      scratch[i] *= get_sample(samples, i, 0)
    scratchPow[0] += 1
  #fill zero row and last column
  matrix[0][0] = n
  matrix[0][sentinel] = sum( (get_sample(samples, i, 1) for i in range(n)) )
  for j in range(1, sentinel):
    matrix[0][j] = sum(scratch)
    matrix[j][sentinel] = sum( (get_sample(samples, k, 1) * scratch[k] for k in range(n)) )
    scratchUp()
  assert scratchPow[0] == degree + 1, scratchPow[0]
  #fill subsequent rows by shifting left and copying; then computing last sum
  for i in range(1, sentinel):
    for j in range(0, sentinel - 1):
      matrix[i][j] = matrix[i - 1][j + 1]
    matrix[i][sentinel - 1] = sum(scratch)
    scratchUp()
  assert scratchPow[0] == 2 * degree + 1, scratchPow[0]


def make_ols_matrix(samples, degree, scratch=None, get_sample=None):
  matrix = pymatrix27.Matrix(degree+1, degree+2)
  fill_ols_matrix(matrix, samples, degree, scratch, get_sample)
  return matrix


def extract_poly_coeffs(coeffs, matrix, degree):
  '''
  Extract polynomial coefficients from solved lsq matrix.
  Argumets:
    coeffs - output parameter. [b0, b1, b2, ...], where number is power of argument (so b0 is free member)
    matrix - solved lsq matrix, row-based (m[i][j] is item in row i and column j)
    degree - degree of polynomial
  '''
  for k in range(len(coeffs)):
    coeffs[k] = 0.0
  sentinel = degree + 1
  #i is row, j is column
  for j in range(sentinel):
    for i in range(sentinel):
      if abs(matrix[i][j] - 1.0) < 1e-4:
        coeffs[i] = matrix[i][sentinel]
        break


def calc_poly(x, coeffs, degree):
  '''
  Compute value of polynomial with _degree_ and _coeffs_ for _x_.
  '''
  if len(coeffs) < degree + 1:
    raise ArgumentError
  r, xx = coeffs[0], 1.0
  for i in range(1, degree + 1):
    xx *= x
    r += coeffs[i] * xx
  return r


class PolynomialApproximator:
  logger = get_logger(logger, "PolynomialApproximator")

  def calc(self, x):
    self.update_()
    if self.currentDegree_ is None:
      return None
    else:
      x = self.conv_x_(self.buffer_, x)
      return calc_poly(x, self.coeffs_, self.currentDegree_)

  def append(self, x, y):
    self.buffer_.append((x,y))
    self.dirty_ = True

  def replace(self, x, y):
    i = None
    for j in range(len(self.buffer_)):
      if self.buffer_[j] == x:
        i = j
        break
    if i is None:
      raise KeyError
    self.buffer_[i] = (x,y)
    self.dirty_ = True

  def clear(self):
    self.buffer_.clear()
    assert(len(self.buffer_) == 0)
    for i in range(len(self.coeffs_)):
      self.coeffs_[i] = 0.0
    for i in range(len(self.scratch_)):
      self.scratch_[i] = 0.0
    #have to clear the matrix, because rref() operates on the whole matrix
    #even if it is partially filled when currentDegree_ < degree_
    for i in range(self.degree_+1):
      for j in range(self.degree_+2):
        self.matrix_[i][j] = 0.0
    self.currentDegree_ = None
    self.dirty_ = False

  def __init__(self, degree, numSamples, get_sample=None, conv_x=None):
    import collections
    self.degree_, self.currentDegree_ = degree, None
    if conv_x is None:
      def cx(samples, x):
        return x
      conv_x = cx
    self.get_sample_, self.conv_x_ = get_sample, conv_x
    self.matrix_ = pymatrix27.Matrix(degree+1, degree+2)
    self.coeffs_ = [0.0 for i in range(degree+1)]
    self.buffer_ = collections.deque(maxlen=numSamples)
    self.scratch_ = [0.0 for i in range(numSamples+1)]
    self.dirty_ = False
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: created".format(log_loc(self)))

  def update_(self):
    if self.dirty_ == False:
      return
    self.currentDegree_ = min(self.degree_, len(self.buffer_)-1)
    fill_ols_matrix(self.matrix_, self.buffer_, self.currentDegree_, self.scratch_, self.get_sample_)
    self.matrix_ = self.matrix_.rref()
    extract_poly_coeffs(self.coeffs_, self.matrix_, self.currentDegree_)
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: coeffs: {}".format(hex(log_loc(self)), self.coeffs_[:self.currentDegree_]))
    self.dirty_ == False


class KeyErrorEx(KeyError):
  def __init__(self, key, keys):
    KeyError.__init__(self, key)
    self.key, self.keys = key, keys
  def __str__(self):
    return "'{}' not in {}".format(self.key, str2(self.keys))


class NotFoundError(RuntimeError):
  def __init__(self, what, name):
    self.what, self.name = what, name

  def __str__(self):
    return "{} '{}' not found".format(self.what, self.name)


class ConfigReadError(RuntimeError):
  def __init__(self, configName, e):
    self.configName, self.e = configName, e
  def __str__(self):
    return "Cannot read config file {} ({})".format(self.configName, self.e)


class ParseError(RuntimeError):
  def __init__(self, cfg, path=None, e=None):
    if path is None:
      path = []
    if is_str_type(e):
      e = RuntimeError(e)
    self.cfg, self.path, self.e = cfg, path, e
  def __str__(self):
    return "could not parse '{}' at '{}': {}".format(str2(self.cfg), v2p_path2str(self.path), self.e)


class ParserState:
  logger = get_logger(logger, "ParserState")

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
    obj, i = None, 0
    if objectName[0] == "self":
      obj = self.at("eps", 0)
    if objectName[0] == "root":
      obj = self.at("eps", -1)
    else:
      while True:
        ep = self.at("eps", i)
        if ep is None:
          break
        objects = ep.get("objects", None)
        if objects is not None:
          obj = objects.get(objectName[0])
          if obj is not None:
            break
        i += 1
    if obj is None:
      raise NotFoundError("obj", name)
    if len(objectName) > 1:
      for s in objectName[1].split(memberSep):
        obj = obj.get(s)
        if obj is None:
          raise NotFoundError("obj", s)
    return self.get_var_or_value_(obj, **kwargs)

  def make_objs(self, cfg, cb, keys=None):
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("Constructing objects from '{}'".format(str2(cfg)))
    if keys is None:
      keys = []
    for k,v in cfg.items():
      keys.append(k)
      try:
        o = None
        if is_dict_type(v):
          if has_value_tag(v):
            o = v
          elif "class" in v:
            o = self.resolve_def(v)
          else:
            self.make_objs(v, cb, keys)
        else:
          o = self.resolve_def(v)
        if o is not None:
          cb(keys, o)
      except RuntimeError as e:
        self.logger.warning("Could not create object '{}': {}".format(".".join(keys), e))
      finally:
        keys.pop()

  def get_arg(self, name, **kwargs):
    r = None
    args = self.stacks_.get("args")
    if args is not None:
      r = get_nested_from_stack_d(args, name, None)
      if r is None:
        raise NotFoundError("arg", name)
    else:
      raise RuntimeError("No args were specified, so cannot get arg: {}".format(str2(name)))
    return self.get_var_or_value_(r, **kwargs)

  def resolve_args(self, args):
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("Resolving args '{}'".format(str2(args)))
    r = collections.OrderedDict()
    for n,v in args.items():
      try:
        o = None
        if is_dict_type(v):
          if has_value_tag(v):
            o = v
          elif "class" in v:
            o = self.resolve_def(v)
          else:
            o = self.resolve_args(v)
        else:
          o = self.resolve_def(v)
        r[n] = o
        #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("arg '{}': '{}' -> '{}'".format(n, str2(v), r[n]))
      except NotFoundError as e:
        self.logger.warning(e)
        continue
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

  def make_mapping(self, mappingCfg):
    if mappingCfg is None:
      return None
    mapping = {}
    for k,v in mappingCfg.items():
      k = clear_value_tag(self.resolve_def(k))
      v = clear_value_tag(self.resolve_def(v))
      mapping[k] = v
    def op(v):
      r = mapping.get(v)
      if r is None:
        raise RuntimeError("{} not found in mapping".format(v))
      return r
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("Created mapping {} from {}".format(op, str2(mappingCfg)))
    return op

  def deref(self, refOrValue, **kwargs):
    def make_expression_mapping(p, s):
      expr = "{}v{}".format(p, s)
      compiledExpr = compile(expr, "", "eval")
      def op(v):
        globs = { "v" : v }
        #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: evaluating {} with {}".format(log_loc(self), expr, str2(globs)))
        return eval(compiledExpr, globs)
      return op
    prefix, suffix, mapping, dfault = None, None, None, None
    cls = kwargs.get("cls")
    if cls is not None:
      del kwargs["cls"]
    r = refOrValue
    if is_dict_type(refOrValue):
      dfault = self.resolve_d(refOrValue, "default", None)
      for p in ("obj", "arg", "var"):
        suffix = get_nested_d(refOrValue, p, None)
        if suffix is not None:
          prefix = p
          mappingCfg = self.resolve_d(refOrValue, "mapping", None)
          if prefix == "var" and mappingCfg is not None:
            mapping = make_mapping(mappingCfg)
          else:
            refOrValueRe = re.compile("([+\-*/&|]*)([^ +\-*/&|]*)(.*?)")
            refOrValueMatch = refOrValueRe.match(suffix)
            if refOrValueMatch is not None:
              suffix = refOrValueMatch.group(2)
              g1, g3 = refOrValueMatch.group(1), refOrValueMatch.group(3)
              mapping = make_expression_mapping(g1, g3)
          break
    elif is_str_type(refOrValue):
      refOrValueRe = re.compile("(.*?)(obj|arg|var):([^ +\-*/&|]*)(.*?)")
      refOrValueMatch = refOrValueRe.match(refOrValue)
      if refOrValueMatch is not None:
        prefix, suffix = refOrValueMatch.group(2), refOrValueMatch.group(3)
        g1, g4 = refOrValueMatch.group(1), refOrValueMatch.group(4)
        if len(g1) or len(g4):
          mapping = make_expression_mapping(g1, g4)
          #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("Created mapping {} with expression '{}' from '{}'".format(mapping, expr, refOrValue))
    if prefix is not None:
      suffix = self.deref(suffix, **kwargs)
      setter = kwargs.get("setter")
      asValue = kwargs.get("asValue", True)
      if prefix in ("arg", "obj"):
        try:
          if prefix == "obj":
            r = self.get_obj(suffix, setter=setter, mapping=mapping, asValue=asValue)
          elif prefix == "arg":
            r = self.get_arg(suffix, setter=setter, mapping=mapping, asValue=asValue)
          else:
            assert False
        except NotFoundError as e:
          if dfault is not None:
            r = clear_value_tag(dfault)
          else:
            raise
      elif prefix == "var":
        r = self.get_var(suffix, setter=setter, mapping=mapping, asValue=asValue)
      else:
        raise RuntimeError("Unknown prefix: '{}'".format(prefix))
    if cls is not None and r.__class__ is not cls:
      r = cls(r)
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("Dereferenced '{}' to '{}'".format(str2(refOrValue), str2(r)))
    #This return statement must be at deref() scope, not in nested blocks!
    return r

  def resolve_d(self, d, name, dfault=None, **kwargs):
    cfg = get_nested_d(d, name, dfault)
    if cfg == dfault:
      return dfault
    try:
      return self.deref(cfg, **kwargs)
    except NotFoundError as e:
      return dfault
    except StandardError as e:
      raise ParseError(cfg, self.get_path(cfg), e)

  def resolve(self, d, name, **kwargs):
    cfg = get_nested_ex(d, name, self)
    try:
      return self.deref(cfg, **kwargs)
    except StandardError as e:
      raise ParseError(cfg, self.get_path(cfg), e)

  def parse_def(self, cfg):
    assert is_dict_type(cfg)
    parser = self.get("parser")
    obj = None
    className = cfg.get("class", None)
    if className is None:
      raise ParseError(cfg, self.get_path(cfg), KeyErrorEx("class", cfg.keys()))
    obj = parser(className, cfg, self)
    if obj is None:
      raise ParseError(cfg, self.get_path(cfg))
    return obj

  def resolve_def(self, cfg):
    r = self.deref(cfg, asValue=False)
    if is_dict_type(r) and not has_value_tag(r):
      r = self.parse_def(r)
    return r

  def get_path(self, v):
    return self.get("main").get_path(v)

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
    varManager = self.get("main").get("varManager")
    mapping = kwargs.get("mapping")
    isBaseVar = isinstance(r, BaseVar)
    asValue = kwargs.get("asValue", True)
    if asValue:
      r = clear_value_tag(r)
    if isBaseVar == True:
      setter = kwargs.get("setter")
      if setter is not None:
        actualSetter = setter
        if mapping is not None:
          def mapping_setter(x):
            mx = mapping(x)
            setter(mx)
          actualSetter = mapping_setter
        #r can be assigned to different value further down the execution path, so using varOrValue here
        varOrValue.add_callback(actualSetter)
        self.get("main").get("callbackManager").add_callback(lambda : varOrValue.remove_callback(actualSetter))
      if asValue == True:
        r = r.get()
        if mapping is not None:
          r = mapping(r)
    else:
      if mapping is not None:
        r = mapping(r)
    return r


class DevRegister:
  def register_dev(self, name):
    """Input event dev __init__() should call this with the name of dev."""
    hsh = self.hash_
    self.hash_ += 1
    self.devs_[hsh] = name
    self.hashes_[name] = hsh
    return hsh

  def get_name(self, hsh):
    if hsh is None:
      return None
    r = self.devs_.get(hsh, None)
    if r is None:
      raise RuntimeError("Dev with hash {} not registered".format(hsh))
    return r

  def get_hash(self, name):
    if name is None:
      return None
    r = self.hashes_.get(name, None)
    if r is None:
      if self.addMissing_:
        r = self.register_dev(name)
      else:
        raise RuntimeError("Dev with name {} not registered".format(name))
    return r

  def __init__(self, addMissing=True):
    self.devs_, self.hashes_, self.addMissing_ = dict(), dict(), addMissing
    self.hash_ = 0

g_sr = DevRegister(addMissing=True)

def register_dev(dev):
  """Input event dev __init__() should call this with the name of dev."""
  return g_sr.register_dev(dev)

def get_dev_name(hsh):
  return g_sr.get_name(hsh)

def get_dev_hash(name):
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
    raise RuntimeError("bad name: {}".format(str2(name)))
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


SplitName = collections.namedtuple("SplitName", "state dev shash type code")

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
  dev = None if i == -1 else s[:i]
  shash = None if dev is None else get_dev_hash(dev)
  name = s if i == -1 else s[i+1:]
  code = name2code(name)
  type = name2type(name)
  return SplitName(state=st, dev=dev, shash=shash, type=type, code=code)


DevName = collections.namedtuple("DevName", "dev name")
DevCode = collections.namedtuple("DevCode", "dev code")
DevNameState = collections.namedtuple("DevNameState", "dev name state")
DevCodeState = collections.namedtuple("DevCodeState", "dev code state")
TypeCode = collections.namedtuple("TypeCode", "type code")
DevTypeCode = collections.namedtuple("DevTypeCode", "dev type code")
DevTypeCodeState = collections.namedtuple("DevTypeCodeState", "dev type code state")

def fn2dn(s, sep="."):
  """
  Splits full name into dev and name.
  'mouse.REL_X' -> ('mouse', 'REL_X')
  'REL_X' -> (None, 'REL_X')
  """
  i = s.find(sep)
  return DevName(None, s) if i == -1 else DevName(s[:i], s[i+1:])


def fn2dc(s, sep="."):
  """
  Splits full name into dev and code.
  'mouse.REL_X' -> ('mouse', codes.REL_X)
  'REL_X' -> (None, codes.REL_X)
  """
  r = fn2dn(s, sep)
  return DevCode(dev=r.dev, code=name2code(r.name))


def fn2hc(s, sep="."):
  """
  Splits full name into dev hash and code.
  'mouse.REL_X' -> (get_dev_hash('mouse'), codes.REL_X)
  'REL_X' -> (None, codes.REL_X)
  """
  r = fn2dc(s, sep)
  h = get_dev_hash(r.dev)
  return DevCode(dev=h, code=r.code)


def fn2tc(s, sep="."):
  """
  Splits full name into type and code.
  'mouse.REL_X' -> TypeCode(codes.EV_REL, codes.REL_X)
  'REL_X' -> TypeCode(codes.EV_REL, codes.REL_X)
  """
  r = fn2dn(s, sep)
  return TypeCode(type=name2type(r.name), code=name2code(r.name))


def fn2dtc(s, sep="."):
  """
  Splits full name into dev, type and code.
  'mouse.REL_X' -> ('mouse', codes.EV_REL, codes.REL_X)
  'REL_X' -> (None, codes.EV_REL, codes.REL_X)
  """
  r = fn2dn(s, sep)
  return DevTypeCode(dev=r.dev, type=name2type(r.name), code=name2code(r.name))


def fn2htc(s, sep="."):
  """
  Splits full name into dev hash, type and code.
  'mouse.REL_X' -> (get_dev_hash('mouse'), codes.EV_REL, codes.REL_X)
  'REL_X' -> (None, codes.EV_REL, codes.REL_X)
  """
  r = fn2dtc(s, sep)
  h = get_dev_hash(r.dev)
  return DevTypeCode(dev=h, type=r.type, code=r.code)


def dtc2fn(devName, type, code, sep=".", nameSep="/"):
  """
  Joins dev name, type and code into full name.
  'mouse', codes.EV_REL, codes.REL_X -> 'mouse.REL_X'
  None, codes.EV_REL, codes.REL_X -> 'REL_X'
  """
  tcn = tc2ns(type, code)
  if devName is not None:
    tcn = (sep.join((devName, t)) for t in tcn)
    tcn = nameSep.join(tcn)
  return tcn


def htc2fn(devHash, type, code, sep=".", nameSep="/"):
  """
  Joins dev hash, type and code into full name.
  get_dev_hash('mouse'), codes.EV_REL, codes.REL_X -> 'mouse.REL_X'
  None, codes.EV_REL, codes.REL_X -> 'REL_X'
  """
  s = None if devHash is None else str(get_dev_name(devHash))
  return dtc2fn(s, type, code, sep, nameSep)


def fn2dne(s, sep="."):
  """
  Splits full name into dev, name and state.
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
  return DevNameState(dev=None, name=s, state=state) if i == -1 else DevNameState(dev=s[:i], name=s[i+1:], state=state)


def fn2dce(s, sep="."):
  """
  Splits full name into dev, code and state.
  'mouse.REL_X' -> ('mouse', codes.REL_X, True)
  'REL_X' -> (None, codes.REL_X, True)
  '+mouse.REL_X' -> ('mouse', codes.REL_X, True)
  '+REL_X' -> (None, codes.REL_X, True)
  '-mouse.REL_X' -> ('mouse', codes.REL_X, False)
  '-REL_X' -> (None, codes.REL_X, False)
  """
  r = fn2dne(s, sep)
  return DevCodeState(dev=r.dev, code=name2code(r.name), state=r.state)


def fn2hce(s, sep="."):
  """
  Splits full name into dev hash, code and state.
  'mouse.REL_X' -> ('mouse', codes.REL_X, True)
  'REL_X' -> (None, codes.REL_X, True)
  '+mouse.REL_X' -> ('mouse', codes.REL_X, True)
  '+REL_X' -> (None, codes.REL_X, True)
  '-mouse.REL_X' -> ('mouse', codes.REL_X, False)
  '-REL_X' -> (None, codes.REL_X, False)
  """
  r = fn2dce(s, sep)
  h = get_dev_hash(r.dev)
  return DevCodeState(dev=h, code=r.code, state=r.state)


def fn2dtce(s, sep="."):
  """
  Splits full name into dev, type, code and state.
  'mouse.REL_X' -> ('mouse', codes.EV_REL, codes.REL_X, True)
  'REL_X' -> (None, codes.EV_REL, codes.REL_X, True)
  '+mouse.REL_X' -> ('mouse', codes.EV_REL, codes.REL_X, True)
  '+REL_X' -> (None, codes.EV_REL, codes.REL_X, True)
  '-mouse.REL_X' -> ('mouse', codes.EV_REL, codes.REL_X, False)
  '-REL_X' -> (None, codes.EV_REL, codes.REL_X, False)
  """
  r = fn2dne(s, sep)
  return DevTypeCodeState(dev=r.dev, type=name2type(r.name), code=name2code(r.name), state=r.state)


def fn2htce(s, sep="."):
  """
  Splits full name into dev hash, type, code and state.
  'mouse.REL_X' -> (get_dev_hash('mouse'), codes.EV_REL, codes.REL_X, True)
  'REL_X' -> (None, codes.EV_REL, codes.REL_X, True)
  '+mouse.REL_X' -> (get_dev_hash('mouse'), codes.EV_REL, codes.REL_X, True)
  '+REL_X' -> (None, codes.EV_REL, codes.REL_X, True)
  '-mouse.REL_X' -> (get_dev_hash('mouse'), codes.EV_REL, codes.REL_X, False)
  '-REL_X' -> (None, codes.EV_REL, codes.REL_X, False)
  """
  r = fn2dtce(s, sep)
  return DevTypeCodeState(dev=get_dev_hash(r.dev), type=r.type, code=r.code, state=r.state)


def parse_modifier_desc(s, state, sep="."):
  t = split_full_name2(s, state, sep)
  return DevCodeState(dev=t.shash, code=t.code, state=t.state)


class ReloadException:
  pass


class ExitException:
  pass


class NullJoystick:
  """Placeholder joystick class."""

  logger = get_logger(logger, "NullJoystick")

  def __init__(self, values=None, limits=None, buttons=None):
    self.limits_ = {}
    if limits is not None:
      for tca,l in limits.items():
        self.limits_[tca] = l
    self.v_ = {}
    noLimits = (float("-inf"), float("+inf"))
    if values is not None:
      for a,v in values.items():
        self.v_[a] = clamp(v, *self.limits_[a]) if a in self.limits_ else v
    self.b_ = {}
    if buttons is not None:
      for b in buttons:
        self.b_[b] = False
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{} created".format(log_loc(self)))

  def __del__(self):
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{} destroyed".format(log_loc(self)))
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
    return self.limits_.keys()

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
    return fmt.format(self.type, "/".join(type2names(self.type)), self.code, self.code, dtc2fn(None, self.type, self.code), str2(self.value), self.timestamp)

  __slots__ = ("type", "code", "value", "timestamp", )
  def __init__(self, type, code, value, timestamp=None):
    if timestamp is None:
      timestamp = time.time()
    self.type, self.code, self.value, self.timestamp = type, code, value, timestamp


class InputEvent(Event):
  def __str__(self):
    #Had to reference members of parent class directly, because FreePie does not handle super() well
    fmt = ", idev: {} ({}), modifiers: {}"
    modifiers = [((s, m), htc2fn(s, codes.EV_KEY, m)) for s,m in self.modifiers]
    return Event.__str__(self) + fmt.format(self.idev, get_dev_name(self.idev), modifiers)
    #these do not work in FreePie
    #return super(InputEvent, self).__str__() + ", idev: {}, modifiers: {}".format(self.idev, self.modifiers)
    #return super(InputEvent, Event).__str__() + ", idev: {}, modifiers: {}".format(self.idev, self.modifiers)
    #return super().__str__() + ", idev: {}, modifiers: {}".format(self.idev, self.modifiers)
    #return Event.__str__(self) + ", idev: {}, modifiers: {}".format(self.idev, self.modifiers)
    #return "idev: {}, modifiers: {}".format(self.idev, self.modifiers)

  __slots__ = ("idev", "modifiers",)
  def __init__(self, t, code, value, timestamp, idev, modifiers=None):
    #Had to reference members of parent class directly, because FreePie does not handle super() well
    #This does not work in FreePie
    #super().__init__(t, code, value, timestamp)
    self.type, self.code, self.value, self.timestamp = t, code, value, timestamp
    self.idev = idev
    self.modifiers = [] if modifiers is None else modifiers


class ClickEvent(InputEvent):
  def __str__(self):
    return InputEvent.__str__(self) + ", num_clicks: {}".format(self.num_clicks)

  __slots__ = ("num_clicks",)
  def __init__(self, t=None, code=None, timestamp=None, idev=None, modifiers=None, num_clicks=0):
    InputEvent.__init__(self, t, code, 3, timestamp, idev, modifiers)
    self.num_clicks = num_clicks

  @classmethod
  def from_event(cls, event, numClicks):
    ce = ClickEvent()
    ce.type, ce.code, ce.value, ce.timestamp, ce.idev, ce.modifiers = event.type, event.code, 3, event.timestamp, event.idev, event.modifiers
    ce.num_clicks = numClicks
    return ce


class EventCompressorDevice:
  """Compresses movement events for each relative axis.
     Movement events along a given axis are compressed as long as direciton of movement is not changed.
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
        k = (event.idev, event.code, None if event.modifiers is None else tuple(m for m in event.modifiers))
        e = self.events_.get(k)
        if e is None:
          self.events_[k] = event
        else:
          if sign(e.value) == sign(event.value):
            e.value += event.value
            e.timestamp = event.timestamp
          else:
            self.events_[k], event = event, e
      else:
        break
    return event

  def swallow(self, s):
    self.next_.swallow(s)

  def __init__(self, next):
    self.next_ = next
    self.events_ = {}


class EventSource:
  logger = get_logger(logger, "EventSource")

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
        if self.logger.isEnabledFor(logging.ERROR): self.logger.error(e)
        continue
    events.sort(key = lambda e : e.timestamp)
    if self.ep_ is not None:
      for event in events:
        #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: Sending event: {}".format(log_loc(self), event))
        self.ep_(event)

  def set_ep(self, ep):
    self.ep_ = ep

  def add_device(self, name, device):
    if name in self.devices_:
      raise RuntimeError("{} is already registered".format(name))
    self.devices_[name] = device

  def swallow(self, name, s):
    if name is None:
      for n,d in self.devices_.items():
        d.swallow(s)
    else:
      dev = self.devices_.get(name)
      if dev is not None:
        dev.swallow(s)

  def __init__(self, devices, ep=None):
    self.devices_, self.ep_ = devices, ep
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{} created".format(log_loc(self)))

  def __del__(self):
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{} destroyed".format(log_loc(self)))
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
    r = False
    if self.curve_ is not None:
      v = event.value*self.factor_
      if event.type == codes.EV_REL:
        self.curve_.move_by(v, event.timestamp)
        r = True
      elif event.type == codes.EV_ABS:
        self.curve_.move(v, event.timestamp)
        r = True
    return r

  def set_factor(self, factor):
    self.factor_ = factor

  def __init__(self, curve, factor=1.0):
    self.curve_, self.factor_ = curve, factor


class SetJoystickAxis:
  logger = get_logger(logger, "SetJoystickAxis")

  def __init__(self, joystick, tcAxis, value):
    self.js_, self.axis_, self.value_ = joystick, tcAxis, value
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{} created".format(log_loc(self)))

  def __del__(self):
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{} destroyed".format(log_loc(self)))
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
        if logger.isEnabledFor(logging.DEBUG): logger.debug("Resetting curve: {}".format(curve))
        curve.reset()
    return True
  return op


class MoveAxisTo:
  def __call__(self, event):
    if self.axis_ is not None:
      self.axis_.move(self.value_, False)
    return True

  def set_value(self, value):
    self.value_ = value

  def __init__(self, axis, value):
    self.axis_, self.value_ = axis, value


class MoveAxisBy:
  def __call__(self, event):
    if self.axis_ is not None:
      value = self.value_
      if self.valueFunc_ is not None:
        value = self.valueFunc_(value)
      if self.stopAt_ is not None:
        current = self.axis_.get()
        proposed = current + value
        selected = select_nearest(current, proposed, self.stopAt_, False)
        if selected is not None:
          value = selected - current
      self.axis_.move(value, True)
    return True

  def set_value(self, value):
    self.value_ = value

  def __init__(self, axis, value, stopAt=None, valueFunc=None):
    self.axis_, self.value_, self.stopAt_, self.valueFunc_ = axis, value, stopAt, valueFunc


class MoveAxisValueSetter:
  def __call__(self, value):
    if self.moveAxis_ is not None:
      self.moveAxis_.set_value(value)
  def set_move_axis(self, moveAxis):
    self.moveAxis_ = moveAxis
  def __init__(self, moveAxis=None):
    self.moveAxis_ = moveAxis


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


def SetButtonState(odev, button, state):
  def op(event):
    odev.set_button_state(button, state)
    if logger.isEnabledFor(logging.DEBUG): logger.debug("Setting {} key {} (0x{:X}) to {}".format(odev, dtc2fn(None, codes.EV_KEY, button), button, state))
    return True
  return op


#Event processors (EPs for short)
class ClickEP:
  """Generates key click input events."""

  logger = get_logger(logger, "ClickEP")

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
      #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{} {}".format(event.code, event.value))
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
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{} created".format(log_loc(self)))

  def __del__(self):
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{} destroyed".format(log_loc(self)))
    pass


class HoldEvent(InputEvent):
  def __init__(self, k, value, timestamp, idev, modifiers, heldTime):
    InputEvent.__init__(self, codes.EV_KEY, k, value, timestamp, idev, modifiers)
    self.heldTime = heldTime


class HoldEP:
  """Generates key hold input events."""

  logger = get_logger(logger, "HoldEP")

  KeyDesc = collections.namedtuple("KeyDesc", "idev code modifiers")
  HT = collections.namedtuple("HT", "keyDesc period value num")

  def __call__(self, event):
    if event.type == codes.EV_BCT and event.code == codes.BCT_INIT:
      self.clear()
    elif event.type == codes.EV_KEY:
      if event.value == 0:
        for i in range(len(self.keyData_)):
          kd = self.keyData_[i]
          #ignore modifiers to correctly process key release if the key is modifier itself
          keyDesc = HoldEP.KeyDesc(event.idev, event.code, None)
          if self.match_(kd.keyDesc, keyDesc):
            self.keyData_[i] = None
        self.cleanup_()
      elif event.value == 1:
        class KD:
          pass
        keyDesc = HoldEP.KeyDesc(event.idev, event.code, tuple(m for m in event.modifiers))
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
          event = HoldEvent(keyDesc.code, ht.value, timestamp, keyDesc.idev, modifiers, heldTime)
          #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: {}".format(log_loc(self), event))
          self.next_(event)
        if kd.num > 0:
          kd.num = kd.num - 1
          if kd.num == 0:
            self.keyData_[i] = None
    self.cleanup_()

  def add(self, idev, code, modifiers, period, value, num):
    modifiers = tuple(m for m in modifiers) if modifiers is not None else None
    keyDesc = HoldEP.KeyDesc(idev, code, modifiers)
    ht = HoldEP.HT(keyDesc, period, value, num)
    self.holdTimes_.append(ht)

  def set_next(self, next):
    self.next_ = next
    return next

  def clear(self):
    self.keyData_ = []

  def __init__(self):
    self.next_, self.keyData_, self.holdTimes_ = None, [], []
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{} created".format(log_loc(self)))

  def __del__(self):
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{} destroyed".format(log_loc(self)))
    pass

  def match_(self, keyDesc, ht):
    return (ht.idev is None or (ht.idev == keyDesc.idev)) and (ht.code is None or (ht.code == keyDesc.code)) and (ht.modifiers is None or (ht.modifiers == keyDesc.modifiers))

  def cleanup_(self):
    while True:
      try:
        self.keyData_.remove(None)
      except ValueError:
        break


Modifier = collections.namedtuple("Modifier", "idev code")

def cmp_modifiers(eventModifier, referenceModifier):
  r = False
  if eventModifier.code == referenceModifier.code:
    if referenceModifier.idev is not None:
      r = eventModifier.idev == referenceModifier.idev
    else:
      r = True
  return r


class ModifierEP:
  """Adds modifier keys to input events."""

  logger = get_logger(logger, "ModifierEP")

  APPEND = 0
  OVERWRITE = 1

  def __call__(self, event):
    if event.type == codes.EV_BCT and event.code == codes.BCT_INIT and event.value == 0:
      self.clear()
    elif event.type == codes.EV_KEY:
      if self.addedModifiers_ is not None:
        em = Modifier(idev=event.idev, code=event.code)
        #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: got: {}".format(log_loc(self), em))
        for am in self.addedModifiers_:
          #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: checking against: {}".format(log_loc(self), am))
          if cmp_modifiers(em, am):
            #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: {} matched {}".format(log_loc(self), em, am))
            if event.value == 1 and em not in self.currentModifiers_:
              self.currentModifiers_.append(em)
            elif event.value == 0 and em in self.currentModifiers_:
              self.currentModifiers_.remove(em)
          else:
            #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: {} mismatched {}".format(log_loc(self), em, am))
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
    self.currentModifiers_, self.next_, self.addedModifiers_, self.removedModifiers_, self.saveModifiers_, self.mode_ = [], next, [], [], saveModifiers, mode
    if modifierDescs is not None:
      for md in modifierDescs:
        if md.state == True:
          self.addedModifiers_.append(Modifier(md.dev, md.code))
        elif md.state == False:
          self.removedModifiers_.append(Modifier(md.dev, md.code))


#TODO Unused. Remove?
class ScaleEP:
  """Scales value of relative axis input event."""
  def __call__(self, event):
    if event.type == codes.EV_REL:
      event.value *= 1.0 if self.sens_ is None else self.sens_.get(event.code, 1.0)
    return self.next_(event) if self.next_ is not None else False

  def set_next(self, next):
    self.next_ = next
    return next

  def __init__(self, sens):
    self.next_, self.sens_ = None, sens


class ScaleEP2:
  """Scales value of relative and absolute axis input events."""

  logger = get_logger(logger, "ScaleEP2")

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
          #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: keys:{}, old:{}, sens:{}, new:{}".format(log_loc(self), keys, oldValue, sens, event.value))
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
      self.logger.debug("No sens preinitialized for {}".format(htc2fn(*sc)))
    self.sens_[sc] = s

  def get_sens(self, sc):
    sens = self.sens_.get(sc, 0.0)
    return sens

  def get_name(self):
    return "" if self.name_ is None else self.name_

  def set_name(self, name):
    self.name_ = name

  def __init__(self, sens, keyOp = lambda event : (DevTypeCode(event.idev, event.type, event.code), DevTypeCode(None, event.type, event.code)), name = None):
    self.next_, self.sens_, self.keyOp_, self.name_ = None, sens, keyOp, name


#TODO Unused. Remove?
class SensSetEP:
  logger = get_logger(logger, "SensSetEP")

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

  def __init__(self, sensSets, keyOp = lambda event : (DevTypeCode(event.idev, event.type, event.code), DevTypeCode(None, event.type, event.code)), initial=0, makeName=lambda k : dtc2fn(*k)):
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


class MappingEP:
  """Maps events."""
  def __call__(self, event):
    frm = DevTypeCode(event.idev, event.type, event.code)
    to = self.mapping_.get(frm, None)
    if to is not None:
      event.idev, event.type, event.code = to.idev, to.type, to.code
    try:
      if self.next_ is not None:
        return self.next_(event)
    finally:
      if to is not None:
        event.idev, event.type, event.code = frm.idev, frm.type, frm.code

  def set_next(self, next):
    self.next_ = next
    return next

  def __init__(self, mapping):
    assert is_dict_type(mapping)
    self.mapping_ = mapping


#TODO Unused. Remove?
class CalibratingEP:
  logger = get_logger(logger, "CalibratingEP")

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

  def __init__(self, makeName=lambda k : dtc2fn(*k)):
    self.next_, self.sens_, self.mode_ = None, {}, 0
    self.makeName_ = makeName

  def process_event_(self, event):
    if self.next_ is not None:
      if event.type in (codes.EV_REL, codes.EV_ABS):
        sens = self.sens_.get((event.type, event.idev, event.code), 1.0)
        event.value *= sens
      return self.next_(event)
    else:
      return False

  def gather_data_(self, event):
    if event.type in (codes.EV_REL, codes.EV_ABS):
      k = (event.idev, event.type, event.code)
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
      #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: min:{}, max:{}, delta:{}".format(dtc2fn(k[1], k[0], k[2]), d.min, d.max, delta))
      logger.info("Sensitivity for {} is now {:+.5f}".format(self.makeName_(k), s))


#Event tests
class AttrsEventTest:
  logger = get_logger(logger, "AttrsEventTest")

  __slots__ = ("attrs_", "cmp_",)

  def __call__(self, event):
    for attrName, attrValue in self.attrs_:
      eventValue = getattr(event, attrName, None)
      if eventValue is None:
        #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: Event [{}] does not have attribute '{}'".format(log_loc(self), event, attrName))
        return False
      if not self.cmp_(attrName, eventValue, attrValue):
        #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: Mismatch while matching attrs {} with event [{}] at attr '{}' (got {}, needed {})".format(log_loc(self), c.attrs, event, attrName, eventValue, attrValue))
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


class BindEP:
  logger = get_logger(logger, "BindEP")

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
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: processing {})".format(log_loc(self), event))
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
        #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: Event [{}] matched by op {}".format(log_loc(self), event, c.op))
        for ci in c.children:
          #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("Sending event [{}] to {}".format(str(event), ci.child))
          processed = ci.child(event) or processed
    return processed

  def add(self, op, child, level=0, name=None):
    """Adds one child for given op and level."""
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: Adding child {} to {} for level {}".format(log_loc(self), child, op, level))
    assert(child is not None)
    for ci in self.children_:
      if op == ci.op and level == ci.level:
        ci.children.append(self.ChildInfo(child, name))
        break
    else:
      self.children_.append(self.ChildrenInfo(op, level, [self.ChildInfo(child, name)]))
    self.dirty_ = True
    #TODO Remove?
    return child

  def add_several(self, op, children, level=0, names=None):
    """Adds several children for given op and level."""
    if names is None:
      names = (None for i in range(len(children)))
    elif len(names) != len(children):
        raise RuntimeError("children and names lenghts must be equal")
    childInfos = [self.ChildInfo(child, name) for child,name in zip(children, names)]
    for ci in self.children_:
      if op == ci.op and level == ci.level:
        ci.children.extend(childInfos)
        break
    else:
      self.children_.append(self.ChildrenInfo(op, level, childInfos))
    self.dirty_ = True

  def clear(self):
    del self.children_[:]

  def get(self, name):
    """Returns binding proxy that returns ed op on .get("on") and output action or ep on .get("do").
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
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{} created".format(log_loc(self)))

  def __del__(self):
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{} destroyed".format(log_loc(self)))
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
  KEY_ANY matches all keys (from given idev if idev is specified),
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
          idevFound = am.dev is None or am.dev == em.idev
          codeFound = am.code == codes.KEY_ANY or am.code == em.code
          found = idevFound and codeFound
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


class StateEP:
  logger = get_logger(logger, "StateEP")

  def __call__(self, event):
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: processing event: {}, state: {}, next: {}".format(log_loc(self), event, self.state_, self.next_))
    if (self.state_ == True) and (self.next_ is not None):
      return self.next_(event)
    else:
      return False

  def set_state(self, state):
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: setting state to {}".format(log_loc(self), state))
    self.state_ = state
    if self.next_:
      self.next_(Event(codes.EV_BCT, codes.BCT_INIT, 1 if state == True else 0, time.time()))

  def get_state(self):
    return self.state_

  def set_next(self, next):
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: setting next to {}".format(log_loc(self), next))
    self.next_ = next
    return next

  def __init__(self):
    self.next_ = None
    self.state_ = False


def SetState(stateEP, state):
  def op(event):
    if stateEP.get_state() == state:
      if logger.isEnabledFor(logging.DEBUG): logger.debug("SetState.op() not setting {} state".format(stateEP))
      return False
    else:
      if logger.isEnabledFor(logging.DEBUG): logger.debug("SetState.op() setting {} state to {}".format(stateEP, state))
      stateEP.set_state(state)
      return True
  return op


def ToggleState(stateEP):
  def op(event):
    stateEP.set_state(not stateEP.get_state())
    if logger.isEnabledFor(logging.DEBUG): logger.debug("{} state is {}".format(stateEP, stateEP.get_state()))
    return True
  return op


class FilterEP:
  logger = get_logger(logger, "FilterEP")

  def __call__(self, event):
   #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: processing event: {}, next: {}".format(log_loc(self), event, self.next_))
   if self.next_ is not None and self.op_(event) == True:
     return self.next_(event)
   else:
     return False

  def set_next(self, next):
   #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: setting next to {}".format(log_loc(self), next))
   self.next_ = next
   return next

  def set_op(self, op):
    self.op_ = op

  def __init__(self, op=lambda event: True, next=None):
   self.op_, self.next_ = op, next


class IDevFilterOp:
  def __call__(self, event):
    return not (not self.state_ and getattr(event, "idev", None) in self.idevs_)

  def set_state(self, state):
   self.state_ = state

  def get_state(self):
   return self.state_

  def __init__(self, idevs, state=True):
    self.idevs_, self.state_ = [get_dev_hash(s) for s in idevs], state


class ModeInitEvent(Event):
  def __str__(self):
    return Event.__str__(self) + ", other: {}".format(self.other)

  def __init__(self, state, timestamp=None, other=None):
    if timestamp is None:
      timestamp = time.time()
    Event.__init__(self, codes.EV_BCT, codes.BCT_INIT, state, timestamp)
    self.other = other


class ModeEP:
  logger = get_logger(logger, "ModeEP")

  def __call__(self, event):
    #if event.type == codes.EV_BCT and event.code == codes.BCT_INIT:
    #  self.logger.debug("{}: Recieved init event: {}".format(log_loc(self), event.value))
    if self.mode_ is None:
      raise RuntimeError("{}: Initital mode was not set".format(self.name_))
    child = self.children_.get(self.mode_, None)
    if child is not None:
      return child(event)
    else:
      return False

  def set_mode(self, mode, report=True):
    if mode == self.mode_:
      return True
    if report:
      for cb in self.modeCallbacks_:
        cb(self, self.mode_, mode)
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}({}): Setting mode: {}".format(self.name_, self, mode))
    if mode not in self.children_:
      raise RuntimeError("{}: No such mode: {}".format(self.name_, mode))
    self.set_active_child_state_(0, mode)
    old = self.mode_
    self.mode_ = mode
    self.set_active_child_state_(1, old)
    return True

  def get_mode(self):
    return self.mode_

  def get_name(self):
    return self.name_

  def add(self, mode, child):
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: Adding child {} to  mode {}".format(log_loc(self), child, mode))
    if child is None:
      raise RuntimeError("Child is None")
    self.children_[mode] = child
    return child

  def get(self, modeName):
    return self.children_.get(modeName, None)

  def add_mode_callback(self, cb):
    self.modeCallbacks_.append(cb)

  def remove_mode_callback(self, cb):
    self.modeCallbacks_.remove(cb)

  def set_active_child_state_(self, state, other):
    if self.mode_ in self.children_:
      child = self.children_.get(self.mode_, None)
      if child is not None:
        #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: Notifying child {} about setting state to {}".format(log_loc(self), child, state))
        child(ModeInitEvent(state=state, other=other))

  def __init__(self, name="", reportModeSwitchCb=None):
    self.children_, self.mode_, self.name_ = {}, None, name
    self.modeCallbacks_ = []

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
      self.modeEP.set_mode(self.modes[self.i])
    return True

  def __init__(self, modeEP, modes, loop=True):
    self.i, self.modeEP, self.modes, self.loop = 0, modeEP, modes, loop


class SetMode:
  def __call__(self, event):
    self.modeEP.set_mode(self.mode)
    return True

  def __init__(self, modeEP, mode):
    self.modeEP, self.mode = modeEP, mode

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


class ModeEPModeManager:
  def save(self):
    self.mode_.append(self.ep_.get_mode())

  def restore(self, report=True):
    if len(self.mode_):
      self.ep_.set_mode(self.mode_.pop(), report)

  def add(self, mode, current, report=True):
    if current is None or self.ep_.get_mode() in current:
      self.mode_.append(mode)
      self.ep_.set_mode(mode, report)
      return True
    else:
      return False

  def remove(self, mode, current, report=True):
    if current is None or self.ep_.get_mode() in current:
      for i in range(len(self.mode_)-1, -1, -1):
        if self.mode_[i] == mode:
          self.mode_.pop(i)
          break;
      self.set_top_mode_(report)
      return True
    else:
      return False

  def swap(self, f, t, current, report=True):
    if current is None or self.ep_.get_mode() in current:
      for i in range(len(self.mode_)-1, -1, -1):
        if self.mode_[i] == f:
          self.mode_[i] = t
          break;
      self.set_top_mode_(report)
      return True
    else:
      return False

  def cycle_swap(self, modes, current, report=True):
    if current is None or self.ep_.get_mode() in current:
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
    if current is None or self.ep_.get_mode() in current:
      self.save_(save)
      self.ep_.set_mode(mode, report)
      return True
    else:
      return False

  def cycle(self, modes, step, loop, save, report=True):
    self.save_(save)
    m = self.ep_.get_mode()
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
    self.ep_.set_mode(m, report)
    return True

  def __init__(self, ep):
    self.ep_, self.mode_ = ep, []

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
      if m != self.ep_.get_mode():
        self.ep_.set_mode(m, report)

  def make_current_(self, current):
    if current is not None and not is_list_type(current):
      return [current]
    else:
      return current


class MultiCurveEP:
  def __call__(self, event):
    if event.type in (codes.EV_REL,):
      k = (event.idev, event.code)
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
  logger = get_logger(logger, "MCSThresholdOp")

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
            #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("Selecting {} over {}; dist:{}; thr:{}".format(j, self.selected_, self.distances_[j], self.thresholds_[j]))
            self.selected_ = j
            for k in self.distances_.keys():
              self.distances_[k] = 0.0
            break
          self.distances_[j] = threshold
      else:
        #When subtracting from total distances of other axes, clamp to 0
        self.distances_[j] -= cd
        self.distances_[j] = max(self.distances_[j], 0.0)
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{} {} {} {}".format(candidate, cd, self.distances_, self.selected_))
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
    self.update_points_()
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

  def set_points(self, points):
    self.points_ = points
    self.update_points_()

  def get_points(self):
    self.update_points_()
    return zip(self.x_, self.y_)

  def __init__(self, points, factor=1.0, clampLeft=False, clampRight=False, tracker=None):
    self.points_ = points
    self.factor_ = factor
    self.clampLeft_, self.clampRight_ = clampLeft, clampRight
    self.tracker_ = tracker
    self.x_, self.y_ = (), ()

  def update_points_(self):
    if self.points_ is None:
      return
    temp = [(float(d[0]), float(d[1])) for d in self.points_ if len(d) == 2]
    temp.sort(key = lambda d : d[0])
    if len(temp) == 0:
      self.x_, self.y_ = (), ()
    else:
      self.x_, self.y_ = zip(*temp)
    self.points_ = None

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
  logger = get_logger(logger, "BezierFunc")

  def __call__(self, x):
    l, r = self.points_[0][0], self.points_[len(self.points_)-1][0]
    x = clamp(x, l, r)
    #TODO Is this correct?
    t = (x - l) / (r - l)
    points = [p for p in self.points_]
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: points: {}, t: {}".format(log_loc(self), points, t))
    y = calc_bezier(points, t)[1]
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: result: {: .3f}".format(log_loc(self), y))
    if self.tracker_ is not None:
      self.tracker_({ "caller" : self, "x" : x, "y" : y })
    return y

  def set_points(self, points):
    self.points_ = points

  def get_points(self):
    return self.points_

  def __init__(self, points, tracker=None):
    self.points_ = tuple((p[0],p[1]) for p in points)
    self.tracker_ = tracker


class SegmentedBezierFunc:
  logger = get_logger(logger, "SegmentedBezierFunc")

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

    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: points: {}".format(log_loc(self), points))
    y = calc_bezier(points, t)[1]
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: t: {: .3f}, result: {: .3f}".format(log_loc(self), t, y))
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
    sx, ax = sign(x), abs(x)
    y = (sx*f(ax) - sx*fDB)/(1.0 - fDB) if ax > self.deadband_ else 0.0
    y *= self.factor_
    y += self.offset_
    if self.tracker_ is not None:
      self.tracker_({ "caller" : self, "x" : x, "y" : y })
    return y

  def __init__(self, degree, weight, deadband, factor, offset, tracker):
    self.degree_, self.weight_, self.deadband_, self.offset_, self.factor_, self.tracker_ = degree, weight, deadband, offset, factor, tracker


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
class ProbingAxisMixin:
  def probe(self, v, relative):
    """
    Checks whether can move to/by v.
    Arguments:
      v - desired absolute/relative axis position
      relative - False if v is absolute, True if relative
    Returns:
      clamped absolute/relative axis positon
    """
    value = self.get() if relative == True else 0.0
    return clamp(value + v, *self.limits()) - value


class JoystickAxis(ProbingAxisMixin):
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


class JoystickButtonAxis(ProbingAxisMixin):
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


class ReportingAxis(ProbingAxisMixin):
  logger = get_logger(logger, "ReportingAxis")

  def move(self, v, relative):
    old = self.next_.get()
    r = self.next_.move(v, relative)
    new = self.next_.get()
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug(("{}: {} -> {}".format(log_loc(self), old, new)))
    dirty = False
    for c in self.listeners_:
      if c() is None:
        #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: Listener {} has been removed".format(log_loc(self), c))
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
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: Adding listener {}".format(log_loc(self), listener))
    self.listeners_.append(weakref.ref(listener))

  def remove_listener(self, listener):
    try:
      self.listeners_.remove(listener)
    except ValueError:
      raise RuntimeError("Listener {} not registered".format(listener))

  def remove_all_listeners(self):
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: Removing all listeners, number of listeners: {}".format(log_loc(self), len(self.listeners_)))
    self.listeners_ = []

  def __init__(self, next):
    assert(next is not None)
    self.next_, self.listeners_ = next, []
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{} created".format(log_loc(self)))

  def __del__(self):
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{} destroyed".format(log_loc(self)))
    pass

  def cleanup_(self):
    i = 0
    while i < len(self.listeners_):
      if self.listeners_[i]() is None:
        self.listeners_.pop(i)
        continue
      else:
        i += 1


class RateSettingAxis(ProbingAxisMixin):
  logger = get_logger(logger, "RateSettingAxis")

  def move(self, v, relative):
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: moving to {} {}".format(log_loc(self), v, "relative" if relative else "absolute"))
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


#Filters
class ExpFilter:
  def calc(self, y, x=None):
    if self.y_ is None:
      self.y_ = y
    else:
      self.y_ = self.weight_ * y + (1.0 - self.weight_) * self.y_
    return self.y_

  def reset(self):
    self.y_ = None

  def __init__(self, weight=1.0):
    self.weight_, self.y_ = weight, None


class PolyApproxFilter:
  def calc(self, y, x):
    self.approx_.append(x, y)
    ddx = x - self.delay_
    return self.approx_.calc(ddx)

  def reset(self):
    self.approx_.clear()

  def __init__(self, degree, numSamples, delay=0.0):
    #sample is [timestamp, axis_value]
    #for numerical stability sample is converted in-place to [dt, axis_value]
    #when computing polynomial coeffs in PolynomialApproximator
    #dt is timestamp - oldest_timestamp_in_samples
    def get_sample(samples, i, k):
      r = samples[i][k]
      if k == 0:
        r -= samples[0][0]
      return r
    def conv_x(samples, x):
      if len(samples) == 0:
        raise IndexError("samples buffer is empty, so cannot adjust x")
      return x - samples[0][0]
    self.approx_ = PolynomialApproximator(degree, numSamples, get_sample, conv_x)
    self.delay_ = delay


class FilterOp:
  def calc(self, value, timestamp):
    if self.next_ is not None:
      value = self.next_.calc(value, timestamp)
    assert self.filter_ is not None
    return self.filter_.calc(value, timestamp)

  def reset(self):
    if self.next_ is not None:
      self.next_.reset()
    assert self.filter_ is not None
    self.filter_.reset()

  def __init__(self, filter_, next_=None):
    if filter_ is None:
      raise ValueError("filter must not be None")
    self.next_, self.filter_ = next_, filter_


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
  logger = get_logger(logger, "InputBasedCurve2")

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
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: on_move_axis({}, {}, {})".format(log_loc(self), axis, old, new))
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
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: resetting".format(log_loc(self)))
    if not axisMoved or (axisMoved and self.resetOpsOnAxisMove_):
      #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: resetting ops".format(log_loc(self)))
      self.inputOp_.reset()
      self.outputOp_.reset()
      self.deltaOp_.reset()
    self.inputValue_ = self.inputOp_.calc(self.axis_.get())
    self.busy_, self.dirty_ = False, False


class IterativeInputOp:
  logger = get_logger(logger, "IterativeInputOp")

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
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: Found root {} for value {} in {} steps; delta: {}; limits: {}".format(log_loc(self), mInputValue, outputValue, i, delta, inputValueLimits))
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
        raise RuntimeError("{}: Wrong interval [{}, {}] for value {}".format(log_loc(self), self.ovs_[ie-1], self.ovs_[ie], outputValue))
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
  logger = get_logger(logger, "LookupOp")

  def calc(self, outputValue):
    ie = self.fill_(outputValue)
    ob, oe = self.ovs_[ie-1], self.ovs_[ie]
    if not (ob <= outputValue and outputValue <= oe):
      raise RuntimeError("Wrong interval [{}, {}] for value {} (ie: {}; ivs: {}; ovs: {})".format(ob, oe, outputValue, ie, self.ivs_, self.ovs_))
    ivLimits = (self.ivs_[ie-1], self.ivs_[ie])
    inputValue = self.inputOp_.calc(outputValue, ivLimits)
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug( "{}: found inputValue {:0.3f} for outputValue {:0.3f} (ivLimits: {}; ivs: {}; ovs: {})" .format(log_loc(self), inputValue, outputValue, ivLimits, self.ivs_, self.ovs_))
    return inputValue

  def reset(self):
    self.inputOp_.reset()
    self.outputOp_.reset()

  def __init__(self, inputOp, outputOp, inputStep=0.1, inputLimits=None, expandLimits=False):
    if inputLimits is None:
      expandLimits = True
      inputLimits = [0.0, inputStep]
    else:
      inputLimits = list(inputLimits)
    if inputLimits[0] > inputLimits[1]:
      inputLimits[0], inputLimits[1] = inputLimits[1], inputLimits[0]
    self.inputOp_, self.outputOp_, self.inputStep_, self.expandLimits_ = inputOp, outputOp, inputStep, expandLimits
    self.inputStep_, self.inputLimits_, self.expandLimits_ = inputStep, inputLimits, expandLimits
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
        #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: outputValue {:0.3f}: inserting iv: {:0.3f}, ov: {:0.3f}".format(log_loc(self), outputValue, iv, ov))
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
        #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: outputValue {:0.3f}: inserting iv: {:0.3f}, ov: {:0.3f}".format(log_loc(self), outputValue, iv, ov))
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
      raise RuntimeError("Requested input value {: 0.3f} is out of input limits [{: 0.3f}, {: 0.3f}]".format(iv, *self.inputLimits_))


class FuncOp:
  def calc(self, value, timestamp=None):
    return self.func_(value)
  def reset(self):
    pass
  def __init__(self, func):
    self.func_ = func


class ReturnValueInputOp:
  def calc(self, value, timestamp=None):
    return value

  def reset(self):
    pass

  def __init__(self):
    pass


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
  logger = get_logger(logger, "CombineDeltaOp")

  def calc(self, x, timestamp):
    r = None
    for op in self.ops_:
      r = op.calc(x, timestamp) if r is None else self.combine_(r, op.calc(x, timestamp))
    return r
  def reset(self):
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: resetting".format(log_loc(self)))
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
  logger = get_logger(logger, "AccumulateDeltaOp")

  def calc(self, x, timestamp):
    for op in self.ops_:
      self.distance_ = op.calc(self.distance_, x, timestamp)
    self.distance_ += x
    return self.func_(self.distance_) if self.func_ is not None else self.distance_
  def reset(self):
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: resetting".format(log_loc(self)))
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
  logger = get_logger(logger, "DeadzoneDeltaOp")

  def calc(self, x, timestamp):
    """Returns 0 while inside deadzone radius, x otherwise."""
    s = sign(x)
    if self.s_ != s:
      self.s_, self.sd_ = s, 0.0
    if self.sd_ is not None:
      self.sd_ += abs(x)
      if self.sd_ > self.deadzone_:
        x = s*(self.sd_ - self.deadzone_)
        self.sd_ = None
      else:
        return 0.0
    return self.next_.calc(x, timestamp)
  def reset(self):
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: resetting".format(log_loc(self)))
    self.s_, self.sd_ = 0, 0.0
    self.next_.reset()
  def __init__(self, next, deadzone=0.0):
    self.sd_, self.s_, self.next_, self.deadzone_ = 0.0, 0, next, deadzone


#distance-delta ops
class SignDistanceDeltaOp:
  logger = get_logger(logger, "SignDistanceDeltaOp")

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
        #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: leaved deadzone, changing sign from {} to {}".format(log_loc(self), self.s_, s))
        self.localDistance_, self.s_, factor = 0.0, s, 0.0
    elif self.localDistance_ != 0.0:
      self.localDistance_ = 0.0
    r = distance if self.next_ is None else self.next_.calc(distance, delta, timestamp)
    return factor * r
  def reset(self):
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: resetting".format(log_loc(self)))
    self.s_, self.localDistance_ = 0, 0.0
    if self.next_:
      self.next_.reset()
  def __init__(self, deadzone=0.0, next=None):
    self.next_, self.deadzone_ = next, deadzone
    self.localDistance_, self.s_ = 0.0, 0


class TimeDistanceDeltaOp:
  logger = get_logger(logger, "TimeDistanceDeltaOp")

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
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: factor:{:.3f}".format(log_loc(self), factor))
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
  logger = get_logger(logger, "AccumulateRelChainCurve")

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
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: value_:{:+.3f}".format(log_loc(self), self.value_))
    return self.value_

  def reset(self):
    self.reset_self_()
    self.next_.reset()
    self.dirty_ = False

  def on_move_axis(self, axis, old, new):
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}.on_move_axis({}, {:+0.3f}, {:+0.3f})".format(log_loc(self), axis, old, new))
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
      #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: recalculated value_: {:+0.3f}".format(log_loc(self), self.value_))
      self.dirty_ = False


class DeltaRelChainCurve:
  logger = get_logger(logger, "DeltaRelChainCurve")

  def move_by(self, x, timestamp):
    """x is relative."""
    self.update_()
    self.value_ = self.valueDDOp_.calc(self.value_, x, timestamp)
    self.value_ = self.combineValue_(self.value_, x)
    factor = self.outputOp_.calc(self.value_)
    delta = self.deltaDDOp_.calc(self.value_, x, timestamp)
    delta = self.combineDelta_(delta, factor)
    originalX, originalDelta = x, delta
    actualDelta = self.next_.move_by(delta, timestamp)
    n = 0
    while n < 50:
      if abs(actualDelta - delta) < self.eps_:
        if n > 0:
          #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug( "{} orig x:{: 0.3f}; adj x:{: 0.3f}; orig delta:{: 0.3f}; adj delta:{: 0.3f}; n:{}" .format(log_loc(self), originalX, x, originalDelta, delta, n))
          pass
        break
      n += 1
      x *= actualDelta / delta
      delta = self.combineDelta_(self.deltaDDOp_.calc(self.value_, x, timestamp), factor)
    return x

  def reset(self):
    if self.next_ is not None and self.resetNext_ == True:
      self.next_.reset()
    self.reset_self_()

  def on_move_axis(self, axis, old, new):
    self.dirty_ = True
    self.next_.on_move_axis(axis, old, new)

  def get_value(self):
    self.update_()
    return self.value_

  def set_next(self, next):
    self.next_ = next

  def __init__(self, next, valueDDOp, deltaDDOp, outputOp, combineValue, combineDelta, resetOnMoveAxis, resetNext=True, eps=1e-4):
    self.next_, self.valueDDOp_, self.deltaDDOp_, self.outputOp_ = next, valueDDOp, deltaDDOp, outputOp
    self.combineValue_, self.combineDelta_ = combineValue, combineDelta
    self.resetOnMoveAxis_, self.resetNext_ = resetOnMoveAxis, resetNext
    self.value_, self.dirty_ = 0.0, False
    self.eps_ = eps

  def reset_self_(self):
    self.valueDDOp_.reset()
    self.deltaDDOp_.reset()
    self.outputOp_.reset()
    self.value_ = 0.0
    self.dirty_ = False

  def update_(self):
    if self.dirty_ == True:
      if self.resetOnMoveAxis_ == True:
        self.reset_self_()
      self.dirty_ = False


class FullDeltaRelChainCurve:
  logger = get_logger(logger, "FullDeltaRelChainCurve")

  def move_by(self, x, timestamp):
    """x is relative."""
    if x == 0.0:
      return 0.0
    #update if needed
    self.update_()
    #adjust stored input value (i.e. set to 0.0 if delta has changed sign, or on timeout)
    inputValue = self.inputValueDDOp_.calc(self.inputValue_, x, timestamp)
    #  if input value was adjusted, compute new stored output value
    if inputValue != self.inputValue_:
      self.outputValue_ = self.outputValueOp_.calc(inputValue)
      self.inputValue_ = inputValue
    #adjust input delta (for sens etc.)
    inputDelta = self.inputDeltaDDOp_.calc(self.inputValue_, x, timestamp)
    if inputDelta is None or inputDelta == 0.0:
      return 0.0
    #assumes that inputDelta == 0.0 for x == 0.0, might not always be the case
    deltaFactor = inputDelta / x
    #add input delta to stored input value
    inputValue = self.inputValue_ + inputDelta
    #compute new output value
    outputValue = self.outputValueOp_.calc(inputValue)
    if outputValue is None:
      return 0.0
    #compute output delta
    outputDelta = outputValue - self.outputValue_
    #call next
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug( "{} x:{: 0.3f}; iv:{: 0.3f}; id:{: 0.3f}; df:{: 0.3f}" .format(log_loc(self), x, inputValue, inputDelta, deltaFactor))
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug( "{} old ov:{: 0.3f}; ov:{: 0.3f}; od:{: 0.3f}" .format(log_loc(self), self.outputValue_, outputValue, outputDelta))
    actualOutputDelta = self.next_.move_by(outputDelta, timestamp)
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug( "{} od:{: 0.3f}; aod:{: 0.3f}" .format(log_loc(self), outputDelta, actualOutputDelta))
    #recalculate values and deltas backward if needed
    if abs(actualOutputDelta - outputDelta) > 1e-6:
      outputValue = self.outputValue_ + actualOutputDelta
      inputValue = self.inputValueOp_.calc(outputValue)
      inputDelta = inputValue - self.inputValue_
      assert deltaFactor != 0.0
      x = inputDelta / deltaFactor
      #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug( "{} recalculated x:{: 0.3f}; id:{: 0.3f}; iv:{: 0.3f}; ov:{: 0.3f}" .format(log_loc(self), x, inputDelta, inputValue, outputValue))
    self.inputValue_, self.outputValue_ = inputValue, outputValue
    #return x, adjusted or not
    return x

  def reset(self):
    if self.next_ is not None and self.resetNext_ == True:
      #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{} resetting next".format(log_loc(self)))
      self.next_.reset()
    else:
      #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{} not resetting next".format(log_loc(self)))
      pass
    self.reset_self_()

  def on_move_axis(self, axis, old, new):
    self.dirty_ = True
    if self.next_ is not None:
      self.next_.on_move_axis(axis, old, new)

  def get_value(self):
    self.update_()
    return self.inputValue_

  def set_next(self, next):
    self.next_ = next

  def __init__(self, next, inputValueDDOp, inputDeltaDDOp, outputValueOp, inputValueOp, resetOnMoveAxis, resetNext=True):
    """
    next: Next curve (relative).
    inputValueDDOp: Adjusts input value based on current input value, input delta and timestamp. Is reset on call to reset(), so can have state.
    inputDeltaDDOp: Adjusts input delta based on current input value, input delta and timestamp. Is reset on call to reset(), so can have state.
    outputValueOp: Computes output value from input value. Is not reset on call to reset(), so supposed to be stateless.
    inputValueOp: Inverse of outputValueOp: computes input value from output value. Supposed to be stateless.
    resetOnMoveAxis: If True, curve will be reset after call to on_move_axis().
    """
    self.next_, self.inputValueDDOp_, self.outputValueOp_, self.inputValueOp_, self.inputDeltaDDOp_ = \
      next, inputValueDDOp, outputValueOp, inputValueOp, inputDeltaDDOp
    self.resetOnMoveAxis_, self.resetNext_ = resetOnMoveAxis, resetNext
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
    """
    Moves this (and next) curve by x.
    Returns:
      The value this curve has moved by.
    """
    v = self.get_value()
    return self.next_.move(v + x, timestamp) - v

  def move(self, x, timestamp):
    """
    Moves this (and next) curve to x.
    Returns:
      The value this curve has moved to.
    """
    return self.next_.move(x, timestamp)

  def probe_by(self, x):
    """
    Probes whether can move this curve by x without actually moving it.
    Returns:
      The value this curve can move by.
    """
    v = self.get_value()
    return self.probe(v + x) - v

  def probe(self, x):
    """
    Probes whether can move this curve by x without actually moving it.
    Returns:
      The value this curve can move to.
    """
    return self.next_.probe(x)

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


class AbsToRelChainCurve:
  """
  Converts absolute movement along an axis to relative.
  """

  logger = logger.getChild("AbsToRelChainCurve")

  NEXT_NONE = 0
  NEXT_REL = 1
  NEXT_ABS = 2
  NEXT_BOTH = 3

  def move_by(self, x, timestamp):
    """
    Moves this curve by x.
    """
    if self.value_ is None:
      raise RuntimeError("value was not set")
    value = clamp(self.value_ + x, *self.get_limits())
    delta = value - self.value_
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{} x:{: 0.3f}; old v:{: 0.3f}; v:{: 0.3f}; dv:{: 0.3f}".format(log_loc(self), x, self.value_, value, delta))
    r = 0.0
    if delta != 0.0:
      if self.state_ == True:
        if self.nextRelative_ is not None:
          r = self.nextRelative_.move_by(delta, timestamp)
      else:
        if self.nextAbsolute_ is not None:
          r = self.nextAbsolute_.move_by(delta, timestamp)
      self.value_ += r
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{} r:{: 0.3f}".format(log_loc(self), r))
    return r

  def move(self, x, timestamp):
    """
    Moves this curve to x.
    """
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}.move() x:{}".format(self, x))
    x = clamp(x, *self.get_limits())
    if self.value_ is None:
      self.value_ = x
    delta = x - self.value_
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{} x:{: 0.3f}; old v:{: 0.3f}; v:{: 0.3f}; dv:{: 0.3f}".format(log_loc(self), x, self.value_, value, delta))
    r = 0.0
    if self.state_ == True:
      if self.nextRelative_ is not None and delta != 0.0:
        r = self.nextRelative_.move_by(delta, timestamp)
        r += x
    else:
      if self.nextAbsolute_ is not None:
        r = self.nextAbsolute_.move(x, timestamp)
    self.value_ = r
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{} r:{: 0.3f}".format(log_loc(self), r))
    return r

  def reset(self):
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}".format(log_loc(self)))
    if self.resetNext_ & self.NEXT_REL == True:
      #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: resetting next relative".format(log_loc(self)))
      if self.nextRelative_ is not None:
        self.nextRelative_.reset()
    if self.resetNext_ & self.NEXT_ABS == True:
      #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: resetting next absolute".format(log_loc(self)))
      if self.nextAbsolute_ is not None:
        self.nextAbsolute_.reset()
    self.head_().set_busy(True)
    try:
      #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}.reset(): moving next absolute to {}".format(self, self.value_))
      if self.nextAbsolute_ is not None:
        self.nextAbsolute_.move(self.value_, time.time())
    finally:
      self.head_().set_busy(False)

  def on_move_axis(self, axis, old, new):
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}.on_move_axis() {} {} {}".format(self, axis, old, new))
    if self.nextRelative_ is not None:
      self.nextRelative_.on_move_axis(axis, old, new)
    if self.nextAbsolute_ is not None:
      self.value_ = self.nextAbsolute_.get_value()

  def get_value(self):
    return self.value_

  def get_limits(self):
    return self.limits_

  def set_state(self, state):
    self.state_ = state

  def get_state(self):
    return self.state_

  def set_next(self, next, which=1):
    if which == self.NEXT_REL:
      self.nextRelative_ = next
    elif which == self.NEXT_ABS:
      self.nextAbsolute_ = next
    else:
      raise ValueError(which)

  def __init__(self, head, nextRelative, nextAbsolute, state=True, resetNext=1, limits=None):
    #head is AxisTrackerChainCurve
    #nextRelative is FullDeltaRelChainCurve, nextAbsolute is RelToAbsChainCurve
    self.head_ = weakref.ref(head)
    self.nextRelative_, self.nextAbsolute_ = nextRelative, nextAbsolute
    self.value_ = None
    self.state_ = state
    self.resetNext_ = resetNext
    if limits is None:
      limits = (-float("inf"), float("inf"))
    self.limits_ = limits


class TransformAbsChainCurve:
  logger = get_logger(logger, "TransformAbsChainCurve")

  def move(self, x, timestamp):
    """Moves current curve to x and next curve to transformed value."""
    self.update_()
    outputValue = self.outputOp_.calc(x, timestamp)
    actualOutputValue = self.next_.move(outputValue, timestamp)
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: x:{:+.3f}, ov:{:+.3f}, aov:{:+.3f}".format(log_loc(self), x, outputValue, actualOutputValue))
    if actualOutputValue != outputValue and self.allowOffLimits_ == False:
      #TODO If outputOp_.calc() changes state of outputOp_, and this state corellates with outputValue,
      #TODO but curve is set to actualOutputValue, then outputOp_ is out of sync.
      #TODO Mb replace outputOp_ and inputOp_ with funcs
      #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: aov != ov".format(log_loc(self)))
      #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: wanted outputValue {:+.6f}, got {:+.6f}".format(log_loc(self), outputValue, actualOutputValue))
      self.value_ = self.inputOp_.calc(actualOutputValue)
      #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: recalculated value_:{:+.6f}".format(log_loc(self), self.value_))
    else:
      self.value_ = x
    return self.value_

  #TODO Remove since it's abs curve?
  #move_by() is deliberately implemented via move() to avoid out-of-sync situations
  #when allowOffLimits_ == True and value_ is out of limits of next_ curve
  def move_by(self, x, timestamp):
    v = self.get_value()
    return self.move(v + x) - v

  def probe(self, x):
    """
    Probes whether can move this curve to x without actually moving it.
    Returns:
      The value this curve can move to.
    """
    #Assuming this call to calc() does not change outputOp_ state.
    outputValue = self.outputOp_.calc(x)
    newOutputValue = self.next_.probe(outputValue)
    if newOutputValue != outputValue and self.allowOffLimits_ == False:
      return self.inputOp_.calc(newOutputValue)
    else:
      return x

  #TODO Remove since it's abs curve?
  #probe_by() is deliberately implemented via probe() to avoid out-of-sync situations
  #when allowOffLimits_ == True and value_ is out of limits of next_ curve
  def probe_by(self, x):
    v = self.get_value()
    return self.probe(v + x) - v

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

  def __init__(self, next, inputOp, outputOp, resetOnMoveAxis=False, allowOffLimits=False):
    self.next_, self.inputOp_, self.outputOp_ = next, inputOp, outputOp
    self.resetOnMoveAxis_, self.allowOffLimits_ = resetOnMoveAxis, allowOffLimits
    self.value_, self.dirty_ = 0.0, False

  def update_(self):
    if self.dirty_ == True:
      if self.allowOffLimits_ == False:
        self.value_ = self.inputOp_.calc(self.next_.get_value())
        #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: recalculated value_: {:+0.3f}".format(log_loc(self), self.value_))
      if self.resetOnMoveAxis_ == True:
        self.reset()
      self.dirty_ = False


class UnlinkableAbsChainCurve:
  logger = get_logger(logger, "UnlinkableAbsChainCurve")

  def move(self, x, timestamp):
    """Moves current curve to x with offset."""
    r = 0.0
    if self.state_ == True:
      #self.value_ is actual output value; value is desired output value
      value = x + self.offset_
      #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: linked x:{: 0.3f}, off:{: 0.3f}, value:{: 0.3f}".format(log_loc(self), x, self.offset_, value))
      actualValue = self.next_.move(value, timestamp)
      self.value_ = actualValue if self.allowOffLimits_ == False else value
      r = x if value == self.value_ else self.value_ - self.offset_
    else:
      r = self.next_.probe(x)
      self.offset_ = self.value_ - r
      #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: unlinked x:{: 0.3f}, off:{: 0.3f}, value_:{: 0.3f}".format(log_loc(self), x, self.offset_, self.value_))
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: r:{: 0.3f}".format(log_loc(self), r))
    return r

  def probe(self, x):
    """
    Probes whether can move this curve to x without actually moving it.
    """
    return self.next_.probe(x + self.offset_) - self.offset_

  def reset(self):
    self.next_.reset()
    self.value_ = self.next_.get_value()
    self.offset_ = 0.0

  def on_move_axis(self, axis, old, new):
    self.next_.on_move_axis(axis, old, new)
    self.value_ = self.next_.get_value()
    self.offset_ = 0.0

  def get_value(self):
    return self.value_ - self.offset_

  def set_next(self, next):
    self.next_ = next
    if self.next_ is not None:
      self.value_ = self.next_.get_value()

  def set_state(self, state):
    self.state_ = state

  def get_state(self):
    return self.state_

  def __init__(self, next, state=True, allowOffLimits=False):
    self.next_ = next
    self.offset_, self.value_ = 0.0, 0.0
    if self.next_ is not None:
      self.value_ = self.next_.get_value()
    self.state_ = state
    self.allowOffLimits_ = allowOffLimits


class UpdatedChainCurve:
  logger = get_logger(logger, "UpdatedChainCurve")

  """Moves next curve to desired value during periodic updates."""
  MODE_RELATIVE = 0
  MODE_ABSOLUTE = 1

  def move_by(self, x, timestamp):
    """Adjusts desired value by x."""
    r = self.next_.probe_by(x)
    self.desiredValue_ += r
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: x:{: 6.3f}; timestamp:{}; desired:{: 6.3f}".format(log_loc(self), x, timestamp, self.desiredValue_))
    return r

  def move(self, x, timestamp):
    """Sets desired value to x."""
    self.desiredValue_ = self.next_.probe(x)
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: x:{: 6.3f}; timestamp:{}; desired:{: 6.3f}".format(log_loc(self), x, timestamp, self.desiredValue_))
    return self.desiredValue_

  def probe_by(self, x):
    """
    Probes whether can move this curve by x without actually moving it.
    Returns:
      The value this curve can move to.
    """
    return self.next_.probe_by(x)

  def probe(self, x):
    """
    Probes whether can move this curve to x without actually moving it.
    Returns:
      The value this curve can move to.
    """
    return self.next_.probe(x)

  def reset(self):
    self.op_.reset()
    self.next_.reset()
    self.desiredValue_ = self.next_.get_value()

  def on_move_axis(self, axis, old, new):
    if self.busy_ == True:
      return
    self.next_.on_move_axis(axis, old, new)
    self.desiredValue_ = self.next_.get_value()
    self.op_.reset()
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: new desired:{: 6.3f}".format(log_loc(self), self.desiredValue_))

  def get_value(self):
    return self.desiredValue_

  def update(self, tick, timestamp):
    if self.state_ == False:
      return
    currentValue = self.next_.get_value()
    desiredValue = self.desiredValue_
    if abs(currentValue - desiredValue) < 1e-6:
      return
    newValue = self.op_.calc(current=currentValue, desired=desiredValue, tick=tick, timestamp=timestamp)
    if self.head_ is not None:
      self.head_().set_busy(True)
    self.busy_ = True
    try:
      if self.mode_ == self.MODE_RELATIVE:
        self.next_.move_by(newValue-currentValue, timestamp)
      elif self.mode_ == self.MODE_ABSOLUTE:
        self.next_.move(newValue, timestamp)
      else:
        assert False, "Bad mode"
      #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug( "{}: curr:{: 6.3f}; des:{: 6.3f}; new:{: 6.3f}; next:{: 6.3f}" .format(log_loc(self), currentValue, desiredValue, newValue, self.next_.get_value()))
    finally:
      self.busy_ = False
      if self.head_ is not None:
        self.head_().set_busy(False)

  def set_next(self, next):
    self.next_ = next
    if self.next_ is not None:
      self.desiredValue_ = self.next_.get_value()

  def set_head(self, head):
    self.head_ = weakref.ref(head)

  def set_state(self, state):
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: state:{}".format(log_loc(self), state))
    self.state_ = state
    if state == True and self.next_ is not None:
      self.desiredValue_ = self.next_.get_value()

  def __init__(self, head, next, op, mode=0):
    """
    Arguments:
      head - AxisTrackerChainCurve instance at the top of this curve chain
      next - next curve in chain
      op - used to compute new value for next axis
      mode - how next curve is moved: MODE_RELATIVE or MODE_ABSOLUTE
    """
    self.head_ = weakref.ref(head)
    self.set_next(next)
    self.op_ = op
    self.mode_ = mode
    self.state_ = True
    self.desiredValue_ = 0.0
    self.busy_ = False


class DistanceUpdatedChainCurveOp:
  logger = get_logger(logger, "DistanceUpdatedChainCurveOp")

  def calc(self, **kwargs):
    current = kwargs.get("current")
    desired = kwargs.get("desired")
    tick = kwargs.get("tick")
    delta = desired - current
    s, absDelta = sign(delta), abs(delta)
    if self.desired_ is None:
      self.desired_ = desired
    desiredSpeed = (desired - self.desired_) / tick
    self.desired_ = desired
    if self.current_ is None:
      self.current_ = current
    currentSpeed = (current - self.current_) / tick
    self.current_ = current
    speed = self.func_(absDelta)
    assert speed >= 0.0
    if s != self.s_ or (absDelta < 0.0001 and abs(desiredSpeed) < 0.0001):
      self.speed_, self.s_ = 0.0, s
      self.desired_, self.current_ = None, None
    if self.keepSpeed_ == True:
      if speed < self.speed_:
        speed = self.speed_
      else:
        self.speed_ = speed
    step = speed*tick
    r = absDelta if absDelta < step else step
    r *= s
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug( "{}: desired: {:0.3f}; current: {:0.3f}; dspeed: {:0.3f}; cspeed: {:0.3f}; speed: {:0.3f}; r: {:0.3f}".format(log_loc(self), desired, current, desiredSpeed, currentSpeed, speed, r))
    return r + current

  def reset(self):
    self.speed_, self.s_ = 0.0, 0
    self.desired_, self.current_ = None, None

  def __init__(self, func, keepSpeed=False):
    self.func_, self.keepSpeed_ = func, keepSpeed
    self.speed_, self.s_ = 0.0, 0
    self.desired_, self.current_ = None, None


class AccelUpdatedChainCurveOp:
  logger = get_logger(logger, "AccelUpdatedChainCurveOp")

  def calc(self, **kwargs):
    current = kwargs.get("current")
    desired = kwargs.get("desired")
    tick = kwargs.get("tick")
    r = desired
    st = "hit"
    delta = desired - current
    sDelta, absDelta = sign(delta), abs(delta)
    if absDelta != 0.0:
      if self.sDelta_ is None:
        self.sDelta_ = sDelta
      if self.sDelta_ != sDelta:
        self.speed_, self.acceleration_, self.sDelta_ = self.minSpeed_, 0.0, sDelta
        #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{} flip".format(log_loc(self)))
      #Using internally stored speed, because cannot depend on speed
      #that is based on desired and current ((desired - current) / tick)
      speed, acceleration = self.speed_, self.accelerationFunc_(absDelta)
      assert acceleration >= 0.0
      if self.acceleration_ == 0.0:
        self.acceleration_ = acceleration
      if self.keepAcceleration_ == True:
        if acceleration < self.acceleration_:
          acceleration = self.acceleration_
        else:
          self.acceleration_ = acceleration
      st = "acc"
      #need to decelerate?
      assert self.minSpeed_ >= 0.0
      dspeed = speed - self.minSpeed_
      deceleration = 0.0
      if self.decelerationFunc_ is not None:
        deceleration = self.decelerationFunc_(absDelta)
      if deceleration != 0.0 and dspeed > 0.0001:
        assert deceleration > 0.0
        timeToStop = dspeed / deceleration
        deltaToStop = dspeed*timeToStop - 0.5*deceleration*timeToStop**2
        if abs(deltaToStop) > absDelta:
          #calculate actual deceleration
          timeToStop = 2.0*absDelta / dspeed
          deceleration = dspeed / timeToStop
          acceleration = -deceleration
          st = "dcc"
      #apply (positive or negative) acceleration
      assert speed >= 0.0
      speed += acceleration*tick
      #limit max speed if needed
      assert self.maxSpeed_ >= 0.0
      if self.maxSpeed_ != 0.0 and speed > self.maxSpeed_:
        speed = self.maxSpeed_
      if self.desired_ is None:
        self.desired_ = desired
      absDesiredSpeed = abs(desired - self.desired_) / tick
      self.desired_ = desired
      #don't overshoot desired
      #if self.minSpeed_ > 0.0, speed > 0.0 even if self.deceleration_ > 0.0
      if speed > 0.0:
        absStep = speed*tick
        if absDelta > absStep:
          r = sign(delta)*absStep + current
          self.speed_ = speed
        else:
          r = desired
          if absDesiredSpeed < 0.0001:
            self.speed_, self.acceleration_ = self.minSpeed_, 0.0
          st = "clp"
      else:
        #can get here only if decelerated too much
        r = desired
        self.speed_, self.acceleration_ = self.minSpeed_, 0.0
        st = "snp"
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{} {} speed:{: 6.3f}; accel:{: 6.3f}; curr:{: 6.3f}; desr:{: 6.3f}; r:{: 6.3f}".format(log_loc(self), st, self.speed_, self.acceleration_, current, desired, r))
    return r

  def reset(self):
    self.speed_ = self.minSpeed_
    self.acceleration_ = 0.0
    self.sDelta_ = None
    self.desired_ = None

  def __init__(self, accelerationFunc, decelerationFunc=None, minSpeed=0.0, maxSpeed=0.0, keepAcceleration=False):
    self.accelerationFunc_ = accelerationFunc
    self.decelerationFunc_ = decelerationFunc
    self.minSpeed_ = minSpeed
    self.maxSpeed_ = maxSpeed
    self.speed_ = minSpeed
    self.acceleration_ = 0.0
    self.keepAcceleration_ = keepAcceleration
    self.sDelta_ = None
    self.desired_ = None


class SensModUpdatedChainCurveOp:
  def calc(self, **kwargs):
    new = self.next_.calc(**kwargs)
    current = kwargs.get("current")
    step = new - current
    step *= self.func_(self.axis_.get())
    return step + current

  def reset(self):
    self.next_.reset()

  def __init__(self, next, func, axis):
    self.next_, self.func_, self.axis_ = next, func, axis


class AxisChainCurve:
  """Moves axis. Is meant to be at the bottom of chain."""

  logger = get_logger(logger, "AxisChainCurve")

  def move_by(self, x, timestamp):
    r = self.axis_.move(x, relative=True)
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: x:{: .3f}; r:{: .3f}; v:{: .3f}".format(log_loc(self), x, r, self.get_value()))
    return r

  def move(self, x, timestamp):
    r = self.axis_.move(x, relative=False)
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: x:{: .3f}; r:{: .3f}; v:{: .3f}".format(log_loc(self), x, r, self.get_value()))
    return r

  def probe_by(self, x):
    """
    Probes whether can move axis by x without actually moving it.
    Returns:
      The value axis can move to.
    """
    return self.axis_.probe(x, relative=True)

  def probe(self, x):
    """
    Probes whether can move axis to x without actually moving it.
    Returns:
      The value axis can move to.
    """
    return self.axis_.probe(x, relative=False)

  def reset(self):
    pass

  def on_move_axis(self, axis, old, new):
    pass

  def get_value(self):
    return self.axis_.get()

  def __init__(self, axis):
    self.axis_ = axis


class AxisTrackerChainCurve:
  """
  Prevents endless recursion on moving axis.
  Is meant to be at the top of chain.
  Subscribe as axis listener.
  """

  logger = get_logger(logger, "AxisTrackerChainCurve")

  def move_by(self, x, timestamp):
    """x is relative."""
    if self.state_ == False:
      return 0.0
    self.busy_ = True
    v = None
    try:
      v = self.next_.move_by(x, timestamp)
    except RuntimeError as e:
      self.logger.error("Can't move axis: {}".format(e))
    finally:
      self.busy_ = False
    return v

  def move(self, x, timestamp):
    """x is absolute."""
    if self.state_ == False:
      return 0.0
    self.busy_ = True
    v = None
    try:
      v = self.next_.move(x, timestamp)
    except RuntimeError as e:
      self.logger.error("Can't move axis: {}".format(e))
    finally:
      self.busy_ = False
    return v

  def reset(self):
    self.busy_ = False
    self.next_.reset()

  def on_move_axis(self, axis, old, new):
    #self.next_.on_move_axis() is called event if self.state_ == False
    #Since old and new are final axis position values, and if a curve in chain uses some intermediate value, 
    #it should call its next_.on_move_axis() and then next_.get_value() to get the updated value
    if self.busy_ == True:
      return
    self.next_.on_move_axis(axis, old, new)

  def get_value(self):
    return self.next_.get_value()

  def set_next(self, next):
    self.next_ = next

  def set_busy(self, busy):
    self.busy_ = busy

  def set_state(self, state):
    self.state_ = state
    for stateful in self.statefuls_:
      stateful.set_state(state)

  def get_state(self):
    return self.state_

  def add_stateful(self, stateful):
    self.statefuls_.append(stateful)

  def get(self, name):
    return self.objects_.get(name)

  def add(self, name, obj):
    self.objects_[name] = obj

  def __init__(self, next):
    self.next_ = next
    self.busy_ = False
    self.state_ = True
    self.statefuls_ = []
    self.objects_ = {}


class OffsetAbsChainCurve:
  logger = get_logger(logger, "OffsetAbsChainCurve")

  def move(self, x, timestamp):
    """x is absolute."""
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: x:{:+.3f}".format(log_loc(self), x))
    if self.value_ is not None:
      self.offset_ += (self.next_.get_value() - self.value_)
      self.value_ = None
    s = sign(x)
    if self.s_ != s:
      if self.s_ != 0:
        self.offset_ += self.x_
        #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: new offset_: {}".format(log_loc(self), self.offset_))
      self.s_ = s
    elif abs(x) < abs(self.x_):
      self.offset_ += self.x_ - x
      self.x_ = x
      return self.x_
    ox = x + self.offset_
    nox = self.next_.move(ox, timestamp)
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: ox:{:+.3f}, nox:{:+.3f}".format(log_loc(self), ox, nox))
    #nox can still be outside of next_ input limits, so have to store sign of x to be able to backtrack
    if nox == ox:
      #within limits
      if self.state_ == 1:
        self.sx_, self.state_ = 0, 0
      self.x_ = x
      #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: within limits, x: {}, x_: {}".format(log_loc(self), x, self.x_))
    else:
      #outside limits
      if self.state_ == 0:
        self.sx_, self.state_ = s, 1
      self.x_ = x if self.sx_ != s else (nox - self.offset_)
      #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: outside limits, x: {}, x_: {}".format(log_loc(self), x, self.x_))
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: offset_:{:+.3f}, x_:{:+.3f}".format(log_loc(self), self.offset_, self.x_))
    return self.x_

  def reset(self):
    self.next_.reset()
    self.s_, self.sx_, self.state_, self.x_, self.offset_ = 0, 0, 0, 0.0, self.next_.get_value()
    self.value_ = None

  def on_move_axis(self, axis, old, new):
    if self.value_ is None:
      self.value_ = self.next_.get_value()
    self.next_.on_move_axis(axis, old, new)
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: offset_:{:+.3f}, x_:{:+.3f}".format(log_loc(self), self.offset_, self.x_))

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
  """
  Directly links positions of 2 axes using func and offset.
  If controlled axis is moved externally by delta, adds this delta to offset.
  When resetting axes, reset controlling axis first, then controlled.
  """

  logger = get_logger(logger, "AxisLinker")

  def reset(self):
    controlledValue = self.controlledAxis_.get()
    controllingValue = self.controllingAxis_.get()
    desiredControlledValue = self.func_(controllingValue)
    self.offset_ = controlledValue - desiredControlledValue
    self.oldControlledValue_ = None
    self.dirty_ = False
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug( "{}: after reset: controlling: {:+0.3f}; controlled: {:+0.3f}; desired controlled: {:+0.3f}; offset: {:+0.3f}" .format(log_loc(self), controllingValue, controlledValue, desiredControlledValue, self.offset_))

  def set_state(self, state):
    self.state_ = state

  def get_state(self):
    return self.state_

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
    if self.busy_ == True:
      return
    if self.state_ == False:
      self.dirty_ = True
    else:
      self.update_()
      if axis == self.controlledAxis_:
        if self.oldControlledValue_ is None:
          self.oldControlledValue_ = old
        #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug( "{}: Controlled axis has moved to {:+0.3f}; oldControlledValue_: {:+0.3f}" .format(log_loc(self), new, self.oldControlledValue_))
      elif axis == self.controllingAxis_:
        if self.oldControlledValue_ is not None:
          self.offset_ += self.controlledAxis_.get() - self.oldControlledValue_
          self.oldControlledValue_ = None
        #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug( "{}: Controlling axis has moved to {:+0.3f}; offset_: {:+0.3f}" .format(log_loc(self), new, self.offset_))
        cv = self.func_(new)
        try:
          self.busy_= True
          desired = cv + self.offset_
          actual = self.controlledAxis_.move(desired, relative=False)
          #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug( "{}: Moving controlled axis: from: {:+0.3f}; desired: {:+0.3f}, actual: {:+0.3f}" .format(log_loc(self), self.controlledAxis_.get(), desired, actual))
          if actual != desired and self.adjustOffset_ == True:
            self.offset_ -= (desired - actual)
          #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: offset after move {:+0.3f}".format(log_loc(self), self.offset_))
        finally:
          self.busy_= False

  def __init__(self, controllingAxis, controlledAxis, func, adjustOffset=True):
    self.controllingAxis_, self.controlledAxis_, = controllingAxis, controlledAxis
    self.func_, self.adjustOffset_ = func, adjustOffset
    self.oldControlledValue_, self.offset_, self.busy_, self.dirty_, self.state_  = None, 0.0, False, False, False
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{} created".format(log_loc(self)))

  def __del__(self):
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{} destroyed".format(log_loc(self)))
    pass

  def update_(self):
    if self.dirty_ == True:
      self.reset()


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


class ToggleEP:
  def __call__(self, event):
    self.ep_.set_state(not self.ep_.get_state())
    return True

  def __init__(self, ep):
    self.ep_ = ep


class DeviceGrabberEP:
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
  logger = get_logger(logger, "SwallowDevices")

  def __call__(self, event):
    self.set_mode_(self.mode_)
    return True

  def __init__(self, devices, mode):
    self.mode_, self.devices_ = mode, devices
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{} created".format(log_loc(self)))

  def __del__(self):
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{} destroyed".format(log_loc(self)))
    pass

  def set_mode_(self, mode):
    for d in self.devices_:
      try:
        #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: setting swallow state {} to {}".format(log_loc(self), self.mode_, d))
        d.swallow(mode)
      except IOError as e:
        #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: got IOError ({}), but that was expected".format(log_loc(self), e))
        continue


class SwallowSource:
  logger = get_logger(logger, "SwallowSource")

  def __call__(self, event):
    for name,mode in self.deviceNamesAndModes_:
      try:
        #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: setting swallow state {} to {}".format(log_loc(self), mode, name))
        self.source_.swallow(name, mode)
      except (IOError, OSError) as e:
        #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: got exception ({}), but that was expected".format(log_loc(self), e))
        continue
    return True

  def __init__(self, source, deviceNamesAndModes):
    self.source_, self.deviceNamesAndModes_ = source, deviceNamesAndModes
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{} created".format(log_loc(self)))

  def __del__(self):
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{} destroyed".format(log_loc(self)))
    pass


class FreePIEHeadTrackerIDEV:
  """
  Input device that recieves orientation data sent over network
  from Android smartphone by FreePIE IMU app and translates them
  to absolute or relative events.
  FreePIE IMU is included into Opentrack distribution:
  https://github.com/opentrack/opentrack/blob/master/contrib/freepie-udp/FreePIE_IMU_Android9.apk
  Angles are measured in degrees, ABS/REL_RX is yaw, ABS/REL_RY is pitch, ABS/REL_RZ is roll.
  """

  MODE_ABS = 0
  MODE_REL = 1

  logger = get_logger(logger, "FreePIEHeadTrackerIDEV")

  def read_one(self):
    relAxesIds = (codes.REL_RX, codes.REL_RY, codes.REL_RZ)
    absAxesIds = (codes.ABS_RX, codes.ABS_RY, codes.ABS_RZ)
    assert self.lo_ == len(relAxesIds) and self.lo_ == len(absAxesIds)
    for i in range(self.lo_):
      new = self.orient_[i]
      if new is None:
        continue
      type_, code, value = None, None, None
      mode = self.mode_
      if mode == self.MODE_ABS:
        #send abs event
        type_, code, value = codes.EV_ABS, absAxesIds[i], new
      elif mode == self.MODE_REL:
        #send rel event
        old = self.oldOrient_[i]
        self.oldOrient_[i] = new
        #new == old covers case when both are None
        if new == old:
          continue
        elif old is None:
          continue
        type_, code, value = codes.EV_REL, relAxesIds[i], new - old
        if abs(value) >= 180.0:
          value += -1.0 * sign(value) * 360.0
      else:
        assert False, mode
      self.orient_[i] = None
      event = InputEvent(type_, code, value, self.timestamp_, self.idev_, None)
      return event
    return None

  def swallow(self, s):
    pass

  def update(self, tick, ts):
    while True:
      orient = self.get_orient_()
      if orient is None:
        return
      lo = len(orient)
      assert lo == self.lo_
      for i in range(lo):
        self.orient_[i] = orient[i]
      self.timestamp_ = ts

  def __init__(self, idev, address, from_=None, mode=1):
    """
    Arguments:
      idev - idev name or hash
      address - address to bind to: (ip, port)
        ip is str, can be empty
        port is int
      from_ - process packets sent only from here: (ip, port) or None
        ip is str
        port is int, can be None
      mode - MODE_ABS for absolute events, MODE_REL for relative
    """
    self.sock_ = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    self.sock_.bind(address)
    self.sock_.setblocking(0)
    self.from_ = from_
    self.idev_ = idev
    self.mode_ = mode
    self.orient_ = [None, None, None]
    self.oldOrient_ = [None, None, None]
    self.timestamp_ = time.time()
    self.lo_ = len(self.orient_)

  def get_orient_(self):
    def get_fmt_and_off(data):
      FLAGS_RAW = 1 << 0
      FLAGS_ORIENT = 1 << 1
      fmtHeader = "<xB"
      szHeader = struct.calcsize(fmtHeader)
      assert szHeader == 2
      fmtPayloadShort = "<3f"
      fmtPayloadLong = "<12f"
      flags = struct.unpack_from(fmtHeader, data)[0]
      fmt, i = None, 0
      if flags == FLAGS_RAW:
        pass
      elif flags == FLAGS_RAW | FLAGS_ORIENT:
        fmt, i = fmtPayloadLong, 9
      elif flags == FLAGS_ORIENT:
        fmt, i = fmtPayloadShort, 0
      else:
        #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("Unknown flags: {}".format(flags))
        pass
      return (fmt, i, szHeader)

    szData = 50
    while True:
      try:
        data, addr = self.sock_.recvfrom(szData)
      except socket.error:
        return None
      if data is None:
        return None
      if self.from_ is not None:
        ipMatch = addr[0] == self.from_[0]
        portMatch = addr[1] == self.from_[1] if self.from_[1] is not None else True
        if not (ipMatch and portMatch):
          #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("skipping packet from {}".format(addr))
          continue
      fmt, off, szHeader = get_fmt_and_off(data)
      if fmt is None:
        return None
      unpacked = struct.unpack_from(fmt, data, szHeader)
      if unpacked is None:
        return None
      import math
      radToDeg = 180.0 / math.pi
      orient = tuple(radToDeg * o for o in unpacked[off:])
      return orient


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

  logger = get_logger(logger, "JoystickPoseManager")

  def set_pose(self, i, l):
    self.poses_[i] = [[p[0], p[1]] for p in l]

  def update_pose(self, i):
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("update_pose({})".format(i))
    pose = self.poses_.get(i, None)
    if pose is None:
      #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: no pose {}".format(log_loc(self), i))
      return False
    else:
      for j in xrange(len(pose)):
        pose[j][1] = self.joystick_.get_axis_value(pose[j][0])
      return True

  def pose_to(self, i):
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("pose_to({})".format(i))
    pose = self.poses_.get(i, None)
    if pose is None:
      #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: no pose {}".format(log_loc(self), i))
      return False
    else:
      for p in pose:
        self.joystick_.move_axis(p[0], p[1], self.relative_)
      return True

  def __init__(self, joystick, relative):
    self.poses_, self.joystick_, self.relative_ = dict(), joystick, relative


class AxisPoseManager:
  """Axis-based pose manager"""

  logger = get_logger(logger, "AxisPoseManager")

  def set_pose(self, i, l):
    self.poses_[i] = [[p[0], p[1]] for p in l]

  def get_pose(self, i):
    return self.poses_.get(i, None)

  def has_pose(self, i):
    return i in self.poses_

  def get_poses(self):
    return self.poses_

  def update_pose(self, i):
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: updating pose {}".format(log_loc(self), i))
    pose = self.poses_.get(i, None)
    if pose is None:
      #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: no pose {}".format(log_loc(self), i))
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
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: poseing to {}".format(log_loc(self), i))
    pose = self.poses_.get(i, None)
    if pose is None:
      #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: no pose {}".format(log_loc(self), i))
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
      #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: no pose {}".format(log_loc(self), frm))
      return False
    t = self.poses_.setdefault(to, [])
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
    limits = self.limits_.get(tcAxis, None)
    if limits is None:
      if self.next_ is not None:
        limits = self.next_.get_limits(tcAxis)
      else:
        limits = (0.0, 0.0)
    return limits

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
      if rate == 0.0:
        continue
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
    if not relative and self.ep_() is not None:
      self.ep_()(Event(tcAxis.type, tcAxis.code, value, time.time()))
    return r

  def set_ep(self, ep):
    self.ep_ = weakref.ref(ep)
    return ep

  def __init__(self, ep=None, next=None):
    super(NotifyingJoystick, self).__init__(next)
    if ep is not None: self.ep_ = weakref.ref(ep)


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
      print("{}: {: .3f} {: .3f}".format(dtc2fn(None, tcAxis.type, tcAxis.code), error, d[2]))

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


class ReportingJoystickAxis(ProbingAxisMixin):
  logger = get_logger(logger, "ReportingJoystickAxis")

  def move(self, v, relative):
    return self.joystick_.move_axis(self.tcAxis_, v, relative)

  def get(self):
    return self.joystick_.get_axis_value(self.tcAxis_)

  def limits(self):
    return self.joystick_.get_limits(self.tcAxis_)

  def add_listener(self, listener):
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: Adding listener: {}, number of listeners: {}".format(log_loc(self), listener, len(self.listeners_)))
    self.listeners_.append(weakref.ref(listener))

  def remove_listener(self, listener):
    try:
      self.listeners_.remove(listener)
      #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: Removing listener: {}, number of listeners: {}".format(log_loc(self), listener, len(self.listeners_)))
    except ValueError:
      raise RuntimeError("Listener {} not registered".format(listener))

  def remove_all_listeners(self):
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: Removing all listeners, number of listeners: {}".format(log_loc(self), len(self.listeners_)))
    self.listeners_ = []

  def on_move(self, old, new):
    dirty = False
    for c in self.listeners_:
      cc = c()
      if cc is None:
        dirty = True
      else:
        #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: moving listener {}, old: {:0.3f}, new: {:0.3f}".format(log_loc(self), cc, old, new))
        cc.on_move_axis(self, old, new)
    if dirty:
      self.cleanup_()

  def __init__(self, joystick, tcAxis):
    if tcAxis not in joystick.get_supported_axes():
      raise RuntimeError("Axis '{}' is not supported by {}".format(tc2ns(*tcAxis)[0], joystick))
    self.joystick_, self.tcAxis_, self.listeners_ = joystick, tcAxis, []
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{} created".format(log_loc(self)))

  def __del__(self):
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{} destroyed".format(log_loc(self)))
    pass

  def cleanup_(self):
    i = 0
    while i < len(self.listeners_):
      if self.listeners_[i]() is None:
        self.listeners_.pop(i)
      else:
        i += 1
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: listeners after cleanup {}".format(log_loc(self), self.listeners_))


class ReportingJoystick(NodeJoystick):
  logger = get_logger(logger, "ReportingJoystick")

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
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: axes after cleanup {}".format(log_loc(self), self.axes_))


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
  logger = get_logger(logger, "RelativeHeadMovementJoystick")

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

      #Clamp to limits of next ep and move, both in global cs
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
      ov = self.angles_[tcAxis]
      v = value + ov if relative else value
      if v == ov:
        return 0.0 if relative else v
      #FIXME Not exactly correct, because yaw and pitch limits do change if roll != 0.0.
      #Essentially, yaw-pitch limits "box" is rotated by -roll angle.
      v = clamp(v, *self.get_limits(tcAxis))
      self.angles_[tcAxis] = v
      tcYaw, tcPitch, tcRoll = self.tcAngleAxes_
      dRoll = self.angles_[tcRoll]
      if dRoll != 0.0 and tcAxis in (tcYaw, tcPitch):
        rRoll = math.radians(dRoll)
        sinRoll, cosRoll = math.sin(rRoll), math.cos(rRoll)
        #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("dRoll:{:+0.3f} sinRoll:{:+0.3f} cosRoll:{:+0.3f}".format(dRoll, sinRoll, cosRoll))
        dThisYaw, dThisPitch = self.angles_[tcYaw], self.angles_[tcPitch]
        #Assuming that yaw increases when moving right, pitch increases when moving down, roll increases when tilting head to the right
        dYaw = dThisYaw * cosRoll - dThisPitch * sinRoll
        dPitch = dThisYaw * sinRoll + dThisPitch * cosRoll
        #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("dYaw:{:+0.3f} dPitch:{:+0.3f}".format(dYaw, dPitch))
        self.next_.move_axis(tcYaw, dYaw, relative=False)
        self.next_.move_axis(tcPitch, dPitch, relative=False)
        return v - ov if relative else v
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
    """Returns relative, local limits for position axes, calls next ep for other."""
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
    self.angles_ = { self.tcAngleAxes_[i] : 0.0 for i in range(len(self.tcAngleAxes_)) }
    self.dirsDirty_, self.limitsDirty_ = True, True

  def update_dirs_(self):
    if self.dirsDirty_ == True and self.next_ is not None:
      dYaw, dPitch, dRoll = (tca for tca in (self.next_.get_axis_value(tcAxis) for tcAxis in self.tcAngleAxes_))
      rYaw, rPitch, rRoll = (math.radians(a) for a in (dYaw, dPitch, dRoll))
      sinYaw, sinPitch, sinRoll = (math.sin(a) for a in (rYaw, rPitch, rRoll))
      cosYaw, cosPitch, cosRoll = (math.cos(a) for a in (rYaw, rPitch, rRoll))

      #x - 0, y - 1, z - 2
      #caclulated by negating sines as if dPitch and dRoll are negated (dYaw is not)
      self.dirs_[0] = (cosRoll*cosYaw - sinRoll*sinPitch*sinYaw, sinRoll*cosYaw + cosRoll*sinPitch*sinYaw, -cosPitch*sinYaw)
      self.dirs_[1] = (-sinRoll*cosPitch, cosRoll*cosPitch, sinPitch)
      self.dirs_[2] = (cosRoll*sinYaw + sinRoll*sinPitch*cosYaw, sinRoll*sinYaw - cosRoll*sinPitch*cosYaw, cosPitch*cosYaw)

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
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("global_to_local(): dirs{}; gp:{}; lp:{}".format(self.dirs_, gp, lp))
    return lp


  def local_to_global_(self, lp):
    gp = [0.0 for i in range(len(lp))]
    #TODO for ia in len(self.tcPosAxes_) ?
    for tca in self.tcPosAxes_:
      ia = self.tcPosAxes_.index(tca)
      for j in range(len(self.dirs_)):
        gp[ia] += lp[ia]*self.dirs_[j][ia]
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("local_to_global(): dirs{}; lp:{}; gp:{}".format(self.dirs_, lp, gp))
    return gp


#TODO Unused. Remove?
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


#Widgets
def make_tk_var(value):
  varType = type(value)
  tkVarTypes = {
    int : tk.IntVar,
    float : tk.DoubleVar,
    str : tk.StringVar,
    unicode : tk.StringVar
  }
  tkVarType = tkVarTypes.get(varType)
  if tkVarType is None:
    raise RuntimeError("Unsupported var type: {}".format(varType))
  return tkVarType(value=value)


def configure_widget(widget, propNames, kwargs, func):
  kwa = {}
  for propName in propNames:
    prop = kwargs.get(propName)
    if prop is not None:
      kwa[propName] = prop
  if len(kwa) != 0:
    func(widget, kwa)


class UpdatedMixin:
  def __init__(self, **kwargs):
    self.updatePeriod_ = kwargs.get("updatePeriod", 100)
    self.cbID_ = None
    def on_map(event):
      self.update_()
    def on_unmap(event):
      if self.cbID_ is not None: self.after_cancel(self.cbID_)
    self.bind("<Map>", on_map)
    self.bind("<Unmap>", on_unmap)

  def update_(self):
    self.cbID_ = self.after(self.updatePeriod_, self.update_)


class UpdatedMixin2:
  def __init__(self, **kwargs):
    self.updateState_ = False
    def on_map(event):
      self.updateState_ = True
    def on_unmap(event):
      self.updateState_ = False
    self.bind("<Map>", on_map)
    self.bind("<Unmap>", on_unmap)

  def update_self(self, *args, **kwargs):
    if self.updateState_ == True:
      self.update_()

  def update_(self):
    pass


class NamedWidget(tk.Frame):
  def set(self, child):
    self.child_ = child
    child.pack(in_=self)

  def __init__(self, **kwargs):
    tk.Frame.__init__(self, **exclude_from_dict(kwargs, "nameSide"))
    self.pack_propagate(True)
    name = kwargs.get("name", None)
    if name is not None:
      nameLabel = tk.Label(self, text=name)
      nameSide = kwargs.get("nameSide", "top")
      nameLabel.pack(expand=False, side=nameSide)
    self.child_ = None


class Marker:
  def update(self):
    canvas = self.parent_.canvas_
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

  def __init__(self, parent, vpx, vpy, shapes):
    self.parent_, self.vpx_, self.vpy_, self.shapes_ = parent, vpx, vpy, shapes
    bbox = self.parent_.canvas_.bbox(*self.shapes_)
    self.size_ = (bbox[2] - bbox[0], bbox[3] - bbox[1])


class AxesWidget(tk.Frame, UpdatedMixin2):
  def add_marker(self, vpx, vpy, shapeType, **kwargs):
    def make_vp(vp, scale=None):
      if is_str_type(vp):
        s = vp[0]
        sm = 1.0
        if s in ("+", "-"):
          vp = vp[1:]
          sm = 1.0 if s == "+" else -1.0
        odevName, tAxis, cAxis = fn2dtc(vp)
        tcAxis = TypeCode(tAxis, cAxis)
        if self.get_odev_ is None:
          raise RuntimeError("ODev locator is not set")
        odev = self.get_odev_(odevName)
        if odev is None:
          raise RuntimeError("Cannot get odev '{}'".format(odevName))
        if scale is None:
          limits = odev.get_limits(tcAxis)
          scale = 0.0 if limits[0] == limits[1] else 2.0 / abs(limits[1] - limits[0])
        scale *= sm
        return lambda : scale*odev.get_axis_value(tcAxis)
      elif type(vp) in (int, float):
        return lambda : vp
      else:
        return vp
    sx, sy = kwargs.get("sx", None), kwargs.get("sy", None)
    vpx, vpy = make_vp(vpx, sx), make_vp(vpy, sy)
    shapes = self.create_shapes_(shapeType, **kwargs)
    marker = Marker(self, vpx, vpy, shapes)
    marker.update()
    self.markers_.append(marker)
    return marker

  def __init__(self, **kwargs):
    tk.Frame.__init__(self, **exclude_from_dict(kwargs, "canvasBg", "canvasSize", "layout", "gridColor", "gridWidth", "getODev"))
    UpdatedMixin2.__init__(self, **kwargs)
    canvas = tk.Canvas(master=self, bg=kwargs.get("canvasBg", "black"))
    canvasSize = kwargs.get("canvasSize", (200, 20))
    fill = "both"
    layout = kwargs["layout"]
    if layout == "box":
      canvas["width"], canvas["height"] = canvasSize[0], canvasSize[0]
      fill = "both"
    elif layout == "h":
      canvas["width"], canvas["height"] = canvasSize[0], canvasSize[1]
      fill = "x"
    elif layout == "v":
      canvas["width"], canvas["height"] = canvasSize[1], canvasSize[0]
      fill = "y"
    canvas.pack(expand=True, fill=fill)
    self.canvas_ = canvas
    self.add_grid_(layout, color=kwargs.get("gridColor", "white"), width=kwargs.get("gridWidth", 1))
    self.markers_ = []
    self.get_odev_ = kwargs.get("getODev", None)

  def create_shapes_(self, shapeType, **kwargs):
    size = kwargs.get("size", (11, 11))
    color = kwargs.get("color", "white")
    canvas = self.canvas_
    if shapeType == "oval":
      return [canvas.create_oval(0,0,size[0],size[1], fill=color)]
    elif shapeType == "rect":
      return [canvas.create_rectangle(0,0,size[0],size[1], fill=color)]
    elif shapeType == "cross":
      width = kwargs.get("width", 1)
      return [
        canvas.create_line(0,0.5*size[1],size[0],0.5*size[1], fill=color, width=width),
        canvas.create_line(0.5*size[0],0,0.5*size[0],size[1], fill=color, width=width),
      ]
    elif shapeType == "hline":
      return [canvas.create_line(0,0,size[0],0, fill=color, width=size[1])]
    elif shapeType == "vline":
      return [canvas.create_line(0,0,0,size[1], fill=color, width=size[0])]
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

  def update_(self):
    for marker in self.markers_:
      marker.update()
    UpdatedMixin2.update_(self)


class GridWidget(tk.Frame):
  def add(self, **kwargs):
    child = kwargs["child"]
    child.grid(in_=self)
    configure_widget(
      child,
      ("sticky", "row", "column", "rowspan", "columnspan", "padx", "pady", "ipadx", "ipady"),
      kwargs,
      lambda widget,kwa : widget.grid_configure(**kwa)
    )
    self.children_.append(child)

  def __init__(self, **kwargs):
    tk.Frame.__init__(self, **kwargs)
    self.pack_propagate(True)
    self.grid_propagate(True)
    self.children_ = []


class EntriesWidget(tk.Frame):
  def add(self, **kwargs):
    child = kwargs["child"]
    child.grid(in_=self, row=self.r_, column=self.c_, rowspan=1, columnspan=1)
    configure_widget(child, ("sticky", "padx", "pady", "ipadx", "ipady"), kwargs, lambda widget,kwa : widget.grid_configure(**kwa))
    #setting weights to avoid clipping
    rowWeight = 1 if self.grow_ in ("y", "both") else 0
    columnWeight = 1 if self.grow_ in ("x", "both") else 0
    self.grid_rowconfigure(self.r_, weight=rowWeight)
    self.grid_columnconfigure(self.c_, weight=columnWeight)
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

  def __init__(self, **kwargs):
    tk.Frame.__init__(self, **exclude_from_dict(kwargs, "dim", "layout", "grow"))
    frame = self
    frame.pack_propagate(True)
    frame.grid_propagate(True)
    self.children_ = []
    self.dim_ = kwargs.get("dim", 8)
    self.layout_ = kwargs.get("layout", "v")
    if self.layout_ not in ("h", "v"):
      raise RuntimeError("Bad layout: '{}'".format(self.layout_))
    self.grow_ = kwargs.get("grow", "").lower()
    self.r_, self.c_ = 0, 0


class ButtonStateWidget(tk.Label, UpdatedMixin2):
  def __init__(self, **kwargs):
    tk.Label.__init__(self, text=kwargs["name"], **exclude_from_dict(kwargs, "getButtonState", "style", "name"))
    UpdatedMixin2.__init__(self, **kwargs)
    self.getButtonState_ = kwargs["getButtonState"]
    self.style_ = kwargs["style"]
    self.state_ = None

  def update_(self):
    state = self.getButtonState_()
    if state != self.state_:
      self.state_ = state
      styleName = "pressed" if state == True else "released"
      style = self.style_[styleName]
      for p in (("foreground", "fg"), ("background", "bg")):
        self[p[0]] = style[p[1]]
    UpdatedMixin2.update_(self)


class ButtonsStatesWidget(EntriesWidget, UpdatedMixin2):
  class GetButtonState:
    def __call__(self):
      return self.output_.get_button_state(self.buttonID_)
    def __init__(self, output, buttonID):
      self.output_, self.buttonID_ = output, buttonID

  def add_buttons_from(self, odev, **kwargs):
    odev = self.get_odev_(odev) if is_str_type(odev) else odev
    if odev is None:
      return
    idButtons = None
    nButtons = kwargs.get("buttons")
    if nButtons is not None:
      idButtons = [fn2tc(n).code for n in nButtons]
    else:
      idButtons = odev.get_supported_buttons()
    for idButton in idButtons:
      name = str(idButton - codes.BTN_0)
      getButtonState = self.GetButtonState(odev, idButton)
      buttonStateWidget = ButtonStateWidget(master=self, name=name, getButtonState=getButtonState, style=self.style_)
      self.add(child=buttonStateWidget)

  def __init__(self, **kwargs):
    EntriesWidget.__init__(self, **exclude_from_dict(kwargs, "getODev", "style", "idev"))
    UpdatedMixin2.__init__(self, **kwargs)
    self.style_ = kwargs.get("style", {"released" : {"fg" : "black", "bg" : None}, "pressed" : {"fg" : "red", "bg" : None}})
    self.get_odev_ = kwargs["getODev"]
    idev = kwargs.get("idev", None)
    if idev is not None:
      self.add_buttons_from(idev, **kwargs)

  def update_(self):
    for child in self.children_:
      child.update_self()
    UpdatedMixin2.update_(self)


class AxisValueWidget(tk.Frame, UpdatedMixin2):
  def __init__(self, **kwargs):
    tk.Frame.__init__(self, **exclude_from_dict(kwargs, "name", "getAxisValue"))
    UpdatedMixin2.__init__(self, **kwargs)
    self.nameLabel_ = tk.Label(master=self, text=kwargs["name"])
    self.nameLabel_.pack(side="left")
    self.valueLabel_ = tk.Label(master=self)
    self.valueLabel_.pack(side="right")
    self.getAxisValue_ = kwargs["getAxisValue"]

  def update_(self):
    value = self.getAxisValue_()
    self.valueLabel_["text"] = "{:+.3f}".format(value)
    UpdatedMixin2.update_(self)


class AxesValuesWidget(EntriesWidget, UpdatedMixin2):
  class GetAxisValue:
    def __call__(self):
      return self.output_.get_axis_value(self.tcAxis_)
    def __init__(self, output, tcAxis):
      self.output_, self.tcAxis_ = output, tcAxis

  def add_axes_from(self, output, **kwargs):
    odev = self.get_odev_(output) if is_str_type(output) else output
    if odev is None:
      return
    tcAxiss = None
    nAxiss = kwargs.get("axes")
    if nAxiss is not None:
      tcAxiss = [fn2tc(n) for n in nAxiss]
    else:
      tcAxiss = odev.get_supported_axes()
      tcAxiss.sort(key=lambda tc : tc.code)
    for tcAxis in tcAxiss:
      namesList=tc2ns(*tcAxis)
      name=namesList[0][4:]
      getAxisValue = self.GetAxisValue(odev, tcAxis)
      axisValue = AxisValueWidget(master=self, name=name, getAxisValue=getAxisValue)
      self.add(child=axisValue)
      axisValue.grid(sticky="nsew")

  def __init__(self, **kwargs):
    EntriesWidget.__init__(self, **exclude_from_dict(kwargs, "getODev", "idev"))
    UpdatedMixin2.__init__(self, **kwargs)
    self.get_odev_ = kwargs["getODev"]
    idev = kwargs.get("idev", None)
    if idev is not None:
      self.add_axes_from(idev, **kwargs)

  def update_(self):
    for child in self.children_:
      child.update_self()
    UpdatedMixin2.update_(self)


class ValueWidget(tk.Frame, UpdatedMixin2):
  def __init__(self, **kwargs):
    tk.Frame.__init__(self, **exclude_from_dict(kwargs, "state", "height", "width", "var", "fmt"))
    UpdatedMixin2.__init__(self, **kwargs)
    self.valueLabel_ = tk.Label(master=self)
    self.valueLabel_.pack(expand=True, fill="x")
    configure_widget(
      self.valueLabel_,
      ("state", "height", "width"),
      kwargs,
      lambda widget,kwa : widget.configure(**kwa)
    )
    self.var_ = kwargs["var"]
    self.fmt_ = kwargs["fmt"]

  def update_(self):
    v = self.var_.get()
    msg = None
    if v is not None:
      try:
        if is_dict_type(v):
          msg = self.fmt_.format(**v)
        elif is_list_type(v):
          msg = self.fmt_.format(*v)
        else:
          msg = self.fmt_.format(v)
      except Exception as e:
        msg = "Cannot format ({})".format(e)
    self.valueLabel_["text"] = msg
    UpdatedMixin2.update_(self)


class VarPointsSource:
  def set_points(self, points):
    if is_dict_type(self.var_.get(self.keys_)):
      points = { str(x) : y for x,y in points }
    self.var_.set(points, self.keys_)

  def get_points(self):
    points = self.var_.get(self.keys_)
    if is_dict_type(points):
      points = [[float(k), float(v)] for k,v in points.items()]
    points.sort(key=lambda p : p[0])
    return points

  def __init__(self, var, keys=None):
    self.var_, self.keys_ = var, keys


class CurveEditorWidget(tk.Canvas):
  def set_func(self, func):
    self.func_ = func
    self.update_curve_()

  def set_points_source(self, ps):
    self.pointsSource_ = ps
    self.update_curve_()

  def __init__(self, **kwargs):
    master = kwargs.get("master")
    style = kwargs.get("style")
    self.style_ = style
    self.screenSize_ = kwargs.get("screenSize", [200, 200])
    tk.Canvas.__init__(
      self,
      width=self.screenSize_[0],
      height=self.screenSize_[1],
      bg=get_nested_d(style, "bg", "white"),
      **exclude_from_dict(kwargs, "style", "screenSize", "func", "pointsSource", "worldBBox", "worldPos", "worldSize")
    )
    self.pack(expand=True, fill="both")
    self.bind("<Button-1>", self.add_or_select_node_)
    self.bind("<ButtonRelease-1>", self.deselect_node_)
    self.bind("<Motion>", self.motion_)
    self.bind("<B1-Motion>", self.drag_node_)
    self.bind("<Button-3>", self.remove_node_)
    self.bind("<Configure>", self.configure_)
    self.nodes_ = []
    self.func_ = kwargs.get("func")
    self.pointsSource_ = kwargs.get("pointsSource")
    worldPos, worldSize = None, None
    worldBBox = kwargs.get("worldBBox", None)
    if worldBBox is not None:
      worldPos = [worldBBox[0], worldBBox[1]]
      worldSize = [worldBBox[2] - worldBBox[0], worldBBox[3] - worldBBox[1]]
    else:
      worldPos = kwargs.get("worldPos", [0.0, 0.0])
      worldSize = kwargs.get("worldSize", [1.0, 1.0])
    self.worldPos_, self.worldSize_ = worldPos, worldSize
    self.selected_ = None
    color = get_nested_d(self.style_, "vline.color", "black")
    width = get_nested_d(self.style_, "vline.width", 1)
    dash = get_nested_d(self.style_, "vline.dash", None)
    self.vline_ = self.create_line(0, 0, 0, self.screenSize_[1], fill=color, width=width, dash=dash, state="hidden")
    self.intersectionText_ = self.create_text(0, 0, anchor="nw", text="", fill=color, state="hidden")
    self.update_grid_()
    self.curve_ = None
    if self.func_ is not None:
      for center in self.pointsSource_.get_points():
        self.add_node_(center)
      self.update_curve_()
    self.set_vline_state_(True)

  class Node:
    def __init__(self, shapes, center):
      self.shapes, self.center = shapes, center

  def to_screen_(self, p):
    return (
      None if p[0] is None else lerp(float(p[0]), self.worldPos_[0], self.worldPos_[0] + self.worldSize_[0], 0.0, self.screenSize_[0]),
      None if p[1] is None else lerp(float(p[1]), self.worldPos_[1], self.worldPos_[1] + self.worldSize_[1], self.screenSize_[1], 0.0)
    )

  def from_screen_(self, p):
    return (
      None if p[0] is None else lerp(float(p[0]), 0.0, self.screenSize_[0], self.worldPos_[0], self.worldPos_[0] + self.worldSize_[0]),
      None if p[1] is None else lerp(float(p[1]), self.screenSize_[1], 1.1, self.worldPos_[1], self.worldPos_[1] + self.worldSize_[1])
    )

  def set_vline_state_(self, s):
    state = "normal" if s == True and len(self.nodes_) >= 2 else "hidden"
    self.itemconfigure(self.vline_, state=state)
    self.itemconfigure(self.intersectionText_, state=state)

  def add_or_select_node_(self, event):
    x, y = event.x, event.y
    for node in self.nodes_:
      if is_inside_bbox(x, y, self.bbox(node.shapes["marker"])):
        self.selected_ = node
        #TODO Save offset between event x and y, and node center, to use this offset in drag_node_()
        self.set_vline_state_(False)
        return
    center = self.from_screen_((x, y))
    self.add_node_(center)
    self.update_curve_()
    self.set_vline_state_(True)

  def add_node_(self, center):
    x, y = self.to_screen_(center)
    w, h = get_nested_d(self.style_, "curve.marker.size", (10, 10))
    fill = get_nested_d(self.style_, "curve.marker.fill", None)
    outline = get_nested_d(self.style_, "curve.marker.outline", "black")
    hw, hh = 0.5 * w, 0.5 * h
    precision = get_nested_d(self.style_, "curve.text.precision", 3)
    fmt = "{{: 0.{}f}}\n{{: 0.{}f}}".format(precision, precision)
    shapes = {
      "marker" : self.create_rectangle(x - hw, y - hh, x + hw, y + hh, fill=fill, outline=outline),
      "text" : self.create_text(x, y, anchor="nw", text=fmt.format(center[0], center[1]))
    }
    self.nodes_.append(self.Node(shapes, center))

  def deselect_node_(self, event):
    self.selected_ = None
    self.set_vline_state_(True)

  def remove_node_(self, event):
    x, y = event.x, event.y
    for node in self.nodes_:
      if is_inside_bbox(x, y, self.bbox(node.shapes["marker"])):
        for shape in node.shapes.values():
          self.delete(shape)
        self.nodes_.remove(node)
        if self.selected_ == node:
          self.selected_ = None
    self.update_curve_()
    self.set_vline_state_(True)

  def drag_node_(self, event):
    node = self.selected_
    if node is not None:
      x, y = event.x, event.y
      node.center = self.from_screen_((x, y))
      self.update_node_(node)
      text = node.shapes["text"]
      precision = get_nested_d(self.style_, "curve.line.precision", 3)
      fmt = "{{: 0.{}f}}\n{{: 0.{}f}}".format(precision, precision)
      self.itemconfigure(text, text=fmt.format(node.center[0], node.center[1]))
      textBBox = self.bbox(text)
      textW, textH = textBBox[2] - textBBox[0], textBBox[3] - textBBox[1]
      textX = clamp(x, 0.0, self.screenSize_[0] - textW)
      textY = clamp(y, 0.0, self.screenSize_[1] - textH)
      self.coords(text, textX, textY)
      self.update_curve_(False)

  def update_node_(self, node=None):
    def update_node(node):
      c = self.to_screen_(node.center)
      cx, cy = c[0], c[1]
      for shape in node.shapes.values():
        coords = self.coords(shape)
        lc = len(coords)
        if lc == 2:
          self.coords(shape, cx, cy)
        elif lc == 4:
          w, h = coords[3] - coords[1], coords[2] - coords[0]
          hw, hh = 0.5 * w, 0.5 * h
          self.coords(shape, cx - hw, cy - hh, cx + hw, cy + hh)
        else:
          assert False
    if node is not None:
      update_node(node)
    else:
      for node in self.nodes_:
        update_node(node)

  def update_curve_(self, recreate=True):
    if self.func_ is None or len(self.nodes_) < 2:
      return
    centers = [node.center for node in self.nodes_]
    centers.sort(key=lambda c : c[0])
    self.pointsSource_.set_points(centers)
    points = []
    step = get_nested_d(self.style_, "curve.line.step", None)
    if step is None:
      step = self.worldSize_[0] / self.screenSize_[0]
    x = self.worldPos_[0]
    xTo = self.worldPos_[0] + self.worldSize_[0]
    while True:
      y = self.func_(x)
      if y is not None:
        points.append(self.to_screen_((x, y)))
      remaining = xTo - x
      if remaining == 0.0:
        break
      elif remaining > step:
        x += step
      else:
        x = xTo
    color = get_nested_d(self.style_, "curve.line.color", "black")
    width = get_nested_d(self.style_, "curve.line.width", 1)
    dash = get_nested_d(self.style_, "curve.line.dash", None)
    if self.curve_ is not None and recreate == True:
      self.delete(self.curve_)
      self.curve_ = None
    if self.curve_ is None:
      self.curve_ = self.create_line(points, fill=color, width=width, dash=dash)
    else:
      import itertools
      self.coords(self.curve_, *itertools.chain.from_iterable(points))

  def update_grid_(self):
    def create_vline(self, x, **kwargs):
      x, _ = self.to_screen_((x, None))
      self.create_line(x, 0, x, self.screenSize_[1], **kwargs)
    def create_hline(self, y, **kwargs):
      _, y = self.to_screen_((None, y))
      self.create_line(0, y, self.screenSize_[0], y, **kwargs)
    tag = "grid"
    self.delete(tag)
    fmt = "{{: 0.{}f}}".format(get_nested_d(self.style_, "grid.text.precision", 2))
    color = get_nested_d(self.style_, "grid.axis.color", "black")
    width = get_nested_d(self.style_, "grid.axis.width", 2)
    create_hline(self, 0.0, fill=color, width=width, tag=tag)
    create_vline(self, 0.0, fill=color, width=width, tag=tag)
    self.create_text(self.to_screen_((0.0, 0.0)), anchor="nw", text=fmt.format(0.0), tag=tag)
    color = get_nested_d(self.style_, "grid.line.color", "black")
    width = get_nested_d(self.style_, "grid.line.width", 1)
    dash = get_nested_d(self.style_, "grid.line.dash", None)
    xStep = get_nested_d(self.style_, "grid.step.x", 0.10)
    x = int(self.worldPos_[0] / xStep) * xStep
    xTo = self.worldPos_[0] + self.worldSize_[0]
    while x <= xTo:
      if abs(x) > 1e-6:
        create_vline(self, x, fill=color, width=width, dash=dash, tag=tag)
        self.create_text(self.to_screen_((x, 0.0)), anchor="nw", text=fmt.format(x), tag=tag)
      x += xStep
    yStep = get_nested_d(self.style_, "grid.step.y", 0.10)
    y = int(self.worldPos_[1] / yStep) * yStep
    yTo = self.worldPos_[1] + self.worldSize_[1]
    while y <= yTo:
      if abs(y) > 1e-6:
        create_hline(self, y, fill=color, width=width, dash=dash, tag=tag)
        self.create_text(self.to_screen_((0.0, y)), anchor="nw", text=fmt.format(y), tag=tag)
      y += yStep

  def configure_(self, event):
    if self.screenSize_[0] == event.width and self.screenSize_[1] == event.height:
      return
    self.screenSize_[0], self.screenSize_[1] = event.width, event.height
    self.update_curve_()
    self.update_grid_()
    self.update_node_()

  def motion_(self, event):
    if len(self.nodes_) < 2:
      return
    self.coords(self.vline_, event.x, 0, event.x, self.screenSize_[1])
    nx, _ = self.from_screen_((event.x, None))
    ny = self.func_(nx)
    if ny is not None:
      precision = get_nested_d(self.style_, "vline.precision", 3)
      fmt = "{{: 0.{}f}}\n{{: 0.{}f}}".format(precision, precision)
      self.coords(self.intersectionText_, *self.to_screen_((nx, ny)))
      self.itemconfigure(self.intersectionText_, text=fmt.format(nx, ny))
      self.itemconfigure(self.intersectionText_, state="normal")
    else:
      self.itemconfigure(self.intersectionText_, state="hidden")


class FuncEditorWidget(tk.Frame):
  def __init__(self, **kwargs):
    import ttk
    tk.Frame.__init__(self, **exclude_from_dict(kwargs, "funcs", "main", "style"))
    self.funcs_ = kwargs["funcs"]
    self.main_ = kwargs.get("main", None)
    self.currentDev_, self.currentAxis_, self.currentFunc_ = None, None, None
    #First create widgets and add them to master, then set commands,
    #then set values to dev combobox, which should invoke commands of other boxes and fill self.current... members
    self.widths_ = {
      n : get_nested_d(kwargs, "style.{}.width".format(n), 0) for n in ("devbox", "axisbox", "funcbox")
    }
    self.devBox_ = ttk.Combobox(master=self, width=self.widths_["devbox"])
    self.devBox_.pack(side="left")
    self.axisBox_ = ttk.Combobox(master=self, width=self.widths_["axisbox"])
    self.axisBox_.pack(side="left")
    self.funcBox_ = ttk.Combobox(master=self, width=self.widths_["funcbox"])
    self.funcBox_.pack(side="left")
    self.btn_ = tk.Button(master=self, text="edit", command=self.edit_func_)
    self.btn_.pack(side="left")
    self.devBox_.bind("<<ComboboxSelected>>", self.select_dev_)
    self.axisBox_.bind("<<ComboboxSelected>>", self.select_axis_)
    self.funcBox_.bind("<<ComboboxSelected>>", self.select_func_)
    values = values=self.funcs_.keys()
    self.devBox_.configure(values=values)
    self.devBox_.set(values[0])
    if self.widths_["devbox"] == 0:
      self.devBox_.configure(width=max(len(value) for value in values))
    self.select_dev_()

  def select_dev_(self, event=None):
    v = self.devBox_.get()
    self.currentDev_ = v
    values = self.funcs_[v].keys()
    self.axisBox_.configure(values=values)
    axisBoxValue = self.currentAxis_ if self.currentAxis_ in values else values[0]
    self.axisBox_.set(axisBoxValue)
    if self.widths_["axisbox"] == 0:
      self.axisBox_.configure(width=max(len(value) for value in values))
    self.select_axis_()

  def select_axis_(self, event=None):
    v = self.axisBox_.get()
    self.currentAxis_ = v
    values=self.funcs_[self.currentDev_][self.currentAxis_].keys()
    self.funcBox_.configure(values=values)
    funcBoxValue = self.currentFunc_ if self.currentFunc_ in values else values[0]
    self.funcBox_.set(funcBoxValue)
    if self.widths_["funcbox"] == 0:
      self.funcBox_.configure(width=max(len(value) for value in values))
    self.select_func_()

  def select_func_(self, event=None):
    v = self.funcBox_.get()
    self.currentFunc_ = v

  def edit_func_(self):
    tlw = tk.Toplevel(master=self)
    funcCfg = self.funcs_[self.currentDev_][self.currentAxis_][self.currentFunc_]
    funcCfg["master"] = tlw
    state = ParserState(self.main_)
    ce = self.main_.get("parser")("widget", funcCfg, state)
    ce.pack(expand=True, fill="both")
    #Needed to ensure that tlw.winfo_width() and tlw.winfo_height() will return correct dimensions
    tlw.update_idletasks()
    width, height = tlw.winfo_width(), tlw.winfo_height()
    swidth, sheight = tlw.winfo_screenwidth(), tlw.winfo_screenheight()
    x, y = 0.5 * (swidth - width), 0.5 * (sheight - height)
    geometry = "+{x:.0f}+{y:.0f}".format(x=x, y=y)
    tlw.geometry(geometry)
    self.main_.get("info").add_top_level_widget(tlw)


class InfoWidget:
  def add(self, child):
    self.widgets_.append(child)

  def set_state(self, s):
    if self.state_ == s:
      return
    else:
      self.state_ = s
    if s == True:
      self.w_.deiconify()
    elif s == False:
      for tlw in self.tlws_:
        tlw.destroy()
      self.tlws_ = []
      self.w_.withdraw()

  def get_state(self):
    return self.state_

  def update(self):
    if self.state_:
      self.w_.update()

  def add_top_level_widget(self, tlw):
    self.tlws_.append(tlw)

  def destroy(self):
    self.w_.destroy()

  def __init__(self, **kwargs):
    self.state_, self.widgets_ = False, []
    self.tlws_ = []
    master = kwargs.get("master")
    self.w_ = tk.Toplevel(master=master) if master is not None else tk.Tk()
    self.w_.title(kwargs.get("title", ""))
    self.w_.propagate(True)
    self.w_.grid_propagate(True)
    self.w_.withdraw()


class NextEP:
  def __call__(self, event):
    return self.next_(event) if self.next_ is not None else False

  def set_next(self, nxt):
    self.next_ = nxt

  def __init__(self, nxt=None):
    self.next_ = nxt


class MainEP:
  def __call__(self, event):
    return self.top_(event) if self.top_ is not None else False

  def set_top(self, top):
    self.top_ = top

  def set_bottom(self, bottom):
    self.bottom_ = bottom

  def set_next(self, nxt):
    if self.bottom_ is not None:
      self.bottom_.set_next(nxt)

  def set_state(self, state):
    self.state_ = state
    for stateful in self.stateful_:
      stateful.set_state(state)

  def get_state(self):
    return self.state_

  def add_stateful(self, stateful):
    self.stateful_.append(stateful)

  def get(self, name, dfault=None):
    return dfault

  def __init__(self, top=None, bottom=None, stateful=None, state=False):
    self.top_, self.bottom_ = top, bottom
    self.stateful_ = [st for st in stateful] if stateful is not None else []
    self.state_ = state


def init_main_ep(state):
  if logger.isEnabledFor(logging.DEBUG): logger.debug("init_main_ep()")
  main = state.get("main")
  config = main.get("config")

  headEP = HeadEP()
  state.push("eps", headEP)
  topEP = bottomEP = headEP
  mainEP = MainEP()
  mainEP.set_top(topEP)
  scParser = state.get("parser").get("sc")
  scParser.get("objects")(config, state)
  mappingEP = scParser.get("mapping")(config, state)
  if mappingEP is not None:
    bottomEP.set_next(mappingEP)
    bottomEP = mappingEP
  defaultModifierDescs = [
    DevCodeState(None, m, True) for m in
    (codes.KEY_LEFTSHIFT, codes.KEY_RIGHTSHIFT, codes.KEY_LEFTCTRL, codes.KEY_RIGHTCTRL, codes.KEY_LEFTALT, codes.KEY_RIGHTALT)
  ]
  modifiers = state.resolve_d(config, "modifiers", None, cls=list)
  modifierDescs = defaultModifierDescs if modifiers is None else [parse_modifier_desc(m, None) for m in modifiers]
  modifierEP = ModifierEP(modifierDescs=modifierDescs, saveModifiers=False, mode=ModifierEP.OVERWRITE)
  bottomEP.set_next(modifierEP)
  clickEP = modifierEP.set_next(ClickEP(state.resolve_d(config, "clickTime", 0.5, cls=float)))
  holdDataCfg = state.resolve_d(config, "holds", state.resolve_d(config, "hold", [], cls=list), cls=list)
  holdEP = clickEP.set_next(HoldEP())
  for hd in holdDataCfg:
    keyFullName = state.resolve_d(hd, "key", None, cls=str)
    keyIDev, keyCode = fn2hc(keyFullName) if keyFullName is not None else (None, None)
    modifiers = state.resolve_d(hd, "modifiers", None, cls=list)
    if modifiers is not None:
      modifiers = (parse_modifier_desc(m, state) for m in modifiers)
    num = state.resolve_d(hd, "num", -1, cls=int)
    holdEP.add(keyIDev, keyCode, modifiers, state.resolve(hd, "period", cls=float), state.resolve(hd, "value", cls=int), num)
  main.add_to_updated(lambda tick,ts : holdEP.update(tick, ts))

  sensSetsCfg = state.resolve_d(config, "sens", None, cls=dict)
  scaleEP = None
  if sensSetsCfg is not None:
    sensSet = state.resolve_d(config, "sensSet", None, cls=str)
    if sensSet not in sensSetsCfg:
      raise Exception("Invalid sensitivity set: {}".format(sensSet))
    sensCfg = { "sens" : sensSetsCfg[sensSet] }
    scaleEP = main.get("parser").get("sc")("sens", sensCfg, state)
  else:
    scaleEP = ScaleEP2({})
  assert scaleEP is not None
  holdEP.set_next(scaleEP)

  stateEP = StateEP()
  mainEP.add_stateful(stateEP)

  released = state.resolve_d(config, "released", [], cls=list)
  for i in range(len(released)):
    released[i] = state.deref(released[i], cls=str)
  idevFilterOp = IDevFilterOp(released)
  filterEP = stateEP.set_next(FilterEP(idevFilterOp))
  namesOfReleasedStr = ", ".join(released)

  def print_ungrabbed(event):
    logger.info("{} ungrabbed".format(namesOfReleasedStr))
  def print_grabbed(event):
    logger.info("{} grabbed".format(namesOfReleasedStr))

  enabled = [True]
  actionParser = main.get("parser").get("action")

  def parseToggle(cfg, state):
    def op(event):
      mainEP.set_state(not mainEP.get_state())
    return op
  actionParser.add("toggle", parseToggle)

  def parseEnable(cfg, state):
    callbacks = (SetState(idevFilterOp, True), SwallowSource(main.get("source"), [(n,True) for n in released]),  print_grabbed,)
    def op(event):
      if stateEP.get_state() and not enabled[0]:
        for cb in callbacks:
          cb(event)
        enabled[0] = True
    return op
  actionParser.add("enable", parseEnable)

  def parseDisable(cfg, state):
    callbacks2 = (SetState(idevFilterOp, False), SwallowSource(main.get("source"), [(n,False) for n in released]),  print_ungrabbed,)
    def op(event):
      if stateEP.get_state() and enabled[0]:
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

  bindEP = scParser.get("binds")(config, state)
  bindEP.add(None, stateEP, 1)
  scaleEP.set_next(bindEP)

  grabbed = state.resolve_d(config, "grabbed", [], cls=list)
  for i in range(len(grabbed)):
    grabbed[i] = state.deref(grabbed[i], cls=str)
  namesOfGrabbedStr = ", ".join(grabbed)

  def print_enabled(event):
    logger.info("Emulation enabled; {} grabbed".format(namesOfGrabbedStr))
  def print_disabled(event):
    logger.info("Emulation disabled; {} ungrabbed".format(namesOfGrabbedStr))

  stateValue = None
  stateValueName = state.resolve_d(config, "stateValueName", None, cls=str)
  if stateValueName is not None:
    stateValue = state.get("main").get("valueManager").get_var(stateValueName)
  def make_set_state_val(s):
    def op(event):
      if stateValue is not None: stateValue.set(s)
    return op

  grabEP = filterEP.set_next(BindEP())
  grabEP.add(ET.init(1), Call(SwallowSource(main.get("source"), [(n,True) for n in grabbed]), print_enabled, make_set_state_val("enabled")), 0)
  grabEP.add(ET.init(0), Call(SwallowSource(main.get("source"), [(n,False) for n in grabbed]), print_disabled, make_set_state_val("disabled")), 0)

  nextEP = NextEP()
  grabEP.add(None, nextEP, 1)

  mainEP.set_bottom(nextEP)

  initialState = state.resolve_d(config, "initialState", False, cls=bool)
  mainEP.set_state(initialState)

  logger.info("Initialization successfull")

  return mainEP


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
    except IOError as e:
      logger.warning("{} is missing".format(configName))
    except (KeyError, ValueError) as e:
      raise ConfigReadError(configName, str2(e))
  return cfg


def init_preset_config(state):
  main = state.get("main")
  config = main.get("config")
  presetName = state.resolve(config, "preset", cls=str)
  logger.info("Using '{}' preset from config".format(presetName))
  presetsCfg = state.resolve_d(config, "presets", {}, cls=dict)
  presetCfg = get_nested_d(presetsCfg, presetName, None)
  if presetCfg is None:
    raise Exception("'{}' preset not found in config".format(presetName))
  else:
    try:
      parser = main.get("parser")
      r = parser("ep", presetCfg, state)
      return r
    except (ParseError, Exception) as e:
      logger.error("Error while initializing config preset '{}': {}".format(presetName, e))
      raise
    except KeyError as e:
      logger.error("Error while initializing config preset '{}': cannot find key '{}'".format(presetName, str(e)))
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


def parse_dict_live_ordered(d, cfg, state, kp, vp, op, update, exceptionHandler=None):
  items = cfg.items()
  items.sort(key=op)
  for key,value in items:
    try:
      k = kp(key, state)
      if k in d and not update:
        continue
      d[k] = vp(value, state)
    except Exception as e:
      if exceptionHandler is not None:
        if exceptionHandler(key, value, e):
          continue
        else:
          break
      else:
        raise
  return d


class SelectParser:
  def __call__(self, key, cfg, state):
    if key not in self.parsers_:
      raise ParseError(key, state.get_path(cfg), KeyErrorEx(key, self.parsers_.keys()))
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
  logger = get_logger(logger, "DerefSelectParser")

  def __call__(self, key, cfg, state, **kwargs):
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: key: '{}', cfg: '{}'".format(log_loc(self), str2(key), str2(cfg)))
    d = key if self.derefKey_ else cfg
    r = state.deref(d, **kwargs)
    #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: dereferenced '{}' to '{}'".format(log_loc(self), str2(d), str2(r)))
    if r == d: #r (or d) is not a reference
      r = self.p_(key, cfg, state)
    elif is_dict_type(r) and not has_value_tag(r):
      r = self.p_(key, r, state)
    return r

  def add(self, key, parser):
    self.p_.add(key, parser)

  def get(self, key, dfault=None):
    return self.p_.get(key, dfault)

  def has(self, key):
    return self.p_.has(key)

  def __init__(self, parser=None, derefKey=True):
    self.p_ = SelectParser() if parser is None else parser
    self.derefKey_ = derefKey


class DerefParser:
  def __call__(self, cfg, state, **kwargs):
    r = state.deref(cfg, **kwargs)
    return self.p_(cfg, state) if r == cfg else r

  def add(self, key, parser):
    self.p_.add(key, parser)

  def get(self, key, dfault=None):
    return self.p_.get(key, dfault)

  def has(self, key):
    return self.p_.has(key)

  def __init__(self, parser):
    self.p_ = parser


class HeadEP:
  logger = get_logger(logger, "HeadEP")

  def __call__(self, event):
    #Can be actually called during init when next_ is not set yet
    if self.next_ is None:
      #if self.logger.isEnabledFor(logging.DEBUG): self.logger.debug("{}: next ep is not set".format(log_loc(self)))
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
    set_nested(self.objects_, name, obj)

  def __init__(self):
    self.objects_ = {}


def make_parser():
  global logger
  logger = get_logger(logger, "make_parser()")

  def make_double_deref_parser(keyOp):
    return DerefParser(parser=IntrusiveSelectParser(keyOp=keyOp, parser=DerefSelectParser()))

  def make_outer_deref_parser(keyOp):
    return DerefParser(parser=IntrusiveSelectParser(keyOp=keyOp, parser=SelectParser()))

  def make_inner_deref_parser(keyOp):
    return IntrusiveSelectParser(keyOp=keyOp, parser=DerefSelectParser())

  mainParser = DerefSelectParser(parser=SelectParser(), derefKey=False)

  def literalParser(cfg, state):
    return state.resolve(cfg, "literal")
  mainParser.add("literal", literalParser)

  funcParserKeyOp = lambda cfg,state : get_nested_ex(cfg, "func", state)
  funcParser = IntrusiveSelectParser(keyOp=funcParserKeyOp, parser=SelectParser())
  mainParser.add("func", funcParser)

  def make_symm_wrapper(wrapped, symm):
    if symm in (1, "x"):
      return lambda x : wrapped(abs(x))
    elif symm in (2, "xy"):
      return lambda x : sign(x)*wrapped(abs(x))
    else:
      return wrapped

  def make_func_wrapper(func):
    class Wrapper:
      def __call__(self, x):
        if self.symm_ is None:
          return self.call_(x)
        else:
          return self.symm_(self.call_, x)
      def __init__(self, **kwargs):
        self.f_ = kwargs.get("f")
        self.xf_, self.yf_ = kwargs.get("xf"), kwargs.get("yf")
        self.xo_, self.yo_ = kwargs.get("xo"), kwargs.get("yo")
        self.ymin_, self.ymax_ = kwargs.get("ymin"), kwargs.get("ymax")
        self.symm_ = kwargs.get("symm")
      def call_(self, x):
        x = self.xo_ + self.xf_ * x
        y = self.f_(x)
        if y is None:
          return None
        y = self.yo_ + self.yf_ * y
        y = min(max(y, self.ymin_), self.ymax_)
        return y
      def __getattr__(self, name):
        return getattr(self.f_, name)
    def make_setter(wrapper, name):
      def op(value):
        setattr(wrapper, name, value)
      return op
    def make_symm_setter(wrapper):
      def op(value):
        symm = None
        if value in (1, "x"):
          symm = lambda f,x : f(abs(x))
        elif value in (2, "xy"):
          symm = lambda f,x : copysign(f(abs(x)), x)
        wrapper.symm_ = symm
      return op
    def op(cfg, state):
      wrapper = Wrapper()
      wrapper.f_ = func(cfg, state)
      wrapper.xf_ = state.resolve_d(cfg, "xfactor", 1.0, cls=float, setter=make_setter(wrapper, "xf_"))
      wrapper.yf_ = state.resolve_d(cfg, "yfactor", 1.0, cls=float, setter=make_setter(wrapper, "yf_"))
      wrapper.xo_ = state.resolve_d(cfg, "xoffset", 0.0, cls=float, setter=make_setter(wrapper, "xo_"))
      wrapper.yo_ = state.resolve_d(cfg, "yoffset", 0.0, cls=float, setter=make_setter(wrapper, "yo_"))
      wrapper.ymin_ = state.resolve_d(cfg, "ymin", -float("inf"), cls=float, setter=make_setter(wrapper, "ymin_"))
      wrapper.ymax_ = state.resolve_d(cfg, "ymax", float("inf"), cls=float, setter=make_setter(wrapper, "ymax_"))
      symmSetter = make_symm_setter(wrapper)
      symmSetter(state.resolve_d(cfg, "symmetric", 0, setter=symmSetter))
      return wrapper
    return op

  def make_tracker(cfg, state):
    tracker = None
    trackerCfg = state.resolve_d(cfg, "tracker", None, cls=dict)
    if trackerCfg is not None:
      tracker = state.get("parser")("tracker", trackerCfg, state)
      assert(tracker is not None)
    return tracker

  def constant(cfg, state):
    return ConstantFunc(state.resolve(cfg, "value", cls=float), make_tracker(cfg, state))
  funcParser.add("constant", constant)

  @make_func_wrapper
  def segment(cfg, state):
    factor = state.resolve_d(cfg, "factor", 1.0, cls=float)
    clampLeft = state.resolve_d(cfg, "clampLeft", True, cls=bool)
    clampRight = state.resolve_d(cfg, "clampRight", True, cls=bool)
    func = SegmentFunc(None, factor, clampLeft, clampRight, make_tracker(cfg, state))
    pointsCfg, setter = None, None
    pointsCfg = state.resolve_d(cfg, "points")
    if pointsCfg is not None:
      #If points are bound to Var, they have to be stored not in a list, but in a dict,
      #because in this case list is not updated the way it should be
      #when merging vars config into regular one
      if is_dict_type(pointsCfg):
        setter = lambda pointsDict : func.set_points([[float(k),v] for k,v in pointsDict.items()])
      elif is_list_type(pointsCfg):
        for p in pointsCfg:
          if len(p) != 2:
            raise ParseError(pointsCfg, state.get_path(pointsCfg), "points should be a list of value pairs")
        setter = lambda points : func.set_points(points)
      else:
        raise ParseError(pointsCfg, state.get_path(pointsCfg), "bad points format")
      #Registering setter in case "points" is bound to Var
      state.resolve(cfg, "points", setter=setter)
    else:
      pointsCfg = state.resolve_d(cfg, "pointsEx", cls=dict)
      if pointsCfg is not None:
        def make_setter(func, get_items):
          def setter(pointsCfg):
            last, points = [0.0, 0.0], []
            n = len(last)
            for off,pts in get_items(pointsCfg):
              assert len(off) == n
              #off must be created anew to avoid unneeded value transfer to further calculations
              off = [float(off[i]) + last[i] for i in range(n)]
              for p in get_items(pts):
                assert len(p) == n
                #last must be created anew to avoid unneeded value transfer to further calculations
                last = [off[i] + float(p[i]) for i in range(n)]
                points.append(last)
            func.set_points(points)
          return setter
        if is_list_type(pointsCfg):
          setter = make_setter(func, lambda l : l)
    if pointsCfg is None:
      raise ParseError(cfg, state.get_path(cfg), "must specify either 'points' or 'pointsEx'")
    assert setter is not None
    setter(pointsCfg)
    return func
  funcParser.add("segment", segment)

  @make_func_wrapper
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
    if not is_dict_type(coeffs):
      raise ParseError(coeffs, state.get_path(coeffs), "coeffs should be dict-like")
    coeffs = {int(p) : k for p,k in coeffs.items()}
    offset = state.resolve_d(cfg, "offset", 0.0, cls=float)
    func = PolynomialFunc(coeffs, offset, make_tracker(cfg, state))
    coeffsSetter.set_func(func)
    return func
  funcParser.add("poly", poly)

  @make_func_wrapper
  def sigmoid(cfg, state):
    k = state.resolve_d(cfg, "k", 1.0, cls=float)
    p0 = state.resolve_d(cfg, "p0", 0.5, cls=float)
    r = state.resolve_d(cfg, "r", 1.0, cls=float)
    s = state.resolve_d(cfg, "s", 0.0, cls=float)
    func = SigmoidFunc(k, p0, r, s, make_tracker(cfg, state))
    return func
  funcParser.add("sigmoid", sigmoid)

  @make_func_wrapper
  def bezier(cfg, state):
    points = state.resolve(cfg, "points", cls=list)
    func = BezierFunc(points, make_tracker(cfg, state))
    return func
  funcParser.add("bezier", bezier)

  @make_func_wrapper
  def sbezier(cfg, state):
    points = state.resolve(cfg, "points", cls=list)
    func = SegmentedBezierFunc(points, make_tracker(cfg, state))
    return func
  funcParser.add("sbezier", sbezier)

  @make_func_wrapper
  def weighted(cfg, state):
    o = state.resolve(cfg, "degree", cls=float)
    w = state.resolve(cfg, "weight", cls=float)
    db = state.resolve_d(cfg, "deadband", 0.0, cls=float)
    offset = state.resolve_d(cfg, "offset", 0.0, cls=float)
    factor = state.resolve_d(cfg, "factor", 1.0, cls=float)
    func = WeightedFunc(o, w, db, factor, offset, make_tracker(cfg, state))
    return func
  funcParser.add("weighted", weighted)

  @make_func_wrapper
  def hermite(cfg, state):
    import hermite
    points = state.resolve(cfg, "points")
    if is_dict_type(points):
      points = points.items()
    for i in range(len(points)):
      points[i] = tuple(float(e) for e in points[i])
    points.sort(key=lambda p : p[0])
    c = state.resolve_d(cfg, "c", None, cls=float)
    calc_ms = None
    if c is None:
      calc_ms = lambda xs,ys : [hermite.m_fd(k, xs, ys) for k in range(len(xs))]
    else:
      c = float(c)
      calc_ms = lambda xs,ys : [hermite.m_c(k, xs, ys, c) for k in range(len(xs))]
    extend = state.resolve_d(cfg, "extend", 0, cls=int)
    func = hermite.HermiteFunc2(points, calc_ms, extend, make_tracker(cfg, state))
    def set_points(points):
      if is_dict_type(points):
        points = [[float(x), y] for x,y in points.items()]
      points.sort(key=lambda p : p[0])
      func.set_points(points)
    state.resolve(cfg, "points", setter=set_points)
    return func
  funcParser.add("hermite", hermite)

  @make_func_wrapper
  def presetFunc(cfg, state):
    config = state.get("main").get("config")
    presetName = state.resolve_d(cfg, "name", None, cls=str)
    if presetName is None:
      raise ParseError(cfg, state.get_path(cfg), "preset name was not specified")
    presets = config.get("presets", {})
    presetCfg = get_nested_d(presets, presetName, None)
    if presetCfg is None:
      raise ParseError(cfg, state.get_path(cfg), "preset '{}' does not exist; available presets are: '{}'".format(presetName, [str2(k) for k in presets.keys()]))
    argsPresent = False
    if "args" in cfg:
      state.push_args(cfg)
      argsPresent = True
    try:
      return state.get("parser")("func", presetCfg, state)
    finally:
      if argsPresent == True:
        state.pop_args()
  funcParser.add("preset", presetFunc)

  @make_func_wrapper
  def proxyFunc(cfg, state):
    class ProxyFunc:
      def __call__(self, x):
        assert self.next_ is not None
        return self.next_(x)
      def set_next(self, next_):
        self.next_ = next_
      def get_next(self):
        return self.next_
      def __init__(self, next_):
        self.next_ = next_
    func = ProxyFunc(None)
    main = state.get("main")
    class Setter:
      def __call__(self, cfg, keys=None):
        if keys is None or self.nextSetter_(cfg, keys) == False:
          parser = self.main_.get("parser")
          state = ParserState(self.main_)
          next_ = parser("func", cfg, state)
          self.func_.set_next(next_)
          nextSetter = parser("funcSetter", cfg, state)
          nextSetter.set_func(next_)
          self.nextSetter_ = nextSetter
      def __init__(self, main, func):
        self.main_, self.func_, self.nextSetter_ = main, func, None
    setter = Setter(main, func)
    nextCfg = state.resolve(cfg, "next", setter=setter)
    #should init func
    setter(nextCfg)
    return func
  funcParser.add("proxy", proxyFunc)


  #func setters
  funcSetterParserKeyOp = lambda cfg,state : get_nested_ex(cfg, "func", state)
  funcSetterParser = IntrusiveSelectParser(keyOp=funcSetterParserKeyOp, parser=SelectParser())
  mainParser.add("funcSetter", funcSetterParser)

  def hermiteSetter(cfg, state):
    class Setter:
      def __call__(self, cfg, keys):
        """Returns True if property was set, False otherwise (in this case caller should recreate func and setter)."""
        if keys is None:
          return False
        elif keys[0] == "symmetric":
          return False
        elif keys[0] == "points":
          assert self.func_ is not None
          points = cfg["points"]
          if is_dict_type(points):
            points = [[float(k), float(v)] for k,v in points.items()]
          points.sort(key=lambda p : p[0])
          self.func_.set_points(points)
          return True
        else:
          raise RuntimeError("unknown keys: '{}'".format(keys))
      def set_func(self, func):
        self.func_ = func
    return Setter()
  funcSetterParser.add("hermite", hermiteSetter)


  #Filters
  filterParserKeyOp = lambda cfg,state : get_nested(cfg, "type")
  filterParser = IntrusiveSelectParser(keyOp=filterParserKeyOp, parser=SelectParser())
  mainParser.add("filter", filterParser)

  def parseExpFilter(cfg, state):
    weight = state.resolve(cfg, "weight", cls=float)
    return ExpFilter(weight)
  filterParser.add("exp", parseExpFilter)

  def parsePolyFilter(cfg, state):
    degree = state.resolve(cfg, "degree", cls=float)
    numSamples = state.resolve(cfg, "numSamples", cls=int)
    delay = state.resolve_d(cfg, "delay", 0.0, cls=float)
    return PolyApproxFilter(degree, numSamples, delay)
  filterParser.add("poly", parsePolyFilter)

  #Curves
  curveParserKeyOp=lambda cfg,state : get_nested(cfg, "curve")
  #because curve cfg nodes are fuzed with action (i.e. move) cfg nodes,
  #this needs to be inner deref parser to process '"curve" : "obj:..."'
  curveParser = make_inner_deref_parser(keyOp=curveParserKeyOp)
  mainParser.add("curve", curveParser)

  def parseAxisLinker(cfg, state):
    def resolve_axis(cfg, name, state):
      fnAxis = state.resolve(cfg, name, cls=str)
      try:
        return fnAxis, state.get_axis_by_full_name(fnAxis)
      except RuntimeError as e:
        raise ParseError(fnAxis, state.get_path(fnAxis), e)
    fnControlledAxis, controlledAxis = resolve_axis(cfg, "follower", state)
    class FuncSetter:
      def __call__(self, func):
        self.axisLinker.set_func(func)
    funcSetter = FuncSetter()
    func = get_deprecated_func(cfg, state, setter=funcSetter)
    fnControllingAxis, controllingAxis = resolve_axis(cfg, "leader", state)
    adjustOffset = state.resolve_d(cfg, "adjustOffset", True, cls=bool)
    linker = AxisLinker(controllingAxis, controlledAxis, func, adjustOffset)
    s = state.resolve_d(cfg, "state", False, cls=bool)
    linker.set_state(s)
    funcSetter.axisLinker = linker
    controlledAxis.add_listener(linker)
    controllingAxis.add_listener(linker)
    state.add_curve(fnControlledAxis, linker)
    state.add_curve(fnControllingAxis, linker)
    return linker

  curveParser.add("linker", parseAxisLinker)

  def get_deprecated_prop(cfg, propName, sectionName, dfault, state, **kwargs):
    v = None
    if sectionName is None:
      v = state.resolve_d(cfg, propName, dfault, **kwargs)
    else:
      v = state.resolve_d(cfg, propName, None, **kwargs)
      if v is not None:
        logger.warning("'{}' in curve config is deprecated, move in into '{}' ({})".format(propName, sectionName, str2(cfg, 100)))
      else:
        sectionCfg = get_nested_d(cfg, sectionName, None)
        v = dfault if sectionCfg is None else state.resolve_d(sectionCfg, propName, dfault, **kwargs)
    return v

  def get_deprecated_func(cfg, state, **kwargs):
    cfg2 = get_nested_ex(cfg, "func", state)
    funcOrCfg = state.deref(cfg2, **kwargs)
    if cfg2 != funcOrCfg:
      if is_dict_type(funcOrCfg):
        cfg2 = funcOrCfg
      else:
        return funcOrCfg
    if is_str_type(cfg2):
      logger.warning("'func' should be separate config node ({})".format(str2(cfg, 200)))
    elif is_dict_type(cfg2):
      cfg = cfg2
    else:
      raise ParseError(cfg2, state.get_path(cfg2), "invalid func")
    return state.get("parser")("func", cfg, state)

  def makeSensModOp(cfg, state, sensOp, combine=lambda a,b: a*b):
    #cfg is curve cfg
    sensModCfg = get_deprecated_prop(cfg, "sensMod", "dynamic", None, state)
    if sensModCfg is not None:
      axis = state.get_axis_by_full_name(state.resolve(sensModCfg, "axis", cls=str))
      func = state.get("parser")("func", get_nested(sensModCfg, "func"), state)
      class SensModOp:
        def calc(self, x, timestamp):
          n, f = self.next_.calc(x, timestamp), self.func_(self.axis_.get())
          return None if n is None or f is None else self.combine_(n, f)
        def reset(self):
          self.next_.reset()
        def __init__(self, combine, next, func, axis):
          self.next_, self.combine_, self.func_, self.axis_ = next, combine, func, axis
      sensOp = SensModOp(combine, sensOp, func, axis)
    return sensOp

  def makeIterativeInputOp(cfg, outputOp, state, sectionName=None):
    eps = get_deprecated_prop(cfg, "eps", sectionName, 0.001, state, cls=float)
    numSteps = get_deprecated_prop(cfg, "numSteps", sectionName, 100, state, cls=int)
    inputOp = IterativeInputOp(outputOp=outputOp, eps=eps, numSteps=numSteps)
    inputLimits = get_deprecated_prop(cfg, "inputLimits", sectionName, None, state)
    inputStep = get_deprecated_prop(cfg, "inputStep", sectionName, 0.1, state, cls=float)
    expandLimits = get_deprecated_prop(cfg, "expandLimits", sectionName, False, state, cls=bool)
    inputOp = LookupOp(inputOp, outputOp, inputStep, inputLimits, expandLimits)
    #inputOp = LimitedOpToOp(inputOp, inputLimits)
    return inputOp

  def parseInputBasedCurve2(cfg, state):
    fnAxis = state.resolve(cfg, "axis", cls=str)
    axis = state.get_axis_by_full_name(fnAxis)
    dynamicCfg = get_nested(cfg, "dynamic")
    signDDOp = SignDistanceDeltaOp()
    timeDDOp = TimeDistanceDeltaOp(
      resetTime=state.resolve_d(dynamicCfg, "resetTime", float("inf"), cls=float),
      holdTime=state.resolve_d(dynamicCfg, "holdTime", 0.0, cls=float)
    )
    deltaOp = CombineDeltaOp(
      combine=lambda x,s : x*s,
      ops=(ReturnDeltaOp(), AccumulateDeltaOp(get_deprecated_func(dynamicCfg, state), ops=[signDDOp, timeDDOp]))
    )
    outputOp = FuncOp(func=get_deprecated_func(get_nested(cfg, "static"), state))
    inputOp = makeIterativeInputOp(cfg, outputOp, state, "static")
    deltaOp = makeSensModOp(cfg, state, deltaOp)
    deltaOp = DeadzoneDeltaOp(deltaOp, state.resolve_d(cfg, "deadzone", 0.0, cls=float))
    resetOpsOnAxisMove = state.resolve_d(cfg, "resetOpsOnAxisMove", True, cls=bool)
    ivLimits = state.resolve_d(cfg, "inputLimits", (-1.0, 1.0), cls=list)
    curve = InputBasedCurve2(axis=axis, inputOp=inputOp, outputOp=outputOp, deltaOp=deltaOp, inputValueLimits=ivLimits, resetOpsOnAxisMove=resetOpsOnAxisMove)
    axis.add_listener(curve)
    state.add_curve(fnAxis, curve)
    return curve
  curveParser.add("input2", parseInputBasedCurve2)

  def parseOffsetCurve(cfg, state):
    #axis tracker
    top = AxisTrackerChainCurve(next=None)
    curve = top
    fnAxis = state.resolve(cfg, "axis", cls=str)
    axis = state.get_axis_by_full_name(fnAxis)
    axis.add_listener(curve)
    #accumulate
    #Order of ops should not matter
    dynamicCfg = get_nested(cfg, "dynamic")
    valueDDOp = SignDistanceDeltaOp()
    valueDDOp = TimeDistanceDeltaOp(next=valueDDOp, resetTime=dynamicCfg.get("resetTime", float("inf")), holdTime=dynamicCfg.get("holdTime", 0.0))
    deltaDOp = ReturnDeltaOp()
    deltaDOp = DeadzoneDeltaOp(deltaDOp, dynamicCfg.get("deadzone", 0.0))
    deltaDOp = makeSensModOp(cfg, state, deltaDOp)
    combine = lambda a,b: a+b
    class ResetOp:
      def calc(self, value):
        return value if self.value_ is None else self.value_
      def reset(self):
        pass
      def __init__(self, value=None):
        self.value_ = value
    resetOnMoveAxis = state.resolve_d(cfg, "resetOnMoveAxis", True, cls=bool)
    inputOp = ResetOp(0.0 if resetOnMoveAxis else None)
    accumulateChainCurve = AccumulateRelChainCurve(next=None, valueDDOp=valueDDOp, deltaDOp=deltaDOp, combine=combine, inputOp=inputOp, resetOnMoveAxis=resetOnMoveAxis)
    top.add("accumulate", accumulateChainCurve)
    curve.set_next(accumulateChainCurve)
    #transform accumulated
    dynamicOutputOp = FuncOp(func=get_deprecated_func(dynamicCfg, state))
    dynamicInputOp = makeIterativeInputOp(cfg, dynamicOutputOp, state, "dynamic")
    dynamicChainCurve = TransformAbsChainCurve(next=None, inputOp=dynamicInputOp, outputOp=dynamicOutputOp)
    top.add("dynamic", dynamicChainCurve)
    accumulateChainCurve.set_next(dynamicChainCurve)
    #offset transformed
    offsetChainCurve = OffsetAbsChainCurve(next=None)
    top.add("offset", offsetChainCurve)
    dynamicChainCurve.set_next(offsetChainCurve)
    #transform offset
    staticCfg = get_nested(cfg, "static")
    staticOutputOp = FuncOp(func=get_deprecated_func(staticCfg, state))
    staticInputOp = makeIterativeInputOp(cfg, staticOutputOp, state, "static")
    staticChainCurve = TransformAbsChainCurve(next=None, inputOp=staticInputOp, outputOp=staticOutputOp)
    top.add("static", staticChainCurve)
    offsetChainCurve.set_next(staticChainCurve)
    #move axis
    axisChainCurve = AxisChainCurve(axis=axis)
    top.add("axis", axisChainCurve)
    staticChainCurve.set_next(axisChainCurve)
    state.add_curve(fnAxis, curve)
    return top
  curveParser.add("offset", parseOffsetCurve)

  def makeInputValueDDOp(cfg, state):
    signChangeDeadZone = state.resolve_d(cfg, "signChangeDeadZone", 0.0, cls=bool)
    inputValueDDOp = SignDistanceDeltaOp(deadzone=signChangeDeadZone)
    resetFuncCfg = get_nested_d(cfg, "resetFunc", None)
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
    #cfg is curve cfg
    inputDeltaDOp = ReturnDeltaOp()
    deadzone = get_deprecated_prop(cfg, "deadzone", "dynamic", 0.0, state, cls=float)
    inputDeltaDOp = DeadzoneDeltaOp(inputDeltaDOp, deadzone)
    filterCfg = get_deprecated_prop(cfg, "filter", "dynamic", None, state)
    if filterCfg is not None:
      filter_ = state.get("parser")("filter", filterCfg, state)
      inputDeltaDOp = FilterOp(filter_, inputDeltaDOp)
    inputDeltaDOp = makeSensModOp(cfg, state, inputDeltaDOp)
    inputDeltaDDOp = DistanceDeltaFromDeltaOp(inputDeltaDOp)
    return inputDeltaDDOp

  def makeStaticFilterCurve(top, bottom, staticCfg, state):
    staticFilterCfg = get_nested_d(staticCfg, "filter", None)
    if staticFilterCfg is not None:
      filter_ = state.get("parser")("filter", staticFilterCfg, state)
      filterOp = FilterOp(filter_, None)
      filterCurve = TransformAbsChainCurve(next=None, inputOp=ReturnValueInputOp(), outputOp=filterOp, resetOnMoveAxis=True)
      top.add("staticFilter", filterCurve)
      bottom.set_next(filterCurve)
      bottom = filterCurve
    return bottom

  def makeUpdatedCurve(top, bottom, cfg, state):
    updatedCfg = get_nested_d(cfg, "updated", None)
    if updatedCfg is not None:
      op = None
      opCfg = get_nested_d(updatedCfg, "op")
      opType = state.resolve(opCfg, "type", cls=str)
      if opType == "distance":
        funcCfg = get_nested_d(opCfg, "func")
        func = state.get("main").get("parser")("func", funcCfg, state)
        keepSpeed = state.resolve_d(opCfg, "keepSpeed", False, cls=bool)
        op = DistanceUpdatedChainCurveOp(func, keepSpeed)
      elif opType == "accel":
        accelerationCfg = state.resolve(opCfg, "acceleration")
        accelerationFunc = None
        if is_dict_type(accelerationCfg):
          accelerationFunc = state.get("parser")("func", accelerationCfg, state)
        else:
          acceleration = float(accelerationCfg)
          accelerationFunc = lambda x : acceleration
        decelerationCfg = state.resolve_d(opCfg, "deceleration", 0.0, cls=float)
        decelerationFunc = None
        if is_dict_type(decelerationCfg):
          decelerationFunc = state.get("parser")("func", decelerationCfg, state)
        else:
          deceleration = float(decelerationCfg)
          decelerationFunc = lambda x : deceleration
        minSpeed = float(state.resolve_d(opCfg, "minSpeed", 0.0, cls=float))
        maxSpeed = float(state.resolve_d(opCfg, "maxSpeed", 0.0, cls=float))
        keepAcceleration = state.resolve_d(opCfg, "keepAcceleration", False, cls=bool)
        op = AccelUpdatedChainCurveOp(accelerationFunc, decelerationFunc, minSpeed, maxSpeed, keepAcceleration)
      else:
        raise ParseError(opType, state.get_path(opType), "unknown op type")
      sensModCfg = get_nested_d(updatedCfg, "sensMod")
      if sensModCfg is not None:
        sensModAxis = state.get_axis_by_full_name(state.resolve(sensModCfg, "axis", cls=str))
        sensModFunc = state.get("parser")("func", get_nested(sensModCfg, "func"), state)
        op = SensModUpdatedChainCurveOp(op, sensModFunc, sensModAxis)
      modeName = state.resolve_d(updatedCfg, "mode", "absolute", cls=str)
      mode = {
        "absolute" : UpdatedChainCurve.MODE_ABSOLUTE,
        "relative" : UpdatedChainCurve.MODE_RELATIVE
      }.get(modeName.lower())
      if mode is None:
        raise ParseError(modeName, state.get_path(modeName), "bad mode")
      updatedChainCurve = UpdatedChainCurve(top, None, op, mode)
      state.get("main").add_to_updated(lambda tick,ts : updatedChainCurve.update(tick, ts))
      top.add_stateful(updatedChainCurve)
      top.add("updated", updatedChainCurve)
      bottom.set_next(updatedChainCurve)
      bottom = updatedChainCurve
    return bottom

  def parseAccelCurve(cfg, state):
    #axis tracker
    top = AxisTrackerChainCurve(next=None)
    bottom = top
    fnAxis = state.resolve(cfg, "axis", cls=str)
    axis = state.get_axis_by_full_name(fnAxis)
    axis.add_listener(top)
    #accelerate
    #Order of ops should not matter
    dynamicCfg = get_nested_d(cfg, "dynamic", None)
    if dynamicCfg is not None:
      valueDDOp = makeInputValueDDOp(dynamicCfg, state)
      #settings are taken from cfg here
      deltaDDOp = makeInputDeltaDDOp(cfg, state)
      dynamicOutputOp = FuncOp(func=get_deprecated_func(dynamicCfg, state))
      combineValue = lambda value,x: value+x
      combineDelta = lambda delta,factor: delta*factor
      resetOnMoveAxis = get_deprecated_prop(cfg, "resetOnMoveAxis", "dynamic", True, state, cls=bool)
      resetNext = state.resolve_d(dynamicCfg, "resetNext", True, cls=bool)
      eps = state.resolve_d(dynamicCfg, "eps", 1e-4, cls=float)
      accelChainCurve = DeltaRelChainCurve(
        next=None,
        valueDDOp=valueDDOp, deltaDDOp=deltaDDOp, outputOp=dynamicOutputOp,
        combineValue=combineValue, combineDelta=combineDelta,
        resetOnMoveAxis=resetOnMoveAxis, resetNext=resetNext, eps=eps)
      top.add("dynamic", accelChainCurve)
      bottom.set_next(accelChainCurve)
      bottom = accelChainCurve
    #accumulate, filter, and transform (and update)
    staticCfg = get_nested_d(cfg, "static", None)
    if staticCfg is not None:
      #accumulate
      relToAbsChainCurve = RelToAbsChainCurve(next=None)
      top.add("rel2abs", relToAbsChainCurve)
      bottom.set_next(relToAbsChainCurve)
      bottom = relToAbsChainCurve
      #filter
      bottom = makeStaticFilterCurve(top, bottom, staticCfg, state)
      #transform
      staticOutputOp = FuncOp(func=get_deprecated_func(staticCfg, state))
      staticInputOp = makeIterativeInputOp(cfg, staticOutputOp, state, "static")
      staticChainCurve = TransformAbsChainCurve(next=None, inputOp=staticInputOp, outputOp=staticOutputOp)
      top.add("static", staticChainCurve)
      bottom.set_next(staticChainCurve)
      bottom = staticChainCurve
      #update
      bottom = makeUpdatedCurve(top, bottom, cfg, state)
    #move axis
    axisChainCurve = AxisChainCurve(axis=axis)
    top.add("axis", axisChainCurve)
    bottom.set_next(axisChainCurve)
    state.add_curve(fnAxis, top)
    return top
  curveParser.add("accel", parseAccelCurve)

  def parseFullDeltaCurve(cfg, state):
    #axis tracker
    top = AxisTrackerChainCurve(next=None)
    bottom = top
    fnAxis = state.resolve(cfg, "axis", cls=str)
    axis = state.get_axis_by_full_name(fnAxis)
    axis.add_listener(top)
    #accelerate
    #Order of ops should not matter
    #just getting config node or arg/obj reference here; resolving would be handled later by func parser
    #as a rule, config nodes that are passed to parser (dictionary or arg/obj/var reference nodes) should be retrieved by get_nested[_d](),
    #and other elements - by state.resolve[_d]()
    dynamicCfg = get_nested_d(cfg, "dynamic", None)
    if dynamicCfg is not None:
      inputValueDDOp = makeInputValueDDOp(dynamicCfg, state)
      #settings are taken from cfg here
      inputDeltaDDOp = makeInputDeltaDDOp(cfg, state)
      dynamicOutputValueOp = FuncOp(func=get_deprecated_func(dynamicCfg, state))
      dynamicInputValueOp = makeIterativeInputOp(dynamicCfg, dynamicOutputValueOp, state, None)
      resetOnMoveAxis = get_deprecated_prop(cfg, "resetOnMoveAxis", "dynamic", True, state, cls=bool)
      #resetNext is taken from dynamicCfg
      resetNext = state.resolve_d(dynamicCfg, "resetNext", True, cls=bool)
      accelChainCurve = FullDeltaRelChainCurve(
        next=None,
        inputValueDDOp=inputValueDDOp, inputDeltaDDOp=inputDeltaDDOp,
        outputValueOp=dynamicOutputValueOp, inputValueOp=dynamicInputValueOp,
        resetOnMoveAxis=resetOnMoveAxis, resetNext=resetNext)
      top.add("dynamic", accelChainCurve)
      bottom.set_next(accelChainCurve)
      bottom = accelChainCurve
    #accumulate, filter, and transform (and update)
    staticCfg = get_nested_d(cfg, "static", None)
    if staticCfg is not None:
      #accumulate
      relToAbsChainCurve = RelToAbsChainCurve(next=None)
      top.add("rel2abs", relToAbsChainCurve)
      bottom.set_next(relToAbsChainCurve)
      bottom = relToAbsChainCurve
      #filter
      #cannot include filter op in staticOutputOp of the next curve,
      #because staticInputOp calls staticOutputOp to recalculate input value,
      #and this will throw off filter
      bottom = makeStaticFilterCurve(top, bottom, staticCfg, state)
      #transform
      staticOutputOp = FuncOp(func=get_deprecated_func(staticCfg, state))
      staticInputOp = makeIterativeInputOp(cfg, staticOutputOp, state, "static")
      staticResetOnMoveAxis = get_deprecated_prop(cfg, "resetOnMoveAxis", "static", True, state, cls=bool)
      staticAllowOffLimits = state.resolve_d(staticCfg, "allowOffLimits", False, cls=bool)
      staticChainCurve = TransformAbsChainCurve(
        next=None, inputOp=staticInputOp, outputOp=staticOutputOp,
        resetOnMoveAxis=staticResetOnMoveAxis, allowOffLimits=staticAllowOffLimits)
      top.add("static", staticChainCurve)
      bottom.set_next(staticChainCurve)
      bottom = staticChainCurve
      #update
      bottom = makeUpdatedCurve(top, bottom, cfg, state)
    #move axis
    axisChainCurve = AxisChainCurve(axis=axis)
    top.add("axis", axisChainCurve)
    bottom.set_next(axisChainCurve)
    state.add_curve(fnAxis, top)
    return top
  curveParser.add("fulldelta", parseFullDeltaCurve)

  def parseAbsToAbsCurve(cfg, state):
    #axis tracker
    top = AxisTrackerChainCurve(next=None)
    bottom = top
    fnAxis = state.resolve(cfg, "axis", cls=str)
    axis = state.get_axis_by_full_name(fnAxis)
    axis.add_listener(top)
    #convert abs changes to deltas
    st = state.resolve_d(cfg, "abs2rel.state", True, cls=bool)
    resetNext = state.resolve_d(cfg, "abs2rel.resetNext", "relative", cls=str)
    resetNext = {
      "none" : AbsToRelChainCurve.NEXT_NONE,
      "relative" : AbsToRelChainCurve.NEXT_REL,
      "absolute" : AbsToRelChainCurve.NEXT_ABS,
      "both" : AbsToRelChainCurve.NEXT_BOTH
    }.get(resetNext.lower())
    limits = state.resolve_d(cfg, "abs2rel.limits", None, cls=list)
    absToRelChainCurve = AbsToRelChainCurve(top, None, None, st, resetNext, limits)
    top.add("abs2rel", absToRelChainCurve)
    bottom.set_next(absToRelChainCurve)
    bottom = absToRelChainCurve
    #accelerate
    accelChainCurve = None
    dynamicCfg = get_nested_d(cfg, "dynamic", None)
    if dynamicCfg is not None:
      dynamicCurveType = state.resolve_d(dynamicCfg, "type", "fulldelta", cls=str)
      if dynamicCurveType == "accel":
        valueDDOp = makeInputValueDDOp(dynamicCfg, state)
        deltaDDOp = makeInputDeltaDDOp(cfg, state) #settings are taken from cfg here
        dynamicOutputOp = FuncOp(func=get_deprecated_func(dynamicCfg, state))
        combineValue = lambda value,x: value + x
        combineDelta = lambda delta,factor: delta * factor
        resetOnMoveAxis = state.resolve_d(dynamicCfg, "resetOnMoveAxis", True, cls=bool)
        resetNext = state.resolve_d(dynamicCfg, "resetNext", True, cls=bool)
        eps = state.resolve_d(dynamicCfg, "eps", 1e-4, cls=float)
        accelChainCurve = DeltaRelChainCurve(
          next=None,
          valueDDOp=valueDDOp, deltaDDOp=deltaDDOp, outputOp=dynamicOutputOp,
          combineValue=combineValue, combineDelta=combineDelta,
          resetOnMoveAxis=resetOnMoveAxis, resetNext=resetNext, eps=eps)
      elif dynamicCurveType == "fulldelta":
        inputValueDDOp = makeInputValueDDOp(dynamicCfg, state)
        inputDeltaDDOp = makeInputDeltaDDOp(cfg, state) #settings are taken from cfg here
        dynamicOutputValueOp = FuncOp(func=get_deprecated_func(dynamicCfg, state))
        dynamicInputValueOp = makeIterativeInputOp(dynamicCfg, dynamicOutputValueOp, state, None)
        resetOnMoveAxis = state.resolve_d(dynamicCfg, "resetOnMoveAxis", True, cls=bool)
        resetNext = state.resolve_d(dynamicCfg, "resetNext", True, cls=bool)
        accelChainCurve = FullDeltaRelChainCurve(
          next=None,
          inputValueDDOp=inputValueDDOp, inputDeltaDDOp=inputDeltaDDOp,
          outputValueOp=dynamicOutputValueOp, inputValueOp=dynamicInputValueOp,
          resetOnMoveAxis=resetOnMoveAxis, resetNext=resetNext)
      else:
        raise RuntimeError("unknown dynamic curve type: '{}'".format(dynamicCurveType))
      top.add("dynamic", accelChainCurve)
      absToRelChainCurve.set_next(accelChainCurve, AbsToRelChainCurve.NEXT_REL)
      bottom = accelChainCurve
    #accumulate
    relToAbsChainCurve = RelToAbsChainCurve(next=None)
    top.add("rel2abs", relToAbsChainCurve)
    absToRelChainCurve.set_next(relToAbsChainCurve, AbsToRelChainCurve.NEXT_ABS)
    bottom.set_next(relToAbsChainCurve)
    bottom = relToAbsChainCurve
    #filter, and transform (and update)
    staticCfg = get_nested_d(cfg, "static", None)
    if staticCfg is not None:
      #accumulate
      #filter
      #cannot include filter op in staticOutputOp of the next curve,
      #because staticInputOp calls staticOutputOp to recalculate input value,
      #and this will throw off filter
      bottom = makeStaticFilterCurve(top, bottom, staticCfg, state)
      #transform
      staticOutputOp = FuncOp(func=get_deprecated_func(staticCfg, state))
      staticInputOp = makeIterativeInputOp(cfg, staticOutputOp, state, "static")
      staticResetOnMoveAxis = state.resolve_d(staticCfg, "resetOnMoveAxis", False, cls=bool)
      staticAllowOffLimits = state.resolve_d(staticCfg, "allowOffLimits", False, cls=bool)
      staticChainCurve = TransformAbsChainCurve(
        next=None, inputOp=staticInputOp, outputOp=staticOutputOp,
        resetOnMoveAxis=staticResetOnMoveAxis, allowOffLimits=staticAllowOffLimits)
      top.add("static", staticChainCurve)
      bottom.set_next(staticChainCurve)
      bottom = staticChainCurve
    #unlink on demand
    unlinkableCfg = get_nested_d(cfg, "unlinkable", {})
    unlinkableState = state.resolve_d(unlinkableCfg, "state", True, cls=bool)
    unlinkableAllowOffLimits = state.resolve_d(unlinkableCfg, "allowOffLimits", False, cls=bool)
    unlinkableAbsChainCurve = UnlinkableAbsChainCurve(None, state=unlinkableState, allowOffLimits=unlinkableAllowOffLimits)
    top.add("unlinkable", unlinkableAbsChainCurve)
    bottom.set_next(unlinkableAbsChainCurve)
    bottom = unlinkableAbsChainCurve
    #update
    bottom = makeUpdatedCurve(top, bottom, cfg, state)
    #move axis
    axisChainCurve = AxisChainCurve(axis=axis)
    top.add("axis", axisChainCurve)
    bottom.set_next(axisChainCurve)
    state.add_curve(fnAxis, top)
    return top
  curveParser.add("abs2abs", parseAbsToAbsCurve)

  def parsePresetCurve(cfg, state):
    if logger.isEnabledFor(logging.DEBUG): logger.debug("parsePresetCurve(): cfg: '{}'".format(str2(cfg)))
    config = state.get("main").get("config")
    presetName = state.resolve_d(cfg, "name", None, cls=str)
    if presetName is None:
      raise ParseError(cfg, state.get_path(cfg), "preset name was not specified")
    presets = config.get("presets", {})
    presetCfg = get_nested_d(presets, presetName, None)
    if presetCfg is None:
      raise ParseError(cfg, state.get_path(cfg), "preset '{}' does not exist; available presets are: '{}'".format(presetName, [str2(k) for k in presets.keys()]))
    #creating curve
    if "args" in cfg:
      if logger.isEnabledFor(logging.DEBUG): logger.debug("parsePresetCurve(): args: '{}'".format(str2(get_nested_d(cfg, "args"))))
      state.push_args(cfg)
      try:
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
    fnAxis = state.resolve(cfg, "axis", cls=str)
    #To init state
    state.get_axis_by_full_name(fnAxis)
    curve = NoopCurve(value=state.resolve_d(cfg, "value", 0.0, cls=float))
    state.add_curve(fnAxis, curve)
    return curve
  curveParser.add("noop", parseNoopCurve)

  #EP
  def parseBasesDecorator(wrapped):
    def worker(cfg, state):
      """Merges all base config definitions if they are specified."""
      bases = state.resolve_d(cfg, "bases", None, cls=list)
      if bases is None:
        return cfg
      else:
        sectNames = ("presets",)
        config = state.get("main").get("config")
        full = {}
        for baseName in bases:
          if logger.isEnabledFor(logging.DEBUG): logger.debug("Parsing base : {}".format(baseName))
          base = get_nested_from_sections_d(config, sectNames, baseName, None)
          if base is None:
            raise ParseError(cfg, state.get_path(cfg), "preset '{}' was not found".format(str2(baseName)))
          merge_dicts(full, worker(base, state))
        merge_dicts(full, cfg)
        del full["bases"]
        return full
    def parseBasesOp(cfg, state):
      expandedCfg = worker(cfg, state)
      if logger.isEnabledFor(logging.DEBUG): logger.debug("parseBasesOp():\n{}\n->\n{}".format(str2(cfg), str2(expandedCfg)))
      return wrapped(expandedCfg, state)
    return parseBasesOp

  def parseExternal(propName, groupNames):
    def parseExternalOp(cfg, state):
      config = state.get("main").get("config")
      name = cfg.get(propName, None)
      if name is None:
        name = state.resolve(cfg, "name", cls=str)
      if logger.isEnabledFor(logging.DEBUG): logger.debug("Parsing {} '{}'".format(propName, name))
      #preset or class name can be specified by arg, so need to deref it here
      name = state.deref(name)
      externalCfg = get_nested_from_sections_d(config, groupNames, name, None)
      if externalCfg is None:
        raise ParseError(cfg, state.get_path(cfg), "'{}' not found".format(str2(name)))
      state.push_args(cfg)
      try:
        return state.get("parser")("ep", externalCfg, state)
      finally:
        state.pop_args()
    return parseExternalOp

  def epParserKeyOp(cfg, state):
    names = ("preset",)
    if is_dict_type(cfg):
      for name in names:
        if name in cfg or get_nested_d(cfg, "type", "") == name:
          return name
    return "ep"

  epParser = IntrusiveSelectParser(keyOp=epParserKeyOp, parser=SelectParser())
  mainParser.add("ep", epParser)
  epParser.add("preset", parseExternal("preset", ("presets",)))

  @parseBasesDecorator
  def parseEP(cfg, state):
    """
    Constructs ep chain from components as specified in cfg.
    At the top of this chain is a HeadEP that stores all initialized components.
    Some of initialized components are then linked one after another.
    Each component is described by dedicated section in cfg. If a section is missing, components is not intialized.
    next and modes components are mutually exclusive.
    Init order: objects, (next or modes), state, sens, modifiers, binds
    Link order: modifiers, sens, binds, state, (next or modes)
    """
    parser = state.get("parser").get("sc")
    state.push_args(cfg)
    state.push("curves", {})
    #Init head ep
    parent = state.at("eps", 0)
    headEP = HeadEP(parent=parent)
    state.push("eps", headEP)
    #Since python 2.7 does not support nonlocal variables, declaring 'ep' as list to allow parse_component() modify it
    if logger.isEnabledFor(logging.DEBUG): logger.debug("parsing ep {}".format(cfg))
    def parse_component(name, set_component=None):
      if logger.isEnabledFor(logging.DEBUG): logger.debug("parsing component '{}'".format(name))
      if name in cfg:
        t = parser(name, cfg, state)
        if t is not None and set_component is not None:
          set_component(headEP, name, t)
    ep = [None]
    def link_component(name, op=None):
      if logger.isEnabledFor(logging.DEBUG): logger.debug("linking component '{}'".format(name))
      t = headEP.get_component(name, None)
      if t is not None:
        if op is not None:
          op(ep[0], t)
        ep[0] = t
    def set_next(next, ep):
      if next is not None:
        ep.set_next(next)
    def add_default_bind(next, ep):
      if next is not None:
        #By default next ep is added to level 0 so it will be able to process events that were processed by other binds.
        #This is useful in case like when a bind and a mode both need to process some axis event.
        defaultBindET = state.resolve_d(cfg, "defaultBind.on", None)
        if defaultBindET is not None:
          defaultBindET = state.get("parser")("et", defaultBindET, state)
        defaultBindLevel = state.resolve_d(cfg, "defaultBind.level", 0, cls=int)
        ep.add(defaultBindET, next, defaultBindLevel)
    try:
      #TODO Refactor
      if len(cfg) == 0:
        def noop(event):
          return False
        return noop
      #Parse components
      if "modes" in cfg and "next" in cfg:
        raise ParseError(cfg, state.get_path(cfg), "'next' and 'modes' components are mutually exclusive")
      def set_component(headEP, name, t):
        headEP.set_component(name, t)
      assert headEP is state.at("eps", 0)
      parseOrder = (
        ("objects", None), ("next", set_component), ("modes", None), ("state", set_component),
        ("sens", set_component), ("hold", set_component), ("modifiers", set_component), ("binds", set_component), ("mapping", set_component))
      for name,set_component in parseOrder:
        parse_component(name, set_component)
      #Link components
      #Linking is performed in reverse order - from "tail" to "head", with linking "tail" to "head"
      linkOrder = (
        ("next", None), ("modes", None), ("state", set_next), ("binds", add_default_bind),
        ("sens", set_next), ("hold", set_next), ("modifiers", set_next), ("mapping", set_next))
      assert headEP is state.at("eps", 0)
      for p in linkOrder:
        link_component(p[0], p[1])
      #Check result
      if ep[0] is None:
        if logger.isEnabledFor(logging.DEBUG): logger.debug("Could not make ep out of '{}'".format(cfg))
        return None
      else:
        headEP.set_next(ep[0])
        return headEP
    finally:
      state.pop("eps")
      state.pop_args()
      state.pop("curves")
  epParser.add("ep", parseEP)

  #EP components
  #EP components cfgs are supposed to be specified in ep cfg, they cannot be referenced as args or objs, so using regular SelectParser.
  scParser = SelectParser()
  mainParser.add("sc", scParser)

  def parseMapping(cfg, state):
    mappingCfg = cfg.get("mapping", None)
    if mappingCfg is not None:
      mapping = {}
      for frm,to in mappingCfg.items():
        mapping[fn2htc(frm)] = fn2htc(to)
      mappingEP = MappingEP(mapping)
      return mappingEP
    else:
      return None
  scParser.add("mapping", parseMapping)

  def parseObjects(cfg, state):
    objectsCfg = cfg.get("objects", None)
    if objectsCfg is not None:
      if logger.isEnabledFor(logging.DEBUG): logger.debug("parseObjects(): parsing objects from '{}'".format(str2(objectsCfg)))
      objectsComponent = ObjectsComponent()
      state.at("eps", 0).set("objects", objectsComponent)
      state.make_objs(objectsCfg, lambda k,o : objectsComponent.set(k, o))
      return objectsComponent
    else:
      return None
  scParser.add("objects", parseObjects)

  def parseModifiers(cfg, state):
    modifierDescs = [parse_modifier_desc(m, state) for m in state.resolve(cfg, "modifiers", cls=list)]
    modifierEP = ModifierEP(next=None, modifierDescs=modifierDescs, saveModifiers=True, mode=ModifierEP.APPEND)
    return modifierEP
  scParser.add("modifiers", parseModifiers)

  def parseHold(cfg, state):
    holdDataCfg = get_nested_d(cfg, "hold", None)
    if holdDataCfg is not None:
      holdEP = HoldEP()
      for hd in holdDataCfg:
        keyFullName = state.resolve_d(hd, "key", None, cls=str)
        keyIDev, keyCode = fn2hc(keyFullName) if keyFullName is not None else (None, None)
        modifiers = state.resolve_d(hd, "modifiers", None, cls=list)
        if modifiers is not None:
          modifiers = (parse_modifier_desc(m, state) for m in modifiers)
        num = state.resolve_d(hd, "num", -1, cls=int)
        holdEP.add(keyIDev, keyCode, modifiers, state.resolve(hd, "period", cls=float), state.resolve(hd, "value", cls=int), num)
        state.get("main").add_to_updated(lambda tick,ts : holdEP.update(tick, ts))
      return holdEP
    else:
      return None
  scParser.add("hold", parseHold)

  def parseSens(cfg, state):
    class Setter:
      def __call__(self, v):
        self.scaleEP_.set_sens(self.key_, v)
      def __init__(self, scaleEP, key):
        self.scaleEP_, self.key_ = scaleEP, key
    try:
      name = state.resolve_d(cfg, "name", None, cls=str)
      sens = state.resolve(cfg, "sens")
      scaleEP = ScaleEP2(sens={}, name=name)
      sens2 = {}
      for fnAxis,value in sens.items():
        key = fn2htc(fnAxis)
        setter = Setter(scaleEP, key)
        value = state.deref(value, setter=setter)
        scaleEP.set_sens(key, value)
      return scaleEP
    except RuntimeError as e:
      raise ParseError(cfg, state.get_path(cfg), e)
  scParser.add("sens", parseSens)

  @parseBasesDecorator
  def parseMode(cfg, state):
    class ModeSetter:
      def __call__(self, v):
        self.msmm_.set(v, self.save_, self.current_, self.report_)
      def __init__(self, msmm, save, current, report):
        self.msmm_, self.save_, self.current_, self.report_ = msmm, save, current, report
    name = state.resolve_d(cfg, "name", "", cls=str)
    allowMissingModes = state.resolve_d(cfg, "allowMissingModes", False, cls=bool)
    headEP = state.at("eps", 0)
    def mode_callback(modeEP, old, new):
      logger.info("{}: Setting mode: {}".format(modeEP.get_name(), str2(new)))
    modeEP = ModeEP(name)
    modeEP.add_mode_callback(mode_callback)
    modeValueName = state.resolve_d(cfg, "modeValueName", None, cls=str)
    if modeValueName is not None:
      modeValue = state.get("main").get("valueManager").get_var(modeValueName)
      def cb(modeEP, old, new):
        modeValue.set(new)
      modeEP.add_mode_callback(cb)
    msmm = ModeEPModeManager(modeEP)
    headEP.set_component("msmm", msmm)
    headEP.set_component("modes", modeEP)
    try:
      for modeName,modeCfg in state.resolve(cfg, "modes").items():
        try:
          if logger.isEnabledFor(logging.DEBUG): logger.debug("{}: parsing mode:".format(name, modeName))
          child = state.get("parser")("ep", modeCfg, state)
          modeEP.add(modeName, child)
        except Exception as e:
          if allowMissingModes:
            logger.warning("Error parsing mode '{}' in '{}' ({})".format(modeName, name, e))
            continue
          else:
            raise
      savePolicy = nameToMSMMSavePolicy(state.resolve_d(cfg, "setter.save", "clearAndSave", cls=str))
      current = state.resolve_d(cfg, "setter.current", None)
      report = state.resolve_d(cfg, "setter.report", True, cls=bool)
      modeSetter = ModeSetter(msmm, savePolicy, current, report)
      mode = state.resolve(cfg, "mode", setter=modeSetter)
      if mode is not None:
        if not modeEP.set_mode(mode):
          logger.warning("Cannot set mode: {}".format(mode))
      #Saving initial mode in msmm afer modeEP was initialized
      msmm.save()
      return modeEP
    except:
      headEP.remove_component("msmm")
      headEP.remove_component("modes")
      raise
  scParser.add("modes", parseMode)

  def parseState(cfg, state):
    ep = StateEP()
    stateCfg = state.resolve(cfg, "state")
    if "next" in stateCfg:
      next = state.get("parser")("ep", stateCfg["next"], state)
      ep.set_next(next)
    if "initialState" in stateCfg:
      ep.set_state(stateCfg["initialState"])
    return ep
  scParser.add("state", parseState)

  def parseNext(cfg, state):
    parser = state.get("parser")
    r = parser("ep", state.resolve(cfg, "next"), state)
    if r is None:
      if logger.isEnabledFor(logging.DEBUG): logger.debug("EP parser could not parse '{}', so trying action parser".format(cfg))
      r = parser("action", state.resolve(cfg, "next"), state)
    return r
  scParser.add("next", parseNext)

  #Actions
  def get_ep(cfg, state):
    """Helper. Retrieves ep from eps stack by depth or by object name.
       depth: 0 - current component ep, 1 - its parent, etc
    """
    ep = state.resolve_d(cfg, "ep", None)
    if ep is None:
      if logger.isEnabledFor(logging.DEBUG): logger.debug("Cannot get target ep by '{}'".format(ep))
      ep = state.at("eps", state.resolve_d(cfg, "depth", 0))
    return ep

  def get_component(name, cfg, state):
    """Helper. Retrieves component by depth or by object name.
       depth: 0 - current component ep, 1 - its parent, etc
    """
    ep = get_ep(cfg, state)
    component = ep.get_component(name)
    if component is None:
      raise ParseError(cfg, state.get_path(cfg), "component '{}' not found".format(name))
    return component

  def actionParserKeyOp(cfg, state):
    key = get_nested_d(cfg, "action", None)
    if key is None:
      key = get_nested_d(cfg, "type", None)
    return key
  actionParser = IntrusiveSelectParser(keyOp=actionParserKeyOp, parser=SelectParser())
  mainParser.add("action", actionParser)

  actionParser.add("saveMode", lambda cfg, state : get_component("msmm", cfg, state).make_save())
  actionParser.add("restoreMode", lambda cfg, state : get_component("msmm", cfg, state).make_restore(state.resolve_d(cfg, "report", True, cls=bool)))
  actionParser.add("addMode", lambda cfg, state : get_component("msmm", cfg, state).make_add(state.resolve(cfg, "mode"), state.resolve_d(cfg, "current"), state.resolve_d(cfg, "report", True, cls=bool)))
  actionParser.add("removeMode", lambda cfg, state : get_component("msmm", cfg, state).make_remove(state.resolve(cfg, "mode"), state.resolve_d(cfg, "current"), state.resolve_d(cfg, "report", True, cls=bool)))
  actionParser.add("swapMode", lambda cfg, state : get_component("msmm", cfg, state).make_swap(state.resolve(cfg, "f"), state.resolve(cfg, "t"), state.resolve_d(cfg, "current", None), state.resolve_d(cfg, "report", True, cls=bool)))
  actionParser.add("cycleSwapMode", lambda cfg, state : get_component("msmm", cfg, state).make_cycle_swap(state.resolve(cfg, "modes"), state.resolve_d(cfg, "current"), state.resolve_d(cfg, "report", True, cls=bool)))
  actionParser.add("clearMode", lambda cfg, state : get_component("msmm", cfg, state).make_clear())
  actionParser.add("setMode", lambda cfg, state : get_component("msmm", cfg, state).make_set(state.resolve(cfg, "mode"), nameToMSMMSavePolicy(state.resolve_d(cfg, "savePolicy", "noop")), state.resolve_d(cfg, "current"), state.resolve_d(cfg, "report", True, cls=bool)))
  actionParser.add("cycleMode", lambda cfg, state : get_component("msmm", cfg, state).make_cycle(state.resolve(cfg, "modes"), state.resolve_d(cfg, "step", 1, cls=int), state.resolve_d(cfg, "loop", True, cls=bool), nameToMSMMSavePolicy(state.resolve_d(cfg, "savePolicy", "noop", cls=str)), state.resolve_d(cfg, "report", True, cls=bool)))

  def parseSetState(cfg, state):
    s = state.resolve(cfg, "state", cls=bool)
    return SetState(get_component("state", cfg, state), s)
  actionParser.add("setState", parseSetState)

  def parseToggleState(cfg, state):
    return ToggleState(get_component("state", cfg, state))
  actionParser.add("toggleState", parseToggleState)

  def parseSetSens(cfg, state):
    try:
      htc = fn2htc(state.resolve(cfg, "axis", cls=str))
      value = state.resolve(cfg, "value", cls=float)
      scaleEP = get_component("sens", cfg, state)
      def op(e):
        scaleEP.set_sens(htc, value)
        name = scaleEP.get_name()
        logger.info("{}: {} sens is now {}".format(name, htc2fn(htc.idev, htc.type, htc.code), scaleEP.get_sens(htc)))
      return op
    except Exception as e:
      logger.error(e)
      raise
  actionParser.add("setSens", parseSetSens)

  def parseChangeSens(cfg, state):
    try:
      htc = fn2htc(state.resolve(cfg, "axis", cls=str))
      delta = state.resolve(cfg, "delta", cls=float)
      scaleEP = get_component("sens", cfg, state)
      def op(e):
        sens = scaleEP.get_sens(htc)
        sens += delta
        scaleEP.set_sens(htc, sens)
        name = scaleEP.get_name()
        logger.info("{}: {} sens is now {}".format(name, htc2fn(htc.idev, htc.type, htc.code), scaleEP.get_sens(htc)))
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
    factor = state.resolve_d(cfg, "factor", 1.0, setter=FactorSetter(mc), cls=float)
    mc.set_factor(factor)
    return mc
  actionParser.add("move", parseMove)

  def parseMoveOneOf(cfg, state):
    axesData = state.resolve(cfg, "axes")
    curves = {}
    for fnInputAxis,curveCfg in axesData.items():
      curve = state.get("parser")("curve", curveCfg, state)
      curves[fn2hc(state.deref(fnInputAxis))] = curve
    op = state.resolve(cfg, "op", cls=str)
    if op == "min":
      op = MCSCmpOp(cmp = lambda new,old : new < old)
    elif op == "max":
      op = MCSCmpOp(cmp = lambda new,old : new > old)
    elif op == "thresholds":
      op = MCSThresholdOp(thresholds = {fn2hc(state.deref(fnInputAxis)):state.deref(threshold) for fnInputAxis,threshold in state.resolve(cfg, "thresholds").items()})
    else:
      raise ParseError(cfg, state.get_path(cfg), "unknown op '{}'".format(op))
    mcs = MultiCurveEP(curves, op)
    state.get("main").add_to_updated(lambda tick,ts : mcs.update(tick, ts))
    return mcs
  actionParser.add("moveOneOf", parseMoveOneOf)

  def parseSetAxis(cfg, state):
    axis = state.get_axis_by_full_name(state.resolve(cfg, "axis", cls=str))
    valueSetter = MoveAxisValueSetter()
    value = state.resolve(cfg, "value", setter=valueSetter, cls=float)
    r = MoveAxisTo(axis, value)
    valueSetter.set_move_axis(r)
    return r
  actionParser.add("setAxis", parseSetAxis)

  def parseMoveAxisBy(cfg, state):
    axis = state.get_axis_by_full_name(state.resolve(cfg, "axis", cls=str))
    valueSetter = MoveAxisValueSetter()
    value = state.resolve(cfg, "value", setter=valueSetter, cls=float)
    stopAt = state.resolve_d(cfg, "stopAt", None)
    valueFunc = None
    valueFuncCfg = state.resolve_d(cfg, "valueFunc", None)
    if valueFuncCfg is not None:
      class ValueFunc:
        def __call__(self, value):
          return value*self.func_(self.axis_.get())
        def __init__(self, func, axis):
          self.func_, self.axis_ = func, axis
      valueFuncAxis = state.get_axis_by_full_name(state.resolve(valueFuncCfg, "axis"))
      func = state.get("parser")("func", state.resolve(valueFuncCfg, "func"), state)
      valueFunc = ValueFunc(func, valueFuncAxis)
    r = MoveAxisBy(axis, value, stopAt, valueFunc)
    valueSetter.set_move_axis(r)
    return r
  actionParser.add("moveAxisBy", parseMoveAxisBy)

  def parseMoveAxisByEvent(cfg, state):
    axis = state.get_axis_by_full_name(state.resolve(cfg, "axis", cls=str))
    r = MoveAxisByEvent(axis)
    return r
  actionParser.add("moveAxisByEvent", parseMoveAxisByEvent)

  def parseSetAxes(cfg, state):
    axesAndValues = state.resolve(cfg, "axesAndValues")
    allRelative = state.resolve_d(cfg, "relative", False, cls=bool)
    if logger.isEnabledFor(logging.DEBUG): logger.debug("parseSetAxes(): {}".format(axesAndValues))
    assert is_dict_type(axesAndValues)
    axesAndValues = axesAndValues.items()
    if logger.isEnabledFor(logging.DEBUG): logger.debug("parseSetAxes(): {}".format(axesAndValues))
    av = []
    for axisData in axesAndValues:
      fnAxis, value, relative = axisData[0], axisData[1], allRelative
      if is_list_type(value):
        assert(len(value) >= 2)
        value, relative = value[0], value[1]
      axis = state.deref(fnAxis)
      if is_str_type(fnAxis):
        axis = state.get_axis_by_full_name(axis)
      value = float(state.deref(value))
      relative = state.deref(relative)
      av.append([axis, value, relative])
      if logger.isEnabledFor(logging.DEBUG): logger.debug("parseSetAxes(): {}, {}, {}".format(fnAxis, axis, value))
    if logger.isEnabledFor(logging.DEBUG): logger.debug("parseSetAxes(): {}".format(av))
    r = MoveAxes(av)
    return r
  actionParser.add("setAxes", parseSetAxes)

  def parseSetKeyState_(cfg, state, s):
    fnKey = state.resolve(cfg, "key", cls=str)
    nOutput, cKey = fn2dc(fnKey)
    odev = state.get("main").get("odevs").get(nOutput)
    if odev is None:
      raise ParseError(cfg, state.get_path(cfg), "odev '{}' not found".format(nOutput))
    return SetButtonState(odev, cKey, s)

  def parseSetKeyState(cfg, state):
    s = state.resolve(cfg, "state", cls=int)
    return parseSetKeyState_(cfg, state, s)
  actionParser.add("setKeyState", parseSetKeyState)

  def parsePress(cfg, state):
    return parseSetKeyState_(cfg, state, 1)
  actionParser.add("press", parsePress)

  def parseRelease(cfg, state):
    return parseSetKeyState_(cfg, state, 0)
  actionParser.add("release", parseRelease)

  def parseClick(cfg, state):
    fnKey = state.resolve(cfg, "key", cls=str)
    nODev, cKey = fn2dc(fnKey)
    odev = state.get("main").get("odevs").get(nODev)
    if odev is None:
      raise ParseError(cfg, state.get_path(cfg), "odev '{}' not found".format(nODev))
    numClicks = state.resolve_d(cfg, "numClicks", 1, cls=int)
    delay = state.resolve_d(cfg, "delay", 0.0, cls=float)
    class Clicker:
      def on_event(self, event):
        if self.delay_ == 0.0:
          for i in range(self.numClicks_):
            for s in (1, 0):
              self.odev_.set_button_state(self.key_, s)
        else:
          self.timestamp_ = event.timestamp
          self.s_, self.i_ = 1, self.numClicks_
          self.set_button_state_(self.key_, self.s_)
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
          self.set_button_state_(self.key_, self.s_)
      def __init__(self, odev, key, numClicks, delay):
        self.odev_, self.key_, self.numClicks_, self.delay_ = odev, key, numClicks, delay
        self.timestamp_, self.i_ = None, 0
      def set_button_state_(self, button, s):
        try:
          self.odev_.set_button_state(button, s)
        except RuntimeError as e:
          logger.error(str2(e))
    clicker = Clicker(odev, cKey, numClicks, delay)
    eventOp = lambda e : clicker.on_event(e)
    updateOp = lambda tick,ts : clicker.on_update(tick, ts)
    state.get("main").add_to_updated(updateOp)
    return eventOp
  actionParser.add("click", parseClick)

  def parseResetCurves(cfg, state):
    curvesToReset = []
    allCurves = state.at("curves", 0)
    assert(allCurves is not None)
    if "axes" in cfg:
      for fnAxis in state.resolve(cfg, "axes", cls=list):
        curves = allCurves.get(state.deref(fnAxis), None)
        if curves is None:
          logger.warning("No curves were initialized for '{}' axis ({})".format(fnAxis, str2(cfg, 100)))
        else:
          curvesToReset += curves
    elif "objects" in cfg:
      ep = state.at("eps", 0)
      for objectName in state.resolve(cfg, "objects", cls=list):
        #TODO Use state.deref() here and specify object name as "obj:..." for unification
        curve = state.get_obj(objectName)
        if curve is None:
          raise ParseError(objectName, state.get_path(objectName), "curve '{}' not found".format(str2(objectName)))
        curvesToReset.append(curve)
    else:
      raise ParseError(cfg, state.get_path(cfg), "must specify either 'axes' or 'objects'")
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
    step = state.resolve(cfg, "step", cls=int)
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
    fileName = state.resolve(cfg, "file", cls=str)
    update = state.resolve_d(cfg, "update", False, cls=bool)
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
    soundName = state.resolve(cfg, "sound", cls=str)
    soundFileName = state.get("main").get("sounds").get(soundName, None)
    if soundFileName is None:
      raise ParseError(cfg, state.get_path(cfg), "sound '{}' not found".format(soundName))
    immediate = state.resolve_d(cfg, "immediate", False, cls=bool)
    def op(e):
      soundPlayer.queue(soundFileName, immediate)
    return op
  actionParser.add("playSound", parsePlaySound)

  def parsePrintVar(cfg, state):
    varName = state.resolve(cfg, "varName", cls=str)
    level = name2loglevel(state.resolve_d(cfg, "level", "INFO", cls=str))
    key = state.resolve_d(cfg, "key", None)
    var = state.get("main").get("varManager").get_var(varName)
    def op(e):
      value = var.get()
      if key is not None:
        if not hasattr(value, "__getitem__"):
          raise ParseError(varName, state.get_path(varName), "var '{}' has no subscript getter".format(varName))
        value = value[key]
      logger.log(level, "{} is {}".format(varName, str2(value)))
      return True
    return op
  actionParser.add("printVar", parsePrintVar)

  def parseSetVar(cfg, state):
    varName = state.resolve(cfg, "varName", cls=str)
    level = name2loglevel(state.resolve_d(cfg, "level", "INFO", cls=str))
    value = state.resolve(cfg, "value")
    key = state.resolve_d(cfg, "key", None)
    var = state.get("main").get("varManager").get_var(varName)
    def op(e):
      v = None
      if key is not None:
        v = var.get()
        if not hasattr(v, "__setitem__"):
          raise ParseError(varName, state.get_path(varName), "var '{}' has no subscript setter".format(varName))
        v[key] = value
      else:
        v = value
      var.set(v)
      logger.log(level, "{} is now {}".format(varName, str2(value)))
      return True
    return op
  actionParser.add("setVar", parseSetVar)

  def check_var(var, key):
    value = var.get()
    if not hasattr(value, "__getitem__"):
      raise ParseError(varName, state.get_path(varName), "var '{}' has no subscript getter".format(varName))
    if not hasattr(value, "__setitem__"):
      raise ParseError(varName, state.get_path(varName), "var '{}' has no subscript setter".format(varName))
    if key not in value:
      raise ParseError(varName, state.get_path(varName), "var '{}' has no key '{}'".format(varName, key))

  def parseChangeVar(cfg, state):
    varName = state.resolve(cfg, "varName", cls=str)
    delta = state.resolve(cfg, "delta")
    key = state.resolve_d(cfg, "key", None)
    var = state.get("main").get("varManager").get_var(varName)
    r = None
    if key is not None:
      check_var(var, key)
      def op(e):
        value = var.get()
        v = value[key]
        v += delta
        value[key] = v
        var.set(value)
        logger.info("{} is now {}".format(varName, str2(value)))
        return True
      r = op
    else:
      def op(e):
        value = var.get()
        value += delta
        var.set(value)
        logger.info("{} is now {}".format(varName, str2(value)))
      r = op
    return r
  actionParser.add("changeVar", parseChangeVar)

  def parseCycleVars(cfg, state):
    varName = state.resolve(cfg, "varName", cls=str)
    key = state.resolve_d(cfg, "key", None)
    var = state.get("main").get("varManager").get_var(varName)
    values = [state.deref(value) for value in state.resolve(cfg, "values")]
    step = state.resolve(cfg, "step")
    r = None
    if key is not None:
      check_var(var, key)
      def op(e):
        current = values.index(var.get()[key])
        n = clamp(current + step, 0, len(values) - 1)
        if n == current:
          return
        v = values[n]
        value = var.get()
        value[key] = v
        var.set(value)
        logger.info("Setting var {} to {}".format(varName, value))
      r = op
    else:
      def op(e):
        current = values.index(var.get())
        n = clamp(current + step, 0, len(values) - 1)
        if n == current:
          return
        v = values[n]
        var.set(v)
        logger.info("Setting var {} to {}".format(varName, v))
      r = op
    return r
  actionParser.add("cycleVars", parseCycleVars)

  def parseWriteVars(cfg, state):
    def replace_var_with_value(cfg):
      r = collections.OrderedDict()
      for name,value in cfg.items():
        if is_dict_type(value):
          r[name] = replace_var_with_value(value)
        elif isinstance(value, BaseVar):
          v = value.get()
          if is_dict_type(v):
            v = add_value_tag(v)
          r[name] = v
        else:
          logger.error("Unexpected element {} of type {} in vars".format(name, type(value)))
      return r
    fileName = state.resolve(cfg, "file", cls=str)
    groupName = state.resolve_d(cfg, "group", None, cls=str)
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
    offset = state.resolve(cfg, "offset", cls=float)
    def op(event):
      curve.set_offset(offset)
      return True
    return op
  actionParser.add("setOffset", parseSetOffset)

  def parseSetObjectState(cfg, state):
    logger.warning("'setObjectState' action is deprecated, use 'call'")
    obj = state.resolve(cfg, "object")
    if obj is None:
      raise ParseError(cfg, state.get_path(cfg), "object '{}' not found".format(get_nested(cfg, "object")))
    return SetState(obj, state.resolve(cfg, "state"))
  actionParser.add("setObjectState", parseSetObjectState)

  def parseCall(cfg, state):
    target = state.resolve(cfg, "target")
    methodName = state.resolve(cfg, "method", cls=str)
    try:
      method = getattr(target, methodName)
    except AttributeError as e:
      raise ParseError(methodName, state.get_path(methodName), e)
    args = state.resolve_d(cfg, "args", ())
    kwargs = state.resolve_d(cfg, "kwargs", {})
    def op(event):
      method(*args, **kwargs)
      return True
    return op
  actionParser.add("call", parseCall)

  def parseSetObjectState(cfg, state):
    obj = state.resolve(cfg, "object")
    if obj is None:
      raise ParseError(cfg, state.get_path(cfg), "object '{}' not found".format(get_nested(cfg, "object")))
    return SetState(obj, state.resolve(cfg, "state", cls=bool))
  actionParser.add("setObjectState", parseSetObjectState)

  def parseEmitCustomEvent(cfg, state):
    etype = state.resolve_d(cfg, "etype", None, cls=str)
    etype = codes.EV_CUSTOM if etype is None else name2code(etype)
    code, value = state.resolve_d(cfg, "code", 0, cls=int), state.resolve(cfg, "value")
    ep = get_ep(cfg, state)
    if ep is None:
      raise ParseError(cfg, state.get_path(cfg), "target ep not found")
    def callback(e):
      event = Event(etype, code, value)
      return ep(event)
    return callback
  actionParser.add("emit", parseEmitCustomEvent)

  def parseForwardEvent(cfg, state):
    ep = get_ep(cfg, state)
    if ep is None:
      raise ParseError(cfg, state.get_path(cfg), "target ep not found")
    def callback(e):
      return ep(e)
    return callback
  actionParser.add("forward", parseForwardEvent)

  def parseLog(cfg, state):
    message, level = state.resolve(cfg, "message", cls=str), state.resolve_d(cfg, "level", "INFO", cls=str)
    def callback(e):
      logger.log(name2loglevel(level), message)
      return True
    return callback
  actionParser.add("log", parseLog)

  def parseLogEvent(cfg, state):
    levelName = state.resolve_d(cfg, "level", "INFO", cls=str)
    level = name2loglevel(levelName)
    def callback(e):
      logger.log(level, str2(e))
      return True
    return callback
  actionParser.add("logEvent", parseLogEvent)

  def parseSetValueItem(cfg, state):
    valueObj = state.resolve(cfg, "target")
    item = state.resolve(cfg, "item")
    value = state.resolve(cfg, "value")
    def callback(e):
      valueObj.set_item(item, value)
      return True
    return callback
  actionParser.add("setValueItem", parseSetValueItem)

  def parseSetValue(cfg, state):
    def copy(v):
      tv = type(v)
      if tv in (list,):
        return [copy(vv) for vv in v]
      elif is_dict_type(tv):
        return {k:copy(vv) for k,vv in v.items()}
      else:
        return v
    valueObj = state.resolve(cfg, "target")
    value = state.resolve(cfg, "value")
    def callback(e):
      valueObj.set(copy(value))
      return True
    return callback
  actionParser.add("setValue", parseSetValue)

  def parseShowInfo(cfg, state):
    main = state.get("main")
    def op(e):
      info = main.get("info")
      if info is not None: info.set_state(True)
    return op
  actionParser.add("showInfo", parseShowInfo)

  def parseHideInfo(cfg, state):
    main = state.get("main")
    def op(e):
      info = main.get("info")
      if info is not None: info.set_state(False)
    return op
  actionParser.add("hideInfo", parseHideInfo)

  def parseRefreshInfo(cfg, state):
    main = state.get("main")
    def op(e):
      info = main.get("info")
      if info is not None: info.refresh()
    return op
  actionParser.add("refreshInfo", parseRefreshInfo)

  def parseToggleInfo(cfg, state):
    main = state.get("main")
    def op(e):
      info = main.get("info")
      if info is not None: info.set_state(not info.get_state())
    return op
  actionParser.add("toggleInfo", parseToggleInfo)

  def parseReload(cfg, state):
    main = state.get("main")
    def op(e):
      main.set("state", Main.STATE_NEED_TO_RELOAD)
    return op
  actionParser.add("reload", parseReload)

  def parseExit(cfg, state):
    main = state.get("main")
    def op(e):
      main.set("state", Main.STATE_NEED_TO_EXIT)
    return op

    return op
  actionParser.add("exit", parseExit)

  #Event types
  def etParserKeyOp(cfg, state):
    key = get_nested_d(cfg, "et", None)
    if key is None:
      key = get_nested_d(cfg, "type", None)
    if key is None:
      raise ParseError(cfg, state.get_path(cfg), "must specify either 'et' or 'type'")
    return key
  etParser = IntrusiveSelectParser(keyOp=etParserKeyOp, parser=SelectParser())
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
    idevHash, eventType, key = fn2htc(state.resolve(cfg, "key", cls=str))
    r = [("type", EqPropTest(eventType)), ("code", EqPropTest(key)), ("value", EqPropTest(value))]
    if idevHash is not None:
      r.append(("idev", EqPropTest(idevHash)))
    return r

  @make_et
  def parseAny(cfg, state):
    return []
  etParser.add("any", parseAny)

  @make_et
  def parseIdev(cfg, state):
    idevHash = get_dev_hash(state.resolve(cfg, "idev", cls=str))
    return [("idev", EqPropTest(idevHash))]
  etParser.add("idev", parseIdev)

  @make_et
  def parseKey(cfg, state):
    idevHash, eventType, key = fn2htc(state.resolve(cfg, "key", cls=str))
    r = [("type", EqPropTest(eventType)), ("code", EqPropTest(key))]
    if idevHash is not None:
      r.append(("idev", EqPropTest(idevHash)))
    return r
  etParser.add("key", parseKey)

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
    '''
    numClicks can be either a single number to match it,
      a list of numbers to match one of them,
      or a -1 to match any number of clicks
    '''
    r = parseKey_(cfg, state, 3)
    num = state.resolve(cfg, "numClicks", cls=int)
    numClicksPropTest = None
    if is_list_type(num):
      num = [int(n) for n in num]
      numClicksPropTest = lambda v : v in num
    else:
      if is_str_type(num):
        num = int(num)
      elif isinstance(num, int):
        pass
      else:
        raise ParseError(num, state.get_path(num), "invalid numClicks")
      numClicksPropTest = lambda v : True if num == -1 else v == num
    r.append(("num_clicks", numClicksPropTest))
    return r
  etParser.add("multiclick", parseMultiClick)

  @make_et
  def parseHold(cfg, state):
    r = parseKey_(cfg, state, state.resolve_d(cfg, "value", 4, cls=int))
    holdTime = state.resolve_d(cfg, "heldTime", None, cls=float)
    if holdTime is not None:
      holdTime = float(holdTime)
      r.append(("heldTime", CmpPropTest(holdTime, lambda ev,v : ev >= v)))
    return r
  etParser.add("hold", parseHold)

  @make_et
  def parseMove(cfg, state):
    idevHash, eventType, axis = fn2htc(state.resolve(cfg, "axis", cls=str))
    r = [("type", EqPropTest(eventType)), ("code", EqPropTest(axis))]
    if idevHash is not None:
      r.append(("idev", EqPropTest(idevHash)))
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
    eventName = state.resolve_d(cfg, "event", cls=str)
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
    name = state.resolve_d(cfg, "name", cls=str)
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
    propValue = state.resolve_d(cfg, "etype", None, cls=str)
    propValue = codes.EV_CUSTOM if propValue is None else name2code(propValue)
    r = [("type", EqPropTest(propValue))]
    def eq(ev, pv):
      return ev == pv
    def eq_dict(ev, pv):
      if is_dict_type(ev) and is_dict_type(pv):
        for n,v in pv.items():
          vv = ev.get(n, None)
          if not eq_dict(vv, v):
            return False
        return True
      else:
        return eq(ev, pv)
    for p in  (
      ("idev", get_dev_hash, eq),
      ("code", lambda x : name2code(x) if is_str_type(x) else x, eq),
      ("value", lambda x : x, eq_dict)
    ):
      propName, propOp, cmpOp = p
      propValue = state.resolve_d(cfg, propName, None)
      if propValue is not None:
        propValue = propOp(propValue)
        r.append((propName, CmpPropTest(propValue, cmpOp)))
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
        if is_list_type(cfgs):
          pass
        elif is_dict_type(cfgs):
          cfgs = (cfgs,)
        else:
          raise ParseError(cfg, state.get_path(cfg), "'{}' in must be a dictionary or a list of dictionaries".format(name))
        r, t = [], None
        for c in cfgs:
          try:
            t = parser(c, state)
          except ParseError as e:
            logger.warning("{}".format(e))
            continue
          except RuntimeError as e:
            logger.warning("{} when parsing '{}' '{}' at '{}'".format(e, name, str2(c, 100), v2p_path2str(state.get_path(c))))
            continue
          except Exception as e:
            logger.error("{} when parsing '{}' '{}' at '{}'".format(e, name, str2(c, 200), v2p_path2str(state.get_path(c))))
            state.get("main").print_trace()
            raise ParseError(c, state.get_path(c))
          except:
            logger.warning("Unknown exception while parsing '{}' '{}'".format(name, str2(c, 100)))
            continue
          if t is None:
            logger.warning("Could not parse '{}' '{}')".format(name, str2(c, 100)))
            continue
          r.append(t)
        return r

      def parseActionOrEP(cfg, state):
        mainParser = state.get("parser")
        try:
          return mainParser("action", cfg, state)
        except ParseError as e:
          if logger.isEnabledFor(logging.DEBUG): logger.debug("Action parser could not parse '{}', so trying ep parser".format(str2(cfg, 100)))
          r = mainParser("ep", cfg, state)
          if r is None:
            raise e
          return r

      mainParser = state.get("parser")
      ons = parseGroup("on", lambda cfg,state: mainParser("et", cfg, state), cfg, state)
      if len(ons) == 0:
        logger.warning("No 'on' instances were constructed in '{}' at '{}'".format(str2(cfg, 100), v2p_path2str(state.get_path(cfg))))

      dos = parseGroup("do", parseActionOrEP, cfg, state)
      if len(dos) == 0:
        logger.warning("No 'do' instances were constructed in '{}' at '{}'".format(str2(cfg, 100), v2p_path2str(state.get_path(cfg))))

      return ((on,dos) for on in ons)

    binds = state.resolve_d(cfg, "binds", [])
    if logger.isEnabledFor(logging.DEBUG): logger.debug("binds: {}".format(binds))
    #sorting binds so actions that reset curves are initialized after these curves were actually initialized
    def bindsKey(b):
      def checkDo(o):
        if is_dict_type(o):
          actionName = o.get("action", o.get("type", None))
          if actionName in ("resetCurve", "resetCurves"):
            return 10
        else:
          return 0
      r = 0
      do = b.get("odev", b.get("do", None))
      if type(do) is list:
        for d in do:
          r = max(r, checkDo(d))
      else:
        r = checkDo(do)
      return r
    binds.sort(key=bindsKey)
    bindingEP = BindEP()
    for bind in binds:
      level, name = state.resolve_d(bind, "level", 0, cls=int), state.resolve_d(bind, "name", None, cls=str)
      for on,dos in parseOnsDos(bind, state):
        names = None if name is None else (name for i in range(len(dos)))
        bindingEP.add_several(on, dos, level, names)
    return bindingEP

  scParser.add("binds", parseBinds)

  def idevParserKeyOp(cfg, state):
    key = get_nested_d(cfg, "type", None)
    if key is None:
      raise ParseError(cfg, state.get_path(cfg), "'type' not found")
    return key
  idevParser = IntrusiveSelectParser(keyOp=idevParserKeyOp, parser=SelectParser())
  mainParser.add("idev", idevParser)

  def parseFreePIEHeadTrackerIDEV(cfg, state):
    idevName = state.resolve(cfg, "idev", cls=str)
    idevHash = register_dev(idevName)
    address = state.resolve(cfg, "address")
    i = address.find(":")
    if i == -1:
      #just port
      address = ("", int(address))
    else:
      #ip and port
      address = (address[:i], int(address[i + 1:]))
    from_ = state.resolve_d(cfg, "from", None, cls=str)
    if from_ is not None:
      i = from_.find(":")
      if i == -1:
        from_ = (from_, None)
      else:
        from_ = (from_[:i], int(from_[i + 1:]))
    mode = state.resolve_d(cfg, "mode", "relative", cls=str)
    if mode == "relative":
      mode = FreePIEHeadTrackerIDEV.MODE_REL
    elif mode == "absolute":
      mode = FreePIEHeadTrackerIDEV.MODE_ABS
    else:
      raise ParseError(mode, state.get_path(mode), "invalid mode")
    idev = FreePIEHeadTrackerIDEV(idevHash, address, from_, mode)
    state.get("main").add_to_updated(lambda tick,ts : idev.update(tick, ts))
    return idev
  idevParser.add("freepie", parseFreePIEHeadTrackerIDEV)

  def odevParserKeyOp(cfg, state):
    key = get_nested_d(cfg, "odev", None)
    if key is None:
      key = get_nested_d(cfg, "type", None)
    if key is None:
      raise ParseError(cfg, state.get_path(cfg), "must specify either 'odev' or 'type'")
    return key
  odevParser = IntrusiveSelectParser(keyOp=odevParserKeyOp, parser=SelectParser())
  mainParser.add("odev", odevParser)

  def get_or_make_odev(name, state):
    main = state.get("main")
    odevs = main.get("odevs")
    config = main.get("config")
    j = odevs.get(name, None)
    #TODO Redundant, because all outputs should be already created by init_odevs()?
    if j is None:
      odevs = state.resolve_d(config, "odevs", None)
      if odevs is None:
        raise RuntimeError("Cannot find 'odevs' section in configs")
      odevCfg = state.resolve_d(odevs, name, None)
      if odevCfg is None:
        raise RuntimeError("Cannot find section for odev '{}' in configs".format(name))
      j = state.get("parser")("odev", odevCfg, state)
      odevs[name] = j
    assert name in main.get("odevs")
    return j

  @make_reporting_joystick
  def parseNullJoystickODev(cfg, state):
    values, limits = None, None
    axesDatum = get_nested_d(cfg, "axesDatum")
    if axesDatum is not None:
      values, limits = {}, {}
      for axisName, axisData in axesDatum.items():
        axisId = fn2tc(axisName)
        axisValue = get_nested_d(axisData, "value")
        if axisValue is not None:
          values[axisId] = axisValue
        axisLimits = get_nested_d(axisData, "limits")
        if axisLimits is not None:
          limits[axisId] = axisLimits
    else:
      values = get_nested_d(cfg, "values")
      if values is not None:
        values = {fn2tc(n) : v for n,v in values.items()}
      limits = get_nested_d(cfg, "limits")
      if limits is not None:
        limits = {fn2tc(n) : v for n,v in limits.items()}
    buttons = None
    numButtons = get_nested_d(cfg, "numButtons")
    if numButtons is not None:
      buttons = [codes.BTN_0+i for i in range(numButtons)]
    j = NullJoystick(values=values, limits=limits, buttons=buttons)
    return j
  odevParser.add("null", parseNullJoystickODev)
  odevParser.add("virtual", parseNullJoystickODev)

  def parseExternalODev(cfg, state):
    name = state.resolve(cfg, "name", cls=str)
    return get_or_make_odev(name, state)
  odevParser.add("external", parseExternalODev)

  @make_reporting_joystick
  def parseRateLimitODev(cfg, state):
    rates = {fn2tc(nAxis):value for nAxis,value in state.resolve(cfg, "rates").items()}
    next = state.get("parser")("odev", state.resolve(cfg, "next"), state)
    j = RateLimititngJoystick(next, rates)
    state.get("main").add_to_updated(lambda tick,ts : j.update(tick))
    return j
  odevParser.add("rateLimit", parseRateLimitODev)

  @make_reporting_joystick
  def parseRateSettingODev(cfg, state):
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
    limits = {fn2tc(nAxis):value for nAxis,value in state.resolve_d(cfg, "limits", {}).items()}
    next = state.get("parser")("odev", state.resolve(cfg, "next"), state)
    rateOps = {}
    ratesCfg = state.resolve(cfg, "rates")
    for nAxis,rateOrCfg in ratesCfg.items():
      rateOp = None
      if type(rateOrCfg) in (int, float):
        rateOp = ConstantRateOp(rateOrCfg)
      else:
        for opCfg in rateOrCfg:
          t = state.resolve(opCfg, "type", cls=str)
          if t == "time":
            func = state.get("parser")("func", state.resolve(opCfg, "func"), state)
            rateOp = TimeRateOp(rateOp, func)
          elif t == "axis":
            axis = state.get_axis_by_full_name(state.resolve(opCfg, "axis", cls=str))
            func = state.get("parser")("func", state.resolve(opCfg, "func"), state)
            rateOp = AxisRateOp(rateOp, axis, func)
          else:
            raise ParseError(t, state.get_path(t), "unknown op type")
      tcAxis = fn2tc(nAxis)
      rateOps[tcAxis] = rateOp
    j = RateSettingJoystick(next, rateOps, limits)
    state.get("main").add_to_updated(lambda tick,ts : j.update(tick, ts))
    return j
  odevParser.add("rateSet", parseRateSettingODev)

  @make_reporting_joystick
  def parseRelativeODev(cfg, state):
    next = state.get("parser")("odev", state.resolve(cfg, "next"), state)
    j = RelativeHeadMovementJoystick(
      next=next,
      r=state.resolve_d(cfg, "clampRadius", float("inf"), cls=float),
      stick=state.resolve_d(cfg, "stick", True, cls=bool)
    )
    return j
  odevParser.add("relative", parseRelativeODev)

  @make_reporting_joystick
  def parseCompositeODev(cfg, state):
    parser = state.get("parser")
    children = parse_list(state.resolve(cfg, "children"), state, lambda cfg,state : parser("odev", cfg, state))
    checkChild = state.resolve(cfg, "checkChild", cls=bool)
    union = state.resolve(cfg, "union")
    j = CompositeJoystick(children=children, checkChild=checkChild, union=union)
    return j
  odevParser.add("composite", parseCompositeODev)

  @make_reporting_joystick
  def parseMappingODev(cfg, state):
    j = MappingJoystick()
    for fromAxis,to in state.resolve_d(cfg, "axisMapping", {}).items():
      toJoystick, toAxis = fn2dc(state.resolve(to, "to", cls=str))
      toJoystick = get_or_make_odev(toJoystick, state)
      factor = state.resolve_d(to, "factor", 1.0, cls=float)
      j.add_axis(fn2tc(fromAxis), toJoystick, toAxis, factor)
    for fromButton,to in state.resolve_d(cfg, "buttonMapping", {}).items():
      toJoystick, toButton = fn2dc(state.resolve(to, "to", cls=str))
      toJoystick = get_or_make_odev(toJoystick, state)
      negate = state.resolve_d(to, "negate", False, cls=bool)
      j.add_button(name2code(fromButton), toJoystick, toButton, negate)
    return j
  odevParser.add("mapping", parseMappingODev)

  @make_reporting_joystick
  def parseOpentrackODev(cfg, state):
    j = Opentrack(state.resolve(cfg, "ip", cls=str), state.resolve(cfg, "port", cls=int))
    state.get("main").add_to_updated(lambda tick,ts : j.send())
    return j
  odevParser.add("opentrack", parseOpentrackODev)

  @make_reporting_joystick
  def parseUdpJoystickODev(cfg, state):
    packetMakers = {
      "il2" : make_il2_packet,
      "il2_6dof" : make_il2_6dof_packet,
      "opentrack" : make_opentrack_packet
    }
    j = UdpJoystick(
      state.resolve(cfg, "ip", cls=str),
      state.resolve(cfg, "port", cls=int),
      packetMakers[state.resolve(cfg, "format", cls=str)],
      int(state.resolve_d(cfg, "numPackets", 1, cls=int))
    )
    for nAxis,l in state.resolve_d(cfg, "limits", {}).items():
      j.set_limits(fn2tc(nAxis), l)
    state.get("main").add_to_updated(lambda tick,ts : j.send())
    return j
  odevParser.add("udpJoystick", parseUdpJoystickODev)

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

  #placeholder for more sophisticated var value parsing
  def parseVarValue(cfg, state):
    return cfg
  mainParser.add("varValue", parseVarValue)

  class Value:
    def set(self, value):
      self.value_ = value
      self.emit_event_()

    def get(self):
      return self.value_

    def set_item(self, item, value):
      self.value_[item] = value
      self.emit_event_()

    def get_item(self, item):
      return self.value_[item]

    def __init__(self, value, name, ep):
      self.value_, self.name_, self.ep_ = value, name, ep

    def emit_event_(self):
      event = ValueEvent(self.name_, self.value_)
      self.ep_(event)

  def parseValue(cfg, state):
    ep = get_ep(cfg, state)
    if ep is None:
      raise ParseError(cfg, state.get_path(cfg), "target ep not found")
    value = state.resolve(cfg, "value")
    name = state.resolve(cfg, "name")
    valueObj = Value(value, name, ep)
    return valueObj
  mainParser.add("value", parseValue)

  trackerParserKeyOp=lambda cfg,state : get_nested(cfg, "tracker")
  trackerParser = IntrusiveSelectParser(keyOp=trackerParserKeyOp, parser=SelectParser())
  mainParser.add("tracker", trackerParser)

  def parseConsoleTracker(cfg, state):
    fmt = state.resolve(cfg, "fmt", cls=str)
    level = name2loglevel(state.resolve_d(cfg, "level", "INFO", cls=str))
    def op(values):
      msg = fmt.format(values)
      logger.log(level, msg)
    return GainTracker(op)
  trackerParser.add("console", parseConsoleTracker)

  def parseValueTracker(cfg, state):
    valueName = state.resolve(cfg, "value", cls=str)
    value = state.get("main").get("valueManager").get_var(valueName)
    if value is None:
      raise ParseError(valueName, state.get_path(valueName), "value '{}' is missing".format(valueName))
    def op(values):
      value.set(values)
    return GainTracker(op)
  trackerParser.add("value", parseValueTracker)

  #Widgets
  def widgetParserKeyOp(cfg,state):
    tpe = get_nested_d(cfg, "type", None)
    if tpe is None:
      raise ParseError(cfg, state.get_path(cfg), "must specify 'type'")
    return tpe
  widgetParser = IntrusiveSelectParser(keyOp=widgetParserKeyOp, parser=SelectParser())
  mainParser.add("widget", widgetParser)

  def mapProps(cfg, props, state):
    return map_dict_ex(cfg, props, lambda d,f : state.resolve_d(d, f, None))

  def mapWidgetProps(cfg, state):
    return mapProps(cfg, ("master", "relief", "borderwidth",), state)

  def mapNamedWidgetProps(cfg, state):
    return mapProps(cfg, ("master", "relief", "borderwidth", "name", "nameSide"), state)

  def mapEntriesWidgetProps(cfg, state):
    return mapProps(cfg, ("master", "dim", "layout", "grow"), state)

  def namedWidgetDecorator(func):
    def parse(cfg, state):
      name, namedWidget = state.resolve_d(cfg, "name", None), None
      if name is not None:
        kwargs = mapNamedWidgetProps(cfg, state)
        namedWidget = NamedWidget(**kwargs)
        cfg["master"] = namedWidget
        try:
          widget = func(cfg, state)
          namedWidget.set(widget)
        finally:
          if "master" in cfg:
            del cfg["master"]
        return namedWidget
      else:
        return func(cfg, state)
    return parse

  def labelFrameDecorator(func):
    def parse(cfg, state):
      label, widget = state.resolve_d(cfg, "label", None), None
      if label is not None:
        labelOpts = ("master", ("label", "text"), ("labelrelief", "relief"), ("labelborderwidth", "borderwidth"), "labelanchor")
        kwargs = mapProps(cfg, labelOpts, state)
        widget = tk.LabelFrame(**kwargs)
        cfg["master"] = widget
        try:
          childCfg = exclude_from_dict(cfg, ("label", "labelrelief", "labelborderwidth", "labelanchor"))
          child = func(childCfg, state)
          child.pack(fill="both", expand=True)
        finally:
          if "master" in cfg:
            del cfg["master"]
        return widget
      else:
        return func(cfg, state)
    return parse

  @parseBasesDecorator
  @namedWidgetDecorator
  @labelFrameDecorator
  def parseLabelFrameWidget(cfg, state):
    kwargs = mapProps(cfg, ("master", "text", "relief", "borderwidth", "labelanchor"), state)
    widget = tk.LabelFrame(**kwargs)
    childCfg = state.resolve_d(cfg, "child", {})
    childCfg["master"] = widget
    try:
      child = state.get("main").get("parser")("widget", childCfg, state)
      child.pack(fill="both", expand=True)
    finally:
      if "master" in childCfg:
        del childCfg["master"]
    return widget
  widgetParser.add("labelFrame", parseLabelFrameWidget)

  @parseBasesDecorator
  def parseLabelWidget(cfg, state):
    kwargs = map_dict_ex(
      cfg,
      ("master", "text"),
      lambda d,f : state.resolve(d, f)
    )
    widget = tk.Label(**kwargs)
    return widget
  widgetParser.add("label", parseLabelWidget)

  @parseBasesDecorator
  @namedWidgetDecorator
  @labelFrameDecorator
  def parseAxesWidget(cfg, state):
    kwargs = mapProps(cfg, ("master", "canvasBg", "canvasSize", "layout", "gridColor", "gridWidth"), state)
    odevs = state.get("main").get("odevs")
    kwargs["getODev"] = lambda name : odevs.get(name, None)
    widget = AxesWidget(**kwargs)
    markersCfg = state.resolve_d(cfg, "markers", ())
    for markerCfg in markersCfg:
      try:
        kwargs = filter_dict(
          markerCfg,
          ("vpx", "vpy", "shapeType", "sx", "sy", "size", "color", "width"),
          lambda d,f : state.resolve_d(d, f, None)
        )
        widget.add_marker(**kwargs)
      except RuntimeError as e:
        logger.warning("Cannot create marker for '{}' ({})".format(str2(markerCfg, 100), e))

    state.get("main").add_to_updated(widget.update_self)
    return widget
  widgetParser.add("axes", parseAxesWidget)

  @parseBasesDecorator
  @namedWidgetDecorator
  @labelFrameDecorator
  def parseButtonsWidget(cfg, state):
    kwargs = merge_dicts(mapEntriesWidgetProps(cfg, state), mapProps(cfg, ("idev", "buttons", "style"), state))
    odevs = state.get("main").get("odevs")
    kwargs["getODev"] = lambda name : odevs.get(name, None)
    widget = ButtonsStatesWidget(**kwargs)
    state.get("main").add_to_updated(widget.update_self)
    return widget
  widgetParser.add("buttons", parseButtonsWidget)

  @parseBasesDecorator
  @namedWidgetDecorator
  @labelFrameDecorator
  def parseAxesValuesWidget(cfg, state):
    kwargs = merge_dicts(mapEntriesWidgetProps(cfg, state), mapProps(cfg, ("idev", "axes"), state))
    odevs = state.get("main").get("odevs")
    kwargs["getODev"] = lambda name : odevs.get(name, None)
    widget = AxesValuesWidget(**kwargs)
    state.get("main").add_to_updated(widget.update_self)
    return widget
  widgetParser.add("axesValues", parseAxesValuesWidget)

  @parseBasesDecorator
  @namedWidgetDecorator
  @labelFrameDecorator
  def parseValueWidget(cfg, state):
    kwargs = mapProps(cfg, ("master", "fmt", "state", "height", "width"), state)
    valueName = state.resolve(cfg, "value")
    valueManager = state.get("main").get("valueManager")
    var = valueManager.get_var(valueName)
    kwargs["var"] = var
    widget = ValueWidget(**kwargs)
    state.get("main").add_to_updated(widget.update_self)
    return widget
  widgetParser.add("value", parseValueWidget)

  def bind_box_to_var(box, cfg, state):
    class Manager:
      def update_var(self):
        varValue = self.var_.get()
        varValue = self.write_(varValue, self.boxVar_.get())
        self.busy_ = True
        try:
          self.var_.set(varValue)
        finally:
          self.busy_ = False
      def update_box_var(self):
        if self.busy_ == True:
          return
        self.boxVar_.set(self.read_(self.var_.get()))
      def __init__(self, var, boxVar, read=None, write=None):
        def read_(varValue):
          return varValue
        def write_(varValue, value):
          return value
        self.read_ = read_ if read is None else read
        self.write_ = write_ if write is None else write
        self.var_, self.boxVar_ = var, boxVar
        self.busy_ = False

    varName = state.resolve_d(cfg, "varName", None, cls=str)
    if varName is None:
      return
    manager = None
    varManager = state.get("main").get("varManager")
    var = varManager.get_var(varName)
    if var is None:
      raise ParseError(varName, state.get_path(varName), "cannot get var '{}'".format(varName))
    value = var.get()
    key = state.resolve_d(cfg, "key", None)
    read, write = None, None
    if key is not None:
      keys = key if is_list_type(key) else (key,)
      value = get_nested(value, keys)
      read = lambda varValue : get_nested(varValue, keys)
      write = lambda varValue, value : set_nested(varValue, keys, value)
    boxVar = make_tk_var(value)
    box.configure(textvariable=boxVar)
    manager = Manager(var, boxVar, read, write)
    boxValueSetter = lambda value : manager.update_box_var()
    var.add_callback(boxValueSetter)
    state.get("main").get("callbackManager").add_callback(lambda : var.remove_callback(boxValueSetter))
    return manager

  @parseBasesDecorator
  @namedWidgetDecorator
  @labelFrameDecorator
  def parseSpinboxWidget(cfg, state):
    kwargs = mapProps(cfg, ("master", "values", "from", "to", "increment", "wrap", "state", "width", "format"), state)
    from_ = kwargs.get("from")
    if from_ is not None:
      kwargs["from_"] = from_
      del kwargs["from"]
    widget = tk.Spinbox(**kwargs)
    manager = bind_box_to_var(widget, cfg, state)
    #format is reset if spinbox is configured with value or textvariable, 
    #so need to apply format again
    if "format" in kwargs:
      widget.configure(format=kwargs["format"])
    def command(*args, **kwargs):
      manager.update_var()
    widget.configure(command=command)
    widget.bind("<Return>", command)
    return widget
  widgetParser.add("spinbox", parseSpinboxWidget)

  @parseBasesDecorator
  @namedWidgetDecorator
  @labelFrameDecorator
  def parseComboboxWidget(cfg, state):
    kwargs = mapProps(cfg, ("master", "values", "key", "state", "width", "height", "justify"), state)
    import ttk
    widget = ttk.Combobox(**kwargs)
    manager = bind_box_to_var(widget, cfg, state)
    def command(*args, **kwargs):
      manager.update_var()
    widget.bind("<<ComboboxSelected>>", command)
    return widget
  widgetParser.add("combobox", parseComboboxWidget)

  @parseBasesDecorator
  @labelFrameDecorator
  def parseButtonWidget(cfg, state):
    kwargs = mapProps(cfg, ("master", "text", "state", "width"), state)
    actionCfg = get_nested_d(cfg, "command", None)
    if actionCfg is not None:
      action = state.get("parser")("action", actionCfg, state)
      def command():
        event = Event(0, 0, 0)
        action(event)
      kwargs["command"] = command
    widget = tk.Button(**kwargs)
    return widget
  widgetParser.add("button", parseButtonWidget)

  @parseBasesDecorator
  def parse_curve_editor_props(cfg, state):
    defaultStyle = {
      "grid" : { "precision" : 1 },
      "curve" : {
        "marker" : { "fill" : None, "outline" : "black" },
        "text" : { "precision" : 2 },
        "line" : { "color" : "black", "widht" : 1 }
      }
    }
    main = state.get("main")
    func = state.resolve(cfg, "func")
    if is_str_type(func):
      func = get_nested(main.get("config"), func)
    if is_dict_type(func):
      func = main.get("parser")("func", func, state)
    var = state.resolve(cfg, "var_", asValue=False)
    keys = state.resolve_d(cfg, "keys", None)
    pointsSource = VarPointsSource(var, keys)
    screenSize = state.resolve_d(cfg, "screenSize", [200, 200])
    style = {}
    merge_dicts(style, defaultStyle)
    merge_dicts(style, state.resolve_d(cfg, "style", {}))
    r = { "func" : func, "pointsSource" : pointsSource, "screenSize" : screenSize, "style" : style }
    worldBBox = state.resolve_d(cfg, "worldBBox", None)
    if worldBBox is not None:
      r["worldBBox"] = worldBBox
    else:
      r["worldPos"] = state.resolve_d(cfg, "worldPos", [0.0, 0.0])
      r["worldSize"] = state.resolve_d(cfg, "worldSize", [1.0, 1.0])
    return r

  def preparse(cfg, state):
    if is_dict_type(cfg):
      r = cfg.__class__()
      for k,v in cfg.items():
        r[k] = preparse(state.deref(v, asValue=False), state)
    elif is_list_type(cfg):
      r = cfg.__class__()
      for v in cfg:
        r.append(preparse(state.deref(v), state))
    else:
      r = cfg
    return r

  @parseBasesDecorator
  @labelFrameDecorator
  def parseCurveEditorFrameWidget(cfg, state):
    curveEditorKwargs = parse_curve_editor_props(cfg, state)
    ce = CurveEditorWidget(master=cfg["master"], **curveEditorKwargs)
    return ce
  widgetParser.add("curveEditorFrame", parseCurveEditorFrameWidget)

  @parseBasesDecorator
  def parseCurveEditorWidget(cfg, state):
    curveEditorKwargs = parse_curve_editor_props(cfg, state)
    info = state.get("main").get("info")
    def create_curve_editor():
      tlw = tk.Toplevel()
      info.add_top_level_widget(tlw)
      ce = CurveEditorWidget(master=tlw, **curveEditorKwargs)
      ce.pack(expand=True, fill="both")
    kwargs = mapProps(cfg, ("master", "text"), state)
    kwargs["command"] = create_curve_editor
    widget = tk.Button(**kwargs)
    return widget
  widgetParser.add("curveEditor", parseCurveEditorWidget)

  @parseBasesDecorator
  @namedWidgetDecorator
  @labelFrameDecorator
  def parseFuncEditorWidget(cfg, state):
    kwargs = mapProps(cfg, ("master", ), state)
    funcsCfg = state.resolve(cfg, "funcs")
    funcs = preparse(funcsCfg, state)
    kwargs["funcs"] = funcs
    style = state.resolve_d(cfg, "style", None)
    if style is not None:
      kwargs["style"] = style
    kwargs["main"] = state.get("main")
    widget = FuncEditorWidget(**kwargs)
    return widget
  widgetParser.add("funcEditor", parseFuncEditorWidget)

  @parseBasesDecorator
  @namedWidgetDecorator
  @labelFrameDecorator
  def parseGridWidget(cfg, state):
    parser = state.get("parser")
    kwargs = mapWidgetProps(cfg, state)
    widget = GridWidget(**kwargs)
    for childCfg in state.resolve_d(cfg, "children", {}):
      childCfg["master"] = widget
      try:
        child = parser("widget", childCfg, state)
      finally:
        if "master" in childCfg:
          del childCfg["master"]
      addKwargs = mapProps(childCfg, ("sticky", "row", "column", "rowspan", "columnspan", "padx", "pady", "ipadx", "ipady"), state)
      addKwargs["child"] = child
      widget.add(**addKwargs)
    weightsCfg = state.resolve_d(cfg, "weights", {})
    for row,weight in state.resolve_d(weightsCfg, "rows", {}).items():
      widget.grid_rowconfigure(int(row), weight=weight)
    for column,weight in state.resolve_d(weightsCfg, "columns", {}).items():
      widget.grid_columnconfigure(int(column), weight=weight)
    return widget
  widgetParser.add("grid", parseGridWidget)

  @parseBasesDecorator
  @namedWidgetDecorator
  @labelFrameDecorator
  def parseEntriesWidget(cfg, state):
    parser = state.get("parser")
    kwargs = mapEntriesWidgetProps(cfg, state)
    widget = EntriesWidget(**kwargs)
    for childCfg in state.resolve_d(cfg, "children", {}):
      childCfg["master"] = widget
      try:
        child = parser("widget", childCfg, state)
      finally:
        if "master" in childCfg:
          del childCfg["master"]
      addKwargs = mapProps(childCfg, ("sticky", "padx", "pady", "ipadx", "ipady"), state)
      addKwargs["child"] = child
      widget.add(**addKwargs)
    weightsCfg = state.resolve_d(cfg, "weights", {})
    for row,weight in state.resolve_d(weightsCfg, "rows", {}).items():
      widget.grid_rowconfigure(int(row), weight=weight)
    for column,weight in state.resolve_d(weightsCfg, "columns", {}).items():
      widget.grid_columnconfigure(int(column), weight=weight)
    return widget
  widgetParser.add("entries", parseEntriesWidget)

  @parseBasesDecorator
  def parseInfoWidget(cfg, state):
    try:
      parser = state.get("parser")
      f = state.resolve_d(cfg, "format", 1, cls=int)
      title = state.resolve_d(cfg, "title", "", cls=str)
      info = InfoWidget(master=state.get("main").get("tk"), title=title)
      #setting info in main right after creation so widgets can access info
      state.get("main").set("info", info)
      widgetsCfg = state.resolve_d(cfg, "widgets", ())
      if f == 1:
        for widgetCfg in widgetsCfg:
          widgetCfg["master"] = info.w_
          try:
            widget = parser("widget", widgetCfg, state)
          finally:
            if "master" in widgetCfg:
              del widgetCfg["master"]
          info.add(child=widget)
          #Layout parameters are taken from immediate widget cfg (and not from i.e. preset cfg)
          gridKwargs = map_dict_ex(
            widgetCfg,
            (("r", "row", r), ("c", "column", c), ("rs", "rowspan", 1), ("cs", "columnspan", 1), "sticky"),
            lambda d,f,dfault : state.resolve_d(d, f, dfault)
          )
          widget.grid(**gridKwargs)
      elif f == 2:
        r, c = 0, 0
        for row in widgetsCfg:
          for widgetCfg in row:
            widgetCfg["master"] = info.w_
            try:
              widget = parser("widget", widgetCfg, state)
            finally:
              if "master" in widgetCfg:
                del widgetCfg["master"]
            info.add(child=widget)
            #Layout parameters are taken from immediate widget cfg (and not from i.e. preset cfg)
            gridKwargs = map_dict_ex(
              widgetCfg,
              (("rs", "rowspan", 1), ("cs", "columnspan", 1), "sticky"),
              lambda d,f : state.resolve(d, f)
            )
            gridKwargs["row"], gridKwargs["column"] = r, c
            widget.grid(**gridKwargs)
            info.w_.grid_rowconfigure(r, weight=state.resolve_d(widgetCfg, "rw", 1))
            info.w_.grid_columnconfigure(c, weight=state.resolve_d(widgetCfg, "cw", 1))
            c += gridKwargs.get("columnspan", 1)
          c = 0
          r += 1
      else:
        raise ParseError(cfg, state.get_path(cfg), "unknown format: {}".format(f))
      return info
    except:
      state.get("main").set("info", None)
      raise
  widgetParser.add("info", parseInfoWidget)

  @parseBasesDecorator
  def parsePresetWidget(cfg, state):
    config = state.get("main").get("config")
    presetName = state.resolve_d(cfg, "name", None, cls=str)
    if presetName is None:
      raise ParseError(cfg, state.get_path(cfg), "'name' is missing")
    presets = config.get("presets", {})
    presetCfg = get_nested_d(presets, presetName, None)
    if presetCfg is None:
      raise ParseError(cfg, state.get_path(cfg), "preset '{}' does not exist; available presets are: '{}'".format(presetName, presets.keys()))
    state.push_args(cfg)
    master = cfg.get("master", None)
    if master is not None:
      presetCfg["master"] = master
    try:
      return state.get("parser")("widget", presetCfg, state)
    finally:
      state.pop_args()
      if master in presetCfg:
        del presetCfg["master"]
  widgetParser.add("preset", parsePresetWidget)

  return mainParser


class SoundPlayer:
  def queue(self, soundFileName, immediate=False):
    if immediate == True:
      playsound.playsound(soundFileName, False)
      return
    else:
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

  def remove_callback(self, callback):
    pass


class Var(BaseVar):
  def get(self, keys=None):
    return self.value_ if keys is None else get_nested_d(self.value_, keys, None)

  def set(self, value, keys=None):
    if self.validate_ is not None:
      if keys is not None:
        self.validate_(value, keys)
      else:
        self.validate_(value)
    if keys is not None:
      self.value_ = set_nested(self.value_, keys, value)
    else:
      self.value_ = value
    value = self.value_
    if self.mapping_ is not None:
      value = self.mapping_(value)
    if keys is not None:
      for cb in self.callbacks_:
        cb(value, keys)
    else:
      for cb in self.callbacks_:
        cb(value)

  def add_callback(self, callback):
    self.callbacks_.append(callback)

  def remove_callback(self, callback):
    try:
      self.callbacks_.remove(callback)
    except ValueError:
      logger.warning("Callback was not registered.")

  def set_mapping(self, mapping):
    self.mapping_ = mapping

  def __init__(self, value, validate=None, mapping=None):
    self.value_, self.validate_, self.mapping_ = value, validate, mapping
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
        raise NotFoundError("var", varName)
    return var

  def get_var_d(self, varName, dfault=None):
    return get_nested_d(self.vars_, varName, dfault)

  def get_vars(self):
    return self.vars_

  def add_var(self, varName, var):
    set_nested(self.vars_, varName, var)

  def __init__(self, make_var = None):
    self.vars_ = collections.OrderedDict()
    self.make_var_ = make_var


class CallbackManager:
  def add_callback(self, callback):
    self.callbacks_[-1].append(callback)

  def push_callbacks(self):
    self.callbacks_.append([])

  def pop_callbacks(self):
    cs = self.callbacks_.pop()
    for callback in cs:
      callback()

  def __init__(self):
    self.callbacks_ = [[]]


class Main:
  STATE_NOT_INITIALIZED = 0
  STATE_INITIALIZING = 1
  STATE_FALLBACK = 2
  STATE_INITIALIZED = 3
  STATE_RUNNING = 4
  STATE_NEED_TO_RELOAD = 5
  STATE_RELOADING = 6
  STATE_NEED_TO_EXIT = 7
  STATE_EXITING = 8

  def print_help(self):
    print "Usage: " + sys.argv[0] + " args"
    print "args are:\n\
    -h | --help : this message\n\
    -d fileName | --devices=fileName : print input devices info to file fileName (- for stdout)\n\
    -j fileName | --devices_json=fileName : print input devices JSON config to file fileName (- for stdout)\n\
    -i | --log_input : log input from input devices to console (Ctrl-C to exit)\n\
    -p presetName | --preset=presetName : use preset presetName\n\
    -c configFileName | --config=configFileName : use config file configFileName\n\
    -v logLevel | --log_level=logLevel : set log level to logLevel\n"

  def add_logging_handler(self, logger, handler, level=logging.NOTSET, fmt="%(levelname)s:%(asctime)s:%(message)s", datefmt="%H:%M:%S"):
    if handler is None:
      return
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(fmt=fmt, datefmt=datefmt))
    logger.addHandler(handler)

  def preinit_log(self):
    root = logging.getLogger()
    level = logging.INFO
    root.setLevel(level)
    handler = logging.StreamHandler(sys.stdout)
    fmt = "%(levelname)s:%(asctime)s:%(message)s"
    datefmt = "%H:%M:%S"
    self.add_logging_handler(root, handler, level, fmt, datefmt)

  def init_log(self, state):
    config = self.get("config")
    logLevelName = state.resolve_d(config, "logLevel", "NOTSET", cls=str).upper()
    logLevel = name2loglevel(logLevelName)
    set_loggers_level(logLevel)
    print("Setting default log level to {}".format(logLevelName))
    def parse_logger(logger, config, state):
      #logger levels are set in set_logger_levels()
      childrenCfg = state.resolve_d(config, "loggers", {})
      for childName,childCfg in childrenCfg.items():
        child = logger.getChild(childName)
        parse_logger(child, childCfg, state)
      for handlerCfg in state.resolve_d(config, "handlers", ()):
        t = state.resolve(handlerCfg, "type", cls=str)
        name = state.resolve(handlerCfg, "name", cls=str)
        stream = None
        if t == "stream":
          streams = { "stdout" : sys.stdout, "stderr" : sys.stderr }
          stream = streams.get(name, None)
        elif t == "file":
          stream = open(name, "w")
        else:
          raise ParseError(t, state.get_path(t), "bad handler type: '{}'".format(t))
        if stream is None:
          raise ParseError(cfg, state.get_path(cfg), "cannot create log handler '{}' of type '{}'".format(name, t))
        fmt = state.resolve_d(handlerCfg, "fmt", "%(levelname)s:%(asctime)s:%(message)s", cls=str)
        datefmt = state.resolve_d(handlerCfg, "datefmt", "%T", cls=str)
        levelName = state.resolve_d(handlerCfg, "level", "NOTSET", cls=str).upper()
        level = name2loglevel(levelName)
        handler = logging.StreamHandler(stream)
        self.add_logging_handler(logger, handler, level, fmt, datefmt)
    parse_logger(logging.getLogger(), state.resolve_d(config, "loggers", {}), state)

  def init_config2(self):
    if self.get("config") is not None and self.get("state") != self.STATE_RELOADING:
      return
    config = self.options_
    configNames = self.options_.get("configNames", None)
    if configNames is not None:
      externalConfig = init_config(configNames)
      merge_dicts(externalConfig, config)
      config = externalConfig
    else:
      logger.info("No configs specified, exiting")
      raise ExitException
    overrides = self.get("overrides")
    for k,v in overrides:
      set_nested_strict(config, k, v)
    self.set("config", config)
    self.set("v2p", v2p_make(config))
    logger.info("Configs loaded successfully")
    self.set("numTraceLines", config.get("numTraceLines", 0))

  def init_odevs(self, state):
    nameParser = lambda key,state : key
    parser = self.get("parser")
    odevParser = lambda cfg,state : parser("odev", cfg, state)
    def exception_handler(key, value, e):
      logger.error("Cannot create output '{}' ({})".format(key, e))
      return True
    orderOp = lambda i : state.resolve_d(i[1], "seq", 100000, cls=int)
    cfg = state.resolve(self.get("config"), "odevs")
    state = ParserState(self)
    parse_dict_live_ordered(self.get("odevs"), cfg, state=state, kp=nameParser, vp=odevParser, op=orderOp, update=False, exceptionHandler=exception_handler)

  def init_sounds(self, state):
    soundsCfg = state.resolve_d(self.get("config"), "sounds", {})
    sounds = self.get("sounds")
    for soundName,soundFileName in soundsCfg.items():
      sounds[soundName] = state.deref(soundFileName)

  def init_vars(self, state, update=False):
    parser = state.get("main").get("parser")
    config = self.get("config")
    varsCfg = config.get("vars", {})
    varsFileName = state.resolve_d(config, "varsConfig", None)
    if varsFileName is not None:
      with open(varsFileName, "r") as f:
        varsFileCfg = json.load(f, object_pairs_hook = lambda l : collections.OrderedDict(l))
        varsFileCfg = varsFileCfg.get("vars", {})
        should_overwrite = lambda key,destinationValue,sourceValue : is_dict_type(sourceValue) and has_value_tag(sourceValue)
        merge_dicts(varsCfg, varsFileCfg, should_overwrite)
    varMappingsCfg = config.get("varMappings", {})
    varManager = self.get("varManager")
    def get_mapping_cfg(tokens, varMappingsCfg):
      if len(tokens) == 0:
        return None
      r = varMappingsCfg
      for token in tokens:
        r = r.get(token, None)
        if r is None:
          break
      return r
    def add_nested_vars(cfg, tokens):
      sep = "."
      for name,cfg2 in cfg.items():
        tokens.append(name)
        isDict = is_dict_type(cfg2)
        isValueDict = True if isDict and has_value_tag(cfg2) else False
        if isValueDict:
          cfg2 = remove_value_tag(cfg2)
        if not isDict or isValueDict:
          varValue = parser("varValue", cfg2, state)
          path = sep.join(tokens)
          if update == True:
            var = varManager.get_var_d(path, None)
            if var is None:
              raise ParseError(cfg2, state.get_path(cfg2), "var '{}' not found".format(path))
            var.set(varValue)
          else:
            var = Var(varValue)
            varManager.add_var(path, var)
          mappingCfg = get_mapping_cfg(tokens, varMappingsCfg)
          if mappingCfg is not None:
            mapping = state.make_mapping(mappingCfg)
            var.set_mapping(mapping)
        else:
          add_nested_vars(cfg2, tokens)
        tokens.pop()
    tokens = []
    add_nested_vars(varsCfg, tokens)

  def init_poses(self, state):
    poseManager = self.get("poseManager")
    poseParser = lambda cfg,state: self.get("parser")("pose", cfg, state)
    posesCfg = self.get("config").get("poses")
    if posesCfg is not None:
      for poseName,poseCfg in posesCfg.items():
        try:
          pose = poseParser(poseCfg, state)
          poseManager.set_pose(poseName, pose)
        except Exception as e:
          logger.error("Cannot create pose '{}' ({})".format(poseName, e))

  def set_logger_levels(self, state):
    def set_logger_level(logger, config, state):
      levelName = state.resolve_d(config, "level", None, cls=str)
      if levelName is not None:
        level = name2loglevel(levelName.upper())
        logger.setLevel(level)
      childrenCfg = state.resolve_d(config, "loggers", {})
      for childName,childCfg in childrenCfg.items():
        child = logger.getChild(childName)
        set_logger_level(child, childCfg, state)
    root = logging.getLogger()
    config = get_nested_d(self.get("config"), "loggers", {})
    set_logger_level(root, config, state)

  def init_source(self, state):
    parser = self.get("parser")
    idevsCfg = self.get("config").get("idevs", {})
    idevs = {}
    for idevName,idevCfg in idevsCfg.items():
      try:
        #Skipping comments
        if idevName[0] == "#":
          continue
        if is_str_type(idevCfg):
          #Implementation-dependend runner must register 'default' parser in 'idevs' parser
          idevCfg = { "type" : "default", "identifier" : idevCfg }
        idevCfg["idev"] = idevName
        idevs[idevName] = parser("idev", idevCfg, state)
      except RuntimeError as e:
        logger.error(e)
    source = EventSource(idevs, None)
    self.set("source", source)

  def init_main_ep(self, state):
    ep = init_main_ep(state)
    self.set("mainEP", ep)
    self.get("source").set_ep(ep)

  def remove_axes_listeners(self):
    #axes are created on demand by get_axis_by_full_name
    for oName, oAxes in self.get("axes").items():
      for tcAxis, axis in oAxes.items():
        axis.remove_all_listeners()

  def init_worker_ep(self, state):
    #remove listeners from axes in case of reinitialization
    self.remove_axes_listeners()
    ep = init_preset_config(state)
    self.get("mainEP").set_next(ep)
    state.push("eps", ep)

  def init_info(self, state):
    info = self.get("info")
    if info is not None:
      info.destroy()
      self.set("info", None)
    cfg = state.resolve_d(self.get("config"), "info", { "type" : "info" })
    info = state.get("parser")("widget", cfg, state)
    self.add_to_updated(lambda tick,ts : info.update())
    self.set("info", info)

  def init_loop(self, state):
    step = state.resolve_d(self.get("config"), "updatePeriod", 0.01, cls=float)
    if step is None:
      refreshRate = state.resolve_d(self.get("config"), "refreshRate", 100.0, cls=float)
      step = 1.0 / refreshRate
    source = self.get("source")
    assert(source is not None)
    def run_source(tick, ts):
      source.run_once()
    updated = self.get("updated")
    def run_updated(tick, ts):
      for u in updated:
        u(tick, ts)
    def check_state(tick, ts):
      state = self.get("state")
      if state == self.STATE_NEED_TO_RELOAD:
        self.set("state", self.STATE_RELOADING)
        raise ReloadException()
      elif state == self.STATE_NEED_TO_EXIT:
        self.set("state", self.STATE_EXITING)
        raise ExitException()
    callbacks = [run_source, run_updated, check_state]
    loop = Loop(callbacks, step)
    if self.loop_ is not None:
      del self.loop_
    self.loop_ = loop

  def print_trace(self):
    numTraceLines = self.props_["numTraceLines"]
    if numTraceLines > 0:
      logger.error("===Traceback begin===")
      for l in traceback.format_exc().splitlines()[-numTraceLines:]:
        logger.error(l)
      logger.error("===Traceback end===")

  def reinit_or_fallback(self):
    state = ParserState(self)
    state.push("eps", self.get("mainEP"))
    try:
      self.init_config2()
      self.init_vars(state, update=True)
      self.init_poses(state)
      self.set_logger_levels(state)
      self.init_worker_ep(state)
      self.init_info(state)
      self.set("state", self.STATE_INITIALIZED)
    except Exception as e:
      logger.error("Could not create or recreate loop; reason: '{}'".format(e))
      self.print_trace()
      logger.error("Falling back to initial state.")
      self.get("mainEP").set_next(None)
      self.set("state", self.STATE_FALLBACK)
    self.init_loop(state)

  def restore_axes_values(self):
    allAxes = self.get("axes")
    for odevName,odevAxes in allAxes.items():
      for tcAxis,axis in odevAxes.items():
        #moving each axis to its value,
        #to make listeners subscribed to an axis (i.e. curves)
        #update their states according to axis value
        axis.move(axis.get(), relative=False)

  def reinit_and_run(self):
    callbackManager = self.get("callbackManager")
    callbackManager.push_callbacks()
    try:
      if logger.isEnabledFor(logging.DEBUG): logger.debug("len(updated) before reinit_or_fallback: {}".format(len(self.get("updated"))))
      self.reinit_or_fallback()
      self.restore_axes_values()
      if logger.isEnabledFor(logging.DEBUG): logger.debug("len(updated) after reinit_or_fallback: {}".format(len(self.get("updated"))))
      assert(self.loop_ is not None)
      self.set("state", self.STATE_RUNNING)
      self.loop_.run()
    finally:
      callbackManager.pop_callbacks()

  def ask_for_config(self):
    if self.options_.get("configNames") is not None:
      return
    print "Asking for config file..."
    lastPath = ""
    try:
      with open(".lastrun.cfg", "r") as f:
        j = json.load(f)
        lastPath = j["config"]
    except IOError:
      if logger.isEnabledFor(logging.DEBUG): logger.debug(".lastrun.cfg does not exist")
    import os
    initialdir, initialfile = os.path.split(lastPath)
    import tkFileDialog as tkf
    fname = tkf.askopenfilename(master=self.get("tk"), initialdir=initialdir, initialfile=initialfile)
    if fname != tuple():
      print "Selected config file '{}'".format(fname)
      self.options_["configNames"] = [fname]
      with open(".lastrun.cfg", "w") as f:
        json.dump({ "config" : fname }, f)

  def init_gui(self):
    if sys.__stdin__ is not None and sys.__stdin__.isatty() == True:
      return
    gui = tk.Toplevel(master=self.get("tk"))
    def on_close(*args, **kwargs):
      self.set("state", self.STATE_NEED_TO_EXIT)
    gui.protocol("WM_DELETE_WINDOW", on_close)
    self.add_to_updated(lambda tick,ts : gui.update())
    textWidget = tk.Text(master=gui, wrap="word")
    textWidget.bind("<Key>", lambda e : "break")
    textWidget.pack(side="left", fill="both", expand=True)
    vScrollbarWidget = tk.Scrollbar(master=gui, command=textWidget.yview)
    textWidget.configure(yscrollcommand=vScrollbarWidget.set)
    vScrollbarWidget.pack(side="right", fill="y", expand=False)
    class Redirector:
      def write(self, string):
        self.tw_.insert("end", string)
        self.tw_.see("end")
        #Updating gui after each text input is a workaround for printing log messages during init
        #TODO Need to run gui in separate thread
        self.gui_.update()
      def __init__(self, tw, gui):
        self.tw_, self.gui_ = tw, gui
    sys.stdout = Redirector(textWidget, gui)

  def preinit(self):
    self.init_gui()
    self.preinit_log()
    if (len(sys.argv)) == 1:
      print "Launch as '{} -h|--help' for help on command-line parameters".format(sys.argv[0])

    self.set("state", self.STATE_INITIALIZING)
    MODE_NORMAL = 0
    MODE_LOG_INPUT = 1
    mode = MODE_NORMAL
    opts, args = getopt.getopt(sys.argv[1:], "hd:j:ip:v:c:o:", ["help", "devices=", "devices_json=", "log_input", "preset=", "log_level=", "config=", "override="])
    for o, a in opts:
      if o in ("-h", "--help"):
        self.print_help()
        self.set("state", self.STATE_EXITING)
        raise ExitException
      elif o in ("-d", "--devices"):
        self.output_devices_("text", a)
        self.set("state", self.STATE_EXITING)
        raise ExitException
      elif o in ("-j", "--devices_json"):
        self.output_devices_("json", a)
        self.set("state", self.STATE_EXITING)
        raise ExitException
      elif o in ("-i", "--log_input"):
        mode = MODE_LOG_INPUT
      if o in ("-p", "--preset"):
        self.options_["preset"] = a
      elif o in ("-v", "--log_level"):
        self.options_["log_level"] = a
      elif o in ("-c", "--config"):
        cns = self.options_.setdefault("configNames", [])
        cns.append(a)
      elif o in ("-o", "--override"):
        overrides = self.get("overrides")
        keySep, keyValueSep = ".", "="
        k,v = a.split(keyValueSep)
        k = k.split(keySep)
        overrides.append((k, v))

    self.ask_for_config()
    self.init_config2()
    state = ParserState(self)
    self.init_log(state)
    self.init_source(state)
    if mode == MODE_LOG_INPUT:
      #Should raise ExitException on completion
      self.log_input_()
    self.init_odevs(state)
    self.init_vars(state)
    self.init_sounds(state)
    self.init_main_ep(state)

  def run(self):
    callbackManager = self.get("callbackManager")
    callbackManager.push_callbacks()
    try:
      if logger.isEnabledFor(logging.DEBUG): logger.debug("len(updated) before preinit: {}".format(len(self.get("updated"))))
      self.preinit()
      if logger.isEnabledFor(logging.DEBUG): logger.debug("len(updated) after preinit: {}".format(len(self.get("updated"))))
      while (True):
        try:
          if logger.isEnabledFor(logging.DEBUG): logger.debug("len(updated) before reinit_and_run: {}".format(len(self.get("updated"))))
          r = self.reinit_and_run()
        except ReloadException:
          if logger.isEnabledFor(logging.DEBUG): logger.debug("len(updated) after reinit_and_run: {}".format(len(self.get("updated"))))
          logger.info("Reloading")

    except KeyboardInterrupt:
      logger.info("Exiting normally")
      return 0
    except ExitException:
      logger.info("Exiting normally")
      return 0
    except ConfigReadError as e:
      logger.error("Error reading config: {}".format(e))
      return 1
    except Exception as e:
      logger.error("Unexpected exception: {}".format(e))
      raise
    finally:
      source = self.get("source")
      if source is not None:
        source.swallow(None, False)
      self.get("soundPlayer").quit()
      callbackManager.pop_callbacks()


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
    odevName, tAxis, cAxis = fn2dtc(fnAxis)
    tcAxis = TypeCode(tAxis, cAxis)
    odevAxes = allAxes.setdefault(odevName, {})
    axis = None
    if tcAxis not in odevAxes:
      #raise RuntimeError("Axis was not initialized for '{}'".format(fnAxis))
      odevs = self.get("odevs")
      odev = odevs.get(odevName)
      if odev is None:
        raise RuntimeError("Cannot find axis '{}' because odev '{}' is missing".format(fnAxis, odevName))
      if tcAxis not in odev.get_supported_axes():
        raise RuntimeError("Axis '{}' is not supported by '{}'".format(tc2ns(*tcAxis)[0], odevName))
      axis = None
      if tAxis == codes.EV_KEY:
        cButton = cAxis
        axis = ReportingAxis(JoystickButtonAxis(odev, cButton))
      else:
        isReportingJoystick = type(odev) is ReportingJoystick
        axis = odev.make_axis(tcAxis) if isReportingJoystick else ReportingAxis(JoystickAxis(odev, tcAxis))
      odevAxes[tcAxis] = axis
      self.get("axesToNames")[axis] = fnAxis
    else:
      axis = odevAxes[tcAxis]
    return axis

  def get_full_name_by_axis(self, axis):
    return self.get("axesToNames").get(axis, None)

  def add_to_updated(self, callback):
    if logger.isEnabledFor(logging.DEBUG): logger.debug("Adding to updated: {}".format(callback))
    updated = self.get("updated")
    updated.append(callback)
    self.get("callbackManager").add_callback(lambda : self.remove_from_updated(callback))

  def remove_from_updated(self, callback):
    if logger.isEnabledFor(logging.DEBUG): logger.debug("Removing from updated: {}".format(callback))
    updated = self.get("updated")
    try:
      updated.remove(callback)
    except ValueError:
      pass

  def get_path(self, v):
    return v2p_path(v, self.get("v2p"))

  def __init__(self, parser=make_parser(), get_idevs_info=lambda a:None):
    self.loop_ = None
    self.get_idevs_info_ = get_idevs_info
    self.options_ = {}
    self.props_ = {}
    self.props_["state"] = self.STATE_NOT_INITIALIZED
    self.props_["source"] = None
    self.props_["mainEP"] = None
    self.props_["config"] = None
    self.props_["overrides"] = []
    self.props_["v2p"] = {}
    self.props_["parser"] = parser
    self.props_["info"] = None
    self.props_["updated"] = []
    self.props_["axes"] = {}
    self.props_["axesToNames"] = {}
    self.props_["odevs"] = {}
    self.props_["sounds"] = {}
    self.props_["numTraceLines"] = 0
    self.props_["soundPlayer"] = SoundPlayer()
    self.props_["varManager"] = VarManager()
    self.props_["callbackManager"] = CallbackManager()
    self.props_["valueManager"] = VarManager(make_var = lambda : Var(None))
    poseManager = AxisPoseManager()
    self.props_["poseManager"] = poseManager
    self.props_["poseTracker"] = PoseTracker(poseManager)
    tk_ = tk.Tk()
    tk_.withdraw()
    self.props_["tk"] = tk_

  def output_devices_(self, mode, fname):
    r = self.get_idevs_info_()
    if mode == "text":
      if fname == "-":
        for l in r:
          for k,v in l.items():
            print "{} : {};".format(k, v),
          print "\n"
      else:
        with open(fname, "w") as f:
          for l in r:
            for k,v in l.items():
              f.write("{} : {};".format(k, v))
            f.write("\n")
    elif mode == "json":
      d, i = collections.OrderedDict(), 0
      for l in r:
        s = "idev{}".format(i)
        #Adding comment containting device info
        d["#{}".format(s)] = str(l)
        d[s] = "hash:{}".format(l["hash"])
        i += 1
      d = { "idevs" : d }
      if fname == "-":
        json.dump(d, sys.stdout, indent=2)
        sys.stdout.write("\n")
      else:
        with open(fname, "w") as f:
          json.dump(d, f, indent=2)
    else:
      raise RuntimeError("Bad mode: {}".format(mode))

  def log_input_(self):
    source = self.get("source")
    def ep(event):
      if isinstance(event, InputEvent):
        fmt = "{fn} {value}"
        msg = fmt.format(fn=htc2fn(event.idev, event.type, event.code), value=event.value)
        logger.info(msg)
    source.set_ep(ep)
    updated = self.get("updated")
    ts = time.time()
    try:
      logger.info("Printing input events, press Ctrl-C to exit")
      while True:
        source.run_once()
        nts = time.time()
        tick = nts - ts
        for u in updated:
          u(tick, nts)
        ts = nts
        time.sleep(0.1)
    except KeyboardInterrupt:
      raise ExitException()
