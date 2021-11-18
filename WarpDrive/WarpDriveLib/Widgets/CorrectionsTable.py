import qt, vtk, slicer
from slicer.util import VTKObservationMixin
import WarpDrive


class TextEditDelegate(qt.QItemDelegate):
  def __init__(self, parent, renameControlPointsFunction):
    qt.QItemDelegate.__init__(self, parent)
    self.renameControlPointsFunction = renameControlPointsFunction

  def createEditor(self, parent, option, index):
    lineEdit = qt.QLineEdit(parent)
    return lineEdit

  def setEditorData(self, editor, index):
    editor.blockSignals(True)
    editor.text = index.model().data(index) if index.model().data(index) else ""
    editor.blockSignals(False)
  
  def setModelData(self, editor, model, index):
    previousName = index.model().data(index)
    newName = editor.text
    model.setData(index, newName)
    self.renameControlPointsFunction(previousName, newName)

class SpinBoxDelegate(qt.QItemDelegate):
  def __init__(self, parent, updateRadiusFunction):
    qt.QItemDelegate.__init__(self, parent)
    self.updateRadiusFunction = updateRadiusFunction

  def createEditor(self, parent, option, index):
    spinBox = qt.QDoubleSpinBox(parent)
    spinBox.setSingleStep(1)
    spinBox.maximum = 50
    spinBox.minimum = 5
    return spinBox

  def setEditorData(self, editor, index):
    editor.blockSignals(True)
    editor.value = float(index.model().data(index)) if index.model().data(index) else 30
    editor.blockSignals(False)

  def setModelData(self, editor, model, index):
    newValue = editor.value
    model.setData(index, newValue)
    controlPointName = index.model().data(index.siblingAtColumn(1))
    self.updateRadiusFunction(controlPointName, newValue)

class firstColumnCheckableModel(qt.QStandardItemModel):
  def __init__(self , *args, **kwargs):
    super().__init__(*args, **kwargs)
    self.updateSelectedFuntion = None

  def flags(self, index):
    baseFlags = qt.Qt.ItemIsEnabled | qt.Qt.ItemIsSelectable
    if index.column() == 0:
      return baseFlags | qt.Qt.ItemIsUserCheckable
    else:
      return baseFlags | qt.Qt.ItemIsEditable

  def setData(self , *args, **kwargs):
    index = args[0] if args else None
    if isinstance(index, qt.QModelIndex) and args[-1] == qt.Qt.CheckStateRole:
      controlPointName = index.model().data(index.siblingAtColumn(1))
      self.updateSelectedFuntion(controlPointName, args[1])
    qt.QStandardItemModel.setData(self , *args, **kwargs)

class WarpDriveCorrectionsTable(qt.QWidget):


  def __init__(self, parent):
    super().__init__()

    self.sourceVisibleCheckBox = qt.QCheckBox('View Source')
    self.targetVisibleCheckBox = qt.QCheckBox('View Target')

    self.removeButton = qt.QPushButton('Remove')
    self.addFixedPointButton = qt.QPushButton('Add Fixed Point')

    self.buttonsFrame = qt.QFrame()
    self.buttonsFrame.setSizePolicy(qt.QSizePolicy.Preferred, qt.QSizePolicy.Minimum)
    self.buttonsFrame.setLayout(qt.QHBoxLayout())
    self.buttonsFrame.layout().addWidget(self.sourceVisibleCheckBox)
    self.buttonsFrame.layout().addWidget(self.targetVisibleCheckBox)
    self.buttonsFrame.layout().addWidget(self.addFixedPointButton)
    self.buttonsFrame.layout().addWidget(self.removeButton)

    columnNames = ["Include", "Name", "Radius"]
    self.model = firstColumnCheckableModel(1, len(columnNames))
    self.model.updateSelectedFuntion = parent.updateSelected
    for i, columnName in enumerate(columnNames):
      self.model.setHeaderData(i, qt.Qt.Horizontal, columnName)

    self.view = qt.QTableView()
    self.view.setEditTriggers(self.view.DoubleClicked)
    self.view.setSelectionMode(self.view.SingleSelection)
    self.view.setSelectionBehavior(self.view.SelectRows)
    self.view.horizontalHeader().setStretchLastSection(True)
    self.view.setHorizontalScrollMode(self.view.ScrollPerPixel)
    self.view.setModel(self.model)
    
    self.view.setItemDelegateForColumn(1, TextEditDelegate(self.model, parent.renameControlPoints))
    self.view.setItemDelegateForColumn(2, SpinBoxDelegate(self.model, parent.updateRadius))

    layout = qt.QVBoxLayout(self)
    layout.addWidget(self.buttonsFrame)
    layout.addWidget(self.view)
  

  def clearTable(self):
    while self.model.rowCount() > 0:
      self.model.removeRow(self.model.rowCount()-1)

  def onAddButton(self):
    pass

  def getSelectedRow(self):
    selectedRows = self.view.selectionModel().selectedRows()
    for selectedRow in selectedRows:
      return selectedRow.row() # is a single selection view

  def onSelectionChanged(self, selection):
    pass

