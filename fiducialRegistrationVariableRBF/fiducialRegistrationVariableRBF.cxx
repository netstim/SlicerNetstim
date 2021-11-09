#include "fiducialRegistrationVariableRBFCLP.h"

// ITK includes
#include <itkImage.h>
#include <itkImageFileWriter.h>

#include "SimpleITK.h"


namespace sitk = itk::simple;

// Use an anonymous namespace to keep class types and function names
// from colliding when module is used as shared object module.  Every
// thing should be in an anonymous namespace except for the module
// entry point, e.g. main()
//
namespace
{
  // Function to convert a point from std::vector to itk::Point
  itk::Point<double, 3> convertStdVectorToITKPoint(const std::vector<float> & vec)
  {
    itk::Point<double, 3> p;
    p[0] = vec[0];
    p[1] = vec[1];
    p[2] = vec[2];
    return p;
  }

  static float rbf_value (itk::Point<double, 3> * rbf_center, itk::Point<double, 3> * loc, float radius)
  {
    float r = rbf_center->EuclideanDistanceTo(*loc) / radius;
    float val = exp( -r*r );   
    return val;
  }

  void rbf_gauss_update_vf( 
    sitk::Image *vf, 
    float *coeff, 
    std::vector< itk::Point<double, 3> > * fixed_landmarks,
    float * adapt_radius)
  {
    unsigned int i, lidx;
    float rbf;
    unsigned int num_landmarks = fixed_landmarks->size();

    itk::Point<double, 3> physicalPointITK;
    std::vector<double> physicalPoint;

    std::vector<unsigned int> size = vf->GetSize();
    float * buffer = vf->GetBufferAsFloat();
    unsigned int linearIndex;
    std::vector<itk::int64_t> ijk {0,0,0};

    for(ijk[0]=0; ijk[0]<size[0]; ijk[0]=ijk[0]+1){
    for(ijk[1]=0; ijk[1]<size[1]; ijk[1]=ijk[1]+1){
    for(ijk[2]=0; ijk[2]<size[2]; ijk[2]=ijk[2]+1){

      physicalPoint = vf->TransformIndexToPhysicalPoint(ijk);
      for (i=0; i<3; i++){
        physicalPointITK[i] = physicalPoint[i];
      }

      linearIndex = ijk[0] + (size[0] * (ijk[1] + size[1] * ijk[2]));

      for (lidx=0; lidx < num_landmarks; lidx++) {
        
        rbf = rbf_value(&fixed_landmarks->at(lidx), &physicalPointITK, adapt_radius[lidx]);

        for (i=0; i<3; i++){
          buffer[3*linearIndex+i] += coeff[3*lidx+i] * rbf;
        }
      }

    }
    }
    }

  }

  static void bspline_rbf_find_coeffs(float *coeff, 
    std::vector< itk::Point<double, 3> > * fixed_landmarks, 
    std::vector< itk::Point<double, 3> > * moving_landmarks,
    float * adapt_radius,
    float rbf_radius,
    float stiffness)
  {
    float rbfv1, rbfv2;
    int i, j, k, d;
    float rbf_prefactor, reg_term, r2, tmp;
    unsigned int num_landmarks = fixed_landmarks->size();

    typedef vnl_matrix <double> Vnl_matrix;
    typedef vnl_svd <double> SVDSolverType;
    Vnl_matrix A, b;

    A.set_size (3 * num_landmarks, 3 * num_landmarks);
    A.fill(0.);

    b.set_size (3 * num_landmarks, 1);
    b.fill (0.0);

    // right-hand side
    for (i=0; i<num_landmarks; i++) {
	  for (j=0; j<num_landmarks; j++) {
	    rbfv1 = rbf_value (&fixed_landmarks->at(i), &fixed_landmarks->at(j), adapt_radius[j]);
		
	    for (d=0;d<3;d++) {
		    b (3*i +d, 0) -= rbfv1 * (fixed_landmarks->at(j)[d] - moving_landmarks->at(j)[d]);
	    }
	  }
    }

    // matrix
    for (i = 0; i < num_landmarks; i++) {
	  for (j = 0; j < num_landmarks; j++) {
	    tmp = 0;
	    for (k = 0; k < num_landmarks; k++) {

		  rbfv1 = rbf_value (&fixed_landmarks->at(k), &fixed_landmarks->at(i), adapt_radius[k]);
		  rbfv2 = rbf_value (&fixed_landmarks->at(k), &fixed_landmarks->at(j), adapt_radius[k]);

		  tmp += rbfv1*rbfv2;
	    }
	    for (d=0;d<3;d++){
		    A(3*i+d, 3*j+d) = tmp;
	    }
	  }
    }

    //add regularization terms to the matrix
    rbf_prefactor = sqrt(M_PI/2.)*sqrt(M_PI/2.)*sqrt(M_PI/2.)/rbf_radius;
    for (d=0;d<3;d++) {
	  for (i=0;i<num_landmarks;i++) {
	    for (j=0;j<num_landmarks;j++) {
        tmp = A(3*i+d, 3*j+d);
        reg_term = 0.;			
        if (i==j) {
            reg_term = rbf_prefactor * 15.;
        }
        else
        {
          // r2 = sq distance between landmarks i,j in mm
          float d = fixed_landmarks->at(i).EuclideanDistanceTo(fixed_landmarks->at(j));
          r2 = (d * d) / (adapt_radius[i] * adapt_radius[j]);
          reg_term = rbf_prefactor * exp(-r2/2.) * (-10 + (r2-5.)*(r2-5.));
        }
        A (3*i+d,3*j+d) = tmp + reg_term * stiffness;
      } 
	  }
    }

    SVDSolverType svd (A, 1e-6);
    Vnl_matrix x = svd.solve (b);

    for (i=0; i<3*num_landmarks; i++) {
	    coeff[i] = x(i,0);
    }
  }


} // end of anonymous namespace

