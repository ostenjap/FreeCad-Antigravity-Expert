import os
import math
import cadquery as cq

def rotate_and_scale_airfoil(scale, twist_deg, z_offset):
    # Base normalized coordinates for a simple airfoil shape
    base_pts = [
        (0.0, 0.0),        # Leading edge
        (0.15, 0.05),
        (0.35, 0.08),
        (0.60, 0.06),
        (0.85, 0.02),
        (1.0, 0.0),        # Trailing edge
        (0.85, -0.015),
        (0.60, -0.025),
        (0.35, -0.03),
        (0.15, -0.02)
    ]
    
    # Twist angle in radians
    rad = math.radians(twist_deg)
    transformed_pts = []
    
    for x, y in base_pts:
        # Center the airfoil around its center of chord (0.5) to twist around the axis
        x_centered = (x - 0.4) * scale
        y_centered = y * scale
        
        # Apply 2D rotation matrix
        rx = x_centered * math.cos(rad) - y_centered * math.sin(rad)
        ry = x_centered * math.sin(rad) + y_centered * math.cos(rad)
        
        transformed_pts.append((rx, ry))
        
    return transformed_pts

def generate_turbine_blade(length=120.0, step_path="turbine_blade.step"):
    print(f"Generating gas turbine blade CAD profile (Length: {length}mm)...")
    
    # Define airfoil coordinates at 3 spanwise stations
    # Station 0 (Root, Z = 0)
    pts_root = rotate_and_scale_airfoil(scale=40.0, twist_deg=25.0, z_offset=0.0)
    # Station 1 (Mid-span, Z = 60)
    pts_mid = rotate_and_scale_airfoil(scale=30.0, twist_deg=10.0, z_offset=length/2.0)
    # Station 2 (Tip, Z = 120)
    pts_tip = rotate_and_scale_airfoil(scale=20.0, twist_deg=-5.0, z_offset=length)
    
    # Construct lofted blade using CadQuery
    # We create the workplane, add the root spline, offset Z to mid and add mid spline,
    # then offset Z to tip and add tip spline, and loft them.
    try:
        blade = (
            cq.Workplane("XY")
            .workplane(offset=0.0)
            .spline(pts_root).close()
            .workplane(offset=length/2.0)
            .spline(pts_mid).close()
            .workplane(offset=length/2.0) # Offset is relative to previous workplane -> 60 + 60 = 120
            .spline(pts_tip).close()
            .loft(ruled=False) # ruled=False creates a smooth aerofoil surface
        )
        
        # Export to STEP
        print(f"Exporting turbine blade to: {step_path}")
        cq.exporters.export(blade, step_path)
        print("Turbine blade generation successful!")
        
    except Exception as e:
        print(f"Failed to generate turbine blade: {e}")

if __name__ == "__main__":
    generate_turbine_blade(120.0, "turbine_blade.step")
