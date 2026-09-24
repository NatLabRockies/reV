# -*- coding: utf-8 -*-
"""Collection of functions used to hybridize columns in rep profiles meta.

@author: ppinchuk
"""
import logging
from warnings import warn

import numpy as np
import pandas as pd

from reV.utilities import SupplyCurveField
from reV.utilities.exceptions import OutputWarning

logger = logging.getLogger(__name__)


def aggregate_solar_capacity(h):
    """Compute the total solar capcity allowed in hybridization.

    Parameters
    ----------
    h : `reV.hybrids.Hybridization`
        Instance of `reV.hybrids.Hybridization` class containing the
        attribute `hybrid_meta`, which is a DataFrame containing
        hybridized meta data.

    Returns
    -------
    data : Series | None
        A series of data containing the capacity allowed in the hybrid
        capacity sum, or `None` if 'hybrid_solar_capacity' already
        exists.

    Notes
    -----
    No limiting is done on the ratio of wind to solar. This method
    checks for an existing 'hybrid_solar_capacity'. If one does not
    exist, it is assumed that there is no limit on the solar to wind
    capacity ratio and the solar capacity is copied into this new
    column.
    """
    if f'hybrid_solar_{SupplyCurveField.CAPACITY_AC_MW}' in h.hybrid_meta:
        return None
    return h.hybrid_meta[f'solar_{SupplyCurveField.CAPACITY_AC_MW}']


def aggregate_wind_capacity(h):
    """Compute the total wind capcity allowed in hybridization.

    Parameters
    ----------
    h : `reV.hybrids.Hybridization`
        Instance of `reV.hybrids.Hybridization` class containing the
        attribute `hybrid_meta`, which is a DataFrame containing
        hybridized meta data.

    Returns
    -------
    data : Series | None
        A series of data containing the capacity allowed in the hybrid
        capacity sum, or `None` if 'hybrid_solar_capacity' already
        exists.

    Notes
    -----
    No limiting is done on the ratio of wind to solar. This method
    checks for an existing 'hybrid_wind_capacity'. If one does not
    exist, it is assumed that there is no limit on the solar to wind
    capacity ratio and the wind capacity is copied into this new column.
    """
    if f'hybrid_wind_{SupplyCurveField.CAPACITY_AC_MW}' in h.hybrid_meta:
        return None
    return h.hybrid_meta[f'wind_{SupplyCurveField.CAPACITY_AC_MW}']


def aggregate_capacity(h):
    """Compute the total capcity by summing the individual capacities.

    Parameters
    ----------
    h : `reV.hybrids.Hybridization`
        Instance of `reV.hybrids.Hybridization` class containing the
        attribute `hybrid_meta`, which is a DataFrame containing
        hybridized meta data.

    Returns
    -------
    data : Series | None
        A series of data containing the aggregated capacity, or `None`
        if the capacity columns are missing.
    """
    sc = f'hybrid_solar_{SupplyCurveField.CAPACITY_AC_MW}'
    wc = f'hybrid_wind_{SupplyCurveField.CAPACITY_AC_MW}'
    missing_solar_cap = sc not in h.hybrid_meta.columns
    missing_wind_cap = wc not in h.hybrid_meta.columns
    if missing_solar_cap or missing_wind_cap:
        return None

    total_cap = h.hybrid_meta[sc] + h.hybrid_meta[wc]
    return total_cap


def aggregate_capacity_factor(h):
    """Compute the capacity-weighted mean capcity factor.

    Parameters
    ----------
    h : `reV.hybrids.Hybridization`
        Instance of `reV.hybrids.Hybridization` class containing the
        attribute `hybrid_meta`, which is a DataFrame containing
        hybridized meta data.

    Returns
    -------
    data : Series | None
        A series of data containing the aggregated capacity, or `None`
        if the capacity and/or mean_cf columns are missing.
    """

    sc = f'hybrid_solar_{SupplyCurveField.CAPACITY_AC_MW}'
    wc = f'hybrid_wind_{SupplyCurveField.CAPACITY_AC_MW}'
    scf = f'solar_{SupplyCurveField.MEAN_CF_AC}'
    wcf = f'wind_{SupplyCurveField.MEAN_CF_AC}'
    missing_solar_cap = sc not in h.hybrid_meta.columns
    missing_wind_cap = wc not in h.hybrid_meta.columns
    missing_solar_mean_cf = scf not in h.hybrid_meta.columns
    missing_wind_mean_cf = wcf not in h.hybrid_meta.columns
    missing_any = (missing_solar_cap or missing_wind_cap
                   or missing_solar_mean_cf or missing_wind_mean_cf)
    if missing_any:
        return None

    solar_cf_weighted = h.hybrid_meta[sc] * h.hybrid_meta[scf]
    wind_cf_weighted = h.hybrid_meta[wc] * h.hybrid_meta[wcf]
    total_capacity = aggregate_capacity(h)
    hybrid_cf = (solar_cf_weighted + wind_cf_weighted) / total_capacity
    return hybrid_cf


