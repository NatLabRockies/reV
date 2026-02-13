"""Make reV solar project points for a study area and resoure dataset.

This requires a running HSDS service that points to NLR's (formerly NREL)
resource data S3 bucket.
"""
from pathlib import Path

import numpy as np

from rex import Resource


HOME = Path(__file__).parent
SAMPLE_FPATH = "/nrel/nsrdb/GOES/conus/v4.0.0/nsrdb_conus_2018.h5"


def main(src, state=None, sample_ratio=None):
    """Write a project points file from an NREL-formatted resource file.

    Parameters
    ----------
    src : str
        The file path an NREL-formatted HDF5 resource file. If HSDS is running
        it will attempt to open a remote path, if not it will search for a
        local path. Required.
    state : str | NoneType
        A state in the United States used to filter the points, optional.
    sample_ratio : float | NoneType
        Create a sample project points file with this fraction of the total
        number of points. So, if this was value was 0.1 for a 500,000 point
        dataset, the output would represent 50,000 points (e.g., the size of
        of 1 node in a 10 node run). Overrides state parameter. Defaults to
        None.
    """
    # Read and adjust meta table
    print(f"Reading meta data for {src}")
    with Resource(src) as file:
        pp = file.meta
    pp.loc[:, "gid"] = pp.index
    pp.loc[:, "config"] = "default"

    # Filter points
    if state and not sample_ratio:
        print(f"Filtering for {state}")
        state = state.title()
        tag = "_".join(state.split()).lower()
        dst = HOME.joinpath(f"project_points_{tag}.csv")
        pp = pp[pp["state"] == state]
    else:
        print("Filtering for the United States")
        dst = HOME.joinpath(f"project_points.csv")
        pp = pp[pp["country"] == "United States"]

    # Reduce to sample if requested
    if sample_ratio:
        pct = f"{sample_ratio * 100:.0f}"
        print(f"Reducing points to a {pct}% sample")
        tag = f"{pct}pct"
        dst = HOME.joinpath(f"project_points_{tag}.csv")
        n = int(np.ceil(pp.shape[0] * sample_ratio))
        pp = pp.iloc[:n]

    # Write to file
    print(f"Writing project points to {dst}")
    pp.to_csv(dst, index=False)


if __name__ == "__main__":
    src=SAMPLE_FPATH; state=None; sample_ratio=0.1
    main(src=SAMPLE_FPATH, state=None, sample_ratio=0.1)
