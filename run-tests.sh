#!/bin/sh
#
# This file is part of REANA.
# Copyright (C) 2017, 2018 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

pydocstyle reana_client && \
isort -rc -c -df **/*.py && \
reana-client --help > cmd_list.txt && \
diff -q -w docs/cmd_list.txt cmd_list.txt  && \
rm cmd_list.txt && \
check-manifest --ignore ".travis-*" && \
sphinx-build -qnNW docs docs/_build/html && \
python setup.py test && \
sphinx-build -qnNW -b doctest docs docs/_build/doctest
