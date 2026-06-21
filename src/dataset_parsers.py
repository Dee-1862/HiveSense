import os
import glob
import pandas as pd

def parse_nuhive_labels(data_dir: str):
    """
    Parses NU-Hive/OSBH labels.
    - .lab files indicate intervals of Bee vs. NoBee (Gate).
    - Filenames indicate QueenBee vs. NoQueenBee (Queen Status).
    
    Args:
        data_dir (str): Path to the nu_hive raw data directory.
        
    Returns:
        dict: A dictionary mapping audio paths to their annotations.
    """
    labels = []
    
    # Example filename structure: recording_QueenBee_H1_2021-08-10.wav
    # Example label file structure: recording_QueenBee_H1_2021-08-10.lab
    audio_files = glob.glob(os.path.join(data_dir, "**/*.wav"), recursive=True)
    
    for audio_path in audio_files:
        base_name = os.path.basename(audio_path)
        
        # Parse Queen Status from filename
        is_queen = "QueenBee" in base_name and "NoQueenBee" not in base_name
        queen_label = 1 if is_queen else 0
        
        # Parse Bee/NoBee from corresponding .lab file
        lab_path = audio_path.replace('.wav', '.lab')
        intervals = []
        if os.path.exists(lab_path):
            with open(lab_path, 'r') as f:
                for line in f:
                    # Example .lab format: start_time end_time label (e.g., 0.0 5.0 Bee)
                    parts = line.strip().split()
                    if len(parts) >= 3:
                        start, end, label = float(parts[0]), float(parts[1]), parts[2]
                        intervals.append({"start": start, "end": end, "label": label})
        
        labels.append({
            "audio_path": audio_path,
            "queen_status": queen_label,
            "intervals": intervals
        })
        
    return labels

def parse_urban_metadata(metadata_csv_path: str):
    """
    Parses UrBAN dataset phenotypic metadata for Varroa mites.
    
    Args:
        metadata_csv_path (str): Path to the metadata CSV file.
        
    Returns:
        pd.DataFrame: DataFrame containing hive IDs, timestamps, and mite presence.
    """
    if not os.path.exists(metadata_csv_path):
        print(f"Warning: Metadata file {metadata_csv_path} not found.")
        return pd.DataFrame()
        
    df = pd.read_csv(metadata_csv_path)
    
    # Filter for relevant columns (assuming 'hive_id', 'date', 'varroa_present')
    # This structure needs to be adjusted based on the actual UrBAN CSV format.
    expected_cols = ['hive_id', 'date', 'varroa_present']
    available_cols = [col for col in expected_cols if col in df.columns]
    
    return df[available_cols]

if __name__ == "__main__":
    # Test the parsing logic with placeholders
    print("NU-Hive Parser Loaded.")
    print("UrBAN Metadata Parser Loaded.")
