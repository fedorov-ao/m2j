#!/usr/bin/env python3

import pymatrix
from pymatrix import Matrix
import math
import textwrap

def matrix_str(self, fmt="{:.3f}"):
  maxlen = max(len(str(e)) for _, _, e in self)
  string = '\n'.join(' '.join(fmt.format(e).rjust(maxlen) for e in row) for row in self.grid)
  return textwrap.dedent(string)

Matrix.__str__ = matrix_str


def vector_from_list(l, column=True):
  v = Matrix.from_list([l])
  if column:
    v = v.trans()
  return v


def vector_get(v, i):
  if v.numrows == 1:
    return v[0][i]
  elif v.numcols == 1:
    return v[i][0]
  else:
    raise ValueError("Not a vector")


def vector_set(v, i, e):
  if v.numrows == 1:
    v[0][i] = e
  elif v.numcols == 1:
    v[i][0] = e
  else:
    raise ValueError("Not a vector")


def matrix_from_list(l):
  return Matrix.from_list(l)


def list_from_vector(v):
  if v.numrows == 1:
    return [v[0][i] for i in range(v.numcols)]
  elif v.numcols == 1:
    return [v[i][0] for i in range(v.numrows)]
  else:
    raise ValueError("Not a vector")


#cleaning up m is vital for further inverse calculations!
def clean_up_matrix(m, eps=1e-6):
  for r, c, el in m:
    if el != 0.0 and abs(el) < eps:
      m[r][c] = 0.0
  return m


ROTATION_ORDER_YPR = 0
ROTATION_ORDER_RYP = 1

def matrix_from_angles_impl_(m, dYaw, dPitch, dRoll, ro=ROTATION_ORDER_YPR):
  """
  Right-handed coordinate system, x right, y up, z from screen.
  Angles are in degrees, measured ccw when looking along the axis towards the origin.
  Order of rotations is yaw-pitch-roll.
  v = Matrix.from_list([[1],[2],[3]]) #column vec
  vr = mRoll*mPitch*mYaw*v
  v = Matrix.from_list([1, 2, 3]) #row vec
  vr = v*mYaw.trans()*mPitch.trans()*mRoll.trans()
  """
  rYaw, rPitch, rRoll = (math.radians(a) for a in (dYaw, dPitch, dRoll))
  sinYaw, sinPitch, sinRoll = (math.sin(a) for a in (rYaw, rPitch, rRoll))
  cosYaw, cosPitch, cosRoll = (math.cos(a) for a in (rYaw, rPitch, rRoll))

  if ro == ROTATION_ORDER_YPR:
    m[0][0] = cosRoll*cosYaw - sinRoll*sinPitch*sinYaw
    m[0][1] = -sinRoll*cosPitch
    m[0][2] = cosRoll*sinYaw + sinRoll*sinPitch*cosYaw
    m[1][0] = sinRoll*cosYaw + cosRoll*sinPitch*sinYaw
    m[1][1] = cosRoll*cosPitch
    m[1][2] = sinRoll*sinYaw - cosRoll*sinPitch*cosYaw
    m[2][0] = -cosPitch*sinYaw
    m[2][1] = sinPitch
    m[2][2] = cosPitch*cosYaw
  elif ro == ROTATION_ORDER_RYP:
    m[0][0] = cosYaw*cosRoll
    m[0][1] = -cosYaw*sinRoll
    m[0][2] = sinYaw
    m[1][0] = sinRoll*cosPitch + cosRoll*sinYaw*sinPitch
    m[1][1] = cosRoll*cosPitch - sinYaw*sinRoll*sinPitch
    m[1][2] = -sinPitch*cosYaw
    m[2][0] = sinRoll*sinPitch - cosRoll*sinYaw*cosPitch
    m[2][1] = cosRoll*sinPitch + sinRoll*sinYaw*cosPitch
    m[2][2] = cosYaw*cosPitch
  else:
    raise ArgumentError("Invalid rotation order")
  return clean_up_matrix(m)