int main( int argc, char * argv[] )
{
  PARSE_ARGS;

  // Checking conditions.

  if( fixedFiducials.size() <= 0 || movingFiducials.size() <= 0 ||
    fixedFiducials.size() != movingFiducials.size() )
  {
    std::cerr << "Fixed and moving landmark lists must be of the same size "
      << "and contain at least one point" << std::endl;
  }

  unsigned long numFiducials = fixedFiducials.size();

  if(outputDisplacementField.empty())
  {
    std::cerr << "An output transform must be specified" << std::endl;
  }

  unsigned long numRBFRadius = RBFRadius.size();

  if (numRBFRadius > 1 && numRBFRadius != numFiducials){
    std::cerr << "The number of RBF radius specified is more than one but does not match the number of fiducials.\n"
              << "Specify one RBF radius to use as a global parameter or multiple comma separated values corresponding to each fiducial.\n";
    return EXIT_FAILURE;
  }

  float * adaptRadius = (float *)malloc(numFiducials*sizeof(float));
  float RBFRadiusMean = 0.0;
  for (unsigned long i = 0; i<numFiducials; i++){
    if (numRBFRadius == 1){
      adaptRadius[i] = RBFRadius[0];
    }else{
      adaptRadius[i] = RBFRadius[i];
    }
    RBFRadiusMean += adaptRadius[i];
  }

  RBFRadiusMean = RBFRadiusMean / numFiducials;


  typedef std::vector< itk::Point<double, 3> > PointList;

  PointList fixedPoints(fixedFiducials.size());
  PointList movingPoints(movingFiducials.size());

  // Convert both points lists to ITK points

  std::transform(fixedFiducials.begin(), fixedFiducials.end(),
    fixedPoints.begin(),
    convertStdVectorToITKPoint);

  std::transform(movingFiducials.begin(), movingFiducials.end(),
    movingPoints.begin(),
    convertStdVectorToITKPoint);

  // BSpline coeff

  float * coeff = (float*) malloc (3 * fixedPoints.size() * sizeof(float));
  bspline_rbf_find_coeffs (coeff, &fixedPoints, &movingPoints, adaptRadius, RBFRadiusMean, stiffness);

  // Create vector field
  sitk::ImageFileReader reader;
  reader.SetFileName(referenceVolume);
  sitk::Image &&referenceImage = reader.Execute();

  sitk::PixelIDValueEnum pixelType = sitk::sitkVectorFloat32;

  sitk::Image output(referenceImage.GetSize(), pixelType);
  output.SetOrigin(referenceImage.GetOrigin());
  output.SetSpacing(referenceImage.GetSpacing());
  output.SetDirection(referenceImage.GetDirection());

  rbf_gauss_update_vf (&output, coeff, &fixedPoints, adaptRadius);

  sitk::WriteImage(output, outputDisplacementField);

  return EXIT_SUCCESS;
}
