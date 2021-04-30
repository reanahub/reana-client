
.. include:: ../README.rst
   :end-before: About

.. include:: ../README.rst
   :start-after: =====
   :end-before: Useful links


CLI API
=======

.. include:: cmd_list.txt
   :literal:

.. click:: reana_client.cli:cli
   :prog: reana-client
   :show-nested:

API docs
========

.. automodule:: reana_client.api.client
  :members: create_workflow_from_json, upload_to_server, upload_file, start_workflow, list_files, get_workflow_status, download_file, get_workflow_logs

.. include:: ../CHANGES.rst

.. include:: ../CONTRIBUTING.rst

License
=======

.. include:: ../LICENSE

In applying this license, CERN does not waive the privileges and immunities
granted to it by virtue of its status as an Intergovernmental Organization or
submit itself to any jurisdiction.

.. include:: ../AUTHORS.rst
