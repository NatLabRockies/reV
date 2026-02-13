# -*- coding: utf-8 -*-
"""Trace memory use of HSDS/HDF5 data access call.

Testing for differences in memory use between a local and remotely accessed
HDF5 file.

Author: ubuntu
Date: Mon Feb  9 17:49:21 UTC 2026
"""
import os
import sys
import tracemalloc

from pathlib import Path

import h5py
import h5pyd

from rex import Resource

os.environ["PYTHONTRACEMALLOC"] = "10"

HOME = Path(__file__)
SAMPLE_REMOTE = "/nrel/nsrdb/GOES/conus/v4.0.0/nsrdb_conus_2018.h5"
SAMPLE_LOCAL = "/kfs2/datasets/NSRDB/conus/nsrdb_conus_irradiance_2018.h5"


def trace_run(src, hfun, ntime=1, nsites=2000):
    """Trace memory for a data request.

    Parameters
    ----------
    src : str
        Path to an HDF5 file.
    hfun : function
        A function used to read the data in. One of h5py.File, h5pyd.File, or
        rex.Resource.
    ntime : int
        The time index interval to use to pull the data. Defaults to 1.
    nsites : int
        The number of sites to sample. Defaults to 10,000.
    """
    base = str(hfun.__base__.__module__).split(".")[0]
    print(f"{base}: {nsites} sites, {ntime} time step(s), {src} ")
    tracemalloc.start()
    with hfun(src) as ds:
        if hfun.__name__ == "Resource":
            ghi = ds["ghi", ::ntime, :nsites]    
        else:
            ghi = ds["ghi"][::ntime, :nsites]
    data_size = sys.getsizeof(ghi)
    mem_size, mem_peak = tracemalloc.get_traced_memory()
    data_size /= 1e9
    mem_size /= 1e9
    mem_peak /= 1e9
    print(f"  {data_size=:.3f} GB")
    print(f"  {mem_size=:.3f} GB")
    print(f"  {mem_peak=:.3f} GB")


def main(remote=True):
    """Trace memory used to read in a remote or local HDF5 file.

    Parameters
    ----------
    remote : bool
        Attempt to read from NREL's remote HSDS server. Defaults to False,
        which will attempt to read from a local file.
    """
    if remote:
        src = SAMPLE_REMOTE
        hfun = h5pyd.File
    else:
        hfun = h5py.File
        src = SAMPLE_LOCAL

    trace_run(src, hfun, ntime=1)
    trace_run(src, Resource, ntime=1)
    trace_run(src, hfun, ntime=6)
    trace_run(src, Resource, ntime=6)


if __name__ == "__main__":
    main()
