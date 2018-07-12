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
"""REANA client configuration."""

import pkg_resources

reana_yaml_default_file_path = './reana.yaml'  # e.g. `./.reana.yaml`
"""REANA specification file default location."""

reana_yaml_schema_file_path = pkg_resources.resource_filename(
        __name__,
        'schemas/reana_analysis_schema.json')
"""REANA specification schema location."""

default_user = '00000000-0000-0000-0000-000000000000'
"""Default user to use when submitting workflows to Reana Server."""

ERROR_MESSAGES = {
        'missing_access_token':
        'Please provide your access token by using'
        ' the -at/--access-token flag, or by setting the'
        ' REANA_ACCESS_TOKEN environment variable.'
}
