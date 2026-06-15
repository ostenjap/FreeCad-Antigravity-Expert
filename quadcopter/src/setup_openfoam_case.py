"""
setup_openfoam_case.py
======================
Automated OpenFOAM case builder for the 5-blade quadcopter propeller.
Generates all necessary dictionary files (0/, constant/, system/)
with valid FoamFile headers, and exports the propeller STL model.
"""

import os
import pathlib
import sys
import math

# Resolve project root so we can import generate_propeller
ROOT = pathlib.Path(__file__).resolve().parents[2]   # CAD-Expert/
sys.path.insert(0, str(ROOT / "quadcopter" / "src"))

try:
    import cadquery as cq
    from generate_propeller import build_propeller
    HAS_CQ = True
except ImportError:
    HAS_CQ = False

# Output CFD Case directory
CASE_DIR = ROOT / "quadcopter" / "cfd" / "propeller_case"

# ---------------------------------------------------------------------------
# Dictionary Contents with valid FoamFile headers
# ---------------------------------------------------------------------------

U_CONTENT = """/*--------------------------------*- C++ -*----------------------------------*\\
  version:     2.0;
  format:      ascii;
  class:       volVectorField;
  object:      U;
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       volVectorField;
    object      U;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

dimensions      [0 1 -1 0 0 0 0];

internalField   uniform (0 0 0);

boundaryField
{
    inlet
    {
        type            fixedValue;
        value           uniform (0 0 0);
    }
    outlet
    {
        type            pressureInletOutletVelocity;
        value           uniform (0 0 0);
    }
    propeller
    {
        type            noSlip;
    }
    tunnelWalls
    {
        type            slip;
    }
}
"""

P_CONTENT = """/*--------------------------------*- C++ -*----------------------------------*\\
  version:     2.0;
  format:      ascii;
  class:       volScalarField;
  object:      p;
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       volScalarField;
    object      p;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

dimensions      [0 2 -2 0 0 0 0];

internalField   uniform 0;

boundaryField
{
    inlet
    {
        type            zeroGradient;
    }
    outlet
    {
        type            fixedValue;
        value           uniform 0;
    }
    propeller
    {
        type            zeroGradient;
    }
    tunnelWalls
    {
        type            zeroGradient;
    }
}
"""

K_CONTENT = """/*--------------------------------*- C++ -*----------------------------------*\\
  version:     2.0;
  format:      ascii;
  class:       volScalarField;
  object:      k;
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       volScalarField;
    object      k;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

dimensions      [0 2 -2 0 0 0 0];

internalField   uniform 0.06;

boundaryField
{
    inlet
    {
        type            fixedValue;
        value           uniform 0.06;
    }
    outlet
    {
        type            inletOutlet;
        inletValue      uniform 0.06;
        value           uniform 0.06;
    }
    propeller
    {
        type            kqRWallFunction;
        value           uniform 0.06;
    }
    tunnelWalls
    {
        type            slip;
    }
}
"""

OMEGA_CONTENT = """/*--------------------------------*- C++ -*----------------------------------*\\
  version:     2.0;
  format:      ascii;
  class:       volScalarField;
  object:      omega;
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       volScalarField;
    object      omega;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

dimensions      [0 0 -1 0 0 0 0];

internalField   uniform 400.0;

boundaryField
{
    inlet
    {
        type            fixedValue;
        value           uniform 400.0;
    }
    outlet
    {
        type            inletOutlet;
        inletValue      uniform 400.0;
        value           uniform 400.0;
    }
    propeller
    {
        type            omegaWallFunction;
        value           uniform 400.0;
    }
    tunnelWalls
    {
        type            slip;
    }
}
"""

NUT_CONTENT = """/*--------------------------------*- C++ -*----------------------------------*\\
  version:     2.0;
  format:      ascii;
  class:       volScalarField;
  object:      nut;
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       volScalarField;
    object      nut;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

dimensions      [0 2 -1 0 0 0 0];

internalField   uniform 0.0001;

boundaryField
{
    inlet
    {
        type            calculated;
        value           uniform 0.0001;
    }
    outlet
    {
        type            calculated;
        value           uniform 0.0001;
    }
    propeller
    {
        type            nutkWallFunction;
        value           uniform 0.0001;
    }
    tunnelWalls
    {
        type            slip;
    }
}
"""

