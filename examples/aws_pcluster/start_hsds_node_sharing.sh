#!/bin/bash
# shellcheck disable=SC2155
#
# Install and start a local NREL Public Data Service with HSDS.
# Ubuntu 24.04
# Online Data Browser:
#     https://data.openei.org/s3_viewer?bucket=nrel-pds-hsds&prefix=nrel

thisfile=$(realpath $0)
echo "Running $thisfile..."

# Log to file
if [ "$1" == "--log" ]; then
    logfpath="./logs/stdout/start_hsds_$HOSTNAME-$$.logs"
    if [ -f $logfpath ]; then
        rm $logfpath
    fi
    if [ ! -d ./logs/stdout ]; then
        mkdir -p ./logs/stdout
    fi
    exec 3>&1 1>$logfpath 2>&1
fi

# Set the location of the HSDS code directory
export HSDS_DIR="$HOME/hsds"

# Set a location for the HSDS image
LOCAL_IMAGE=/scratch/hsds_docker_image.tar

# Get this instance's ID and type (with Instance Meta Data Service (IMDS) V2 below, comment out and use V1 below if needed)
export TOKEN=$(curl --silent -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")
export EC2_ID=$(curl --silent -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/instance-id)
export EC2_TYPE=$(curl --silent -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/instance-type)

# Get the ID and Type using IMDS V1
# export EC2_ID=$(curl -s http://169.254.169.254/latest/meta-data/instance-id)
# export EC2_TYPE=$(curl -s http://169.254.169.254/latest/meta-data/instance-type)

# Stop server if requested
if [[ $1 == "--stop" ]]; then
    echo "Stopping HSDS server."
    cd $HSDS_DIR
    ./runall.sh --stop
    exit 0
fi

# Define Docker checking and installation functions
check_hsds () {
    hsds_running=false
    if command -v docker &>/dev/null; then
        echo "HSDS present on system."
        if [[ $(docker ps | wc -l) -ge 5 ]]; then
            echo "HSDS is running."
            hsds_running=true
        fi
    fi
}

install_docker () {
    # Run this convenient docker installation script
    curl https://get.docker.com | sudo sh

    # Set the socket file permissions
    sudo chmod 666 /var/run/docker.sock

    # Update groups
    sudo groupadd docker
    sudo usermod -aG docker "$USER"

    # See if we've saved an image so we avoid pulling it each time
    if [[ -f  $LOCAL_IMAGE ]]; then
        echo "Local Docker image found, loading $LOCAL_IMAGE"
        sudo docker load < $LOCAL_IMAGE
    fi
}

# First check to see if HSDS is running
check_hsds
if [ "$hsds_running" = true ]; then
    # We're good to go
    echo HSDS service running: $hsds_running
    exit 0
else
    # Lock this file so only one process on any EC2 hardware can run it
    lockfile=/var/lock/start_hsds_$EC2_ID.flock
    thisfile=$(realpath $0)
    exec 9>$lockfile || exit 1
    flock -x -w 600 9 || { echo "ERROR: flock() failed." >&2; exit 1; }
    echo "Locking $thisfile with $lockfile..."

    # Clone HSDS repository if not found
    if [ ! -d $HSDS_DIR ]; then
        echo "$HSDS_DIR not found, cloning https://github.com/HDFGroup/hsds.git..."
        git clone https://github.com/HDFGroup/hsds.git $HSDS_DIR
        cd $HSDS_DIR
    fi

    # Install Docker if not found
    if type docker &>/dev/null; then
        echo "Docker found."
    else
        echo "Docker not found, installing..."
        install_docker
    fi

    # Second check if HSDS is running, start it if not
    check_hsds
    if [ "$hsds_running" = false ]; then
        # Double check that Docker is running
        echo "HSDS not running, starting docker service..."
        sudo service docker start

        # Start HSDS
        echo "Starting local HSDS server..."
        cd $HSDS_DIR  || exit 1
        echo $PWD
        ./runall.sh "$(nproc --all)"

        # Save image to a local file if it hasn't been already
        if [[ ! -f $LOCAL_IMAGE ]]; then
            echo "No local Docker image found, saving HSDS image to $LOCAL_IMAGE"
            sudo docker save hdfgroup/hsds:latest -o $LOCAL_IMAGE
            sudo chown ubuntu $LOCAL_IMAGE
        fi
    else
        echo HSDS service running: $hsds_running
    fi

    # Give HSDS a chance to warm up (not sure why but this helps a ton!)
    sleep 15s

    # Release the lock on this file (Not necessary unless further steps are added)
    echo "Releasing lock on $thisfile"
    flock -u 9

fi

# Test with rex Resource to make sure it's actually working
test=$(python /scratch/reV-tutorial/tutorial_13_rev_in_cloud/test_hsds.py)
echo "Running HSDS Python access test..."
if [[ $test == *"rex data access test passed."* ]]; then
    echo "Python data access test PASSED"
else
    echo "Python data access test FAILED"
fi

# Now test with hsls to see if one method works while the other doesn't
test_fpath="/nrel/wtk/conus/wtk_conus_2010.h5"
test=$(hsls /nrel/wtk/conus/wtk_conus_2010.h5 | grep windspeed_10m)
echo "Running HSDS access test on $test_fpath..."
if [[ $test == "windspeed_10m Dataset {8760, 2488136}" ]]; then
    echo "HSLS data access test PASSED"
else
    echo "HSLS data access test FAILED"
fi

# Print out some server information
state=$(hsinfo | grep "server state")
uptime=$(hsinfo | grep "up:" | cut -d":" -f2)
echo "HSDS $state, uptime: $uptime"
