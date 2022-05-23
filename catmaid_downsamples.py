#!/usr/bin/env python3
"""
Script to permute BDV downscaling metadata for pasting into "Custom downsampling" field of CATMAID stack admin.
"""
from argparse import ArgumentParser
from pathlib import Path
import json

from attr import attributes

DIMS = "xyz"


def validate_dimensions(s):
    s = s.lower()
    if len(s) != 3:
        raise ValueError("Dimensions must have length 3")
    if set(s) != set(DIMS):
        raise ValueError("Dimensions must be a permutation of x, y, and z")
    return tuple(s)


def main(args=None):

    parser = ArgumentParser()
    parser.add_argument("n5group", type=Path)
    parser.add_argument("-d", "--dimension-order", default=validate_dimensions(DIMS))

    parsed = parser.parse_args(args)

    _main(parsed.n5group, parsed.dimension_order)


def list_scales(path: Path):
    name_to_level = dict()
    for p in path.glob("s*"):
        name = p.name
        try:
            level = int(name[1:])
        except ValueError:
            continue
        name_to_level[name] = level
    return sorted(name_to_level, key=name_to_level.get)


def get_downsampling_factors(group_path):
    with open(group_path / "attributes.json") as f:
        attrs = json.load(f)

    scales = list_scales(group_path)

    factors = attrs.get("downsamplingFactors")
    if factors is None:
        factors = attrs.get("scales")
    if factors is None:
        for scale in scales:
            with open(group_path / scale / "attributes.json") as f:
                s_attrs = json.load(f)
            factor = s_attrs.get("downsamplingFactors")
            if factor is None:
                if scale == "s0":
                    factor = [1, 1, 1]
                else:
                    raise RuntimeError("Could not find scale information")
            factors.append(factor)

    if len(factors) != len(scales):
        raise RuntimeError(
            "Number of downsampling factors does not match number of scale levels"
        )

    return factors


def get_slicing_dim(plane_dims):
    return (set(DIMS) - set(plane_dims)).pop()


def _main(n5_group: Path, dimension_order: str):
    factors = get_downsampling_factors(n5_group)
    factor_dicts = [dict(zip(dimension_order, f)) for f in factors]
    for permutation in ["xy", "xz", "zy"]:
        slicing_dim = get_slicing_dim(permutation)
        dims = [*permutation, slicing_dim]
        print(permutation)
        print("--")
        print("|".join(",".join(str(f[d]) for d in dims) for f in factor_dicts))


if __name__ == "__main__":
    main()
