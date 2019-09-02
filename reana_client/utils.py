# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2017, 2018 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
"""REANA client utils."""
import base64
import json
import logging
import os
import subprocess
import sys
import traceback
from uuid import UUID

import click
import yadageschemas
import yaml
from cwltool.main import main as cwltool_main
from jsonschema import ValidationError, validate
from reana_commons.serial import serial_load
from reana_commons.utils import get_workflow_status_change_verb
from six import StringIO

from reana_client.config import reana_yaml_schema_file_path


def workflow_uuid_or_name(ctx, param, value):
    """Get UUID of workflow from configuration / cache file based on name."""
    if not value:
        click.echo(click.style(
            'Workflow name must be provided either with '
            '`--workflow` option or with REANA_WORKON '
            'environment variable', fg='red'),
            err=True)
    else:
        return value


def yadage_load(workflow_file, toplevel='.'):
    """Validate and return yadage workflow specification.

    :param workflow_file: A specification file compliant with
        `yadage` workflow specification.
    :type workflow_file: string
    :param toplevel: URL/path for the workflow file
    :type toplevel: string

    :returns: A dictionary which represents the valid `yadage` workflow.
    """
    schema_name = 'yadage/workflow-schema'
    schemadir = None

    specopts = {
        'toplevel': toplevel,
        'schema_name': schema_name,
        'schemadir': schemadir,
        'load_as_ref': False,
    }

    validopts = {
        'schema_name': schema_name,
        'schemadir': schemadir,
    }

    return yadageschemas.load(spec=workflow_file, specopts=specopts,
                              validopts=validopts, validate=True)


def cwl_load(workflow_file):
    """Validate and return cwl workflow specification.

    :param workflow_file: A specification file compliant with
        `cwl` workflow specification.
    :returns: A dictionary which represents the valid `cwl` workflow.
    """
    mystdout = StringIO()
    mystderr = StringIO()
    cwltool_main(argsl=["--pack", "--quiet", workflow_file],
                 stdout=mystdout, stderr=mystderr)
    value = mystdout.getvalue()
    return json.loads(value)


