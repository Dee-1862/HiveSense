import torch
import torch.nn as nn
import torchaudio

class SharedFeatureExtractor(nn.Module):
    """
    Shared substrate for acoustic state work.
    Extracts Mel-spectrograms from raw audio and passes them through a CNN backbone.
    """
    def __init__(self, sample_rate=16000, n_mels=128, n_fft=1024, hop_length=512):
        super(SharedFeatureExtractor, self).__init__()
        
        # Audio to Mel-spectrogram
        self.mel_spectrogram = torchaudio.transforms.MelSpectrogram(
            sample_rate=sample_rate,
            n_fft=n_fft,
            hop_length=hop_length,
            n_mels=n_mels
        )
        
        # CNN Backbone (similar to Vikas CNN or standard audio feature extractors)
        self.conv_block = nn.Sequential(
            nn.Conv2d(1, 32, kernel_size=3, stride=1, padding=1),
            nn.BatchNorm2d(32),
            nn.ReLU(),
            nn.MaxPool2d(2, 2),
            
            nn.Conv2d(32, 64, kernel_size=3, stride=1, padding=1),
            nn.BatchNorm2d(64),
            nn.ReLU(),
            nn.MaxPool2d(2, 2),
            
            nn.Conv2d(64, 128, kernel_size=3, stride=1, padding=1),
            nn.BatchNorm2d(128),
            nn.ReLU(),
            nn.AdaptiveAvgPool2d((1, 1)) # Global Average Pooling
        )

    def forward(self, x):
        # x: (batch_size, num_samples)
        mel_spec = self.mel_spectrogram(x) # (batch_size, n_mels, time)
        
        # Add channel dimension
        mel_spec = mel_spec.unsqueeze(1) # (batch_size, 1, n_mels, time)
        
        # Extract features
        features = self.conv_block(mel_spec) # (batch_size, 128, 1, 1)
        features = features.view(features.size(0), -1) # (batch_size, 128)
        
        return features

class GateClassifier(nn.Module):
    """
    Model A: Bee / NoBee Gate (Input-validity check).
    """
    def __init__(self, input_dim=128):
        super(GateClassifier, self).__init__()
        self.classifier = nn.Sequential(
            nn.Linear(input_dim, 64),
            nn.ReLU(),
            nn.Dropout(0.5),
            nn.Linear(64, 1),
            nn.Sigmoid() # Outputs probability of "Bee"
        )

    def forward(self, x):
        return self.classifier(x)

class QueenStateClassifier(nn.Module):
    """
    Model B: Queen / NoQueen Classifier.
    """
    def __init__(self, input_dim=128):
        super(QueenStateClassifier, self).__init__()
        self.classifier = nn.Sequential(
            nn.Linear(input_dim, 64),
            nn.ReLU(),
            nn.Dropout(0.5),
            nn.Linear(64, 1),
            nn.Sigmoid() # Outputs probability of "Queen Present"
        )

    def forward(self, x):
        return self.classifier(x)


class FullAcousticPipeline(nn.Module):
    """
    Inference pipeline stringing together the Gate and State classifiers.
    """
    def __init__(self, feature_extractor, gate_model, queen_model):
        super(FullAcousticPipeline, self).__init__()
        self.feature_extractor = feature_extractor
        self.gate_model = gate_model
        self.queen_model = queen_model

    def forward(self, x, gate_threshold=0.5):
        features = self.feature_extractor(x)
        
        # 1. Gate Check
        bee_prob = self.gate_model(features)
        
        # If gate says NoBee, we shouldn't trust the downstream models.
        # Returning dictionary of outputs. In practice, you might mask out the other outputs.
        
        results = {
            "is_bee_prob": bee_prob,
            "gate_passed": bee_prob > gate_threshold,
            "queen_prob": None
        }
        
        # 2. State Classification (only logically valid if gate_passed is True)
        results["queen_prob"] = self.queen_model(features)
            
        return results

if __name__ == "__main__":
    # Quick test of the architecture
    dummy_audio = torch.randn(2, 16000 * 3) # 2 samples of 3 seconds at 16kHz
    
    extractor = SharedFeatureExtractor()
    gate = GateClassifier()
    queen = QueenStateClassifier()
    
    pipeline = FullAcousticPipeline(extractor, gate, queen)
    
    out = pipeline(dummy_audio)
    print("Pipeline Output:", out)
