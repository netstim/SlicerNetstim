import vtk, qt, slicer
import os, sys, shutil
from scipy import io
import numpy as np
from subprocess import call
import json
import glob

from . import GridNodeHelper

import ImportAtlas

def checkExtensionInstall(extensionName):
  em = slicer.app.extensionsManagerModel()
  if not em.isExtensionInstalled(extensionName):
    extensionMetaData = em.retrieveExtensionMetadataByName(extensionName)
    url = os.path.join(em.serverUrl().toString(), 'download', 'item', extensionMetaData['item_id'])
    extensionPackageFilename = os.path.join(slicer.app.temporaryPath, extensionMetaData['md5'])
    slicer.util.downloadFile(url, extensionPackageFilename)
    em.installExtension(extensionPackageFilename)
    qt.QMessageBox.information(qt.QWidget(), '', 'Slicer will install %s and quit.\nPlease restart.' % extensionName)
    slicer.util.exit()
    return True

class LeadFileManager():
  def __init__(self, subjectPath):
    self.subjectPath = subjectPath
    self.subjectID = os.path.split(self.subjectPath)[-1]
    self.useBIDS = os.path.isdir(os.path.join(self.subjectPath,'preprocessing'))
  
  def getNormalizationMethod(self):
    if self.useBIDS:
      return os.path.join(self.getNormalizationPath(), 'log', self.subjectID + '_desc-normmethod.json')
    else:
      return os.path.join(self.subjectPath,'ea_coreg_approved.mat')

  def getCoregImages(self, modality='*'):
    if self.useBIDS:
      modality = self.subjectID + '*ses-preop_acq-*_' + modality if modality=='*' else modality
      return glob.glob(os.path.join(self.subjectPath, 'coregistration', 'anat', modality + '.nii'))
    else:
      modality = 'anat_' + modality if modality == '*' else modality
      return glob.glob(os.path.join(self.subjectPath, modality + '.nii'))

  def getNormalizedImages(self):
    if self.useBIDS:
      return glob.glob(os.path.join(self.subjectPath, 'normalization', 'anat', self.subjectID + '*ses-preop*.nii'))
    else:
      return glob.glob(os.path.join(self.subjectPath, 'glanat*.nii'))

  def getANTSForwardWarp(self):
    if self.useBIDS:
      return os.path.join(self.getNormalizationPath(), 'transformations', self.subjectID + '_from-anchorNative_to-MNI152NLin2009bAsym_desc-ants.nii.gz')
    else:
      return os.path.join(self.subjectPath, 'glanatComposite.nii.gz')

  def getANTSInverseWarp(self):
    if self.useBIDS:
      return os.path.join(self.getNormalizationPath(), 'transformations', self.subjectID + '_from-MNI152NLin2009bAsym_to-anchorNative_desc-ants.nii.gz')
    else:
      return os.path.join(self.subjectPath, 'glanatInverseComposite.nii.gz')
    
  def getNormalizationPath(self):
    return os.path.join(self.subjectPath, 'normalization')

  def getWarpDrivePath(self):
    return os.path.join(self.subjectPath, 'warpdrive')


def saveApprovedDataJSON(normalizationMethodFile):
  with open(normalizationMethodFile, 'a+') as f:
    normalizationMethod = json.load(f)
    normalizationMethod['approval'] = 1
    f.seek(0)
    json.dump(normalizationMethod, f)
    f.truncate()

def saveApprovedDataLegacy(normalizationMethodFile):
  try:
    import h5py
  except:
    slicer.util.pip_install('h5py')
    import h5py
  try:
    import hdf5storage
  except:
    slicer.util.pip_install('hdf5storage')
    import hdf5storage

  matfiledata = {}
  if os.path.isfile(normalizationMethodFile):
    try:
      # read file and copy data except for glanat
      with h5py.File(normalizationMethodFile,'r') as f:
        for k in f.keys():
          if k != 'glanat':
            keyValue = f[k][()]
            matfiledata[k] = keyValue
      # now add approved glanat
      matfiledata[u'glanat'] = np.array([2])

    except: # use other reader for .mat file
      f = io.loadmat(normalizationMethodFile)
      for k in f.keys():
        if k != 'glanat':
          keyValue = f[k]
          matfiledata[k] = keyValue
      matfiledata['glanat'] = np.array([[2]],dtype='uint8')
      io.savemat(normalizationMethodFile,matfiledata)
      return

  else:
    matfiledata[u'glanat'] = np.array([2])

  # save
  # for some reason putting subject path into hdf5storage.write doesnt work
  currentDir = os.getcwd()
  os.chdir(os.path.dirname(normalizationMethodFile))
  hdf5storage.write(matfiledata, '.', 'ea_coreg_approved.mat', matlab_compatible=True)
  os.chdir(currentDir)