def aggregate_lcoe(h):
    """Compute hybrid LCOE from annual cost and hybrid generation.

    The primary calculation sums annualized capital, fixed operating,
    and variable operating costs for each active resource. If those
    inputs are unavailable, the calculation falls back to an
    energy-weighted mean of the source LCOE values. Annual generation
    uses the reV convention of 8,760 hours per year.

    Parameters
    ----------
    h : `reV.hybrids.Hybridization`
        Instance containing the hybridized meta data.

    Returns
    -------
    data : pd.Series
        Hybrid LCOE in $/MWh. Rows that cannot be computed by either
        method are returned as ``NaN``.
    """
    meta = h.hybrid_meta
    hybrid_capacity = _column_or_nan(
        meta, f"hybrid_{SupplyCurveField.CAPACITY_AC_MW}"
    )
    hybrid_cf = _column_or_nan(
        meta, f"hybrid_{SupplyCurveField.MEAN_CF_AC}"
    )
    hybrid_aep = hybrid_capacity * hybrid_cf * 8760
    valid_hybrid_aep = np.isfinite(hybrid_aep) & (hybrid_aep > 0)
    resource_data = [
        _resource_lcoe_data(meta, resource)
        for resource in ("solar", "wind")
    ]
    annual_cost = sum(data["annual_cost"] for data in resource_data)
    component_inputs_valid = valid_hybrid_aep & np.logical_and.reduce(
        [data["component_valid"] for data in resource_data]
    )
    fallback_numerator = sum(
        data["fallback_numerator"] for data in resource_data
    )
    fallback_inputs_valid = valid_hybrid_aep & np.logical_and.reduce(
        [data["fallback_valid"] for data in resource_data]
    )

    hybrid_lcoe = (annual_cost / hybrid_aep).where(component_inputs_valid)
    fallback_lcoe = (fallback_numerator / hybrid_aep).where(
        fallback_inputs_valid
    )
    needs_fallback = ~component_inputs_valid
    fallback_used = needs_fallback & fallback_inputs_valid
    hybrid_lcoe.loc[fallback_used] = fallback_lcoe.loc[fallback_used]

    if needs_fallback.any():
        _warn_lcoe_fallback(needs_fallback, fallback_used, hybrid_lcoe)

    return hybrid_lcoe.astype(np.float32)


def _resource_lcoe_data(meta, resource):
    """Compute annual cost and fallback data for one resource."""
    capacity = _column_or_nan(
        meta, f"hybrid_{resource}_{SupplyCurveField.CAPACITY_AC_MW}"
    )
    capacity_factor = _column_or_nan(
        meta, f"{resource}_{SupplyCurveField.MEAN_CF_AC}"
    )
    resource_aep = capacity * capacity_factor * 8760
    active = np.isfinite(capacity) & (capacity > 0)

    capital_cost = _column_or_nan(
        meta,
        f"{resource}_{SupplyCurveField.COST_SITE_CC_USD_PER_AC_MW}",
    )
    fixed_operating_cost = _column_or_nan(
        meta,
        f"{resource}_{SupplyCurveField.COST_SITE_FOC_USD_PER_AC_MW}",
    )
    variable_operating_cost = _column_or_nan(
        meta,
        f"{resource}_{SupplyCurveField.COST_SITE_VOC_USD_PER_AC_MWH}",
    )
    fixed_charge_rate = _column_or_nan(
        meta, f"{resource}_{SupplyCurveField.FIXED_CHARGE_RATE}"
    )
    component_valid = ~active | (
        np.isfinite(capital_cost)
        & np.isfinite(fixed_operating_cost)
        & np.isfinite(variable_operating_cost)
        & np.isfinite(fixed_charge_rate)
    )
    annual_cost = capacity * (
        fixed_charge_rate * capital_cost + fixed_operating_cost
    ) + resource_aep * variable_operating_cost

    source_lcoe = _column_or_nan(
        meta, f"{resource}_{SupplyCurveField.MEAN_LCOE}"
    )
    generating = np.isfinite(resource_aep) & (resource_aep > 0)
    return {
        "annual_cost": annual_cost.where(active, 0),
        "component_valid": component_valid,
        "fallback_numerator": (source_lcoe * resource_aep).where(
            generating, 0
        ),
        "fallback_valid": ~generating | np.isfinite(source_lcoe),
    }


def _warn_lcoe_fallback(needs_fallback, fallback_used, hybrid_lcoe):
    """Warn about fallback and unresolved hybrid LCOE rows."""
    unresolved = needs_fallback & hybrid_lcoe.isna()
    msg = (
        "Could not compute hybrid LCOE from cost components for "
        f"{needs_fallback.sum()} row(s); used the energy-weighted source "
        f"LCOE fallback for {fallback_used.sum()} row(s). Hybrid LCOE "
        f"remains NaN for {unresolved.sum()} row(s)."
    )
    logger.warning(msg)
    warn(msg, OutputWarning)


def _column_or_nan(meta, column):
    """Return a meta column or an aligned all-NaN series."""
    if column in meta:
        return meta[column]
    return pd.Series(np.nan, index=meta.index)


HYBRID_METHODS = {
    f'hybrid_solar_{SupplyCurveField.CAPACITY_AC_MW}': (
        aggregate_solar_capacity
    ),
    f'hybrid_wind_{SupplyCurveField.CAPACITY_AC_MW}': aggregate_wind_capacity,
    f'hybrid_{SupplyCurveField.CAPACITY_AC_MW}': aggregate_capacity,
    f'hybrid_{SupplyCurveField.MEAN_CF_AC}': aggregate_capacity_factor,
    f"hybrid_{SupplyCurveField.MEAN_LCOE}": aggregate_lcoe,
}
