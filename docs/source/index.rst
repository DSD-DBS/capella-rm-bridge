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
management for Capella_ models via specific RM tools like **Codebeamer** or
**SIEMENS' Polarion ALM**. So all this library does is calculating a
:ref:`change set <change-set>`, based on an exported :ref:`snapshot <snapshot>`
from the RM software. This change set can then be applied to a
:external:class:`~capellambse.model.MelodyModel` instance from the
`capellambse`_ headless model API.

It is essential for the **synchronization process of ReqIFElements** from any
RM tool to Capella.

.. toctree::
   :maxdepth: 2
   :caption: Input

   snapshot


.. toctree::
   :maxdepth: 2
   :caption: Output

   changeset

.. toctree::
   :maxdepth: 3
   :caption: API reference

   code/modules


.. _Capella: https://www.eclipse.org/capella/
.. _capellambse: https://github.com/DSD-DBS/py-capellambse
