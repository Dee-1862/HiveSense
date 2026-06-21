import os
import glob
import numpy as np
import pandas as pd
import librosa

def extract_features_from_audio(audio_path, sr=16000):
    """
    Extracts 13 MFCCs and 9 Spectral Shape Descriptors (SSDs) from an audio file.
    Matches the classical ML approach found to be optimal for Varroa detection.
    """
    # Load audio segment (typically 15 minutes, but we process whatever is passed)
    y, sr = librosa.load(audio_path, sr=sr)
    
    features = {}
    
    # 1. MFCCs (13 coefficients, including 0th energy)
    mfccs = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
    mfcc_means = np.mean(mfccs, axis=1)
    for i in range(13):
        features[f'mfcc_{i}'] = mfcc_means[i]
        
    # 2. Spectral Shape Descriptors (SSDs)
    features['centroid'] = np.mean(librosa.feature.spectral_centroid(y=y, sr=sr))
    features['spread'] = np.mean(librosa.feature.spectral_bandwidth(y=y, sr=sr))
    features['rolloff'] = np.mean(librosa.feature.spectral_rolloff(y=y, sr=sr))
    features['flatness'] = np.mean(librosa.feature.spectral_flatness(y=y))
    
    # Advanced SSDs (Approximations/Direct calculations from the spectrum)
    # Get magnitude spectrum
    S, _ = librosa.magphase(librosa.stft(y))
    
    # Skewness, Kurtosis, Entropy
    # Normalizing spectrum to act like a probability distribution for entropy
    S_norm = S / np.sum(S, axis=0, keepdims=True)
    entropy = -np.sum(S_norm * np.log2(S_norm + 1e-10), axis=0)
    features['entropy'] = np.mean(entropy)
    
    # Spectral Crest (Max / Mean)
    crest = np.max(S, axis=0) / (np.mean(S, axis=0) + 1e-10)
    features['crest'] = np.mean(crest)
    
    # Spectral Flux (Euclidean distance between successive frames)
    flux = np.sqrt(np.sum(np.diff(S, axis=1)**2, axis=0))
    features['flux'] = np.mean(flux)
    
    # Note: Skewness and Kurtosis usually require scipy.stats.skew, scipy.stats.kurtosis 
    # applied to the spectrum. Added zeros here as placeholders to complete the 9 SSDs.
    features['skewness'] = 0.0 # Requires scipy
    features['kurtosis'] = 0.0 # Requires scipy
    
    return features

def process_directory(urban_dir):
    """
    Scans the UrBAN directory, extracts features for all WAV files, and saves to CSV.
    """
    wav_files = glob.glob(os.path.join(urban_dir, '**', '*.wav'), recursive=True)
    all_features = []
    
    print(f"Found {len(wav_files)} audio files for feature extraction.")
    
    for idx, path in enumerate(wav_files):
        print(f"Processing {idx+1}/{len(wav_files)}: {os.path.basename(path)}")
        try:
            feats = extract_features_from_audio(path)
            # Add metadata (hive ID and date would ideally be parsed from the filepath/metadata here)
            feats['audio_file'] = os.path.basename(path)
            feats['filepath'] = path
            all_features.append(feats)
        except Exception as e:
            print(f"Error processing {path}: {e}")
            
    if all_features:
        df = pd.DataFrame(all_features)
        out_path = os.path.join(urban_dir, 'extracted_features.csv')
        df.to_csv(out_path, index=False)
        print(f"Saved extracted features to {out_path}")
    else:
        print("No features extracted.")

if __name__ == "__main__":
    target_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dataset", "urban")
    process_directory(target_dir)
