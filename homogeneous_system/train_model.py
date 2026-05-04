"""
This module is used to train the Random Forest CLassifier model for detecting custom gesture
It uses the samples collected using collect_gesture_data module
"""
import csv
import pickle
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score

def train():
    print("--------------------------")
    print("Loading gesture_data.csv...")

    X, y = [], []
    try:
        with open('gesture_data.csv', 'r') as file:
            reader = csv.reader(file)
            next(reader) 
            for row in reader:
                if not row: continue 
                y.append(row[0])
                X.append([float(x) for x in row[1:]])
    except FileNotFoundError:
        print("ERROR: 'gesture_data.csv' not found.")
        return

    print(f"Loaded {len(X)} samples.")

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, stratify=y, random_state=42)

    print("Training Random Forest Model...")
    model = RandomForestClassifier(n_estimators=100, random_state=42)
    model.fit(X_train, y_train)

    predictions = model.predict(X_test)
    acc = accuracy_score(y_test, predictions)
    print(f"Model Accuracy on Test Data: {acc * 100:.2f}%")

    with open("gesture_model.pkl", "wb") as f:
        pickle.dump(model, f)
        
    print("Model successfully trained and saved to gesture_model.pkl!")

if __name__ == "__main__":
    train()