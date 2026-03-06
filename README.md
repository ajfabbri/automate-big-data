# automate-big-data

_A faster dev loop for open-source distributed data platforms._

Testing and automation for open-source big data frameworks.

Goal: To enable fast testing of open-source storage and analytics stacks.
Bonus points for being able to test cloud storage integrations locally with
emulated services.

Note: this is an **early development prototype.**

## Current Functionality

- Create a build container with all the dependencies needed to build releases
  of Apache Hadoop Common.

- Automate building Hadoop Common from source and deploying to test nodes (containers).

- Running tests which exercise Hadoop Common features and integrations.

### Roadmap

- Apache Spark deploy and test.
- Consider Hive, HBase, Impala, Iceberg, etc. (they depend on Hadoop Common
  library).

## Getting Started

The `abd` command-line tool provides commands for building and deploying
containers and software builds.

### Installing ABD Commandline Tool

From the root of the repository:

```bash
python -m venv venv                             # create a local virtual env.
source venv/bin/activate                        # activate the virtual env.
python -m pip intstall -r requirements.txt      # install dependencies
pip install -e .                                # install (editable mode) so you can run `abd`
```

To view available commands, use the `--help` or `-h` option:

```bash
abd --help
```

### Running ABD Commands

See the [dist-readme.md](dist-readme.md) doc for more detail.

## How It Works

The automation scripting works in phases. The work is split into tasks. Each
task has an ID `<phase>:<task-name>`. Tasks can depend on each other, and the
tool runs them in parallel according to those dependencies.

E.g. `build:cluster-node` is a task in the `build` phase that creates container
images for the main worker nodes that will be tested. Running that task or
phase will first run any that it depends on, and so on.

### 1. Configure

The configure phase is where you choose which software you want to run, where
you want to run it, etc.. This phase also generates inputs for the following
phases (e.g. Docker files, ansible? , etc.).

### 2. Build

The build phase downloads and/or builds any of the selected software to prepare
for deployment and execution.

### 3. Deploy

The deploy phase spawns and configures containers and/or VMs as needed.

### 4. Execute

Execute phase is where tasks are run, which are typically tests used to
validate releases or patches.

## Supported Software

### Hadoop Common

[Apache Hadoop Common](https://hadoop.apache.org/) is a common dependency for
many big data / analytics projects. (E.g. Hive, Spark, MapReduce, Impala, HBase,
Iceberg, etc.). It provides a common interface, `FileSystem`, which provides
access to distributed filesystems such as Amazon S3, Azure (blob storage /
datalake), Google Cloud Storage (GCS), HDFS, and Ozone.

#### S3A

S3A is the official S3 storage client implementation for Hadoop Common.

We use localstack to quickly test S3A builds with AWS SDKs and a local
(emulated) S3 service.
