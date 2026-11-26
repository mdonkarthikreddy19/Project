"""
Small fully-convolutional network that outputs a per-region "edited" score.

It looks at the RGB image plus three fixed high-pass (SRM-style) residuals.
Retyped or pasted text almost never carries the same compression noise and
anti-aliasing as the pixels around it, and the residuals make that visible.

Output is a logit map at 1/8 of the input resolution. The image score is
the mean of the strongest few cells, so one edited field is enough to flag it.
"""
import torch
import torch.nn as nn
import torch.nn.functional as F


def _srm_kernels():
    k1 = torch.tensor([[0, 0, 0, 0, 0],
                       [0, -1, 2, -1, 0],
                       [0, 2, -4, 2, 0],
                       [0, -1, 2, -1, 0],
                       [0, 0, 0, 0, 0]], dtype=torch.float32) / 4
    k2 = torch.tensor([[-1, 2, -2, 2, -1],
                       [2, -6, 8, -6, 2],
                       [-2, 8, -12, 8, -2],
                       [2, -6, 8, -6, 2],
                       [-1, 2, -2, 2, -1]], dtype=torch.float32) / 12
    k3 = torch.tensor([[0, 0, 0, 0, 0],
                       [0, 0, 0, 0, 0],
                       [0, 1, -2, 1, 0],
                       [0, 0, 0, 0, 0],
                       [0, 0, 0, 0, 0]], dtype=torch.float32) / 2
    return torch.stack([k1, k2, k3]).unsqueeze(1)


def block(cin, cout, stride=1, dilation=1):
    return nn.Sequential(
        nn.Conv2d(cin, cout, 3, stride, padding=dilation, dilation=dilation, bias=False),
        nn.BatchNorm2d(cout),
        nn.ReLU(inplace=True),
        nn.Conv2d(cout, cout, 3, 1, padding=dilation, dilation=dilation, bias=False),
        nn.BatchNorm2d(cout),
        nn.ReLU(inplace=True),
    )


class TamperNet(nn.Module):
    STRIDE = 8

    def __init__(self):
        super().__init__()
        self.register_buffer("srm", _srm_kernels())
        # full-resolution work is kept to a single thin conv so this runs on a CPU
        self.stem = nn.Sequential(nn.Conv2d(6, 24, 3, 1, 1, bias=False), nn.BatchNorm2d(24), nn.ReLU(inplace=True))
        self.enc2 = block(24, 48, stride=2)
        self.enc3 = block(48, 96, stride=2)
        self.enc4 = block(96, 128, stride=2)
        self.ctx = nn.Sequential(block(128, 128, dilation=2), block(128, 128, dilation=4))
        self.head = nn.Conv2d(128 + 96, 1, 1)

    def forward(self, x):
        # x: (B,3,H,W) RGB in [0,1]
        gray = x.mean(1, keepdim=True) * 255.0
        res = torch.clamp(F.conv2d(gray, self.srm, padding=2), -3, 3) / 3
        h = self.stem(torch.cat([x * 2 - 1, res], 1))
        h = self.enc2(h)
        h3 = self.enc3(h)
        h = self.ctx(self.enc4(h3))
        h3 = F.avg_pool2d(h3, 2, ceil_mode=True)[..., : h.shape[2], : h.shape[3]]
        return self.head(torch.cat([h, h3], 1))


def image_logit(logit_map: torch.Tensor, k: int = 4) -> torch.Tensor:
    flat = logit_map.flatten(1)
    k = min(k, flat.shape[1])
    return flat.topk(k, dim=1).values.mean(1)
