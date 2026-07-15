# -*- coding: utf-8 -*-
"""
PyTest file for reV plant noise module.
"""

import json
import os
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from reV import TESTDATADIR
from reV.bespoke.bespoke import BespokeSinglePlant
from reV.bespoke.place_turbines import PlaceTurbines
from reV.bespoke.plant_noise import (
    PlantNoiseInputs,
    _extend_sound,
    _get_turbine_res_gids,
)
from reV.supply_curve.tech_mapping import TechMapping

pytest.importorskip("shapely")

SAM = os.path.join(TESTDATADIR, "SAM/i_windpower.json")
EXCL = os.path.join(TESTDATADIR, "ri_exclusions/ri_exclusions.h5")
RES = os.path.join(TESTDATADIR, "wtk/ri_100_wtk_{}.h5")
SPL = os.path.join(TESTDATADIR, "bespoke/ri_sc33_spl.h5")
OBS = os.path.join(TESTDATADIR, "bespoke/ri_sc33_observers.tif")
TM_DSET = "techmap_wtk_ri_100"

EXCL_DICT = {
    "ri_srtm_slope": {"include_range": (None, 5), "exclude_nodata": False},
    "ri_padus": {"exclude_values": [1], "exclude_nodata": False},
    "ri_reeds_regions": {
        "include_range": (None, 400),
        "exclude_nodata": False,
    },
}

with open(SAM) as f:
    SAM_SYS_INPUTS = json.load(f)

SAM_SYS_INPUTS["wind_farm_wake_model"] = 2
SAM_SYS_INPUTS["wind_farm_losses_percent"] = 0
del SAM_SYS_INPUTS["wind_resource_filename"]

OBJECTIVE_FUNCTION = (
    "(0.0975 * capital_cost + fixed_operating_cost) "
    "/ (aep + 1E-6) + variable_operating_cost"
)
CAP_COST_FUN = (
    "[140,60][0] * system_capacity "
    "* np.exp(-system_capacity / 1E5 * 0.1 + (1 - 0.1)) "
    "+ (self.wind_plant[annual_energy] or 0) * 0"
)
FOC_FUN = (
    "[50,60,70][1] * system_capacity "
    "* np.exp(-system_capacity / 1E5 * 0.1 + (1 - 0.1)) "
    "+ (self.wind_plant[annual_energy] or 0) * 0"
)
VOC_FUN = "[3][0]"
BOS_FUN = "0 * (self.wind_plant[annual_energy] or 0)"


@pytest.fixture(scope="module")
def plant_noise_case():
    """Build a small real-data plant-noise case around SC point 33."""

    output_request = ("system_capacity", "cf_mean", "cf_profile")

    with tempfile.TemporaryDirectory() as td:
        res_fp = os.path.join(td, "ri_100_wtk_{}.h5")
        excl_fp = os.path.join(td, "ri_exclusions.h5")
        shutil.copy(EXCL, excl_fp)
        shutil.copy(RES.format(2012), res_fp.format(2012))
        shutil.copy(RES.format(2013), res_fp.format(2013))

        TechMapping.run(
            excl_fp, RES.format(2012), dset=TM_DSET, max_workers=1,
            sc_resolution=2560
        )
        bsp = BespokeSinglePlant(
            33,
            excl_fp,
            res_fp.format("*"),
            TM_DSET,
            SAM_SYS_INPUTS,
            OBJECTIVE_FUNCTION,
            CAP_COST_FUN,
            FOC_FUN,
            VOC_FUN,
            BOS_FUN,
            excl_dict=EXCL_DICT,
            output_request=output_request,
        )

        try:
            sc_point = bsp.sc_point
            sc_point._incl_mask = np.zeros_like(sc_point.include_mask)
            sc_point._incl_mask[1, -2] = 1

            pt = PlaceTurbines(
                sc_point,
                bsp.wind_plant_pd,
                bsp.objective_function,
                bsp.capital_cost_function,
                bsp.fixed_operating_cost_function,
                bsp.variable_operating_cost_function,
                bsp.balance_of_system_cost_function,
                min_spacing=45,
            )

            pt.define_exclusions()
            pt.initialize_packing()

            yield {
                "buffer": sc_point.area_based_pixel_side_length_meters + 45,
                "sc_point": sc_point,
                "x_locations": pt.x_locations,
                "y_locations": pt.y_locations,
            }
        finally:
            bsp.close()


