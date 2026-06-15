#!/bin/bash
# ===========================================================================
# run_cfd.sh
# OpenFOAM pipeline for 5-blade quadcopter propeller CFD simulation.
# ===========================================================================

# Exit immediately if any command fails
set -e

# Clean up previous mesh/results if any
echo "=== Cleaning up previous run files ==="
rm -rf constant/polyMesh
rm -rf postProcessing
rm -f 0/cellLevel 0/pointLevel

# Scale propeller from mm to meters
echo "=== Scaling propeller geometry from mm to meters ==="
surfaceTransformPoints -scale "(0.001 0.001 0.001)" constant/triSurface/propeller_mm.stl constant/triSurface/propeller.stl

echo "=== [1/5] Running blockMesh ==="
blockMesh

echo "=== [2/5] Running surfaceFeatureExtract ==="
if [ ! -f system/surfaceFeaturesDict ]; then
    echo '/*--------------------------------*- C++ -*----------------------------------*\
  version:     2.0;
  format:      ascii;
  class:       dictionary;
  object:      surfaceFeaturesDict;
\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      surfaceFeaturesDict;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //
surfaces (propeller.stl);' > system/surfaceFeaturesDict
fi
surfaceFeatureExtract

echo "=== [3/5] Running snappyHexMesh ==="
snappyHexMesh -overwrite

echo "=== [4/5] Running renumberMesh ==="
renumberMesh -overwrite

echo "=== [5/5] Running simpleFoam ==="
simpleFoam
