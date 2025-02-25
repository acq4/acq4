import torch.nn as nn


class NeuronAutoencoder(nn.Module):
    def __init__(self, latent_dim=64):
        super().__init__()

        # Encoder
        # incoming data 1x5x63x63
        self.encoder = nn.Sequential(
            nn.Conv3d(1, 16, kernel_size=3, padding=1),  # 16x5x63x63
            nn.BatchNorm3d(16),
            nn.ReLU(),
            nn.MaxPool3d(kernel_size=(1, 2, 2), stride=(1, 2, 2)),  # 16x5x31x31

            nn.Conv3d(16, 32, kernel_size=3, padding=1),
            nn.BatchNorm3d(32),
            nn.ReLU(),
            nn.MaxPool3d(kernel_size=(1, 2, 2), stride=(1, 2, 2)),  # 32x5x15x15

            nn.Conv3d(32, 64, kernel_size=3, padding=1),
            nn.BatchNorm3d(64),
            nn.ReLU(),
            nn.MaxPool3d(kernel_size=(1, 2, 2), stride=(1, 2, 2)),  # 64x5x7x7

            nn.Conv3d(64, 128, kernel_size=3, padding=1),
            nn.BatchNorm3d(128),
            nn.ReLU(),
            nn.MaxPool3d(kernel_size=2, stride=2),  # 128x2x3x3

            nn.Conv3d(128, 256, kernel_size=3, padding=1),
            nn.BatchNorm3d(256),
            nn.ReLU(),
            nn.MaxPool3d(kernel_size=2, stride=2),  # 256x1x1x1

            nn.Flatten(),
            nn.Linear(256, latent_dim),
        )
        # Decoder
        self.decoder = nn.Sequential(
            nn.Linear(latent_dim, 256),
            nn.Unflatten(1, (256, 1, 1, 1)),
            nn.ConvTranspose3d(256, 128, kernel_size=2, stride=2, output_padding=(0, 1, 1)),
            nn.BatchNorm3d(128),
            nn.ReLU(),
            nn.ConvTranspose3d(128, 64, kernel_size=2, stride=2, output_padding=1),
            nn.BatchNorm3d(64),
            nn.ReLU(),
            nn.ConvTranspose3d(64, 32, kernel_size=(1, 2, 2), stride=(1, 2, 2), output_padding=(0, 1, 1)),
            nn.BatchNorm3d(32),
            nn.ReLU(),
            nn.ConvTranspose3d(32, 16, kernel_size=(1, 2, 2), stride=(1, 2, 2), output_padding=(0, 1, 1)),
            nn.BatchNorm3d(16),
            nn.ReLU(),
            nn.ConvTranspose3d(16, 1, kernel_size=(1, 2, 2), stride=(1, 2, 2), output_padding=(0, 1, 1)),
            nn.Sigmoid(),
        )

    def forward(self, x):
        latent = self.encoder(x)
        reconstructed = self.decoder(latent)
        return reconstructed, latent
