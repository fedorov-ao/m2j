#!/usr/bin/python

import unittest

def m_fd(k, xs, ps):
  r, d = 0.0, 0.0
  lxs, lps = len(xs), len(ps)
  if lxs != lps:
    raise ValueError("lengths of xs and ps are not equal (got {} and {})".format(lxs, lps))
  if not (k >= 0 and k < lxs):
    raise ValueError("k is out of range (must be >= 0 and < {})".format(lxs))
  if k < lxs - 1:
    dx = xs[k + 1] - xs[k]
    if dx == 0.0:
      raise ValueError("xs for indices {} and {} are equal (must not be)".format(k, k + 1))
    r += (ps[k + 1] - ps[k]) / dx
    d += 1
  if k > 0:
    dx = xs[k] - xs[k - 1]
    if dx == 0.0:
      raise ValueError("xs for indices {} and {} are equal (must not be)".format(k - 1, k))
    r += (ps[k] - ps[k - 1]) / dx
    d += 1
  assert d != 0.0
  r /= d
  return r

def m_c(k, xs, ps, c):
  lxs = len(xs)
  k = 1 if k < 1 else lxs - 2 if k > lxs - 2 else k
  dx = xs[k + 1] - xs[k - 1]
  if dx == 0.0:
    raise ValueError("xs for indices {} and {} are equal (must not be)".format(k - 1, k + 1))
  return (1.0 - c) * (ps[k + 1] - ps[k - 1]) / dx

def hermite_m(x, xs, ps, ms):
  """https://en.wikipedia.org/wiki/Cubic_Hermite_spline"""
  k = 0
  lxs = len(xs)
  if len(ps) != lxs:
    raise ValueError("lengths of xs and ps must be equal")
  if len(ms) != lxs:
    raise ValueError("lengths of xs and ms must be equal")
  isSortedAsc = all(xs[i] < xs[i + 1] for i in xrange(lxs - 1))
  isSortedDesc = all(xs[i] > xs[i + 1] for i in xrange(lxs - 1))
  if not (isSortedAsc or isSortedDesc):
    raise ValueError("xs must be sorted and distinct")
  if isSortedAsc and (x < xs[0] or x > xs[-1]) or isSortedDesc and (x > xs[0] or x < xs[-1]):
    raise ValueError("x out of range", x)
  for i in range(1, lxs):
    if xs[i] >= x if isSortedAsc else xs[i] <= x:
      k = i - 1
      break
  dx = xs[k + 1] - xs[k]
  t = (x - xs[k]) / dx
  assert t >= 0.0 and t <= 1.0, t
  t2 = t * t
  t3 = t2 * t
  h00 = 2.0 * t3 - 3.0 * t2 + 1
  h10 = t3 - 2.0 * t2 + t
  h01 = -2.0 * t3 + 3.0 * t2
  h11 = t3 - t2
  mk, mk1 = ms[k], ms[k + 1]
  p = h00 * ps[k] + h10 * dx * mk + h01 * ps[k + 1] + h11 * dx * mk1
  #print "x:{}, k:{}, t:{}, h00:{}, h01:{}, h10:{}, h11:{}, m(k):{}, m(k + 1):{}, p:{}".format(x, k, t, h00, h01, h10, h11, mk, mk1, p)
  return p

def hermite(x, xs, ps, c=None):
  ms = None
  lxs = len(xs)
  if c is None:
    ms = [m_fd(k, xs, ps) for k in range(lxs)]
  else:
    ms = [m_c(k, xs, ps, c) for k in range(lxs)]
  return hermite_m(x, xs, ps, ms)

class Hermite:
  def __call__(self, x):
    return hermite_m(x, self.xs_, self.ps_, self.ms_)

  def __init__(self, xs, ps, ms):
    self.xs_, self.ps_, self.ms_ = xs, ps, ms


class HermiteErrorsTest(unittest.TestCase):
  def test_neq_length(self):
    xs = [0.0, 1.0]
    ps = [0.0]
    with self.assertRaises(ValueError):
      hermite(0.0, xs, ps)

  def test_unsorted(self):
    xs = [1.0, 0.0, 2.0]
    ps = [0.0, 1.0, 2.0]
    with self.assertRaises(ValueError):
      hermite(0.0, xs, ps)

  def test_sorted_asc(self):
    xs = [0.0, 1.0, 2.0]
    ps = [0.0, 1.0, 2.0]
    hermite(0.0, xs, ps)

  def test_sorted_desc(self):
    xs = [2.0, 1.0, 0.0]
    ps = [0.0, 1.0, 2.0]
    hermite(0.0, xs, ps)

  def test_out_of_range(self):
    xs = [0.0, 1.0]
    ps = [0.0, 1.0]
    with self.assertRaises(ValueError):
      hermite(-1.0, xs, ps)
    with self.assertRaises(ValueError):
      hermite(2.0, xs, ps)

class HermiteTestAsc(unittest.TestCase):
  def setUp(self):
    self.xs = [0.1 * i for i in range(11)]
    self.ps = [0.2 * x * x + 0.3 * x + 0.4 for x in self.xs]

  def test_fd(self):
    ps = [hermite(x, self.xs, self.ps) for x in self.xs]
    for i in range(len(ps)):
      self.assertAlmostEqual(ps[i], self.ps[i])

  def test_c(self):
    for c in (0.1 * i for i in range(11)):
      ps = [hermite(x, self.xs, self.ps, c) for x in self.xs]
      for i in range(len(ps)):
        self.assertAlmostEqual(ps[i], self.ps[i])

class HermiteTestDesc(unittest.TestCase):
  def setUp(self):
    self.xs = [0.1 * i for i in range(11, -1)]
    self.ps = [0.2 * x * x + 0.3 * x + 0.4 for x in self.xs]

  def test_fd(self):
    ps = [hermite(x, self.xs, self.ps) for x in self.xs]
    for i in range(len(ps)):
      self.assertAlmostEqual(ps[i], self.ps[i])

  def test_c(self):
    for c in (0.1 * i for i in range(11)):
      ps = [hermite(x, self.xs, self.ps, c) for x in self.xs]
      for i in range(len(ps)):
        self.assertAlmostEqual(ps[i], self.ps[i])

class HermiteClassTest(unittest.TestCase):
  def setUp(self):
    self.xs = [0.1 * i for i in range(11, -1)]
    self.lxs = len(self.xs)
    self.ps = [0.2 * x * x + 0.3 * x + 0.4 for x in self.xs]

  def test_fd(self):
    ms = [m_fd(k, self.xs, self.ps) for k in range(self.lxs)]
    hermite = Hermite(self.xs, self.ps, ms)
    ps = [hermite(x) for x in self.xs]
    for i in range(len(ps)):
      self.assertAlmostEqual(ps[i], self.ps[i])

  def test_c(self):
    for c in (0.1 * i for i in range(11)):
      ms = [m_c(k, self.xs, self.ps, c) for k in range(self.lxs)]
      hermite = Hermite(self.xs, self.ps, ms)
      ps = [hermite(x) for x in self.xs]
      for i in range(len(ps)):
        self.assertAlmostEqual(ps[i], self.ps[i])

if __name__ == "__main__":
  unittest.main()