def saveApprovedData(subjectPath):
  normalizationMethodFile = LeadFileManager(subjectPath).getNormalizationMethod()
  if normalizationMethodFile.endswith('json'):
    saveApprovedDataJSON(normalizationMethodFile)
  else:
    saveApprovedDataLegacy(normalizationMethodFile)


def loadSubjectTransform(subjectPath, antsApplyTransformsPath):

  transformPath = LeadFileManager(subjectPath).getANTSForwardWarp()

  # update subject warp fields to new lead dbs specification
  if os.path.isfile(transformPath.replace('.nii.gz','.h5')):
    updateTranform(subjectPath, antsApplyTransformsPath)

  # load glanat composite
  glanatCompositeNode = slicer.util.loadTransform(transformPath)
  
  return glanatCompositeNode

def updateTranform(directory, antsApplyTransformsPath):
  bidsSubject = LeadFileManager(directory)
  transforms = [bidsSubject.getANTSForwardWarp(), bidsSubject.getANTSInverseWarp()]
  references = [bidsSubject.getNormalizedImages()[0], bidsSubject.getCoregImages()[0]]
  for transform,reference in zip(transforms,references):
    transformFullPath = os.path.join(directory,transform + '.h5') # in case inverse doesnt exist
    if os.path.isfile(transformFullPath):
      h5transform = transform.replace('.nii.gz','.h5')
      command = antsApplyTransformsPath + " -r " + reference + " -t " + h5transform + " -o [" + transform + ",1] -v 1"
      commandOut = call(command, env=slicer.util.startupEnvironment(), shell=True) # run antsApplyTransforms
      os.remove(h5transform)
  return True
  
def queryUserApproveSubject(subjectPath):
  msgBox = qt.QMessageBox()
  msgBox.setText('No corrections made')
  msgBox.setInformativeText('Save subject as approved?')
  msgBox.setStandardButtons(qt.QMessageBox().Save | qt.QMessageBox().Discard | qt.QMessageBox().Cancel)
  ret = msgBox.exec_()
  if ret == qt.QMessageBox().Cancel:
    return False
  if ret == qt.QMessageBox().Save:
    saveApprovedData(subjectPath)
  return True

def applyChanges(subjectPath, inputNode, imageNode):

  qt.QApplication.setOverrideCursor(qt.Qt.WaitCursor)
  qt.QApplication.processEvents()
  
  # undo changes to image node
  imageNode.SetAndObserveTransformNodeID(None)

  # FORWARD
  
  size, origin, spacing = GridNodeHelper.getGridDefinition(inputNode)
  # harden changes in input
  inputNode.HardenTransform()
  # to grid transform
  outNode = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLTransformNode')
  referenceVolume = GridNodeHelper.emptyVolume(size, origin, spacing)    
  slicer.modules.transforms.logic().ConvertToGridTransform(inputNode, referenceVolume, outNode)
  # set to input and delete aux
  inputNode.SetAndObserveTransformFromParent(outNode.GetTransformFromParent())
  slicer.mrmlScene.RemoveNode(outNode)
  slicer.mrmlScene.RemoveNode(referenceVolume)
  # save
  slicer.util.saveNode(inputNode, LeadFileManager(subjectPath).getANTSForwardWarp())

  # BACKWARD

  inputNode.Inverse()
  # to grid
  outNode = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLTransformNode')
  slicer.modules.transforms.logic().ConvertToGridTransform(inputNode, imageNode, outNode)
  # save
  slicer.util.saveNode(outNode, LeadFileManager(subjectPath).getANTSInverseWarp())
  # delete aux node
  slicer.mrmlScene.RemoveNode(outNode)
  
  # back to original
  inputNode.Inverse()
  imageNode.SetAndObserveTransformNodeID(inputNode.GetID())
  
  qt.QApplication.setOverrideCursor(qt.QCursor(qt.Qt.ArrowCursor))


