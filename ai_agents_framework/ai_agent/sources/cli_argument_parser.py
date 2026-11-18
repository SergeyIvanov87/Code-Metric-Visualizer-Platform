#!/usr/bin/env python3
"""Argument parsing helpers for filesystem-API command processors."""

import argparse


class ArgumentParsingError(ValueError):
    """Raised when command-line arguments do not satisfy a parser contract."""


class RaisingArgumentParser(argparse.ArgumentParser):
    """Raise a catchable exception instead of terminating on invalid arguments."""

    def error(self, message):
        raise ArgumentParsingError(message)
