# -*- coding: utf-8 -*-
"""
Plant noise module
"""
import os
import logging
from warnings import warn
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

import h5py
import numpy as np
from scipy.interpolate import LinearNDInterpolator
from affine import Affine
from rasterio.windows import Window, bounds as window_bounds
from rasterio.warp import transform_bounds, transform
import rioxarray


logger = logging.getLogger(__name__)


@dataclass
class PlantNoiseInputs:
    """Configuration inputs needed to build plant noise evaluators.

    Attributes
    ----------
    spl_path : str | os.PathLike | None
        Path to the HDF5 file containing turbine SPL tables.
    obs_tiff_fp : str | os.PathLike | None
        Path to the raster of observer locations used for noise checks.
    plant_noise_limit : float
        Maximum allowed plant-level sound in dB at observer locations.
    spl_type : str
        SPL metric to extract from the source file, such as ``Leq``.
    """

    spl_path: str | os.PathLike | None = None
    obs_tiff_fp: str | os.PathLike | None = None
    plant_noise_limit: float = 55
    spl_type: str = 'Leq'

    def __post_init__(self):
        """Normalize file paths and validate the SPL type input."""

        if self.spl_path is not None:
            self.spl_path = Path(self.spl_path)

        if self.obs_tiff_fp is not None:
            self.obs_tiff_fp = Path(self.obs_tiff_fp)

        if not isinstance(self.spl_type, str):
            raise TypeError("spl_type must be a string.")

        self.spl_type = self.spl_type.title()

    def build_for_sc_point(self, sc_point, x_locations, y_locations, buffer=0):
        """Build a plant noise evaluator for a supply curve point.

        Parameters
        ----------
        sc_point : SupplyCurvePoint
            Supply curve point providing the exclusions profile and turbine
            mapping.
        x_locations : ndarray
            Turbine x coordinates in the SC-point frame.
        y_locations : ndarray
            Turbine y coordinates in the SC-point frame.
        buffer : float, optional
            Buffer distance around sc boundary to include obs locations.

        Returns
        -------
        PlantNoise | None
            Plant noise evaluator for the requested turbine locations, or
            `None` when noise inputs are unavailable or no observers overlap
            the SC-point.
        """
        if self.spl_path is None or self.obs_tiff_fp is None:
            return None

        shifted_obs_locs = _rel_obs_locs(sc_point, self.obs_tiff_fp,
                                         x_locations, y_locations, buffer=buffer)
        if len(shifted_obs_locs) < 1:
            return None

        turbine_gids = _get_turbine_res_gids(x_locations, y_locations,
                                             sc_point)

        return PlantNoise(self, shifted_obs_locs=shifted_obs_locs,
                          turbine_gids=turbine_gids)


