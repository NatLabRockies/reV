import json
import os

import pandas as pd
import pytest
import toml
import yaml

from reV import TESTDATADIR
from reV.config.project_points import ProjectPoints
from reV.utilities import SiteDataField


def _write_project_points_config(config, config_type, path):
    """Write a project points config file in the requested format."""
    with open(path, "w") as fh:
        if config_type == "json":
            json.dump(config, fh)
        elif config_type == "yaml":
            yaml.safe_dump(config, fh, sort_keys=False)
        else:
            toml.dump(config, fh)


def _project_points_config_dict():
    """Build a gid-keyed project points config mapping for tests."""
    return {
        "2": {"config": "default", "curtailment": "curt"},
        "0": {"config": "default"},
        "1": {"config": "default"},
    }


@pytest.mark.parametrize("config_type", ["json", "yaml", "toml"])
def test_parse_project_points_from_config(tmp_path, config_type):
    """Parse gid-keyed project points configs from supported file formats."""
    config = _project_points_config_dict()
    config_path = tmp_path / f"project_points.{config_type}"
    _write_project_points_config(config, config_type, config_path)

    points = ProjectPoints._parse_points(config_path)

    assert points[SiteDataField.GID].tolist() == [0, 1, 2]
    assert points[SiteDataField.CONFIG].tolist() == ["default"] * 3
    assert points[SiteDataField.CURTAILMENT].tolist() == [None, None, "curt"]
    assert points["points_order"].tolist() == [1, 2, 0]


def test_parse_project_points_from_gid_keyed_mapping():
    """Parse gid-keyed project points mappings passed directly as a dict."""
    points = ProjectPoints._parse_points(_project_points_config_dict())

    assert points[SiteDataField.GID].tolist() == [0, 1, 2]
    assert points[SiteDataField.CONFIG].tolist() == ["default"] * 3
    assert points[SiteDataField.CURTAILMENT].tolist() == [None, None, "curt"]


@pytest.mark.parametrize("config_type", ["json", "yaml", "toml"])
def test_project_points_init_from_config_file(tmp_path, config_type):
    """Initialize ProjectPoints from a gid-keyed config file."""
    config = _project_points_config_dict()
    config_path = tmp_path / f"project_points.{config_type}"
    _write_project_points_config(config, config_type, config_path)

    sam_file = os.path.join(TESTDATADIR, "SAM", "naris_pv_1axis_inv13.json")
    project_points = ProjectPoints(config_path, {"default": sam_file})

    assert project_points.sites == [0, 1, 2]
    assert project_points.get_sites_from_config("default") == [0, 1, 2]
    assert project_points.df[SiteDataField.CURTAILMENT].tolist() == [None, None, "curt"]


def test_parse_project_points_column_mapping_dict():
    """Parse project points from a dict of column arrays."""
    points = {
        SiteDataField.GID: [3, 1],
        SiteDataField.CONFIG: ["default", "default"],
    }

    parsed = ProjectPoints._parse_points(points)

    expected = pd.DataFrame(points).sort_values(SiteDataField.GID).reset_index(drop=True)
    expected[SiteDataField.CURTAILMENT] = None
    expected["points_order"] = [1, 0]

    assert parsed.equals(expected)