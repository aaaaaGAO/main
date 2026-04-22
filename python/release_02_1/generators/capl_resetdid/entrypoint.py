#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ResetDid 入口模块（转发到 capl_didinfo）。"""

from generators.capl_didinfo.entrypoint import (
    run_generation,
    run_generation_workflow,
)

__all__ = [
    "run_generation_workflow",
    "run_generation",
]
