import ctk
from slicer.util import VTKObservationMixin
import slicer
import qt


class MultiModelSelectorWidget(ctk.ctkCheckableComboBox, VTKObservationMixin):
    def __init__(self, parent=None):
        ctk.ctkCheckableComboBox.__init__(self, parent)
        VTKObservationMixin.__init__(self)

        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.NewSceneEvent, self.autoSetUpModels)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.NodeAddedEvent, self.autoSetUpModels)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.NodeRemovedEvent, self.autoSetUpModels)

        self._closing = False
        self.autoSetUpModels()

    def onSceneStartClose(self, caller, event):
        self._closing = True

    def onSceneEndClose(self, caller, event):
        self._closing = False
        self.setUpModels()

    def initialize(self):
        self.autoSetUpModels()

    def autoSetUpModels(self, caller=None, event=None):
        if self._closing:
            return
        self.blockSignals(True)
        selectedModels = self.getSelectedModelsIDs()
        self.setUpModels()
        self.setSelectedModelsIDs(selectedModels)
        self.blockSignals(False)

    def setUpModels(self):
        self.clear()
        modelNodes = slicer.mrmlScene.GetNodesByClass("vtkMRMLModelNode")
        modelNodes.UnRegister(modelNodes)
        for i in range(modelNodes.GetNumberOfItems()):
            modelNode = modelNodes.GetItemAsObject(i)
            if not modelNode.GetHideFromEditors() and (hasattr(slicer,'vtkMRMLFiberBundleNode') and not isinstance(modelNode, slicer.vtkMRMLFiberBundleNode)):
                self.addItem(self.generateDisplayNameForModel(modelNode))
                item = self.model().item(self.count-1, 0)
                item.setData(modelNode.GetID(), qt.Qt.UserRole)

    def generateDisplayNameForModel(self, modelNode):
        shNode = slicer.mrmlScene.GetSubjectHierarchyNode()
        displayName = modelNode.GetName()
        item = shNode.GetItemParent(shNode.GetItemByDataNode(modelNode))
        while item != shNode.GetSceneItemID():
            displayName = shNode.GetItemName(item) + ' / ' + displayName
            item = shNode.GetItemParent(item)
        return displayName
    
    def getSelectedModelsIDs(self):
        return ','.join([idx.data(qt.Qt.UserRole) for idx in self.checkedIndexes()])
    
    def setSelectedModelsIDs(self, modelsIDs):
        modelsIDs = modelsIDs.split(',')
        for i in range(self.count):
            if self.itemData(i, qt.Qt.UserRole) in modelsIDs:
                self.model().item(i, 0).setCheckState(qt.Qt.Checked)
            else:
                self.model().item(i, 0).setCheckState(qt.Qt.Unchecked)