"""Test resource data access through HSDS."""
from urllib3.exceptions import HTTPError

import h5pyd

from rex.resource import Resource


SAMPLE_FPATH = "/nrel/nsrdb/GOES/conus/v4.0.0/nsrdb_conus_2024.h5"


def test_h5pyd():
    """Test resource data access with h5pyd."""
    try:
        with h5pyd.File(SAMPLE_FPATH, retries=1, timeout=5) as file:
            _ = file["ghi"][0, 0]
            print("h5pyd data access test passed.")
    except Exception as e:
        print(f"h5pyd data access test failed '{e}'")


def test_rex():
    """Test resource data access with rex."""
    try:
        hsds_kwargs = {"retries": 0, "timeout": 15}
        with Resource(SAMPLE_FPATH, hsds_kwargs=hsds_kwargs) as file:
            _ = file["ghi", 0, 0]
            print("rex data access test passed.")
    except Exception as e:
        print(f"rex data access test failed: '{e}'")


if __name__ == "__main__":
    print("Testing HSDS Python access methods...")
    test_h5pyd()
    test_rex()
