import os
import json
import pandas as pd
from huggingface_hub import hf_hub_download

DATASET_REPO = "ADSKAILab/Zero-To-CAD-1m"

def harvest_lofted_dataset(output_json="skills/freecad_expert/scripts/zero_to_cad_sft.json"):
    print("Initializing Zero-To-CAD SFT Data Harvester...")
    os.makedirs(os.path.dirname(output_json), exist_ok=True)
    
    # Download first validation chunk
    try:
        filepath = hf_hub_download(
            repo_id=DATASET_REPO,
            filename="default/validation/0000.parquet",
            repo_type="dataset",
            revision="refs/convert/parquet"
        )
    except Exception as e:
        print(f"Error downloading dataset: {e}")
        return

    try:
        df = pd.read_parquet(filepath)
        print(f"Dataset chunk loaded. Parsing {len(df)} samples...")
        
        sft_data = []
        for idx, row in df.iterrows():
            cq_file = row['cadquery_file']
            if isinstance(cq_file, bytes):
                cq_file = cq_file.decode('utf-8')
            
            ops_json = row['cadquery_ops_json']
            if isinstance(ops_json, bytes):
                ops_json = ops_json.decode('utf-8')
            
            # Simple keyword check for complex structures (lofts, sweeps, splines)
            is_complex = any(keyword in cq_file for keyword in [".loft(", ".sweep(", ".spline("])
            
            if is_complex:
                # Format to SFT structure
                prompt = (
                    "You are a CadQuery expert. Write a Python script to construct a 3D model "
                    f"using the following operations:\n{ops_json}\n"
                    "Ensure the script is self-contained and exports the final object to STEP."
                )
                
                sft_data.append({
                    "instruction": prompt,
                    "input": "",
                    "output": cq_file
                })
        
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(sft_data, f, indent=2)
            
        print(f"Extraction complete! Saved {len(sft_data)} lofted training pairs to: {output_json}")
        
    except Exception as e:
        print(f"Failed to extract training pairs: {e}")

if __name__ == "__main__":
    harvest_lofted_dataset()
