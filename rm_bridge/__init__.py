# SPDX-FileCopyrightText: Copyright DB Netz AG and the rm-bridge contributors
# SPDX-License-Identifier: Apache-2.0

"""The rm_bridge package."""
from importlib import metadata

try:
    __version__ = metadata.version("rm_bridge")
except metadata.PackageNotFoundError:
    __version__ = "0.0.0+unknown"
del metadata
