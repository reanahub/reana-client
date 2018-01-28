.. _userguide:

User guide
==========

Environment variables
---------------------

REANA_SERVER_URL
~~~~~~~~~~~~~~~~

Permits to specify to which REANA cloud instance the client should connect. For
example:

.. code-block:: console

   $ export REANA_SERVER_URL=http://reana.cern.ch

REANA_WORKON
~~~~~~~~~~~~

Permits to specify a concrete workflow ID run for the given analysis. (As an
alternative to specifying ``--workflow-id`` in commands.) For example:

.. code-block:: console

   $ export REANA_WORKON="57c917c8-d979-481e-ae4c-8d8b9ffb2d10"

Examples
--------

You can get inspiration on how to structure your REANA-compatible research data
analysis from several ``reana-demo-...`` examples provided on GitHub:

- `reana-demo-helloworld <https://github.com/reanahub/reana-demo-helloworld/>`_
- `reana-demo-worldpopulation <https://github.com/reanahub/reana-demo-worldpopulation/>`_
- `reana-demo-root6-roofit <https://github.com/reanahub/reana-demo-root6-roofit/>`_

Commands
--------

The full list of ``reana-client`` commands with their documented options is
available in :`cliapi`.
