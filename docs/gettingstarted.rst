.. _gettingstarted:

Getting Started
===============

Install REANA client
--------------------

If you are a researcher that is interested in running analyses on the REANA
cloud, all you need to install is the ``reana-client``, ideally in a new virtual
environment:

.. code-block:: console

   $ mkvirtualenv reana-client
   $ pip install reana-client

Select REANA cloud
------------------

You can now select the REANA cloud instance where to run your analyses by
setting the ``REANA_SERVER_URL`` variable appropriately and providing a valid
access token through the environment variable ``REANA_ACCESS_TOKEN``. For
example:

.. code-block:: console

   $ export REANA_SERVER_URL=http://reana.cern.ch
   $ export REANA_ACCESS_TOKEN=<ACCESS_TOKEN>

Note that if you are trying to run REANA cluster locally on your laptop (and not
only the client!), you can use:

.. code-block:: console

   $ eval $(reana-cluster env --all)

see the `REANA-Cluster getting started guide
<http://reana-cluster.readthedocs.io/en/latest/gettingstarted.html>`_.

Run example analysis
--------------------

Let us take `reana-demo-helloworld
<https://github.com/reanahub/reana-demo-helloworld/>`_ as a simple example
analysis to run on our REANA cloud.

Please familiarise yourself with the structure of ``reana-demo-helloworld``
GitHub repository and how it specifies the analusis code, data, environment, and
the computation workflow to produce the analysis output. The ``reana-client``
usage scenario will be identical in submitting any complex research data
computational workflows.

Let us start by testing connection to the REANA cloud:

.. code-block:: console

   $ reana-client ping
   Server is running.

We can now create a new computational workflow:

.. code-block:: console

   $ reana-client create
   workflow.1

This created a workflow with the default name "workflow" and run number "1".

Note that if you would like to give your workflow a different name, you can use
the ``-n`` argument:

.. code-block:: console

   $ reana-client create -n myfirstdemo
   myfirstdemo.1

We can check the status of our previously created workflow:

.. code-block:: console

   $ reana-client status -w workflow.1
   NAME       RUN_NUMBER   CREATED               STATUS    PROGRESS
   workflow   1            2018-08-10T07:27:15   created   -/-

Note that instead of passing ``-w`` argument with the workflow name every time,
we can define a new environment variable ``REANA_WORKON`` which specifies the
workflow we would like to work on:

.. code-block:: console

   $ export REANA_WORKON=workflow.1

Let us upload our code:

.. code-block:: console

   $ reana-client upload ./code/helloworld.py
   File code/helloworld.py was successfully uploaded.

and check whether it indeed appears seeded in our workspace:

.. code-block:: console

   $ reana-client list
   NAME                 SIZE   LAST-MODIFIED
   code/helloworld.py   2905   2018-08-10 07:29:54.034067+00:00

Similarly, let us now upload the input data file:

.. code-block:: console

   $ reana-client upload ./inputs/names.txt
   File inputs/names.txt was successfully uploaded.

and check whether it was well seeded into our input workspace:

.. code-block:: console

   $ reana-client list
   NAME                 SIZE   LAST-MODIFIED
   inputs/names.txt     18     2018-08-10 07:31:15.986705+00:00
   code/helloworld.py   2905   2018-08-10 07:29:54.034067+00:00

Now that the input data and code was uploaded, we can start the workflow execution:

.. code-block:: console

   $ reana-client start
   workflow.1 has been started.

Let us enquire about its running status; we may see that it is still in the
"running" state:

.. code-block:: console

   $ reana-client status
   NAME       RUN_NUMBER   CREATED               STATUS    PROGRESS
   workflow   1            2018-08-10T07:27:15   running   0/1

After a few minutes, the workflow should be finished:

.. code-block:: console

   $ reana-client status
   NAME       RUN_NUMBER   CREATED               STATUS     PROGRESS
   workflow   1            2018-08-10T07:27:15   finished   1/1

We can now check the list of output files:

.. code-block:: console

   $ reana-client list
   NAME                                    SIZE   LAST-MODIFIED
   helloworld/greetings.txt                32     2018-08-10 07:33:51.885092+00:00
   _yadage/yadage_snapshot_backend.json    576    2018-08-10 07:33:59.698738+00:00
   _yadage/yadage_snapshot_workflow.json   9163   2018-08-10 07:33:59.698738+00:00
   _yadage/yadage_template.json            1099   2018-08-10 07:32:26.684325+00:00
   inputs/names.txt                        18     2018-08-10 07:31:15.986705+00:00
   code/helloworld.py                      2905   2018-08-10 07:29:54.034067+00:00

and retrieve the resulting output file:

.. code-block:: console

   $ reana-client download helloworld/greetings.txt
   File helloworld/greetings.txt downloaded to /home/reana/reanahub/reana-demo-helloworld.

Let us see whether we got the expected output:

.. code-block:: console

   $ cat helloworld/greetings.txt
   Hello John Doe!
   Hello Jane Doe!

Everything is well; the workflow was well executed.

Next steps
----------

For more information, please see:

- Looking for a more comprehensive REANA client user manual? See :ref:`userguide`
- Looking for tips how to develop REANA client component? See :ref:`developerguide`
- Looking for REANA client command-line API reference? See :ref:`cliapi`
