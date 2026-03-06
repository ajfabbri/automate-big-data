# TODOs
[ ] project organization

[ ] cached mode
    [ ] hadoop-build

[ ] dry run awareness:
    [ ] install hadoop

[ ] clean command(s)

[ ] tests
    [ ] `test_abd_commands.sh` v1
## Implementation

_Work in progress._

This tool focuses on speed and ease of use for developer productivity.

TODO ? The `abd` tool caches state between in invocations, to simplify skipping work
that is already done for its common-case `--cached` mode.

### How to express phases

I.e. execute --depends-on--> deploy --> build --> configure

and sometimes a build needs to deploy a container to build on, e.g.

deploy(node) --> install(hadoop) --> build(hadoop) --> hadoop

Maybe:
- modules register with `job` which is a registry of phases

Thinking about dependency graph:
```
phase_types <- deploy_phase, build_phase, etc.
  ^     +------+
 job <--+           register, providing callback?
 ```

 job.start(phase, options..)
