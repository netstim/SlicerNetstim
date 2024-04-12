import qt
import vtk
from slicer.util import VTKObservationMixin
import json
import slicer

import CurveToBundle
class MultiHandleSliderWidget(qt.QSlider, VTKObservationMixin):

    def __init__(self):
        qt.QSlider.__init__(self)
        VTKObservationMixin.__init__(self)

        self.setOrientation(qt.Qt.Horizontal)
        self.setTickPosition(qt.QSlider.TicksBelow)
        self.setTickInterval(25)
        self.setSingleStep(1)
        self.setMaximum(100)
        self.setMinimum(0)

        # hide default handle
        self.setStyleSheet("""
                           QSlider::handle:horizontal {background-color:rgba(255, 255, 255, 0);}
                           QSlider {height: 40px;}
                           """)

        self._parameterNode = None
        self._parameterNodeObserverTag = None

        self._mouseOffset = 0
        self._shouldMoveHandle = False
        self._previouslyClickedPoint = -1

        self._addRemoveTimer = qt.QTimer()
        self._addRemoveTimer.setSingleShot(True)

    def setParameterNode(self, parameterNode):
        if self._parameterNode:
            self._parameterNode.RemoveObserver(self._parameterNodeObserverTag)
        self._parameterNode = parameterNode
        if self._parameterNode:
            self._parameterNodeObserverTag = self._parameterNode.AddObserver(vtk.vtkCommand.ModifiedEvent, self.updateFromParameterNode)
        self.updateFromParameterNode()

    def updateFromParameterNode(self, caller=None, event=None):
        if self._parameterNode is not None and self._parameterNode.GetParameter("Waypoints"):
            waypoints = json.loads(self._parameterNode.GetParameter("Waypoints"))
            maxSpread = int(self._parameterNode.GetParameter("MaxSpread"))
            waypoints = [{'position': x['position'], 'spread': min(x['spread'],maxSpread)} for x in waypoints]
            self._parameterNode.SetParameter("Waypoints", json.dumps(waypoints))
            self.update()

    def getWaypointsValues(self):
        return [x['position'] for x in json.loads(self._parameterNode.GetParameter("Waypoints"))]

    def getWaypointsPositionsSpreads(self):
        maxSpread = float(self._parameterNode.GetParameter("MaxSpread"))
        waypoints = json.loads(self._parameterNode.GetParameter("Waypoints"))
        return ([x['position'] for x in waypoints], [int(x['spread']/maxSpread*255) for x in waypoints])

    def removeNthWaypoint(self, n):
        if n is not None:
            waypoints = json.loads(self._parameterNode.GetParameter("Waypoints"))
            if len(waypoints) == 1:
                return
            waypoints.pop(n)
            self._parameterNode.SetParameter("WaypointIndex", str(max(0, n-1)))
            self._parameterNode.SetParameter("Waypoints", json.dumps(waypoints))

    def addWaypoint(self, pos):
        waypoints = json.loads(self._parameterNode.GetParameter("Waypoints"))
        positions = [x['position'] for x in waypoints]
        spreads = [x['spread'] for x in waypoints]
        spread = CurveToBundle.CurveToBundleLogic().getSpreadForNewPosition(positions, spreads, pos)
        waypoints.append({'position': pos, 'spread': spread})
        self._parameterNode.SetParameter("Waypoints", json.dumps(waypoints))
        self._parameterNode.SetParameter("WaypointIndex", str(len(waypoints)-1))

    def setNthWaypointValue(self, n, value):
        waypoints = json.loads(self._parameterNode.GetParameter("Waypoints"))
        waypoints[n]['position'] = value
        self._parameterNode.SetParameter("Waypoints", json.dumps(waypoints))

    def paintEvent(self, event):
        qt.QSlider.paintEvent(self, event)
        painter = qt.QPainter(self)
        painter.setRenderHint(qt.QPainter.Antialiasing)

        opt = qt.QStyleOptionSlider()
        self.initStyleOption(opt)   
        
        groove_rect = self.style().subControlRect(qt.QStyle.CC_Slider, opt, self.style().SC_SliderGroove)
        groove_length = groove_rect.width() 
        groove_start = groove_rect.left() 

        idx = int(self._parameterNode.GetParameter("WaypointIndex"))
        otherPen = qt.Qt.NoPen if self._parameterNode.GetParameter("SpreadModify") == "Selected" else qt.QPen()
        for i,(pos,spread) in enumerate(zip(*self.getWaypointsPositionsSpreads())):
            handle_pos = groove_start + int(groove_length * (pos - self.minimum) / (self.maximum - self.minimum))
            handle_center = qt.QPointF(handle_pos, groove_rect.center().y()) 
            handle_radius = self.style().pixelMetric(qt.QStyle.PM_SliderLength) / 2
            handle_rect = qt.QRect(handle_center.x() - handle_radius, handle_center.y() - handle_radius, 2 * handle_radius, 2 * handle_radius)
            painter.setBrush(qt.QColor(*PARULA[spread]))
            painter.setPen(qt.QPen() if i==idx else otherPen)
            painter.drawEllipse(handle_rect)

    def mousePressEvent(self, event):
        if event.button() != qt.Qt.LeftButton:
            return
        shouldInsertOrDelete = self._addRemoveTimer.isActive()
        self._addRemoveTimer.start(250)
        opt = qt.QStyleOptionSlider()
        self.initStyleOption(opt)  
        groove_rect = self.style().subControlRect(qt.QStyle.CC_Slider, opt, self.style().SC_SliderGroove)
        for i, handle in enumerate(self.getWaypointsValues()):
            handle_pos = groove_rect.left() + int(groove_rect.width() * (handle - self.minimum) / (self.maximum - self.minimum))
            handle_center = qt.QPointF(handle_pos, groove_rect.center().y())
            handle_radius = self.style().pixelMetric(qt.QStyle.PM_SliderLength) / 2
            handle_rect = qt.QRect(handle_center.x() - handle_radius, handle_center.y() - handle_radius, 2 * handle_radius, 2 * handle_radius)
            if handle_rect.contains(event.pos()):
                if shouldInsertOrDelete:
                    self.removeNthWaypoint(i)
                else:
                    self._parameterNode.SetParameter("WaypointIndex", str(i))
                    self._mouseOffset = event.pos().x() - handle_center.x()
                    qt.QToolTip.showText(event.globalPos(), '%d'%handle)
                    self._shouldMoveHandle = (i == self._previouslyClickedPoint)
                return
        self._shouldMoveHandle = False
        if shouldInsertOrDelete:
            self.addWaypoint(self.minimum + (event.pos().x() - groove_rect.left()) / groove_rect.width() * (self.maximum - self.minimum))

    def mouseMoveEvent(self, event):
        if not self._shouldMoveHandle:
            return
        opt = qt.QStyleOptionSlider()
        self.initStyleOption(opt) 
        idx = int(self._parameterNode.GetParameter("WaypointIndex"))
        if idx >= 0:
            groove_rect = self.style().subControlRect(qt.QStyle.CC_Slider, opt, self.style().SC_SliderGroove)
            handle_pos = event.pos().x() - self._mouseOffset
            handle_pos = max(handle_pos, groove_rect.left())
            handle_pos = min(handle_pos, groove_rect.right())
            value = self.minimum + (handle_pos - groove_rect.left()) / groove_rect.width() * (self.maximum+0.5 - self.minimum) # +0.5 to get to 100
            qt.QToolTip.showText(event.globalPos(), '%d'%value)
            self.setNthWaypointValue(idx, value)
            self.update()

    def mouseReleaseEvent(self, event):
        self._previouslyClickedPoint = int(self._parameterNode.GetParameter("WaypointIndex"))



