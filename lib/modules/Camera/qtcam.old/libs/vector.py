from numpy import *
from numpy.linalg import *
from PyQt4 import QtCore

def qPtArr(qpt):
  return array([qpt.x(), qpt.y()])

def arrQPt(arr):
  return QtCore.QPointF(arr[0], arr[1])

def angle(v1, v2):
  """
  Return the signed angle between two 2-vectors
  """
  n1 = norm(v1)
  n2 = norm(v2)
  if n1 == 0. or n2 == 0.:
    return None
  ang = arccos(clip(dot(v1, v2) / (n1 * n2), -1.0, 1.0))
  if cross(v1, v2) > 0:
    ang *= -1.
  return ang
  
def rotate(v1, angle):
  """
  Return a vector rotated by angle
  """
  c = cos(angle)
  s = sin(angle)
  return array([v1[0] * c + v1[1] * s, -v1[0] * s + v1[1] * c], dtype=v1.dtype)
