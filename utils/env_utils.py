# utils/env_utils.py

"""
Module: env_utils
Description: Provides utility functions for safely loading environment variables.
Author: Roberto Toapanta
Date: 2025-06-27
License: MIT
"""

import os


def get_env_variable(name: str, default=None, required: bool = False) -> str:
    """
    Returns the value of an environment variable.

    Args:
        name (str): Name of the environment variable to retrieve.
        default (Any): Optional default value to return if variable is not set.
        required (bool): If True, raises an error if the variable is not set.

    Returns:
        str: Value of the environment variable or default value.

    Raises:
        EnvironmentError: If the variable is required but not defined.
    """
    value = os.getenv(name, default)
    if required and value is None:
        raise EnvironmentError(f"Missing required environment variable: {name}")
    return value
