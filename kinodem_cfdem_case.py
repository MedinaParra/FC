#!/usr/bin/env python3
"""
KinoDEM CFD-DEM v3 case generator.

Builds a two-way coupled CFDEM case:
  OpenFOAM-6 / cfdemSolverIB <-> CFDEM twoWayMPI <-> LIGGGHTS

The draw chamber is a globe-like surrogate. The rotating wall is a calibration
hypothesis, not a measured claim about the real Kino draw machine.
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

from kinodem_liggghts import (
    LiggghtsConfig,
    default_ball_calibration,
    write_ball_data,
    write_drum_stl,
)


@dataclass(frozen=True)
class CFDDEMConfig:
    globe_radius_m: float = 0.25
    ball_radius_m: float = 0.020
    ball_density_kg_m3: float = 900.0
    omega_rad_s: float = 7.0
    gravity_m_s2: float = 9.81
    dem_dt_s: float = 1.0e-5
    coupling_interval: int = 10
    end_time_s: float = 0.02
    air_kinematic_viscosity_m2_s: float = 1.5e-5
    base_cells: int = 32
    surface_refinement: int = 1
    n_procs: int = 4
    seed: int = 20260919

    @property
    def cfd_dt_s(self) -> float:
        return self.dem_dt_s * self.coupling_interval

    def validate(self) -> None:
        if self.globe_radius_m <= 3 * self.ball_radius_m:
            raise ValueError("globe too small for balls")
        if self.dem_dt_s <= 0 or self.coupling_interval <= 0:
            raise ValueError("time steps must be positive")
        if self.end_time_s <= self.cfd_dt_s:
            raise ValueError("end_time must exceed one CFD time step")
        if self.base_cells < 12:
            raise ValueError("base_cells too small")
        if self.surface_refinement < 0:
            raise ValueError("surface_refinement must be non-negative")
        if self.n_procs != 4:
            raise ValueError("current DEM processor grid is fixed at 2x2x1 = 4")


def foam_header(cls: str, obj: str, location: str | None = None) -> str:
    loc = f'    location    "{location}";\n' if location else ""
    return f"""FoamFile
{{
    version     2.0;
    format      ascii;
    class       {cls};
{loc}    object      {obj};
}}
"""


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_case(root: str | Path, cfg: CFDDEMConfig) -> Path:
    cfg.validate()
    root = Path(root)
    if root.exists():
        shutil.rmtree(root)
    cfd = root / "CFD"
    dem = root / "DEM"
    tri = cfd / "constant" / "triSurface"
    for p in [
        cfd / "0",
        cfd / "constant",
        cfd / "system",
        cfd / "couplingFiles",
        tri,
        dem / "post",
    ]:
        p.mkdir(parents=True, exist_ok=True)

    lcfg = LiggghtsConfig(
        geometry="globe",
        drum_radius=cfg.globe_radius_m,
        ball_radius=cfg.ball_radius_m,
        ball_density=cfg.ball_density_kg_m3,
        angular_velocity=cfg.omega_rad_s,
        gravity=cfg.gravity_m_s2,
        timestep=cfg.dem_dt_s,
        seconds=cfg.end_time_s,
        dump_every_steps=max(1, int(round(0.001 / cfg.dem_dt_s))),
    )
    specs = default_ball_calibration(lcfg)
    write_drum_stl(dem / "globe.stl", lcfg)
    shutil.copyfile(dem / "globe.stl", tri / "globe.stl")
    write_ball_data(dem / "balls.data", lcfg, cfg.seed, specs)

    margin = cfg.globe_radius_m + 0.03
    n = cfg.base_cells
    level = cfg.surface_refinement

    write_text(cfd / "system" / "blockMeshDict", foam_header("dictionary","blockMeshDict","system") + f"""
