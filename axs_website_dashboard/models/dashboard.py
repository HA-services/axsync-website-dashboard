import json

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from .compat import MAJOR, current_website, slug
from .date_filters import DATE_FILTERS

THEMES = [
    ('axsync', 'AXSync'),
    ('ocean', 'Ocean'),
    ('sunset', 'Sunset'),
    ('forest', 'Forest'),
    ('berry', 'Berry'),
    ('mono', 'Monochrome'),
]
EXPORT_ITEM_FIELDS = [
    'sequence', 'name', 'description', 'item_type', 'domain', 'date_filter_mode', 'fixed_date_filter',
    'measure_type', 'group_interval', 'series_interval', 'drill_interval', 'sort_order', 'limit', 'show_others',
    'multiplier', 'decimals', 'number_format', 'prefix', 'suffix', 'show_values', 'show_legend', 'cumulative',
    'target_value', 'show_percent', 'icon', 'tile_style', 'color', 'kpi_comparison', 'list_order_desc',
    'page_size', 'content', 'link_url', 'open_records', 'grid_x', 'grid_y', 'grid_w', 'grid_h',
]
EXPORT_ITEM_FIELD_REFS = ['date_field_id', 'measure_field_id', 'group_field_id', 'series_field_id',
                          'drill_field_id', 'list_order_field_id']


