import torch
import torch.nn as nn


class EmbeddingMLP(nn.Module):
    def __init__(self, input_dim, output_dim, hidden_dims=(1024, 512), dropout=0.35):
        super().__init__()
        layers = []
        prev = input_dim
        for hidden_dim in hidden_dims:
            layers += [
                nn.Linear(prev, hidden_dim),
                nn.BatchNorm1d(hidden_dim),
                nn.GELU(),
                nn.Dropout(dropout),
            ]
            prev = hidden_dim
        layers.append(nn.Linear(prev, output_dim))
        self.net = nn.Sequential(*layers)

    def forward(self, x):
        return self.net(x)


class ProtCNN(nn.Module):
    def __init__(self, output_dim, vocab_size=21, emb_dim=128, dropout=0.35):
        super().__init__()
        self.embedding = nn.Embedding(vocab_size, emb_dim, padding_idx=0)
        self.conv3 = nn.Sequential(
            nn.Conv1d(emb_dim, 256, 3, padding=1), nn.BatchNorm1d(256), nn.ReLU()
        )
        self.conv5 = nn.Sequential(
            nn.Conv1d(emb_dim, 256, 5, padding=2), nn.BatchNorm1d(256), nn.ReLU()
        )
        self.conv7 = nn.Sequential(
            nn.Conv1d(emb_dim, 256, 7, padding=3), nn.BatchNorm1d(256), nn.ReLU()
        )
        self.conv = nn.Sequential(
            nn.Conv1d(768, 512, 3, padding=1),
            nn.BatchNorm1d(512),
            nn.ReLU(),
            nn.Dropout(dropout),
        )
        self.head = nn.Sequential(
            nn.Linear(1024, 1024),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(1024, output_dim),
        )

    def forward(self, x):
        x = self.embedding(x).transpose(1, 2)
        x = torch.cat([self.conv3(x), self.conv5(x), self.conv7(x)], dim=1)
        x = self.conv(x)
        gap = torch.mean(x, dim=2)
        gmp = torch.max(x, dim=2).values
        return self.head(torch.cat([gap, gmp], dim=1))


class BiLSTMAttention(nn.Module):
    def __init__(self, output_dim, vocab_size=21, emb_dim=128, hidden=256, dropout=0.35):
        super().__init__()
        self.embedding = nn.Embedding(vocab_size, emb_dim, padding_idx=0)
        self.lstm1 = nn.LSTM(emb_dim, hidden, batch_first=True, bidirectional=True)
        self.attn = nn.MultiheadAttention(
            hidden * 2, num_heads=8, dropout=dropout, batch_first=True
        )
        self.norm = nn.LayerNorm(hidden * 2)
        self.lstm2 = nn.LSTM(hidden * 2, hidden // 2, batch_first=True, bidirectional=True)
        self.dropout = nn.Dropout(dropout)
        self.head = nn.Sequential(
            nn.Linear(hidden * 2, 512),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(512, output_dim),
        )

    def forward(self, x):
        pad_mask = x.eq(0)
        x = self.embedding(x)
        x, _ = self.lstm1(x)
        attn_out, _ = self.attn(x, x, x, key_padding_mask=pad_mask)
        x = self.norm(x + self.dropout(attn_out))
        x, _ = self.lstm2(x)
        valid = (~pad_mask).unsqueeze(-1).to(x.dtype)
        gap = (x * valid).sum(dim=1) / valid.sum(dim=1).clamp(min=1.0)
        masked = x.masked_fill(pad_mask.unsqueeze(-1), -1e4)
        gmp = masked.max(dim=1).values
        return self.head(torch.cat([gap, gmp], dim=1))

