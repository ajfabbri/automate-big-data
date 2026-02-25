# Automate Big Data (ABD)

Automates building and running open-source big data frameworks in containers.
Currently focused on the Apache Hadoop Common ecosystem.

See the repository's main [README.md](README.md) for more information.

## Running abd Commands

To view available commands, use the `--help` or `-h` option:

```bash
abd --help
```

Tip: Add `-v` or `-vv` for verbose output, e.g:

```bash
abd -v <command>
```

### Create New Configuration

To run the interactive configuration tool:

```bash
abd config -i
```

To create a default config, you can omit the `-i` argument above.

### Building Software and Container Images

This command rebuilds all container images and software builds / downloads:

```bash
abd build
```

To avoid rebuilding images or releases that already exist, use the `--cached` option:

```
abd build --cached          # don't rebuild software releases, container images
abd build --cached=image    # don't rebuild container images
abd build --cached=release  # don't rebuild software releases
```


### Deploying Hosts (Containers or VMs)

```bash
abd deploy
```

By default, this will:
- Create images for hadoop-build and hadoop-node containers.
- Start the hadoop-build container and create a release from source.
- Start hadoop-node containers and deploy the release to them.

Once the hosts/containers are running, you can use `abd` to manage them:

```bash
abd host list
abd host stop <name>
abd host attach <name>
```
