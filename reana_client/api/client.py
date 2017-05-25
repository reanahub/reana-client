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
"""REANA REST API client."""

import requests

from .. import config


class Client(object):
    """REANA API client code."""

    def __init__(self, server_url, apipath=config.API_PATH):
        """Initialize REST API client."""
        self.server_url = server_url
        self.apipath = apipath

    def ping(self):
        """Health check REANA Server."""
        endpoint = '{server_url}{apipath}/ping'.format(
            server_url=self.server_url,
            apipath=self.apipath)
        try:
            response = requests.get(endpoint)
            if response.status_code == 200:
                return response.text
            else:
                raise Exception(
                    "Expected status code 200 but {endpoint} replied with "
                    "{status_code}".format(
                        status_code=response.status_code, endpoint=endpoint))

        except Exception:
            raise
