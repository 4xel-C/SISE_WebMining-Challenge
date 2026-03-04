import pandas as pd

mouse = pd.read_parquet("mouse_events.parquet")
kb = pd.read_parquet("keyboard_events.parquet")

print("=== MOUSE ===")
print(f"Shape: {mouse.shape}")
print(f"Dtypes:\n{mouse.dtypes}\n")
print(f"Event counts:\n{mouse['event'].value_counts()}\n")
print(mouse.head(10).to_string())

print("\n=== KEYBOARD ===")
print(f"Shape: {kb.shape}")
print(f"Dtypes:\n{kb.dtypes}\n")
print(f"Event counts:\n{kb['event'].value_counts()}\n")
print(kb.to_string())
