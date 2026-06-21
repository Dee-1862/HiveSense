import os
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, roc_auc_score, classification_report
from sklearn.model_selection import GroupKFold

def train_rf_model(features_csv):
    """
    Trains a Random Forest classifier using a Hive-Held-Out split.
    """
    if not os.path.exists(features_csv):
        print(f"Feature file not found: {features_csv}")
        print("Please run extract_features.py first.")
        return

    df = pd.read_csv(features_csv)
    
    # ---------------------------------------------------------
    # PLACEHOLDER: Data Alignment
    # In practice, you must join `df` with the PVMI metadata CSV 
    # based on the audio filename (hive + date) to get the labels.
    # 
    # df['hive_id'] = ... parsed from filename
    # df['label'] = ... 1 if PVMI >= 3% else 0
    # ---------------------------------------------------------
    
    # For demonstration, we will assume these columns exist. 
    # If not, we will mock them so the script runs structurally.
    if 'label' not in df.columns:
        print("Warning: 'label' and 'hive_id' columns not found. Generating mock data for demonstration.")
        df['label'] = (df.index % 2 == 0).astype(int) # Mock binary label
        df['hive_id'] = [f"Hive_{i%3}" for i in range(len(df))] # Mock 3 hives

    # Select feature columns (MFCCs and SSDs)
    feature_cols = [col for col in df.columns if col.startswith('mfcc_') or col in [
        'centroid', 'spread', 'rolloff', 'flatness', 'entropy', 'crest', 'flux', 'skewness', 'kurtosis'
    ]]
    
    X = df[feature_cols].values
    y = df['label'].values
    groups = df['hive_id'].values

    # Setup Random Forest per the Abdollahi paper
    rf = RandomForestClassifier(n_estimators=50, max_depth=5, random_state=42)
    
    # Hive-held-out validation using GroupKFold
    gkf = GroupKFold(n_splits=len(np.unique(groups)))
    
    print("\n--- Training Random Forest (Hive-Held-Out Split) ---")
    
    auc_scores = []
    
    for fold, (train_idx, test_idx) in enumerate(gkf.split(X, y, groups)):
        X_train, y_train = X[train_idx], y[train_idx]
        X_test, y_test = X[test_idx], y[test_idx]
        
        test_hives = np.unique(groups[test_idx])
        
        # Train
        rf.fit(X_train, y_train)
        
        # Predict
        y_pred = rf.predict(X_test)
        y_prob = rf.predict_proba(X_test)[:, 1]
        
        # Evaluate
        try:
            auc = roc_auc_score(y_test, y_prob)
            auc_scores.append(auc)
        except ValueError:
            # Handle cases where the test fold has only one class (e.g. mock data)
            auc = "N/A (single class in fold)"
            
        acc = accuracy_score(y_test, y_pred)
        
        print(f"Fold {fold+1} | Held-out Hives: {test_hives} | Acc: {acc:.2f} | AUC: {auc}")

    if auc_scores:
        print(f"\nAverage AUC: {np.mean(auc_scores):.3f}")
    
    print("\nTraining Complete.")
    
    # Finally, train on all data and save
    rf.fit(X, y)
    model_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models", "rf_urban_varroa.pkl")
    
    import pickle
    with open(model_path, 'wb') as f:
        pickle.dump(rf, f)
    print(f"Final model saved to {model_path}")

if __name__ == "__main__":
    import numpy as np # needed for mock data generation in the script
    target_csv = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dataset", "urban", "extracted_features.csv")
    train_rf_model(target_csv)
