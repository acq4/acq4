import torch
import torch.nn as nn


class NeuronAutoencoder(nn.Module):
    def __init__(self, latent_dim=64):
        super().__init__()

        # Encoder blocks broken down to access intermediate outputs
        # Block 1: 1x5x63x63 -> 16x5x31x31
        self.enc_block1 = nn.Sequential(
            nn.Conv3d(1, 16, kernel_size=3, padding=1),
            nn.BatchNorm3d(16),
            nn.ReLU(),
        )
        self.pool1 = nn.MaxPool3d(kernel_size=(1, 2, 2), stride=(1, 2, 2))

        # Block 2: 16x5x31x31 -> 32x5x15x15
        self.enc_block2 = nn.Sequential(
            nn.Conv3d(16, 32, kernel_size=3, padding=1),
            nn.BatchNorm3d(32),
            nn.ReLU(),
        )
        self.pool2 = nn.MaxPool3d(kernel_size=(1, 2, 2), stride=(1, 2, 2))

        # Block 3: 32x5x15x15 -> 64x5x7x7
        self.enc_block3 = nn.Sequential(
            nn.Conv3d(32, 64, kernel_size=3, padding=1),
            nn.BatchNorm3d(64),
            nn.ReLU(),
        )
        self.pool3 = nn.MaxPool3d(kernel_size=(1, 2, 2), stride=(1, 2, 2))

        # Block 4: 64x5x7x7 -> 128x2x3x3
        self.enc_block4 = nn.Sequential(
            nn.Conv3d(64, 128, kernel_size=3, padding=1),
            nn.BatchNorm3d(128),
            nn.ReLU(),
        )
        self.pool4 = nn.MaxPool3d(kernel_size=2, stride=2)

        # Block 5: 128x2x3x3 -> 256x1x1x1
        self.enc_block5 = nn.Sequential(
            nn.Conv3d(128, 256, kernel_size=3, padding=1),
            nn.BatchNorm3d(256),
            nn.ReLU(),
        )
        self.pool5 = nn.MaxPool3d(kernel_size=2, stride=2)

        # Latent space
        self.flatten = nn.Flatten()
        self.fc_encoder = nn.Linear(256, latent_dim)
        self.fc_decoder = nn.Linear(latent_dim, 256)
        self.unflatten = nn.Unflatten(1, (256, 1, 1, 1))

        # Decoder blocks with skip connections
        # Block 1: 256x1x1x1 -> 128x2x3x3
        self.dec_block1 = nn.Sequential(
            nn.ConvTranspose3d(256, 128, kernel_size=2, stride=2, output_padding=(0, 1, 1)),
            nn.BatchNorm3d(128),
            nn.ReLU(),
        )

        # Block 2: (128+128)x2x3x3 -> 64x5x7x7
        # The doubled input channels are intentional due to concatenation
        self.dec_block2 = nn.Sequential(
            nn.ConvTranspose3d(256 + 128, 64, kernel_size=2, stride=2, output_padding=1),  # 128+128=256 input channels
            nn.BatchNorm3d(64),
            nn.ReLU(),
        )

        # Block 3: (64+64)x5x7x7 -> 32x5x15x15
        self.dec_block3 = nn.Sequential(
            nn.ConvTranspose3d(128 + 64, 32, kernel_size=(1, 2, 2), stride=(1, 2, 2), output_padding=(0, 1, 1)),
            # 64+64=128 input channels
            nn.BatchNorm3d(32),
            nn.ReLU(),
        )

        # Block 4: (32+32)x5x15x15 -> 16x5x31x31
        self.dec_block4 = nn.Sequential(
            nn.ConvTranspose3d(64 + 32, 16, kernel_size=(1, 2, 2), stride=(1, 2, 2), output_padding=(0, 1, 1)),
            # 32+32=64 input channels
            nn.BatchNorm3d(16),
            nn.ReLU(),
        )

        # Block 5: (16+16)x5x31x31 -> 1x5x63x63
        self.dec_block5 = nn.Sequential(
            nn.ConvTranspose3d(
                32 + 16, 1, kernel_size=(1, 2, 2), stride=(1, 2, 2), padding=(0, 0, 0), output_padding=(0, 1, 1)
            ),  # 16+16=32 input channels
            nn.BatchNorm3d(1),
            nn.ReLU(),
        )

        # Optional final adjustment layer to ensure exact dimensions
        self.final_adjust = nn.Sequential(
            nn.Conv3d(1, 1, kernel_size=3, padding=1),
            nn.Sigmoid(),  # Extra conv to fix any remaining dimension issues
        )

    def encode(self, x):
        return self._encode(x)[0]

    def _encode(self, x):
        # Encoder forward pass with saved intermediate outputs
        x1 = self.enc_block1(x)
        p1 = self.pool1(x1)
        x2 = self.enc_block2(p1)
        p2 = self.pool2(x2)
        x3 = self.enc_block3(p2)
        p3 = self.pool3(x3)
        x4 = self.enc_block4(p3)
        p4 = self.pool4(x4)
        x5 = self.enc_block5(p4)
        p5 = self.pool5(x5)

        # Latent space
        flattened = self.flatten(p5)
        latent = self.fc_encoder(flattened)
        return latent, x2, x3, x4, x5

    def forward(self, x):
        latent, x2, x3, x4, x5 = self._encode(x)

        # Begin decoder
        dec_latent = self.fc_decoder(latent)
        unflattened = self.unflatten(dec_latent)

        # Decoder forward pass with skip connections
        d1 = self.dec_block1(unflattened)

        # Concatenate skip connections along channel dimension
        d1_skip = torch.cat([d1, x5], dim=1)
        d2 = self.dec_block2(d1_skip)

        d2_skip = torch.cat([d2, x4], dim=1)
        d3 = self.dec_block3(d2_skip)

        d3_skip = torch.cat([d3, x3], dim=1)
        d4 = self.dec_block4(d3_skip)

        d4_skip = torch.cat([d4, x2], dim=1)
        reconstructed_raw = self.dec_block5(d4_skip)

        # Apply final adjustment to fix dimension issues
        reconstructed = self.final_adjust(reconstructed_raw)

        # Ensure output has exactly the same dimensions as input
        if reconstructed.shape != x.shape:
            # Use interpolation to fix any remaining dimension issues
            reconstructed = torch.nn.functional.interpolate(
                reconstructed, size=(x.shape[2], x.shape[3], x.shape[4]), mode="trilinear", align_corners=True
            )

        return reconstructed, latent
