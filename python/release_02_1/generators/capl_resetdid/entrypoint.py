#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ResetDid 入口模块（兼容转发到 capl_didinfo）。"""

from generators.capl_didinfo.entrypoint import (
    execute_workflow,
    main,
    run_generation,
    run_generation_workflow,
)

__all__ = [
    "run_generation_workflow",
    "main",
    "run_generation",
    "execute_workflow",
]