def matrix_from_angles(dYaw=0.0, dPitch=0.0, dRoll=0.0, ro=ROTATION_ORDER_YPR):
  m = Matrix(3, 3, 0.0)
  return matrix_from_angles_impl_(m, dYaw, dPitch, dRoll, ro)


def matrix_from_angles_pos(dYaw=0.0, dPitch=0.0, dRoll=0.0, x=0.0, y=0.0, z=0.0, ro=ROTATION_ORDER_YPR):
  """
  Right-handed coordinate system, x right, y up, z from screen.
  Angles are in degrees, measured ccw when looking along the axis towards the origin.
  Order of rotations is yaw-pitch-roll.
  v = Matrix.from_list([[1],[2],[3]]) #column vec
  vr = mRoll*mPitch*mYaw*v
  v = Matrix.from_list([1, 2, 3]) #row vec
  vr = v*mYaw.trans()*mPitch.trans()*mRoll.trans()
  """
  m = Matrix(4, 4, 0.0)
  matrix_from_angles_impl_(m, dYaw, dPitch, dRoll, ro)
  m[0][3] = x
  m[1][3] = y
  m[2][3] = z
  m[3][3] = 1.0
  return m


def angles_from_matrix(m, ro=ROTATION_ORDER_YPR):
  rPitch, rYaw, rRoll = 0.0, 0.0, 0.0
  if ro == ROTATION_ORDER_YPR:
    sinPitch = m[2][1]
    rPitch = math.asin(sinPitch)
    if 1.0 - abs(sinPitch) > 0.0001:
      rYaw = math.atan2(-m[2][0], m[2][2])
      rRoll = math.atan2(-m[0][1], m[1][1])
    elif sinPitch > 0.0:
      #rPitch almost 90.0 deg
      #sinYaw=0, cosYaw=1, sinPitch=1, cosPitch=0
      #m[0][0] = cosRoll*cosYaw - sinRoll*sinPitch*sinYaw = cosRoll
      #m[0][1] = -sinRoll*cosPitch = 0
      #m[0][2] = cosRoll*sinYaw + sinRoll*sinPitch*cosYaw = sinRoll
      #m[1][0] = sinRoll*cosYaw + cosRoll*sinPitch*sinYaw = sinRoll
      #m[1][1] = cosRoll*cosPitch = 0
      #m[1][2] = sinRoll*sinYaw - cosRoll*sinPitch*cosYaw = -cosRoll
      #m[2][0] = -cosPitch*sinYaw = 0
      #m[2][1] = sinPitch = 1
      #m[2][2] = cosPitch*cosYaw = 0
      rYaw = 0.0
      rRoll = math.atan2(m[1][0], m[0][0])
    else:
      #rPitch almost -90.0 deg
      #sinYaw=0, cosYaw=1, sinPitch=-1, cosPitch=0
      #m[0][0] = cosRoll*cosYaw - sinRoll*sinPitch*sinYaw = cosRoll
      #m[0][1] = -sinRoll*cosPitch = 0
      #m[0][2] = cosRoll*sinYaw + sinRoll*sinPitch*cosYaw = -sinRoll
      #m[1][0] = sinRoll*cosYaw + cosRoll*sinPitch*sinYaw = sinRoll
      #m[1][1] = cosRoll*cosPitch = 0
      #m[1][2] = sinRoll*sinYaw - cosRoll*sinPitch*cosYaw = cosRoll
      #m[2][0] = -cosPitch*sinYaw = 0
      #m[2][1] = sinPitch = 1
      #m[2][2] = cosPitch*cosYaw = 0
      rYaw = 0.0
      rRoll = math.atan2(m[1][0], m[0][0])
  elif ro == ROTATION_ORDER_RYP:
    #TODO Check for gimbal lock
    rRoll = math.atan2(-m[0][1], m[0][0])
    rPitch = math.atan2(-m[1][2], m[2][2])
    rYaw = math.asin(m[0][2])
  else:
    raise ArgumentError("Invalid rotation order")
  return tuple(math.degrees(a) for a in (rYaw, rPitch, rRoll))


def pos_from_matrix(m):
  return (m[0][3], m[1][3], m[2][3])