convertToMeters 1;
vertices
(
    ({-margin} {-margin} {-margin}) ({margin} {-margin} {-margin})
    ({margin} {margin} {-margin}) ({-margin} {margin} {-margin})
    ({-margin} {-margin} {margin}) ({margin} {-margin} {margin})
    ({margin} {margin} {margin}) ({-margin} {margin} {margin})
);
blocks
(
    hex (0 1 2 3 4 5 6 7) ({n} {n} {n}) simpleGrading (1 1 1)
);
edges ();
boundary
(
    outerBox
    {{
        type patch;
        faces
        (
            (0 4 7 3) (1 2 6 5) (0 1 5 4)
            (3 7 6 2) (0 3 2 1) (4 5 6 7)
        );
    }}
);
mergePatchPairs ();
""")

    write_text(cfd / "system" / "snappyHexMeshDict", foam_header("dictionary","snappyHexMeshDict","system") + f"""
castellatedMesh true;
snap true;
addLayers false;

geometry
{{
    globeWall
    {{
        type triSurfaceMesh;
        file "globe.stl";
    }}
}}

castellatedMeshControls
{{
    maxLocalCells 300000;
    maxGlobalCells 600000;
    minRefinementCells 0;
    maxLoadUnbalance 0.10;
    nCellsBetweenLevels 2;

    features ();

    refinementSurfaces
    {{
        globeWall
        {{
            level ({level} {level});
            patchInfo {{ type wall; }}
        }}
    }}

    resolveFeatureAngle 30;
    refinementRegions {{}}
    locationInMesh (0 0 0);
    allowFreeStandingZoneFaces true;
}}

snapControls
{{
    nSmoothPatch 3;
    tolerance 2.0;
    nSolveIter 30;
    nRelaxIter 5;
}}

addLayersControls
{{
    relativeSizes true;
    layers {{}}
    expansionRatio 1.0;
    finalLayerThickness 0.3;
    minThickness 0.1;
    nGrow 0;
    featureAngle 60;
    slipFeatureAngle 30;
    nRelaxIter 3;
    nSmoothSurfaceNormals 1;
    nSmoothNormals 3;
    nSmoothThickness 10;
    maxFaceThicknessRatio 0.5;
    maxThicknessToMedialRatio 0.3;
    minMedianAxisAngle 90;
    nBufferCellsNoExtrude 0;
    nLayerIter 50;
}}

meshQualityControls
{{
    maxNonOrtho 65;
    maxBoundarySkewness 20;
    maxInternalSkewness 4;
    maxConcave 80;
    minVol 1e-13;
    minTetQuality 1e-15;
    minArea -1;
    minTwist 0.02;
    minDeterminant 0.001;
    minFaceWeight 0.02;
    minVolRatio 0.01;
    minTriangleTwist -1;
    nSmoothScale 4;
    errorReduction 0.75;
}}

debug 0;
mergeTolerance 1e-6;
""")

    write_text(cfd / "system" / "controlDict", foam_header("dictionary","controlDict","system") + f"""
application     cfdemSolverIB;
startFrom       startTime;
startTime       0;
stopAt          endTime;
endTime         {cfg.end_time_s:.12g};
deltaT          {cfg.cfd_dt_s:.12g};
writeControl    timeStep;
writeInterval   {max(1, int(round(0.001/cfg.cfd_dt_s)))};
purgeWrite      0;
writeFormat     ascii;
writePrecision  8;
writeCompression uncompressed;
timeFormat      general;
timePrecision   8;
runTimeModifiable no;
adjustTimeStep  no;
maxCo           0.5;
""")

    write_text(cfd / "system" / "decomposeParDict", foam_header("dictionary","decomposeParDict","system") + """
numberOfSubdomains 4;
method simple;
simpleCoeffs
{
    n (2 2 1);
    delta 0.001;
}
distributed no;
roots ();
""")

    write_text(cfd / "system" / "fvSchemes", foam_header("dictionary","fvSchemes","system") + """
