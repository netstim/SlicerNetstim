from email.mime import base
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
    combo.currentTextChanged.connect(lambda text, feature=index.model().data(index.siblingAtColumn(0)): logic.setFeatureMapTo(feature, text))
    return combo

  def setEditorData(self, editor, index):
    editor.blockSignals(True)
    editor.setCurrentText(index.model().data(index))
    editor.blockSignals(False)

  def setModelData(self, editor, model, index):
    name = editor.currentText
    model.setData(index, name, qt.Qt.DisplayRole)


class customStandardItemModel(qt.QStandardItemModel):
  def __init__(self , *args, **kwargs):
    self.columnNames = kwargs["columnNames"]
    del kwargs["columnNames"]
    super().__init__(*args, **kwargs)

  def flags(self, index):
    baseFlags = qt.Qt.ItemIsEnabled | qt.Qt.ItemIsSelectable
    if index.column() == self.columnNames.index("Visible"):
      return baseFlags | qt.Qt.ItemIsUserCheckable
    elif index.column() == self.columnNames.index("Name"):
      return baseFlags
    else:
      return baseFlags | qt.Qt.ItemIsEditable

  def setData(self , *args, **kwargs):
    index = args[0] if args else None
    if isinstance(index, qt.QModelIndex) and args[-1] == qt.Qt.CheckStateRole:
      featureName = index.model().data(index.siblingAtColumn(self.columnNames.index("Name")))
      import LeadOR
      logic = LeadOR.LeadORLogic()
      logic.setFeatureVisibility(featureName, args[1])
    qt.QStandardItemModel.setData(self , *args, **kwargs)

  def headerData(self,section,orientation,role):
    if section == 2:
      if orientation == qt.Qt.Horizontal and role == qt.Qt.DecorationRole:
        return qt.QIcon(':Icons/Small/SlicerVisibleInvisible.png')
    elif orientation == qt.Qt.Horizontal and role == qt.Qt.DisplayRole:
      return self.columnNames[section]
    qt.QStandardItemModel.headerData(self,section,orientation,role)

class FeaturesTable:

  RowHeight = 25

  def __init__(self,view):
    # super().__init__()

    self.columnNames = ["Name", "MapTo", "Visible"]
    self.model = customStandardItemModel(0, len(self.columnNames), columnNames=self.columnNames)

    self.view = view
    self.view.setVisible(0)
    self.view.verticalHeader().setMaximumSectionSize(self.RowHeight)
    self.view.verticalHeader().setMinimumSectionSize(self.RowHeight)
    self.view.verticalHeader().setDefaultSectionSize(self.RowHeight)
    self.view.setFixedHeight(65)
    self.view.setModel(self.model)
    self.view.selectionModel().selectionChanged.connect(self.onSelectionChanged)

    self.view.setItemDelegateForColumn(self.columnNames.index("MapTo"), ComboDelegate(self.model, ["","TubeRadiusAndColor","TubeRadius","TubeColor"]))

  def onSelectionChanged(self):
    pass

  def getSelectedRow(self):
    selectedRows = self.view.selectionModel().selectedRows()
    for selectedRow in selectedRows:
      return selectedRow.row() # is a single selection view

  def addRowAndSetVisibility(self):
    self.model.insertRow(self.model.rowCount())
    self.view.setFixedHeight(self.view.height+self.RowHeight)
    if self.model.rowCount():
      self.view.setVisible(1)
      self.view.horizontalHeader().setSectionResizeMode(0, qt.QHeaderView.Stretch)
      self.view.horizontalHeader().setSectionResizeMode(1, qt.QHeaderView.Stretch)
      self.view.horizontalHeader().setSectionResizeMode(2, qt.QHeaderView.ResizeToContents)

  def updateNthRowFromFeature(self, rowN, feature):
    for colN,attr in enumerate(self.columnNames):
      index = self.model.index(rowN, colN)
      val = getattr(feature,attr)
      if colN == self.columnNames.index("Visible"):
        val = qt.Qt.Checked if val else qt.Qt.Unchecked
        role = qt.Qt.CheckStateRole
      else:
        role = qt.Qt.DisplayRole
      self.model.setData(index, val, role)
