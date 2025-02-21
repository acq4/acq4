import torch.nn as nn


class NeuronAutoencoder(nn.Module):
    def __init__(self, latent_dim=32):
        super().__init__()

        # Encoder
        self.encoder = nn.Sequential(
            nn.Conv3d(1, 16, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.MaxPool3d(2),  # -> 16x18x18x8
            nn.Conv3d(16, 32, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.MaxPool3d(2),  # -> 32x9x9x4
            nn.Conv3d(32, 64, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.MaxPool3d(2),  # -> 64x5x5x2
            nn.Flatten(),
            nn.Linear(64 * 5 * 5 * 2, latent_dim),
        )

        # Decoder
        self.decoder = nn.Sequential(
            nn.Linear(latent_dim, 64 * 5 * 5 * 2),
            nn.Unflatten(1, (64, 5, 5, 2)),
            nn.ConvTranspose3d(64, 32, kernel_size=2, stride=2),
            nn.ReLU(),
            nn.ConvTranspose3d(32, 16, kernel_size=2, stride=2),
            nn.ReLU(),
            nn.ConvTranspose3d(16, 1, kernel_size=2, stride=2),
            nn.Sigmoid(),
        )

    def forward(self, x):
        latent = self.encoder(x)
        reconstructed = self.decoder(latent)
        return reconstructed, latent
