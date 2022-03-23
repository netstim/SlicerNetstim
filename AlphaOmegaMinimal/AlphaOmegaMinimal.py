import logging
import os

import vtk
import qt

import slicer
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin

from math import nan

#
# AlphaOmegaMinimal
#

class AlphaOmegaMinimal(ScriptedLoadableModule):
  """Uses ScriptedLoadableModule base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "AlphaOmega Minimal"
    self.parent.categories = ["Netstim"]
    self.parent.dependencies = []
    self.parent.contributors = ["Simon Oxenford (Charite Berlin)"]
    self.parent.helpText = """
Implementation of AlphaOmega communication using pip installable python wrapper
"""
    self.parent.acknowledgementText = ""

#
# AlphaOmegaMinimalWidget
#

class AlphaOmegaMinimalWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
  """Uses ScriptedLoadableModuleWidget base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent=None):
    """
    Called when the user opens the module the first time and the widget is initialized.
    """
    ScriptedLoadableModuleWidget.__init__(self, parent)
    VTKObservationMixin.__init__(self)  # needed for parameter node observation
    self.logic = None
    self._parameterNode = None
    self._updatingGUIFromParameterNode = False
    self.updateNeuroOmegaInstallStatus()

  def setup(self):
    """
    Called when the user opens the module the first time and the widget is initialized.
    """
    ScriptedLoadableModuleWidget.setup(self)

    # Load widget from .ui file (created by Qt Designer).
    # Additional widgets can be instantiated manually and added to self.layout.
    uiWidget = slicer.util.loadUI(self.resourcePath('UI/AlphaOmegaMinimal.ui'))
    self.layout.addWidget(uiWidget)
    self.ui = slicer.util.childWidgetVariables(uiWidget)
    self.ui.wheelsPathLineEdit.currentPath = os.path.expanduser('~')

    # Set scene in MRML widgets. Make sure that in Qt designer the top-level qMRMLWidget's
    # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's.
    # "setMRMLScene(vtkMRMLScene*)" slot.
    uiWidget.setMRMLScene(slicer.mrmlScene)

    # Create logic class. Logic implements all computations that should be possible to run
    # in batch mode, without a graphical user interface.
    self.logic = AlphaOmegaMinimalLogic()

    # Connections

    # These connections ensure that we update parameter node when scene is closed
    self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
    self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

    # These connections ensure that whenever user changes some settings on the GUI, that is saved in the MRML scene
    # (in the selected parameter node).
    self.ui.outputTransformSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI)

    # Buttons
    self.ui.wheelsPathLineEdit.currentPathChanged.connect(lambda p: self.onWheelsPathChanged(p))
    self.ui.connectButton.connect('clicked(bool)', self.onConnectButton)

    # Make sure parameter node is initialized (needed for module reload)
    self.initializeParameterNode()

    # qt timer for depth update
    self._timer = qt.QTimer()
    self._timer.timeout.connect(lambda: self.onTimerTimeout())
    self._timer.start(1000)

  def cleanup(self):
    """
    Called when the application closes and the module widget is destroyed.
    """
    self.removeObservers()

  def enter(self):
    """
    Called each time the user opens this module.
    """
    # Make sure parameter node exists and observed
    self.initializeParameterNode()

  def exit(self):
    """
    Called each time the user opens a different module.
    """
    # Do not react to parameter node changes (GUI wlil be updated when the user enters into the module)
    self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)

  def onSceneStartClose(self, caller, event):
    """
    Called just before the scene is closed.
    """
    # Parameter node will be reset, do not use it anymore
    self.setParameterNode(None)

  def onSceneEndClose(self, caller, event):
    """
    Called just after the scene is closed.
    """
    # If this module is shown while the scene is closed then recreate a new parameter node immediately
    if self.parent.isEntered:
      self.initializeParameterNode()

  def initializeParameterNode(self):
    """
    Ensure parameter node exists and observed.
    """
    # Parameter node stores all user choices in parameter values, node selections, etc.
    # so that when the scene is saved and reloaded, these settings are restored.

    self.setParameterNode(self.logic.getParameterNode())

  def setParameterNode(self, inputParameterNode):
    """
    Set and observe parameter node.
    Observation is needed because when the parameter node is changed then the GUI must be updated immediately.
    """

    if inputParameterNode:
      self.logic.setDefaultParameters(inputParameterNode)

    # Unobserve previously selected parameter node and add an observer to the newly selected.
    # Changes of parameter node are observed so that whenever parameters are changed by a script or any other module
    # those are reflected immediately in the GUI.
    if self._parameterNode is not None:
      self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)
    self._parameterNode = inputParameterNode
    if self._parameterNode is not None:
      self.addObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)

    # Initial GUI update
    self.updateGUIFromParameterNode()

  def updateGUIFromParameterNode(self, caller=None, event=None):
    """
    This method is called whenever parameter node is changed.
    The module GUI is updated to show the current state of the parameter node.
    """

    if self._parameterNode is None or self._updatingGUIFromParameterNode:
      return

    # Make sure GUI changes do not call updateParameterNodeFromGUI (it could cause infinite loop)
    self._updatingGUIFromParameterNode = True

    # Update node selectors and sliders
    self.ui.outputTransformSelector.setCurrentNode(self._parameterNode.GetNodeReference("OutputTransform"))
    self.ui.systemMACLineEdit.text = self._parameterNode.GetParameter("SystemMAC")

    # Enable / disable parts of the GUI
    self.ui.sdkCollapsibleButton.enabled = not self._neuro_omega_installed
    self.ui.sdkCollapsibleButton.collapsed = self._neuro_omega_installed
    self.ui.sdkCollapsibleButton.text = "SDK installed" if self._neuro_omega_installed else "SDK required"
    self.ui.connectionCollapsibleButton.enabled = self._neuro_omega_installed
    self.ui.driveCollapsibleButton.enabled = self._neuro_omega_installed

    # All the GUI updates are done
    self._updatingGUIFromParameterNode = False

  def updateParameterNodeFromGUI(self, caller=None, event=None):
    """
    This method is called when the user makes any change in the GUI.
    The changes are saved into the parameter node (so that they are restored when the scene is saved and loaded).
    """

    if self._parameterNode is None or self._updatingGUIFromParameterNode:
      return

    wasModified = self._parameterNode.StartModify()  # Modify all properties in a single batch

    self._parameterNode.SetNodeReferenceID("OutputTransform", self.ui.outputTransformSelector.currentNodeID)
    self._parameterNode.SetParameter("SystemMAC", self.ui.systemMACLineEdit.text)

    self._parameterNode.EndModify(wasModified)

  def onWheelsPathChanged(self, wheelsPath):
    try:
      slicer.util.pip_install(wheelsPath)
    except:
      print("Couldn't install the provided wheels: %s" % wheelsPath)
    self.updateNeuroOmegaInstallStatus()
    self.updateGUIFromParameterNode()

  def updateNeuroOmegaInstallStatus(self):
    try:
      import neuro_omega
      self._neuro_omega_installed = True
    except:
      self._neuro_omega_installed = False

  def onConnectButton(self):
    if self.ui.connectButton.text == 'Connect':
      with slicer.util.tryWithErrorDisplay("Failed to connect.", waitCursor=True):
        self.logic.connectDevice(self.ui.systemMACLineEdit.text)
    else:
      self.logic.disconnectDevice()
    self.ui.connectButton.text == 'Disconnect' if self.logic.getDeviceIsConnected() else 'Connect'    

  def onTimerTimeout(self):
    if self.logic._neuro_omega_device is not None:
      dtt = self.logic._neuro_omega_device.getDriveDistanceToTargetMiliM()
      self.ui.distanceToTargetLabel.text = str(dtt)
      transformNode = self.ui.outputTransformSelector.currentNode()
      if transformNode and dtt != nan:
        transformNode.GetMatrixTransformToParent().SetElement(2,3,dtt)

