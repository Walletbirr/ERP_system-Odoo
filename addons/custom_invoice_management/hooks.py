# -*- coding: utf-8 -*-


def post_init_hook(env):
    """Fresh-install path. See res.company._cim_post_install_setup() for
    what this does and why the upgrade path (data/post_install_data.xml)
    is also needed alongside this.
    """
    env['res.company']._cim_post_install_setup()
