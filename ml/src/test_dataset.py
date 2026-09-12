from dataset import FloodDataset


print("=" * 60)
print("TESTING PYTORCH DATASET")
print("=" * 60)


train_dataset = FloodDataset("train.txt")

val_dataset = FloodDataset("val.txt")

test_dataset = FloodDataset("test.txt")


print("\nDataset sizes:")
print("Train:", len(train_dataset))
print("Validation:", len(val_dataset))
print("Test:", len(test_dataset))


# Get first training sample

image, label = train_dataset[0]


print("\nFirst sample:")

print("Image shape:", image.shape)
print("Image dtype:", image.dtype)

print("Label shape:", label.shape)
print("Label dtype:", label.dtype)

print("\nImage min:", image.min().item())
print("Image max:", image.max().item())

print("Label values:", label.unique().tolist())


print("\nDataset test complete!")