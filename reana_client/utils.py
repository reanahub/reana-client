# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2017, 2018 CERN.
#
# REANA is free software; you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software
# Foundation; either version 2 of the License, or (at your option) any later
# version.
#
# REANA is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
# A PARTICULAR PURPOSE. See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with
# REANA; if not, write to the Free Software Foundation, Inc., 59 Temple Place,
# Suite 330, Boston, MA 02111-1307, USA.
#
# In applying this license, CERN does not waive the privileges and immunities
# granted to it by virtue of its status as an Intergovernmental Organization or
# submit itself to any jurisdiction.
"""REANA client utils."""

import json
import logging

import yadageschemas
import yaml
from cwltool.main import main
from jsonschema import ValidationError, validate
from six import StringIO

from reana_client.config import reana_yaml_schema_file_path


def yadage_load(workflow_file, toplevel='.'):
    """Validate and return yadage workflow specification.

    :param workflow_file: A specification file compliant with
        `yadage` workflow specification.
    :returns: A dictionary which represents the valid `yadage` workflow.
    """
    return yadageschemas.load(workflow_file, toplevel=toplevel,
                              schema_name='yadage/workflow-schema',
                              schemadir=None, validate=True)


def cwl_load(workflow_file):
    """Validate and return cwl workflow specification.

    :param workflow_file: A specification file compliant with
        `cwl` workflow specification.
    :returns: A dictionary which represents the valid `cwl` workflow.
    """
    mystdout = StringIO()
    main(["--debug", "--pack", workflow_file], stdout=mystdout)
    value = mystdout.getvalue()
    return json.loads(value)


workflow_load = {
    'yadage': yadage_load,
    'cwl': cwl_load
}
"""Dictionary to extend with new workflow specification loaders."""


def load_workflow_spec(workflow_type, workflow_file, **kwargs):
    """Validate and return machine readable workflow specifications.

    :param workflow_type: A supported workflow specification type.
    :param workflow_file: A workflow file compliant with `workflow_type`
        specification.
    :returns: A dictionary which represents the valid workflow specification.
    """
    return workflow_load[workflow_type](workflow_file, **kwargs)


def load_reana_spec(filepath, skip_validation=False):
    """Load and validate reana specification file.

    :raises IOError: Error while reading REANA spec file from given filepath`.
    :raises ValidationError: Given REANA spec file does not validate against
        REANA specification.
    """
    try:
        with open(filepath) as f:
            reana_yaml = yaml.load(f.read())

        if not (skip_validation):
            logging.info('Validating REANA specification file: {filepath}'
                         .format(filepath=filepath))
            _validate_reana_yaml(reana_yaml)

        return reana_yaml
    except IOError as e:
        logging.info(
            'Something went wrong when reading specifications file from '
            '{filepath} : \n'
            '{error}'.format(filepath=filepath, error=e.strerror))
        raise e
    except Exception as e:
        raise e


def _validate_reana_yaml(reana_yaml):
    """Validate REANA specification file according to jsonschema.

    :param reana_yaml: Dictionary which represents REANA specifications file.
    :raises ValidationError: Given REANA spec file does not validate against
        REANA specification schema.
    """
    try:
        with open(reana_yaml_schema_file_path, 'r') as f:
            reana_yaml_schema = json.loads(f.read())

            validate(reana_yaml, reana_yaml_schema)

    except IOError as e:
        logging.info(
            'Something went wrong when reading REANA validation schema from '
            '{filepath} : \n'
            '{error}'.format(filepath=reana_yaml_schema_file_path,
                             error=e.strerror))
        raise e
    except ValidationError as e:
        logging.info('Invalid REANA specification: {error}'
                     .format(error=e.message))
        raise e
