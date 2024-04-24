cmake_minimum_required(VERSION 3.13.4)

project(SlicerNetstim)

#-----------------------------------------------------------------------------
# Extension meta-information
set(EXTENSION_HOMEPAGE "https://github.com/netstim/SlicerNetstim")
set(EXTENSION_CATEGORY "Netstim")
set(EXTENSION_CONTRIBUTORS "Simon Oxenford (Charite Berlin)")
set(EXTENSION_DESCRIPTION "Netstim modules collection for deep brain stimulation applications")
set(EXTENSION_ICONURL "https://raw.githubusercontent.com/netstim/SlicerNetstim/master/logo.png")
set(EXTENSION_SCREENSHOTURLS "https://raw.githubusercontent.com/netstim/SlicerNetstim/master/LeadOR/Screenshots/Lead-OR_Scene.png")
set(EXTENSION_DEPENDS "") # Specified as a list or "NA" if no dependencies

#-----------------------------------------------------------------------------
# Extension dependencies
find_package(Slicer REQUIRED)
include(${Slicer_USE_FILE})

#-----------------------------------------------------------------------------
# Extension modules
add_subdirectory(LeadOR)
add_subdirectory(StereotacticPlan)
add_subdirectory(ImportAtlas)
add_subdirectory(WarpDrive)
add_subdirectory(NetstimPreferences)
add_subdirectory(FiducialRegistrationVariableRBF)
add_subdirectory(CompositeToGridTransform)
add_subdirectory(ImportACPCAutodetect)
add_subdirectory(CurveToBundle)
## NEXT_MODULE

#-----------------------------------------------------------------------------
include(${Slicer_EXTENSION_GENERATE_CONFIG})
include(${Slicer_EXTENSION_CPACK})
