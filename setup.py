# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""REANA client"""

from __future__ import absolute_import, print_function

import os
import re

from setuptools import find_packages, setup

readme = open("README.md").read()
history = open("CHANGELOG.md").read()

tests_require = [
    "pytest-reana>=0.9.2,<0.10.0",
]

extras_require = {
    "docs": [
        "myst-parser",
        "Sphinx>=1.5.1",
        "sphinx-rtd-theme>=0.1.9",
        "sphinx-click>=1.0.4",
    ],
    "tests": tests_require,
}

extras_require["all"] = []
for key, reqs in extras_require.items():
    if ":" == key[0]:
        continue
    extras_require["all"].extend(reqs)

setup_requires = [
    "pytest-runner>=2.7",
]

install_requires = [
    "click>=7",
    "pathspec==0.9.0",
    "jsonpointer>=2.0",
    "reana-commons[yadage,snakemake,cwl]>=0.9.8,<0.10.0",
    "tablib>=0.12.1,<0.13",
    "werkzeug>=0.14.1 ; python_version<'3.10'",
    "werkzeug>=0.15.0 ; python_version>='3.10'",
    "swagger_spec_validator>=2.4.0,<3.0.0; python_version<'3.7'",
]

packages = find_packages()


# Get the version string. Cannot be done with import!
with open(os.path.join("reana_client", "version.py"), "rt") as f:
    version = re.search(r'__version__\s*=\s*"(?P<version>.*)"\n', f.read()).group(
        "version"
    )

setup(
    name="reana-client",
    version=version,
    description=__doc__,
    long_description=readme + "\n\n" + history,
    long_description_content_type="text/markdown",
    author="REANA",
    author_email="info@reana.io",
    url="https://github.com/reanahub/reana-client",
    packages=[
        "reana_client",
    ],
    zip_safe=False,
    include_package_data=True,
    entry_points={
        "console_scripts": [
            "reana-client = reana_client.cli:cli",
            "reana-cwl-runner = reana_client.cli.cwl_runner:cwl_runner",
        ],
    },
    python_requires=">=3.6",
    extras_require=extras_require,
    install_requires=install_requires,
    setup_requires=setup_requires,
    tests_require=tests_require,
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Environment :: Console",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Programming Language :: Python :: Implementation :: CPython",
        "Programming Language :: Python",
        "Topic :: Internet :: WWW/HTTP :: Dynamic Content",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
)
