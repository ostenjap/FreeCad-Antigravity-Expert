import FreeCAD as App
import Part
import os
import sys

# Redirect stdout to a log file to capture output in FreeCADCmd
sys.stdout = open("import_verify_log.txt", "w")
sys.stderr = sys.stdout

def run_import_and_verify():
    # Parse CLI arguments if passed inside FreeCADCmd using --pass
    # FreeCADCmd passes arguments after --pass
    args = []
    if "--pass" in sys.argv:
        pass_idx = sys.argv.index("--pass")
        args = sys.argv[pass_idx+1:]
        
    step_file_name = args[0] if len(args) > 0 else "t_slot_4040.step"
    fcstd_file_name = args[1] if len(args) > 1 else "t_slot_4040.FCStd"

    # Create document
    doc = App.newDocument("CadQueryImport")

    # Resolve STEP file path
    step_file_path = os.path.abspath(step_file_name)
    if not os.path.exists(step_file_path):
        print(f"Error: STEP file not found at {step_file_path}")
        sys.exit(1)

    print(f"Importing STEP file: {step_file_path}")
    Part.insert(step_file_path, doc.Name)
    doc.recompute()

    # Find the imported object
    objs = doc.Objects
    if not objs:
        print("Error: No objects found in document after import.")
        sys.exit(1)

    imported_obj = objs[0]
    print(f"Imported object: {imported_obj.Name} ({imported_obj.TypeId})")

    # Geometry verification checks
    if not hasattr(imported_obj, "Shape"):
        print("Error: Object has no Shape attribute.")
        sys.exit(1)

    shape = imported_obj.Shape
    if not shape.isValid():
        print("Error: Shape is non-manifold or contains self-intersections.")
        sys.exit(1)

    volume = shape.Volume
    if volume <= 0.0:
        print(f"Error: Shape has zero or negative volume: {volume}")
        sys.exit(1)

    print("\nGeometry Verification Passed successfully!")
    print(f"Shape Metrics:")
    print(f"  Volume: {volume:.2f} mm3")
    print(f"  Surface Area: {shape.Area:.2f} mm2")
    print(f"  Faces count: {len(shape.Faces)}")
    print(f"  Edges count: {len(shape.Edges)}")

    # Save FreeCAD document
    fcstd_path = os.path.abspath(fcstd_file_name)
    doc.saveAs(fcstd_path)
    print(f"FreeCAD document saved to: {fcstd_path}")

run_import_and_verify()
