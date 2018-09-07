.. _developerguide:

Developer guide
===============

Using latest ``reana-client`` version
-------------------------------------

If you want to use the latest bleeding-edge version of ``reana-client``, without
cloning it from GitHub, you can use:

.. code-block:: console

    $ mkvirtualenv reana-client-latest
    $ pip install git+git://github.com/reanahub/reana-commons.git@master#egg=reana-commons
    $ pip install git+git://github.com/reanahub/reana-client.git@master#egg=reana-client
