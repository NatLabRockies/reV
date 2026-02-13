# Memory Considerations

When configuring execution control parameters for a reV run, there are important considerations 


reV 5-minute NSRDB read through HSDS has apparently been consuming more memory than our HDF5 methods. This is a quick look at memory useage between local- and remote-accessed HDF5 data reads. 

## Local File - /kfs2/datasets/NSRDB/conus/nsrdb_conus_irradiance_2018.h5
### h5py: 2000 sites, 1 time step(s) (So the full 5-minute data)
  - data_size=0.420 GB
  - mem_size=0.420 GB
  - mem_peak=0.420 GB
### rex: 2000 sites, 1 time step(s)
  - data_size=0.420 GB
  - mem_size=0.420 GB
  - mem_peak=0.420 GB
### h5py: 2000 sites, 6 time step(s) (So, this recreates the main half-hour NSRDB)
  - data_size=0.070 GB
  - mem_size=0.070 GB
  - mem_peak=0.420 GB
### rex: 2000 sites, 6 time step(s)
  - data_size=0.070 GB
  - mem_size=0.070 GB
  - mem_peak=0.420 GB

## Remote File Read - /nrel/nsrdb/GOES/conus/v4.0.0/nsrdb_conus_2018.h5
### h5pyd: 2000 sites, 1 time step(s),
  - data_size=0.420 GB
  - mem_size=0.421 GB
  - mem_peak=1.267 GB
### rex: 2000 sites, 1 time step(s)
  - data_size=0.420 GB
  - mem_size=0.421 GB
  - mem_peak=1.267 GB
### h5pyd: 2000 sites, 6 time step(s)
  - data_size=0.070 GB
  - mem_size=0.070 GB
  - mem_peak=1.267 GB
### rex: 2000 sites, 6 time step(s)
  - data_size=0.070 GB
  - mem_size=0.070 GB
  - mem_peak=1.267 GB