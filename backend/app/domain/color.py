"""Colour difference maths: sRGB → CIE Lab → ΔE2000. Pure, no I/O, no model.

Brand palette compliance is a *measurement*, not a judgement — this module is the
measuring instrument, and it is the reason a brand defect can quote a number the
Owner can check. The agent's job is only to decide whether the thing measured is
a designed element or scene content.

ΔE2000 rather than plain Lab distance: perceptual uniformity matters most exactly
where brands care, in near-neutrals and saturated blues, where CIE76 disagrees
with the eye by a factor of two or more.
"""

import math
import re

#: D65, 2° observer — the white point sRGB is defined against.
WHITE_D65 = (95.047, 100.000, 108.883)

_HEX = re.compile(r"^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


class BadHex(ValueError):
    pass


def parse_hex(value: str) -> tuple[int, int, int]:
    """``#1d9e75`` or ``#abc`` → (r, g, b). Raises ``BadHex`` on anything else."""
    match = _HEX.match((value or "").strip())
    if not match:
        raise BadHex(f"{value!r} is not a hex colour")

    digits = match.group(1)
    if len(digits) == 3:
        digits = "".join(digit * 2 for digit in digits)
    return tuple(int(digits[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def to_hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*(max(0, min(255, round(c))) for c in rgb))


def normalise_hex(value: str) -> str:
    """Lower-case, six-digit, hash-prefixed — so two spellings compare equal."""
    return to_hex(parse_hex(value))


def _linearise(channel: float) -> float:
    """Undo the sRGB transfer function. The 0.04045 knee is not a gamma curve."""
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def rgb_to_xyz(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    r, g, b = (_linearise(channel / 255.0) for channel in rgb)
    return (
        (0.4124564 * r + 0.3575761 * g + 0.1804375 * b) * 100.0,
        (0.2126729 * r + 0.7151522 * g + 0.0721750 * b) * 100.0,
        (0.0193339 * r + 0.1191920 * g + 0.9503041 * b) * 100.0,
    )


def _pivot(t: float) -> float:
    return t ** (1 / 3) if t > 216 / 24389 else (24389 / 27 * t + 16) / 116


def xyz_to_lab(xyz: tuple[float, float, float]) -> tuple[float, float, float]:
    fx, fy, fz = (_pivot(value / white) for value, white in zip(xyz, WHITE_D65, strict=True))
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def rgb_to_lab(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    return xyz_to_lab(rgb_to_xyz(rgb))


def hex_to_lab(value: str) -> tuple[float, float, float]:
    return rgb_to_lab(parse_hex(value))


def delta_e(lab1: tuple[float, float, float], lab2: tuple[float, float, float]) -> float:
    """CIEDE2000 colour difference (CIE 142-2001), kL = kC = kH = 1.

    Implemented from the standard formulation. The hue-difference branches look
    fussy but each one is load-bearing: they keep the result continuous where hue
    angles wrap past 360°, which is precisely where a naive implementation reports
    a large difference between two colours that look identical.
    """
    L1, a1, b1 = lab1
    L2, a2, b2 = lab2

    C1 = math.hypot(a1, b1)
    C2 = math.hypot(a2, b2)
    C_bar = (C1 + C2) / 2

    G = 0.5 * (1 - math.sqrt(C_bar**7 / (C_bar**7 + 25.0**7))) if C_bar else 0.5
    a1p, a2p = (1 + G) * a1, (1 + G) * a2

    C1p, C2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    h1p = math.degrees(math.atan2(b1, a1p)) % 360 if (b1 or a1p) else 0.0
    h2p = math.degrees(math.atan2(b2, a2p)) % 360 if (b2 or a2p) else 0.0

    dLp = L2 - L1
    dCp = C2p - C1p

    if C1p * C2p == 0:
        dhp = 0.0
    elif abs(h2p - h1p) <= 180:
        dhp = h2p - h1p
    elif h2p - h1p > 180:
        dhp = h2p - h1p - 360
    else:
        dhp = h2p - h1p + 360
    dHp = 2 * math.sqrt(C1p * C2p) * math.sin(math.radians(dhp) / 2)

    Lp_bar = (L1 + L2) / 2
    Cp_bar = (C1p + C2p) / 2

    if C1p * C2p == 0:
        hp_bar = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        hp_bar = (h1p + h2p) / 2
    elif h1p + h2p < 360:
        hp_bar = (h1p + h2p + 360) / 2
    else:
        hp_bar = (h1p + h2p - 360) / 2

    T = (
        1
        - 0.17 * math.cos(math.radians(hp_bar - 30))
        + 0.24 * math.cos(math.radians(2 * hp_bar))
        + 0.32 * math.cos(math.radians(3 * hp_bar + 6))
        - 0.20 * math.cos(math.radians(4 * hp_bar - 63))
    )

    d_theta = 30 * math.exp(-(((hp_bar - 275) / 25) ** 2))
    R_C = 2 * math.sqrt(Cp_bar**7 / (Cp_bar**7 + 25.0**7)) if Cp_bar else 0.0
    S_L = 1 + (0.015 * (Lp_bar - 50) ** 2) / math.sqrt(20 + (Lp_bar - 50) ** 2)
    S_C = 1 + 0.045 * Cp_bar
    S_H = 1 + 0.015 * Cp_bar * T
    R_T = -math.sin(math.radians(2 * d_theta)) * R_C

    return math.sqrt(
        (dLp / S_L) ** 2
        + (dCp / S_C) ** 2
        + (dHp / S_H) ** 2
        + R_T * (dCp / S_C) * (dHp / S_H)
    )


def delta_e_hex(one: str, other: str) -> float:
    return delta_e(hex_to_lab(one), hex_to_lab(other))


def nearest(value: str, palette: list[str]) -> tuple[str, float]:
    """The palette entry closest to ``value``, and how far off it is.

    Returns ``("", inf)`` for an empty palette — an unconfirmed profile must not
    silently score every colour as compliant.
    """
    if not palette:
        return "", math.inf
    lab = hex_to_lab(value)
    scored = [(entry, delta_e(lab, hex_to_lab(entry))) for entry in palette]
    return min(scored, key=lambda pair: pair[1])