class PlantNoise:
    """Evaluate turbine and plant-level sound at observer locations."""

    def __init__(self, noise_inputs, shifted_obs_locs, turbine_gids):
        """

        Parameters
        ----------
        noise_inputs : PlantNoiseInputs
            Noise configuration and source file paths.
        shifted_obs_locs : ndarray
            Observer coordinates shifted into each turbine-centered frame.
        turbine_gids : ndarray
            Resource gids used to select turbine-specific SPL tables.
        """

        self.noise_inputs = noise_inputs
        self.shifted_obs_locs = shifted_obs_locs
        self.turbine_gids = turbine_gids

    @cached_property
    def turbine_interp(self):
        """Interpolators that map observer offsets to turbine sound power."""

        with h5py.File(self.noise_inputs.spl_path, "r") as spl_fh:
            return {
                gid: self._make_turbine_power_interpolator(gid, spl_fh)
                for gid in np.unique(self.turbine_gids)
            }

    @cached_property
    def turbines_power(self):
        """Sound power at each observer for every turbine in the layout."""

        power = np.vstack(
            [
                self.turbine_interp[gid](shifted_obs)
                for gid, shifted_obs in zip(
                    self.turbine_gids, self.shifted_obs_locs
                )
            ]
        )
        if np.any(np.isnan(power)):
            msg = "Warning: Nan in self.turbines_power"
            logger.warning(msg)
            warn(msg)

        return power

    def _make_turbine_power_interpolator(self, gid, spl_fh):
        """Create an interpolator for one turbine resource gid.

        Parameters
        ----------
        gid : int
            Resource gid used to select the SPL table.
        spl_fh : h5py.File
            Open SPL HDF5 file handle.

        Returns
        -------
        scipy.interpolate.LinearNDInterpolator
            Interpolator from observer offsets to sound power.
        """

        # centered at (0, 0)
        turbine_spl = spl_fh["SPL"][f"{gid:08d}"][self.noise_inputs.spl_type]

        extended_xy, extended_turbine_spl = _extend_sound(
            turbine_spl, radius=17
        )
        extended_turbine_power = 10 ** (extended_turbine_spl / 10)
        return LinearNDInterpolator(extended_xy, extended_turbine_power)

    def compute_noise(self, turbine_inds, plant_level=True):
        """Compute sound levels for a selection of turbines.

        Parameters
        ----------
        turbine_inds : ndarray
            Boolean mask or index array selecting turbines in the layout.
        plant_level : bool, optional
            If `True`, sum turbine powers before converting to dB. If `False`,
            return the loudest single-turbine level at each observer.

        Returns
        -------
        ndarray
            Sound level in dB at each observer location.
        """

        selected_power = self.turbines_power[turbine_inds.astype(bool)]

        if selected_power.size == 0:
            return np.array([0])  # doesn't matter how many obs to return

        if plant_level:
            power_sum = selected_power.sum(axis=0)
        else:
            power_sum = selected_power.max(axis=0)

        return 10 * np.log10(np.maximum(power_sum, 1.0))

    def total_noise_penalty(self, turbine_inds):
        """Sum plant-level sound violations above the configured limit

        Parameters
        ----------
        turbine_inds : ndarray
            Boolean mask or index array selecting turbines in the layout.

        Returns
        -------
        float
            Sum of sound level in dB at each observer location that
            exceeds the noise limit.
        """
        noise = self.compute_noise(turbine_inds, plant_level=True)
        return np.sum(noise[noise > self.noise_inputs.plant_noise_limit])

    def violation_stats(self, turbine_inds):
        """Statistics about noise violations

        Parameters
        ----------
        turbine_inds : ndarray
            Boolean mask or index array selecting turbines in the layout.

        Returns
        -------
        float
            Sum of sound level in dB at each observer location that
            exceeds the noise limit.
        """
        noise = self.compute_noise(turbine_inds, plant_level=True)
        violations = (noise > self.noise_inputs.plant_noise_limit).sum()
        num_obs = self.shifted_obs_locs.shape[1]
        violation_pct = 100 * violations / num_obs if num_obs > 0 else 0
        return violations, num_obs, violation_pct


def _extend_sound(turbine_spl, radius=15.5):
    """Extend turbine SPL data beyond the tabulated radial distance.

    Parameters
    ----------
    turbine_spl : ndarray
        Two-dimensional SPL table indexed by azimuth and radial distance.
    radius : float, optional
        Maximum interpolation radius in kilometers.

    Returns
    -------
    tuple
        Tuple of ``(x_y_points, spl_values)`` describing the extended sound
        field.
    """

    theta = np.arange(0., 360., 22.5)
    r1 = np.arange( 10.,  500., 10.)
    r2 = np.arange(500., 5001., 20.)
    r_turbine = np.hstack((r1, r2))
    r_ext = np.arange(5100., radius * 1000, 100)
    r = np.hstack((r1, r2, r_ext))
    r, theta = np.meshgrid(r, theta)
    x = r * np.cos(np.radians(-theta + 90))
    y = r * np.sin(np.radians(-theta + 90))

    extended_xy = np.vstack((x.flatten(), y.flatten())).T
    extended_spl = np.zeros_like(r)
    for i, spl_1d in enumerate(turbine_spl):
        spl_ext = spl_1d[-1] - 20 * np.log10(r_ext / r_turbine[-1])
        extended_spl[i, :] = np.hstack((spl_1d, spl_ext))

    return extended_xy, extended_spl.flatten()


