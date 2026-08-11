# -*- coding: utf-8 -*-
"""
Created on Wed Jun 19 15:37:05 2019

@author: gbuster
"""

# pylint: disable=no-member
import os

import numpy as np
import pytest

from reV import TESTDATADIR
from reV.handlers.outputs import Outputs
from reV.supply_curve.extent import SupplyCurveExtent
from reV.supply_curve.points import (
    GenerationSupplyCurvePoint,
    SupplyCurvePoint,
    _validate_sub_agg_factors,
    extract_unique_area_developable_agg_factors,
)
from reV.supply_curve.sc_aggregation import SupplyCurveAggregation
from reV.utilities import SupplyCurveField
from reV.utilities.exceptions import SupplyCurveInputError


F_EXCL = os.path.join(TESTDATADIR, "ri_exclusions/ri_exclusions.h5")
F_GEN = os.path.join(TESTDATADIR, "gen_out/gen_ri_pv_2012_x000.h5")
TM_DSET = "techmap_nsrdb"
EXCL_DICT = {
    "ri_srtm_slope": {"inclusion_range": (None, 5), "exclude_nodata": True},
    "ri_padus": {"exclude_values": [1], "exclude_nodata": True},
    "ri_reeds_regions": {
        "inclusion_range": (None, 400),
        "exclude_nodata": True,
    },
}

F_TECHMAP = os.path.join(TESTDATADIR, "sc_out/baseline_ri_tech_map.h5")
DSET_TM = "res_ri_pv"
RTOL = 0.001


def _make_generation_sc_point_for_sub_agg_stats(include_mask, resolution):
    """Create a minimal GenerationSupplyCurvePoint for sub_agg_stats."""

    point = object.__new__(GenerationSupplyCurvePoint)
    point._resolution = resolution
    point._incl_mask = np.array(include_mask, dtype=float)
    point.tm = np.ones_like(include_mask)
    point._gids = point.tm.flatten()
    point._excl_area = 1.0
    point._incl_mask_flat = None
    point._zone_mask = None
    return point


@pytest.mark.parametrize(
    ("equations", "expected"),
    [
        ((), set()),
        (("",), set()),
        (("capacity_ac_mw + n_gids",), set()),
        (
            (
                f"mean_agg2_{SupplyCurveField.AREA_SQ_KM}",
                f"max_agg10_{SupplyCurveField.AREA_SQ_KM}",
            ),
            {2, 10},
        ),
        (
            (
                f"p50_agg2_{SupplyCurveField.AREA_SQ_KM} + "
                f"std_agg2_{SupplyCurveField.AREA_SQ_KM}",
                f"min_agg3_{SupplyCurveField.AREA_SQ_KM}",
            ),
            {2, 3},
        ),
    ],
)
def test_extract_unique_area_developable_agg_factors(equations, expected):
    """Test extraction of valid unique area aggregation factors."""

    assert extract_unique_area_developable_agg_factors(*equations) == expected


@pytest.mark.parametrize(
    "equation",
    [
        f"mean_agg_{SupplyCurveField.AREA_SQ_KM}",
        f"mean_agg-2_{SupplyCurveField.AREA_SQ_KM}",
        f"mean_agg2.5_{SupplyCurveField.AREA_SQ_KM}",
        f"mean_agg2_{SupplyCurveField.AREA_SQ_KM}_extra",
        "mean_agg2_area_sq_miles",
        f"mean_value_agg2_{SupplyCurveField.AREA_SQ_KM}",
    ],
)
def test_extract_unique_area_developable_agg_factors_invalid_patterns(
    equation,
):
    """Test that near-matches are not extracted as aggregation factors."""

    assert extract_unique_area_developable_agg_factors(equation) == set()


@pytest.mark.parametrize("agg_factors", [set(), [], tuple()])
def test_validate_sub_agg_factors_empty_inputs(agg_factors):
    """Test that empty agg factor collections are accepted."""

    assert _validate_sub_agg_factors(agg_factors, 64) is None


