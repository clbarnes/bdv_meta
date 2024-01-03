# bdv_meta

Python script for adding BigDataViewer downscaling metadata to N5 containers

## `catmaid_orthoviews.py`

Given a path or URL to a multiscale N5 group with bigdataviewer metadata,
print information for creating a CATMAID stack and stack mirrors in all orientations.

## `add_downsamples.py`

> *DEPRECATED. This metadata should be written at the time of data creation.*

Attempts to infer downsampling factors from scale array dimensions,
writing it as bigdataviewer multiscale metadata on the containing group.

## `catmaid_downsamples.py`

> *DEPRECATED. `catmaid_orthoviews.py` also contains this functionality.*

Given a path to a local multiscale N5 group with bigdataviewer metadata,
print downscaling information to be pasted into CATMAID's "Custom downsampling" field.
