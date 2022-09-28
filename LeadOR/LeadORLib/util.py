import slicer, vtk
import numpy as np
from io import StringIO

#
# Feature
#

class Feature():

  def __init__(self, sourceNodeID, recordingSitesMarkupsNodeID):

    sourceText = slicer.util.getNode(sourceNodeID).GetText()

    self.channelNames =  sourceText.splitlines()[0].split(",")[1:]
    self.textData = np.genfromtxt(StringIO(sourceText), delimiter=',', skip_header=1)

    self.recordingSitesNode = slicer.util.getNode(recordingSitesMarkupsNodeID)
    allRecordingSitePoints = self.initRecordingSitePoints()
    self.validRecordingSitesIdx = ~np.any(np.isnan(allRecordingSitePoints),1)
    self.recordingSitePoints = allRecordingSitePoints[self.validRecordingSitesIdx,:]

  def getValuesForChannel(self, channelName):
    allValues = self.textData[:,self.channelNames.index(channelName)+1].squeeze()
    return allValues[self.validRecordingSitesIdx]

  def getRecordingSitesPoints(self):
    return self.recordingSitePoints

  def initRecordingSitePoints(self):
    recordingSitesIDs = np.array(self.textData[:,0], dtype=int)
    recordingSitePoints = np.zeros((len(recordingSitesIDs),3))
    for i,recordingSiteID in enumerate(recordingSitesIDs):
      recordingSitePoints[i,:] = self.getRecordingSitePointFromID(recordingSiteID)
    return recordingSitePoints

  def getRecordingSitePointFromID(self, id):
    for i in range(self.recordingSitesNode.GetNumberOfControlPoints()):
      if int(self.recordingSitesNode.GetNthControlPointLabel(i)) == id:
        return self.recordingSitesNode.GetNthControlPointPosition(i)



#
# Trajectory
#