import unittest

eps = 1e-6

class PymatrixTestCase(unittest.TestCase):
  def testInvDiagonal(self):
    m = Matrix.from_list([[1.0, 0.0, 0.0, 0.0], [0.0, 5.0, 0.0, 0.0], [0.0, 0.0, 9.0, 0.0], [0.0, 0.0, 0.0, 1.0]])
    mi = m.inv()
    ident = Matrix.identity(m.numrows)
    self.assertTrue(ident.equals(m*mi, eps))

  def testInvNonDiagonal(self):
    m = matrix_from_angles_pos(90.0, 90.0, 90.0, 1.0, 2.0, 3.0)
    mi = m.inv()
    mi_m = mi*m
    m_mi = m*mi
    ident = Matrix.identity(m.numrows)
    self.assertTrue(ident.equals(m_mi, eps), f'\n{matrix_str(m_mi, fmt="{:.6f}")}')
    self.assertTrue(ident.equals(mi_m, eps), f'\n{matrix_str(mi_m, fmt="{:.6f}")}')

  def testInvNonDiagonal2(self):
    m = Matrix.from_list([[-1.0, -0.0,  0.0,  1.0], [0.0,  0.0,  1.0,  2.0], [-0.0,  1.0,  0.0,  3.0], [0.0,  0.0,  0.0,  1.0]])
    ident = Matrix.identity(m.numrows)
    mi = m.inv()
    mi_m = mi*m
    m_mi = m*mi
    self.assertTrue(ident.equals(m_mi, eps), f'\n{matrix_str(m_mi, fmt="{:.6f}")}')
    self.assertTrue(ident.equals(mi_m, eps), f'\n{matrix_str(mi_m, fmt="{:.6f}")}')


class MatrixFromAnglesTestCase(unittest.TestCase):
  v = vector_from_list([1.0, 2.0, 3.0]) #column vec
  mYaw = matrix_from_angles(90.0, 0.0, 0.0)
  mPitch = matrix_from_angles(0.0, 90.0, 0.0)
  mRoll = matrix_from_angles(0.0, 0.0, 90.0)
  mCombined = mRoll*mPitch*mYaw
  mCombinedTrans = mYaw.trans()*mPitch.trans()*mRoll.trans()
  ident = Matrix.identity(3)

  def testZeroAngles(self):
    self.assertTrue(matrix_from_angles(0.0, 0.0, 0.0).equals(self.ident, eps))

  def testYaw(self):
    w = vector_from_list([3.0, 2.0, -1.0]) #column vec
    mv = self.mYaw*self.v
    self.assertTrue((mv).equals(w, eps), mv)

  def testPitch(self):
    w = vector_from_list([1.0, -3.0, 2.0]) #column vec
    mv = self.mPitch*self.v
    self.assertTrue((mv).equals(w, eps), mv)

  def testRoll(self):
    w = vector_from_list([-2.0, 1.0, 3.0]) #column vec
    mv = self.mRoll*self.v
    self.assertTrue((mv).equals(w, eps), mv)

  def testRotationOrder(self):
    m = self.mRoll*self.mPitch*self.mYaw
    self.assertTrue(matrix_from_angles(90.0, 90.0, 90.0).equals(m, eps))
    
  def testRotationOrderTransposed(self):
    self.assertTrue(matrix_from_angles(90.0, 90.0, 90.0).trans().equals(self.mCombinedTrans, eps))

  def testRotationOrderInv(self):
    mi = matrix_from_angles(90.0, 90.0, 90.0).inv()
    mb = self.mYaw.inv()*self.mPitch.inv()*self.mRoll.inv()
    self.assertTrue(mi.equals(mb, eps))

  def testVecRotation(self):
    vr = self.v.trans() #row vec
    self.assertTrue((self.mCombined*self.v).equals((vr*self.mCombinedTrans).trans(), eps))

  def testVecRoundtrip(self):
    self.assertTrue((self.mCombined.inv()*self.mCombined*self.v).equals(self.v, eps))

  def testInvTrans(self):
    self.assertTrue(self.mCombined.inv().equals(self.mCombined.trans(), eps))

  def testInv(self):
    mim = self.mCombined*self.mCombined.inv()
    self.assertTrue(mim.equals(self.ident, eps), mim)

  def testInvEquiv(self):
    m = matrix_from_angles(90.0, 90.0, 90.0)
    mi = m.inv()
    mim = mi*m
    mim2 = m*mi
    self.assertTrue(mim.equals(mim2, eps), f"\nm:\n{m}\n\nmi:\n{mi}\n\nmim:\n{mim}\n\nmim2:\n{mim2}")


