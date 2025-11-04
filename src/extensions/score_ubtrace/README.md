# ubTrace Sphinx Extension

Sphinx extension that registers and configures the ubtrace builder.

To build the ubTrace output for the [docs](../../../docs) in this Bazel project, run the Sphinx build with
```
bazel run //:docs_ubtrace
```
from the repo root.

Then start the ubTrace server with:

```
docker compose -f src/extensions/score_ubtrace/docker-compose.yml up
```
from the repo root.