ddtSchemes { default Euler; }
gradSchemes { default Gauss linear; grad(p) Gauss linear; grad(U) Gauss linear; }
divSchemes
{
    default Gauss linear;
    div(phi,U) Gauss limitedLinearV 1;
    div((nuEff*dev(grad(U).T()))) Gauss linear;
    div(U) Gauss linear;
}
laplacianSchemes
{
    default Gauss linear corrected;
    laplacian(nuEff,U) Gauss linear corrected;
    laplacian((1|A(U)),p) Gauss linear corrected;
    laplacian((voidfraction2|A(U)),p) Gauss linear corrected;
    laplacian(phiIB) Gauss linear corrected;
    laplacian(U) Gauss linear corrected;
}
interpolationSchemes { default linear; interpolate(U) linear; }
snGradSchemes { default corrected; }
fluxRequired { default no; p; }
""")

    write_text(cfd / "system" / "fvSolution", foam_header("dictionary","fvSolution","system") + """
solvers
{
    p { solver PCG; preconditioner DIC; tolerance 1e-7; relTol 0; }
    pFinal { solver PCG; preconditioner DIC; tolerance 1e-7; relTol 0; }
    U { solver PBiCG; preconditioner DILU; tolerance 1e-6; relTol 0; }
    phiIB { solver PCG; preconditioner DIC; tolerance 1e-7; relTol 0; }
}
PISO
{
    nCorrectors 4;
    nNonOrthogonalCorrectors 1;
    pRefCell 0;
    pRefValue 0;
}
""")

    write_text(cfd / "constant" / "transportProperties", foam_header("dictionary","transportProperties","constant") + f"""
transportModel Newtonian;
nu nu [0 2 -1 0 0 0 0] {cfg.air_kinematic_viscosity_m2_s:.12g};
""")
    write_text(cfd / "constant" / "turbulenceProperties", foam_header("dictionary","turbulenceProperties","constant") + """
simulationType laminar;
""")
    write_text(cfd / "constant" / "dynamicMeshDict", foam_header("dictionary","dynamicMeshDict","constant") + """
dynamicFvMesh staticFvMesh;
""")
    write_text(cfd / "constant" / "g", foam_header("uniformDimensionedVectorField","g","constant") + f"""
dimensions [0 1 -2 0 0 0 0];
value (0 {-cfg.gravity_m_s2:.12g} 0);
""")

    write_text(cfd / "constant" / "couplingProperties", foam_header("dictionary","couplingProperties","constant") + f"""
modelType none;
couplingInterval {cfg.coupling_interval};
depth 0;
voidFractionModel IB;
locateModel engineIB;
meshMotionModel noMeshMotion;
dataExchangeModel twoWayMPI;
IOModel basicIO;
probeModel off;
averagingModel dilute;
clockModel off;
smoothingModel off;
forceModels
(
    ShirgaonkarIB
    ArchimedesIB
);
momCoupleModels ();
turbulenceModelType turbulenceProperties;

ShirgaonkarIBProps
{{
    pressureFieldName "p";
}}
ArchimedesIBProps
{{
    voidfractionFieldName "voidfractionNext";
}}
twoWayFilesProps
{{
    maxNumberOfParticles 100;
    DEMts {cfg.dem_dt_s:.12g};
}}
twoWayMPIProps
{{
    maxNumberOfParticles 100;
    liggghtsPath "../DEM/in.liggghts_run";
}}
IBProps
{{
    maxCellsPerParticle 2000;
    alphaMin 0.30;
    scaleUpVol 1.0;
}}
engineIBProps
{{
    treeSearch false;
    zSplit 8;
    xySplit 16;
}}
""")
    write_text(cfd / "constant" / "liggghtsCommands", foam_header("dictionary","liggghtsCommands","constant") + """
liggghtsCommandModels
(
    runLiggghts
);
""")

    def vector_field(obj: str, dims: str, internal: str, bc: str) -> str:
        return foam_header("volVectorField",obj,"0") + f"""
