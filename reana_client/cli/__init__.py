# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2017 CERN.
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
"""REANA command line interface client."""
import json
import logging
import os
import sys
import traceback
import urllib
from time import sleep
import re
import click
import yaml
from bravado.exception import HTTPServerError

from reana_client.cli import analyses, workflow, inputs, outputs, ping
from reana_client.api import Client
from reana_client.config import default_user, default_organization
from reana_client.utils import load_workflow_spec

DEBUG_LOG_FORMAT = '[%(asctime)s] p%(process)s ' \
                   '{%(pathname)s:%(lineno)d} ' \
                   '%(levelname)s - %(message)s'

LOG_FORMAT = '[%(levelname)s] %(message)s'


class Config(object):
    """Configuration object to share across commands."""

    def __init__(self):
        """Initialize config variables."""
        server_url = os.environ.get('REANA_SERVER_URL', 'http://reana.cern.ch')

        logging.info('REANA Server URL ($REANA_SERVER_URL) is: {}'
                     .format(server_url))

        self.client = Client(server_url)


@click.group()
@click.option(
    '--loglevel',
    '-l',
    help='Sets log level',
    type=click.Choice(['debug', 'info']),
    default='info')
@click.pass_context
def cli(ctx, loglevel):
    """REANA Client for interacting with REANA Server."""
    logging.basicConfig(
        format=DEBUG_LOG_FORMAT if loglevel == 'debug' else LOG_FORMAT,
        stream=sys.stderr,
        level=logging.DEBUG if loglevel == 'debug' else logging.INFO)
    ctx.obj = Config()


@click.command()
@click.option('--quiet', is_flag=True,
              help='No diagnostic output')
@click.option('--outdir', type=click.Path(),
              help='Output directory, defaults to the current directory')
@click.argument('processfile', required=False)
@click.argument('jobfile')
@click.pass_context
def cwl_runner(ctx, quiet, outdir, processfile, jobfile):
    """Run CWL files in a standard format <workflow.cwl> <job.json>"""
    logging.basicConfig(
        format='[%(levelname)s] %(message)s',
        stream=sys.stderr,
        level=logging.INFO if quiet else logging.DEBUG)
    ctx.obj = Config()
    try:
        if processfile:
            with open(jobfile) as f:
                reana_spec = {"workflow": {"type": "cwl"},
                              "parameters": {"input": yaml.load(f)}}

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
            reana_spec['parameters']['input'] = job
        reana_spec['workflow']['spec'] = replace_location_in_cwl_spec(reana_spec['workflow']['spec'])
        logging.info('Connecting to {0}'.format(ctx.obj.client.server_url))
        response = ctx.obj.client.create_workflow(default_user, default_organization,
                                                  reana_spec)
        logging.error(response)

        workflow_id = response['workflow_id']
        upload_files_from_cwl_spec(ctx, reana_spec['workflow']['spec'], processfile, workflow_id)
        if reana_spec['parameters']['input']:
            upload_files(ctx, reana_spec['parameters']['input'], jobfile, workflow_id)

            response = ctx.obj.client.start_analysis(default_user,
                                                 default_organization,
                                                 workflow_id)
        logging.error(response)

        first_logs = ""
        while True:
            sleep(1)
            logging.error('Polling workflow logs')
            response = ctx.obj.client.get_workflow_logs(default_user,
                                                        default_organization,
                                                        workflow_id)
            logs = response['logs']
            if logs != first_logs:
                
                logging.error(logs[len(first_logs):])
                first_logs = logs

            if "Final process status" in logs or "Traceback (most recent call last)" in logs:
                # click.echo(response['status'])
                break
        try:
            out = re.search("success[\S\s]*", logs).group().replace("success", "")
        except AttributeError:
            logging.error("Workflow execution failed")
            sys.exit(1)
        stdout = sys.stdout
        if isinstance(out, str):
            stdout.write(out)
        else:
            stdout.write(json.dumps(out, indent=4))
        stdout.write("\n")
        stdout.flush()

    except HTTPServerError as e:
        logging.error(traceback.print_exc())
        logging.error(e)
    except Exception as e:
        logging.error(traceback.print_exc())


def upload_files(ctx, input_structure, jobfile, workflow_id):
    if type(input_structure) is dict:
        if type(input_structure) is dict and input_structure.get('class', None) == 'File':
            with open(os.path.join(os.path.dirname(jobfile), input_structure['location'])) as f:
                response = ctx.obj.client.seed_analysis(
                    default_user,
                    default_organization,
                    workflow_id,
                    f,
                    input_structure['location'])
                logging.error(response)
                logging.error("Transferred file: {0}".format(f.name))
        else:
            for parameter, value in input_structure.items():
                if type(value) is dict and value.get('class', None) == 'File':
                    with open(os.path.join(os.path.abspath(os.path.dirname(jobfile)), value['location'])) as f:
                        response = ctx.obj.client.seed_analysis(
                            default_user,
                            default_organization,
                            workflow_id,
                            f,
                            value['location'])
                        logging.error(response)
                        logging.error("Transferred file: {0}".format(f.name))
                elif type(value) is list:
                    upload_files(ctx, value, jobfile, workflow_id)
    elif type(input_structure) is list:
        for item in input_structure:
            upload_files(ctx, item, jobfile, workflow_id)

def upload_files_from_cwl_spec(ctx, spec, spec_file, workflow_id):
    if spec['inputs']:
        for param in spec['inputs']:
            if param['type'] == "File":
                if param.get('default', ''):
                    upload_file(ctx, param, spec_file, workflow_id)


def replace_location_in_cwl_spec(spec):
    if spec['inputs']:
        params = []
        for param in spec['inputs']:
            if param['type'] == "File":
                if param.get('default', ''):
                    param['default']['location'] = param['default']['location'].split('/')[-1]
            params.append(param)
        spec['inputs'] = params
    return spec


def upload_file(ctx, param, spec_file, workflow_id):
    location = param['default']['location']
    if os.path.isabs(location):
        path = location
    else:
        path = os.path.join(os.path.dirname(spec_file), location)
    if path.startswith("file:///"):
        path = urllib.parse.unquote(path)[7:]
    with open(path) as f:
        response = ctx.obj.client.seed_analysis(
            default_user,
            default_organization,
            workflow_id,
            f,
            location.split("/")[-1])
        logging.error(response)
        logging.error("Transferred file: {0}".format(f.name))


cli.add_command(ping.ping)
cli.add_command(analyses.analyses)
cli.add_command(workflow.workflow)
cli.add_command(inputs.inputs)
cli.add_command(outputs.outputs)
cli.add_command(cwl_runner)

if __name__ == "__main__":
    cwl_runner()
