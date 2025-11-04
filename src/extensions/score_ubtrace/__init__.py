# *******************************************************************************
# Copyright (c) 2025 Contributors to the Eclipse Foundation
#
# See the NOTICE file(s) distributed with this work for additional
# information regarding copyright ownership.
#
# This program and the accompanying materials are made available under the
# terms of the Apache License Version 2.0 which is available at
# https://www.apache.org/licenses/LICENSE-2.0
#
# SPDX-License-Identifier: Apache-2.0
# *******************************************************************************
from sphinx.application import Sphinx


def setup(app: Sphinx) -> dict[str, str | bool | list[str]]:
    """
    Extension to configure the ubTrace Sphinx builder.

    See https://ubtrace.useblocks.com/usage/builder.html
    """

    app.config.ubtrace_organization = "eclipse-score"
    """The organisation name for ubTrace."""

    to_replace = {" "}
    proj_id = app.config.project
    for ch in to_replace:
        proj_id = proj_id.replace(ch, "_")

    app.config.ubtrace_project = proj_id
    """The project name for ubTrace."""

    app.config.ubtrace_version = app.config.version
    """The project version for ubTrace."""

    app.setup_extension("ubt_sphinx")

    return {
        "version": "0.1",
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }
