#!/usr/bin/env python3
"""
Script for (somewhat safely) adding metadata required by BigDataViewer
(and optionally n5-viewer) to multiscale datasets stored in N5 containers.
"""
from dataclasses import dataclass
import json
from pathlib import Path
from argparse import ArgumentParser
import re
import typing as tp
from collections.abc import MutableMapping
import logging

logger = logging.getLogger(__name__)

ATTRS_FILE = "attributes.json"
ARRAY_ATTR_KEYS = {"dimensions", "dataType", "blockSize", "compression"}
SCALE_RE = re.compile(r"s(\d+)")
unit_re_str = r"([YZEPTGMkhdcmuμnpfazy]|da)?(m|s|Hz)"
UNIT_RE = re.compile(unit_re_str)
RESOLUTION_RE = re.compile(
    r"(?P<value>(\d*\.?)?\d+)\s*(?P<unit>" + unit_re_str + ")?"
)

Jso = tp.Optional[tp.Union[tp.Dict[str, "Jso"], tp.List["Jso"], int, float, bool, str]]


def check_key(k: str):
    if not isinstance(k, (str, bytes)):
        raise TypeError(f"Not a valid key: {repr(k)}")


def check_value(v: Jso):
    if isinstance(v, list):
        for item in v:
            check_value(item)
    elif isinstance(v, dict):
        for k, val in v.items():
            check_key(k)
            check_value(val)
    elif v is not None and not isinstance(v, (int, float, bool, str, bytes)):
        raise TypeError(f"Not a valid value: {repr(v)}")


class ArrayAttrs(tp.TypedDict):
    dimensions: tp.List[int]
    dataType: str
    blockSize: tp.List[int]
    compression: tp.Union[tp.Dict[str, Jso], str]


class N5Attrs(MutableMapping):
    def __init__(self, d: tp.Dict[str, Jso], gentle=True) -> None:
        check_value(d)
        self._d: tp.Dict[str, Jso] = d
        self.gentle = gentle

    def array_meta(self) -> tp.Optional[ArrayAttrs]:
        try:
            return ArrayAttrs(**{k: self._d[k] for k in ARRAY_ATTR_KEYS})
        except KeyError:
            return None

    def is_array(self) -> bool:
        return self.array_meta() is not None

    def ndim(self) -> tp.Optional[int]:
        arr = self.array_meta()
        if arr:
            return len(arr["dimensions"])
        return None

    @classmethod
    def from_dir(cls, dpath: Path, gentle=True):
        if not dpath.is_dir():
            raise FileNotFoundError(f"Directory does not exist: {dpath}")
        attr_path = dpath / ATTRS_FILE
        if not attr_path.is_file():
            return cls(dict(), gentle)
        with open(dpath / ATTRS_FILE) as f:
            d = json.load(f)
        return cls(d, gentle)

    def to_dir(self, dpath: Path, pretty=True, dry_run=False):
        if pretty:
            kwargs = {"sort_keys": True, "indent": 2}
        else:
            kwargs = {}
        s = json.dumps(self._d, **kwargs)
        fpath = dpath / ATTRS_FILE
        if dry_run:
            logger.info("Dry-run mode: would write to %s", fpath)
            print(s)
        else:
            with open(fpath, "w") as f:
                f.write(s)

    def __iter__(self):
        return self._d.__iter__()

    def __len__(self):
        return self._d.__len__()

    def __getitem__(self, key: str) -> Jso:
        check_key(key)
        return self._d.__getitem__(key)

    def __delitem__(self, key: str):
        check_key(key)
        if key in ARRAY_ATTR_KEYS:
            raise ValueError(f"Cannot write reserved keys: '{key}'")
        if self.gentle and key in self._d:
            raise ValueError(f"Cannot delete key: '{key}'")
        return super().__delitem__(key)

    def __setitem__(self, key: str, value: Jso):
        check_key(key)
        if key in ARRAY_ATTR_KEYS:
            raise ValueError(f"Cannot write reserved keys: '{key}'")

        key_msg = f"Key already exists: '{key}'"

        if key in self._d:
            if self.gentle:
                raise ValueError(key_msg)
            else:
                logger.warning(key_msg)

        check_value(value)
        return self._d.__setitem__(key, value)


def infer_downsampling_factor(s0_shape, sN_shape) -> tp.List[int]:
    if len(s0_shape) != len(sN_shape):
        raise ValueError("Shapes are of different dimensionalities")
    return [round(s0 / sN) for s0, sN in zip(s0_shape, sN_shape)]


