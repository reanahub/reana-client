.. _userguide:

User guide
==========

Environment variables
---------------------

REANA_SERVER_URL
~~~~~~~~~~~~~~~~

You can set this environment variable in order to specify to which REANA cloud
instance your client should connect and a valid token. For example:

.. code-block:: console

   $ export REANA_SERVER_URL=https://reana.cern.ch

REANA_ACCESS_TOKEN
~~~~~~~~~~~~~~~~~~

You should specify valid access token for the REANA cloud instance you would
like to use. For example:

.. code-block:: console

   $ export REANA_ACCESS_TOKEN=XXXXXXX

The token should have been given to you by the REANA cluster administrators.

REANA_WORKON
~~~~~~~~~~~~

You can set this environment variable in order to specify a concrete workflow
you would like to work on. (As an alternative to specifying ``--workflow``
option in commands.) For example:

.. code-block:: console

   $ export REANA_WORKON=myfirstanalysis

will work on the latest run of your "myfirstanalysis" workflow.

Note that you can also specify a concrete run number:

.. code-block:: console

   $ export REANA_WORKON=myfirstanalysis.3

which will permit to work on the third run of the "myfirstanalysis" workflow,
for example to check out past input and output files.

You can list all your workflow runs and their statuses by doing:

.. code-block:: console

   $ reana-client workflows

and set ``REANA_WORKON`` to the one you would like to work on.

Usage
-----

Overview
~~~~~~~~

Please see the :ref:`gettingstarted` section for a basic ``reana-client`` use
case scenario.

Uploading analysis assets
~~~~~~~~~~~~~~~~~~~~~~~~~

Uploading files or directories to an analysis workspace is simple as:

.. code-block:: console

   $ reana-client upload file1 file2 directory1
   File file1 was successfully uploaded.
   File file2 was successfully uploaded.
   File directory1/file3 was successfully uploaded.

If you want to upload all input files defined in the reana.yaml of the analysis,
you can just run:

.. code-block:: console

   $ reana-client upload
   File file1 was successfully uploaded.
   File file2 was successfully uploaded.

Directory structures are maintained, i.e.
directory1 exists in the workspace.

Note that symbolic links are resolved at the moment of upload
so that a hard copy of the link target is uploaded to the cloud
storage workspace. The link is not maintained throughout the
workflow execution.

Overriding default input parameters
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If you want to run a workflow with different input parameters than the ones in
``reana.yaml``, you can do it by running `reana-client start` with flag ``-p``
and specifying parameters that you want to override.

Note that parameters passed with ``-p`` flag must exist in reana.yaml.
Non-existing parameters will be skipped.

.. code-block:: console

   $ reana-client start -p myparam1=myval1 -p myparam2=myval2
   workflow.1 has been started.

Downloading outputs
~~~~~~~~~~~~~~~~~~~

Downloading files from an analysis workspace works in the same way:

.. code-block:: console

   $ reana-client download result.png
   File plot.png downloaded to /myfirstanalysis.

In the same way you can download all outputs defined in the reana.yaml
file of the analysis, by just running:

.. code-block:: console

   $ reana-client download

Note that downloading directories is not yet supported.

Running analysis
~~~~~~~~~~~~~~~~

If you have fully working analysis with ``reana.yaml``, you can run the workflow
easily via the ``run`` wrapper command, which will create a new workflow, upload
analysis inputs, and start the workflow run.

.. code-block:: console

   $ vim reana.yaml
   $ reana-client run -n myanalysis
   [INFO] Creating a workflow...
   myanalysis.1
   [INFO] Uploading files...
   File code/helloworld.py was successfully uploaded.
   File data/names.txt was successfully uploaded.
   [INFO] Starting workflow...
   myanalysis.1 has been started.
   $ export REANA_WORKON=myanalysis
   $ reana-client status
   NAME         RUN_NUMBER   CREATED               STATUS    PROGRESS
   myanalysis   1            2018-11-07T12:45:18   running   1/1
   $ reana-client download results/plot.png

Deleting workflows
~~~~~~~~~~~~~~~~~~

You can mark a workflow as deleted with:

.. code-block:: console

   $ reana-client delete

Passing no argument will mark the workflow selected by your REANA_WORKON
variable as deleted. To specify a different workflow than your
currently selected one use the -w/--workflow flag and set the workflow name
and run number.
If e.g. workflow run number 123 of your analysis failed, you can delete it
as follows:

.. code-block:: console

   $ reana-client delete --workflow=myanalysis.123

After simple deletion the workspace can be accessed to retrieve files uploaded
there. If you are sure the workspace can also be deleted pass the
--include-workspace flag.

.. code-block:: console

   $ reana-client delete --workflow=myanalysis.123 --include-workspace

To delete all runs of a given workflow, pass the --include-all-runs flag and
run:

.. code-block:: console

   $ reana-client delete --workflow=myanalysis --include-all-runs

and to completely remove a workflow run and its workspace from REANA
pass the --include-records flag:

.. code-block:: console

   $ reana-client delete --workflow=myanalysis.1 --include-records

Stopping workflows
~~~~~~~~~~~~~~~~~~

You can stop a workflow with:

.. code-block:: console

    $ reana-client stop --force

The workflow assigned to REANA_WORKON variable will be stopped. To specify a
different workflow than your currently selected one use the -w/--workflow flag
and set the workflow name or UUID.

.. code-block:: console

    $ reana-client stop --force --workflow=otherworkflow.1

Note that currently only force stop is implemented.

Examples
--------

You can get inspiration on how to structure your REANA-compatible research data
analysis from several ``reana-demo-...`` examples
`provided on GitHub <https://github.com/reanahub?utf8=%E2%9C%93&q=reana-demo&type=&language=>`_.

Commands
--------

The full list of ``reana-client`` commands with their documented options is
available in the :ref:`cliapi` documentation.
