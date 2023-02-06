..
   SPDX-FileCopyrightText: Copyright DB Netz AG and the capella-rm-bridge contributors
   SPDX-License-Identifier: Apache-2.0

*****************************
Welcome to the documentation!
*****************************

Capella-RM-Bridge
=================

.. image:: https://img.shields.io/badge/code%20style-black-000000.svg
    :target: https://github.com/psf/black
    :alt: Black

**Date**: |today| **Version**: |Version|

This library was designed to enable and support outsourcing requirements
management for Capella_ models via specific RM tools like `Codebeamer`_ or
SIEMENS' `Polarion`_. So all this library does is, based on an exported
:ref:`snapshot <snapshot>` from the RM software calculating a :ref:`ChangeSet
<change-set>`. This ChangeSet can then be applied to a
:external:class:`~capellambse.model.MelodyModel` instance from the
`capellambse`_ headless model API.

It is essential for a safe **synchronization process of ReqIFElements** from
any RM tool to Capella via `capellambse`_.

.. diagram:: [LAB] Just Architecture

.. toctree::
   :hidden:
   :maxdepth: 2
   :caption: Input

   snapshot


.. toctree::
   :hidden:
   :maxdepth: 2
   :caption: Output

   changeset

.. toctree::
   :hidden:
   :maxdepth: 3
   :caption: API reference

   code/modules


.. _Capella: https://www.eclipse.org/capella/
.. _Codebeamer: https://codebeamer.com/
.. _Polarion: https://polarion.plm.automation.siemens.com/
.. _capellambse: https://github.com/DSD-DBS/py-capellambse