dimensions {dims};
internalField uniform {internal};
boundaryField
{{
    globeWall
    {{
{bc}
    }}
}}
"""
    write_text(cfd / "0" / "U", vector_field(
        "U","[0 1 -1 0 0 0 0]","(0 0 0)",
        f"""        type rotatingWallVelocity;
        origin (0 0 0);
        axis (0 0 1);
        omega {cfg.omega_rad_s:.12g};
        value uniform (0 0 0);"""
    ))
    write_text(cfd / "0" / "Us", vector_field(
        "Us","[0 1 -1 0 0 0 0]","(0 0 0)",
        """        type zeroGradient;"""
    ))

    def scalar_field(obj: str, dims: str, internal: str, bc: str) -> str:
        return foam_header("volScalarField",obj,"0") + f"""
dimensions {dims};
internalField uniform {internal};
boundaryField
{{
    globeWall
    {{
        type {bc};
    }}
}}
"""
    write_text(cfd / "0" / "p", scalar_field("p","[0 2 -2 0 0 0 0]","0","zeroGradient"))
    write_text(cfd / "0" / "voidfraction", scalar_field("voidfraction","[0 0 0 0 0 0 0]","1","zeroGradient"))
    write_text(cfd / "0" / "phiIB", scalar_field("phiIB","[0 2 -1 0 0 0 0]","0","zeroGradient"))

    write_text(dem / "in.liggghts_run", f"""echo both
log ../DEM/log.liggghts
atom_style sphere
atom_modify map array sort 0 0
boundary f f f
newton off
communicate single vel yes
units si
processors 2 2 1

read_data ../DEM/balls.data

neighbor 0.004 bin
neigh_modify delay 0

fix m1 all property/global youngsModulus peratomtype {lcfg.youngs_modulus:.12g}
fix m2 all property/global poissonsRatio peratomtype {lcfg.poisson_ratio:.12g}
fix m3 all property/global coefficientRestitution peratomtypepair 1 {lcfg.restitution:.12g}
fix m4 all property/global coefficientFriction peratomtypepair 1 {lcfg.friction:.12g}
pair_style gran model hertz tangential history
pair_coeff * *

fix globe all mesh/surface file ../DEM/globe.stl type 1 surface_ang_vel origin 0 0 0 axis 0 0 1 omega {cfg.omega_rad_s:.12g}
fix wall all wall/gran model hertz tangential history mesh n_meshes 1 meshes globe

timestep {cfg.dem_dt_s:.12g}
fix grav all gravity {cfg.gravity_m_s2:.12g} vector 0 -1 0
fix integr all nve/sphere
fix ts_check all check/timestep/gran 100 0.1 0.1 warn yes error yes

fix cfd all couple/cfd couple_every {cfg.coupling_interval} mpi
fix cfd2 all couple/cfd/force

thermo_style custom step atoms ke f_ts_check[1] f_ts_check[2] f_ts_check[3]
thermo 100
thermo_modify lost error norm no

dump dmp all custom 100 ../DEM/post/dump.liggghts_run id type x y z vx vy vz fx fy fz omegax omegay omegaz radius
dump_modify dmp sort id
run 1
""")

    write_text(root / "Allrun.sh", """#!/bin/bash
set -eo pipefail

# Load an existing CFDEM environment only when the caller has not loaded it.
# Avoid nounset while sourcing legacy OpenFOAM/CFDEM bashrc files.
if [ -z "${CFDEM_SRC_DIR:-}" ]; then
    set +u
    if [ -f /opt/openfoam6/etc/bashrc ]; then
        source /opt/openfoam6/etc/bashrc
    fi
    if [ -f /home/cfdem/CFDEM/CFDEMcoupling/etc/bashrc ]; then
        source /home/cfdem/CFDEM/CFDEMcoupling/etc/bashrc
    fi
    set -u
fi

: "${CFDEM_SRC_DIR:?CFDEM environment is not loaded}"
casePath="$(cd "$(dirname "$0")" && pwd)"

cd "$casePath/CFD"
blockMesh
snappyHexMesh -overwrite
checkMesh
decomposePar -force