class Trajectory():

  def __init__(self, N, fromFolderID=False):

    shNode = slicer.mrmlScene.GetSubjectHierarchyNode()

    if fromFolderID:
      self.folderID = N
      self.trajectoryNumber = shNode.GetItemAttribute(self.folderID, 'LeadORTrajectory')
      self.channelName = shNode.GetItemAttribute(self.folderID, 'ChannelName')
    else:
      self.trajectoryNumber = N
      self.channelName = ''
      self.folderID = shNode.CreateFolderItem(shNode.GetSceneItemID(), "LeadOR Trajectory " + str(self.trajectoryNumber))
      shNode.SetItemAttribute(self.folderID, 'LeadORTrajectory', str(self.trajectoryNumber))
      shNode.SetItemAttribute(self.folderID, 'ChannelName', self.channelName)
      transformID = self.createTranslationTransform()
      self.createMEModel(transformID)
      self.createTrajectoryLine(transformID)
      self.createTipFiducial(transformID)
      self.createTubeModel()

    self.translationTransformNodeID = shNode.GetItemAttribute(self.folderID, 'translationTransformNodeID')
    self.microElectrodeModelNodeID = shNode.GetItemAttribute(self.folderID, 'microElectrodeModelNodeID')
    self.trajectoryLineNodeID = shNode.GetItemAttribute(self.folderID, 'trajectoryLineNodeID')
    self.tipFiducialNodeID = shNode.GetItemAttribute(self.folderID, 'tipFiducialNodeID')
    self.tubeModelNodeID = shNode.GetItemAttribute(self.folderID, 'tubeModelNodeID')

    self.setNodeNames()

  def setModelVisibility(self, visible):
    slicer.util.getNode(self.microElectrodeModelNodeID).GetDisplayNode().SetVisibility3D(visible)

  def setLineVisibility(self, visible):
    slicer.util.getNode(self.trajectoryLineNodeID).GetDisplayNode().SetVisibility3D(visible)

  def setTipVisibility(self, visible):
    slicer.util.getNode(self.tipFiducialNodeID).GetDisplayNode().SetVisibility3D(visible)

  def setDistanceToTargetTransformID(self, distanceToTargetTransformID):
    planningTransformID = slicer.util.getNode(distanceToTargetTransformID).GetTransformNodeID()
    slicer.util.getNode(self.translationTransformNodeID).SetAndObserveTransformNodeID(distanceToTargetTransformID)
    slicer.util.getNode(self.tubeModelNodeID).SetAndObserveTransformNodeID(planningTransformID)

  def setChannelName(self, channelName):
    self.channelName = channelName
    slicer.mrmlScene.GetSubjectHierarchyNode().SetItemAttribute(self.folderID, 'ChannelName', self.channelName)
    self.setNodeNames()

  def setNodeNames(self):
    name = self.channelName if self.channelName != '' else str(self.trajectoryNumber)
    shNode = slicer.mrmlScene.GetSubjectHierarchyNode()
    shNode.SetItemName(self.folderID, "LeadOR Trajectory %s" % name)
    slicer.util.getNode(self.translationTransformNodeID).SetName("%s: Translation Transform" % name)
    slicer.util.getNode(self.microElectrodeModelNodeID).SetName("%s: ME Model" % name)
    slicer.util.getNode(self.trajectoryLineNodeID).SetName("%s: Trajectory Line" % name)
    slicer.util.getNode(self.tipFiducialNodeID).SetName("%s: Tip Fiducial" % name)
    slicer.util.getNode(self.tubeModelNodeID).SetName("%s: Tube Model" % name)

  def addNodeAndAttributeToSHFolder(self, node, attributeName):
    shNode = slicer.mrmlScene.GetSubjectHierarchyNode()
    shNode.SetItemParent(shNode.GetItemByDataNode(node), self.folderID)
    shNode.SetItemAttribute(self.folderID, attributeName, node.GetID())

  def createTranslationTransform(self):
    index = np.array(np.unravel_index(self.trajectoryNumber, (3,3))) - 1  # from 0:8 to (-1,-1) : (1,1)
    # get translation ammount
    np.seterr(divide='ignore')
    hypotenuse = 2
    alpha = np.arctan(abs(np.divide(index[0],index[1]))) if any(index) else 0
    # create matrix
    m = vtk.vtkMatrix4x4()
    m.SetElement(0, 3, -index[0]*np.sin(alpha)*hypotenuse)
    m.SetElement(1, 3, -index[1]*np.cos(alpha)*hypotenuse)
    # add node
    transformNode = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLLinearTransformNode')
    transformNode.SetMatrixTransformToParent(m)
    self.addNodeAndAttributeToSHFolder(transformNode, 'translationTransformNodeID')
    return transformNode.GetID()

  def createMEModel(self, parentTransformID):
    # create cylinder (macro)
    cylinder = vtk.vtkCylinderSource()
    cylinder.SetRadius(0.35)
    cylinder.SetHeight(80)
    cylinder.SetCenter(0, cylinder.GetHeight()/2 + 3, 0)
    cylinder.SetResolution(12)
    cylinder.Update()
    # cone line (micro)
    cone = vtk.vtkConeSource()
    cone.SetRadius(0.2)
    cone.SetHeight(3)
    cone.SetDirection(0,-1,0)
    cone.SetCenter(0, 1.5, 0)
    cone.SetResolution(12)
    cone.Update()
    # append cone and cylinder
    input1 = vtk.vtkPolyData()
    input2 = vtk.vtkPolyData()
    input1.ShallowCopy(cylinder.GetOutput())
    input2.ShallowCopy(cone.GetOutput())
    appendFilter = vtk.vtkAppendPolyData()
    appendFilter.AddInputData(input1)
    appendFilter.AddInputData(input2)
    appendFilter.Update()
    cleanFilter = vtk.vtkCleanPolyData()
    cleanFilter.SetInputConnection(appendFilter.GetOutputPort())
    cleanFilter.Update()
    # add model node
    modelsLogic = slicer.modules.models.logic()
    model = modelsLogic.AddModel(cleanFilter.GetOutput())
    model.CreateDefaultSequenceDisplayNodes()
    model.CreateDefaultDisplayNodes()
    model.GetDisplayNode().SetColor(0,1,1)
    model.GetDisplayNode().SetVisibility2D(1)
    model.GetDisplayNode().SetVisibility3D(1)
    self.setDefaultOrientationToModel(model)
    model.SetAndObserveTransformNodeID(parentTransformID)
    self.addNodeAndAttributeToSHFolder(model, 'microElectrodeModelNodeID')

  def createTrajectoryLine(self, parentTransformID):
    ls = vtk.vtkLineSource()
    ls.SetPoint1(0, -10, 0)
    ls.SetPoint2(0,  80, 0)
    ls.Update()
    model = slicer.modules.models.logic().AddModel(ls.GetOutput())
    model.CreateDefaultSequenceDisplayNodes()
    model.CreateDefaultDisplayNodes()
    model.SetDisplayVisibility(1)
    model.GetDisplayNode().SetColor(0.9,0.9,0.9)
    self.setDefaultOrientationToModel(model)
    model.SetAndObserveTransformNodeID(parentTransformID)
    self.addNodeAndAttributeToSHFolder(model, 'trajectoryLineNodeID')

  def createTipFiducial(self, parentTransformID):
    fiducialNode = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLMarkupsFiducialNode')
    fiducialNode.GetDisplayNode().SetTextScale(0)
    fiducialNode.GetDisplayNode().SetVisibility3D(1)
    fiducialNode.AddControlPointWorld(vtk.vtkVector3d([0, 0, 0]))
    fiducialNode.SetLocked(True)
    fiducialNode.SetAndObserveTransformNodeID(parentTransformID)
    self.addNodeAndAttributeToSHFolder(fiducialNode, 'tipFiducialNodeID')

  def setDefaultOrientationToModel(self, model):
    # put in I-S axis
    vtkTransform = vtk.vtkTransform()
    vtkTransform.RotateWXYZ(90, 1, 0, 0)
    model.ApplyTransform(vtkTransform)

  def createTubeModel(self):
    tubeModel = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLModelNode')
    tubeModel.CreateDefaultDisplayNodes()
    tubeModel.GetDisplayNode().SetAndObserveColorNodeID(slicer.util.getNode('Viridis').GetID())
    tubeModel.GetDisplayNode().ScalarVisibilityOn()
    self.addNodeAndAttributeToSHFolder(tubeModel, 'tubeModelNodeID')

  def mapFeatureValuesToTubeRadiusAndColor(self, valuesArray, samplePoints, visible):
    matrix = vtk.vtkMatrix4x4()
    slicer.util.getNode(self.translationTransformNodeID).GetMatrixTransformToParent(matrix)
    transformedPoint = np.zeros(4)
    samplePointsVTK = vtk.vtkPoints()
    for i in range(samplePoints.shape[0]):
      matrix.MultiplyPoint(np.append(samplePoints[i,:],1.0), transformedPoint)
      samplePointsVTK.InsertNextPoint(transformedPoint[:-1])
    # array to vtk
    valuesMedian = np.median(valuesArray[:min(len(valuesArray),5)])
    vtkValuesArray = vtk.vtkDoubleArray()
    vtkValuesArray.SetName('values')
    for value in valuesArray:
      rel_val_from_cero = max((value / valuesMedian) - 1, 0.1)
      rel_val_from_cero_to_one = min(rel_val_from_cero / 2.0, 1) # values greater than three times the median are caped to one
      vtkValuesArray.InsertNextTuple((rel_val_from_cero_to_one,))
    # line source
    polyLineSource = vtk.vtkPolyLineSource()
    polyLineSource.SetPoints(samplePointsVTK)
    polyLineSource.Update()
    # poly data
    polyData = polyLineSource.GetOutput()
    polyData.GetPointData().AddArray(vtkValuesArray)
    polyData.GetPointData().SetScalars(vtkValuesArray)
    # run tube filter
    tubeFilter = vtk.vtkTubeFilter()
    tubeFilter.SetInputData(polyData)
    tubeFilter.SetVaryRadiusToVaryRadiusByAbsoluteScalar()
    tubeFilter.SetNumberOfSides(16)
    tubeFilter.CappingOn()
    tubeFilter.Update()
    # smooth
    smoothFilter = vtk.vtkSmoothPolyDataFilter()
    smoothFilter.SetInputData(tubeFilter.GetOutput())
    smoothFilter.SetNumberOfIterations(2)
    smoothFilter.SetRelaxationFactor(0.5)
    smoothFilter.FeatureEdgeSmoothingOff()
    smoothFilter.BoundarySmoothingOn()
    smoothFilter.Update()
    # update
    tubeModelNode = slicer.util.getNode(self.tubeModelNodeID)
    tubeModelNode.SetAndObservePolyData(smoothFilter.GetOutput())
    tubeModelNode.GetDisplayNode().SetActiveScalarName('values')
    tubeModelNode.GetDisplayNode().SetAutoScalarRange(False)
    tubeModelNode.GetDisplayNode().SetScalarRange(0.0,1.0)
    tubeModelNode.GetDisplayNode().SetVisibility(visible)
    tubeModelNode.Modified()

  @classmethod
  def InitOrGetNthTrajectory(cls, trajectoryNumber):
    trajectory = cls.GetNthTrajectory(trajectoryNumber)
    if trajectory is not None:
      return trajectory
    else:
      return cls(trajectoryNumber)

  @classmethod
  def GetNthTrajectory(cls, trajectoryNumber):
    folderID = cls.GetFolderIDForNthTrajectory(trajectoryNumber)
    if folderID is not None:
      return cls(folderID, fromFolderID=True)

  @classmethod
  def GetTrajectoryFromChannelName(cls, channelName):
    folderID = cls.GetFolderIDForChannelName(channelName)
    if folderID is not None:
      return cls(folderID, fromFolderID=True)

  @classmethod
  def RemoveNthTrajectory(cls, trajectoryNumber):
    folderID = cls.GetFolderIDForNthTrajectory(trajectoryNumber)
    if folderID is not None:
      shNode = slicer.mrmlScene.GetSubjectHierarchyNode()
      shNode.RemoveItemChildren(folderID)
      shNode.RemoveItem(folderID)

  @staticmethod
  def GetFolderIDForNthTrajectory(N):
    shNode = slicer.mrmlScene.GetSubjectHierarchyNode()
    vtk_ids = vtk.vtkIdList()
    shNode.GetItemChildren(shNode.GetSceneItemID(), vtk_ids)
    IDs = [vtk_ids.GetId(i) for i in range(vtk_ids.GetNumberOfIds())]
    for ID in IDs:
      if 'LeadORTrajectory' in shNode.GetItemAttributeNames(ID):
        if int(shNode.GetItemAttribute(ID, 'LeadORTrajectory')) == N:
          return ID
  
  @staticmethod
  def GetFolderIDForChannelName(channelName):
    shNode = slicer.mrmlScene.GetSubjectHierarchyNode()
    vtk_ids = vtk.vtkIdList()
    shNode.GetItemChildren(shNode.GetSceneItemID(), vtk_ids)
    IDs = [vtk_ids.GetId(i) for i in range(vtk_ids.GetNumberOfIds())]
    for ID in IDs:
      if 'LeadORTrajectory' in shNode.GetItemAttributeNames(ID):
        if shNode.GetItemAttribute(ID, 'ChannelName') == channelName:
          return ID


