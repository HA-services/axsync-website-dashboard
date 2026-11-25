from odoo import _, http
from odoo.exceptions import AccessError, UserError
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal

from ..models.compat import current_website


def _visible_dashboards():
    """Published dashboards the current visitor may see on the current website."""
    website = current_website(request.env)
    dashboards = request.env['axs.dashboard'].sudo().search([('website_published', '=', True)])
    user = request.env.user
    return dashboards.filtered(lambda d: d._can_view_website(user, website))


class AxsDashboardController(http.Controller):

    @http.route(['/dashboards'], type='http', auth='public', website=True, sitemap=True)
    def dashboards(self, **kw):
        return request.render('axs_website_dashboard.dashboard_index', {
            'dashboards': _visible_dashboards(),
        })

    @http.route(['/dashboards/<string:ref>'], type='http', auth='public', website=True, sitemap=False)
    def dashboard_page(self, ref, **kw):
        try:
            dashboard_id = int(ref.rsplit('-', 1)[-1])
        except ValueError:
            raise request.not_found()
        dashboard = request.env['axs.dashboard'].sudo().browse(dashboard_id).exists()
        website = current_website(request.env)
        if not dashboard or not dashboard.active or not dashboard.website_published:
            raise request.not_found()
        if not dashboard._can_view_website(request.env.user, website):
            if request.env.user._is_public():
                return request.redirect('/web/login?redirect=%s' % request.httprequest.path)
            raise request.not_found()
        return request.render('axs_website_dashboard.dashboard_page', {
            'dashboard': dashboard,
            'main_object': dashboard,
        })

    @http.route('/axs_dashboard/data', type='jsonrpc', auth='public', website=True)
    def dashboard_data(self, dashboard_id, channel='website', date_filter=None, date_from=None, date_to=None,
                       item_ids=None, drill=None, pages=None, **kw):
        dashboard = request.env['axs.dashboard'].browse(int(dashboard_id))
        if not dashboard.sudo().exists():
            return {'error': _("This dashboard does not exist anymore.")}
        if channel == 'backend' and request.env.user._is_public():
            channel = 'website'
        try:
            return dashboard._payload(channel if channel in ('website', 'backend') else 'website',
                                      date_filter=date_filter, date_from=date_from, date_to=date_to,
                                      item_ids=[int(i) for i in item_ids or []] or None,
                                      drill=drill if isinstance(drill, dict) else None,
                                      pages=pages if isinstance(pages, dict) else None)
        except AccessError:
            return {'error': _("You are not allowed to see this dashboard."), 'access': False}

    @http.route('/axs_dashboard/layout', type='jsonrpc', auth='user')
    def dashboard_layout(self, dashboard_id, layout, **kw):
        dashboard = request.env['axs.dashboard'].browse(int(dashboard_id)).exists()
        if not dashboard:
            raise UserError(_("This dashboard does not exist anymore."))
        return dashboard.save_layout(layout)

    @http.route('/axs_dashboard/todo', type='jsonrpc', auth='user')
    def dashboard_todo(self, todo_id, done, **kw):
        todo = request.env['axs.dashboard.todo'].browse(int(todo_id)).exists()
        if not todo:
            raise UserError(_("This task does not exist anymore."))
        dashboard = todo.item_id.dashboard_id
        if not dashboard._is_manager():
            raise AccessError(_("Only dashboard managers can update tasks."))
        todo.done = bool(done)
        return True


class AxsDashboardPortal(CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)  # up to Odoo 19
        if 'axs_dashboard_count' in counters:
            values['axs_dashboard_count'] = len(_visible_dashboards().filtered('show_in_portal'))
        return values

    def _prepare_portal_counter_values(self, counter):
        # Odoo 20: portal cards ask each counter for (model, domain, access)
        if counter == 'axs_dashboard_count':
            ids = _visible_dashboards().filtered('show_in_portal').ids
            return 'axs.dashboard', [('id', 'in', ids)], 'sudo'
        return super()._prepare_portal_counter_values(counter)
