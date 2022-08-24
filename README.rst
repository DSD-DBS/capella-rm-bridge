..
   SPDX-FileCopyrightText: Copyright DB Netz AG and the rm-bridge contributors
   SPDX-License-Identifier: Apache-2.0

Capella/RM-Bridge
=================

.. image:: https://github.com/DSD-DBS/rm-bridge/actions/workflows/build-test-publish.yml/badge.svg

.. image:: https://github.com/DSD-DBS/rm-bridge/actions/workflows/lint.yml/badge.svg

Sync requirements from different ALM tools from and back to Capella

Documentation
-------------

Read the `full documentation on Github pages`__.

__ https://dsd-dbs.github.io/rm-bridge

Installation
------------

You can install the latest released version directly from PyPI.

.. code::

    pip install rm-bridge

To set up a development environment, clone the project and install it into a
virtual environment.

.. code::

    git clone https://github.com/DSD-DBS/rm-bridge
    cd rm-bridge
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
