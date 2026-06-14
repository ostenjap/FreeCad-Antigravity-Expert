# CFD & Coupled Multi-Physics Swarm Optimization Guide

This guide details the mathematical equations, multi-agent architecture, and advanced scaling pathways for the coupled aerothermal-structural turbine blade topology optimizer.

---

## 1. Mathematical Foundations of Coupled Multi-Physics

In high-performance gas turbines, design optimization requires simultaneous modeling of three tightly coupled physical fields: aerodynamics, heat transfer, and structural mechanics.

```
       [External Airfoil Scale (w_i)]
                     │
         ┌───────────┴───────────┐
         ▼                       ▼
  [Aerodynamics]            [Thermal CHT]
  - Lift: L ∝ w_i           - Gas-side h_gas ∝ w_i^-0.2
  - Drag: D ∝ (w_i)^2       - Coolant h_coolant ∝ d_i^0.5 * w_i^-0.3
         │                       │
         │ (Pressure Loads)      │ (Blade Temperature T_i)
         ▼                       ▼
  ┌─────────────────────────────────┐
  │         [Structural FEA]        │
  │ - Area: A = A_nom * w_i^2 * d_i │
  │ - Mass: m ∝ A_nom * w_i^2 * d_i │
  │ - Stresses: σ_cf + σ_th         │
  └─────────────────────────────────┘
                     ▲
                     │
       [Internal Lattice Density (d_i)]
```

### 1.1 Aerodynamics & Shape Parameterization
The external shape of the blade is parameterized at $N=24$ cross-sectional slices by a scaling factor $w_i \in [0.4, 1.5]$ that adjusts the nominal chord $c_{nom}(z_i)$ and thickness $t_{nom}(z_i)$ at height $z_i$:
$$c_i = c_{nom}(z_i) \cdot w_i$$
$$t_i = 0.15 \cdot c_i$$

For each section, relative velocity $W_i$ is computed from the rotor speed $\omega$ and radius $r_i = R_{hub} + z_i$:
$$W_i = \sqrt{V_{gas}^2 + (\omega r_i)^2}$$

Lift and drag forces per unit span are calculated as:
$$L_i = \frac{1}{2} \rho_{gas} W_i^2 c_i C_L(w_i)$$
$$D_i = \frac{1}{2} \rho_{gas} W_i^2 c_i C_D(w_i)$$

where the coefficients are modeled after boundary-layer profile friction and wake-shock losses:
$$C_L(w_i) = 2 \pi \sin(\alpha_i) \cdot (1.0 + 0.15(w_i - 1.0))$$
$$C_D(w_i) = 0.006 + 0.07 \left(\frac{t_i}{c_i}\right)^2 (1.0 + 3.0 \sin^2\alpha_i)$$

The aerodynamic efficiency of the blade is evaluated as the average lift-to-drag ratio:
$$\eta_{avg} = \frac{\sum L_i}{\sum D_i}$$

### 1.2 Conjugate Heat Transfer (CHT)
The blade surface temperature $T_i$ results from the thermal equilibrium between convective heat flux from hot gas and heat extraction from internal cooling channels:
$$q_{in}(z_i) = q_{out}(z_i) \implies h_{gas, i} (T_{gas} - T_i) = h_{coolant, i} (T_i - T_{coolant})$$
$$T_i = \frac{h_{gas, i} T_{gas} + h_{coolant, i} T_{coolant}}{h_{gas, i} + h_{coolant, i}}$$

The gas-side convective coefficient $h_{gas, i}$ is derived from the Reynolds number boundary layer correlation:
$$Re_i = \frac{\rho_{gas} W_i c_i}{\mu_{gas}} \implies Nu_{gas, i} = 0.023 Re_i^{0.8} Pr^{0.4}$$
$$h_{gas, i} = \frac{Nu_{gas, i} \cdot k_{gas}}{c_i}$$

The coolant heat transfer coefficient $h_{coolant, i}$ scales with the internal lattice structure density $d_i$ (increasing internal surface area and air turbulence) and the external shape scaling factor $w_i$ (increasing size increases coolant travel distance, which dampens flow velocity):
$$h_{coolant, i} = 15000.0 \cdot \sqrt{d_i} \cdot \left(\frac{1.0}{w_i}\right)^{0.3}$$

### 1.3 Coupled Structural Mechanics
The FEA solver calculates the effective cross-sectional area and mass of each slice based on both the external scale $w_i$ and the internal lattice density $d_i$:
$$A_i = A_{nom}(z_i) \cdot w_i^2 \cdot d_i$$
$$m_i = \rho_{Inconel} \cdot A_i \cdot dz$$

