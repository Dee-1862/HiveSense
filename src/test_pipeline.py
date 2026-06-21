import torch
import pandas as pd
from models import SharedFeatureExtractor, GateClassifier, QueenStateClassifier, UrBANMiteStressClassifier, FullAcousticPipeline

def test_models():
    print("--- Testing Model Architectures ---")
    
    # Simulate a batch of 4 audio clips, 3 seconds long, at 16kHz
    batch_size = 4
    sample_rate = 16000
    duration = 3
    dummy_audio = torch.randn(batch_size, sample_rate * duration)
    
    extractor = SharedFeatureExtractor()
    gate = GateClassifier()
    queen = QueenStateClassifier()
    stress = UrBANMiteStressClassifier()
    
    pipeline = FullAcousticPipeline(extractor, gate, queen, stress)
    
    # Run forward pass
    results = pipeline(dummy_audio)
    
    print(f"Input Audio Shape: {dummy_audio.shape}")
    print("Output from Pipeline:")
    for key, value in results.items():
        if isinstance(value, torch.Tensor):
            print(f"  {key}: shape {value.shape}")
        else:
            print(f"  {key}: {value}")
            
    print("\nModel test passed successfully!\n")

def test_parsers():
    print("--- Testing Parsers Structure ---")
    from dataset_parsers import parse_nuhive_labels, parse_urban_metadata
    
    # Since we don't have actual data locally yet, we just test the imports and availability
    print("NU-Hive label parser and UrBAN metadata parser are importable and structured.")
    print("Parsers test passed successfully!\n")

if __name__ == "__main__":
    test_models()
    test_parsers()