def _rel_obs_locs(sc_point, obs_tiff_fp, x_locations, y_locations, buffer=0):
    """Compute the locations of observers relative to each turbine.

    Parameters
    ----------
    sc_point : SupplyCurvePoint
        Supply curve point defining the SC-point bounds and CRS.
    obs_tiff_fp : str | os.PathLike
        Raster file containing observer pixels marked with value 1.
    x_locations : ndarray
        Turbine x coordinates in the SC-point frame.
    y_locations : ndarray
        Turbine y coordinates in the SC-point frame.
    buffer : float, optional
        Buffer distance around the SC-point boundary to include observer locations.

    Returns
    -------
    ndarray
        Observer x/y coordinates relative to each turbine.
    """

    profile = sc_point.exclusions.excl_h5.profile

    excl_crs = profile["crs"]
    full_transform = Affine(*profile["transform"][:6])
    window = Window.from_slices(sc_point.rows, sc_point.cols)
    left, bottom, right, top = window_bounds(window, full_transform)
    left -= buffer
    right += buffer
    bottom -= buffer
    top += buffer

    with rioxarray.open_rasterio(obs_tiff_fp) as obs_raster:
        src_left, src_bottom, src_right, src_top = transform_bounds(
            excl_crs,
            obs_raster.rio.crs,
            left,
            bottom,
            right,
            top,
        )

        # Small pad so edge pixels are not dropped by bound rounding
        xres, yres = obs_raster.rio.resolution()
        src_left -= abs(xres)
        src_right += abs(xres)
        src_bottom -= abs(yres)
        src_top += abs(yres)

        subset = obs_raster.rio.clip_box(
            minx=src_left,
            miny=src_bottom,
            maxx=src_right,
            maxy=src_top,
        ).squeeze(drop=True)

        mask = np.isclose(subset.values, 1)
        row_idx, col_idx = np.where(mask)
        x_src = subset.x.values[col_idx]
        y_src = subset.y.values[row_idx]

        if str(obs_raster.rio.crs) != str(excl_crs):
            x_sc, y_sc = transform(
                obs_raster.rio.crs,
                excl_crs,
                x_src.tolist(),
                y_src.tolist(),
            )
            x_sc = np.asarray(x_sc)
            y_sc = np.asarray(y_sc)
        else:
            x_sc = np.asarray(x_src, dtype=float)
            y_sc = np.asarray(y_src, dtype=float)

    x_rel = x_sc - left
    y_rel = y_sc - bottom
    obs_loc = np.c_[x_rel, y_rel]
    turbine_locs = np.c_[x_locations, y_locations]
    return turbine_locs[:, None, :] - obs_loc



def _get_turbine_res_gids(x_locations, y_locations, sc_point):
    """Map turbine coordinates to resource gids within the SC-point.

    Parameters
    ----------
    x_locations : ndarray
        Turbine x coordinates in the SC-point frame.
    y_locations : ndarray
        Turbine y coordinates in the SC-point frame.
    sc_point : SupplyCurvePoint
        Supply curve point containing the resource gid map.

    Returns
    -------
    ndarray
        Resource gids corresponding to each turbine location.
    """

    nrows, ncols = np.shape(sc_point.include_mask)
    pixel_side_length = sc_point.area_based_pixel_side_length_meters
    row_idx = np.clip((y_locations // pixel_side_length).astype(int),
                      0, nrows - 1)
    col_idx = np.clip((x_locations // pixel_side_length).astype(int),
                      0, ncols - 1)
    return sc_point.tm[row_idx, col_idx]
