import slicer, vtk, qt
import numpy as np
import re
from datetime import datetime


#
# PDF Import
#

try:
  import pdfplumber
except:
  slicer.util.pip_install('pdfplumber')
  import pdfplumber


class StereotaxyReport():

  def __init__(self, PDFPath):
    self.pdf = pdfplumber.open(PDFPath)
    self.pdfWidth = float(self.pdf.pages[0].width)
    self.pdfHeight = float(self.pdf.pages[0].height)

  def hasPatientID(self, patientID):
    return patientID == self.getPatientInformation()['Patient ID']

  def hasSide(self, side):
    return side in self.getTrajectoryInformation()['Name']

  def getTrajectoryInformation(self):
    cropRegion = (self.pdfWidth/2, 130, self.pdfWidth, 240)
    tableSettings = {
      "vertical_strategy": "text",
      "horizontal_strategy": "lines",
      "intersection_y_tolerance": 20,    
      "keep_blank_chars": True,
    }
    outList = self.pdf.pages[0].crop(cropRegion).extract_table(tableSettings)
    outDict = {r[0]:r[1] for r in outList}
    return outDict

  def getPatientInformation(self):
    cropRegion = (0, 130, self.pdfWidth/2, 240)
    tableSettings = {
      "vertical_strategy": "text",
      "horizontal_strategy": "lines",
      "intersection_y_tolerance": 20,    
      "keep_blank_chars": True,
    }
    outList = self.pdf.pages[0].crop(cropRegion).extract_table(tableSettings)
    outDict = {r[0]:r[1] for r in outList}
    return outDict

  def getArcSettings(self):
    cropRegion = (0, 419, self.pdfWidth, 480)
    tableSettings = {
      "vertical_strategy": "text",
      "horizontal_strategy": "text",
      "min_words_vertical": 0,
      "keep_blank_chars": True,
    }
    outList = self.pdf.pages[0].crop(cropRegion).extract_table(tableSettings)
    outList = [[outList[0][i], outList[1][i]] for i in range(len(outList[0]))] # Transpose
    outDict = {r[0]:r[1].split(' ')[0] for r in outList} # Remove units
    outDict["Headring Coordinates"] = ",".join([outDict[C] for C in ["X","Y","Z"]]) # Join X Y Z
    return outDict

  def getCoordinates(self, queryPoint, queryCoordinateSystem, outCoordinateSystem=None):
    # define crop bounding box and transform to RAS
    if queryCoordinateSystem is 'Headring':
      cropBoundingBox = (0, self.pdfHeight * 0.57 , self.pdfWidth/2, self.pdfHeight * 0.85)     
      toRAS = np.array([[ -1,  0,  0,  100],
                        [  0,  1,  0, -100],
                        [  0,  0, -1,  100],
                        [  0,  0,  0,    1]])
    elif queryCoordinateSystem is 'DICOM':
      cropBoundingBox = (self.pdfWidth/2, self.pdfHeight * 0.57 , self.pdfWidth, self.pdfHeight * 0.85)  
      toRAS = np.array([[ -1,  0,  0,  0],
                        [  0, -1,  0,  0],
                        [  0,  0,  1,  0],
                        [  0,  0,  0,  1]])   
    else:
      raise RuntimeError('Invalid queryCoordinateSystem: ' + queryCoordinateSystem)
    # extract text
    PDFText = self.pdf.pages[1].crop(cropBoundingBox).extract_text()
    # extract coords
    m = re.search('(?<=' + queryPoint + ' Point)' + ' [-]?\d+[.]\d+ mm' * 3, PDFText)
    xyz_str = m.group(0).split('mm')
    xyz_flt = [float(x) for x in xyz_str[:-1]]
    # transform
    if outCoordinateSystem is 'RAS':
      xyz_flt = np.dot(toRAS, np.append(xyz_flt, 1))[:3]
    return xyz_flt

  def getDICOMInformation(self):
    t = None
    maxHeight = self.pdfHeight * 0.61
    while not t or t.find("X Y Z")==-1:
      maxHeight = maxHeight+1
      t = self.pdf.pages[1].crop((self.pdfWidth/2, self.pdfHeight * 0.61 , self.pdfWidth, maxHeight)).extract_text()
    maxHeight = maxHeight-1
    cropRegion = (self.pdfWidth/2, self.pdfHeight * 0.61 , self.pdfWidth, maxHeight)
    tableSettings = {
        "vertical_strategy": "text",
        "horizontal_strategy": "lines",
        "min_words_vertical": 1,
        "keep_blank_chars": True,
        "intersection_y_tolerance":15,
        "edge_min_length":15,
        "explicit_horizontal_lines":[maxHeight],
        "explicit_vertical_lines":[570]
        }
    outList = self.pdf.pages[1].crop(cropRegion).extract_table(tableSettings)
    outDict = {r[0]:r[1].replace('\n','') for r in outList}
    outDict['SeriesDescription'] = outDict['Image Set']
    outDict['AcquisitionDateTime'] = datetime.strptime(outDict['Scanned'], '%m/%d/%Y, %I:%M %p')
    return outDict

  def getMaxHeightCoord(self, coordInit, textMatch):
    t = None
    while not t or t.find(textMatch)==-1:
      t = secondPage.crop((secondPage.width/2, float(secondPage.height) * 0.61 , secondPage.width, max_y)).extract_text()
      max_y = max_y+1

def exctractPlanningFromPDF(PDFFilePath):
  stereotaxyReport = StereotaxyReport(PDFFilePath)
  return stereotaxyReport.getArcSettings()


def setDefaultResliceDriver(transformNode):
  # Get Reslice Driver Logic
  try:    
    logic = slicer.modules.volumereslicedriver.logic()
  except:
    qt.QMessageBox.warning(qt.QWidget(),'','Reslice Driver Module not Found')
    return
  # Settings
  redSettings    = {'node':slicer.util.getNode('vtkMRMLSliceNodeRed'),    'mode':6, 'angle':90 , 'flip':True}
  yellowSettings = {'node':slicer.util.getNode('vtkMRMLSliceNodeYellow'), 'mode':5, 'angle':180, 'flip':False}
  greenSettings  = {'node':slicer.util.getNode('vtkMRMLSliceNodeGreen'),  'mode':4, 'angle':180, 'flip':False}
  # Set
  for settings in [redSettings, yellowSettings, greenSettings]:
    logic.SetDriverForSlice(    transformNode,      settings['node'])
    logic.SetModeForSlice(      settings['mode'],   settings['node'])
    logic.SetRotationForSlice(  settings['angle'],  settings['node'])
    logic.SetFlipForSlice(      settings['flip'],   settings['node'])
      