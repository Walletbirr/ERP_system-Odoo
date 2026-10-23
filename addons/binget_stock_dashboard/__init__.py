from . import controllers
from . import models


def post_init_hook(env):
    from .hooks import post_init_hook as _hook
    _hook(env)


def uninstall_hook(env):
    from .hooks import uninstall_hook as _hook
    _hook(env)