#
# VTA
#


class VTASource():

  def __init__(self):

    self.sphereSource = self.createSphereSource()
    self.sphereFunction = self.createSphereFunction()
    self.ROINode = self.createROI()
    self.VTAModel = self.createVTAModel()
    self.markupsNode = self.createMarkups()
    self.setFibersVisibility(True)

  def SetRadius(self, r):
    self.sphereSource.SetRadius(r)
    self.sphereSource.Update()
    self.sphereFunction.SetRadius(r)
    # fiberBundleNode = slicer.mrmlScene.GetFirstNodeByClass('vtkMRMLFiberBundleNode')
    # if fiberBundleNode:
      # fiberBundleNode.InvokeCustomModifiedEvent(slicer.vtkMRMLModelNode.MeshModifiedEvent)

  def SetAndObserveTransformNodeID(self, transformNodeID):
    for node in [self.markupsNode, self.VTAModel]:
      node.SetAndObserveTransformNodeID(transformNodeID)
    slicer.util.getNode(transformNodeID).AddObserver(slicer.vtkMRMLTransformNode.TransformModifiedEvent, lambda c,e: self.transformModified())
    self.transformModified()
    
  def transformModified(self):
    p = [0]*3
    self.markupsNode.GetNthControlPointPositionWorld(0,p)
    self.sphereFunction.SetCenter(p)
    # fiberBundleNode = slicer.mrmlScene.GetFirstNodeByClass('vtkMRMLFiberBundleNode')
    # if fiberBundleNode:
      # fiberBundleNode.InvokeCustomModifiedEvent(slicer.vtkMRMLModelNode.MeshModifiedEvent)

  def createMarkups(self):
    markupsNode = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLMarkupsFiducialNode')
    markupsNode.AddFiducialFromArray([0,0,3])
    markupsNode.SetDisplayVisibility(0)
    return markupsNode

  def createSphereSource(self):
    sphereSource = vtk.vtkSphereSource()
    sphereSource.SetCenter(0,0,3)
    sphereSource.SetPhiResolution(12)
    sphereSource.SetThetaResolution(12)
    return sphereSource

  def createSphereFunction(self):
    sphereFun = vtk.vtkSphere()
    return sphereFun

  def createROI(self):
    ROINode = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLAnnotationROINode')
    ROINode.SetDisplayVisibility(0)
    return ROINode

  def createVTAModel(self):
    stimulationVTAModel = slicer.modules.models.logic().AddModel(self.sphereSource.GetOutput())
    stimulationVTAModel.CreateDefaultSequenceDisplayNodes()
    stimulationVTAModel.CreateDefaultDisplayNodes()
    stimulationVTAModel.GetDisplayNode().SetColor(0.8,0.1,0.1)
    stimulationVTAModel.GetDisplayNode().SetOpacity(0.8)
    stimulationVTAModel.GetDisplayNode().SetVisibility2D(1)
    return stimulationVTAModel

  def setFibersVisibility(self, state):
    if slicer.mrmlScene.GetNumberOfNodesByClass('vtkMRMLFiberBundleNode'):
      fiberBundleNode = slicer.mrmlScene.GetFirstNodeByClass('vtkMRMLFiberBundleNode')
      fiberBundleNode.SetAndObserveAnnotationNodeID(self.ROINode.GetID())
      fiberBundleNode.SetSelectWithAnnotation(True)
      fiberBundleNode.GetDisplayNode().SetVisibility(state)
      fiberBundleNode.GetExtractFromROI().SetImplicitFunction(self.sphereFunction)

  def cleanup(self):
    self.setFibersVisibility(False)
    slicer.mrmlScene.RemoveNode(self.ROINode)
    slicer.mrmlScene.RemoveNode(self.VTAModel)
    slicer.mrmlScene.RemoveNode(self.markupsNode)