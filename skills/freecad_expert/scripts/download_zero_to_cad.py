import os
import argparse
import json
import pandas as pd
from huggingface_hub import hf_hub_download

DATASET_REPO = "ADSKAILab/Zero-To-CAD-1m"

def download_and_inspect(output_dir="data", limit=5):
    print(f"Downloading dataset files from: {DATASET_REPO}")
    os.makedirs(output_dir, exist_ok=True)
    
    # We will download the first validation split parquet file as a quick starter
    try:
        # Resolve the split's parquet file path on refs/convert/parquet branch
        # HuggingFace automatically converts datasets to parquet on refs/convert/parquet
        filepath = hf_hub_download(
            repo_id=DATASET_REPO,
            filename="default/validation/0000.parquet",
            repo_type="dataset",
            revision="refs/convert/parquet"
        )
        print(f"Successfully downloaded validation parquet to: {filepath}")
    except Exception as e:
        print(f"Failed to download via huggingface_hub: {e}")
        print("Please ensure huggingface_hub is installed: `pip install huggingface_hub`")
        return

    # Read parquet and inspect
    try:
        print("Reading Parquet file...")
        df = pd.read_parquet(filepath)
        print(f"Parquet loaded successfully! Shape: {df.shape}")
        print("Columns: ", list(df.columns))
        
        # Save a few example CadQuery scripts and CAD ops
        examples = []
        for idx, row in df.head(limit).iterrows():
            uuid = row['uuid']
            cq_file = row['cadquery_file']
            ops_json = row['cadquery_ops_json']
            
            # Save individual CQ python files for inspection
            cq_filename = os.path.join(output_dir, f"{uuid}.py")
            with open(cq_filename, "w", encoding="utf-8") as f:
                f.write(cq_file)
            print(f"Saved example CadQuery script to: {cq_filename}")
            
            examples.append({
                "uuid": uuid,
                "ops": json.loads(ops_json) if isinstance(ops_json, str) else ops_json
            })
            
        # Save structural summary
        summary_file = os.path.join(output_dir, "dataset_summary.json")
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump(examples, f, indent=2)
        print(f"Saved ops metadata summary to: {summary_file}")
        
    except Exception as e:
        print(f"Failed to read parquet file: {e}")
        print("Please ensure pandas and pyarrow/fastparquet are installed: `pip install pandas pyarrow`")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download and inspect Zero-To-CAD-1m dataset")
    parser.add_argument("--dir", default="zero_to_cad_data", help="Output directory for downloaded data")
    parser.add_argument("--limit", type=int, default=5, help="Number of example scripts to extract")
    args = parser.parse_args()
    
    download_and_inspect(args.dir, args.limit)
