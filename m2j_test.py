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


if __name__ == '__main__':
    unittest.main() 
