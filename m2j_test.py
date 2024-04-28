#!/usr/bin/python

import unittest
import m2j
from m2j import *


#IterativeInputOp
class IncIterativeInputOpTestCase(unittest.TestCase):
  longMessage = True
  delta = 0.001
  inputLimits = [-1.0, 1.0]
  coeffs = {1:2.0}
  eps = 0.001
  numSteps = 100
  values = (
    (0.0, 0.0),
    (1.0, 2.0),
    (-1.0, -2.0)
  )

  def setUp(self):
    outputOp = FuncOp(PolynomialFunc(coeffs=self.coeffs))
    self.inputOp = IterativeInputOp(outputOp=outputOp, eps=self.eps, numSteps=self.numSteps)

  def test(self):
    for x,y in self.values:
      self.assertAlmostEqual(self.inputOp.calc(y, self.inputLimits), x, delta=self.delta)


class DecIterativeInputOpTestCase(unittest.TestCase):
  longMessage = True
  delta = 0.001
  inputLimits = [-1.0, 1.0]
  coeffs = {1:-2.0}
  eps = 0.001
  numSteps = 100
  values = (
    (0.0, 0.0),
    (1.0, -2.0),
    (-1.0, 2.0)
  )

  def setUp(self):
    outputOp = FuncOp(PolynomialFunc(coeffs=self.coeffs))
    self.inputOp = IterativeInputOp(outputOp=outputOp, cmp=lambda a,b: a > b, eps=self.eps, numSteps=self.numSteps)

  def test(self):
    for x,y in self.values:
      self.assertAlmostEqual(self.inputOp.calc(y, self.inputLimits), x, delta=self.delta)


class SelectNearestTestCase(unittest.TestCase):
  def testEmptyValues(self):
    self.assertIsNone(select_nearest(0.0, 1.0, None))
    self.assertIsNone(select_nearest(0.0, 1.0, []))

  def testSwappedLimits(self):
    self.assertEqual(1.0, select_nearest(1.0, 0.0, [0.0, 1.0, 2.0]))

  def testSingleValue(self):
    self.assertIsNone(select_nearest(0.0, 0.5, [1.0]))
    self.assertEqual(0.5, select_nearest(0.0, 1.0, [0.5]))
    self.assertEqual(0.0, select_nearest(0.0, 1.0, [0.0]))
    self.assertEqual(1.0, select_nearest(0.0, 1.0, [1.0]))
    self.assertIsNone(select_nearest(1.5, 2.0, [1.0]))

  def testMultipleOrderedValues(self):
    values = [0.0, 1.0, 2.0]
    self.assertIsNone(select_nearest(-1.5, -0.5, values))
    self.assertEqual(0.0, select_nearest(-0.5, 0.5, values))
    self.assertEqual(0.0, select_nearest(-0.5, 1.5, values))
    self.assertEqual(1.0, select_nearest(0.5, 1.5, values))
    self.assertEqual(1.0, select_nearest(0.5, 2.5, values))
    self.assertEqual(2.0, select_nearest(1.5, 2.5, values))
    self.assertIsNone(select_nearest(2.5, 3.0, values))

  def testMultipleUnorderedValues(self):
    values = [1.0, 0.0, 2.0]
    self.assertIsNone(select_nearest(-1.5, -0.5, values))
    self.assertEqual(0.0, select_nearest(-0.5, 0.5, values))
    self.assertEqual(0.0, select_nearest(-0.5, 1.5, values))
    self.assertEqual(1.0, select_nearest(0.5, 1.5, values))
    self.assertEqual(1.0, select_nearest(0.5, 2.5, values))
    self.assertEqual(2.0, select_nearest(1.5, 2.5, values))
    self.assertIsNone(select_nearest(2.5, 3.0, values))

  def testSkipExactMatch(self):
    values = [0.0, 1.0, 2.0]
    self.assertIsNone(select_nearest(0.0, 0.5, values, False))
    self.assertEqual(1.0, select_nearest(0.0, 1.5, values, False))


class SetNestedStrictTest(unittest.TestCase):
  def testInvalidSeqType(self):
    with self.assertRaises(ValueError):
      set_nested_strict(tuple(), "name", 42, ".")

  def testValidKeysType(self):
    seq = {"42" : 24}
    set_nested_strict(seq, "42", 42, ".")
    self.assertEqual({"42" : 42}, seq)
    seq = {"42" : 24}
    set_nested_strict(seq, ("42",), 42, ".")
    self.assertEqual({"42" : 42}, seq)
    seq = {"42" : 24}
    set_nested_strict(seq, ["42"], 42, ".")
    self.assertEqual({"42" : 42}, seq)

  def testInvalidKeysType(self):
    with self.assertRaises(ValueError):
      set_nested_strict({}, 42, 42, ".")

if __name__ == '__main__':
    unittest.main() 
