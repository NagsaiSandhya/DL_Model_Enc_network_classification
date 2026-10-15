
from pathlib import Path
import joblib
import pandas as pd

model_path = Path("models/vpn_classifier.pkl")
artifact = joblib.load(model_path)

pipeline = artifact["pipeline"]
feature_names = artifact["feature_names"]
label_mapping = artifact["label_mapping"]

print("=" * 50)
print("MODEL PIPELINE VERIFICATION")
print("=" * 50)

print("Model version:", artifact["model_version"])
print("Task:", artifact["task"])
print("Pipeline type:", type(pipeline).__name__)

print("\nPipeline steps:")
for name, step in pipeline.steps:
    print(f"  {name}: {type(step).__name__}")

print("\nNumber of expected features:", len(feature_names))
print("First 10 features:", feature_names[:10])

print("\nLabel mapping:", label_mapping)
print("Pipeline classes:", pipeline.classes_)

# Create one synthetic row with the correct feature schema.
# This checks that the pipeline accepts the expected input shape.
sample = pd.DataFrame(
    [[0.0] * len(feature_names)],
    columns=feature_names
)

prediction = pipeline.predict(sample)
print("\nPrediction on synthetic input:", prediction)

if hasattr(pipeline, "predict_proba"):
    probabilities = pipeline.predict_proba(sample)
    print("Probability output shape:", probabilities.shape)
    print("Class order for probabilities:", pipeline.classes_)

print("\nPIPELINE CHECK COMPLETED")
