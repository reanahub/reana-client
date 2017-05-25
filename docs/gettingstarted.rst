Getting started
===============

.. admonition:: Work-In-Progress

   **FIXME** The ``reana-client`` package is a not-yet-released work in
   progress. Moreover, the ``reana-server`` instance at reana.cern.ch is
   still not available.

In order to check if the ``reana-client`` can connect with ``reana-cloud``
we can run the following command.

.. code-block:: console

   $ reana-client ping
   [INFO] REANA Server URL set to: http://reana.cern.ch
   [INFO] Connecting to http://reana.cern.ch
   [INFO] Server is running.

Submitting jobs
---------------

.. admonition:: Work-In-Progress

   **FIXME** Not implemented yet.

You can submit your job to REANA as follows:

.. code-block:: console

   $ cd my-reseach-data-analysis
   $ reana-client run
   [INFO] Preparing to run analysis...
   [...]
   [INFO] Done. You can see the results in the `output/` directory.
