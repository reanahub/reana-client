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
"""CWL v1.0 interface CLI implementation."""

import io
import logging
import os
import re
import sys
import traceback
import urllib
from time import sleep

import click
import yaml
from bravado.exception import HTTPServerError
from cwltool.context import LoadingContext
from cwltool.load_tool import fetch_document
from cwltool.main import printdeps
from cwltool.workflow import findfiles

from reana_client.api import Client
from reana_client.cli.utils import add_access_token_options
from reana_client.config import default_user
from reana_client.decorators import with_api_client
from reana_client.utils import load_workflow_spec
from reana_client.version import __version__


PY3 = sys.version_info > (3,)


def get_file_dependencies_obj(cwl_obj, basedir):
    """Return a dictionary which contains the CWL workflow file dependencies.

    :param cwl_obj: A CWL tool or job which might contain file dependencies.
    :param basedir: Workflow base dir.
    :returns: A dictionary composed of valid CWL file dependencies.
    """
    # Load de document
    loading_context = LoadingContext()
    document_loader, workflow_obj, uri = fetch_document(
        cwl_obj, resolver=loading_context.resolver,
        fetcher_constructor=loading_context.fetcher_constructor)
    in_memory_buffer = io.StringIO() if PY3 else io.BytesIO()
    # Get dependencies
    printdeps(workflow_obj, document_loader, in_memory_buffer, 'primary', uri,
              basedir=basedir)
    file_dependencies_obj = yaml.load(in_memory_buffer.getvalue())
    in_memory_buffer.close()
    return file_dependencies_obj


@click.command()
@click.version_option(version=__version__)
@click.option('--quiet', is_flag=True,
              help='No diagnostic output')
@click.option('--outdir', type=click.Path(),
              help='Output directory, defaults to the current directory')
@click.option('--basedir', type=click.Path(),
              help='Base directory.')
@add_access_token_options
@click.argument('processfile', required=False)
@click.argument('jobfile')
@click.pass_context
@with_api_client
def cwl_runner(ctx, quiet, outdir, basedir, processfile, jobfile,
               access_token):
    """Run CWL files in a standard format <workflow.cwl> <job.json>."""
    logging.basicConfig(
        format='[%(levelname)s] %(message)s',
        stream=sys.stderr,
        level=logging.INFO if quiet else logging.DEBUG)
    try:
        basedir = basedir or os.path.abspath(
            os.path.dirname(processfile))
        if processfile:
            with open(jobfile) as f:
                reana_spec = {
                    "workflow": {"type": "cwl"},
                    "inputs": {"parameters": {"input": yaml.load(f)}}}

            reana_spec['workflow']['spec'] = load_workflow_spec(
                reana_spec['workflow']['type'],
                processfile,
            )
        else:
            with open(jobfile) as f:
                job = yaml.load(f)
            reana_spec = {"workflow": {"type": "cwl"},
                          "parameters": {"input": ""}}

            reana_spec['workflow']['spec'] = load_workflow_spec(
                reana_spec['workflow']['type'],
                job['cwl:tool']
            )
            del job['cwl:tool']
            reana_spec['inputs']['parameters'] = {'input': job}
        reana_spec['workflow']['spec'] = replace_location_in_cwl_spec(
            reana_spec['workflow']['spec'])

        logging.info('Connecting to {0}'.format(ctx.obj.client.server_url))
        response = ctx.obj.client.create_workflow(reana_spec, 'cwl-test',
                                                  access_token)
        logging.error(response)
        workflow_name = response['workflow_name']
        workflow_id = response['workflow_id']
        logging.info('Workflow {0}/{1} has been created.'.format(
            workflow_name, workflow_id))

        file_dependencies_list = []
        for cwlobj in [processfile, jobfile]:
            file_dependencies_list.append(
                get_file_dependencies_obj(cwlobj, basedir))
        files_to_upload = findfiles(file_dependencies_list)
        for cwl_file_object in files_to_upload:
            file_path = cwl_file_object.get('location')
            abs_file_path = os.path.join(basedir, file_path)
            with open(abs_file_path, 'r') as f:
                ctx.obj.client.upload_file(workflow_id, f, file_path,
                                           access_token)
                logging.error('File {} uploaded.'.format(file_path))

        response = ctx.obj.client.start_workflow(
            workflow_id, access_token, reana_spec['inputs']['parameters'])
        logging.error(response)

        first_logs = ""
        while True:
            sleep(1)
            logging.error('Polling workflow logs')
            response = ctx.obj.client.get_workflow_logs(workflow_id,
                                                        access_token)
            logs = response['logs']
            if logs != first_logs:

                logging.error(logs[len(first_logs):])
                first_logs = logs

            if "Final process status" in logs or \
               "Traceback (most recent call last)" in logs:
                # click.echo(response['status'])
                break
        try:
            out = re.search("success{[\S\s]*",
                            logs).group().replace("success", "")
            import ast
            import json
            json_output = json.dumps(ast.literal_eval(str(out)))
        except AttributeError:
            logging.error("Workflow execution failed")
            sys.exit(1)
        except Exception as e:
            logging.error(traceback.format_exc())
            sys.exit(1)
        sys.stdout.write(json_output)
        sys.stdout.write("\n")
        sys.stdout.flush()

    except HTTPServerError as e:
        logging.error(traceback.print_exc())
        logging.error(e)
    except Exception as e:
        logging.error(traceback.print_exc())


def replace_location_in_cwl_spec(spec):
    """Replace absolute paths with relative in a workflow.

    Recursively replace absolute paths with relative in a normalized (packed)
    workflow.
    """
    if spec.get('$graph'):
        result = spec.copy()
        result['$graph'] = []
        for tool in spec['$graph']:
            result['$graph'].append(replace_location_in_cwl_tool(tool))
        return result
    elif spec.get('inputs'):
        return replace_location_in_cwl_tool(spec)
    else:
        return spec


def replace_location_in_cwl_tool(spec):
    """Recursively replace absolute paths with relative."""
    # tools
    inputs_parameters = []
    for param in spec['inputs']:
        if param['type'] == "File":
            if param.get('default', ''):
                location = "location" if param['default'].get(
                    "location") else "path"
                param['default'][location] = param['default'][location].split(
                    '/')[-1]
        inputs_parameters.append(param)
    spec['inputs'] = inputs_parameters
    # workflows
    if spec.get("steps"):
        steps = []
        for tool in spec['steps']:
            tool_inputs = []
            for param in tool['in']:
                if param.get('default') and type(param['default']) is dict:
                    if param['default'].get('class',
                                            param['default'].get('type')) == \
                            'File':
                        location = "location" if param['default'].get(
                            "location") else "path"
                        param['default'][location] = \
                            param['default'][location].split('/')[-1]
                tool_inputs.append(param)
            tool['in'] = tool_inputs
            steps.append(tool)
        spec['steps'] = steps
    return spec


if __name__ == "__main__":
    cwl_runner()