@pytest.mark.parametrize(
    ("agg_factors", "resolution"),
    [
        ({1}, 64),
        ({2, 4, 8, 16, 32}, 64),
        ({3, 9}, 27),
    ],
)
def test_validate_sub_agg_factors_valid(agg_factors, resolution):
    """Test that valid sub-aggregation factors pass validation."""

    assert _validate_sub_agg_factors(agg_factors, resolution) is None


@pytest.mark.parametrize("agg_factors", [{64}, {128}, {2, 64}, {2, 128}])
def test_validate_sub_agg_factors_too_large(agg_factors):
    """Test that factors >= resolution raise the expected error."""

    with pytest.raises(
        SupplyCurveInputError,
        match="greater than or equal to the supply curve resolution",
    ):
        _validate_sub_agg_factors(agg_factors, 64)


@pytest.mark.parametrize("agg_factors", [{3}, {5}, {2, 3}, {6, 10}])
def test_validate_sub_agg_factors_not_divisible(agg_factors):
    """Test that non-divisible factors raise the expected error."""

    with pytest.raises(
        SupplyCurveInputError,
        match="do not divide evenly into the supply curve resolution",
    ):
        _validate_sub_agg_factors(agg_factors, 64)


def test_validate_sub_agg_factors_too_large_precedes_not_divisible():
    """Test validation order when both error classes are present."""

    with pytest.raises(
        SupplyCurveInputError,
        match="greater than or equal to the supply curve resolution",
    ):
        _validate_sub_agg_factors({65, 3}, 64)


def test_validate_sub_agg_factors_zero_factor_invalid():
    """Test that zero-valued factors raise the expected error."""

    with pytest.raises(
        SupplyCurveInputError,
        match="non-positive sub-aggregation factors",
    ):
        _validate_sub_agg_factors({0}, 64)


def test_sub_agg_stats_agg2():
    """Test sub-aggregation stats for 2x2 chunking on a known mask."""

    include_mask = np.arange(1, 17).reshape(4, 4)
    point = _make_generation_sc_point_for_sub_agg_stats(include_mask, 4)

    summary = point.sub_agg_stats(2)
    area = SupplyCurveField.AREA_SQ_KM
    expected_chunk_sums = np.array([[14.0, 22.0], [46.0, 54.0]])

    expected = {
        f"min_agg2_{area}": expected_chunk_sums.min(),
        f"max_agg2_{area}": expected_chunk_sums.max(),
        f"mean_agg2_{area}": expected_chunk_sums.mean(),
        f"std_agg2_{area}": expected_chunk_sums.std(),
        f"p10_agg2_{area}": np.percentile(expected_chunk_sums, 10),
        f"p25_agg2_{area}": np.percentile(expected_chunk_sums, 25),
        f"p50_agg2_{area}": np.percentile(expected_chunk_sums, 50),
        f"p75_agg2_{area}": np.percentile(expected_chunk_sums, 75),
        f"p90_agg2_{area}": np.percentile(expected_chunk_sums, 90),
    }

    assert set(summary) == set(expected)
    for key, value in expected.items():
        assert np.isclose(summary[key], value)


def test_sub_agg_stats_agg1_returns_pixel_stats():
    """Test sub-aggregation stats when each chunk is a single pixel."""

    include_mask = np.array([[0.0, 0.5], [1.0, 0.25]])
    point = _make_generation_sc_point_for_sub_agg_stats(include_mask, 2)

    summary = point.sub_agg_stats(1)
    area = SupplyCurveField.AREA_SQ_KM
    expected_chunk_sums = include_mask

    assert np.isclose(summary[f"min_agg1_{area}"], expected_chunk_sums.min())
    assert np.isclose(summary[f"max_agg1_{area}"], expected_chunk_sums.max())
    assert np.isclose(
        summary[f"mean_agg1_{area}"], expected_chunk_sums.mean()
    )
    assert np.isclose(summary[f"std_agg1_{area}"], expected_chunk_sums.std())
    assert np.isclose(
        summary[f"p50_agg1_{area}"], np.percentile(expected_chunk_sums, 50)
    )


