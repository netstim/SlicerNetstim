#include "compositeToGridTransformCLP.h"

// ITK includes
#include <itkImage.h>

#include "SimpleITK.h"

namespace sitk = itk::simple;

// Use an anonymous namespace to keep class types and function names
// from colliding when module is used as shared object module.  Every
// thing should be in an anonymous namespace except for the module
// entry point, e.g. main()
//
namespace
{
void DoIt(sitk::Image *vectorField, sitk::Transform *compositeTransform)
{

  unsigned int i, imageLinearIndex;
  std::vector<double> physicalPoint, physicalPointTransformed;
  std::vector<unsigned int> size = vectorField->GetSize();
  float * buffer = vectorField->GetBufferAsFloat();
  std::vector<itk::int64_t> ijk {0,0,0};

  float numberOfVoxels = size[0] * size[1] * size[2];
  unsigned int voxelCount = 0;

  for(ijk[0]=0; ijk[0]<size[0]; ijk[0]=ijk[0]+1){
  for(ijk[1]=0; ijk[1]<size[1]; ijk[1]=ijk[1]+1){
  for(ijk[2]=0; ijk[2]<size[2]; ijk[2]=ijk[2]+1){

    physicalPoint = vectorField->TransformIndexToPhysicalPoint(ijk);
    physicalPointTransformed = compositeTransform->TransformPoint(physicalPoint);

    imageLinearIndex = ijk[0] + (size[0] * (ijk[1] + size[1] * ijk[2]));
    for (i=0; i<3; i++){
      buffer[3*imageLinearIndex+i] = physicalPointTransformed[i] - physicalPoint[i];
    }

    voxelCount++;
  }
  }
    std::cout << "<filter-progress>" << (voxelCount / numberOfVoxels) << "</filter-progress>" << std::endl << std::flush;
  }

}

} // end of anonymous namespace

int main( int argc, char * argv[] )
{
  PARSE_ARGS;

  bool saveToNode = outputDisplacementField.compare("None") != 0;
  bool saveToFile = !outputFileName.empty();

  if ((saveToNode && saveToFile) || (!saveToNode && !saveToFile))
  {
    std::cerr << "Specify either a MRML output node or an output file name" << std::endl;
    return EXIT_FAILURE;
  }

  // Read input
  sitk::Transform input = sitk::ReadTransform(inputCompositeTransform);

  // Create vector field
  sitk::ImageFileReader reader;
  reader.SetFileName(referenceVolume);
  sitk::Image &&referenceImage = reader.Execute();

  sitk::Image outputImage(referenceImage.GetSize(), sitk::sitkVectorFloat32);
  outputImage.SetOrigin(referenceImage.GetOrigin());
  outputImage.SetSpacing(referenceImage.GetSpacing());
  outputImage.SetDirection(referenceImage.GetDirection());

  // Apply
  std::cout << "<filter-comment>" << "Computing" << "</filter-comment>" << std::endl << std::flush;
  DoIt(&outputImage, &input);

  std::cout << "<filter-comment>" << "Saving" << "</filter-comment>" << std::endl << std::flush;
  sitk::WriteImage(outputImage, saveToNode ? outputDisplacementField : outputFileName);

  return EXIT_SUCCESS;
}
