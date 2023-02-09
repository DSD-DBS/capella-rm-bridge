..
   SPDX-FileCopyrightText: Copyright DB Netz AG and the capella-rm-bridge contributors
   SPDX-License-Identifier: Apache-2.0

Capellambse RM-Bridge
=====================

.. image:: https://img.shields.io/pypi/pyversions/capella-rm-bridge
   :target: https://pypi.org/project/capella-rm-bridge/
   :alt: PyPI - Python Version

.. image:: https://github.com/DSD-DBS/capella-rm-bridge/actions/workflows/build-test-publish.yml/badge.svg
    :target: https://github.com/DSD-DBS/capella-rm-bridge/actions/workflows/build-test-publish.yml/badge.svg

.. image:: https://github.com/DSD-DBS/capella-rm-bridge/actions/workflows/lint.yml/badge.svg
    :target: https://github.com/DSD-DBS/capella-rm-bridge/actions/workflows/lint.yml/badge.svg

.. image:: https://img.shields.io/github/license/DSD-DBS/capella-rm-bridge
   :target: LICENSES/Apache-2.0.txt
   :alt: License

.. image:: https://api.reuse.software/badge/github.com/DSD-DBS/capella-rm-bridge
   :target: https://api.reuse.software/info/github.com/DSD-DBS/capella-rm-bridge
   :alt: REUSE status

.. image:: https://img.shields.io/badge/code%20style-black-000000.svg
   :target: https://github.com/psf/black

.. image:: https://img.shields.io/badge/%20imports-isort-%231674b1?style=flat&labelColor=ef8336
   :target: https://pycqa.github.io/isort/


Sync requirements from different ALM tools from and back to Capella

Documentation
-------------

Read the `full documentation on Github pages`__.

__ https://dsd-dbs.github.io/capella-rm-bridge

Installation
------------

You can install the latest released version directly from PyPI.

.. code::

    pip install capella-RM-Bridge

To set up a development environment, clone the project and install it into a
virtual environment.

.. code::

    git clone https://github.com/DSD-DBS/capella-rm-bridge
    cd capella-rm-bridge
    python -m venv .venv

    source .venv/bin/activate.sh  # for Linux / Mac
    .venv\Scripts\activate  # for Windows

    pip install -U pip pre-commit
    pip install -e '.[docs,test]'
    pre-commit install

Contributing
------------

We'd love to see your bug reports and improvement suggestions! Please take a
look at our `guidelines for contributors <CONTRIBUTING.rst>`__ for details.

Licenses
--------

This project is compliant with the `REUSE Specification Version 3.0`__.

__ https://git.fsfe.org/reuse/docs/src/commit/d173a27231a36e1a2a3af07421f5e557ae0fec46/spec.md

Copyright DB Netz AG, licensed under Apache 2.0 (see full text in `<LICENSES/Apache-2.0.txt>`__)

Dot-files are licensed under CC0-1.0 (see full text in `<LICENSES/CC0-1.0.txt>`__)