def test_sub_agg_stats_excludes_invalid_generation_gids():
    """Test sub-aggregation areas match area when a gen gid is unavailable."""

    include_mask = np.array([[1.0, 0.5], [1.0, 0.25]])
    point = _make_generation_sc_point_for_sub_agg_stats(include_mask, 2)
    point._gids[1] = -1

    summary = point.sub_agg_stats(1)
    area = SupplyCurveField.AREA_SQ_KM

    assert np.isclose(point.area, 2.25)
    assert np.isclose(summary[f"min_agg1_{area}"], 0.0)
    assert np.isclose(summary[f"max_agg1_{area}"], 1.0)
    assert np.isclose(summary[f"mean_agg1_{area}"], point.area / 4)


@pytest.mark.parametrize("resolution", [7, 32, 50, 64, 163])
def test_points_calc(resolution):
    """Test the calculation of the SC points setup from exclusions tiff."""

    with SupplyCurveExtent(F_EXCL, resolution=resolution) as sc:
        assert sc.n_cols >= (sc.exclusions.shape[1] / resolution)
        assert sc.n_rows >= (sc.exclusions.shape[0] / resolution)
        assert len(sc) == (sc.n_rows * sc.n_cols)


@pytest.mark.parametrize(
    ("gids", "resolution"), [(range(361), 64), (range(12), 377)]
)
def test_slicer(gids, resolution):
    """Run tests on the different extent slicing algorithms."""

    with SupplyCurveExtent(F_EXCL, resolution=resolution) as sc:
        for gid in gids:
            row_slice0, col_slice0 = sc.get_excl_slices(gid)
            row_slice1, col_slice1 = SupplyCurvePoint.get_agg_slices(
                gid, sc.exclusions.shape, resolution
            )
            msg = "Slicing failed for gid {} and res {}".format(
                gid, resolution
            )
            assert row_slice0 == row_slice1, msg
            assert col_slice0 == col_slice1, msg


@pytest.mark.parametrize(
    ("gid", "resolution", "excl_dict", "time_series"),
    [
        (37, 64, None, None),
        (37, 64, EXCL_DICT, None),
        (37, 64, None, 100),
        (37, 64, EXCL_DICT, 100),
        (37, 37, None, None),
        (37, 37, EXCL_DICT, None),
        (37, 37, None, 100),
        (37, 37, EXCL_DICT, 100),
    ],
)
def test_weighted_means(gid, resolution, excl_dict, time_series):
    """Test Supply Curve Point exclusions weighted mean calculation"""
    with SupplyCurvePoint(
        gid, F_EXCL, TM_DSET, excl_dict=excl_dict, resolution=resolution
    ) as point:
        shape = (point._gids.max() + 1,)
        if time_series:
            shape = (time_series,) + shape

        arr = np.random.random(shape)
        means = point.exclusion_weighted_mean(arr.copy())
        excl = point.include_mask_flat[point.bool_mask]
        excl_sum = excl.sum()
        if len(arr.shape) == 2:
            assert means.shape[0] == shape[0]
            x = arr[:, point._gids[point.bool_mask]]
            x *= excl

            x = x[0]
            means = means[0]
        else:
            x = arr[point._gids[point.bool_mask]]
            x *= excl

        test = x.sum() / excl_sum
        assert np.allclose(test, means, rtol=RTOL)


