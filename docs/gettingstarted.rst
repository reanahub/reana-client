.. _gettingstarted:

Getting Started
===============

Install REANA client
--------------------

If you are a researcher that is interested in running analyses on the REANA
cloud, all you need to install is the ``reana-client``, ideally in a new virtual
environment:

.. code-block:: console

   $ mkvirtualenv reana-client -p /usr/bin/python2.7
   $ pip install reana-client

Select REANA cloud
------------------

You can now select the REANA cloud instance where to run your analyses by
setting the ``REANA_SERVER_URL`` variable appropriately. For example:

.. code-block:: console

   $ export REANA_SERVER_URL=http://reana.cern.ch

Note that if you are trying to run REANA cluster locally on your laptop (and not
only the client!), you can use:

.. code-block:: console

   $ eval $(reana-cluster env)

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

   $ reana-client workflow create
   workflow.1

This created a workflow with the default name "workflow" and run number "1".

Note that if you would like to give your workflow a different name, you can use
the ``-n`` argument:

.. code-block:: console

   $ reana-client workflow create -n myfirstdemo
   myfirstdemo.1

We can check the status of our previously created workflow:

.. code-block:: console

   $ reana-client workflow status -w workflow.1
   NAME       RUN_NUMBER   ID                                     USER                                   ORGANIZATION   STATUS
   workflow   1            91797125-012c-498d-8a92-b4f7e3598513   00000000-0000-0000-0000-000000000000   default        created

Note that instead of passing ``-w`` argument with the workflow name every time,
we can define a new environment variable ``REANA_WORKON`` which specifies the
workflow we would like to work on:

.. code-block:: console

   $ export REANA_WORKON=workflow.1

Let us upload our code:

.. code-block:: console

   $ reana-client code upload ./code/helloworld.py
   /home/simko/private/project/reana/src/reana-demo-helloworld/code/helloworld.py was uploaded successfully.

and check whether it indeed appears seeded in our workspace:

.. code-block:: console

   $ reana-client code list
   NAME            SIZE   LAST-MODIFIED
   helloworld.py   2905   2018-04-20 13:20:01.471120+00:00

Similarly, let us now upload the input data file:

.. code-block:: console

   $ reana-client inputs upload ./inputs/names.txt
   File /home/simko/private/project/reana/src/reana-demo-helloworld/inputs/names.txt was successfully uploaded.

and check whether it was well seeded into our input workspace:

.. code-block:: console

   $ reana-client inputs list
   NAME        SIZE   LAST-MODIFIED
   names.txt   18     2018-04-20 13:20:28.834120+00:00

Now that the input data and code was uploaded, we can start the workflow execution:

.. code-block:: console

   $ reana-client workflow start
   workflow.1 has been started.

Let us enquire about its running status; we may see that it is still in the
"running" state:

.. code-block:: console

   $ reana-client workflow status
   NAME       RUN_NUMBER   ID                                     USER                                   ORGANIZATION   STATUS
   workflow   1            91797125-012c-498d-8a92-b4f7e3598513   00000000-0000-0000-0000-000000000000   default        running

After a few minutes, the workflow should be finished:

.. code-block:: console

   $ reana-client workflow status
   NAME       RUN_NUMBER   ID                                     USER                                   ORGANIZATION   STATUS
   workflow   1            91797125-012c-498d-8a92-b4f7e3598513   00000000-0000-0000-0000-000000000000   default        finished

We can now check the list of output files:

.. code-block:: console

   $ reana-client outputs list
   NAME                                    SIZE   LAST-MODIFIED
   helloworld/greetings.txt                32     2018-04-20 13:22:38.460119+00:00
   _yadage/yadage_snapshot_backend.json    590    2018-04-20 13:22:38.460119+00:00
   _yadage/yadage_snapshot_workflow.json   9267   2018-04-20 13:22:38.460119+00:00
   _yadage/yadage_template.json            1099   2018-04-20 13:22:38.460119+00:00

and retrieve the resulting output file:

.. code-block:: console

   $ reana-client outputs download helloworld/greetings.txt
   File helloworld/greetings.txt downloaded to ./outputs/

Let us see whether we got the expected output:

.. code-block:: console

   $ cat outputs/helloworld/greetings.txt
   Hello John Doe!
   Hello Jane Doe!

Everything is well; the workflow was well executed.

Next steps
----------

For more information, please see:

- Looking for a more comprehensive REANA client user manual? See :ref:`userguide`
- Looking for tips how to develop REANA client component? See :ref:`developerguide`
- Looking for REANA client command-line API reference? See :ref:`cliapi`
