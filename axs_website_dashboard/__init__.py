from . import controllers
from . import models


def _uninstall_hook(*args):
    """Remove the menus and actions generated for the dashboards (``(cr, registry)`` on Odoo 16, ``env`` after)."""
    from odoo import api, SUPERUSER_ID
    env = args[0] if len(args) == 1 else api.Environment(args[0], SUPERUSER_ID, {})
    dashboards = env['axs.dashboard'].with_context(active_test=False).search([])
    (dashboards.mapped('menu_id')).unlink()
    (dashboards.mapped('action_id')).unlink()
    (dashboards.mapped('website_menu_id')).unlink()
