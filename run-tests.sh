#!/bin/bash
#
# This file is part of REANA.
# Copyright (C) 2017, 2018, 2019, 2020 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

# Quit on errors
set -o errexit

# Quit on unbound symbols
set -o nounset


cli_docs_url=https://raw.githubusercontent.com/reanahub/docs.reana.io/master/docs/reference/reana-client-cli-api/index.md
docs_differ_error_msg='Current reana-client differs with the documentation. Please update http://docs.reana.io/reference/reana-client-cli-api/.'
python_version=$(python -c 'import sys;  print(sys.version_info.major)')

pydocstyle reana_client
reana-client --help > cmd_list.txt
diff -q -w docs/cmd_list.txt cmd_list.txt
rm cmd_list.txt
if [ "$python_version" -eq 3 ]
then
    black --check .
    python scripts/generate_cli_api.py > cli_api.md
    #(diff -q -w  cli_api.md <(curl -s $cli_docs_url) || (echo $docs_differ_error_msg && exit 1))
    rm cli_api.md
fi
check-manifest --ignore ".travis-*"
sphinx-build -qnNW docs docs/_build/html
python setup.py test
sphinx-build -qnNW -b doctest docs docs/_build/doctest
