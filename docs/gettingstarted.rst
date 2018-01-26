.. _gettingstarted:

Getting Started
===============

Install REANA client
--------------------

If you are a researcher that is interested in running analyses on the REANA
cloud, all you need to install is the ``reana-client``:

.. code-block:: console

   $ pip install \
     -e 'git+https://github.com/reanahub/reana-client.git@master#egg=reana-client'

Select REANA cloud
------------------

You can now select the REANA cloud instance where to run your analyses by
setting the ``REANA_SERVER_URL`` variable appropriately. For example:

.. code-block:: console

   $ export REANA_SERVER_URL=http://reana.cern.ch

Run example analysis
--------------------

You can use ``reana-client`` as follows:

**FIXME**
