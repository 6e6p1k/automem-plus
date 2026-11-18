"""Where the plugin keeps its own files, and the switch that turns every hook off."""

import os

from automem import constants


def disabled():
    return bool(os.environ.get(constants.DISABLE_ENV))


def state_dir():
    """Machine-local state: the usage log, sync bases, backups. Never synced."""
    path = os.path.expanduser(os.environ.get(constants.STATE_ENV) or constants.DEFAULT_STATE_DIR)
    os.makedirs(path, exist_ok=True)
    return path


def store_dir():
    """The git repo that carries notes between machines."""
    return os.path.expanduser(os.environ.get(constants.STORE_ENV) or constants.DEFAULT_STORE_DIR)
