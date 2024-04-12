import logging
import os
import json

import vtk
import qt,ctk
import slicer
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin

import numpy as np

from CurveToBundleLib.Widgets.multiHandleSlider import MultiHandleSliderWidget
from CurveToBundleLib.Widgets.multiModelSelector import MultiModelSelectorWidget

#
# CurveToBundle
#

class CurveToBundle(ScriptedLoadableModule):
    """Uses ScriptedLoadableModule base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = "CurveToBundle"  # TODO: make this more human readable by adding spaces
        self.parent.categories = ["Netstim"]  # TODO: set categories (folders where the module shows up in the module selector)
        self.parent.dependencies = []  # TODO: add here list of module names that this module requires
        self.parent.contributors = ["Simon Oxenford (Charite Berlin)"]  # TODO: replace with "Firstname Lastname (Organization)"
        # TODO: update with short description of the module and a link to online module documentation
        self.parent.helpText = ""
        # TODO: replace with organization, grant and thanks
        self.parent.acknowledgementText = ""


#
# CurveToBundleWidget
#

class CurveToBundleWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
    """Uses ScriptedLoadableModuleWidget base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
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

    def setup(self):
        """
        Called when the user opens the module the first time and the widget is initialized.
        """
        ScriptedLoadableModuleWidget.setup(self)

        # Load widget from .ui file (created by Qt Designer).
        # Additional widgets can be instantiated manually and added to self.layout.
        uiWidget = slicer.util.loadUI(self.resourcePath('UI/CurveToBundle.ui'))
        self.layout.addWidget(uiWidget)
        self.ui = slicer.util.childWidgetVariables(uiWidget)

        self.ui.parameterNodeSelector.addAttribute("vtkMRMLScriptedModuleNode", "ModuleName", self.moduleName)

        self.ui.duplicateParameterSetToolButton.setIcon(qt.QIcon(":/Icons/Small/SlicerEditCopy.png"))
        self.ui.duplicateParameterSetToolButton.connect('clicked()', self.onDuplicateParameterSet)

        # Waypoints slider widget
        self.ui.waypointsValueWidget = MultiHandleSliderWidget()
        waypointsLayout = qt.QVBoxLayout(self.ui.waypointsFrame)
        waypointsLayout.addWidget(self.ui.waypointsValueWidget)

        # Spread settings
        spreadSettingsMenu = qt.QMenu(self.ui.spreadSettingsToolButton)

        modifyMenu = spreadSettingsMenu.addMenu("Modify")
        self.ui.spreadModifyActionsGroup = qt.QActionGroup(modifyMenu)
        self.ui.spreadModifyActionsGroup.setExclusive(True)
        for kind in ['Selected', 'All']:
            action = qt.QAction(kind, modifyMenu)
            action.setCheckable(True)
            self.ui.spreadModifyActionsGroup.addAction(action)
        modifyMenu.addActions(self.ui.spreadModifyActionsGroup.actions())
        
        self.ui.maxSpreadSpinBox = qt.QSpinBox()
        self.ui.maxSpreadSpinBox.minimum = 1
        self.ui.maxSpreadSpinBox.maximum = 100
        self.ui.maxSpreadSpinBox.value = 10
        maxSpreadMenu = spreadSettingsMenu.addMenu("Max spread")
        action = qt.QWidgetAction(maxSpreadMenu)
        action.setDefaultWidget(self.ui.maxSpreadSpinBox)
        maxSpreadMenu.addAction(action)

        splineOrderMenu = spreadSettingsMenu.addMenu("Spline order")
        self.ui.splineOrderActionsGroup = qt.QActionGroup(splineOrderMenu)
        self.ui.splineOrderActionsGroup.setExclusive(True)
        for order in range(1,6):
            action = qt.QAction(str(order), splineOrderMenu)
            action.setCheckable(True)
            self.ui.splineOrderActionsGroup.addAction(action)
        splineOrderMenu.addActions(self.ui.splineOrderActionsGroup.actions())
        
        self.ui.spreadExtrapolateAction = qt.QAction("Extrapolate bounds", spreadSettingsMenu)
        self.ui.spreadExtrapolateAction.setCheckable(True)
        self.ui.spreadExtrapolateAction.setChecked(True)
        spreadSettingsMenu.addAction(self.ui.spreadExtrapolateAction)

        self.ui.spreadSettingsToolButton.setMenu(spreadSettingsMenu)
        self.ui.spreadSettingsToolButton.setIcon(qt.QIcon(":/Icons/Small/SlicerConfigure.png"))

        # Waypoints
        updateWaypointsMenu = qt.QMenu(self.ui.updateWaypointsToolButton)

        self.ui.resetWaypointsAction = qt.QAction("Reset", updateWaypointsMenu)
        updateWaypointsMenu.addAction(self.ui.resetWaypointsAction)

        self.ui.uShapeAction = qt.QAction("U shape", updateWaypointsMenu)
        updateWaypointsMenu.addAction(self.ui.uShapeAction)

        self.ui.copyPositionMenu = updateWaypointsMenu.addMenu("Copy position from curve")
        self.ui.copyPositionActionGroup = qt.QActionGroup(self.ui.copyPositionMenu)
        
        self.ui.updateWaypointsToolButton.setMenu(updateWaypointsMenu)
        self.ui.updateWaypointsToolButton.setIcon(qt.QIcon(":/Icons/Small/SlicerCheckForUpdates.png"))

        # Constraints
        self.ui.insideModelsSelector = MultiModelSelectorWidget()
        self.ui.constraintsCollapsibleButton.layout().addRow("Inside", self.ui.insideModelsSelector)

        self.ui.outsideModelsSelector = MultiModelSelectorWidget()
        self.ui.constraintsCollapsibleButton.layout().addRow("Outside", self.ui.outsideModelsSelector)

        # Save as trk
        saveAsTrkMenu = qt.QMenu(self.ui.saveAsTrkToolButton)

        saveReferenceMenu = saveAsTrkMenu.addMenu("Reference")
        self.ui.saveReferenceVolumeComboBox = slicer.qMRMLNodeComboBox()
        self.ui.saveReferenceVolumeComboBox.nodeTypes = ["vtkMRMLScalarVolumeNode"]
        self.ui.saveReferenceVolumeComboBox.selectNodeUponCreation = False
        self.ui.saveReferenceVolumeComboBox.addEnabled = False
        self.ui.saveReferenceVolumeComboBox.removeEnabled = False
        self.ui.saveReferenceVolumeComboBox.noneEnabled = True
        self.ui.saveReferenceVolumeComboBox.showHidden = False
        self.ui.saveReferenceVolumeComboBox.showChildNodeTypes = False
        self.ui.saveReferenceVolumeComboBox.setMRMLScene(slicer.mrmlScene)
        action = qt.QWidgetAction(saveReferenceMenu)
        action.setDefaultWidget(self.ui.saveReferenceVolumeComboBox)
        saveReferenceMenu.addAction(action)

        saveAsTrkAction = qt.QAction("Save as .trk", self.ui.saveAsTrkToolButton)
        saveAsTrkAction.setToolTip("Save the output as .trk file")
        saveAsTrkAction.connect('triggered()', self.onSaveAsTrk)
        self.ui.saveAsTrkToolButton.setDefaultAction(saveAsTrkAction)
        self.ui.saveAsTrkToolButton.setMenu(saveAsTrkMenu)
        self.ui.saveAsTrkToolButton.setIcon(qt.QIcon(":/Icons/Small/SlicerSave.png"))

        # Fibers settings
        fibersSettingsMenu = qt.QMenu(self.ui.fibersSettingsToolButton)

        fibersSampleTypeMenu = fibersSettingsMenu.addMenu("Sample type")
        self.ui.fibersSampleTypeActionsGroup = qt.QActionGroup(fibersSampleTypeMenu)
        self.ui.fibersSampleTypeActionsGroup.setExclusive(True)
        for kind in ['uniform', 'normal']:
            action = qt.QAction(kind, fibersSampleTypeMenu)
            action.setCheckable(True)
            self.ui.fibersSampleTypeActionsGroup.addAction(action)
        action.setChecked(True)
        fibersSampleTypeMenu.addActions(self.ui.fibersSampleTypeActionsGroup.actions())

        sineCyclesMenu = fibersSettingsMenu.addMenu("Sine Cycles")
        self.ui.sineCyclesSlider = ctk.ctkSliderWidget()
        self.ui.sineCyclesSlider.minimum = 0
        self.ui.sineCyclesSlider.maximum = 10
        self.ui.sineCyclesSlider.value = 2
        self.ui.sineCyclesSlider.singleStep = 0.1
        action = qt.QWidgetAction(sineCyclesMenu)
        action.setDefaultWidget(self.ui.sineCyclesSlider)
        sineCyclesMenu.addAction(action)

        self.ui.fibersSettingsToolButton.setMenu(fibersSettingsMenu)
        self.ui.fibersSettingsToolButton.setIcon(qt.QIcon(":/Icons/Small/SlicerConfigure.png"))


        # Set scene in MRML widgets. Make sure that in Qt designer the top-level qMRMLWidget's
        # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's.
        # "setMRMLScene(vtkMRMLScene*)" slot.
        uiWidget.setMRMLScene(slicer.mrmlScene)

        # Create logic class. Logic implements all computations that should be possible to run
        # in batch mode, without a graphical user interface.
        self.logic = CurveToBundleLogic()

        # Connections

        # These connections ensure that we update parameter node when scene is closed
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)
        self.parent.connect('mrmlSceneChanged(vtkMRMLScene*)', self.ui.saveReferenceVolumeComboBox, 'setMRMLScene(vtkMRMLScene*)')

        self.ui.parameterNodeSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.setParameterNode)
        self.ui.inputSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.inpuNodeChanged)

        # These connections ensure that whenever user changes some settings on the GUI, that is saved in the MRML scene
        # (in the selected parameter node).
        self.ui.inputSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI)
        self.ui.betweenCurveSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI)
        self.ui.outputSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI)
        self.ui.startModelSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI)
        self.ui.endModelSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI)
        self.ui.insideModelsSelector.checkedIndexesChanged.connect(self.updateParameterNodeFromGUI)
        self.ui.outsideModelsSelector.checkedIndexesChanged.connect(self.updateParameterNodeFromGUI)
        self.ui.numberOfFibersSliderWidget.connect("valueChanged(double)", self.updateParameterNodeFromGUI)
        self.ui.maxSpreadSpinBox.connect("valueChanged(int)", self.updateParameterNodeFromGUI)
        self.ui.splineOrderActionsGroup.connect("triggered(QAction*)", self.updateParameterNodeFromGUI)
        self.ui.spreadExtrapolateAction.connect("toggled(bool)", self.updateParameterNodeFromGUI)
        self.ui.fibersSampleTypeActionsGroup.connect("triggered(QAction*)", self.updateParameterNodeFromGUI)
        self.ui.spreadModifyActionsGroup.connect("triggered(QAction*)", self.updateParameterNodeFromGUI)
        self.ui.sineCyclesSlider.connect("valueChanged(double)", self.updateParameterNodeFromGUI)

        self.ui.waypointSpreadSlider.connect("valueChanged(double)", self.updateSpreadsFromSlider)

        # Buttons
        self.ui.applyButton.connect('clicked(bool)', self.onApplyButton)
        self.ui.resetWaypointsAction.triggered.connect(lambda b,a=self.ui.resetWaypointsAction: self.updateWaypoints(a))
        self.ui.uShapeAction.triggered.connect(lambda b,a=self.ui.uShapeAction: self.updateWaypoints(a))

        # Make sure parameter node is initialized (needed for module reload)
        self.initializeParameterNode()

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
        self.ui.insideModelsSelector.initialize()
        self.ui.outsideModelsSelector.initialize()

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

        # Select default input nodes if nothing is selected yet to save a few clicks for the user
        if not self._parameterNode.GetNodeReference("InputCurve"):
            firstCurveNode = slicer.mrmlScene.GetFirstNodeByClass("vtkMRMLMarkupsCurveNode")
            if firstCurveNode:
                self._parameterNode.SetNodeReferenceID("InputCurve", firstCurveNode.GetID())

    def setParameterNode(self, inputParameterNode):
        """
        Set and observe parameter node.
        Observation is needed because when the parameter node is changed then the GUI must be updated immediately.
        """

        if inputParameterNode:
            self.logic.setDefaultParameters(inputParameterNode)

        # Set parameter node in the parameter node selector widget
        wasBlocked = self.ui.parameterNodeSelector.blockSignals(True)
        self.ui.parameterNodeSelector.setCurrentNode(inputParameterNode)
        self.ui.parameterNodeSelector.blockSignals(wasBlocked)

        # Unobserve previously selected parameter node and add an observer to the newly selected.
        # Changes of parameter node are observed so that whenever parameters are changed by a script or any other module
        # those are reflected immediately in the GUI.
        if self._parameterNode is not None and self.hasObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode):
            self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)
        self._parameterNode = inputParameterNode
        if self._parameterNode is not None:
            self.addObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)

        self.ui.waypointsValueWidget.setParameterNode(self._parameterNode)

        # Initial GUI update
        self.updateGUIFromParameterNode()

    def inpuNodeChanged(self, incomingNode):
        self.setUpCopyPositionMenu()
        if not self._parameterNode:
            return
        previousNode = self._parameterNode.GetNodeReference("InputCurve")
        if previousNode and (previousNode != incomingNode) and hasattr(self, '_inputNodeObserverTag'):
            previousNode.RemoveObserver(self._inputNodeObserverTag)
        if incomingNode:
            self._inputNodeObserverTag = incomingNode.AddObserver(incomingNode.PointModifiedEvent, self.onMarkupsModified)

    def onMarkupsModified(self, caller, event):
        self.setUpCopyPositionMenu()
        self.updateGUIFromParameterNode()

    def setUpCopyPositionMenu(self, caller=None, event=None):
        self.ui.copyPositionMenu.clear()
        inputCurve = self.ui.inputSelector.currentNode()
        if inputCurve and inputCurve.GetNumberOfControlPoints() > 1:
            self.ui.copyPositionActionGroup = qt.QActionGroup(self.ui.copyPositionMenu)
            for i in range(inputCurve.GetNumberOfControlPoints()):
                action = qt.QAction(inputCurve.GetNthControlPointLabel(i), self.ui.copyPositionMenu)
                self.ui.copyPositionActionGroup.addAction(action)
            self.ui.copyPositionMenu.addActions(self.ui.copyPositionActionGroup.actions())
            self.ui.copyPositionActionGroup.connect("triggered(QAction*)", self.updateWaypoints)

    def onDuplicateParameterSet(self):
        duplicate = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScriptedModuleNode")
        duplicate.Copy(self._parameterNode)
        duplicate.SetName(slicer.mrmlScene.GenerateUniqueName(self._parameterNode.GetName() + '_Copy'))
        self.setParameterNode(duplicate)

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
        maxSpread = self._parameterNode.GetParameter("MaxSpread") if self._parameterNode.GetParameter("MaxSpread") else "5"
        self.ui.waypointSpreadSlider.maximum = int(maxSpread)
        self.ui.waypointSpreadSlider.singleStep = float(maxSpread) / 50.0
        self.ui.maxSpreadSpinBox.value = int(maxSpread)
        self.ui.inputSelector.setCurrentNode(self._parameterNode.GetNodeReference("InputCurve"))
        self.ui.betweenCurveSelector.setCurrentNode(self._parameterNode.GetNodeReference("BetweenCurve"))
        self.ui.outputSelector.setCurrentNode(self._parameterNode.GetNodeReference("OutputBundle"))
        self.ui.numberOfFibersSliderWidget.value = float(self._parameterNode.GetParameter("NumberOfFibers"))
        self.ui.spreadExtrapolateAction.setChecked(self._parameterNode.GetParameter("SpreadExtrapolate") == "True")
        self.ui.sineCyclesSlider.value = float(self._parameterNode.GetParameter("SineCycles"))

        inputIsOpenCurve = not isinstance(self.ui.inputSelector.currentNode(), slicer.vtkMRMLMarkupsClosedCurveNode)
        self.ui.startModelSelector.setCurrentNode(self._parameterNode.GetNodeReference("StartModel") if inputIsOpenCurve else None)
        self.ui.endModelSelector.setCurrentNode(self._parameterNode.GetNodeReference("EndModel") if inputIsOpenCurve else None)
        self.ui.insideModelsSelector.setSelectedModelsIDs(self._parameterNode.GetParameter("InsideModels"))
        self.ui.outsideModelsSelector.setSelectedModelsIDs(self._parameterNode.GetParameter("OutsideModels"))
        
        next(filter(lambda action: action.text == self._parameterNode.GetParameter("SplineOrder"), self.ui.splineOrderActionsGroup.actions())).setChecked(True)
        next(filter(lambda action: action.text == self._parameterNode.GetParameter("FibersSampleType"), self.ui.fibersSampleTypeActionsGroup.actions())).setChecked(True)
        next(filter(lambda action: action.text == self._parameterNode.GetParameter("SpreadModify"), self.ui.spreadModifyActionsGroup.actions())).setChecked(True)

        waypoints = json.loads(self._parameterNode.GetParameter("Waypoints"))
        spreadValue = waypoints[int(self._parameterNode.GetParameter("WaypointIndex"))]['spread']
        if spreadValue != self.ui.waypointSpreadSlider.value:
            self.ui.waypointSpreadSlider.setValue(spreadValue)

        # Update buttons states and tooltips
        if self._parameterNode.GetNodeReference("InputCurve") and self._parameterNode.GetNodeReference("OutputBundle"):
            self.ui.applyButton.toolTip = "Compute output bundle"
            self.ui.applyButton.enabled = True
            self.ui.autoApplyCheckBox.enabled = True
        else:
            self.ui.applyButton.toolTip = "Select input and output nodes"
            self.ui.applyButton.enabled = False
            self.ui.autoApplyCheckBox.checked = False
            self.ui.autoApplyCheckBox.enabled = False

        self.ui.startModelSelector.enabled = inputIsOpenCurve
        self.ui.endModelSelector.enabled = inputIsOpenCurve

        if not hasattr(slicer,'vtkMRMLFiberBundleNode'):
            self.ui.outputSelector.enabled = False
            self.ui.outputSelector.toolTip = "This module requires the SlicerDMRI extension"
        
        if self._parameterNode.GetNodeReference("OutputBundle"):
            self.ui.saveAsTrkToolButton.enabled = True
        
        self.setUpCopyPositionMenu()

        # All the GUI updates are done
        self._updatingGUIFromParameterNode = False

        if self.ui.autoApplyCheckBox.checked:
            self.onApplyButton()

    def updateParameterNodeFromGUI(self, caller=None, event=None):
        """
        This method is called when the user makes any change in the GUI.
        The changes are saved into the parameter node (so that they are restored when the scene is saved and loaded).
        """

        if self._parameterNode is None or self._updatingGUIFromParameterNode:
            return

        wasModified = self._parameterNode.StartModify()  # Modify all properties in a single batch

        self._parameterNode.SetParameter("MaxSpread", str(self.ui.maxSpreadSpinBox.value))
        self._parameterNode.SetNodeReferenceID("InputCurve", self.ui.inputSelector.currentNodeID)
        self._parameterNode.SetNodeReferenceID("BetweenCurve", self.ui.betweenCurveSelector.currentNodeID)
        self._parameterNode.SetNodeReferenceID("OutputBundle", self.ui.outputSelector.currentNodeID)
        self._parameterNode.SetNodeReferenceID("StartModel", self.ui.startModelSelector.currentNodeID)
        self._parameterNode.SetNodeReferenceID("EndModel", self.ui.endModelSelector.currentNodeID)
        self._parameterNode.SetParameter("InsideModels", self.ui.insideModelsSelector.getSelectedModelsIDs())
        self._parameterNode.SetParameter("OutsideModels", self.ui.outsideModelsSelector.getSelectedModelsIDs())
        self._parameterNode.SetParameter("NumberOfFibers", str(self.ui.numberOfFibersSliderWidget.value))
        self._parameterNode.SetParameter("SpreadExtrapolate", str(bool(self.ui.spreadExtrapolateAction.isChecked())))
        self._parameterNode.SetParameter("SplineOrder", [action.text for action in self.ui.splineOrderActionsGroup.actions() if action.isChecked()][0])
        self._parameterNode.SetParameter("FibersSampleType", [action.text for action in self.ui.fibersSampleTypeActionsGroup.actions() if action.isChecked()][0])
        self._parameterNode.SetParameter("SpreadModify", [action.text for action in self.ui.spreadModifyActionsGroup.actions() if action.isChecked()][0])
        self._parameterNode.SetParameter("SineCycles", str(self.ui.sineCyclesSlider.value))

        self._parameterNode.EndModify(wasModified)

    def updateSpreadsFromSlider(self, caller=None, event=None):
        if self._updatingGUIFromParameterNode:
            return
        
        waypoints = json.loads(self._parameterNode.GetParameter("Waypoints"))
        selectedIndex = int(self._parameterNode.GetParameter("WaypointIndex"))

        diff = self.ui.waypointSpreadSlider.value - waypoints[selectedIndex]['spread']
        iterator = [selectedIndex] if self._parameterNode.GetParameter("SpreadModify") == "Selected" else range(len(waypoints))

        for i in iterator:
            if diff > 0:
                waypoints[i]['spread'] = min(waypoints[i]['spread'] + diff, self.ui.maxSpreadSpinBox.value)
            else:
                waypoints[i]['spread'] = max(waypoints[i]['spread'] + diff, 0)

        self._parameterNode.SetParameter("Waypoints", json.dumps(waypoints))
        
    def updateWaypoints(self, action):
        if action.text == "Reset":
            spread = np.mean([item['spread'] for item in json.loads(self._parameterNode.GetParameter("Waypoints"))])
            waypoints = [{"position":50, "spread":spread}]
            waypointIndex = 0

        elif action.text == "U shape":
            positions = [10, 20, 40, 60, 80, 90]
            values = np.array([0.7, 0.2, 0.15, 0.15, 0.2, 0.7]) * self.ui.maxSpreadSpinBox.value
            waypoints = [{"position":pos, "spread":val} for pos,val in zip(positions,values)]
            waypointIndex = 0

        else:
            idx = self.ui.copyPositionActionGroup.actions().index(action)
            curve = self.ui.inputSelector.currentNode()
            if not curve:
                return
            absVal = curve.GetCurveLengthBetweenStartEndPointsWorld(curve.GetCurvePointIndexFromControlPointIndex(0), curve.GetCurvePointIndexFromControlPointIndex(idx))
            newPosition = absVal / curve.GetCurveLengthWorld() * 100
            waypoints = json.loads(self._parameterNode.GetParameter("Waypoints"))
            spread = self.logic.getSpreadForNewPosition([item['position'] for item in waypoints], [item['spread'] for item in waypoints], newPosition)
            waypoints.append({"position":newPosition, "spread":spread})
            waypointIndex = len(waypoints)-1

        wasModified = self._parameterNode.StartModify()  # Modify all properties in a single batch
        self._parameterNode.SetParameter("WaypointIndex", str(waypointIndex))
        self._parameterNode.SetParameter("Waypoints", json.dumps(waypoints))
        self._parameterNode.EndModify(wasModified)

    def onApplyButton(self):
        """
        Run processing when user clicks "Apply" button.
        """
        with slicer.util.tryWithErrorDisplay("Failed to compute results.", waitCursor=True):

            waypoints = json.loads(self._parameterNode.GetParameter("Waypoints"))
            spreadValues = [item['spread'] for item in waypoints]
            spreadPositions = [item['position'] for item in waypoints]
            splineOrder = int([action.text for action in self.ui.splineOrderActionsGroup.actions() if action.isChecked()][0])
            spreadExtrapolate = self.ui.spreadExtrapolateAction.isChecked()

            fibersSampleType = [action.text for action in self.ui.fibersSampleTypeActionsGroup.actions() if action.isChecked()][0]

            insideModels = [slicer.mrmlScene.GetNodeByID(id) for id in self.ui.insideModelsSelector.getSelectedModelsIDs().split(',')]
            outsideModels = [slicer.mrmlScene.GetNodeByID(id) for id in self.ui.outsideModelsSelector.getSelectedModelsIDs().split(',')]

            # Compute output
            numberOfFibers = self.logic.process(self.ui.inputSelector.currentNode(),
                               self.ui.betweenCurveSelector.currentNode(), 
                               self.ui.outputSelector.currentNode(),
                               int(self.ui.numberOfFibersSliderWidget.value),
                               fibersSampleType,
                               self.ui.sineCyclesSlider.value,
                               spreadValues,
                               spreadPositions,
                               splineOrder,
                               spreadExtrapolate,
                               self.ui.startModelSelector.currentNode(),
                               self.ui.endModelSelector.currentNode(),
                               insideModels,
                               outsideModels)
            
            self.ui.outputFibersLabel.setText(str(numberOfFibers))

    def onSaveAsTrk(self):
        outputBundleNode = self.ui.outputSelector.currentNode()
        if not outputBundleNode:
            return
        
        referenceNode = self.ui.saveReferenceVolumeComboBox.currentNode()
        if not referenceNode:
            qt.QMessageBox().warning(qt.QWidget(), "", "Select reference node.")
            return

        trkPath = qt.QFileDialog.getSaveFileName(slicer.util.mainWindow(), "Save as .trk", "", "Trackvis files (*.trk)")
        if trkPath:
            self.logic.saveBundleAsTrk(outputBundleNode, referenceNode, trkPath)


