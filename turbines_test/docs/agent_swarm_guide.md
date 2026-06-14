# Multi-Agent Topology Optimization Swarm Guide

This guide details the mathematical foundations, multi-agent prompts, and integration workflows for the automated turbine blade topology optimization swarm.

---

## 1. Swarm Overview

The multi-agent swarm consists of three primary cognitive agents and a hardware-in-the-loop (HIL) safety mechanism:

```
[User Prompt] ➔ [Physics Architect] ➔ [Orchestrator] ➔ [Critic] ➔ [Dead Man's Switch] ➔ [STEP/FreeCAD Export]
                    (NL to Math)        (PyTorch Coder)  (Debugger)      (Manual Verify)
```

---

## 2. Mathematical Foundations (Inconel 718)

Gas turbine blades operate under extreme load conditions. The solver models two dominant stress components:

### A. Centrifugal Stress
For a blade rotating at $\omega$ rad/s:
$$F_c(z) = \int_{z}^{L} \rho(z') \cdot A(z') \cdot \omega^2 \cdot (R_{hub} + z') \, dz'$$
$$\sigma_c(z) = \frac{F_c(z)}{A_{eff}(z)}$$

Where:
- $\rho$ = Material density ($8190 \text{ kg/m}^3$)
- $A(z)$ = Slice cross-sectional area
- $A_{eff}(z) = A(z) \cdot \rho_{relative}(z)$ (Effective area of the internal lattice structure)
- $R_{hub}$ = Hub radius ($200 \text{ mm}$)

### B. Thermal Gradient Stress
Under a 1D linear thermal gradient between $T_{root}$ and $T_{tip}$:
$$T(z) = T_{root} + (T_{tip} - T_{root}) \cdot \frac{z}{L}$$
$$\sigma_{th}(z) = \gamma \cdot E(T) \cdot \alpha(T) \cdot |T(z) - T_{root}|$$

Where:
- $E(T)$ = Temperature-dependent Young's Modulus ($200 \text{ GPa} \rightarrow 120 \text{ GPa}$)
- $\alpha(T)$ = Temperature-dependent thermal expansion coefficient ($13 \times 10^{-6} \text{ K}^{-1} \rightarrow 16 \times 10^{-6} \text{ K}^{-1}$)
- $\gamma$ = Stress relaxation coefficient ($0.12$) to account for free expansion at the blade tip.

### C. Temperature-Dependent Yield Strength (Inconel 718)
$$\sigma_{yield}(T) = \begin{cases} 
1030 - 0.22 \cdot T & T \le 600^\circ\text{C} \\
900 - 1.875 \cdot (T - 600) & T > 600^\circ\text{C}
\end{cases}$$

---

## 3. Agent Roles & System Prompts

### A. The Physics Architect (Prompt to Math)
**Persona**: Senior Propulsion Materials & FEA Specialist.
**Task**: Translate high-level design constraints into boundary conditions and math equations.

```markdown
SYSTEM PROMPT:
You are the Physics Architect. Your role is to analyze mechanical engineering requirements
for turbine blade designs and output strict numerical definitions for optimization.
Identify:
1. Maximum Operating Speed (RPM) -> Angular Velocity (omega)
2. Operating Temperatures (Root & Tip) -> Boundary thermal conditions
3. Material properties -> Elastic modulus, density, thermal expansion, yield strength curves
4. Target Safety Factor (eta)
Output these as a structured JSON object.
```

### B. The Orchestrator (The Coder)
**Persona**: Applied Mathematician & Neural Topology Developer.
**Task**: Build the neural density fields (using PyTorch/NumPy) and bind outputs to the solver.

```markdown
SYSTEM PROMPT:
You are the Orchestrator. Your role is to write optimization scripts that couple
the relative density field parameters to the multi-physics FEA solver.
Structure:
1. Define a latent space representing relative density profile (density fraction in [0.4, 1.0]).
2. Compute loss = mass_objective + penalty * max(0, target_sf - safety_factor)^2.
3. Perform gradient descent updates to optimize the density configuration.
```

### C. The Critic (The Debugger)
**Persona**: FEA QA Director & Boundary Conditions Debugger.
**Task**: Analyze solver reports and handle non-convergence or safety factor violations.

```markdown
SYSTEM PROMPT:
You are the Critic. Monitor the optimizer's performance at each epoch.
Verify:
1. Are there mesh self-intersections or volume errors?
2. Has the optimizer converged to a safety factor >= target_sf?
If not:
- Recommend increasing constraint penalty weight.
- Suggest raising local minimum density bounds.
- Return the correction parameter feedback to the Orchestrator.
```

---

## 4. Hardware-in-the-Loop Dead Man's Switch

Physics is unforgiving. Autonomous agent swarms should **never** directly push STEP files directly to manufacturing tools (like metal 3D printers or CNC mills) without manual validation.

The `DeadMansSwitch` class halts execution, plots the stress distribution graphs, and prompts for explicit operator approval:

```
[DANGER] HARDWARE-IN-THE-LOOP DEAD MAN'S SWITCH TRIGGERED
Awaiting manual operator geometry validation before STEP file generation...
Do you approve this geometry for production printing? (y/n): 
```

---

## 5. Production Integration Guide (PyTorch + FEniCS)

To move from the numerical 1D slice solver to a 3D volumetric topology optimization:

1. **Install FEniCS & PyTorch**:
   ```bash
   conda create -n fenics-opt python=3.10
   conda activate fenics-opt
   conda install -c conda-forge fenics
   pip install torch torchvision
   ```

2. **Differentiable FEA (Torch-FEniCS)**:
   Use `fenics-adjoint` to make the FEA solver differentiable. This allows PyTorch's auto-differentiation to backpropagate gradients directly from the Von Mises stress objective through the FEA system of equations back to the neural coordinate network (SDF).

3. **Neural Representation**:
   Map $(x, y, z)$ coordinates to a density value $\rho \in [0.4, 1.0]$ using a multi-layer perceptron (MLP) with periodic sine activations (Siren) to represent the complex internal gyroid/lattice structure.