class AxsDashboard(models.Model):
    _name = 'axs.dashboard'
    _description = 'Dashboard'
    _order = 'sequence, name, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    description = fields.Text(translate=True)
    color = fields.Integer('Color Index')
    company_id = fields.Many2one('res.company', 'Company', help="Leave empty to share the dashboard between companies.")
    user_id = fields.Many2one('res.users', 'Responsible', default=lambda self: self.env.user)
    item_ids = fields.One2many('axs.dashboard.item', 'dashboard_id', 'Items', copy=True)
    item_count = fields.Integer(compute='_compute_item_count')

    # display
    theme = fields.Selection(THEMES, default='axsync', required=True)
    show_date_filter = fields.Boolean('Show Date Filter', default=True)
    date_filter = fields.Selection(DATE_FILTERS, 'Default Period', default='this_year', required=True)
    refresh_interval = fields.Integer('Auto Refresh (seconds)', default=0,
                                      help="Reload the data automatically. 0 disables it, the minimum is 15 seconds.")

    # back end
    group_ids = fields.Many2many('res.groups', 'axs_dashboard_group_rel', 'dashboard_id', 'group_id',
                                 'Back-end Access', help="Internal users of these groups can open the dashboard "
                                                         "in the back end. Leave empty for all dashboard users.")
    backend_menu = fields.Boolean('Back-end Menu', help="Add a menu entry that opens this dashboard.")
    menu_parent_id = fields.Many2one('ir.ui.menu', 'Parent Menu',
                                     default=lambda self: self.env.ref('axs_website_dashboard.menu_dashboard_root',
                                                                       raise_if_not_found=False))
    menu_id = fields.Many2one('ir.ui.menu', 'Menu', readonly=True, copy=False)
    action_id = fields.Many2one('ir.actions.client', 'Action', readonly=True, copy=False)

    # website
    website_published = fields.Boolean('Published on Website', copy=False)
    website_id = fields.Many2one('website', 'Website', ondelete='set null',
                                 help="Restrict the dashboard to one website. Leave empty for all websites.")
    website_visibility = fields.Selection([
        ('public', 'Everyone'),
        ('signed_in', 'Signed-in users'),
        ('groups', 'Selected groups'),
    ], 'Website Visibility', default='signed_in', required=True)
    website_group_ids = fields.Many2many('res.groups', 'axs_dashboard_website_group_rel', 'dashboard_id', 'group_id',
                                         'Website Groups', help="Users of these groups can see the dashboard on the "
                                                                "website (for example Portal).")
    data_scope = fields.Selection([
        ('viewer', "Viewer's data"),
        ('shared', 'All data (shared)'),
    ], 'Data Shown', default='viewer', required=True,
        help="Viewer's data: each visitor sees what their own access rights allow.\n"
             "All data: every visitor sees the figures computed with the access rights of the Data User.")
    data_user_id = fields.Many2one('res.users', 'Data User', default=lambda self: self._default_data_user(),
                                   domain="[('share', '=', False)]",
                                   help="Internal user whose access rights compute the shared data.")
    website_menu = fields.Boolean('Website Menu', help="Add the dashboard to the website menu.")
    website_menu_id = fields.Many2one('website.menu', 'Website Menu Entry', readonly=True, copy=False)
    show_in_portal = fields.Boolean('Show in My Account', default=True,
                                    help="List the dashboard on the customer portal home page.")
    website_url = fields.Char(compute='_compute_website_url')
    embed_code = fields.Char(compute='_compute_website_url')

    @api.model
    def _default_data_user(self):
        user = self.env.user
        if user.active and not user.share:
            return user
        return self.env.ref('base.user_admin', raise_if_not_found=False)

    def _compute_item_count(self):
        for dashboard in self:
            dashboard.item_count = len(dashboard.item_ids)

    @api.depends('name')
    def _compute_website_url(self):
        for dashboard in self:
            if dashboard.id:
                dashboard.website_url = '/dashboards/%s' % slug(dashboard)
                dashboard.embed_code = '<div data-axs-dashboard="%s"></div>' % dashboard.id
            else:
                dashboard.website_url = dashboard.embed_code = False

    @api.constrains('refresh_interval', 'data_scope', 'data_user_id')
    def _check_settings(self):
        for dashboard in self:
            if dashboard.refresh_interval and dashboard.refresh_interval < 15:
                raise ValidationError(_("The automatic refresh interval must be at least 15 seconds."))
            if dashboard.refresh_interval < 0:
                raise ValidationError(_("The automatic refresh interval cannot be negative."))
            if dashboard.data_scope == 'shared' and dashboard.data_user_id.share:
                raise ValidationError(_("The data user must be an internal user."))

    # ------------------------------------------------------------------ CRUD and generated objects
    @api.model_create_multi
    def create(self, vals_list):
        dashboards = super().create(vals_list)
        dashboards._sync_menus()
        return dashboards

    def write(self, vals):
        res = super().write(vals)
        if {'name', 'sequence', 'active', 'backend_menu', 'menu_parent_id', 'group_ids', 'website_menu',
                'website_published', 'website_id'} & set(vals):
            self._sync_menus()
        return res

    def unlink(self):
        menus = self.mapped('menu_id')
        actions = self.mapped('action_id')
        website_menus = self.mapped('website_menu_id')
        res = super().unlink()
        menus.sudo().unlink()
        actions.sudo().unlink()
        website_menus.sudo().unlink()
        return res

    def copy(self, default=None):
        default = dict(default or {})
        if len(self) == 1:
            default.setdefault('name', _("%s (copy)", self.name))
        return super().copy(default)

    def _sync_menus(self):
        groups_field = 'group_ids' if 'group_ids' in self.env['ir.ui.menu']._fields else 'groups_id'
        for dashboard in self.sudo():
            # back-end client action and menu
            if dashboard.backend_menu and dashboard.active:
                if not dashboard.action_id:
                    dashboard.action_id = self.env['ir.actions.client'].create({
                        'name': dashboard.name,
                        'tag': 'axs_website_dashboard.dashboard',
                        'params': {'dashboard_id': dashboard.id},
                    })
                else:
                    dashboard.action_id.name = dashboard.name
                groups = dashboard.group_ids or self.env.ref('axs_website_dashboard.group_dashboard_user')
                menu_vals = {
                    'name': dashboard.name,
                    'parent_id': dashboard.menu_parent_id.id,
                    'sequence': dashboard.sequence,
                    'action': 'ir.actions.client,%s' % dashboard.action_id.id,
                    groups_field: [(6, 0, groups.ids)],
                    'active': True,
                }
                if dashboard.menu_id:
                    dashboard.menu_id.write(menu_vals)
                else:
                    dashboard.menu_id = self.env['ir.ui.menu'].create(menu_vals)
            elif dashboard.menu_id:
                dashboard.menu_id.active = False
            # website menu
            if dashboard.website_menu and dashboard.website_published and dashboard.active:
                website = dashboard.website_id or self.env['website'].search([], limit=1)
                if not website:
                    continue
                vals = {'name': dashboard.name, 'url': '/dashboards/%s' % slug(dashboard),
                        'website_id': website.id, 'sequence': 60 + dashboard.sequence}
                if dashboard.website_menu_id:
                    dashboard.website_menu_id.write(vals)
                else:
                    vals['parent_id'] = website.menu_id.id
                    dashboard.website_menu_id = self.env['website.menu'].create(vals)
            elif dashboard.website_menu_id:
                menu = dashboard.website_menu_id
                dashboard.website_menu_id = False
                menu.unlink()

    # ------------------------------------------------------------------ access
    def _is_manager(self, user=None):
        user = user or self.env.user
        return user.has_group('axs_website_dashboard.group_dashboard_manager')

    def _can_view_backend(self, user=None):
        self.ensure_one()
        user = user or self.env.user
        if user.share or not self.active:
            return False
        if not user.has_group('axs_website_dashboard.group_dashboard_user'):
            return False
        if self.company_id and self.company_id not in user.company_ids:
            return False
        return self._is_manager(user) or not self.group_ids or bool(self.group_ids & user.groups_id_compat())

    def _can_view_website(self, user=None, website=None):
        self.ensure_one()
        user = user or self.env.user
        if not (self.active and self.website_published):
            return False
        if website and self.website_id and self.website_id != website:
            return False
        if self.company_id and website and website.company_id != self.company_id:
            return False
        if self.website_visibility == 'public':
            return True
        if user._is_public():
            return False
        if self.website_visibility == 'signed_in':
            return True
        return bool(self.website_group_ids & user.groups_id_compat())

    def _data_env(self, channel):
        """Environment used to compute the figures: the viewer, or the shared data user."""
        self.ensure_one()
        env = self.env
        user = env.user
        if self.data_scope == 'shared':
            user = self.data_user_id or self.user_id
            if not user or user.share or not user.active:
                raise AccessError(_("The data user of this dashboard is not available."))
        companies = user.company_ids
        if self.company_id:
            company = self.company_id
            companies = company
        elif user == env.user and channel == 'backend':
            company = env.company
            companies = env.companies
        else:
            website = current_website(env) if channel == 'website' else False
            company = website.company_id if website and website.company_id in user.company_ids else user.company_id
            companies = company | (user.company_ids & company)
        context = dict(env.context, allowed_company_ids=(company | companies).ids,
                       tz=env.context.get('tz') or env.user.tz or user.tz)
        return env(user=user.id, context=context, su=False)

    # ------------------------------------------------------------------ front-end payload
    def _payload(self, channel, date_filter=None, date_from=None, date_to=None, item_ids=None, drill=None,
                 pages=None):
        """Configuration and data of the dashboard, for the website or the back end."""
        self.ensure_one()
        user = self.env.user
        dashboard = self.sudo()
        allowed = dashboard._can_view_backend(user) if channel == 'backend' else dashboard._can_view_website(
            user, current_website(self.env))
        if not allowed:
            raise AccessError(_("You are not allowed to see this dashboard."))
        filter_keys = [k for k, _label in DATE_FILTERS]
        key = date_filter if date_filter in filter_keys else dashboard.date_filter
        data_env = dashboard._data_env(channel)
        tz = data_env.context.get('tz') or 'UTC'
        today = fields.Date.context_today(dashboard.with_context(tz=tz))
        period = {'key': key, 'from': date_from, 'to': date_to, 'today': today, 'tz': tz}
        items = dashboard.item_ids
        if item_ids:
            items = items.filtered(lambda i: i.id in item_ids)
        drill = drill or {}
        pages = pages or {}
        backend = channel == 'backend'
        items_payload = []
        for item in items.with_context(tz=tz, lang=self.env.lang):
            conf = item._config_payload()
            conf['data'] = item._data_payload(data_env, period, drill=drill.get(str(item.id)),
                                              page=pages.get(str(item.id), 0), backend=backend)
            items_payload.append(conf)
        manager = backend and dashboard._is_manager(user)
        lang = self.env['res.lang']._lang_get(self.env.lang or 'en_US') if hasattr(
            self.env['res.lang'], '_lang_get') else False
        return {
            'id': dashboard.id,
            'name': dashboard.with_context(lang=self.env.lang).name,
            'description': dashboard.with_context(lang=self.env.lang).description or '',
            'theme': dashboard.theme,
            'show_date_filter': dashboard.show_date_filter,
            'date_filter': key,
            'date_from': date_from or False,
            'date_to': date_to or False,
            'date_filters': [{'key': k, 'label': label} for k, label in
                             self.env['axs.dashboard']._fields['date_filter']._description_selection(self.env)],
            'refresh_interval': dashboard.refresh_interval if dashboard.refresh_interval >= 15 else 0,
            'can_edit': manager,
            'website_url': dashboard.website_url if dashboard.website_published else False,
            'lang': (self.env.lang or 'en_US').replace('_', '-'),
            'thousands_sep': lang.thousands_sep if lang else ',',
            'decimal_point': lang.decimal_point if lang else '.',
            'today': today.isoformat(),
            'items': items_payload,
        }

    @api.model
    def get_backend_payload(self, dashboard_id, **kwargs):
        """RPC entry point of the back-end client action."""
        return self.browse(int(dashboard_id)).exists()._payload('backend', **kwargs)

    def save_layout(self, layout):
        """Store the positions of the items: ``[{'id', 'x', 'y', 'w', 'h'}]``."""
        self.ensure_one()
        if not self._is_manager():
            raise AccessError(_("Only dashboard managers can change the layout."))
        items = {item.id: item for item in self.item_ids}
        for pos in layout or []:
            item = items.get(int(pos.get('id', 0)))
            if not item:
                continue
            item.write({
                'grid_x': max(0, min(11, int(pos.get('x', 0)))),
                'grid_y': max(0, min(500, int(pos.get('y', 0)))),
                'grid_w': max(1, min(12, int(pos.get('w', 1)))),
                'grid_h': max(1, min(12, int(pos.get('h', 1)))),
            })
        return True

    # ------------------------------------------------------------------ actions
    def action_open_dashboard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'axs_website_dashboard.dashboard',
            'name': self.name,
            'params': {'dashboard_id': self.id},
        }

    def action_view_website(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_url', 'url': self.website_url, 'target': 'new'}

    def action_toggle_published(self):
        for dashboard in self:
            dashboard.website_published = not dashboard.website_published
        return True

    def action_view_items(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Items"),
            'res_model': 'axs.dashboard.item',
            'view_mode': 'list,form' if MAJOR >= 18 else 'tree,form',
            'domain': [('dashboard_id', '=', self.id)],
            'context': {'default_dashboard_id': self.id},
        }

    # ------------------------------------------------------------------ export / import
    def _export_data(self):
        data = []
        for dashboard in self:
            items = []
            for item in dashboard.item_ids:
                vals = {f: item[f] for f in EXPORT_ITEM_FIELDS}
                vals['model'] = item.model_name or False
                for f in EXPORT_ITEM_FIELD_REFS:
                    vals[f] = item[f].name or False
                vals['list_fields'] = item.list_field_ids.mapped('name')
                vals['todos'] = [{'name': t.name, 'done': t.done} for t in item.todo_ids]
                items.append(vals)
            data.append({
                'format': 'axs_website_dashboard', 'version': 1,
                'name': dashboard.name, 'description': dashboard.description or '',
                'theme': dashboard.theme, 'show_date_filter': dashboard.show_date_filter,
                'date_filter': dashboard.date_filter, 'refresh_interval': dashboard.refresh_interval,
                'website_visibility': dashboard.website_visibility, 'data_scope': dashboard.data_scope,
                'items': items,
            })
        return data

    def action_export(self):
        content = json.dumps(self._export_data(), indent=2, default=str)
        name = 'dashboards.json' if len(self) > 1 else '%s.json' % (self.name or 'dashboard').replace('/', '-')
        attachment = self.env['ir.attachment'].create({
            'name': name,
            'raw': content.encode(),
            'mimetype': 'application/json',
        })
        return {'type': 'ir.actions.act_url', 'url': '/web/content/%s?download=true' % attachment.id,
                'target': 'self'}

    @api.model
    def _import_data(self, data):
        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list):
            raise UserError(_("This file is not a dashboard export."))
        created = self.browse()
        Fields = self.env['ir.model.fields']
        IrModel = self.env['ir.model']
        for entry in data:
            if not isinstance(entry, dict) or entry.get('format') != 'axs_website_dashboard':
                raise UserError(_("This file is not a dashboard export."))
            items = []
            for vals in entry.get('items', []):
                item_vals = {f: vals[f] for f in EXPORT_ITEM_FIELDS if f in vals}
                model = vals.get('model') and IrModel._get(vals['model'])
                if vals.get('model') and not model:
                    continue  # the app of this item is not installed here
                item_vals['model_id'] = model.id if model else False
                for f in EXPORT_ITEM_FIELD_REFS:
                    field = model and vals.get(f) and Fields._get(model.model, vals[f])
                    item_vals[f] = field.id if field else False
                list_fields = [Fields._get(model.model, n) for n in vals.get('list_fields', [])] if model else []
                item_vals['list_field_ids'] = [(6, 0, [f.id for f in list_fields if f])]
                item_vals['todo_ids'] = [(0, 0, {'name': t['name'], 'done': bool(t.get('done'))})
                                         for t in vals.get('todos', []) if t.get('name')]
                items.append((0, 0, item_vals))
            created |= self.create({
                'name': entry.get('name') or _("Imported Dashboard"),
                'description': entry.get('description'),
                'theme': entry.get('theme') if entry.get('theme') in dict(THEMES) else 'axsync',
                'show_date_filter': entry.get('show_date_filter', True),
                'date_filter': entry.get('date_filter') or 'this_year',
                'refresh_interval': entry.get('refresh_interval') or 0,
                'website_visibility': entry.get('website_visibility') or 'signed_in',
                'data_scope': entry.get('data_scope') or 'viewer',
                'item_ids': items,
            })
        return created


class ResUsers(models.Model):
    _inherit = 'res.users'

    def groups_id_compat(self):
        """Groups of the user, including implied groups (``groups_id`` up to Odoo 18, ``all_group_ids`` after)."""
        self.ensure_one()
        if 'all_group_ids' in self._fields:
            return self.sudo().all_group_ids
        return self.sudo().groups_id