Stresses are evaluated as the sum of centrifugal and thermal gradients:
$$\sigma_{combined, i} = \sigma_{cf, i} + \sigma_{thermal, i}$$
$$\sigma_{cf, i} = \frac{\sum_{j=i}^N m_j \omega^2 (R_{hub} + z_j)}{A_i}$$
$$\sigma_{thermal, i} = 0.12 \cdot E(T_i) \cdot \alpha(T_i) \cdot |T_i - T_{root}|$$

The safety factor is checked against a spanwise yield strength profile $\sigma_{yield}(T_i)$ for Inconel 718:
$$SF_i = \frac{\sigma_{yield}(T_i)}{\sigma_{combined, i}}$$

---

## 2. Multi-Agent Swarm Roles

The swarm divides responsibilities among specialized agents to manage multi-physics complexity:

1. **Aerodynamic Architect Agent**:
   - Takes natural language prompts and translates them into physical boundary conditions (inlet velocity, gas/coolant temperature limits).
   - Formulates the relative weights of the multi-objective Pareto front.
   
2. **CFD Orchestrator Agent**:
   - Manages the optimization loop, maintaining the parameters for the external shape $w$ and internal density $d$.
   - Computes numerical gradients of the multi-objective loss using finite differences.
   
3. **Thermal Critic Agent**:
   - Reviews the optimized states to ensure critical heat transfer and aerodynamic margins are met.
   - Adjusts weights dynamically and triggers a rebuild if constraints are violated.
   
4. **FSI Bridge Agent**:
   - Coordinates data translation between the fluid domain (CFD solver) and structural domain (FEA solver).
   - Translates surface temperatures and pressure forces into structural loads.

---

## 3. Scaling to High-Fidelity Solvers (Future Path)

To graduate from Phase 1 (Analytical Mock Solvers) to Phase 3 (Production HPC Solvers), the swarm can be integrated with open-source CFD, FEA, and coupling toolkits.

### 3.1 Headless OpenFOAM Integration (Phase 2)
To replace the mock CFD solver, the Orchestrator can execute OpenFOAM in a headless Docker/WSL2 environment:
1. **Geometry mesh**: Export the current STEP file and generate a body-fitted volume mesh using `snappyHexMesh` or `cfMesh`.
2. **Boundary conditions**: Automatically write Case Dictionaries:
   - `0/U`: Inlet flow velocity vector, wall boundaries (no-slip).
   - `0/p`: Inlet total pressure, outlet static pressure.
   - `0/T` & `0/alphat`: Thermal boundary conditions for conjugate heat transfer.
3. **Solver execution**: Run `buoyantSimpleFoam` (steady-state buoyant, turbulent CHT solver) via `subprocess`.
4. **Data extraction**: Read the outputs from `postProcessing/forces/0/forces.dat` to extract lift and drag, and probe the blade surfaces for temperature profiles.

### 3.2 DAFoam Adjoint-Based Shape Optimization (Phase 3)
Instead of finite differences (which scale poorly as the number of design variables increases), discrete adjoint solvers can compute gradients in a single step:
1. Integrate **DAFoam** (Discrete Adjoint for OpenFOAM) with **OpenMDAO**.
2. Run the discrete adjoint solver to compute the sensitivity of the objective function (L/D ratio) with respect to all surface mesh nodes:
   $$\frac{d J_{aero}}{d w} = \frac{\partial J_{aero}}{\partial w} - \psi^T \frac{\partial R}{\partial w}$$
   where $\psi$ is the adjoint vector and $R$ is the residual equation of the Navier-Stokes system.

### 3.3 preCICE FSI Coupling (Phase 3)
To handle structural deformation under high aerodynamic loads, **preCICE** can be used to coordinate partitioned coupling between OpenFOAM and FEniCS:
1. Write a preCICE configuration file defining the coupling interface, data mapping (e.g., radial basis function mapping), and coupling scheme (implicit IQN-ILS coupling for strong FSI).
2. Create python-precice adapters inside `cfd_optimization_swarm.py`.
3. In each time step:
   - OpenFOAM solves the flow, and passes force density loads to preCICE.
   - preCICE maps forces to the FEniCS structural mesh.
   - FEniCS computes structural deformation and thermal expansion, and passes node deflections back.
   - preCICE maps deflections to the fluid mesh, triggering mesh motion in OpenFOAM.
   - Repeat until convergence.
