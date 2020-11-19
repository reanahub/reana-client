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


check_script () {
    shellcheck run-tests.sh
}

check_black () {
    black --check .
}

check_flake8 () {
    flake8 .
}

check_pydocstyle () {
    pydocstyle reana_client
}

check_manifest () {
    check-manifest
}

check_cli_cmds () {
    reana-client --help > cmd_list.txt
    diff -q -w docs/cmd_list.txt cmd_list.txt
    rm cmd_list.txt
}

check_cli_api () {
    #cli_docs_url=https://raw.githubusercontent.com/reanahub/docs.reana.io/master/docs/reference/reana-client-cli-api/index.md
    #docs_differ_error_msg='Current reana-client differs with the documentation. Please update http://docs.reana.io/reference/reana-client-cli-api/.'
    python scripts/generate_cli_api.py > cli_api.md
    #(diff -q -w  cli_api.md <(curl -s $cli_docs_url) || (echo "$docs_differ_error_msg" && exit 1))
    rm cli_api.md
}

check_sphinx () {
    sphinx-build -qnNW docs docs/_build/html
    sphinx-build -qnNW -b doctest docs docs/_build/doctest
}

check_pytest () {
    python setup.py test
}

check_all() {
    check_script
    check_black
    check_flake8
    check_pydocstyle
    check_manifest
    check_cli_cmds
    check_cli_api
    check_sphinx
    check_pytest
}

if [ $# -eq 0 ]; then
    check_all
    exit 0
fi

for arg in "$@"
do
    case $arg in
        --check-shellscript) check_script;;
        --check-black) check_black;;
        --check-flake8) check_flake8;;
        --check-pydocstyle) check_pydocstyle;;
        --check-manifest) check_manifest;;
        --check-cli-cmds) check_cli_cmds;;
        --check-cli-api) check_cli_api;;
        --check-sphinx) check_sphinx;;
        --check-pytest) check_pytest;;
        *)
    esac
done
