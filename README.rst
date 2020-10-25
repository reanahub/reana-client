############
REANA-Client
############

.. image:: https://img.shields.io/pypi/pyversions/reana-client.svg
   :target: https://pypi.org/pypi/reana-client

.. image:: https://github.com/reanahub/reana-client/workflows/CI/badge.svg
   :target: https://github.com/reanahub/reana-client/actions

.. image:: https://readthedocs.org/projects/reana-client/badge/?version=latest
   :target: https://reana-client.readthedocs.io/en/latest/?badge=latest

.. image:: https://codecov.io/gh/reanahub/reana-client/branch/master/graph/badge.svg
   :target: https://codecov.io/gh/reanahub/reana-client

.. image:: https://badges.gitter.im/Join%20Chat.svg
   :target: https://gitter.im/reanahub/reana?utm_source=badge&utm_medium=badge&utm_campaign=pr-badge

.. image:: https://img.shields.io/github/license/reanahub/reana.svg
   :target: https://github.com/reanahub/reana-client/blob/master/LICENSE

.. image:: https://img.shields.io/badge/code%20style-black-000000.svg
   :target: https://github.com/psf/black

About
=====

REANA-Client is a component of the `REANA <http://www.reana.io/>`_ reusable and
reproducible research data analysis platform. It provides a command-line tool
that allows researchers to submit, run, and manage their computational
workflows.

- seed workspace with input code and data
- run computational workflows on remote compute clouds
- list submitted workflows and enquire about their statuses
- download results of finished workflows


Installation
============

.. code-block:: console

   $ # create new virtual environment
   $ virtualenv ~/.virtualenvs/reana
   $ source ~/.virtualenvs/reana/bin/activate
   $ # install reana-client
   $ pip install reana-client

Usage
=====

The detailed information on how to install and use REANA can be found in
`docs.reana.io <https://docs.reana.io>`_.


Useful links
============

- `REANA project home page <http://www.reana.io/>`_
- `REANA user documentation <https://docs.reana.io>`_
- `REANA user support forum <https://forum.reana.io>`_

- `REANA-Client releases <https://reana-client.readthedocs.io/en/latest#changes>`_
- `REANA-Client developer documentation <https://reana-client.readthedocs.io/>`_
- `REANA-Client known issues <https://github.com/reanahub/reana-client/issues>`_
- `REANA-Client source code <https://github.com/reanahub/reana-client>`_
