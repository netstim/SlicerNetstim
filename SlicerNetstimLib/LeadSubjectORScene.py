import sys
from SlicerNetstimLib.util import LeadDBSSubject
import slicer

subject = LeadDBSSubject(sys.argv[2], sys.argv[1])
subject.createORScene()

slicer.util.exit()