@pytest.mark.parametrize(
    ("gid", "resolution", "excl_dict", "time_series"),
    [
        (37, 64, None, None),
        (37, 64, EXCL_DICT, None),
        (37, 64, None, 100),
        (37, 64, EXCL_DICT, 100),
        (37, 37, None, None),
        (37, 37, EXCL_DICT, None),
        (37, 37, None, 100),
        (37, 37, EXCL_DICT, 100),
    ],
)
def test_aggregate(gid, resolution, excl_dict, time_series):
    """
    Test Supply Curve Point aggregate calculation
    """
    with SupplyCurvePoint(
        gid, F_EXCL, TM_DSET, excl_dict=excl_dict, resolution=resolution
    ) as point:
        shape = (point._gids.max() + 1,)
        if time_series:
            shape = (time_series,) + shape

        arr = np.random.random(shape)
        total = point.aggregate(arr.copy())
        excl = point.include_mask_flat[point.bool_mask]
        if len(arr.shape) == 2:
            assert total.shape[0] == shape[0]
            x = arr[:, point._gids[point.bool_mask]]
            x *= excl

            x = x[0]
            total = total[0]
        else:
            x = arr[point._gids[point.bool_mask]]
            x *= excl

        test = x.sum()
        assert np.allclose(test, total, rtol=RTOL)


def plot_all_sc_points(resolution=64):
    """Test the calculation of the SC points setup from exclusions tiff."""

    import matplotlib.pyplot as plt

    prop_cycle = plt.rcParams["axes.prop_cycle"]
    colors = prop_cycle.by_key()["color"]

    _, axs = plt.subplots(1, 1)
    with SupplyCurveExtent(F_EXCL, resolution=resolution) as sc:
        colors *= len(sc)
        for gid in range(len(sc)):
            excl_meta = sc.get_excl_points("meta", gid)
            axs.scatter(
                excl_meta[SupplyCurveField.LONGITUDE],
                excl_meta[SupplyCurveField.LATITUDE],
                c=colors[gid],
                s=0.01,
            )

    with Outputs(F_GEN) as f:
        axs.scatter(
            f.meta[SupplyCurveField.LONGITUDE],
            f.meta[SupplyCurveField.LATITUDE],
            c="k",
            s=25,
        )

    axs.axis("equal")
    plt.show()


def plot_single_gen_sc_point(gid=2, resolution=64):
    """Test the calculation of the SC points setup from exclusions tiff."""
    import matplotlib.pyplot as plt

    colors = ["b", "g", "c", "y", "m"]
    colors *= 100

    _, axs = plt.subplots(1, 1)
    gen_index = SupplyCurveAggregation._parse_gen_index(F_GEN)
    with GenerationSupplyCurvePoint(
        gid,
        F_EXCL,
        F_GEN,
        F_TECHMAP,
        DSET_TM,
        gen_index,
        resolution=resolution,
    ) as sc:
        all_gen_gids = list(set(sc._gen_gids))

        excl_meta = sc.exclusions["meta", sc.rows, sc.cols]

        for i, gen_gid in enumerate(all_gen_gids):
            if gen_gid != -1:
                mask = sc._gen_gids == gen_gid
                axs.scatter(
                    excl_meta.loc[mask, SupplyCurveField.LONGITUDE],
                    excl_meta.loc[mask, SupplyCurveField.LATITUDE],
                    marker="s",
                    c=colors[i],
                    s=1,
                )

                axs.scatter(
                    sc.gen.meta.loc[gen_gid, SupplyCurveField.LONGITUDE],
                    sc.gen.meta.loc[gen_gid, SupplyCurveField.LATITUDE],
                    c="k",
                    s=100,
                )

        axs.scatter(sc.centroid[1], sc.centroid[0], marker="x", c="k", s=200)

    axs.axis("equal")
    plt.show()


def execute_pytest(capture="all", flags="-rapP"):
    """Execute module as pytest with detailed summary report.

    Parameters
    ----------
    capture : str
        Log or stdout/stderr capture option. ex: log (only logger),
        all (includes stdout/stderr)
    flags : str
        Which tests to show logs and results for.
    """

    fname = os.path.basename(__file__)
    pytest.main(["-q", "--show-capture={}".format(capture), fname, flags])


if __name__ == "__main__":
    execute_pytest()
