import enum
import qt, ctk, slicer

class ComboDelegate(qt.QItemDelegate):
  def __init__(self, parent, comboItems):
    qt.QItemDelegate.__init__(self, parent)
    self.comboItems = comboItems

  def createEditor(self, parent, option, index):
    import LeadOR
    logic = LeadOR.LeadORLogic()
    combo = qt.QComboBox(parent)
    combo.addItems(self.comboItems)
    combo.currentTextChanged.connect(lambda text, feature=index.model().data(index.siblingAtColumn(1)): logic.setFeatureMapTo(feature, text))
    return combo

  def setEditorData(self, editor, index):
    editor.blockSignals(True)
    editor.setCurrentText(index.model().data(index))
    editor.blockSignals(False)

  def setModelData(self, editor, model, index):
    name = editor.currentText
    model.setData(index, name, qt.Qt.DisplayRole)


class firstColumnCheckableModel(qt.QStandardItemModel):
  def __init__(self , *args, **kwargs):
    super().__init__(*args, **kwargs)

  def flags(self, index):
    baseFlags = qt.Qt.ItemIsEnabled | qt.Qt.ItemIsSelectable
    if index.column() == 0:
      return baseFlags | qt.Qt.ItemIsUserCheckable
    else:
      return baseFlags | qt.Qt.ItemIsEditable

  def setData(self , *args, **kwargs):
    index = args[0] if args else None
    if isinstance(index, qt.QModelIndex) and args[-1] == qt.Qt.CheckStateRole:
      featureName = index.model().data(index.siblingAtColumn(1))
      import LeadOR
      logic = LeadOR.LeadORLogic()
      logic.setFeatureVisibility(featureName, args[1])
    qt.QStandardItemModel.setData(self , *args, **kwargs)


class FeaturesTable(qt.QWidget):

  RowHeight = 25

  def __init__(self):
    super().__init__()

    self.columnNames = ["Visible", "Name", "MapTo"]
    self.model = firstColumnCheckableModel(0, len(self.columnNames))
    for i, columnName in enumerate(self.columnNames):
      self.model.setHeaderData(i, qt.Qt.Horizontal, columnName)

    self.view = qt.QTableView()
    self.view.setEditTriggers(self.view.CurrentChanged + self.view.DoubleClicked + self.view.SelectedClicked)
    self.view.setSelectionMode(self.view.SingleSelection)
    self.view.setSelectionBehavior(self.view.SelectRows)
    self.view.horizontalHeader().setStretchLastSection(True)
    self.view.setHorizontalScrollMode(self.view.ScrollPerPixel)
    self.view.verticalHeader().setMaximumSectionSize(self.RowHeight)
    self.view.verticalHeader().setMinimumSectionSize(self.RowHeight)
    self.view.verticalHeader().setDefaultSectionSize(self.RowHeight)
    self.view.setFixedHeight(65)
    self.view.setModel(self.model)
    self.view.selectionModel().selectionChanged.connect(self.onSelectionChanged)

    self.view.setItemDelegateForColumn(2, ComboDelegate(self.model, ["","TubeRadiusAndColor","TubeRadius","TubeColor"]))

  def onSelectionChanged(self):
    pass

  def getSelectedRow(self):
    selectedRows = self.view.selectionModel().selectedRows()
    for selectedRow in selectedRows:
      return selectedRow.row() # is a single selection view

  def addRowAndSetHeight(self):
    self.model.insertRow(self.model.rowCount())
    self.view.setFixedHeight(self.view.height+self.RowHeight)

  def updateNthRowFromFeature(self, rowN, feature):
    for colN,attr in enumerate(self.columnNames):
      index = self.model.index(rowN, colN)
      val = getattr(feature,attr)
      if colN == 0:
        val = qt.Qt.Checked if val else qt.Qt.Unchecked
        role = qt.Qt.CheckStateRole
      else:
        role = qt.Qt.DisplayRole
      self.model.setData(index, val, role)
