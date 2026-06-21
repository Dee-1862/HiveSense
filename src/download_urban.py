import os
import sys

def download_urban_dataset(destination_dir):
    """
    Selective download instructions for the UrBAN dataset from FRDR.
    Based on the Abdollahi paper, we DO NOT mirror the entire 2000+ hour dataset.
    """
    print("==================================================")
    print("      UrBAN Dataset Selective Download Strategy   ")
    print("==================================================")
    print(f"Target Directory: {destination_dir}\n")
    
    os.makedirs(destination_dir, exist_ok=True)
    
    print("CRITICAL: Do NOT download the entire dataset. We only need specific windows.")
    print("\nPhase 1: Download Metadata (No Globus Required)")
    print("1. Go to the FRDR discovery portal for the UrBAN dataset.")
    print("2. Find the metadata CSV containing the alcohol-wash PVMI scores.")
    print("3. Use the direct 'Download as Zip' or standard HTTP download for this small file.")
    print(f"4. Place it in {destination_dir}")
    
    print("\nPhase 2: Target Selection")
    print("1. Parse the CSV to find the inspection dates (e.g., Aug 24, Sep 1, Sep 30).")
    print("2. Select ~3 hives that provide a mix of healthy (PVMI < 3%) and stressed (PVMI >= 3%) states.")
    
    print("\nPhase 3: Selective Globus Transfer")
    print("1. Install 'Globus Connect Personal'.")
    print("2. In the Globus File Manager browser, navigate into the UrBAN dataset.")
    print("3. Manually select ONLY the audio folders for your chosen (hive, date) pairs.")
    print("   -> ONLY select the inspection day AND the preceding day.")
    print(f"4. Transfer these specific folders to your local endpoint: {os.path.abspath(destination_dir)}")
    print("\nBy following this strategy, your download will be <10 GB instead of hundreds of GBs.")
    print("==================================================")

if __name__ == "__main__":
    target_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dataset", "urban")
    download_urban_dataset(target_dir)