TRANSPORT_PROPERTIES = """/*--------------------------------*- C++ -*----------------------------------*\\
  version:     2.0;
  format:      ascii;
  class:       dictionary;
  object:      transportProperties;
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      transportProperties;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

transportModel  Newtonian;

nu              [0 2 -1 0 0 0 0] 1.5e-05;
rho             [1 -3 0 0 0 0 0] 1.225;
"""

TURBULENCE_PROPERTIES = """/*--------------------------------*- C++ -*----------------------------------*\\
  version:     2.0;
  format:      ascii;
  class:       dictionary;
  object:      turbulenceProperties;
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      turbulenceProperties;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

simulationType  RAS;

RAS
{
    RASModel        kOmegaSST;
    turbulence      on;
    printCoeffs     on;
}
"""

MRF_PROPERTIES = """/*--------------------------------*- C++ -*----------------------------------*\\
  version:     2.0;
  format:      ascii;
  class:       dictionary;
  object:      MRFProperties;
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      MRFProperties;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

MRF1
{
    cellZone        rotorZone;
    active          true;

    origin          (0 0 0);
    axis            (0 0 1);
    omega           %(omega).3f; // %(rpm).0f RPM in rad/s
}
"""


def build_mrf_properties(rpm: float = 8000.0) -> str:
    """Render the MRFProperties dict with omega computed from rpm."""
    omega = rpm * 2.0 * math.pi / 60.0
    return MRF_PROPERTIES % {"omega": omega, "rpm": rpm}

CONTROL_DICT = """/*--------------------------------*- C++ -*----------------------------------*\\
  version:     2.0;
  format:      ascii;
  class:       dictionary;
  object:      controlDict;
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      controlDict;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

application     simpleFoam;
startFrom       startTime;
startTime       0;
stopAt          endTime;
endTime         1000;
deltaT          1;
writeControl    timeStep;
writeInterval   100;
purgeWrite      2;
writeFormat     ascii;
writePrecision  6;
writeCompression off;
timeFormat      general;
timePrecision   6;
runTimeModifiable true;

functions
{
    forces
    {
        type            forces;
        libs            (forces);
        writeControl    timeStep;
        writeInterval   1;
        patches         (propeller);
        rho             rhoInf;
        rhoInf          1.225;
        coordinateSystem
        {
            origin          (0 0 0);
            rotation
            {
                type            axes;
                e3              (0 0 1);
                e1              (1 0 0);
            }
        }
        log             true;
    }
}
"""

FV_SCHEMES = """/*--------------------------------*- C++ -*----------------------------------*\\
  version:     2.0;
  format:      ascii;
  class:       dictionary;
  object:      fvSchemes;
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      fvSchemes;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

ddtSchemes
{
    default         steadyState;
}

gradSchemes
{
    default         Gauss linear;
    grad(U)         cellLimited Gauss linear 1;
}

divSchemes
{
    default         none;
    div(phi,U)      bounded Gauss upwind;
    div(phi,k)      bounded Gauss upwind;
    div(phi,omega)  bounded Gauss upwind;
    div((nuEff*dev2(T(grad(U))))) Gauss linear;
}

laplacianSchemes
{
    default         Gauss linear corrected;
}

interpolationSchemes
{
    default         linear;
}

snGradSchemes
{
    default         corrected;
}
"""

FV_SOLUTION = """/*--------------------------------*- C++ -*----------------------------------*\\
  version:     2.0;
  format:      ascii;
  class:       dictionary;
  object:      fvSolution;
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      fvSolution;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

solvers
{
    p
    {
        solver          GAMG;
        tolerance       1e-06;
        relTol          0.1;
        smoother        GaussSeidel;
    }

    U
    {
        solver          smoothSolver;
        smoother        GaussSeidel;
        tolerance       1e-08;
        relTol          0.1;
    }

    "(k|omega)"
    {
        solver          smoothSolver;
        smoother        GaussSeidel;
        tolerance       1e-08;
        relTol          0.1;
    }
}

SIMPLE
{
    nNonOrthogonalCorrectors 0;
    consistent      yes;
    residualControl
    {
        p               1e-4;
        U               1e-4;
        k               1e-4;
        omega           1e-4;
    }
}

relaxationFactors
{
    fields
    {
        p               0.3;
    }
    equations
    {
        U               0.7;
        k               0.7;
        omega           0.7;
    }
}
"""

