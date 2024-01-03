#!/usr/bin/env python3
"""Generate all the stack information needed for CATMAID orthoviews from an N5 scale pyramid"""
from argparse import ArgumentParser
import logging
from urllib.request import urlopen, build_opener, install_opener, HTTPPasswordMgrWithDefaultRealm, HTTPBasicAuthHandler
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


def install_http_basic(url: str, user_pass: str):
    """
    Adapted from https://stackoverflow.com/a/77668694
    """
    user, passwd = user_pass.split(":", 1)
    password_mgr = HTTPPasswordMgrWithDefaultRealm()
    password_mgr.add_password(None, url, user, passwd)

    handler = HTTPBasicAuthHandler(password_mgr)

    # create "opener" (OpenerDirector instance)
    opener = build_opener(handler)

    # Install the opener.
    # Now all calls to urllib.request.urlopen use our opener.
    install_opener(opener)


def get_group_s0_attributes(root, group, http_basic=None):
    if http_basic is not None:
        install_http_basic(root, http_basic)
    group_meta = get_attributes(root, group)
    ds_meta = get_attributes(root, group + "/s0")
    return group_meta, ds_meta


def main(args=None):
    parser = ArgumentParser(
        description=(
            "Tool to print information for a CATMAID stack and mirrors "
            "from a multiscale N5 volume with bigdataviewer metadata. "
        )
    )
    parser.add_argument(
        "root",
        help="Path or URL to the root of the N5 container",
    )
    parser.add_argument(
        "group",
        help=(
            "Fully qualified name of the multiscale group within the container. "
            "This group should contain scales s0, s1 etc.."
        )
    )
    parser.add_argument(
        "--h2n5-root",
        "-r",
        help=(
            "If this N5 container can also be accessed through h2n5, "
            "give the URL to the h2n5 instance (should end before 'tile')"
        )
    )
    parser.add_argument(
        "--no-n5",
        "-n",
        action="store_true",
        help=(
            "If given, the stack mirror information for the raw N5 stack is omitted. "
            "This is often preferable because N5 stacks are slow and not very stable."
        )
    )
    parser.add_argument(
        "--http-basic-auth",
        "-a",
        help=(
            "HTTP Basic authentication if required for this script to access the N5 data, "
            "as 'username:password'."
        )
    )
    parsed = parser.parse_args(args)

    _main(parsed.root, parsed.group, parsed.h2n5_root, parsed.no_n5, parsed.http_basic_auth)


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
        h2n5_base, "tile", group, "%SCALE_DATASET%", slice_slug, tile_slug, axis_slug
    )


def make_n5_url(path, slicing="xy"):
    if is_url(path):
        fn = urljoin
    else:
        fn = os.path.join

    depth = get_other_axis(slicing)
    slice_slug = "_".join(str(DIM_IDX[s]) for s in slicing + depth)

    return fn(path, "%SCALE_DATASET%", slice_slug)


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


def _main(root, group, h2n5_root=None, no_n5=False, http_basic=None):
    group_meta, s0_meta = get_group_s0_attributes(root, group, http_basic)

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
        rows.append(
            "Dimension: "
            + "X: {}\tY: {}\tZ: {}".format(*dict_in_order(dims, dim_order))
        )
        rows.append(
            "Resolution: "
            + "X: {}\tY: {}\tZ: {}".format(*dict_in_order(res, dim_order))
        )
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