workflow_load = {
    'yadage': yadage_load,
    'cwl': cwl_load,
    'serial': serial_load,
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
            reana_yaml = yaml.load(f.read(), Loader=yaml.FullLoader)

        if not skip_validation:
            logging.info('Validating REANA specification file: {filepath}'
                         .format(filepath=filepath))
            _validate_reana_yaml(reana_yaml)

        kwargs = {}
        if reana_yaml['workflow']['type'] == 'serial':
            kwargs['specification'] = reana_yaml['workflow'].\
                get('specification')
            kwargs['parameters'] = \
                reana_yaml.get('inputs', {}).get('parameters', {})
            kwargs['original'] = True

        reana_yaml['workflow']['specification'] = load_workflow_spec(
            reana_yaml['workflow']['type'],
            reana_yaml['workflow'].get('file'),
            **kwargs
        )

        if reana_yaml['workflow']['type'] == 'cwl' and \
                'inputs' in reana_yaml:
            with open(reana_yaml['inputs']['parameters']['input']) as f:
                reana_yaml['inputs']['parameters'] = \
                    yaml.load(f, Loader=yaml.FullLoader)

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


def is_uuid_v4(uuid_or_name):
    """Check if given string is a valid UUIDv4."""
    # Based on https://gist.github.com/ShawnMilo/7777304
    try:
        uuid = UUID(uuid_or_name, version=4)
    except Exception:
        return False

    return uuid.hex == uuid_or_name.replace('-', '')


def get_workflow_name_and_run_number(workflow_name):
    """Return name and run_number of a workflow.

    :param workflow_name: String representing Workflow name.

        Name might be in format 'reana.workflow.123' with arbitrary
        number of dot-delimited substrings, where last substring specifies
        the run number of the workflow this workflow name refers to.

        If name does not contain a valid run number, name without run number
        is returned.
    """
    # Try to split a dot-separated string.
    try:
        name, run_number = workflow_name.rsplit('.', 1)

        if not run_number.isdigit():
            # `workflow_name` was split, so it is a dot-separated string
            # but it didn't contain a valid `run_number`.
            # Assume that this dot-separated string is the name of
            # the workflow and return just this without a `run_number`.
            return workflow_name, ''

        return name, run_number

    except ValueError:
        # Couldn't split. Probably not a dot-separated string.
        # Return the name given as parameter without a `run_number`.
        return workflow_name, ''


def get_workflow_root():
    """Return the current workflow root directory."""
    reana_yaml = 'reana.yaml'
    workflow_root = os.getcwd()

    while True:
        file_list = os.listdir(workflow_root)
        parent_dir = os.path.dirname(workflow_root)
        if reana_yaml in file_list:
            break
        else:
            if workflow_root == parent_dir:
                click.echo(click.style(
                    'Not an workflow directory (or any of the parent'
                    ' directories).\nPlease upload from inside'
                    ' the directory containing the reana.yaml '
                    'file of your workflow.', fg='red'))
                sys.exit(1)
            else:
                workflow_root = parent_dir
    workflow_root += '/'
    return workflow_root


def validate_cwl_operational_options(operational_options):
    """Validate cwl operational options."""
    forbidden_args = ['--debug', '--tmpdir-prefix', '--tmp-outdir-prefix'
                      '--default-container', '--outdir']
    for option in operational_options:
        if option in forbidden_args:
            click.echo('Operational option {0} are not allowed. \n'
                       .format(operational_options), err=True)
            sys.exit(1)
    cmd = 'cwltool --version {0}'.format(' '.join(operational_options))
    try:
        subprocess.check_call(cmd, shell=True)
    except subprocess.CalledProcessError as err:
        click.echo('Operational options {0} are not valid. \n'
                   '{1}'.format(operational_options, err), err=True)
        sys.exit(1)


def validate_serial_operational_options(operational_options):
    """Return validated serial operational options."""
    try:
        return dict(p.split('=') for p in operational_options)
    except Exception as err:
        click.echo('Operational options {0} are not valid. \n'
                   '{1}'.format(operational_options, err), err=True)
        sys.exit(1)


def validate_input_parameters(live_parameters, original_parameters):
    """Return validated input parameters."""
    parsed_input_parameters = dict(live_parameters)
    for parameter in parsed_input_parameters.keys():
        if parameter not in original_parameters:
            click.echo(
                click.style('Given parameter - {0}, is not in '
                            'reana.yaml'.format(parameter),
                            fg='red'),
                err=True)
            del live_parameters[parameter]
    return live_parameters


def get_workflow_status_change_msg(workflow, status):
    """Choose verb conjugation depending on status.

    :param workflow: Workflow name whose status changed.
    :param status: String which represents the status the workflow changed to.
    """
    return '{workflow} {verb} {status}'.format(
        workflow=workflow, verb=get_workflow_status_change_verb(status),
        status=status)


def parse_secret_from_literal(literal):
    """Parse a literal string, into a secret dict.

    :param literal: String containg a key and a value. (e.g. 'KEY=VALUE')
    :returns secret: Dictionary in the format suitable for sending
    via http request.
    """
    try:
        key, value = literal.split('=', 1)
        secret = {
            key: {
                'value': base64.b64encode(
                    value.encode('utf-8')
                ).decode('utf-8'),
                'type': 'env'
            }
        }
        return secret

    except ValueError as e:
        logging.debug(traceback.format_exc())
        logging.debug(str(e))
        click.echo(
            click.style(
                'Option "{0}" is invalid: \n'
                'For literal strings use "SECRET_NAME=VALUE" format'
                .format(literal),
                fg='red'),
            err=True)


def parse_secret_from_path(path):
    """Parse a file path into a secret dict.

    :param path: Path of the file containing secret
    :returns secret: Dictionary in the format suitable for sending
     via http request.
    """
    try:
        with open(os.path.expanduser(path), 'rb') as file:
            file_name = os.path.basename(path)
            secret = {
                file_name: {
                    'value': base64.b64encode(
                        file.read()).decode('utf-8'),
                    'type': 'file'
                }
            }
        return secret
    except FileNotFoundError as e:
        logging.debug(traceback.format_exc())
        logging.debug(str(e))
        click.echo(
            click.style(
                'File {0} could not be uploaded: {0} does not exist.'
                .format(path),
                fg='red'),
            err=True)