BLOCK_MESH_DICT = """/*--------------------------------*- C++ -*----------------------------------*\\
  version:     2.0;
  format:      ascii;
  class:       dictionary;
  object:      blockMeshDict;
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      blockMeshDict;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

convertToMeters 1;

vertices
(
    (-0.5 -0.5 -1.0) // 0
    ( 0.5 -0.5 -1.0) // 1
    ( 0.5  0.5 -1.0) // 2
    (-0.5  0.5 -1.0) // 3
    (-0.5 -0.5  0.5) // 4
    ( 0.5 -0.5  0.5) // 5
    ( 0.5  0.5  0.5) // 6
    (-0.5  0.5  0.5) // 7
);

blocks
(
    hex (0 1 2 3 4 5 6 7) (40 40 60) simpleGrading (1 1 1)
);

edges
(
);

boundary
(
    inlet
    {
        type patch;
        faces
        (
            (4 5 6 7)
        );
    }
    outlet
    {
        type patch;
        faces
        (
            (0 3 2 1)
        );
    }
    tunnelWalls
    {
        type wall;
        faces
        (
            (0 1 5 4)
            (1 2 6 5)
            (2 3 7 6)
            (3 0 4 7)
        );
    }
);

mergePatchPairs
(
);
"""

SNAPPY_HEX_MESH_DICT = """/*--------------------------------*- C++ -*----------------------------------*\\
  version:     2.0;
  format:      ascii;
  class:       dictionary;
  object:      snappyHexMeshDict;
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      snappyHexMeshDict;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

castellatedMesh true;
snap            true;
addLayers       true;

geometry
{
    propeller
    {
        type triSurfaceMesh;
        file "propeller.stl";
    }

    rotorZone
    {
        type searchableCylinder;
        point1 (0 0 -0.02);
        point2 (0 0 0.02);
        radius 0.135;
    }
}

castellatedMeshControls
{
    maxLocalCells 1000000;
    maxGlobalCells 2000000;
    minRefinementCells 100;
    maxLoadUnbalance 0.10;
    nCellsBetweenLevels 3;

    features
    (
        {
            file "propeller.eMesh";
            level 6;
        }
    );

    refinementSurfaces
    {
        propeller
        {
            level (5 7);
        }

        rotorZone
        {
            level (4 4);
            cellZone rotorZone;
            faceZone rotorZone;
            cellZoneInside inside;
        }
    }

    resolveFeatureAngle 30;

    refinementRegions
    {
        rotorZone
        {
            mode inside;
            levels ((1e15 4));
        }
    }

    locationInMesh (0.4 0.4 0.4);
    allowFreeStandingZoneFaces true;
}

snapControls
{
    nSmoothPatch 3;
    tolerance 2.0;
    nSolveIter 30;
    nRelaxIter 5;
    nFeatureSnapIter 5;
}

addLayersControls
{
    relativeSizes true;
    layers
    {
        propeller
        {
            nSurfaceLayers 3;
        }
    }
    expansionRatio 1.2;
    finalLayerThickness 0.3;
    minThickness 0.05;
    nGrow 1;
    featureAngle 60;
    slipFeatureAngle 30;
    nRelaxIter 5;
    nSmoothSurfaceNormals 1;
    nSmoothNormals 3;
    nSmoothThickness 10;
    maxFaceThicknessRatio 0.5;
    maxThicknessToMedialRatio 0.3;
    minMedialAxisAngle 90;
    nBufferCellsNoExtrude 0;
    nLayerIter 50;
}

meshQualityControls
{
    maxNonOrtho         65;
    maxBoundarySkewness 20;
    maxInternalSkewness 4;
    maxConcave          80;
    minFlatness         0.5;
    minVol              1e-13;
    minArea             -1;
    minTwist            0.02;
    minDeterminant      0.001;
    minFaceWeight       0.05;
    minVolRatio         0.01;
    minTriangleTwist    -1;
    nSmoothScale        4;
    errorReduction      0.75;
    minTetQuality       -1e30;
    minEdgeLength       -1;
}

writeFlags
(
    scalarLevels
    layerSets
);

mergeTolerance 1e-6;
"""

SURFACE_FEATURE_EXTRACT_DICT = """/*--------------------------------*- C++ -*----------------------------------*\\
  version:     2.0;
  format:      ascii;
  class:       dictionary;
  object:      surfaceFeatureExtractDict;
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      surfaceFeatureExtractDict;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

propeller.stl
{
    extractionMethod    extractFromSurface;
    includedAngle       150;
    geometricTestOnly   no;
    writeObj            yes;
}
"""

