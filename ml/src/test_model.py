import torch

from unet import UNet


print("=" * 60)
print("TESTING U-NET")
print("=" * 60)


# ------------------------------------------------------------
# Device
# ------------------------------------------------------------

device = torch.device(
    "cuda" if torch.cuda.is_available() else "cpu"
)

print("\nDevice:", device)


# ------------------------------------------------------------
# Create model
# ------------------------------------------------------------

model = UNet(
    in_channels=8,
    out_channels=2
)

model = model.to(device)


# ------------------------------------------------------------
# Fake input
# ------------------------------------------------------------

x = torch.randn(
    1,
    8,
    512,
    512
).to(device)


print("\nInput shape:")
print(x.shape)


# ------------------------------------------------------------
# Forward pass
# ------------------------------------------------------------

with torch.no_grad():

    y = model(x)


print("\nOutput shape:")
print(y.shape)


# ------------------------------------------------------------
# Parameter count
# ------------------------------------------------------------

parameters = sum(
    p.numel()
    for p in model.parameters()
)

print("\nTrainable parameters:")
print(f"{parameters:,}")


# ------------------------------------------------------------
# Final check
# ------------------------------------------------------------

expected = (
    1,
    2,
    512,
    512
)

if tuple(y.shape) == expected:

    print("\n✓ U-Net test PASSED")

else:

    print("\n❌ U-Net output shape is incorrect")


print("\nDone!")