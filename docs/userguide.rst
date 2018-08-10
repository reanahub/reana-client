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

   $ export REANA_SERVER_URL=http://reana.cern.ch
   $ export REANA_ACCESS_TOKEN=<ACCESS_TOKEN>

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

Please see the :ref:`gettingstarted` section for a basic ``reana-client`` use
case scenario.

Examples
--------

You can get inspiration on how to structure your REANA-compatible research data
analysis from several ``reana-demo-...`` examples
`provided on GitHub <https://github.com/reanahub?utf8=%E2%9C%93&q=reana-demo&type=&language=>`_.

Commands
--------

The full list of ``reana-client`` commands with their documented options is
available in the :ref:`cliapi` documentation.