MESH_QUALITY_DICT = """/*--------------------------------*- C++ -*----------------------------------*\\
  version:     2.0;
  format:      ascii;
  class:       dictionary;
  object:      meshQualityDict;
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      meshQualityDict;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

#includeEtc "caseDicts/meshQualityDict"
"""

RUN_CFD_SH = """#!/bin/bash
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
    echo '/*--------------------------------*- C++ -*----------------------------------*\\
  version:     2.0;
  format:      ascii;
  class:       dictionary;
  object:      surfaceFeaturesDict;
\\*---------------------------------------------------------------------------*/
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
"""

# ---------------------------------------------------------------------------
# Setup Case Folder
# ---------------------------------------------------------------------------

def write_file(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    # Ensure Unix line endings \\n
    with open(path, "w", newline="\n") as f:
        f.write(content)
    print(f"  Created: {path.relative_to(ROOT)}")


def main(design=None, rpm: float = 8000.0, case_dir: pathlib.Path = None):
    """Build an OpenFOAM case.

    Parameters
    ----------
    design : optional
        Optimizer Design used for the STL geometry and (its rpm) the MRF zone.
    rpm : float
        Rotation speed; sets the MRF omega.  If ``design`` carries an ``rpm``
        attribute it overrides this argument.
    case_dir : Path
        Target case directory (default: the project's propeller_case).
    """
    case_dir = pathlib.Path(case_dir) if case_dir is not None else CASE_DIR
    if design is not None and getattr(design, "rpm", None):
        rpm = design.rpm

    print("=" * 60)
    print("  OpenFOAM CFD Case Directory Builder (Header Fix)")
    print(f"  Target: {case_dir}")
    print(f"  RPM   : {rpm:.0f}")
    print("=" * 60)

    # 1. Write boundary condition files in 0/
    write_file(case_dir / "0" / "U", U_CONTENT)
    write_file(case_dir / "0" / "p", P_CONTENT)
    write_file(case_dir / "0" / "k", K_CONTENT)
    write_file(case_dir / "0" / "omega", OMEGA_CONTENT)
    write_file(case_dir / "0" / "nut", NUT_CONTENT)

    # 2. Write constant files
    write_file(case_dir / "constant" / "transportProperties", TRANSPORT_PROPERTIES)
    write_file(case_dir / "constant" / "turbulenceProperties", TURBULENCE_PROPERTIES)
    write_file(case_dir / "constant" / "MRFProperties", build_mrf_properties(rpm))

    # 3. Write system files
    write_file(case_dir / "system" / "controlDict", CONTROL_DICT)
    write_file(case_dir / "system" / "fvSchemes", FV_SCHEMES)
    write_file(case_dir / "system" / "fvSolution", FV_SOLUTION)
    write_file(case_dir / "system" / "blockMeshDict", BLOCK_MESH_DICT)
    write_file(case_dir / "system" / "snappyHexMeshDict", SNAPPY_HEX_MESH_DICT)
    write_file(case_dir / "system" / "surfaceFeatureExtractDict", SURFACE_FEATURE_EXTRACT_DICT)
    write_file(case_dir / "system" / "meshQualityDict", MESH_QUALITY_DICT)

    # 4. Write script files
    run_sh_path = case_dir / "run_cfd.sh"
    write_file(run_sh_path, RUN_CFD_SH)
    try:
        os.chmod(run_sh_path, 0o755)
    except Exception:
        pass

    # 5. Export STL geometry
    stl_dir = case_dir / "constant" / "triSurface"
    stl_dir.mkdir(parents=True, exist_ok=True)
    stl_path = stl_dir / "propeller_mm.stl"

    if HAS_CQ:
        print("\n  [CQ] CadQuery detected. Generating watertight propeller geometry...")
        try:
            prop = build_propeller(design)
            print(f"  [CQ] Exporting STL -> {stl_path}")
            cq.exporters.export(prop, str(stl_path), exportType="STL",
                                tolerance=0.001, angularTolerance=0.05)
            print("  [CQ] STL Export complete.")
        except Exception as e:
            print(f"  ✗ [CQ] Geometry generation failed: {e}")
    else:
        print("\n  ⚠ CadQuery not found in path. Please export the propeller STL manually")
        print(f"    and save it as: {stl_path}")

    print("\n  Done! Case folder is fully prepared.")
    print("=" * 60)


if __name__ == "__main__":
    main()

