"""Geohash helpers (heatmap cells come back as geohashes and/or lat/lon)."""

from __future__ import annotations

_B32 = "0123456789bcdefghjkmnpqrstuvwxyz"


def encode(lat: float, lon: float, precision: int = 6) -> str:
    lat_rng, lon_rng = [-90.0, 90.0], [-180.0, 180.0]
    out, bit, ch, even = "", 0, 0, True
    bits = (16, 8, 4, 2, 1)
    while len(out) < precision:
        rng, val = (lon_rng, lon) if even else (lat_rng, lat)
        mid = (rng[0] + rng[1]) / 2
        if val > mid:
            ch |= bits[bit]
            rng[0] = mid
        else:
            rng[1] = mid
        even = not even
        if bit < 4:
            bit += 1
        else:
            out += _B32[ch]
            bit, ch = 0, 0
    return out


def decode(geohash: str) -> tuple[float, float]:
    """Center point (lat, lon) of a geohash cell. Raises ValueError on bad input."""
    lat_rng, lon_rng, even = [-90.0, 90.0], [-180.0, 180.0], True
    for char in geohash.lower():
        if char not in _B32:
            raise ValueError(f"invalid geohash character {char!r}")
        cd = _B32.index(char)
        for mask in (16, 8, 4, 2, 1):
            rng = lon_rng if even else lat_rng
            mid = (rng[0] + rng[1]) / 2
            if cd & mask:
                rng[0] = mid
            else:
                rng[1] = mid
            even = not even
    return (lat_rng[0] + lat_rng[1]) / 2, (lon_rng[0] + lon_rng[1]) / 2
