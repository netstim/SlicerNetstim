import qt, vtk, slicer
import SimpleITK as sitk
import sitkUtils

import numpy as np

from . import GridNodeHelper



def delay(msecs = 500):
  # delay application
  dieTime = qt.QTime().currentTime().addMSecs(msecs)
  while qt.QTime().currentTime() < dieTime:
    qt.QCoreApplication.processEvents(qt.QEventLoop.AllEvents, 100)

def previewWarp(sourceNode, targetNode, outNode):
  # points
  sourcePoints = vtk.vtkPoints()
  sourceNode.GetControlPointPositionsWorld(sourcePoints)
  targetPoints = vtk.vtkPoints()
  targetNode.GetControlPointPositionsWorld(targetPoints)
  # thin plate
  transform=vtk.vtkThinPlateSplineTransform()
  transform.SetSourceLandmarks(sourcePoints)
  transform.SetTargetLandmarks(targetPoints)
  transform.SetBasisToR()
  transform.Inverse()
  transformNode=slicer.mrmlScene.AddNewNodeByClass('vtkMRMLTransformNode')
  transformNode.SetAndObserveTransformFromParent(transform)
  # display
  transformNode.CreateDefaultDisplayNodes()
  transformNode.GetDisplayNode().SetVisibility(1)
  transformNode.GetDisplayNode().SetVisibility3D(0)
  transformNode.GetDisplayNode().SetAndObserveGlyphPointsNode(sourceNode)
  transformNode.GetDisplayNode().SetVisibility2D(1)
  delay() # update display
  return transformNode


def createFolderDisplayNode(folderID, color=[0.66,0.66,0.66]):
  # from qSlicerSubjectHierarchyFolderPlugin.cxx
  shNode = slicer.mrmlScene.GetSubjectHierarchyNode()
  displayNode = slicer.vtkMRMLFolderDisplayNode()
  displayNode.SetName(shNode.GetItemName(folderID))
  displayNode.SetHideFromEditors(0)
  displayNode.SetAttribute('SubjectHierarchy.Folder', "1")
  displayNode.SetColor(*color)
  shNode.GetScene().AddNode(displayNode)
  shNode.SetItemDataNode(folderID, displayNode)
  shNode.ItemModified(folderID)


def getPointsFromAttribute(attributeName):
  # iterate over markups fiducial and get points from nodes with specified attribute
  points = vtk.vtkPoints() # init
  shNode = slicer.mrmlScene.GetSubjectHierarchyNode() # subject hierarchy
  nMarkups = slicer.mrmlScene.GetNumberOfNodesByClass('vtkMRMLMarkupsFiducialNode')
  radius = []
  for i in range(nMarkups): # iterate
    markupNode = slicer.mrmlScene.GetNthNodeByClass(i, 'vtkMRMLMarkupsFiducialNode')
    if attributeName in shNode.GetItemAttributeNames(shNode.GetItemByDataNode(markupNode)) and shNode.GetItemDataNode(shNode.GetItemParent(shNode.GetItemByDataNode(markupNode))).GetDescription() == 'Enabled':
      # get points of current node
      p = vtk.vtkPoints()
      markupNode.GetControlPointPositionsWorld(p)
      # add to output points
      points.InsertPoints(points.GetNumberOfPoints(), p.GetNumberOfPoints(), 0, p)
      # get radius
      for i in range(markupNode.GetNumberOfControlPoints()):
        if attributeName == 'fixed':
          radius.append("30.0")
        else:
          radius.append(markupNode.GetNthControlPointDescription(i))
  # return
  return points,radius


def addCorrection(sourceNode, targetNode, spread):

  # create folder display
  shNode = slicer.mrmlScene.GetSubjectHierarchyNode()
  folderID = shNode.CreateFolderItem(shNode.GetSceneItemID(), targetNode.GetName())
  createFolderDisplayNode(folderID)
  shNode.SetItemAttribute(folderID, 'correction', '1')
  shNode.GetItemDataNode(folderID).SetDescription('Enabled')

  # add fiducials
  for fiducial,attribute in zip([sourceNode, targetNode],['source','target']):
    fiducial.SetName(attribute)
    fiducial.SetLocked(1)
    fiducial.GetDisplayNode().SetVisibility(attribute == 'target') # visualize target fiducials
    fiducial.GetDisplayNode().SetTextScale(0)
    shNode.SetItemAttribute(shNode.GetItemByDataNode(fiducial), 'correction', '1')
    shNode.SetItemAttribute(shNode.GetItemByDataNode(fiducial), attribute, '1')
    shNode.SetItemParent(shNode.GetItemByDataNode(fiducial), folderID)
    for i in range(fiducial.GetNumberOfControlPoints()):
      fiducial.SetNthControlPointDescription(i, spread)


def addFixedPointsFolder():
  # create folder dislpay node to store fixed points
  shNode = slicer.mrmlScene.GetSubjectHierarchyNode()
  folderID = shNode.CreateFolderItem(shNode.GetSceneItemID(), '')
  createFolderDisplayNode(folderID)
  shNode.SetItemAttribute(folderID, 'correction', '1')
  shNode.GetItemDataNode(folderID).SetDescription('Enabled')
  folderNode = shNode.GetItemDataNode(folderID)
  folderNode.SetName('Fixed Points')
  return folderNode

def addFixedPoint(node):

  # get fixed points folder
  try:
    folderNode = slicer.util.getNode('Fixed Points')
  except:
    folderNode = addFixedPointsFolder()

  # add node to the folder and set attributes
  shNode = slicer.mrmlScene.GetSubjectHierarchyNode()
  shNode.SetItemAttribute(shNode.GetItemByDataNode(node), 'correction', '1')
  shNode.SetItemAttribute(shNode.GetItemByDataNode(node), 'fixed', '1')
  shNode.SetItemParent(shNode.GetItemByDataNode(node), shNode.GetItemByDataNode(folderNode))