reV Spatial Economics with SAM Single Owner Model
=================================================

This example set shows how several of the reV features (batching, pipeline,
site-data) can be used in concert to create complex spatially-variant economic
analyses.

This example modifies the tax rate and PPA price inputs for each state.
More complex input sets on a site-by-site basis can be easily generated using a
similar point-by-point input method.

Workflow Description
--------------------

The batching config in this example represents the high-level executed module.
The user executes the following command:

.. code-block:: bash

    reV batch -c "../config_batch.json"

This creates and executes three batch job pipelines. You should be able to see
in ``config_batch.json`` how the actual input generation files are
parameterized. This is the power of the batch module - it's sufficiently
generic to modify ANY key-value pairs in any ``.json`` file, including other
config files.

The first module executed in each job pipeline is the econ module. This example
shows how the site-specific inputs can be specified via the ``project_points.csv``.

Specifically, the ``project_points.csv`` file sets site-specific input data
corresponding to each gid. Data inputs keyed by each column header in the
``project_points.csv`` file will be added to or replace an input in the
"tech_configs" ``.json`` files (sam_files).