#
# CurveToBundleLogic
#

class CurveToBundleLogic(ScriptedLoadableModuleLogic):
    """This class should implement all the actual
    computation done by your module.  The interface
    should be such that other python code can import
    this class and make use of the functionality without
    requiring an instance of the Widget.
    Uses ScriptedLoadableModuleLogic base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self):
        """
        Called when the logic class is instantiated. Can be used for initializing member variables.
        """
        ScriptedLoadableModuleLogic.__init__(self)
        if slicer.util.settingsValue('Developer/DeveloperMode', False, converter=slicer.util.toBool):
            import CurveToBundleLib
            import importlib
            import glob
            curveToBundlePath = os.path.split(__file__)[0]
            G = glob.glob(os.path.join(curveToBundlePath, 'CurveToBundleLib','**','*.py'))
            for g in G:
                relativePath = os.path.relpath(g, curveToBundlePath) # relative path
                relativePath = os.path.splitext(relativePath)[0] # get rid of .py
                moduleParts = relativePath.split(os.path.sep) # separate
                importlib.import_module('.'.join(moduleParts)) # import module
                module = CurveToBundleLib
                for i in range(1,len(moduleParts)): # iterate over parts in order to load subpkgs
                    module = getattr(module, moduleParts[i])
                    importlib.reload(module) # reload
    
    def setDefaultParameters(self, parameterNode):
        """
        Initialize parameter node with default settings.
        """
        if not parameterNode.GetParameter("NumberOfFibers"):
            parameterNode.SetParameter("NumberOfFibers", "50")
        if not parameterNode.GetParameter("Waypoints"):
            parameterNode.SetParameter("Waypoints", json.dumps([{"position":50,"spread":2}]))
        if not parameterNode.GetParameter("WaypointIndex"):
            parameterNode.SetParameter("WaypointIndex", "0")
        if not parameterNode.GetParameter("SpreadModify"):
            parameterNode.SetParameter("SpreadModify", "Selected")
        if not parameterNode.GetParameter("MaxSpread"):
            parameterNode.SetParameter("MaxSpread", "5")
        if not parameterNode.GetParameter("SplineOrder"):
            parameterNode.SetParameter("SplineOrder", "3")
        if not parameterNode.GetParameter("SpreadExtrapolate"):
            parameterNode.SetParameter("SpreadExtrapolate", "True")
        if not parameterNode.GetParameter("FibersSampleType"):
            parameterNode.SetParameter("FibersSampleType", "normal")
        if not parameterNode.GetParameter("SineCycles"):
            parameterNode.SetParameter("SineCycles", "2")

    def getInterpolatedSpreads(self, spreadValues, spreadPositions, splineOrder, spreadExtrapolate, numberOfPoints, inputIsClosedCurve):
        numberOfItemsToInterpolate = len(spreadValues)
        
        if numberOfItemsToInterpolate == 1:
            return np.ones(numberOfPoints) * spreadValues[0]
        
        # sort according to position
        spreadValues, spreadPositions = zip(*sorted(zip(spreadValues, spreadPositions), key=lambda x: x[1]))
        spreadValues, spreadPositions = np.array(spreadValues), np.array(spreadPositions)

        if inputIsClosedCurve:
            if spreadPositions[0]+100 <= spreadPositions[-1]:
                spreadValues[0] = np.mean([spreadValues[0], spreadValues[-1]])
                spreadValues = spreadValues[:-1]
                spreadPositions = spreadPositions[:-1]
            spreadValues = np.append(spreadValues, spreadValues)                
            spreadPositions = np.append(spreadPositions, spreadPositions + 100)
        
        if numberOfItemsToInterpolate <= splineOrder:
            splineOrder = numberOfItemsToInterpolate-1

        ext = 'extrapolate' if spreadExtrapolate else 'const'

        from scipy.interpolate import UnivariateSpline
        interpFunction = UnivariateSpline(spreadPositions, 
                               spreadValues,
                               k = splineOrder,
                               ext = ext)
        
        if not inputIsClosedCurve:
            interpolatedSpreads = interpFunction(np.linspace(0, 100, numberOfPoints))
        else:
            interpolatedSpreads = interpFunction(np.linspace(50, 150, numberOfPoints))
            idx = int(np.ceil(numberOfPoints/2))
            interpolatedSpreads = np.concatenate((interpolatedSpreads[idx:], interpolatedSpreads[:idx]))

        return interpolatedSpreads
    
    def applyStartEndConstraints(self, points, startModel, endModel):
        startIndex = 0
        endIndex = points.shape[0]
        if startModel:
            startDistanceFilter = vtk.vtkImplicitPolyDataDistance()
            startDistanceFilter.SetInput(startModel.GetPolyData())
            while startIndex != endIndex:
                distance = startDistanceFilter.EvaluateFunction(points[startIndex])
                if distance < 0:
                    break
                startIndex += 1
        if endModel:
            endDistanceFilter = vtk.vtkImplicitPolyDataDistance()
            endDistanceFilter.SetInput(endModel.GetPolyData())
            while endIndex != startIndex:
                distance = endDistanceFilter.EvaluateFunction(points[endIndex-1])
                if distance < 0:
                    break
                endIndex -= 1
        return points[startIndex:endIndex]

    def applyInsideOutsideConstraints(self, pd, insideModels, outsideModels):
        extractPolyData = vtk.vtkExtractPolyDataGeometry()
        extractPolyData.SetInputData(pd)
        extractPolyData.SetImplicitFunction(vtk.vtkImplicitPolyDataDistance())
        
        extractPolyData.SetExtractInside(True)
        extractPolyData.SetExtractBoundaryCells(True)        
        for model in insideModels:
            if model:
                extractPolyData.GetImplicitFunction().SetInput(model.GetPolyData())
                extractPolyData.Update()
                pd.DeepCopy(extractPolyData.GetOutput())
        
        extractPolyData.SetExtractInside(False)
        extractPolyData.SetExtractBoundaryCells(False)
        for model in outsideModels:
            if model:
                extractPolyData.GetImplicitFunction().SetInput(model.GetPolyData())
                extractPolyData.Update()
                pd.DeepCopy(extractPolyData.GetOutput())

    def getPointDisplacements(self, fibersSampleType, sineCycles, spreads, numberOfPoints):
        if fibersSampleType == 'uniform':
            randomTranslate = np.random.rand(3) * 2 - 1
        elif fibersSampleType == 'normal':
            randomTranslate = np.random.randn(3)
        sine = np.sin((np.random.rand(1) * 2*np.pi) + np.linspace(0, sineCycles*np.pi, numberOfPoints))
        return np.tile(randomTranslate, (numberOfPoints,1)) * spreads[:,np.newaxis] * sine[:,np.newaxis]

    def getPointsBetween(self, curvePoints1, curvePoints2):
        direction = curvePoints2 - curvePoints1
        distance = np.linalg.norm(direction, axis=1)
        normalizedDirection = direction / distance[:,np.newaxis]
        return curvePoints1 + normalizedDirection * distance[:,np.newaxis] * np.random.rand()

    def process(self, inputCurve, betweenCurve, outputBundle, numberOfFibers, fibersSampleType, sineCycles, spreadValues, spreadPositions, splineOrder, spreadExtrapolate, startModel = None, endModel = None, insideModels = [], outsideModels = []):
        if not inputCurve or not outputBundle:
            raise ValueError("Input or output volume is invalid")
        
        inputIsClosedCurve = isinstance(inputCurve, slicer.vtkMRMLMarkupsClosedCurveNode)

        resampledCurve = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsClosedCurveNode" if inputIsClosedCurve else "vtkMRMLMarkupsCurveNode")
        resampledCurve.Copy(inputCurve)
        resampledCurve.ResampleCurveWorld(1) # 1mm spacing

        numberOfPoints = resampledCurve.GetNumberOfControlPoints()
        curvePoints = np.array([resampledCurve.GetNthControlPointPosition(i) for i in range(numberOfPoints)])

        if betweenCurve is not None:
            betweenCurveResampled = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsClosedCurveNode" if inputIsClosedCurve else "vtkMRMLMarkupsCurveNode")
            betweenCurveResampled.Copy(betweenCurve)
            betweenCurveResampled.ResampleCurveWorld(betweenCurveResampled.GetCurveLengthWorld() / max((numberOfPoints - 1), 1))
            betweenCurvePoints = np.array([betweenCurveResampled.GetNthControlPointPosition(i) for i in range(numberOfPoints)])

        spreads = self.getInterpolatedSpreads(spreadValues, spreadPositions, splineOrder, spreadExtrapolate, numberOfPoints, inputIsClosedCurve)
        
        outPoints = vtk.vtkPoints()
        outLines = vtk.vtkCellArray()
        id = 0
        for _ in range(numberOfFibers):
            displacements = self.getPointDisplacements(fibersSampleType, sineCycles, spreads, numberOfPoints)
            if betweenCurve is None:
                localPoints = curvePoints
            else:
                localPoints = self.getPointsBetween(betweenCurvePoints, curvePoints)
            transformedPoints = localPoints + displacements
            validPoints = self.applyStartEndConstraints(transformedPoints, startModel, endModel)
            if validPoints.shape[0] < 2:
                continue
            line = vtk.vtkPolyLine()
            for i in range(validPoints.shape[0]):
                outPoints.InsertNextPoint(validPoints[i])
                line.GetPointIds().InsertNextId(id)
                id += 1
            if inputIsClosedCurve:
                line.GetPointIds().InsertNextId(id - validPoints.shape[0])
            outLines.InsertNextCell(line)
        
        slicer.mrmlScene.RemoveNode(resampledCurve)
        if betweenCurve is not None:
            slicer.mrmlScene.RemoveNode(betweenCurveResampled)

        pd = vtk.vtkPolyData()
        pd.SetPoints(outPoints)
        pd.SetLines(outLines)

        self.applyInsideOutsideConstraints(pd, insideModels, outsideModels)

        outputBundle.SetAndObservePolyData(pd)
        outputBundle.CreateDefaultDisplayNodes()
        outputBundle.GetDisplayNode().SetColorModeToPointFiberOrientation()

        return pd.GetLines().GetNumberOfCells()

    def getSpreadForNewPosition(self, positions, spreads, newPosition):
        sortedPos, sortedSpreads = zip(*sorted(zip(positions, spreads), key=lambda x: x[0]))
        for i,p in enumerate((0,) + sortedPos + (100,)):
            if p > newPosition:
                break
        if i==1:
            spread = sortedSpreads[0]
        elif i==len(sortedPos)+1:
            spread = sortedSpreads[-1]
        else:
            spread = (sortedSpreads[i-2] + sortedSpreads[i-1])/2
        return spread

    def saveBundleAsTrk(self, outputBundle, referenceNode, trkPath):
        try:
            import dipy
        except:
            slicer.util.pip_install('fury')
            slicer.util.pip_install('dipy')
        
        from dipy.io.streamline import load_vtk_streamlines, save_trk
        from dipy.io.stateful_tractogram import StatefulTractogram, Space

        if referenceNode.GetStorageNode() and referenceNode.GetStorageNode().GetFileName() and os.path.exists(referenceNode.GetStorageNode().GetFileName()):
            referenceFile = referenceNode.GetStorageNode().GetFileName()
            shouldRemoveReference = False
        else:
            referenceFile = slicer.app.temporaryPath + '/' + os.path.basename(trkPath).replace('.trk', '.nii')
            slicer.util.saveNode(referenceNode, referenceFile)
            shouldRemoveReference = True

        vtkPath = trkPath.replace('.trk', '.vtk')
        slicer.util.saveNode(outputBundle, vtkPath)

        streamlines = load_vtk_streamlines(vtkPath)
        streamlines = [x * np.array([-1,-1,1]) for x in streamlines]

        st = StatefulTractogram(streamlines, referenceFile, Space.RASMM)
        save_trk(st, trkPath, False)

        os.remove(vtkPath)
        if shouldRemoveReference:
            os.remove(referenceFile)

        qt.QMessageBox().information(qt.QWidget(), "", "Done!")

#
# CurveToBundleTest
#

class CurveToBundleTest(ScriptedLoadableModuleTest):
    """
    This is the test case for your scripted module.
    Uses ScriptedLoadableModuleTest base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def setUp(self):
        """ Do whatever is needed to reset the state - typically a scene clear will be enough.
        """
        slicer.mrmlScene.Clear()

    def runTest(self):
        """Run as few or as many tests as needed here.
        """
        self.setUp()
        self.test_CurveToBundle1()

    def test_CurveToBundle1(self):
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

        self.delayDisplay('Test passed')
