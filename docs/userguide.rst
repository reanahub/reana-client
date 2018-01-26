.. _userguide:

User guide
==========

.. admonition:: Work-In-Progress

   **FIXME** The ``reana-client`` package is a not-yet-released work in
   progress. Moreover, the ``reana-server`` instance at reana.cern.ch is
   still not available.

Verify REANA client connection
------------------------------

In order to check if the ``reana-client`` can connect with REANA cloud,
we can run the following command:

.. code-block:: console

   $ reana-client ping
   [INFO] REANA Server URL set to: http://reana.cern.ch
   [INFO] Connecting to http://reana.cern.ch
   [INFO] Server is running.


Validating analyses specifications
----------------------------------

.. admonition:: Work-In-Progress

   **FIXME** Not implemented yet.

You can validate your current analysis specification (``./reana.yaml``), so it
can be run in REANA, as follows:

.. code-block:: console

   $ reana-client analysis validate
   File ./reana.yaml is a valid REANA specification file.


Create workflow
---------------

.. admonition:: Work-In-Progress

   **FIXME** Not implemented yet.

You can create the workflow and its workspace as follows:

.. code-block:: console

   $ reana-client workflow create --name mytest
   Workflow `mytest` created.


Once the workflow is created, in order to use it you have to export the
following environment variable or explicitly provide to each command to which
workflow should the action be performed:

.. code-block:: console

   $ export REANA_WORKON=mytest


Seeding workflow workspace
--------------------------

.. admonition:: Work-In-Progress

   **FIXME** Not implemented yet.

You add files to the workflow workspace as follows:

.. code-block:: console

   $ reana-client inputs upload mydata.csv
   dataset.csv was successfully uploaded.


Setting analysis parameters
---------------------------

.. admonition:: Work-In-Progress

   **FIXME** Not implemented yet.

You can set analysis parameters as follows:

.. code-block:: console

   $ reana-client inputs set min_year 1990
   min_year=1990
   $ reana-client inputs set max_year 2001
   max_year=2001


List workflow inputs
--------------------

.. admonition:: Work-In-Progress

   **FIXME** Not implemented yet.

You add files to the workflow workspace as follows:

.. code-block:: console

   $ reana-client inputs list --json
   {
     'files': ['mydata.csv'],
     'parameters': [
       {'min_year': '1990'},
       {'max_year': '2001'}
     ]
   }
   $ reana-client inputs list --files
   mydata.csv
   $ reana-client inputs list --parameters
   min_year=1990
   max_year=2001


Adding necessary code to start analysis
---------------------------------------

.. admonition:: Work-In-Progress

   **FIXME** Not implemented yet.

You add code to the workflow workspace as follows:

.. code-block:: console

   $ reana-client code upload mycode.py
   mycode.py was successfully uploaded.


Starting a workflow
-------------------

.. admonition:: Work-In-Progress

   **FIXME** Not implemented yet.

You can start your workflow in REANA as follows:

.. code-block:: console

   $ reana-client workflow start
   Workflow mytest has been started.


Querying for the workflow status
--------------------------------

.. admonition:: Work-In-Progress

   **FIXME** Not implemented yet.

You can query for a specific workflow status like follows:

.. code-block:: console

   $ reana-client workflow status
   running
   $ reana-client workflow status --workflow mytest1
   failed


Listing analyses
----------------

.. admonition:: Work-In-Progress

   **FIXME** Not implemented yet.

You can list the current analyses on REANA like follows:

.. code-block:: console

   $ reana-client workflow list
   Name     UUID                                  Status
   mytest   0328f3a0-a369-4971-b3c8-e8aa865ba5fa  running
   mytest1  0328f3a0-a369-4971-b3c8-e8aa865ba5fa  failed


Getting workflow outputs
------------------------

.. admonition:: Work-In-Progress

   **FIXME** Not implemented yet.

You can start your analysis in REANA as follows:

.. code-block:: console

   $ reana-client outputs list
   plot.png
   $ reana-client outputs download plot.png
   File plot.png downloaded under ./outputs/


Deleting a workflow
-------------------

.. admonition:: Work-In-Progress

   **FIXME** Not implemented yet.

You can delete a workflow like follows:

.. code-block:: console

   $ reana-client workflow destroy --workflow mytest1
   Workflow mytest1 has been destroyed.