def test_plant_noise_inputs(plant_noise_case):
    """Test `PlantNoiseInputs` validation and path normalization."""

    noise_inputs = PlantNoiseInputs(SPL, OBS, plant_noise_limit=42,
                                    spl_type="lEq")

    assert noise_inputs.spl_path == Path(SPL)
    assert noise_inputs.obs_tiff_fp == Path(OBS)
    assert noise_inputs.plant_noise_limit == 42
    assert noise_inputs.spl_type == "Leq"

    noise_inputs = PlantNoiseInputs()
    assert noise_inputs.build_for_sc_point(
        plant_noise_case["sc_point"],
        plant_noise_case["x_locations"],
        plant_noise_case["y_locations"],
    ) is None

    with pytest.raises(TypeError):
        PlantNoiseInputs(spl_type=0)


def test_extend_sound():
    """Test that sound tables are extended with inverse-distance decay."""

    theta = np.arange(0.0, 360.0, 22.5)
    r1 = np.arange(10.0, 500.0, 10.0)
    r2 = np.arange(500.0, 5001.0, 20.0)
    r_turbine = np.hstack((r1, r2))
    r_ext = np.arange(5100.0, 5300.0, 100.0)
    turbine_spl = np.tile(np.linspace(60.0, 40.0, len(r_turbine)),
                          (len(theta), 1))

    extended_xy, extended_spl = _extend_sound(turbine_spl, radius=5.3)
    extended_spl = extended_spl.reshape(len(theta), -1)

    assert extended_xy.shape == ((len(r_turbine) + len(r_ext)) * len(theta), 2)
    assert extended_spl.shape == (len(theta), len(r_turbine) + len(r_ext))
    assert np.allclose(extended_spl[:, :len(r_turbine)], turbine_spl)

    expected_extension = (
        turbine_spl[:, [-1]] - 20 * np.log10(r_ext / r_turbine[-1])
    )
    assert np.allclose(extended_spl[:, len(r_turbine):], expected_extension)


def test_get_turbine_res_gids():
    """Test mapping turbine coordinates to resource gids."""

    sc_point = SimpleNamespace(
        area_based_pixel_side_length_meters=100,
        include_mask=np.ones((3, 4), dtype=int),
        tm=np.arange(12).reshape(3, 4),
    )

    x_locations = np.array([-1, 150, 450])
    y_locations = np.array([50, 250, 350])

    gids = _get_turbine_res_gids(x_locations, y_locations, sc_point)

    assert np.array_equal(gids, np.array([0, 9, 11]))


def test_plant_noise_real_data(plant_noise_case):
    """Test plant-noise calculations using the bespoke test fixtures."""

    x_locations = plant_noise_case["x_locations"]
    y_locations = plant_noise_case["y_locations"]
    noise_inputs = PlantNoiseInputs(SPL, OBS, plant_noise_limit=55)
    plant_noise = noise_inputs.build_for_sc_point(
        plant_noise_case["sc_point"],
        x_locations,
        y_locations,
        buffer=plant_noise_case["buffer"],
    )

    assert plant_noise is not None
    assert len(x_locations) > 0
    assert x_locations[0] == 62 * 90
    assert y_locations[0] == 62 * 90
    assert plant_noise.shifted_obs_locs.shape[0] == len(x_locations)
    assert plant_noise.shifted_obs_locs.shape[2] == 2
    assert plant_noise.shifted_obs_locs.shape[1] > 0
    assert np.array_equal(
        plant_noise.turbine_gids,
        _get_turbine_res_gids(
            x_locations,
            y_locations,
            plant_noise_case["sc_point"],
        ),
    )
    assert (set(plant_noise.turbine_interp)
            == set(np.unique(plant_noise.turbine_gids)))

    turbine_mask = np.ones(len(plant_noise.turbine_gids), dtype=bool)
    plant_level_noise = plant_noise.compute_noise(turbine_mask)
    single_turbine_noise = plant_noise.compute_noise(turbine_mask,
                                                     plant_level=False)

    assert plant_level_noise.shape == single_turbine_noise.shape
    assert np.all(plant_level_noise >= single_turbine_noise)
    assert np.all(plant_level_noise >= 0)
    assert not np.isnan(plant_noise.turbines_power).any()
    assert np.array_equal(
        plant_noise.compute_noise(np.zeros(len(plant_noise.turbine_gids),
                                           dtype=bool)),
        np.array([0]),
    )
    assert plant_noise.total_noise_penalty(turbine_mask) >= 0

    stats = plant_noise.violation_stats(turbine_mask)
    violations, num_obs, violation_pct = stats
    assert 0 <= violations <= num_obs
    assert num_obs == plant_noise.shifted_obs_locs.shape[1]
    assert violation_pct == pytest.approx(100 * violations / num_obs)


def execute_pytest(capture='all', flags='-rapP'):
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
    pytest.main(['-q', '--show-capture={}'.format(capture), fname, flags])


if __name__ == '__main__':
    execute_pytest()
