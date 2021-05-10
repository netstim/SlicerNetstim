import sys
from SlicerNetstimLib.util import LeadDBSSubject
import slicer

subject = LeadDBSSubject(sys.argv[1])
subject.createAnatToFrameTransform()

slicer.util.exit()
