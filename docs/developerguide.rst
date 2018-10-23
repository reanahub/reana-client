.. _developerguide:

Developer guide
===============

Using latest ``reana-client`` version
-------------------------------------

If you want to use the latest bleeding-edge version of ``reana-client``, without
cloning it from GitHub, you can use:

.. code-block:: console

    $ # create new virtual environment
    $ virtualenv ~/.virtualenvs/myreana
    $ source ~/.virtualenvs/myreana/bin/activate
    $ # install reana-commons and reana-client
    $ pip install git+git://github.com/reanahub/reana-commons.git@master#egg=reana-commons
    $ pip install git+git://github.com/reanahub/reana-client.git@master#egg=reana-client
