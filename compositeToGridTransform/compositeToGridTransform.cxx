#include "compositeToGridTransformCLP.h"

// MRML includes
#include <vtkMRMLTransformNode.h>
#include <vtkMRMLScalarVolumeNode.h>
#include <vtkMRMLVolumeArchetypeStorageNode.h>
#include <vtkMRMLTransformStorageNode.h>

// VTK includes
#include <vtkGeneralTransform.h>
#include <vtkImageData.h>
#include <vtkMatrix4x4.h>
#include <vtkOrientedGridTransform.h>
#include <vtkOrientedGridTransform.h>

// Use an anonymous namespace to keep class types and function names
// from colliding when module is used as shared object module.  Every
// thing should be in an anonymous namespace except for the module
// entry point, e.g. main()
//
namespace
{
void GetTransformedPointSamplesAsVectorImage(vtkImageData* vectorImage, vtkMRMLTransformNode* inputTransformNode, vtkMatrix4x4* ijkToRAS)
{
  vtkNew<vtkGeneralTransform> inputTransform;
  inputTransformNode->GetTransformFromWorld(inputTransform.GetPointer());

  // The orientation of the volume cannot be set in the image
  // therefore the volume will not appear in the correct position
  // if the direction matrix is not identity.
  vectorImage->AllocateScalars(VTK_FLOAT, 3);

  double point_RAS[4] = { 0, 0, 0, 1 };
  double transformedPoint_RAS[4] = { 0, 0, 0, 1 };
  double point_IJK[4] = { 0, 0, 0, 1 };
  float* voxelPtr = static_cast<float*>(vectorImage->GetScalarPointer());
  int* extent = vectorImage->GetExtent();
  int* dim = vectorImage->GetDimensions();
  float numberOfVoxels = dim[0] * dim[1] * dim[2];
  uint voxelCount = 0;
  for (point_IJK[2] = extent[4]; point_IJK[2] <= extent[5]; point_IJK[2]++)
  {
    for (point_IJK[1] = extent[2]; point_IJK[1] <= extent[3]; point_IJK[1]++)
    {
      for (point_IJK[0] = extent[0]; point_IJK[0] <= extent[1]; point_IJK[0]++)
      {
        ijkToRAS->MultiplyPoint(point_IJK, point_RAS);

        inputTransform->TransformPoint(point_RAS, transformedPoint_RAS);

        // store the pointDislocationVector_RAS components in the image
        *(voxelPtr++) = static_cast<float>(transformedPoint_RAS[0] - point_RAS[0]);
        *(voxelPtr++) = static_cast<float>(transformedPoint_RAS[1] - point_RAS[1]);
        *(voxelPtr++) = static_cast<float>(transformedPoint_RAS[2] - point_RAS[2]);

        voxelCount++;
        if (voxelCount % 10000 == 0)
        {
          std::cout << "<filter-progress>" << (voxelCount / numberOfVoxels) << "</filter-progress>" << std::endl << std::flush;
        }
      }
    }
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

  vtkNew<vtkMRMLScalarVolumeNode> referenceVolumeNode;
  if (!referenceVolume.empty())
  {
    vtkNew<vtkMRMLVolumeArchetypeStorageNode> storageNode;
    storageNode->SetFileName(referenceVolume.c_str());
    if (!storageNode->ReadData(referenceVolumeNode))
    {
      std::cerr << "Failed to read reference volume from file " << std::endl;
      return EXIT_FAILURE;
    }
  }

  vtkNew<vtkMRMLTransformNode> compositeTransformNode;
  if (!inputCompositeTransform.empty())
  {
    vtkNew<vtkMRMLTransformStorageNode> storageNode;
    storageNode->SetFileName(inputCompositeTransform.c_str());
    if (!storageNode->ReadData(compositeTransformNode))
    {
      std::cerr << "Failed to read composite transform from file " << std::endl;
      return EXIT_FAILURE;
    }
  }

  // Create a grid transform
  vtkSmartPointer<vtkMRMLTransformNode> outputGridTransformNode;
  outputGridTransformNode = vtkSmartPointer<vtkMRMLTransformNode>::New();

  vtkOrientedGridTransform* outputGridTransform = vtkOrientedGridTransform::SafeDownCast(
    outputGridTransformNode->GetTransformToParentAs("vtkOrientedGridTransform",
    false /* don't report conversion error */,
    true /* we would like to modify the transform */));
  if (outputGridTransform == nullptr)
  {
    // we cannot reuse the existing transform, create a new one
    vtkNew<vtkOrientedGridTransform> newOutputGridTransform;
    outputGridTransform = newOutputGridTransform.GetPointer();
    outputGridTransformNode->SetAndObserveTransformFromParent(outputGridTransform);
  }
  // Create/get displacement field image
  vtkImageData* outputVolume = outputGridTransform->GetDisplacementGrid();
  if (outputVolume == nullptr)
  {
    vtkNew<vtkImageData> newOutputVolume;
    outputVolume = newOutputVolume.GetPointer();
    outputGridTransform->SetDisplacementGridData(outputVolume);
  }
  // Update geometry based on reference image
  vtkNew<vtkMatrix4x4> ijkToRas; // RAS refers to world
  if (referenceVolumeNode != nullptr)
  {
    referenceVolumeNode->GetIJKToRASMatrix(ijkToRas.GetPointer());
    vtkNew<vtkMatrix4x4> rasToWorld;
    if (vtkMRMLTransformNode::GetMatrixTransformBetweenNodes(referenceVolumeNode->GetParentTransformNode(), nullptr /* world */, rasToWorld.GetPointer()))
    {
      vtkMatrix4x4::Multiply4x4(rasToWorld.GetPointer(), ijkToRas.GetPointer(), ijkToRas.GetPointer());
    }
    else
    {
      std::cerr << "vtkSlicerTransformLogic::ConvertToGridTransform: non-linearly transformed reference volume" \
       " is not supported. Harden or remove the transform from of the reference volume." << std::endl;
      return EXIT_FAILURE;
    }
    double origin[3] = { 0, 0, 0 };
    double spacing[3] = { 1, 1, 1 };
    vtkNew<vtkMatrix4x4> ijkToRasDirection; // normalized direction matrix
    for (int c = 0; c < 3; c++)
    {
      origin[c] = ijkToRas->GetElement(c, 3);
      spacing[c] = sqrt(ijkToRas->Element[0][c] * ijkToRas->Element[0][c]
        + ijkToRas->Element[1][c] * ijkToRas->Element[1][c]
        + ijkToRas->Element[2][c] * ijkToRas->Element[2][c]);
      if (spacing[c] == 0)
      {
        // Prevent division by zero in case there is a projection matrix is in the transform chain
        spacing[c] = 1.0;
      }
      for (int r = 0; r < 3; r++)
      {
        ijkToRasDirection->SetElement(r, c, ijkToRas->GetElement(r, c) / spacing[c]);
      }
    }
    outputVolume->SetExtent(referenceVolumeNode->GetImageData()->GetExtent());
    outputVolume->SetOrigin(origin);
    outputVolume->SetSpacing(spacing);
    // vtkImageData cannot store directions, therefore that has to be set in the grid transform
    outputGridTransform->SetGridDirectionMatrix(ijkToRasDirection.GetPointer());
  }


  std::cout << "<filter-comment>" << "Computing" << "</filter-comment>" << std::endl << std::flush;
  GetTransformedPointSamplesAsVectorImage(outputVolume, compositeTransformNode, ijkToRas.GetPointer());

  std::cout << "<filter-comment>" << "Writing" << "</filter-comment>" << std::endl << std::flush;
  vtkNew<vtkMRMLTransformStorageNode> storageNode;
  storageNode->SetFileName(saveToNode ? outputDisplacementField.c_str() : outputFileName.c_str());
  if (!storageNode->WriteData(outputGridTransformNode))
  {
    std::cerr << "Failed to write output transform" << std::endl;
    return EXIT_FAILURE;
  }

  return EXIT_SUCCESS;
}