def get_downsampling_factors(dpath: Path) -> tp.Optional[tp.List[tp.List[int]]]:
    scale = 0
    try:
        attrs = N5Attrs.from_dir(dpath / f"s{scale}")
    except FileNotFoundError:
        logger.info("Group has no child 's0'")
        return None

    if not attrs.is_array():
        logger.info("Child 's0' is not an array")
        return None
    s0_shape = attrs["dimensions"]

    factors = []

    while True:
        scale += 1
        try:
            attrs = N5Attrs.from_dir(dpath / f"s{scale}")
        except FileNotFoundError:
            break
        if not attrs.is_array():
            break
        shape = attrs["dimensions"]
        try:
            factors.append(infer_downsampling_factor(s0_shape, shape))
        except ValueError:
            break

    return factors


def parse_scales(s):
    return [[int(c.strip()) for c in lvl] for lvl in s.split(";")]


@dataclass
class Length:
    magnitude: float
    unit: tp.Optional[str]

    @classmethod
    def from_str(cls, s: str):
        logger.debug("Parsing length '%s'", s)
        m = RESOLUTION_RE.match(s.strip())
        if m is None:
            raise ValueError(f"Resolution could not be parsed: '{s}'")
        d = m.groupdict()
        unit = d.get("unit")
        if not unit:
            unit = None
        logger.debug("Got value %s", d["value"])
        logger.debug("Got unit %s", unit)
        return cls(float(d["value"]), unit)


def parse_resolution(s: str) -> tp.List[Length]:
    return [Length.from_str(l_str) for l_str in s.split(",")]


def validate_unit(s: str) -> str:
    if not UNIT_RE.match(s):
        raise ValueError(f"Not a valid unit: '{s}'")
    return s


def main(args=None):
    parser = ArgumentParser(description=__doc__)
    parser.add_argument(
        "group", type=Path, help="Path to directory which contains scale level arrays"
    )
    parser.add_argument(
        "resolution",
        type=parse_resolution,
        help="Resolution, optionally with units, of scale level 0. Given as comma-separated string '1nm,2um,3GHz'. If data are isotropic, a single length can be given.",
    )
    # parser.add_argument(
    #     "-d",
    #     "--downsampling-factors",
    #     type=parse_scales,
    #     help="Downscaling factors relative to scale level 0, given as colon-separated comma-separated strings. If a downsampling factor is isotropic, a single length can be given. e.g. '3,3,1:2,2,1:2:2:2'",
    # )
    parser.add_argument(
        "-u",
        "--unit",
        type=validate_unit,
        help="Default unit if not given in resolution",
    )
    parser.add_argument(
        "-n",
        "--n5-viewer",
        action="store_true",
        help="Add additional metadata for compatibility with n5-viewer",
    )
    parser.add_argument("-d", "--dry-run", action="store_true", help="Do not change any files, just log what would be done")
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Overwrite keys which already exist in the attributes file",
    )
    parsed = parser.parse_args(args)

    resolution = []
    units = []
    for length in parsed.resolution:
        resolution.append(length.magnitude)
        if length.unit is None:
            if parsed.unit is None:
                raise ValueError("Units must be given")
            units.append(parsed.unit)
        else:
            units.append(length.unit)

    downsampling = get_downsampling_factors(parsed.group)

    if downsampling is None:
        raise ValueError(f"Path does not seem to be a scale directory: {parsed.group}")

    ndims = len(downsampling[0])

    if len(resolution) != ndims:
        if len(resolution) == 1:
            resolution = resolution * ndims
            units = units * ndims
        else:
            raise ValueError(
                f"Data has {ndims} dimensions, resolution argument has {len(resolution)}"
            )

    # if parsed.downsampling_factors is not None:
    #     if nlevels != len(parsed.downsampling_factors) + 1:
    #         logger.warning(
    #             "Data has %s scale levels, downsampling_factors arg implies %s",
    #             nlevels,
    #             len(parsed.downsampling_factors) + 1,
    #         )

    #     downsampling = []
    #     for df in parsed.downsamplingFactors:
    #         if len(df) != ndims:
    #             if len(df) == 1:
    #                 df = df * ndims
    #             else:
    #                 raise ValueError(
    #                     f"Data has {ndims} dimensions, downsampling_factors argument has {len(df)}"
    #                 )
    #         downsampling.append(df)

    attrs = N5Attrs.from_dir(parsed.group, not parsed.force)
    attrs["downsamplingFactors"] = downsampling
    attrs["resolution"] = resolution
    attrs["units"] = units

    if parsed.n5_viewer:
        if len(set(units)) != 1:
            raise ValueError(
                "n5-viewer mode only available when dimensions all have the same units"
            )
        attrs["pixelResolution"] = {"dimensions": resolution, "unit": units[0]}

    attrs.to_dir(parsed.group, dry_run=parsed.dry_run)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
