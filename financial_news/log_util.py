#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Module-level logging helper.

Each financial_news module gets its own named logger with its own log file,
so logs no longer collide into whichever module called logging.basicConfig()
first (basicConfig only applies once, to the root logger).
"""
import os
import logging


def get_logger(name, log_file):
    logger = logging.getLogger(name)
    if not logger.handlers:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        handler = logging.FileHandler(log_file, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger
