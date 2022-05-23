#!/usr/bin/env python3
"""Generate all the stack information needed for CATMAID orthoviews from an N5 scale pyramid"""
from argparse import ArgumentParser
import logging
import re
from tokenize import group
from urllib import response
from urllib.request import urlopen
import json
import os
import ssl

DIMS = "xyz"
DIM_IDX = dict(zip(DIMS, range(3)))
AXES_IDX = {k: f"%AXIS_{v}%" for k, v in DIM_IDX.items()}
H2N5_TILE_SIZE = (256, 256)
JPEG_QUALITY = 80
logger = logging.getLogger(__name__)

SSL_CONTEXT = ssl.create_default_context()
SSL_CONTEXT.check_hostname = False
SSL_CONTEXT.verify_mode = ssl.CERT_NONE


def is_url(s):
    return s.startswith("http://") or s.startswith("https://")


def _get_attributes_remote(root, item):
    url = join_root_item(root, item)
    response = urlopen(urljoin(url, "attributes.json"), context=SSL_CONTEXT)
    return json.loads(response.read().decode("utf-8"))


def _get_attributes_local(root, item):
    path = join_root_item(root, item)
    with open(os.path.join(path, "attributes.json")) as f:
        return json.load(f)


def get_attributes(root, item):
    if is_url(root):
        return _get_attributes_remote(root, item)
    if root.startswith("file://"):
        root = root[7:]
    return _get_attributes_local(root, item)


def join_root_item(root, item):
    if is_url(root):
        return f"{root.rstrip('/')}/{item.strip('/')}"
    return os.path.join(root, item.strip(os.path.sep))


def get_group_s0_attributes(root, group):
    group_meta = get_attributes(root, group)
    ds_meta = get_attributes(root, group + "/s0")
    return group_meta, ds_meta


def main(args=None):
    parser = ArgumentParser()
    parser.add_argument("root")
    parser.add_argument("group")
    parser.add_argument("--h2n5-root", "-r")
    parser.add_argument("--no-n5", "-n", action="store_true")
    parsed = parser.parse_args()

    _main(parsed.root, parsed.group, parsed.h2n5_root, parsed.no_n5)


def urljoin(base, *items):
    url = base.rstrip("/")
    for item in items:
        url += "/" + item.lstrip("/")
    return url


def get_other_axis(slicing):
    return (set(DIMS) - set(slicing)).pop()


def make_h2n5_url(h2n5_base, group, slicing="xy"):
    depth = get_other_axis(slicing)
    slice_slug = "_".join(str(DIM_IDX[s]) for s in slicing)
    tile_slug = "{}_{}".format(*H2N5_TILE_SIZE)
    axis_slug = "/".join(AXES_IDX[d] for d in slicing + depth)
    return urljoin(
        h2n5_base, "tile", group,
        "%SCALE_DATASET%", slice_slug, tile_slug, axis_slug
    )


def make_n5_url(path, slicing="xy"):
    if is_url(path):
        fn = urljoin
    else:
        fn = os.path.join

    depth = get_other_axis(slicing)
    slice_slug = "_".join(str(DIM_IDX[s]) for s in slicing + depth)

    return fn(path, "%SCALE_DATASET%", slice_slug)


def make_slicing_data(root, group, slicing="xy", h2n5_root=None, no_n5=False):
    rows = [slicing.upper(), "-"*len(slicing)]


def dict_in_order(d, keys):
    return [d[k] for k in keys]


def format_downsampling(factors, slicing="xy"):
    full_slicing = slicing + get_other_axis(slicing)
    items = []
    for factor in factors:
        inner = ",".join(str(f) for f in dict_in_order(factor, full_slicing))
        items.append(f"{inner}")
    return "|".join(items)


def megatitle(s):
    wrapper = "#" * (len(s) + 4)
    return f"{wrapper}\n# {s} #{wrapper}"


def title(s):
    return f"{s}\n{'-'*len(s)}"


def _main(root, group, h2n5_root=None, no_n5=False):
    group_meta, s0_meta = get_group_s0_attributes(root, group)

    dims = dict(zip(DIMS, s0_meta["dimensions"]))
    res = dict(zip(DIMS, group_meta["resolution"]))
    factors = [dict(zip(DIMS, f)) for f in group_meta["downsamplingFactors"]]

    url = join_root_item(root, group)
    if not is_url(url) and not url.startswith("file://"):
        url = "file://" + url

    rows = []
    for slicing in ["xy", "xz", "zy"]:
        rows.append(slicing.upper())
        dim_order = slicing + get_other_axis(slicing)
        rows.append(megatitle(slicing))
        rows.append("Dimension: " + "X: {}\tY: {}\tZ: {}".format(*dict_in_order(dims, dim_order)))
        rows.append("Resolution: " + "X: {}\tY: {}\tZ: {}".format(*dict_in_order(res, dim_order)))
        rows.append("Downsampling: " + format_downsampling(factors, slicing))
        if h2n5_root:
            rows.append("H2N5 URL: " + make_h2n5_url(h2n5_root, group, slicing))
            rows.append(f"H2N5 file extension: jpg?q={JPEG_QUALITY}")
        if not no_n5:
            rows.append("N5 URL: " + make_n5_url(url, slicing))
        rows.append("")
    rows.pop()
    print("\n".join(rows))


if __name__ == "__main__":
    main()