#
# AlphaOmegaMinimalLogic
#

class AlphaOmegaMinimalLogic(ScriptedLoadableModuleLogic):
  """This class should implement all the actual
  computation done by your module.  The interface
  should be such that other python code can import
  this class and make use of the functionality without
  requiring an instance of the Widget.
  Uses ScriptedLoadableModuleLogic base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self):
    """
    Called when the logic class is instantiated. Can be used for initializing member variables.
    """
    ScriptedLoadableModuleLogic.__init__(self)
    self._neuro_omega_device = None

  def setDefaultParameters(self, parameterNode):
    """
    Initialize parameter node with default settings.
    """
    if not parameterNode.GetParameter("SystemMAC"):
      parameterNode.SetParameter("SystemMAC", "AA:BB:CC:DD:EE:FF")

  def initializeDeviceIfNeeded(self):
    if self._neuro_omega_device is None:
      from neuro_omega import neuro_omega_utils
      self._neuro_omega_device = neuro_omega_utils.Device()

  def getDeviceIsConnected(self):
    self.initializeDeviceIfNeeded()
    return self._neuro_omega_device.isConnected()

  def connectDevice(self, systemMAC):
    if not self.getDeviceIsConnected():
      self._neuro_omega_device.startConnection(systemMAC)

  def getDeviceDriveDistanceToTarget(self):
    self.initializeDeviceIfNeeded()
    return self._neuro_omega_device.getDriveDistanceToTargetMiliM()


#
# AlphaOmegaMinimalTest
#

class AlphaOmegaMinimalTest(ScriptedLoadableModuleTest):
  """
  This is the test case for your scripted module.
  Uses ScriptedLoadableModuleTest base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def setUp(self):
    """ Do whatever is needed to reset the state - typically a scene clear will be enough.
    """
    slicer.mrmlScene.Clear()

  def runTest(self):
    """Run as few or as many tests as needed here.
    """
    self.setUp()
    self.test_AlphaOmegaMinimal1()

  def test_AlphaOmegaMinimal1(self):
    """ Ideally you should have several levels of tests.  At the lowest level
    tests should exercise the functionality of the logic with different inputs
    (both valid and invalid).  At higher levels your tests should emulate the
    way the user would interact with your code and confirm that it still works
    the way you intended.
    One of the most important features of the tests is that it should alert other
    developers when their changes will have an impact on the behavior of your
    module.  For example, if a developer removes a feature that you depend on,
    your test should break so they know that the feature is needed.
    """

    self.delayDisplay("Starting the test")

    # Get/create input data

    # import SampleData
    # registerSampleData()
    # inputVolume = SampleData.downloadSample('AlphaOmegaMinimal1')
    # self.delayDisplay('Loaded test data set')

    # inputScalarRange = inputVolume.GetImageData().GetScalarRange()
    # self.assertEqual(inputScalarRange[0], 0)
    # self.assertEqual(inputScalarRange[1], 695)

    # outputVolume = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode")
    # threshold = 100

    # # Test the module logic

    # logic = AlphaOmegaMinimalLogic()

    # # Test algorithm with non-inverted threshold
    # logic.process(inputVolume, outputVolume, threshold, True)
    # outputScalarRange = outputVolume.GetImageData().GetScalarRange()
    # self.assertEqual(outputScalarRange[0], inputScalarRange[0])
    # self.assertEqual(outputScalarRange[1], threshold)

    # # Test algorithm with inverted threshold
    # logic.process(inputVolume, outputVolume, threshold, False)
    # outputScalarRange = outputVolume.GetImageData().GetScalarRange()
    # self.assertEqual(outputScalarRange[0], inputScalarRange[0])
    # self.assertEqual(outputScalarRange[1], inputScalarRange[1])

    self.delayDisplay('Test passed')
