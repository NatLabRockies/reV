Running reV on an AWS Parallel Cluster
===

The Renewable Energy Potential Model (reV) was originally designed to run on National Laboratory of the Rockies (NLR) High Performance Computer systems (HPCs) and access energy resource data on a local file system. Users wishing to run large-scale reV jobs without access to NLR's HPC can now recreate the original work flow using an [Amazon Web Services (AWS) Parallel Cluster](https://aws.amazon.com/hpc/parallelcluster/) to provide the compute infrastructure and the [Highly Scalable Data Service (HSDS)](https://www.hdfgroup.org/solutions/highly-scalable-data-service-hsds/) to provide access to resource data. This document will walk you through how to set these services up and start using large-scale reV in the cloud.

This guide is designed to provide both a step-by-step guide and detailed explanations for the basic components of a reV environment on an AWS Parallel Cluster. It is oriented towards analysts with moderate to intermediate levels of experience with AWS. More experienced cloud architects may be interested in this Terraform-based guide produced by Switchbox: [https://github.com/switchbox-data/rev-parallel-cluster](https://github.com/switchbox-data/rev-parallel-cluster).

## 1) Set Up an AWS Account
You need an AWS account and all prerequisites setup before you can run reV on AWS Parallel Cluster. You also need to ensure that networking components such as a Virtual Private Cloud (VPC), subnetworks (or subnets), a Network Address Translation gateway (NAT), and an internet gateway already exist.  The subnet's Classless Inter-Domain Routing range (CIDR) should be large enough to handle the number of compute nodes, a CIDR of `/24` is a good starting point. Record the `SubnetId` you plan to use for the head node and compute nodes, it must be reachable from the server/workstation you will use for SSH access to the head node in later steps. The instructions below provide guidance for users leveraging an individual AWS account as well as guidance if your working within an institutional IT organization's AWS account.

### 1a) Individual AWS Account
If you are creating an individual AWS account to run reV, review the AWS recommended steps for creating a new AWS Account: [https://docs.aws.amazon.com/accounts/latest/reference/manage-acct-creating.html](https://docs.aws.amazon.com/accounts/latest/reference/manage-acct-creating.html) as well as the AWS Parallel Cluster prerequisites before proceeding: [https://docs.aws.amazon.com/parallelcluster/latest/ug/install-v3.html#prerequisites](https://docs.aws.amazon.com/parallelcluster/latest/ug/install-v3.html#prerequisites).

We recommend the ["two subnet"](https://docs.aws.amazon.com/parallelcluster/latest/ug/network-configuration-v3-two-subnets.html) configuration for Parallel Cluster networking.  This means the head node will use a public `SubnetId` (you should limit ssh/22 TCP access to just your IP in the security group) and the compute nodes use a private `SubnetId`. Review the [AWS Recommended Parallel Cluster network configurations](https://docs.aws.amazon.com/parallelcluster/latest/ug/network-configuration-v3.html) for more details on network options and best practices.

### 1b) Institutional AWS Account
Institutional users generally work within an AWS Organization or a preconfigured landing zone. Coordinate with your cloud administrator to verify budget, budget controls, and alert thresholds before launching resource-intensive clusters.
- Its highly recommended to setup AWS Budget alerts for projected usage: [https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-managing-costs.html](https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-managing-costs.html).  This can help reduce the risk of a surprise AWS bill and keep costs in control.
> Note: Your VPC must have DNS Resolution = yes, DNS Hostnames = yes and DHCP options with the correct domain name for the Region. The default DHCP Option Set already specifies the required AmazonProvidedDNS. If specifying more than one domain name server, see DHCP options sets in the Amazon VPC User Guide.*

### 1c) IAM versus AWS Single Sign-on (SSO)
At the time of writing, reV and HSDS cannot authenticate with temporary credentials issued by AWS IAM Identity Center (SSO) or any workflow that relies solely on Security Token Service (STS). To avoid authentication failures, create an IAM user with access keys and use those keys when configuring the AWS CLI in step [5b) Configure Data Access](#5b-configure-data-access). If your organization must rely on SSO, consult the HSDS maintainers for updates on STS compatibility before proceeding.

SSO can be used to provision the cluster, but the specific configurations at [5b) Configure Data Access](#5b-configure-data-access) requires IAM access keys at this time of writing and will break when using SSO or STS.


## 2) Install AWS Command-Line Interfaces
Many of the instructions that follow will utilize AWS command-line interfaces (CLIs). Full instructions for installing and using AWS CLIs can be found in the official Amazon page here: [https://docs.aws.amazon.com/cli/latest/userguide/cli-chap-getting-started.html](https://docs.aws.amazon.com/cli/latest/userguide/cli-chap-getting-started.html). To install these programs any user may download the installers from AWS's site [https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html), Unix users may use their OS's package manager (i.e., brew, apt, dnf, yum, etc), or you may create a virtual Python environment and install using `pip` or any other Python package manager, e.g.,:

```bash
python3 -m venv ~/envs/aws
source ~/envs/aws/bin/activate
pip install awscli aws-parallelcluster
```

Once you have installed these two programs, you then need to link them to your AWS account with a profile. The easiest way to do this is to run the `aws configure` or `aws configure sso` command and follow the prompts to build a profile configuration file, which will be stored in a hidden AWS directory in your home folder (`~/.aws`). Before running this command, make sure you know your access key ID, secret access key, and target AWS region. We will default to JSON for the output format prompt. The resulting file will look like this:

Single-Sign On:
`~/.aws/config`
```yaml
[profile profile_name]
sso_session = account_name
sso_account_id = ************
sso_role_name = developers
region = us-west-2
output = json

[sso-session account_name]
sso_start_url = https://org-name.awsapps.com/start/#
sso_region = us-west-2
sso_registration_scopes = sso:account:access
```

Identity and Access Management (IAM):
`~/.aws/config`
```yaml
[profile profile_name]
region = us-west-2
output = json
```
`~/.aws/credentials`
```yaml
[profile_name]
aws_access_key_id = <secret>
aws_secret_access_key = <secret>
```

Moving forward, we need to tell the AWS CLI which profile to use for authentication. You may do this manually for each session by setting the `AWS_PROFILE` environment variable to this name in each command-line session, you may specify the name in a `--profile` option for each CLI command, or you may add the variable to your command-line interpreter's startup script to automate this step, which is what we're suggesting for convenience. Here, we are using a Bash shell so will be editing the `~/.bashrc` script (Linux) or the `~/.bash_profile` (macOS) to add the following line:

```bash
export AWS_PROFILE=profile_name
```

## 3) Configure SSH Access

The most direct way to interact with your parallel cluster is through a Secure Shell (SSH) Protocol connection. This will enable to you to both interact with the operating and file systems and to transfer data to and from the cluster. Because subsequent setup steps will require SSH information, it is best to go ahead and address this one before moving on. To do this, assuming you don't have existing keys stored on your computer, you first need to generate a pair (public and private) of SSH keys. There are a few ways to do this, outlined below.

> Note: While the most common of these algorithms (the Rivest–Shamir–Adleman cryptosystem or `RSA`) will work for some operating systems, other images on AWS do not allow it and will require you to use a more up-to-date algorithm. In this case, you may use the newer `Ed25519` option, which is based on the Edwards-curve Digital Signature Algorithm. For more on AWS and SSH, see: [https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-key-pairs.html](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-key-pairs.html).


#### Method #1: Generate a key-pair on your local machine and copy the public key to AWS's Secrets manager
Users on Unix systems may use the built-in `ssh-keygen` command. Windows users may also use this command, though it will require the installation of an OpenSSH server. There are different algorithms and keysizes that you may specify when running this command and which one will be acceptable for your parallel cluster will depend on the security requirements of the operating system you chose when creating it. Here, given the limitations on some operating systems described above, we will generate a Ed25519 key pair with the following command:

```
ssh-keygen -t ed25519
```

You will be prompted to enter a file in which to save the key pair. You may enter a file path if you wish, or you may just push enter to place your keys in the default location (`~/.ssh/id_ed25519` for Unix systems). Then you will be prompted to enter a passphrase, which is optional but protects you in cases where your private key is compromised. So, you may either use a passphrase or you may push enter for this prompt and the subsequent passphrase verification step to avoid having to enter the phrase each time you SSH into your cluster.

Following this step, assuming you used the default location, you will find your private key (`id_ed25519`) and public key (`id_25519.pub`) in the hidden `~/.ssh` directory. Open your EC2 portal (search for this in the search bar on the top of the page to the right on the AWS icon) and under "Network & Security" click the "Key Pairs" option. On the top right of this page, you'll find a blue "Actions" button with a dropdown option, use that to navigate to the "Import key pair" page. Give your key a name and either click the browse button to upload your public  key contents or paste the contents directly into the box below this option. Remember this key name, you'll need it when configuring your cluster. Once this is done, click the orange "Import key pair" to the bottom-right and you're done.

#### Method #2: Generate a key-pair through AWS Key Manager and copy the public key to your local machine
To use AWS to generate a key pair for you, navigate to the same "Key Pairs" page from your EC2 portal, but click the orange "Create key pair" button instead. You will be asked to give the key pair a name, as before, to choose both the encryption algorithm (RSA or ED25519), and to choose the private key format type. Assuming you are using an OpenSSH server, as described thus far, choose the `.pem` extension and click the orange "Create key pair" button at the bottom right. You will see a download screen pop up. Navigate to the location on your file system where'd you like to store the key file. We would suggest the default `~/.ssh` directory, but be careful not to overwrite any existing keys. Once you've finished this step you are done. 

#### Method #3: Generate a key-pair on your local machine and copy the public key to AWS
The AWS CLI provides an option to import a key pair directly from your terminal. To do this, follow the steps outlined in `Method #1`, but instead of importing your private key in the browser, run the following command:

```Bash
aws ec2 import-key-pair --key-name "your-key-name" --public-key-material "~/.ssh/ed_25519.pub"  # Or wherever you put the public key
```

For more information on this method, see
[https://docs.aws.amazon.com/cli/latest/reference/ec2/import-key-pair.html](https://docs.aws.amazon.com/cli/latest/reference/ec2/import-key-pair.html)


## 4) Setup and Deploy the Parallel Cluster
An AWS Parallel Cluster provides the user a head node that controls the distribution of computational work to a number of compute nodes, each of which are spun up on demand and shutdown after the work is finished. For reV runs, this also requires a shared file system. Once an AWS account is created, the user is able to choose the type of cluster they want and parameterize its characteristics. The following outlines how to configure and spin up a cluster using the AWS CLI, after which you will have access to the head node and file system until you delete the cluster (as outlined in [step 8](#8-aws-parallel-cluster-updating-and-deleting)).

### 4a) Differences with an HPC
At this point, it is worthwhile to point out that there are default behaviors in an AWS Parallel Cluster that may differ from what an user with access to an onsite HPC might expect. This can cause some confusion when configuring a reV job since the model was designed specifically to run on NLR HPC systems.

On NLR's HPC, Slurm's exclusive node access option is turned on. If you submit a job to a compute node, that job has exclusive access to the entire server (i.e., all cpus and available memory). If you submit a second job, that job will check out a second compute node and block all those resources from other jobs submitted through the scheduler. So, this is the assumption that reV makes. This is more appropriate for HPC systems to prevent multiple users from interfering with each other's jobs.

AWS, however, uses the default SLURM settings and shares nodes between jobs by default. When you submit that second job, if there are still enough resources available on the first compute node, it will kick that job off on it. As you kick more jobs off, it will continue using that first node until it runs out of CPUs and/or memory after which the scheduler will spin up a second node and start kicking jobs off on that one. So, this make sense from an efficiency/cost perspective and gets around underutilization problems that can occur with exclusive node scheduling behavior, but it requires you to think differently about your execution control in reV configurations if you're used to this default behavior.

Alternatively, you can tweak a few settings to effectively turn node sharing off. Without having to spin up a new cluster, you may simply set the `memory` option in the reV `execution_control` block to approximately match the available memory on the target compute node. If you want to change the default behavior to be exclusive, you may add `JobExclusiveAllocation = true` to the target SLURM Queue (e.g., standard or bigmem in the example) in your AWS Parallel Cluster configuration file before spinning up your cluster. You may also specify the exclusive node option using the `feature` option in your `execution_control` block by setting the value to `--exclusive`.

Another subtle difference between NLR's Slurm setting and the default parameters used in AWS involves checking out an interactive node. The `salloc` command allows you to manually check out a compute node of your choosing. This may be useful if you wish to monitor a reV job mid-stream or if you'd like to check something like memory overhead before kicking your jobs off. On NLR's HPC systems, this will put you in a resource queue which can take more or less time to get through depending on how many other users are attempting to connect to the same compute nodes on the system. On high-traffic days, this may take a signficant amount of time depending on your node choice, how long you asked to use the resource, and how many other users are trying to checkout the same type of node. On low-traffic days, you may be instantly granted a compute node allocation and will be SSH'd into that node automatically. On an AWS system with default Slurm settings you will not necessarily have to wait for other users, but it will take some time for the node to spin up since these instances aren't on standby as they are on an HPC system. Then, once the node is ready, you will then have to manually log into that node. In this case, you may use the `squeue` command to see the hostname of the machine you checked out and then you can use the `ssh` command to log into it. Slurm settings such as this may be configured to your liking in the [Job Scheduler Section](docs.aws.amazon.com/parallelcluster/latest/ug/Scheduling-v3.html#yaml-Scheduling-Scheduler) of your Parallel Cluster configuration file.


### 4b) The Parallel Cluster Configuration File

The next step is to write a YAML configuration file that specifies the build characteristic of the machines and software you wish to wish to deploy (e.g., operating system, disk, RAM, CPUs, job scheduler, etc.). Here, you may use the AWS CLI for a set of command lines prompts that will guide the build process or you may write your own manually. To use the guided process, use the command below or go to [The AWS Parallel Cluster Configuration page](https://docs.aws.amazon.com/parallelcluster/latest/ug/install-v3-configuring.html) for more detailed instructions.

```bash
pcluster configure --config ./cluster-config.yaml
```

To write your own configuration file, you may start with the [example configuration file](https://github.com/NREL/reV-tutorial/blob/master/tutorial_13_rev_in_cloud/rev-pcluster-config.yaml) provided for you in this repository. Each configuration section used in the example is briefly described below along with some notes on reV-specific considerations. For more information on how to specify your cluster to your needs please visit the latest [AWS documentation](https://docs.aws.amazon.com/parallelcluster/latest/ug/cluster-configuration-file-v3.html) and take a look at some AWS-provided [example configuration files](https://github.com/aws/aws-parallelcluster/tree/release-3.0/cli/tests/pcluster/example_configs).

1. **Region**:

    This is a top-level entry specifying the region of the data center that holds your cluster's hardware. See Amazon's Global Infrastructure page for a map showing all regions [here](https://aws.amazon.com/about-aws/global-infrastructure/regions_az/). We suggest that you use "us-west-2", which is in Oregon, to reduce data transfer latency in the reV generation step (this is where the NLR resource data is stored). 

2. **Image**:

    This section provides an `Os` option for specifying the operating system (OS) you wish to use. The following Linux operating systems are supported in all regions (see [https://docs.aws.amazon.com/parallelcluster/latest/ug/Image-v3.html](https://docs.aws.amazon.com/parallelcluster/latest/ug/Image-v3.html)). We chose Ubuntu 24.04 in the example configuration because the `HSDS` package is tested on it, but other options may be more suitable depending on your comfort levels with the different Linux options or your institution's setup. Do note that different operating systems use different package managers, so that will affect the contents of the Bash script used to connect reV to the HSDS-stored resource data as described in [section 5](#5-configuring-rev).

    - `alinux2`: Amazon Linux 2
    - `alinux2023`: Amazon Linux 2023
    - `ubuntu2004`: Ubuntu 20.04 LTS
    - `ubuntu2204`: Ubuntu 22.04 LTS
    - `ubuntu2404`: Ubuntu 24.04 LTS
    - `rhel8`: Red Hat Enterprise Linux (RHEL) 8
    - `rhel9`: Red Hat Enterprise Linux (RHEL) 9
        > Note that RHEL systems will require registration with an "entitlement server". If you or your organization does not have a RHEL license, you will not be able to install required dependencies with the RHEL package manager (yum). Also, as per the methodology outlined in this guide, you will also need enough licenses to install HSDS and docker on each compute you check out. Because of this, RHEL is not recommended for users without access to RHEL licenses.

3. **HeadNode**

    This section describes the hardware and behavior of the "head" node, which is very similar to the "login" node many HPC users are likely accustomed to. This node does not need the highest performing hardware in your cluster. It only requires needs enough power to allow the user to comfortably navigate the file system, move files around, and to provide reV enough computational resource to efficiently submit jobs to the compute node. The hardware chosen in this example configuration (`t3.large`) is a general purpose, low-cost option with 2 virtual CPUs and 8 GiB of memory. This is "burstable" class of EC2 resources, which charges based on usage and is perfect for a reV head node setup with only periodic file editing and job submission activity. See the Amazon documentation for the [T3 EC2 Instance Class](https://aws.amazon.com/ec2/instance-types/t3/) for more information about this component.

    > Note that this section is also where you will specify the name of the SSH key-pair you created in [section 3](#3-configure-ssh-access). This entry is found in the `Ssh` subsection (`KeyName`).
    
    > Make sure to replace the `SubnetId` value in the `Networking` subsection with the appropriate value given to you by your system administrator or (where would you find this?)

    > Note that we are using read-only access for S3 buckets in this configuration (`AmazonS3ReadOnlyAccess`). This is because we are writing our reV outputs to the shared file system and only use S3 to access the resource data. If, for any reason, you need to elevate or refine your access privileges, change the `AdditionalIamPolicies` `Policy` entries to something more permissible. You may also add additional policies to fit your needs. See all available options here: [https://docs.aws.amazon.com/aws-managed-policy/latest/reference/policy-list.html](https://docs.aws.amazon.com/aws-managed-policy/latest/reference/policy-list.html).

4. **Scheduling**

    A job scheduler is used to distribute computational work to the compute nodes and monitor usage. For multi-user setups, it also handles and prioritizes user requests for resources in a job "queue". This configuration section allows the user to both specify the job scheduler and each compute node that will be managed by that scheduler. In the example setup, the Slurm (originally, an acronym for Simple Linux Utility for Resource Management) job scheduler was used. The AWS Batch scheduler is also available, though this choice will change the configuration parameters needed and is only available on Amazon Linux images. In this section you'll see two different `SlurmQueues` entries; these are two SLURM-managed compute nodes used for different scale reV runs. The first we're calling the `standard` node and it uses a `c6a.12xlarge` EC2 instance. This is a moderately sized setup (48 CPUs, 96 GiB RAM) based on the 3rd generation AMD EPYC processors, which were originally released in 2021 and are suitable for standard reV wind and solar runs at a national scale (i.e., the Contiguous United States). See the AWS entry for the c6a EC2 class [here](https://aws.amazon.com/ec2/instance-types/c6a/). The second entry in the sample config is called the `bigmem` node and uses an m6a.12xlarge EC2 instance which provides 48 EPYC vCPUs as well but increases the available memory to 192 GiB (see [its AWS page here](https://aws.amazon.com/ec2/instance-types/c6a/)). These nodes are more useful for the memory-intensive reV-Bespoke module, which dynamically places individual turbines based on available land, wind resource, and wake losses. The appropriate instance type for your purpose will depend on many factors such as the scale of your reV runs, which modules you wish to use, your budget, etc. 
        
    Detailed information about all options in this section may be found [in AWS Parallel Cluster Scheduling page](https://docs.aws.amazon.com/parallelcluster/latest/ug/Scheduling-v3.html).

5. **SharedStorage**

    The final hardware component in the sample Parallel Cluster configuration file specifies disk and file system settings. reV is highly I/O intensive, relying heavily on the file system to write out temporary chunked files from compute nodes or to read in outputs from previous modules into subsequent modules in the modeling pipeline. Here, we have chosen a solid-state drive (SSD) Lustre file system mounted on `/scratch` with 1.2 TB of storage.  We have found that model performance for large-scale reV runs can be severely hampered by sub-optimal file systems and suggest that you stick with this option, though disk size and mount points will, of course, depend on your use-case. More information on this type of filesystem can be found in [AWS's Fsx for Lustre Documentation Page](aws.amazon.com/fsx/lustre/) and more configuration options for this entry in this configuration file can be found on [AWS's SharedStorage page](https://docs.aws.amazon.com/parallelcluster/latest/ug/SharedStorage-v3.html).

6. **Tags**

    The `Tags` section in the configuration file specifies options for resource management in CloudFormation. It is used in the sample config simply to communicate billing information, but may be used for many other management purposes. To learn more about this section, you may start at the [Parallel Cluster Tag Configuration page](https://docs.aws.amazon.com/parallelcluster/latest/ug/Tags-v3.html), which will then direct you to more resources describing CloudFormation and its options. 



### 4c) Spin Up Cluster

Before you can access your AWS account to create the parallel cluster you configured above,you need to authenticate the connection. To do this, run the appropriate AWS sign-on command using the AWS CLI. For the single sign-on method use:

```bash
aws sso login
```

or, if you didn't set the `AWS_PROFILE` environment variable:
```bash
aws sso login --profile=profile_name
```

Now we can use the `aws-parallelcluster` CLI to create your cluster. Run the following command (if you want to keep default cluster name from the sample config, you may use this command directly, otherwise update the cluster name to your own):
```bash
pcluster create-cluster -c rev-pcluster-config.yaml --cluster-name rev-pcluster
```

If everything was configured correctly, you will see an output JSON message in your shell indicating that the creation process has begun (look for "CREATE_IN_PROGRESS"). This process will take some time to finish, but you may check on it's progress through the EC2 CloudFormation portal in your AWS developers page where you'll see the status of each individual cluster component. You may also run the following command to see its overall status:

```bash
pcluster list-clusters
```

### 4d) Access Cluster

Now that you have a running cluster and an SSH key pair, you may log in to your head node, but you need two more items. First, you need to locate the hostname (or private IP address) associated with this instance. The easiest way to do this is to use the AWS CLI to "describe" your instance and locate the appropriate entry in the response. The response is a large JSON dictionary of information and the IP address is present in several locations. You may use just the `aws ec2 describe-instances` command and find the "PrivateIpAddress" entry manually, or you may use something like the following command to filter the response down to a single line representing the address:

```bash
pcluster describe-cluster --cluster-name rev-pcluster | grep IpAddress | awk '{print $2}'
```

Next, you'll need the username for the server. It is possible to add new usernames to your instances (see, [https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/managing-users.html](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/managing-users.html)), but since we have not described that step here, you will likely need to use the default user for the OS you chose in the image configuration step. Below are the default usernames associated with the three OS groups described in [section 4b](#4b-the-parallel-cluster-configuration-file) but you can find all default names in the "managing users" link above:

- **Amazon Linux**: *ec2-user*
- **RHEL**: *ec2-user* or *root*
- **Ubuntu**: *ubuntu*

Now we'll use the `ssh` command with the public key, username, and IP address (or "hostname") to connect to the clusters head node. This command can be saved as an alias for quick terminal access or used to connect the instance to an Integrated Development Environment (IDE) such as Visual Studio Code (VSCode). VSCode is a popular IDE for activities such as this and is how this team put together the sample runs used to develop this guide; for instructions on how to connect to your head node through VSCode see [https://code.visualstudio.com/docs/remote/ssh](https://code.visualstudio.com/docs/remote/ssh).

```bash
ssh -i ~/.ssh/privatekey.pem user@hostname
```

> Note: If you have created and destroyed several AWS Parallel Clusters trying to get this to work, you may encounter some connection issues associated with SSH. If this happens, try removing entries for previous attempts (lines starting with the hostname or IP address) from the `~/.ssh/known_hosts` file.

## 5) Setup HSDS Server
HSDS can be used to access wind, solar, and other resource data that NLR houses in an AWS S3 bucket. For smaller, single node jobs, this can be done by running HSDS and adjusting the resource file paths in your reV configs. However, since you went through all the trouble to setup your AWS account and spin up a parallel cluster, you're probably not running a small job. For large jobs, running an non-containerized HSDS server will likely encounter connection issues at some point and kill your reV runs. This problem can be largely fixed using HSDS Docker images. The current recommended approach for handling this is to write a script that will install HSDS, Docker, and kick off a containerized HSDS service on each compute node that a reV job uses. The following will walk you through setting up that process.

### 5a) Create Virtual Python Environment

The first step is to create a virtual Python environment that will contain both the reV model and HSDS Python APIs. There are many ways to do this, but this simplest is to use Python's built-in virtual environment module, `venv`. You can use the existing Python interpreter on your system or you can update it with your package manager, but make sure that the Python versions you're working with are compatible with reV. If you choose to use `venv`, you may need to install this module with your package manager. On our Ubuntu system, if you have Python 3.12, that command would be:

```bash
sudo apt install python3.12-venv
```

Then, create and activate this environment using a set of commands like this:
```bash
mkdir ~/envs
cd ~/envs
python3 -m venv rev
source rev/bin/activate
```

Then you could assign the activation command to an alias if you don't want to type it out each time with a command like this:
```bash
echo -e "\nalias arev='source ~/envs/rev/bin/activate'" >> ~/.bashrc
source ~/.bashrc
arev
```

### 5b) Configure Data Access
1. Create an HSDS Configuration file in your home directory called `~/.hscfg` with just the following content:
    ```
    # Local HSDS server
    hs_endpoint = http://localhost:5101
    hs_bucket = nrel-pds-hsds
    ```

2. Clone or move this tutorial repository into the shared directory we established in the AWS Parallel Cluster configuration YAML in [section 4](#4b-the-parallel-cluster-configuration-file) (`/scratch/` by default). We want it in the shared directory because this is where we're going to run reV and write the outputs here.

3. In this directory you'll find several "start_hsds" bash scripts. If you wish to run reV with the Slurm `exclusive` parameter, use `start_hsds.sh`. If you want to use node sharing, you will need to use `start_hsds_node_sharing.sh`, which locks the file so that only one process attempts to install docker and run HSDS while the others wait for the service to start. This is needed in this case because reV will run this script once for each process it kicks off; if node sharing is turned off each process is run on a dedicated node, but if it is left on many reV jobs will be kicked off and each will run the file on the same server.
    > Note: The contents of your `start_hsds.sh` script for installing and starting Docker depend on which OS you’re using since it uses the package manager to do it. Different OSes use different package managers. The sample file included in this repository uses the Advanced Package Tool (APT), which is common to all Debian-based operating systems such as Ubuntu. If you aren't using a Debian-based OS, you'll need to edit the file.

4. Set your AWS environment variables. This can be done at the start of the HSDS script itself or it can be done it your `~/.bashrc` run command file, which will set the variables when you spin up a shell. Here, we are going to add these variables to your `~/.bashrc`. The benefit of putting them here is that it allows you use the HSDS scripts to stop the service more easily and that requires the `AWS_S3_GATEWAY` environment variables to be set in your current shell. Add the following environment variables with your values to the `~/.bashrc` files. Here, use AWS access variables from an IAM user with admin privileges and not your AWS console root user. The `unset` parameter here is needed in case you are using a SSO authentication method and need to override AWS access variables with your IAM user variables.  **This step currently requires IAM access keys and does NOT support SSO or STS.**

    ```
    unset AWS_SESSION_TOKEN
    export AWS_ACCESS_KEY_ID=<your-aws-access-key-id>
    export AWS_SECRET_ACCESS_KEY=<your-aws-secret-access-key>
    export AWS_S3_GATEWAY="http://s3.us-west-2.amazonaws.com/"
    export AWS_S3_NO_SIGN_REQUEST=1
    export AWS_REGION="us-west-2"
    ```

    > Note: Be careful about defining your AWS and HSDS environment variables. These can be defined in many places and can result in unexpected behavior if they aren’t aligned. Some of those places include: the HSDS config: `~/.hscfg`, your `~/.bashrc` file or any other script it runs, the `start_hsds.sh` Bash script, or the parameter override configuration file (`~/hsds/admin/config/override.yml`).
    > Note: If you are using a Single Sign-On (SSO) authentication method, you will also need an IAM user assigned to you since HSDS fails without this authentication procedure. In this case, you'll need to unset the `AWS_SESSION_TOKEN` variable before declaring the `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` variables from the IAM user.

4. Test your HSDS local server configuration on your head node. The start HSDS script will run a quick access test on an example NRL resource file, but you may also run any of the subsequent command after it has finished to double check:

    - Run the start script: `./start_hsds.sh`
    - Run `docker ps` and verify that there are active HSDS services (hsds_rangeget_1, hsds_sn_1, hsds_head_1, and an hsds_dn_* node for every available core). 
    - Run `hsinfo` and verify that this doesn’t throw an error
    - Run the a Python access test with `h5pyd`: `test_hsds.py`.
    - When you're finished testing on the head node, you can run `./start_hsds.sh --stop` to shut the server down. 

Now you (and reV) should have access to all the resource files in this bucket. You can explore available datasets using the `hsls` command on the remote files and directories in the remote resource directory. For example, `hsls /nrel/` will list out all top-level resource directories and `hsls /nrel/wtk/conus/wtk_conus_2007.h5` will list out all the datasets and shapes in that file (include the trailing slash on directory names).

## 6) Setup reV

In this repository, you'll find an example reV wind power run for two years in Rhode Island. All of the reV configuration files you'll need for this example run are provided. You should be able to just run the model, but you may need to tweak some configurations if you installed files in a different locations from the defaults or if you need to update some execution parameters to better fit your AWS system. 

### 6a) Install reV and configuration files
Navigate to the shared file system directory and clone this repository there to get the sample reV configuration files and HSDS startup scripts. We want it in the shared directory because this is where we are going to be writing reV outputs. Then, in the same Python environment you installed HSDS into, install reV through PyPI, and run the CLI to check that it works. If you see reV's help file, the installation was successful and works on your system.

```bash
cd /scratch/
git clone https://github.com/NREL/reV-tutorial.git
cd reV-tutorial/tutorial_13_rev_in_cloud/
pip install NREL-reV
reV
```

In this folder you will see two "start_hsds" scripts. One assumes that you are disabling SLURM's node sharing and the other assumes you haven't. You can find the example reV run configurations in the "wind" directory. This has files for each reV module and a pipeline configuration file that coordinates these. This example represents a mostly complete reV pipeline to demonstrate where you are likely to require an HSDS server and where it isn't necessary. The project points for this run were built using HSDS and the `make_project_points.py` script. If you would like to try other project points, edit the Python script to reflect your study area, run the `start_hsds.sh` script to start the HSDS service, and run the Python script to build the points. Then you'll probably want to stop the HSDS service to save head node resources (`./start_hsds.sh --stop`).

### 6b) Configure reV to start HSDS
There are two steps in a full reV model pipeline where reV will make a call to the resource data and where we need to start the HSDS service:

1) `Generation`: will always require access to resource data.
2) `Supply Curve Aggregation`: will require access to resource data if a `techmap` has not been built and saved to the exclusion file yet.

The `sh_script` option in the execution control of a reV configuration file will run a shell script before running any reV processes. We will use this option run one of the "start_hsds" scripts mentioned above, which will install and start Docker and HSDS on each compute node. If SLURM node sharing is active, this file will need to contain a lock to prevent multiple processes on the same server from attempting to install and run HSDS at the same time (use `start_hsds_node_sharing.sh`). If node sharing is disabled, use `start_hsds.sh`, which is the default setting in the example configs. This script was written using Ubuntu 24.04 LTS and may require adjustments depending on your operating system.

```json
"sh_script": "/scratch/reV-tutorial/tutorial_13_rev_in_cloud/start_hsds.sh",
```

> NOTE: The techmap step in `aggregation` should happen on the fly if the HSDS server if running properly, but it might fail if there's a connection issue. In that case, check the techmap dataset in the exclusion file to make sure it was written correctly. Sometimes the techmap step will appear to succeed, but actually fail to write any values to the data array (i.e., you'll see all -1s). In this case, try deleting the techmap from the exclusion file and running again. If that fails, assuming you verified the configuration settings are correct and that HSDS is running properly, you can either try to build the manually or submit an issue to reV's [GitHub repository](https://github.com/NREL/reV/issues).


### 6c) reV Execution Settings:
When SLURM is not set to node sharing, there is more responsibility for the the user to ensure that each job is efficiently using its compute node. This can be done with a combination of settings in `execution_control`:

- `sites_per_worker`: The number of concurrent process the CPU will run at a time. A higher `sites_per_worker` value requires more memory but will reduce the number of slower I/O processes. If you are getting either low memory utilization or out-of-memory (OOM) errors you can adjust this variable up or down.
- `max_workers`: The maximum number of CPU cores per node to split reV work across. A higher number of workers will increase the memory overhead used to manage concurrency. If you are getting either low memory utilization or OOM errors you can also adjust this variable up or down.
- `memory_utilization_limit`: The percentage of available memory at which reV starts dumping data from memory onto disk. Because disk I/O is slower than memory transfers, it can improve runtimes to perform fewer I/O operations by holding more data in memory for longer. However, full memory utilization is not desired because of the possibility for brief memory spikes that can cause OOM errors (either from reV itself or background processes). So, this number can be adjusted up to some percentage of total available memory that leaves enough room for other processes. 
    > Note: this is the memory utilization at which reV will start dumping data to disk, meaning actual memory use will continue to rise for a period after it starts the write process, so this needs to be somewhat lower than your target threshold (in a full-scale version of the example reV-generation config, this value was set to 70% but actual memory use topped out at about 90%). The proper value will depend on many factors such as your hardware, operating system, other reV execution control settings, and other processes running on the server.
- `nodes`: The number of nodes you choose will also determine the number of individual processes (reV sites) that each individual node runs. The larger number of nodes, the smaller number of sites on each. On a shared HPC system, a higher number of nodes could result in longer queue times, especially on busy days. More nodes will also result in longer node and process start up times and more chunked files written to the filesystem. More nodes may result in faster model runs according to your wall clock, but they could increase overall computational resource costs given the overhead mentioned above.
- `pool_size`: This is the maximum number of processes to submit to the `concurrent.futures.ProcessPoolExecutor` on any one node at a time. Lowering this value will help to reduce parallel process memory overhead, but will result in somewhat longer runtimes since some CPU workers at the end of each process pool execution will remain idle until the last processes are finished and the next pool is submitted.

When SLURM is set to share nodes, additional resources left on any one node may be consumed with additional jobs. While this has the potential to improve efficiency and resource utilization, the reV team has not experimented enough with this setup to describe it much detail or to make execution control suggestions.

### 6d) HSDS Settings

HSDS has certain request limits that you may have to either account for or adjust to perform large-scale reV runs. These values are stored in `hsds/admin/config/config.yml` in the HSDS repository. There are 106 such settings, but here are few to start:

- `max_tcp_connections`: Max number of inflight Transmission Control Protocol (TCP) connections. 
- `max_pending_write_requests`: Maxium number of inflight write requests.
- `max_task_count`: Maximum number of concurrent tasks per node before the server will return a 503 (Service Unavailable) error.
- `max_tasks_per_node_per_request`:  Maximum number of inflight tasks to each node per request.

A common problem you might come across is a violation of the max HSDS task count settings. You are, by default, allowed 100 concurrent tasks per node. If you exceed this count, you will receive a 503 error. You can tell if this is the error by SSHing into the offending node (e.g., `ssh standard-dy-standard-6`), using the Docker logs command on the HSDS server node, and searching the output for 503 errors (`docker logs hsds_sn_1 | grep 503`). You'll have a few minutes after the reV run fails to ssh into the offending compute node and check the logs. You can solve this by reducing the number of concurrent processes in the reV configuration file (e.g., reduce `max_workers`) or by adjusting the HSDS parameter in a new `hsds/admin/config/override.yml` file. This override file will supercede individual entries in `config.yml` with user-supplied values. In our example problem, a `override.yml` file would contain only the line `max_task_count: <task count>` (e.g., `max_task_count: 150`). If you run enough sample reV runs, it will probably become clear whether this is a common problem that requires a more fundamental change to your execution control in reV or if it's rare enough that a higher HSDS task count will be suffice. The default for this parameter is 100.

### 7) Run reV

If everything was configured correctly, you should be able to run the example run! Here, we are running the reV pipeline so that it monitors progress on the compute nodes (and successful modules kick off subsequent modules automatically) as a background process. 

```bash
cd wind/
reV pipeline -c config_pipeline.json --monitor --background
```


## 8) Costs 

In this setup, there are four main sets of costs or fees for running reV on an AWS Parallel Cluster:

1) Constant hourly head node fees.
3) Intermittant hourly compute node fees.
4) Constant hourly and storage-based SLURM accounting fees.
5) Various other AWS programs that provide services such as DNS resolution, system monitoring, threat detection, etc.

So, estimating the cost of your reV run or runs will depend both on how long you incur constant costs while your cluster is deployed and how many intermittant costs you incur from the reV runs themselves. These prices will also vary depending on many factors such as your hardware, time, and location. To provide a rough estimate of how much a reV run might cost you, a set of national-scale runs was performed and the resulting costs are summarized below. 

### Test Run Rate Assumptions:
- **LustreFSx SSD (1.2GB):** $720.13 /month 
- **Head node (t3.large):**  $60.74 /month
- **Compute node (m6a.12xlarge):**  $2.07 /hour *
- **Compute node (c6a.12xlarge):** $1.84 /hour

\* Not tested, but included for reference

### National Scale reV Run Cost Calculations:
- **Solar:** (14.3 hours * $1.84/hour) + ($720.13 / 30 days) + ($60.74 / 30) = $52.341
- **Wind:** (119.5 hours * $1.84/hour) + ($720.13 / 30 days) + ($60.74 / 30) = $245.91

### Estimated Daily Costs
- Day 1 - $128 in total costs
- Day 2 - $202 in total costs
- Day 3 - $51 in total costs


|  Compute module  | Source Data         |  Timesteps (2 years) | Sites       | Total Datum  | Total Compute Time (hr) | Total EC2 Cost (daily) | Cost per datum |
| ---------------- | ------------------- | -------------------- | ----------- | ------------ | ----------------------- | ---------------------- | -------------- |
|   PVWattsV8      |  NSRDB (4km, 30min) |    35,040            |  546,939    |  1.92e+10    |  14.3                   |  $52.34                |  2.73e-09      |
|   Windpower      |  WTK (2km, 1hr)     |    17,520            |  1,853,700  |  3.25e+10    |  119.5                  |  $245.91               |  7.57e-09      |



> Note: These prices are based on a specific set of runs, at a particular time and location. Other price factors such as discounts, time of day, on-demand vs spot prices will affect your costs. Realized prices could be very different from these estimates, use them as a very rough estimate of scale.

For more details on costs see [https://aws.amazon.com/pcs/pricing/](https://aws.amazon.com/pcs/pricing/).

## 9) AWS Parallel Cluster Updating and Deleting

If you wish to adjust your cluster's system configuration after setting everything up, you can do so from your local computer's terminal with the AWS CLI. Pause, update, and restart your cluster with the following commands:

```bash
pcluster list-clusters # For a reminder of the cluster name 
pcluster update-compute-fleet -n cluster_name --status STOP_REQUESTED. # This will take a while
pcluster update-cluster --cluster-name cluster_name --cluster-configuration /path/to/pcluster-config.yaml
pcluster update-compute-fleet -n cluster_name --status START_REQUESTED. # So will this
```

Don’t like your OS? You can't change that with a simple update. Destroy it and start over:

```bash
pcluster delete-cluster --cluster-name cluster_name
# Edit the YAML file...
pcluster create-cluster -c pcluster-config.yaml --cluster-name cluster_name
```

Of course, if you are fully done with the cluster and wish to shut it down permanently, you may run just the `delete-cluster` command and stop there.

<br/><br/>

## Appendix: Deprecated and Untested Methods
### I. Setting up an HSDS Kubernetes Service

Setting up your own HSDS Kubernetes service is one way to run a large reV job with full parallelization. This has not been trialed by the NREL team in full, but we have tested on the HSDS group's Kubernetes cluster. If you want to pursue this route, you can follow the HSDS repository instructions for [HSDS Kubernetes on AWS](https://github.com/HDFGroup/hsds/blob/master/docs/kubernetes_install_aws.md).


### II. Setting up an HSDS Lambda Service

We've tested AWS Lambda functions as the HSDS service for reV workflows and we've found that Lambda functions require too much overhead to work well with the reV workflow. These instructions are included here for posterity, but HSDS-Lambda is _not_ recommended for the reV workflow.

These instructions are generally copied from the [HSDS Lambda README](https://github.com/HDFGroup/hsds/blob/master/docs/aws_lambda_setup.md) with a few modifications.

It seems you cannot currently use the public ECR container image from the HSDS ECR repository so the first few bullets are instructions on how to set up your own HSDS image and push to a private ECR repository.

H5pyd cannot currently call a lambda function directly, so the instructions at the end show you how to set up an API gateway that interfaces between h5pyd and the lambda function.

Follow these instructions from your Cloud9 environment. None of this is directly related to the pcluster environment, except for the requirement to add the ``.hscfg`` file in the pcluster home directory.

1. Clone the [HSDS repository](https://github.com/HDFGroup/hsds) onto your filesystem.

2. You may need to [resize your EBS volume](https://docs.aws.amazon.com/cloud9/latest/user-guide/move-environment.html#move-environment-resize).

3. In the AWS Management Console, create a new ECR repository called "hslambda". Keep the default private repository settings.

4. Create an HSDS image and push to your ``hslambda`` ECR repository. This sublist is a combination of commands from the ECR push commands and the HSDS build instructions (make sure you use the actual push commands from your ECR repository with the actual region, repository name, and AWS account ID):

    ```bash
    cd hsds

    aws ecr get-login-password --region region | docker login --username AWS --password-stdin aws_account_id.dkr.ecr.region.amazonaws.com

    sh lambda_build.sh

    docker tag hslambda:latest aws_account_id.dkr.ecr.region.amazonaws.com/my-repository:tag

    docker push aws_account_id.dkr.ecr.region.amazonaws.com/my-repository:tag
    ```

5. You should now see your new image appear in your ``hslambda`` ECR repository in the AWS Console. Get the URI from this image.

6. In the AWS Management Console, go to the Lambda service interface in your desired region (us-west-2, Oregon).

7. Click "Create Function" -> Choose "Container Image" option, function name is ``hslambda``, use the Container Image URI from the image you just uploaded to your ECR repository, select "Create Function" and wait for the image to load.

8. You should see a banner saying you've successfully created the `hslambda` function.

9. Set the following in the configuration tab:

- Use at least 1024MB of memory (feel free to tune this later for your workload)
- Timeout of at least 30 seconds (feel free to tune this later for your workload)
- Use an execution role that includes S3 read only access
- Add an environment variable `AWS_S3_GATEWAY`: `http://s3.us-west-2.amazonaws.com`

10. Select the "Test" tab and click on the "Test" button. You should see a successful run with a `status_code` of 200 and an output like this:

    ```
        {
          "isBase64Encoded": false,
          "statusCode": 200,
          "headers": {
            "Content-Type": "application/json; charset=utf-8",
            "Content-Length": "323",
            "Date": "Tue, 23 Nov 2021 22:27:08 GMT",
            "Server": "Python/3.8 aiohttp/3.8.1"
          },
          "body": {
            "start_time": 1637706428, 
            "state": "READY",
            "hsds_version": "0.7.0beta",
            "name": "HSDS on AWS Lambda",
            "greeting": "Welcome to HSDS!",
            "about": "HSDS is a webservice for HDF data", 
            "node_count": 1,
            "dn_urls": [
                "http+unix://%2Ftmp%2Fhs1a1c917f%2Fdn_1.sock"
            ],
            "dn_ids": [
                "dn-001"
            ], 
            "username": "anonymous",
            "isadmin": false
           }
        }
    ```

11. Now we need to create an API Gateway so that reV and h5pyd can interface with the lambda function. Go to the API Gateway page in the AWS console and do these things:

- Create API -> choose HTTP API (build)
- Add integration -> Lambda -> use ``us-west-2``, select your lambda function, use some generic name like ``hslambda-api``
- Configure routes -> Method is ``ANY``, the Resource path is ``$default``, the integration target is your lambda function
- Configure stages -> Stage name is ``$default`` and auto-deploy must be enabled
- Create and get the APIs Invoke URL, something like ``https://XXXXXXX.execute-api.us-west-2.amazonaws.com``
- Make an `.hscfg` file in the home dir (e.g., `/home/ec2-user/`). Make sure you also have this config in your pcluster filesystem. The config file should have these entries:

    ```bash
        # HDFCloud configuration file
        hs_endpoint = https://XXXXXXX.execute-api.us-west-2.amazonaws.com
        hs_username = hslambda
        hs_password = lambda
        hs_api_key = None
        hs_bucket = nrel-pds-hsds
    ```

12. All done! You should now be able to run the `aws_pcluster` test sourcing data from `/nrel/nsrdb/v3/nsrdb_{}.h5` or the simple h5pyd test below.

13. Here are some summary notes for posterity:

- We now have a lambda function `hslambda` that will retrieve data from the NSRDB or WTK using the HSDS service.
- We have an API Gateway that we can use as an endpoint for API requests
- We have configured h5pyd with the `.hscfg` file to hit that API endpoint with the proper username, password, and bucket target
- reV will now retrieve data from the NSRDB or WTK in parallel requests to the `hslambda` function via h5pyd.