def setTargetFiducialsAsFixed():
  shNode = slicer.mrmlScene.GetSubjectHierarchyNode()
  fiducialNodes = slicer.mrmlScene.GetNodesByClass('vtkMRMLMarkupsFiducialNode')
  fiducialNodes.UnRegister(slicer.mrmlScene)
  for i in range(fiducialNodes.GetNumberOfItems()):
    fiducialNode = fiducialNodes.GetItemAsObject(i)
    if 'target' in shNode.GetItemAttributeNames(shNode.GetItemByDataNode(fiducialNode)):
      # get parent folder
      parentFolder = shNode.GetItemDataNode(shNode.GetItemParent(shNode.GetItemByDataNode(fiducialNode)))
      parentFolderName = parentFolder.GetName()
      # remove target attribute
      shNode.RemoveItemAttribute(shNode.GetItemByDataNode(fiducialNode), 'target')
      # add as fixed point
      # WarpDriveUtil.addFixedPoint(fiducialNode)
      # remove correction
      removeNodeAndChildren(parentFolder)
      # change fixed point name
      fiducialNode.SetName(parentFolderName)

def saveSourceTarget(subjectPath, sourceNode, targetNode):
  """
  Save source and target in subject directory so will be loaded next time
  """
  warpDriveSavePath = LeadFileManager(subjectPath).getWarpDrivePath()
  if not os.path.isdir(warpDriveSavePath):
    os.mkdir(warpDriveSavePath)  
  slicer.util.saveNode(sourceNode, os.path.join(warpDriveSavePath, 'source.json'))
  slicer.util.saveNode(targetNode, os.path.join(warpDriveSavePath, 'target.json'))

def getAtlasesNamesInScene():
  shNode = slicer.mrmlScene.GetSubjectHierarchyNode()
  folderNodes = slicer.mrmlScene.GetNodesByClass('vtkMRMLFolderDisplayNode')
  folderNodes.UnRegister(slicer.mrmlScene)
  names = []
  for i in range(folderNodes.GetNumberOfItems()):
    folderNode = folderNodes.GetItemAsObject(i)
    if 'atlas' in shNode.GetItemAttributeNames(shNode.GetItemByDataNode(folderNode)):
      if  shNode.GetItemParent(shNode.GetItemByDataNode(folderNode)) == shNode.GetSceneItemID():
        names.append(folderNode.GetName())
  return names

def saveSceneInfo(subjectPath):
  warpDriveSavePath = LeadFileManager(subjectPath).getWarpDrivePath()
  info = {}
  info["atlasNames"] = getAtlasesNamesInScene()
  with open(os.path.join(warpDriveSavePath,'info.json'), 'w') as jsonFile:
    json.dump(info, jsonFile)


def DeleteCorrections():
  shNode = slicer.mrmlScene.GetSubjectHierarchyNode()
  # delete folders
  folderNodes = slicer.mrmlScene.GetNodesByClass('vtkMRMLFolderDisplayNode')
  folderNodes.UnRegister(slicer.mrmlScene)
  for i in range(folderNodes.GetNumberOfItems()):
    folderNode = folderNodes.GetItemAsObject(i)
    if 'correction' in shNode.GetItemAttributeNames(shNode.GetItemByDataNode(folderNode)):
      removeNodeAndChildren(folderNode)

def removeNodeAndChildren(node):
  # get subject hierarchy node ID
  shNode = slicer.mrmlScene.GetSubjectHierarchyNode()
  nodeID = shNode.GetItemByDataNode(node)
  # get children
  removeIDs = vtk.vtkIdList()
  shNode.GetItemChildren(nodeID, removeIDs, True)
  # add selected ID
  removeIDs.InsertNextId(nodeID)
  # remove
  for i in range(removeIDs.GetNumberOfIds()):
    shNode.RemoveItem(removeIDs.GetId(i))