#!/usr/bin/python

import unittest
import m2j
from m2j import *


#IterativeInputOp
class IncIterativeInputOpTestCase(unittest.TestCase):
  longMessage = True

  def setUp(self):
    outputOp = ApproxOp(PolynomialApproximator(coeffs=[0.0, 2.0]))
    self.inputOp = IterativeInputOp(outputOp=outputOp, eps=0.001, numSteps=100)

  def test_0(self):
    delta = 0.001
    inputLimits = [-1.0, 1.0]
    self.assertAlmostEqual(self.inputOp.calc(0.0, inputLimits), 0.0, delta=delta)

  def test_1(self):
    delta = 0.001
    inputLimits = [-1.0, 1.0]
    self.assertAlmostEqual(self.inputOp.calc(2.0, inputLimits), 1.0, delta=delta)

  def test_minus1(self):
    delta = 0.001
    inputLimits = [-1.0, 1.0]
    self.assertAlmostEqual(self.inputOp.calc(-2.0, inputLimits), -1.0, delta=delta)


class DecIterativeInputOpTestCase(unittest.TestCase):
  longMessage = True

  def setUp(self):
    outputOp = ApproxOp(PolynomialApproximator(coeffs=[0.0, -2.0]))
    self.inputOp = IterativeInputOp(outputOp=outputOp, cmp=lambda a,b: a > b, eps=0.001, numSteps=100)

  def test_0(self):
    delta = 0.001
    inputLimits = [-1.0, 1.0]
    self.assertAlmostEqual(self.inputOp.calc(0.0, inputLimits), 0.0, delta=delta)

  def test_1(self):
    delta = 0.001
    inputLimits = [-1.0, 1.0]
    self.assertAlmostEqual(self.inputOp.calc(2.0, inputLimits), -1.0, delta=delta)

  def test_minus1(self):
    delta = 0.001
    inputLimits = [-1.0, 1.0]
    self.assertAlmostEqual(self.inputOp.calc(-2.0, inputLimits), 1.0, delta=delta)


#LookupOp
def make_lookup_op(coeffs, inputStep, cmp=lambda a,b: a < b):
  outputOp = ApproxOp(PolynomialApproximator(coeffs=coeffs))
  inputOp = IterativeInputOp(outputOp=outputOp, cmp=cmp, eps=0.001, numSteps=100)
  lookupOp = LookupOp(inputOp=inputOp, outputOp=outputOp, inputStep=inputStep)
  return lookupOp


class IncLookupOpTestCase(unittest.TestCase):
  longMessage = True

  def setUp(self):
    self.lookupOp = make_lookup_op(coeffs=[0.0, 2.0], inputStep=0.1)

  def test_init(self):
    self.assertEqual(self.lookupOp.ivs_, [0.0, 0.1])
    self.assertEqual(self.lookupOp.ovs_, [0.0, 0.2])

  def test_0(self):
    delta = 0.001
    self.assertAlmostEqual(self.lookupOp.calc(0.0), 0.0, delta=delta, msg="ivs_: {}, ovs_: {}".format(self.lookupOp.ivs_, self.lookupOp.ovs_))

  def test_1(self):
    delta = 0.001
    self.assertAlmostEqual(self.lookupOp.calc(2.0), 1.0, delta=delta, msg="ivs_: {}, ovs_: {}".format(self.lookupOp.ivs_, self.lookupOp.ovs_))

  def test_minus1(self):
    delta = 0.001
    self.assertAlmostEqual(self.lookupOp.calc(-2.0), -1.0, delta=delta, msg="ivs_: {}, ovs_: {}".format(self.lookupOp.ivs_, self.lookupOp.ovs_))
    

class DecLookupOpTestCase(unittest.TestCase):
  longMessage = True
    
  def setUp(self):
    self.lookupOp = make_lookup_op(coeffs=[0.0, -2.0], inputStep=0.1, cmp=lambda a,b : a < b)

  def test_init(self):
    self.assertEqual(self.lookupOp.ivs_, [0.1, 0.0])
    self.assertEqual(self.lookupOp.ovs_, [-0.2, 0.0])

  def test_0(self):
    delta = 0.001
    self.assertAlmostEqual(self.lookupOp.calc(0.0), 0.0, delta=delta, msg="ivs_: {}, ovs_: {}".format(self.lookupOp.ivs_, self.lookupOp.ovs_))

  def test_1(self):
    delta = 0.001
    self.assertAlmostEqual(self.lookupOp.calc(-2.0), 1.0, delta=delta, msg="ivs_: {}, ovs_: {}".format(self.lookupOp.ivs_, self.lookupOp.ovs_))

  def test_minus1(self):
    delta = 0.001
    self.assertAlmostEqual(self.lookupOp.calc(2.0), -1.0, delta=delta, msg="ivs_: {}, ovs_: {}".format(self.lookupOp.ivs_, self.lookupOp.ovs_))


if __name__ == '__main__':
    unittest.main() 
