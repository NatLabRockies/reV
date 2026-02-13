"""Make reV project points for a study area and resoure dataset.

This required a running HSDS service that points to NLR's (formerly NREL)
resource data S3 bucket.
"""
from pathlib import Path

from rex import Resource


HOME = Path(__file__).parent
SAMPLE_FPATH = "/nrel/wtk/conus/wtk_conus_2008.h5"


def main(src, state=None):
    """Write a project points file from an NREL-formatted resource file.

    Parameters
    ----------
    src : str
        The file path an NREL-formatted HDF5 resource file. If HSDS is running
        it will attempt to open a remote path, if not it will search for a
        local path. Required.
    state : str
        A state in the United States, optional.
    """
    # Read and adjust meta table
    print(f"Reading meta data for {src}")
    with Resource(src) as file:
        pp = file.meta

    # Add needed fields and filter
    pp.loc[:, "gid"] = pp.index
    pp.loc[:, "config"] = "default"
    if state:
        state = state.title()
        print(f"Filtering for {state}")
        pp = pp[pp["state"] == state]
    else:
        print(f"Filtering for the United States")
        pp = pp[pp["country"] == "United States"]

    # Write to file
    if state:
        tag = "_".join(state.split()).lower()
        dst = HOME.joinpath(f"project_points_{tag}.csv")
    else:
        dst = HOME.joinpath(f"project_points.csv")
    print(f"Writing project points to {dst}")
    pp.to_csv(dst, index=False)


if __name__ == "__main__":
    main(src=SAMPLE_FPATH)
