"""Tests for the bespoke gradient-free optimizer."""

from unittest.mock import patch

import numpy as np

from reV.bespoke.gradient_free import GeneticAlgorithm


def test_initial_population_has_no_zero_capacity_layouts():
    """Test zero-capacity layouts are repaired before fitness evaluation."""

    bits = np.ones(3, dtype=int)
    bounds = np.tile((0, 2), (3, 1))
    variable_type = np.array(["int"] * 3)

    with patch("numpy.random.randint", return_value=np.zeros((5, 3))):
        ga = GeneticAlgorithm(
            bits,
            bounds,
            variable_type,
            objective_function=np.sum,
            population_size=6,
        )

    assert np.all(np.any(ga.parent_population, axis=1))