# Direct MPI launch is more robust across CFDEM-PUBLIC and CFDEM-PFM than
# the legacy parCFDDEMrun shell wrapper. twoWayMPI is still configured in
# constant/couplingProperties and starts the embedded LIGGGHTS library.
MPIRUN_CMD="mpirun"
if mpirun -version 2>/dev/null | grep -q "Open MPI"; then
    MPIRUN_CMD="mpirun -oversubscribe"
fi
$MPIRUN_CMD -np 4 cfdemSolverIB -parallel 2>&1 | tee "$casePath/log_kinodem_cfdem"

reconstructPar -latestTime || true
foamToVTK -latestTime || true
""")

    manifest = {
        "model": "KinoDEM CFD-DEM v3",
        "coupling": "CFDEM twoWayMPI",
        "cfd_solver": "OpenFOAM-6 cfdemSolverIB",
        "dem_solver": "LIGGGHTS",
        "status": "case_definition_not_yet_a_validated_real-kino_machine",
        "agitation_hypothesis": "rotating globe wall",
        "config": asdict(cfg),
        "derived": {
            "cfd_dt_s": cfg.cfd_dt_s,
            "cfd_steps": int(math.ceil(cfg.end_time_s / cfg.cfd_dt_s)),
            "dem_steps_per_cfd_step": cfg.coupling_interval,
            "ball_count": 25,
        },
    }
    write_text(root / "case_manifest.json", json.dumps(manifest, indent=2, sort_keys=True))
    write_text(dem / "post" / "README.txt", "CFDEM/LIGGGHTS particle dump output is written here.\n")
    return root


def validate_case(root: str | Path) -> dict:
    root = Path(root)
    required = [
        "CFD/0/U","CFD/0/Us","CFD/0/p","CFD/0/voidfraction","CFD/0/phiIB",
        "CFD/constant/couplingProperties","CFD/constant/liggghtsCommands",
        "CFD/system/blockMeshDict","CFD/system/snappyHexMeshDict",
        "DEM/in.liggghts_run","DEM/balls.data","DEM/globe.stl",
        "CFD/constant/triSurface/globe.stl","case_manifest.json","Allrun.sh",
    ]
    missing = [p for p in required if not (root/p).exists()]
    if missing:
        raise ValueError(f"missing case files: {missing}")
    cp=(root/"CFD/constant/couplingProperties").read_text()
    dem=(root/"DEM/in.liggghts_run").read_text()
    u=(root/"CFD/0/U").read_text()
    assert "dataExchangeModel twoWayMPI;" in cp
    assert "voidFractionModel IB;" in cp
    assert "ShirgaonkarIB" in cp and "ArchimedesIB" in cp
    assert "fix cfd all couple/cfd" in dem and "fix cfd2 all couple/cfd/force" in dem
    assert "rotatingWallVelocity" in u
    manifest=json.loads((root/"case_manifest.json").read_text())
    cfg=manifest["config"]
    assert math.isclose(manifest["derived"]["cfd_dt_s"], cfg["dem_dt_s"]*cfg["coupling_interval"])
    return {"ok": True, "required_files": len(required), "manifest": manifest}


def main() -> None:
    ap=argparse.ArgumentParser(description="Generate KinoDEM OpenFOAM/LIGGGHTS CFDEM case")
    ap.add_argument("--out", default="kinodem-cfdem-case")
    ap.add_argument("--end-time", type=float, default=0.02)
    ap.add_argument("--omega", type=float, default=7.0)
    ap.add_argument("--base-cells", type=int, default=32)
    ap.add_argument("--validate-only", action="store_true")
    args=ap.parse_args()
    if args.validate_only:
        print(json.dumps(validate_case(args.out), indent=2))
        return
    cfg=CFDDEMConfig(end_time_s=args.end_time, omega_rad_s=args.omega, base_cells=args.base_cells)
    root=write_case(args.out,cfg)
    print(json.dumps(validate_case(root), indent=2))


if __name__=="__main__":
    main()