class MatrixFromAnglesRYPTestCase(unittest.TestCase):
  def test(self):
    dYaw, dPitch, dRoll = 45.0, 35.0, 25.0
    mRYPCombined = matrix_from_angles(dPitch=dPitch)*matrix_from_angles(dYaw=dYaw)*matrix_from_angles(dRoll=dRoll)
    mRYP = matrix_from_angles(dYaw=dYaw, dPitch=dPitch, dRoll=dRoll, ro=ROTATION_ORDER_RYP)
    self.assertTrue(mRYPCombined.equals(mRYP, delta=eps), f"\nmRYPCombined:\n{mRYPCombined}\n\nmRYP:\n{mRYP}")


class MatrixFromAnglesPosTestCase(unittest.TestCase):
  v = vector_from_list([1.0, 2.0, 3.0, 1.0])

  def testZeroAnglesPos(self):
    ident = Matrix.identity(4)
    m = matrix_from_angles_pos(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    self.assertTrue(m.equals(ident, eps), m)

  def testAnglesPos(self):
    m = Matrix.from_list([[-1.0, 0.0,  0.0,  1.0], [0.0,  0.0,  1.0,  2.0], [0.0,  1.0,  0.0,  3.0], [0.0,  0.0,  0.0,  1.0]])
    mc = matrix_from_angles_pos(90.0, 90.0, 90.0, 1.0, 2.0, 3.0)
    self.assertTrue(m.equals(mc, eps), mc)

  def testVecRotate(self):
    m = matrix_from_angles_pos(90.0, 90.0, 90.0, 0.0, 0.0, 0.0)
    mv = m*self.v
    w = vector_from_list([-1.0, 3.0, 2.0, 1.0])
    self.assertTrue(w.equals(mv, eps))

  def testVecMove(self):
    m = matrix_from_angles_pos(0.0, 0.0, 0.0, 1.0, 2.0, 3.0)
    mv = m*self.v
    w = vector_from_list([2.0, 4.0, 6.0, 1.0])
    self.assertTrue(w.equals(mv, eps))

  def testVecRotateMove(self):
    m = matrix_from_angles_pos(90.0, 90.0, 90.0, 1.0, 2.0, 3.0)
    mv = m*self.v
    w = vector_from_list([0.0, 5.0, 5.0, 1.0])
    self.assertTrue(w.equals(mv, eps), mv)

  def testInvPos(self):
    m = matrix_from_angles_pos(0.0, 0.0, 0.0, 1.0, 2.0, 3.0)
    mi = m.inv()
    mim = mi*m
    ident = Matrix.identity(4)
    self.assertTrue(mim.equals(ident, eps), mim)

  def testInvPos2(self):
    m = matrix_from_angles_pos(0.0, 0.0, 0.0, 1.0, 2.0, 3.0)
    mi = matrix_from_angles_pos(0.0, 0.0, 0.0, -1.0, -2.0, -3.0)
    mim = mi*m
    ident = Matrix.identity(4)
    self.assertTrue(mim.equals(ident, eps), f"\nm:\n{m}\n\nmi:\n{mi}\n\nmim:\n{mim}")

  def testInvAngles(self):
    m = matrix_from_angles_pos(90.0, 90.0, 90.0, 0.0, 0.0, 0.0)
    mi = m.inv()
    mim = mi*m
    ident = Matrix.identity(4)
    self.assertTrue(mim.equals(ident, eps), f"\nm:\n{m}\n\nmi:\n{mi}\n\nmim:\n{mim}")

  def testInvAnglesPos(self):
    m = matrix_from_angles_pos(90.0, 90.0, 90.0, 1.0, 2.0, 3.0)
    mi = m.inv()
    mim = mi*m
    ident = Matrix.identity(4)
    #self.assertTrue(mim.equals(ident, eps), f"\nm:\n{m}\n\nmi:\n{mi}\n\nmim:\n{mim}")
    self.assertTrue(ident.equals(mim, eps), f"\nm:\n{m}\n\nmi:\n{mi}\n\nmim:\n{mim}")

  def testInvEquiv(self):
    m = matrix_from_angles_pos(90.0, 90.0, 90.0, 1.0, 2.0, 3.0)
    mi = m.inv()
    mim = mi*m
    mim2 = m*mi
    self.assertTrue(mim.equals(mim2, eps), f"\nm:\n{m}\n\nmi:\n{mi}\n\nmim:\n{mim}\n\nmim2:\n{mim2}")

  def testOrder(self):
    m = matrix_from_angles_pos(90.0, 90.0, 90.0, 1.0, 2.0, 3.0)
    ma = matrix_from_angles_pos(90.0, 90.0, 90.0, 0.0, 0.0, 0.0)
    mp = matrix_from_angles_pos(0.0, 0.0, 0.0, 1.0, 2.0, 3.0)
    mpa = mp*ma
    self.assertTrue(mpa.equals(m, eps), mpa)

  def testVecRoundtrip(self):
    m = matrix_from_angles_pos(90.0, 90.0, 90.0, 1.0, 2.0, 3.0)
    w = m.inv()*m*self.v
    self.assertTrue(w.equals(self.v, eps), w)

  def testVecRoundtrip2(self):
    m = matrix_from_angles_pos(90.0, 90.0, 90.0, 1.0, 2.0, 3.0)
    ma = matrix_from_angles_pos(90.0, 90.0, 90.0, 0.0, 0.0, 0.0)
    mp = matrix_from_angles_pos(0.0, 0.0, 0.0, 1.0, 2.0, 3.0)
    w = ma.inv()*mp.inv()*mp*ma*self.v
    self.assertTrue(w.equals(self.v, eps), w)


class AnglesFromMatrixTestCase(unittest.TestCase):
  def testZeroAngles(self):
    m = matrix_from_angles(0.0, 0.0, 0.0)
    dYaw, dPitch, dRoll = angles_from_matrix(m)
    self.assertAlmostEqual(dYaw, 0.0, delta=eps)
    self.assertAlmostEqual(dPitch, 0.0, delta=eps)
    self.assertAlmostEqual(dRoll, 0.0, delta=eps)

  def testYaw(self):
    m = matrix_from_angles(90.0, 0.0, 0.0)
    dYaw, dPitch, dRoll = angles_from_matrix(m)
    self.assertAlmostEqual(dYaw, 90.0, delta=eps)
    self.assertAlmostEqual(dPitch, 0.0, delta=eps)
    self.assertAlmostEqual(dRoll, 0.0, delta=eps)

  def testPitch(self):
    m = matrix_from_angles(0.0, 90.0, 0.0)
    dYaw, dPitch, dRoll = angles_from_matrix(m)
    self.assertAlmostEqual(dYaw, 0.0, delta=eps)
    self.assertAlmostEqual(dPitch, 90.0, delta=eps)
    self.assertAlmostEqual(dRoll, 0.0, delta=eps)

  def testRoll(self):
    m = matrix_from_angles(0.0, 0.0, 90.0)
    dYaw, dPitch, dRoll = angles_from_matrix(m)
    self.assertAlmostEqual(dYaw, 0.0, delta=eps)
    self.assertAlmostEqual(dPitch, 0.0, delta=eps)
    self.assertAlmostEqual(dRoll, 90.0, delta=eps)

  def testYawPitchRoll(self):
    m = matrix_from_angles(89.0, 89.0, 89.0)
    dYaw, dPitch, dRoll = angles_from_matrix(m)
    self.assertAlmostEqual(dYaw, 89.0, delta=eps)
    self.assertAlmostEqual(dPitch, 89.0, delta=eps)
    self.assertAlmostEqual(dRoll, 89.0, delta=eps)

  def testNegYawPitchRoll(self):
    m = matrix_from_angles(-89.0, -89.0, -89.0)
    dYaw, dPitch, dRoll = angles_from_matrix(m)
    self.assertAlmostEqual(dYaw, -89.0, delta=eps)
    self.assertAlmostEqual(dPitch, -89.0, delta=eps)
    self.assertAlmostEqual(dRoll, -89.0, delta=eps)

  def testYawPitch(self):
    m = matrix_from_angles(90.0, 90.0, 0.0)
    dYaw, dPitch, dRoll = angles_from_matrix(m)
    self.assertAlmostEqual(dYaw, 0.0, delta=eps)
    self.assertAlmostEqual(dPitch, 90.0, delta=eps)
    self.assertAlmostEqual(dRoll, 90.0, delta=eps) #assumed to be correct
    #testing that matrices made from initial and extracted angles are equal
    m2 = matrix_from_angles(dYaw, dPitch, dRoll)
    self.assertTrue(m2.equals(m, eps))

  def testYawNegPitch(self):
    m = matrix_from_angles(90.0, -90.0, 0.0)
    dYaw, dPitch, dRoll = angles_from_matrix(m)
    self.assertAlmostEqual(dYaw, 0.0, delta=eps)
    self.assertAlmostEqual(dPitch, -90.0, delta=eps)
    self.assertAlmostEqual(dRoll, -90.0, delta=eps) #assumed to be correct
    #testing that matrices made from initial and extracted angles are equal
    m2 = matrix_from_angles(dYaw, dPitch, dRoll)
    self.assertTrue(m2.equals(m, eps))

  def testYawRoll(self):
    m = matrix_from_angles(90.0, 0.0, 90.0)
    dYaw, dPitch, dRoll = angles_from_matrix(m)
    self.assertAlmostEqual(dYaw, 90.0, delta=eps)
    self.assertAlmostEqual(dPitch, 0.0, delta=eps)
    self.assertAlmostEqual(dRoll, 90.0, delta=eps)

  def testPitchRoll(self):
    m = matrix_from_angles(0.0, 90.0, 90.0)
    dYaw, dPitch, dRoll = angles_from_matrix(m)
    self.assertAlmostEqual(dYaw, 0.0, delta=eps)
    self.assertAlmostEqual(dPitch, 90.0, delta=eps)
    self.assertAlmostEqual(dRoll, 90.0, delta=eps)

  def testNegPitchRoll(self):
    m = matrix_from_angles(0.0, -90.0, 90.0)
    dYaw, dPitch, dRoll = angles_from_matrix(m)
    self.assertAlmostEqual(dYaw, 0.0, delta=eps)
    self.assertAlmostEqual(dPitch, -90.0, delta=eps)
    self.assertAlmostEqual(dRoll, 90.0, delta=eps) #assumed to be correct
    #testing that matrices made from initial and extracted angles are equal
    m2 = matrix_from_angles(dYaw, dPitch, dRoll)
    self.assertTrue(m2.equals(m, eps))


class AnglesFromMatrixRYPTestCase(unittest.TestCase):
  def test2 (self):
    for dYaw in (10.0, 20.0, 30.0):
      for dPitch in (10.0, 20.0, 30.0):
        for dRoll in (10.0, 20.0, 30.0):
          m = matrix_from_angles(dYaw=dYaw, dPitch=dPitch, dRoll=dRoll, ro=ROTATION_ORDER_RYP)
          dYaw2, dPitch2, dRoll2 = angles_from_matrix(m, ro=ROTATION_ORDER_RYP)
          try:
            self.assertAlmostEqual(dYaw, dYaw2, delta=eps)
            self.assertAlmostEqual(dPitch, dPitch2, delta=eps)
            self.assertAlmostEqual(dRoll, dRoll2, delta=eps)
          except AssertionError:
            print(f"{dYaw} {dYaw2} {dPitch} {dPitch2} {dRoll} {dRoll2}")
            raise

  def test(self):
    for dYaw in (-180.0, -135.0, -45.0, 0.0, 45.0, 135.0, 180.0):
      for dPitch in (-90.0, -45.0, 0.0, 45.0, 90.0):
        for dRoll in (-180.0, -135.0, -45.0, 0.0, 45.0, 135.0, 180.0):
          m = matrix_from_angles(dYaw=dYaw, dPitch=dPitch, dRoll=dRoll, ro=ROTATION_ORDER_RYP)
          dYaw2, dPitch2, dRoll2 = angles_from_matrix(m, ro=ROTATION_ORDER_RYP)
          try:
            m2 = matrix_from_angles(dYaw=dYaw2, dPitch=dPitch2, dRoll=dRoll2, ro=ROTATION_ORDER_RYP)
            self.assertTrue(m2.equals(m, eps))
            #self.assertAlmostEqual(dYaw, dYaw2, delta=eps)
            #self.assertAlmostEqual(dPitch, dPitch2, delta=eps)
            #self.assertAlmostEqual(dRoll, dRoll2, delta=eps)
          except AssertionError:
            print(f"{dYaw} {dYaw2} {dPitch} {dPitch2} {dRoll} {dRoll2}\n{m}\n\n{m2}")
            raise


class PosFromMatrixTestCase(unittest.TestCase):
  def test(self):
    m = matrix_from_angles_pos(0.0, 0.0, 0.0, 1.0, 2.0, 3.0)
    p = pos_from_matrix(m)
    self.assertAlmostEqual(p[0], 1.0, delta=eps)
    self.assertAlmostEqual(p[1], 2.0, delta=eps)
    self.assertAlmostEqual(p[2], 3.0, delta=eps)


class DirsTestCase(unittest.TestCase):
  def calc_dirs_(self, dYaw, dPitch, dRoll):
    rYaw, rPitch, rRoll = (math.radians(a) for a in (dYaw, dPitch, dRoll))
    sinYaw, sinPitch, sinRoll = (math.sin(a) for a in (rYaw, rPitch, rRoll))
    cosYaw, cosPitch, cosRoll = (math.cos(a) for a in (rYaw, rPitch, rRoll))
    dirs = [None, None, None]
    dirs[0] = (cosRoll*cosYaw - sinRoll*sinPitch*sinYaw, sinRoll*cosYaw + cosRoll*sinPitch*sinYaw, -cosPitch*sinYaw)
    dirs[1] = (-sinRoll*cosPitch, cosRoll*cosPitch, sinPitch)
    dirs[2] = (cosRoll*sinYaw + sinRoll*sinPitch*cosYaw, sinRoll*sinYaw - cosRoll*sinPitch*cosYaw, cosPitch*cosYaw)
    return dirs

  def compare_matrix_to_dirs_(self, m, dirs):
    for i in range(len(dirs)):
      d = dirs[i]
      for j in range(len(d)):
        #dirs are the columns of transformation matrix
        self.assertAlmostEqual(d[j], m[j][i], delta=eps)

  def testPositive(self):
    dYaw, dPitch, dRoll = 20.0, 30.0, 40.0
    dirs = self.calc_dirs_(dYaw, dPitch, dRoll)
    m = matrix_from_angles(dYaw, dPitch, dRoll)
    self.compare_matrix_to_dirs_(m, dirs)

  def testNegative(self):
    dYaw, dPitch, dRoll = -20.0, -30.0, -40.0
    dirs = self.calc_dirs_(dYaw, dPitch, dRoll)
    m = matrix_from_angles(dYaw, dPitch, dRoll)
    self.compare_matrix_to_dirs_(m, dirs)


class HelpersTestCase(unittest.TestCase):
  def testListFromVector(self):
    l = [1, 2, 3]
    v = vector_from_list(l)
    ll = list_from_vector(v)
    self.assertEqual(l, ll)


if __name__ == '__main__':
    unittest.main() 