PARULA = [[ 62,    39,   169],
   [ 63,    39,   172],
   [ 63,    40,   175],
   [ 64,    41,   178],
   [ 64,    42,   181],
   [ 65,    43,   184],
   [ 65,    44,   187],
   [ 65,    45,   189],
   [ 66,    46,   192],
   [ 66,    47,   195],
   [ 67,    48,   198],
   [ 67,    49,   200],
   [ 68,    50,   203],
   [ 68,    51,   206],
   [ 69,    53,   209],
   [ 69,    54,   211],
   [ 69,    55,   214],
   [ 70,    56,   216],
   [ 70,    57,   218],
   [ 70,    58,   220],
   [ 70,    60,   223],
   [ 71,    61,   224],
   [ 71,    62,   226],
   [ 71,    64,   228],
   [ 71,    65,   230],
   [ 71,    67,   231],
   [ 72,    68,   233],
   [ 72,    69,   234],
   [ 72,    71,   236],
   [ 72,    72,   237],
   [ 72,    74,   238],
   [ 72,    75,   239],
   [ 72,    76,   241],
   [ 72,    78,   242],
   [ 72,    79,   243],
   [ 72,    81,   244],
   [ 72,    82,   245],
   [ 72,    83,   246],
   [ 72,    85,   247],
   [ 72,    86,   248],
   [ 72,    88,   248],
   [ 71,    89,   249],
   [ 71,    90,   250],
   [ 71,    92,   251],
   [ 71,    93,   251],
   [ 71,    95,   252],
   [ 70,    96,   252],
   [ 70,    97,   253],
   [ 69,    99,   253],
   [ 69,   100,   254],
   [ 68,   102,   254],
   [ 68,   103,   254],
   [ 67,   105,   255],
   [ 66,   106,   255],
   [ 65,   108,   255],
   [ 64,   109,   255],
   [ 63,   111,   256],
   [ 62,   112,   256],
   [ 61,   114,   256],
   [ 59,   115,   256],
   [ 58,   117,   256],
   [ 56,   118,   255],
   [ 54,   120,   255],
   [ 53,   121,   254],
   [ 51,   123,   254],
   [ 50,   124,   253],
   [ 49,   126,   253],
   [ 48,   127,   252],
   [ 47,   129,   251],
   [ 47,   130,   251],
   [ 47,   132,   250],
   [ 46,   133,   249],
   [ 46,   134,   249],
   [ 46,   136,   248],
   [ 46,   137,   247],
   [ 45,   138,   246],
   [ 45,   140,   245],
   [ 45,   141,   244],
   [ 45,   142,   243],
   [ 45,   143,   241],
   [ 44,   145,   240],
   [ 43,   146,   240],
   [ 42,   147,   239],
   [ 41,   149,   238],
   [ 40,   150,   237],
   [ 39,   151,   236],
   [ 39,   152,   235],
   [ 38,   154,   234],
   [ 38,   155,   233],
   [ 37,   156,   232],
   [ 37,   157,   232],
   [ 37,   158,   231],
   [ 36,   159,   230],
   [ 35,   161,   230],
   [ 35,   162,   229],
   [ 34,   163,   229],
   [ 33,   164,   228],
   [ 32,   165,   228],
   [ 31,   166,   227],
   [ 30,   167,   226],
   [ 29,   169,   225],
   [ 29,   170,   225],
   [ 28,   171,   224],
   [ 27,   172,   223],
   [ 26,   173,   222],
   [ 25,   174,   220],
   [ 23,   175,   219],
   [ 22,   176,   218],
   [ 20,   177,   217],
   [ 18,   178,   215],
   [ 16,   178,   214],
   [ 14,   179,   212],
   [ 11,   180,   211],
   [  8,   181,   209],
   [  6,   182,   208],
   [  4,   183,   206],
   [  2,   183,   205],
   [  1,   184,   203],
   [  0,   185,   202],
   [  0,   186,   200],
   [  0,   186,   198],
   [  1,   187,   197],
   [  2,   188,   195],
   [  4,   188,   193],
   [  6,   189,   192],
   [  9,   189,   190],
   [ 13,   190,   188],
   [ 16,   191,   187],
   [ 20,   191,   185],
   [ 23,   192,   183],
   [ 26,   192,   181],
   [ 29,   193,   180],
   [ 32,   193,   178],
   [ 35,   194,   176],
   [ 37,   194,   174],
   [ 39,   195,   173],
   [ 41,   195,   171],
   [ 43,   196,   169],
   [ 45,   197,   167],
   [ 46,   197,   165],
   [ 47,   198,   163],
   [ 49,   198,   161],
   [ 50,   199,   159],
   [ 51,   199,   157],
   [ 53,   200,   155],
   [ 54,   200,   153],
   [ 56,   201,   151],
   [ 57,   201,   149],
   [ 59,   202,   147],
   [ 61,   202,   144],
   [ 64,   203,   142],
   [ 66,   203,   140],
   [ 69,   204,   137],
   [ 72,   204,   135],
   [ 75,   204,   132],
   [ 78,   204,   130],
   [ 81,   205,   127],
   [ 85,   205,   125],
   [ 88,   205,   122],
   [ 91,   205,   120],
   [ 94,   205,   117],
   [ 97,   205,   114],
   [100,   206,   111],
   [104,   206,   108],
   [107,   206,   106],
   [111,   206,   103],
   [114,   205,   100],
   [118,   205,    97],
   [122,   205,    94],
   [125,   205,    92],
   [129,   205,    89],
   [133,   204,    86],
   [136,   204,    84],
   [140,   204,    81],
   [144,   203,    78],
   [147,   203,    75],
   [151,   203,    73],
   [154,   202,    70],
   [158,   202,    67],
   [161,   201,    65],
   [165,   201,    62],
   [168,   200,    60],
   [172,   200,    57],
   [175,   199,    55],
   [178,   198,    53],
   [182,   198,    51],
   [185,   197,    49],
   [188,   197,    47],
   [191,   196,    46],
   [194,   195,    44],
   [197,   195,    42],
   [200,   194,    41],
   [203,   193,    40],
   [206,   193,    40],
   [209,   192,    39],
   [212,   192,    39],
   [215,   191,    40],
   [217,   190,    40],
   [220,   190,    41],
   [223,   189,    41],
   [225,   189,    42],
   [228,   188,    43],
   [230,   188,    45],
   [233,   187,    46],
   [235,   187,    48],
   [237,   187,    51],
   [240,   187,    53],
   [242,   186,    55],
   [244,   186,    57],
   [246,   186,    59],
   [248,   187,    61],
   [250,   187,    62],
   [252,   188,    63],
   [253,   189,    62],
   [255,   190,    61],
   [255,   191,    60],
   [255,   192,    59],
   [255,   194,    58],
   [255,   195,    57],
   [255,   197,    56],
   [255,   198,    55],
   [255,   200,    54],
   [255,   201,    53],
   [255,   203,    52],
   [254,   204,    51],
   [254,   206,    50],
   [254,   207,    49],
   [253,   209,    48],
   [252,   210,    47],
   [252,   212,    47],
   [251,   214,    46],
   [250,   215,    45],
   [250,   217,    44],
   [249,   218,    43],
   [248,   220,    43],
   [248,   222,    42],
   [247,   223,    41],
   [247,   225,    40],
   [246,   226,    40],
   [246,   228,    39],
   [246,   229,    39],
   [246,   231,    38],
   [246,   233,    37],
   [246,   234,    36],
   [246,   236,    35],
   [246,   237,    34],
   [246,   239,    33],
   [247,   240,    32],
   [247,   242,    31],
   [247,   243,    30],
   [248,   245,    29],
   [248,   246,    27],
   [249,   247,    26],
   [249,   249,    24],
   [250,   250,    22],
   [250,   252,    21]]