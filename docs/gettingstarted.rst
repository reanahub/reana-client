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

Note that we are using Python-2.7 here; this is currently necessary for the
`Yadage <https://github.com/diana-hep/yadage>`_ computational workflows to work
at this moment.

Select REANA cloud
------------------

You can now select the REANA cloud instance where to run your analyses by
setting the ``REANA_SERVER_URL`` variable appropriately. For example:

.. code-block:: console

   $ export REANA_SERVER_URL=http://reana.cern.ch

Note that if you would like to try REANA locally, you can easily install a local
REANA cluster on your laptop. Please follow the `REANA-Cluster getting started
guide <http://reana-cluster.readthedocs.io/en/latest/gettingstarted.html>`_.

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
   [INFO] REANA Server URL ($REANA_SERVER_URL) is: http://192.168.99.100:31201
   [INFO] Connecting to http://192.168.99.100:31201
   [INFO] Server is running.

We can now create a new computational workflow:

.. code-block:: console

   $ reana-client workflows create -f reana.yaml
   [INFO] Validating REANA specification file: /Users/rodrigdi/reana/reana-demo-helloworld/reana.yaml
   [INFO] Connecting to http://192.168.99.100:31201
   {u'message': u'Workflow workspace created', u'workflow_id': u'57c917c8-d979-481e-ae4c-8d8b9ffb2d10'}

and check its status:

.. code-block:: console

   $ reana-client workflows status --workflow 57c917c8-d979-481e-ae4c-8d8b9ffb2d10
   [INFO] REANA Server URL ($REANA_SERVER_URL) is: http://192.168.99.100:31201
   [INFO] Workflow "afbbf6d1-a129-4e4f-ab8a-b8df325351d2" selected
   Name       |UUID                                |User                                |Organization|Status
   -----------|------------------------------------|------------------------------------|------------|-------
   lucid_kirch|57c917c8-d979-481e-ae4c-8d8b9ffb2d10|00000000-0000-0000-0000-000000000000|default     |created

Note that instead of passing ``--workflow`` argument, we can define a new
environment variable ``REANA_WORKON`` which specifies the workflow we are
currently working on:

.. code-block:: console

   $ export REANA_WORKON="57c917c8-d979-481e-ae4c-8d8b9ffb2d10"

Let us upload our code:

.. code-block:: console

   $ reana-client code upload helloworld.py
   [INFO] REANA Server URL ($REANA_SERVER_URL) is: http://192.168.99.100:31201
   [INFO] Workflow "57c917c8-d979-481e-ae4c-8d8b9ffb2d10" selected
   Uploading helloworld.py ...
   File helloworld.py was successfully uploaded.

and check whether it indeed appears seeded in our workspace:

.. code-block:: console

   $ reana-client code list
   [INFO] REANA Server URL ($REANA_SERVER_URL) is: http://192.168.99.100:31201
   Name         |Size|Last-Modified
   -------------|----|--------------------------------
   helloworld.py|2905|2018-01-25 16:34:59.448513+00:00

Similarly, let us now upload the input data file:

.. code-block:: console

   $ reana-client inputs upload names.txt
   [INFO] REANA Server URL ($REANA_SERVER_URL) is: http://192.168.99.100:31201
   [INFO] Workflow "57c917c8-d979-481e-ae4c-8d8b9ffb2d10" selected
   Uploading names.txt ...
   File names.txt was successfully uploaded.

and check whether it was well seeded in our input workspace:

.. code-block:: console

   $ reana-client inputs list
   [INFO] REANA Server URL ($REANA_SERVER_URL) is: http://192.168.99.100:31201
   Name     |Size|Last-Modified
   ---------|----|--------------------------------
   names.txt|18  |2018-01-25 16:34:21.888813+00:00

Now that the input data and code was uploaded, we can start the workflow execution:

.. code-block:: console

   $ reana-client workflows start
   [INFO] REANA Server URL ($REANA_SERVER_URL) is: http://192.168.99.100:31201
   [INFO] Workflow `57c917c8-d979-481e-ae4c-8d8b9ffb2d10` selected
   Workflow `57c917c8-d979-481e-ae4c-8d8b9ffb2d10` has been started.
   [INFO] Connecting to http://192.168.99.100:31201
   {u'status': u'running', u'organization': u'default', u'message': u'Workflow successfully launched', u'user': u'00000000-0000-0000-0000-000000000000', u'workflow_id': u'57c917c8-d979-481e-ae4c-8d8b9ffb2d10'}
   Workflow `57c917c8-d979-481e-ae4c-8d8b9ffb2d10` has been started.

Let us enquire about its running status; we may see that it is still in the
"running" state:

.. code-block:: console

   $ reana-client workflows status
   [INFO] REANA Server URL ($REANA_SERVER_URL) is: http://192.168.99.100:31201
   [INFO] Workflow "afbbf6d1-a129-4e4f-ab8a-b8df325351d2" selected
   Name       |UUID                                |User                                |Organization|Status
   -----------|------------------------------------|------------------------------------|------------|-------
   lucid_kirch|57c917c8-d979-481e-ae4c-8d8b9ffb2d10|00000000-0000-0000-0000-000000000000|default     |running

                After a few minutes, the workflow should be finished:

After the workflow execution successfully finished:

.. code-block:: console

   $ reana-client workflows status
   [INFO] REANA Server URL ($REANA_SERVER_URL) is: http://192.168.99.100:31201
   [INFO] Workflow "afbbf6d1-a129-4e4f-ab8a-b8df325351d2" selected
   Name       |UUID                                |User                                |Organization|Status
   -----------|------------------------------------|------------------------------------|------------|-------
   lucid_kirch|57c917c8-d979-481e-ae4c-8d8b9ffb2d10|00000000-0000-0000-0000-000000000000|default     |finished

We can now check the output files:

.. code-block:: console

   $ reana-client outputs list --workflow 57c917c8-d979-481e-ae4c-8d8b9ffb2d10
   [INFO] REANA Server URL ($REANA_SERVER_URL) is: http://192.168.99.100:31201
   [INFO] Workflow "57c917c8-d979-481e-ae4c-8d8b9ffb2d10" selected
   Name                                 |Size|Last-Modified
   -------------------------------------|----|--------------------------------
   helloworld/greetings.txt             |32  |2018-01-25 16:36:00.582813+00:00
   _yadage/yadage_snapshot_backend.json |590 |2018-01-25 16:36:00.582813+00:00
   _yadage/yadage_snapshot_workflow.json|7668|2018-01-25 16:36:00.582813+00:00
   _yadage/yadage_template.json         |1070|2018-01-25 16:36:00.582813+00:00

and retrieve the output file result:

.. code-block:: console

   $ reana-client outputs download helloworld/greetings.txt
   [INFO] REANA Server URL ($REANA_SERVER_URL) is: http://192.168.99.100:31201
   [INFO] helloworld/greetings.txt binary file downloaded ... writing to ./outputs/
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

- Looking for a more comprehensive user manual? See :ref:`userguide`
- Looking for tips how to develop REANA-Client component? See :ref:`developerguide`
- Looking for command-line API reference? See :ref:`cliapi`
