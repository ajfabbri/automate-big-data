# Automate Big Data (ABD)

Automates building and running open-source big data frameworks in containers.
Currently focused on Apache Hadoop Common.

See the repository's main [README.md](README.md) for more information.

## Running abd Commands

To view available commands, use the `--help` or `-h` option:

```bash
abd --help
```

### Create New Configuration

To run the interactive configuration tool:

```bash
abd config -i
```

To create a default config, you can omit the `-i` argument above.

### Building Container Images

```bash
abd container build
```

Tip: Add `-v` or `-vv` for verbose output:

```bash
abd -v container build
```

### Running Containers

```bash
abd container run
```
By default, this will:
- Create images for hadoop-build and hadoop-node containers.
- Start the hadoop-build container and create a release from source.
- Start hadoop-node containers and deploy the release to them.

Once the containers are running, you can use `abd` to manage them:

```bash
abd container list
abd container stop
abd container attach
```
