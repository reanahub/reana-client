.. _userguide:

User guide
==========

Environment variables
---------------------

REANA_SERVER_URL
~~~~~~~~~~~~~~~~

You can set this environment variable in order to specify to which REANA cloud
instance your client should connect. For example:

.. code-block:: console

   $ export REANA_SERVER_URL=https://reana.cern.ch

REANA_ACCESS_TOKEN
~~~~~~~~~~~~~~~~~~

You should specify valid access token for the REANA cloud instance you would
like to use. For example:

.. code-block:: console

   $ export REANA_ACCESS_TOKEN=XXXXXXX

The token should be provided to you by the REANA cluster administrators.

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

   $ reana-client list

and set ``REANA_WORKON`` to the one you would like to work on.

Usage
-----

Overview
~~~~~~~~

Please see the :ref:`gettingstarted` section for a basic ``reana-client`` use
case scenario.

Uploading analysis assets
~~~~~~~~~~~~~~~~~~~~~~~~~

Uploading files or directories to the analysis workspace is simple as:

.. code-block:: console

   $ reana-client upload mydata.csv mycode.C mytmp
   File mydata.csv was successfully uploaded.
   File mycode.C was successfully uploaded.
   File mytmp/myfiltereddata.csv was successfully uploaded.

If you want to upload all input files defined in the reana.yaml of the analysis,
you can just run:

.. code-block:: console

   $ reana-client upload
   File mydata.csv was successfully uploaded.
   File mycode.C was successfully uploaded.

Directory structures are maintained, i.e.
mytmp exists in the workspace.

Note that symbolic links are resolved at the moment of upload
so that a hard copy of the link target is uploaded to the cloud
storage workspace. The link is not maintained throughout the
workflow execution.


Deleting analysis assets
~~~~~~~~~~~~~~~~~~~~~~~~

The deletion of files contained in the analysis workspace is possible through
the ``remove`` command:

.. code-block:: console

   $ reana-client rm mydata.csv
   File mydata.csv was successfully deleted.
   25356 bytes freed up.

If you want to delete more than one file at once it is possible to use
globbing:

.. code-block:: console

   $ reana-client rm '**/*.csv'
   File mydata.csv was successfully deleted.
   File mytmp/myfiltereddata.csv was successfully deleted.
   79736 bytes freed up.


Moving analysis assets
~~~~~~~~~~~~~~~~~~~~~~

The movement of file(s) or folders within the analysis workspace is
possible through the ``mv`` command:

.. code-block:: console

   $ reana-client mv data/mydata.csv mydata.csv
   File mydata.csv was successfully deleted.


Adding secrets
~~~~~~~~~~~~~~

If you need to use secrets in your workflow you can add them with
the ``secrets-add`` command:

.. code-block:: console

   $ # You can upload secrets from literal strings:
   $ reana-client secrets-add --env CERN_USER=johndoe
                              --env CERN_KEYTAB=.keytab
   Secrets CERN_USER, CERN_KEYTAB were successfully uploaded.

   $ # ...and from files:
   $ reana-client secrets-add --file ~/.keytab
   Secrets .keytab were successfully uploaded.

   $ # ...you can also combine two options in one command:
   $ reana-client secrets-add --env CERN_USER=johndoe
                              --env CERN_KEYTAB=.keytab
                              --file ~/.keytab
   Secrets .keytab, CERN_USER, CERN_KEYTAB were successfully uploaded.

   $ # Trying to add a secret that is already added
   $ # will result in a warning and no action will be taken:
   $ reana-client secrets-add --env CERN_USER=johndoe
   One of the secrets already exists. No secrets were added.

   $ # If you are sure that you want to overwrite it you can use
   $ # the ``--overwrite`` option:
   $ reana-client secrets-add --env CERN_USER=janedoe
                              --overwrite
   Secrets CERN_USER were successfully uploaded.
   $ # Note that the ``--overwrite`` option will aply to
   $ # all of secrets passed next to it.


The added secrets will be available in your workflow execution container either
as environment variables (see example ``CERN_USER`` above) or as
mounted files (see ``.keytab`` example above) in the ``/etc/reana/secrets/``
directory.

Listing secrets
~~~~~~~~~~~~~~~

To list all the secrets that you have uploaded you can use
the ``secrets-list`` command:

.. code-block:: console

   $ reana-client secrets-list
   NAME                    TYPE
   .keytab                 file
   CERN_KEYTAB             env
   CERN_USER               env


Deleting secrets
~~~~~~~~~~~~~~~~

If you want to delete some of the secrets that you have uploaded you can use
the ``secrets-delete`` command:

.. code-block:: console

   $ reana-client secrets-delete CERN_USER, CERN_KEYTAB
   Secrets CERN_USER, CERN_KEYTAB were successfully deleted.


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

Running specific parts of analysis
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

*Serial*

Serial workflows can be executed partially until the step specified by the
user.  To do so, you need to provide the target step name as an operational
option to the ``reana-client start`` or ``reana-client run`` commands.

.. code-block:: console

   $ reana-client start -w workflow.1 -o target='gendata'
   # or
   $ reana-client run -w workflow.1 -o target='gendata'

*CWL*

CWL allows `executing workflows partially <https://github.com/common-workflow-language/cwltool#running-only-part-of-a-workflow>`_.
To do so, you need to provide the specific target as an operational option for
the ``reana-client start`` or ``reana-client run`` commands.

.. code-block:: console

   $ reana-client start -w workflow.1 -o target='gendata'
   # or
   $ reana-client run -w workflow.1 -o target='gendata'

*Yadage*

Not implemented yet.

Downloading outputs
~~~~~~~~~~~~~~~~~~~

Downloading files from an analysis workspace:

.. code-block:: console

   $ reana-client download result.png
   File plot.png downloaded to /myfirstanalysis.

In the same way you can download all outputs defined in the reana.yaml
file of the analysis, by just running:

.. code-block:: console

   $ reana-client download

Note that downloading directories is not yet supported.


Opening interactive sessions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

While your analysis workflows are running, you may want to open interactive
session processes on the workspace, such as Jupyter notebooks, via the `open`
command. This will allow to quickly explore the generated data while the
analysis is in progress, or even run your analyses from within the notebook
environment spawned on the remote containerised platform.

.. code-block:: console

   $ reana-client open -w myanalysis.1 jupyter
   https://reana.cern.ch/7cd4d23e-48d1-4f7f-8a3c-3a6d256fb8bc?token=P-IkL_7w25IDHhes8I7DtICWLNQm2WAZ9gkoKC2vq10
   It could take several minutes to start the interactive session.

Open the link returned by the command in order to access the interactive
notebook session.

.. image:: /_static/interactive-session.png

REANA currently supports `Jupyter <https://jupyter.org>`_ notebooks. Note that
you can pass any notebook image you are interested to run on the workspace,
such as PySpark, or even your own image, by using the `--image` option.


Closing interactive sessions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Once you finished working on your interactive session notebook, you can close it
via ``close`` command.

.. code-block:: console

   $ reana-client close -w myanalysis.1
   Interactive session for workflow myanalysis.1 was successfully closed

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