class WarpDriveCorrectionsManager(VTKObservationMixin):
  def __init__(self):
    VTKObservationMixin.__init__(self)
    self.sourceFiducialNodeID = ""
    self.targetFiducialNodeID = ""
    self._updatingFiducials = False
    self.widget = WarpDriveCorrectionsTable(self)
    self.widget.removeButton.clicked.connect(self.onRemoveButton)
    self.widget.addFixedPointButton.clicked.connect(self.onAddFixedPointButton)
    self.widget.view.selectionModel().selectionChanged.connect(self.onSelectionChanged)
    self.widget.sourceVisibleCheckBox.toggled.connect(self.onSourceVisibleToggled)
    self.widget.targetVisibleCheckBox.toggled.connect(self.onTargetVisibleToggled)
    self.targetFiducialObservers = []
    self.parameterNode = WarpDrive.WarpDriveLogic().getParameterNode()
    self.addObserver(self.parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateNodesListeners)

  def onSourceVisibleToggled(self):
    if self.sourceFiducialNodeID != "":
      sourceFiducialNode = slicer.mrmlScene.GetNodeByID(self.sourceFiducialNodeID)
      sourceFiducialNode.GetDisplayNode().SetVisibility(self.widget.sourceVisibleCheckBox.checked)

  def onTargetVisibleToggled(self):
    if self.targetFiducialNodeID != "":
      targetFiducialNode = slicer.mrmlScene.GetNodeByID(self.targetFiducialNodeID)
      targetFiducialNode.GetDisplayNode().SetVisibility(self.widget.targetVisibleCheckBox.checked)

  def onAddFixedPointButton(self):
    interactionNode = slicer.app.applicationLogic().GetInteractionNode()
    selectionNode = slicer.app.applicationLogic().GetSelectionNode()
    selectionNode.SetReferenceActivePlaceNodeClassName("vtkMRMLMarkupsFiducialNode")
    selectionNode.SetActivePlaceNodeID(self.targetFiducialNodeID)
    interactionNode.SetCurrentInteractionMode(interactionNode.Place)

  def updateNodesListeners(self, caller, event):
    sourceFiducialNode = self.parameterNode.GetNodeReference("SourceFiducial")
    if sourceFiducialNode and self.sourceFiducialNodeID != sourceFiducialNode.GetID():
      self.sourceFiducialNodeID = sourceFiducialNode.GetID()
    
    targetFiducialNode = self.parameterNode.GetNodeReference("TargetFiducial")
    if targetFiducialNode and self.targetFiducialNodeID != targetFiducialNode.GetID():
      previousNode = slicer.mrmlScene.GetNodeByID(self.targetFiducialNodeID)
      if previousNode and bool(self.targetFiducialObservers):
        for obs in self.targetFiducialObservers:
          previousNode.RemoveObserver(obs)
      self.targetFiducialNodeID = targetFiducialNode.GetID()
      self.targetFiducialObservers.clear()
      self.targetFiducialObservers.append(targetFiducialNode.AddObserver(targetFiducialNode.PointAddedEvent, self.targetFiducialModified))
      self.targetFiducialObservers.append(targetFiducialNode.AddObserver(targetFiducialNode.PointRemovedEvent, self.targetFiducialModified))
      self.targetFiducialObservers.append(targetFiducialNode.AddObserver(targetFiducialNode.PointModifiedEvent, self.targetFiducialModified))
      self.targetFiducialObservers.append(targetFiducialNode.AddObserver(targetFiducialNode.PointPositionDefinedEvent, self.onPointPositionDefined))
      self.setUpWidget()

  def targetFiducialModified(self, caller, event):
    self.setUpWidget()

  def setUpWidget(self):
    if self._updatingFiducials:
      return
    self.widget.clearTable()
    targetFiducialNode = slicer.mrmlScene.GetNodeByID(self.targetFiducialNodeID)
    newCorrection = {"include": False, "name": "", "radius":""}
    for i in range(targetFiducialNode.GetNumberOfControlPoints()):
      if newCorrection["name"] == targetFiducialNode.GetNthControlPointLabel(i):
        continue
      else:
        self.addCorrectionToWidget(newCorrection)
        newCorrection["name"] = targetFiducialNode.GetNthControlPointLabel(i)
        newCorrection["radius"] = targetFiducialNode.GetNthControlPointDescription(i)
        newCorrection["include"] = targetFiducialNode.GetNthControlPointSelected(i)
    self.addCorrectionToWidget(newCorrection)

  def addCorrectionToWidget(self, newCorrection):
    if newCorrection["name"] == "":
      return

    row = self.widget.model.rowCount()
    self.widget.model.insertRow(row)
    for col,val in enumerate(newCorrection.values()):
      index = self.widget.model.index(row, col)
      if col == 0:
        val = qt.Qt.Checked if val else qt.Qt.Unchecked
        role = qt.Qt.CheckStateRole
      else:
        role = qt.Qt.DisplayRole

      self.widget.model.setData(index, val, role)

  def onPointPositionDefined(self, caller, event):
    targetFiducialNode = slicer.mrmlScene.GetNodeByID(self.targetFiducialNodeID)
    lastControlPoint = targetFiducialNode.GetNumberOfControlPoints()-1
    name = targetFiducialNode.GetNthControlPointLabel(lastControlPoint)
    if name.startswith(targetFiducialNode.GetName()):
      sourceFiducialNode = slicer.mrmlScene.GetNodeByID(self.sourceFiducialNodeID)
      sourceFiducialNode.AddControlPoint(vtk.vtkVector3d(targetFiducialNode.GetNthControlPointPosition(lastControlPoint)))
      targetFiducialNode.SetNthControlPointLabel(lastControlPoint, slicer.mrmlScene.GenerateUniqueName('fixed point'))
      targetFiducialNode.SetNthControlPointDescription(lastControlPoint, self.parameterNode.GetParameter("Radius"))
      sourceFiducialNode.SetNthControlPointLabel(lastControlPoint, targetFiducialNode.GetNthControlPointLabel(lastControlPoint))
      sourceFiducialNode.SetNthControlPointDescription(lastControlPoint, self.parameterNode.GetParameter("Radius"))

  def getSelectedCorrectionName(self):
    row = self.widget.getSelectedRow()
    if row is None or self.targetFiducialNodeID=="":
      return
    index = self.widget.model.index(row, 1)
    return self.widget.model.itemData(index)[0]

  def onRemoveButton(self):
    correctionName = self.getSelectedCorrectionName()
    if correctionName is None:
      return
    targetFiducialNode = slicer.mrmlScene.GetNodeByID(self.targetFiducialNodeID)
    sourceFiducialNode = slicer.mrmlScene.GetNodeByID(self.sourceFiducialNodeID)
    for i in range(targetFiducialNode.GetNumberOfControlPoints()-1,-1,-1):
      if targetFiducialNode.GetNthControlPointLabel(i) == correctionName:
        targetFiducialNode.RemoveNthControlPoint(i)
        sourceFiducialNode.RemoveNthControlPoint(i)

  def renameControlPoints(self, previousName, newName):
    if self.targetFiducialNodeID == "":
      return
    self._updatingFiducials = True
    targetFiducialNode = slicer.mrmlScene.GetNodeByID(self.targetFiducialNodeID)
    sourceFiducialNode = slicer.mrmlScene.GetNodeByID(self.sourceFiducialNodeID)
    for i in range(targetFiducialNode.GetNumberOfControlPoints()):
      if targetFiducialNode.GetNthControlPointLabel(i) == previousName:
        targetFiducialNode.SetNthControlPointLabel(i, newName)
        sourceFiducialNode.SetNthControlPointLabel(i, newName)
    self._updatingFiducials = False

  def updateRadius(self, controlPointName, value):
    if self.targetFiducialNodeID == "":
      return
    self._updatingFiducials = True
    targetFiducialNode = slicer.mrmlScene.GetNodeByID(self.targetFiducialNodeID)
    sourceFiducialNode = slicer.mrmlScene.GetNodeByID(self.sourceFiducialNodeID)
    for i in range(targetFiducialNode.GetNumberOfControlPoints()):
      if targetFiducialNode.GetNthControlPointLabel(i) == controlPointName:
        targetFiducialNode.SetNthControlPointDescription(i, "%.01f"%value)
        sourceFiducialNode.SetNthControlPointDescription(i, "%.01f"%value)
    self._updatingFiducials = False

  def updateSelected(self, controlPointName, value):
    if self.targetFiducialNodeID == "":
      return    
    self._updatingFiducials = True
    targetFiducialNode = slicer.mrmlScene.GetNodeByID(self.targetFiducialNodeID)
    sourceFiducialNode = slicer.mrmlScene.GetNodeByID(self.sourceFiducialNodeID)
    for i in range(targetFiducialNode.GetNumberOfControlPoints()):
      if targetFiducialNode.GetNthControlPointLabel(i) == controlPointName:
        targetFiducialNode.SetNthControlPointSelected(i, value)
        sourceFiducialNode.SetNthControlPointSelected(i, value)
    self._updatingFiducials = False

  def onSelectionChanged(self):
    correctionName = self.getSelectedCorrectionName()
    if correctionName is None:
      return
    targetFiducialNode = slicer.mrmlScene.GetNodeByID(self.targetFiducialNodeID)
    for i in range(targetFiducialNode.GetNumberOfControlPoints()):
      if targetFiducialNode.GetNthControlPointLabel(i) == correctionName:
        markupsLogic = slicer.modules.markups.logic()
        markupsLogic.JumpSlicesToNthPointInMarkup(self.targetFiducialNodeID,i,False)
        return