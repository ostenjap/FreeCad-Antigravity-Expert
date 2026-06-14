# Quadcopter Propeller — CF-PA6 5-Blade with Tubercles

## Overview

This module generates and structurally analyses a **5-blade quadcopter drone
propeller** made from **30 wt% short carbon-fibre filled PA6 (Nylon 6)**.
The leading edges incorporate **bio-inspired tubercles** — sinusoidal bumps
copied from the pectoral fins of humpback whales — that reduce drag and
acoustic noise.

---

## Directory Structure

```
quadcopter/
├── cad/          # Generated STEP & STL files (output)
├── data/         # JSON analysis reports (output)
├── docs/         # HTML documentation & reference papers
└── src/
    ├── generate_propeller.py      # CadQuery geometry generation
    ├── propeller_physics.py       # Structural FEA (centrifugal + bending + torsion)
    ├── tubercle_analysis.py       # Aeroacoustic benefit model
    └── run_propeller_analysis.py  # Master pipeline runner
```

---

## Quick Start

### 1. Install dependencies

```bash
pip install cadquery numpy
```

### 2. Run the analysis only (no CAD export)

```bash
python quadcopter/src/run_propeller_analysis.py --no-cad
```

### 3. Full run: analysis + STEP + STL generation

```bash
python quadcopter/src/run_propeller_analysis.py
```

### 4. Custom operating point

```bash
python quadcopter/src/run_propeller_analysis.py --rpm 10000 --thrust 22 --torque 0.45
```

---

## Key Design Parameters

| Parameter | Value |
|-----------|-------|
| Number of blades | 5 |
| Diameter | 254 mm (10 in) |
| Hub radius | 12 mm |
| Shaft bore | Ø 6 mm (M6) |
| Airfoil section | NACA 4412 |
| Chord (root → tip) | 28 mm → 10 mm |
| Twist (root → tip) | 35° → 12° |
| Tubercle amplitude | 3 mm |
| Tubercle wavelength | 40 mm |

---

## Material: CF-PA6 (30 wt% Short Carbon Fibre)

| Property | Value |
|----------|-------|
| Young's modulus | 30 GPa |
| Poisson ratio | 0.35 |
| Density | 1300 kg/m³ |
| Tensile strength | 200 MPa |
| Design allowable (SF=2.5) | 80 MPa |
| Max operating temp | 120 °C |

---

## Tubercle Benefits (at 8000 RPM)

| Metric | Improvement |
|--------|-------------|
| Stall angle delay | +2.9° |
| Drag reduction | ~1.7% |
| L/D ratio gain | 1.7% |
| Loading noise reduction | ~1.7 dB |
| Trailing-edge noise reduction | ~0.8 dB |
| Figure of Merit gain | ~1.9% |

---

## References

1. Fish, F.E. & Battle, J.M. (1995). Hydrodynamic design of the humpback whale flipper. *Journal of Morphology*, 225(1), 51–60.
2. Miklosovic, D.S. et al. (2004). Leading-edge tubercles delay stall on humpback whale flippers. *Physics of Fluids*, 16(5), L39–L42.
3. van Nierop, E.A. et al. (2008). How bumps on whale flippers delay stall. *PRL*, 100(5), 054502.
4. Johari, H. et al. (2007). Effects of leading-edge protuberances on airfoil performance. *AIAA Journal*, 45(11).
5. Chong, T.P. et al. (2022). Tubercle leading-edge serration effects on aerofoil broadband noise. *Acta Acustica*, 6.
