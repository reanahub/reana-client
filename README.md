# REANA-Client

[![image](https://img.shields.io/pypi/pyversions/reana-client.svg)](https://pypi.org/pypi/reana-client)
[![image](https://github.com/reanahub/reana-client/workflows/CI/badge.svg)](https://github.com/reanahub/reana-client/actions)
[![image](https://readthedocs.org/projects/reana-client/badge/?version=latest)](https://reana-client.readthedocs.io/en/latest/?badge=latest)
[![image](https://codecov.io/gh/reanahub/reana-client/branch/master/graph/badge.svg)](https://codecov.io/gh/reanahub/reana-client)
[![image](https://img.shields.io/badge/discourse-forum-blue.svg)](https://forum.reana.io)
[![image](https://img.shields.io/github/license/reanahub/reana.svg)](https://github.com/reanahub/reana-client/blob/master/LICENSE)
[![image](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

## About

REANA-Client is a component of the [REANA](https://www.reana.io/) reusable and
reproducible research data analysis platform. It provides a command-line tool
that allows researchers to submit, run, and manage their computational
workflows.

- seed workspace with input code and data
- run computational workflows on remote compute clouds
- list submitted workflows and enquire about their statuses
- download results of finished workflows

## Installation

```console
$ # create new virtual environment
$ virtualenv ~/.virtualenvs/reana
$ source ~/.virtualenvs/reana/bin/activate
$ # install reana-client
$ pip install reana-client
```

## Usage

The detailed information on how to install and use REANA can be found in
[docs.reana.io](https://docs.reana.io).

### Bundling additional workflow source files

The `create` and `validate` commands upload a scoped specification bundle for
server-side workflow loading. Declare every imported source explicitly under
`workflow.files` or `workflow.directories` so it is available to the loader.

For example, given this Snakemake project:

```text
analysis/
├── reana.yaml
├── Snakefile
└── rules/
    └── common.smk
```

where `Snakefile` contains `include: "rules/common.smk"`, declare the included
source in `reana.yaml`:

```yaml
version: 0.9.0
workflow:
  type: snakemake
  file: Snakefile
  directories:
    - rules
```

Paths are relative to the directory containing the selected specification.
Absolute paths, paths that escape through `..`, and symbolic links are rejected.
Use `workflow.files` only for workflow definitions and configuration needed
while loading the workflow; input datasets belong under `inputs.files` or
`inputs.directories`.

Validation snapshots accept at most 1,000 files, 2,000 directories, 100 MiB of
file content, and 64 relative path components. Symbolic links are not followed.

`reana-client validate --environments` performs offline image-reference checks
and reports effective runtime identities. Add `--pull` to verify availability
and inspect those images with your local container runtime and registry
credentials; the REANA server does not contact image registries.

## Useful links

- [REANA project home page](http://www.reana.io/)
- [REANA user documentation](https://docs.reana.io)
- [REANA user support forum](https://forum.reana.io)
- [REANA-Client releases](https://reana-client.readthedocs.io/en/latest#changes)
- [REANA-Client developer documentation](https://reana-client.readthedocs.io/)
- [REANA-Client known issues](https://github.com/reanahub/reana-client/issues)
- [REANA-Client source code](https://github.com/reanahub/reana-client)
