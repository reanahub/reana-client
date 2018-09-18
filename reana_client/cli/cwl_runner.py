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

import logging
import os
import re
import sys
import traceback
from time import sleep
import urllib

import click
import yaml
from bravado.exception import HTTPServerError

from reana_client.api import Client
from reana_client.config import default_user
from reana_client.decorators import with_api_client
from reana_client.utils import load_workflow_spec
from reana_client.version import __version__
from reana_client.cli.utils import add_access_token_options


@click.command()
@click.version_option(version=__version__)
@click.option('--quiet', is_flag=True,
              help='No diagnostic output')
@click.option('--outdir', type=click.Path(),
              help='Output directory, defaults to the current directory')
@add_access_token_options
@click.argument('processfile', required=False)
@click.argument('jobfile')
@click.pass_context
@with_api_client
def cwl_runner(ctx, quiet, outdir, processfile, jobfile, access_token):
    """Run CWL files in a standard format <workflow.cwl> <job.json>."""
    logging.basicConfig(
        format='[%(levelname)s] %(message)s',
        stream=sys.stderr,
        level=logging.INFO if quiet else logging.DEBUG)
    try:
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
        upload_files_from_cwl_spec(
            ctx.obj.client, reana_spec['workflow']['spec'], processfile,
            workflow_id)
        if reana_spec['inputs']['parameters']['input']:
            upload_files(
                ctx.obj.client, reana_spec['inputs']['parameters']['input'],
                jobfile, workflow_id)

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
        except AttributeError:
            logging.error("Workflow execution failed")
            sys.exit(1)
        sys.stdout.write(out)
        sys.stdout.write("\n")
        sys.stdout.flush()

    except HTTPServerError as e:
        logging.error(traceback.print_exc())
        logging.error(e)
    except Exception as e:
        logging.error(traceback.print_exc())


def upload_files(client, input_structure, jobfile, workflow_id):
    """Recursively find and upload input files and directories from CWL job."""
    if type(input_structure) is dict:
        if type(input_structure) is dict and \
           input_structure.get('class', None) == 'File':
            transfer_file(client, input_structure, jobfile, workflow_id)
        elif (type(input_structure) is dict and
              input_structure.get('class', None) == 'Directory'):
            upload_directory(client, jobfile, workflow_id,
                             input_structure.get("location"))
        else:
            for parameter, value in input_structure.items():
                if type(value) is dict and value.get('class', None) == 'File':
                    transfer_file(client, value, jobfile, workflow_id)
                elif type(value) is dict:
                    upload_files(client, value, jobfile, workflow_id)
                elif type(value) is list:
                    upload_files(client, value, jobfile, workflow_id)
    elif type(input_structure) is list:
        for item in input_structure:
            upload_files(client, item, jobfile, workflow_id)


def transfer_file(client, file_dict, jobfile, workflow_id):
    """Upload single file and all secondary files."""
    if file_dict.get("contents"):
        pass
    else:
        path = file_dict.get('location', file_dict.get('path'))
        with open(os.path.join(os.path.abspath(os.path.dirname(jobfile)),
                               path), 'rb') as f:
            response = client.upload_file(
                workflow_id,
                f,
                path,
                access_token)
            logging.error(response)
            logging.error("Transferred file: {0}".format(f.name))
    """
    Example of CWL parameter structure (.yml format):

    input_parameter:
      class: File
      location: hello.tar
      secondaryFiles:
        - class: File
          location: index.py
        - class: Directory
          basename: xtestdir
          location: testdir
    """
    if file_dict.get("secondaryFiles"):
        for f in file_dict["secondaryFiles"]:
            if f['class'] == 'File':
                transfer_file(client, f, jobfile, workflow_id)
            elif f['class'] == 'Directory':
                upload_directory(client, jobfile, workflow_id, f.get(
                    "location"), f.get("basename", None))


def upload_files_from_cwl_spec(client, spec, spec_file, workflow_id):
    """Collect and upload files from cwl workflow.

    Traverse through normalized (packed) cwl workflow to collect and upload all
    file inputs.
    """
    if spec.get('$graph'):
        for tool in spec['$graph']:
            upload_files_from_cwl_tool(client, tool, spec_file, workflow_id)
    elif spec.get('inputs'):
        upload_files_from_cwl_tool(client, spec, spec_file, workflow_id)
    else:
        logging.error("No file input sources detected")
        pass


def upload_files_from_cwl_tool(client, spec, spec_file, workflow_id):
    """Collect and upload files from a cwl workflow step.

    Traverse through tool inputs and workflow steps to collect and upload all
    file inputs.
    """
    if spec['inputs']:
        for param in spec['inputs']:
            if param['type'] == "File":
                if param.get('default', ''):
                    upload_file(client, param, spec_file, workflow_id)
            elif param.get('secondaryFiles'):
                extensions = {ext for ext in param['secondaryFiles']}
                directory = os.path.abspath(os.path.dirname(spec_file))
                for file in os.listdir(directory):
                    if any(file.endswith(ext) for ext in extensions):
                        transfer_file(client, {"location": os.path.join(file)},
                                      spec_file, workflow_id)
    if spec.get("steps"):
        for tool in spec['steps']:
            for param in tool['in']:
                if param.get('type', param.get('class')) == "File":
                    if param.get('default', ''):
                        upload_file(client, param, spec_file, workflow_id)
                elif param.get('default') and type(param['default']) is dict:
                    if (param['default']
                            .get("type", param['default'].get("class")) == "File"):
                        upload_file(client, param, spec_file, workflow_id)


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


def upload_directory(client, spec_file, workflow_id, location, basename=None,
                     disk_directory_name=None):
    """Recursively upload directory as an input to a workflow."""
    if not os.path.isabs(location):
        disk_directory_name = location
        location = os.path.join(os.path.abspath(
            os.path.dirname(spec_file)), location)
    else:
        disk_directory_name = disk_directory_name
    for f in os.listdir(location):
        filename = os.path.abspath(os.path.join(location, f))
        if os.path.isdir(filename):
            upload_directory(client, spec_file, workflow_id,
                             os.path.abspath(filename),
                             basename=basename,
                             disk_directory_name=disk_directory_name)
        elif os.path.isfile(filename):
            with open(filename, 'rb') as file_:
                directory_name = filename.replace(
                    os.path.abspath(os.path.dirname(spec_file)) + "/", "")
                if basename:
                    directory_name = directory_name.replace(
                        disk_directory_name, basename)
                response = client.upload_file(
                    workflow_id,
                    file_,
                    directory_name,
                    access_token)
                logging.error(response)
                logging.error("Transferred file: {0}".format(file_.name))


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


def upload_file(client, param, spec_file, workflow_id):
    """Upload single file."""
    location = param['default'].get("location", param['default'].get("path"))
    if os.path.isabs(location):
        path = location
    else:
        path = os.path.join(os.path.abspath(
            os.path.dirname(spec_file)), location)
    if path.startswith("file:///"):
        path = urllib.parse.unquote(path)[7:]
    if os.path.exists(path):
        with open(path, 'rb') as f:
            filename = path.replace(os.path.abspath(
                os.path.dirname(spec_file)) + "/", "")
            response = ctx.obj.client.\
                upload_to_server(workflow_id,
                                 filename,
                                 access_token)
            response = client.upload_file(
                workflow_id,
                f,
                filename,
                access_token)
            logging.error(response)
            logging.error("Transferred file: {0}".format(f.name))


if __name__ == "__main__":
    cwl_runner()
