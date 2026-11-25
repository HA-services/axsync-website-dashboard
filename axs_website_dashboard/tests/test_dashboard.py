import json

from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import HttpCase, TransactionCase, new_test_user

from ..models.compat import binary_input


class DashboardCase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Dashboard = cls.env['axs.dashboard']
        cls.partner_model = cls.env['ir.model']._get('res.partner')
        cls.Fields = cls.env['ir.model.fields']
        cls.be = cls.env.ref('base.be')
        cls.fr = cls.env.ref('base.fr')
        cls.partners = cls.env['res.partner'].create([
            {'name': 'AXS W1', 'country_id': cls.be.id, 'color': 2, 'type': 'invoice', 'ref': 'axsw'},
            {'name': 'AXS W2', 'country_id': cls.be.id, 'color': 3, 'ref': 'axsw'},
            {'name': 'AXS W3', 'country_id': cls.fr.id, 'color': 5, 'ref': 'axsw'},
            {'name': 'AXS W4', 'color': 7, 'ref': 'axsw'},
        ])
        cls.domain = "[('ref', '=', 'axsw')]"
        cls.manager = new_test_user(cls.env, login='axs_wd_manager',
                                    groups='base.group_user,axs_website_dashboard.group_dashboard_manager')
        cls.user = new_test_user(cls.env, login='axs_wd_user', groups='base.group_user')
        cls.portal = new_test_user(cls.env, login='axs_wd_portal', groups='base.group_portal')
        cls.admin = cls.env.ref('base.user_admin')

    def f(self, name, model='res.partner'):
        return self.Fields._get(model, name)

    def _dashboard(self, items, **vals):
        values = {'name': 'AXS Test Dashboard', 'date_filter': 'none', 'data_user_id': self.admin.id,
                  'item_ids': [(0, 0, dict(item)) for item in items]}
        values.update(vals)
        return self.Dashboard.create(values)

    def _item(self, **vals):
        base = {'name': 'Item', 'item_type': 'tile', 'model_id': self.partner_model.id, 'domain': self.domain,
                'date_filter_mode': 'none'}
        base.update(vals)
        return base

    def _data(self, dashboard, channel='backend', user=None, **kw):
        Dash = dashboard.with_user(user) if user else dashboard
        payload = Dash._payload(channel, **kw)
        return {i['name']: i['data'] for i in payload['items']}, payload


@tagged('post_install', '-at_install', 'axs_dashboard')
class TestDashboardData(DashboardCase):

    def test_tiles_and_kpis(self):
        dashboard = self._dashboard([
            self._item(name='Count'),
            self._item(name='Sum', measure_type='sum', measure_field_id=self.f('color').id, multiplier=10),
            self._item(name='Avg', measure_type='avg', measure_field_id=self.f('color').id),
            self._item(name='Max', measure_type='max', measure_field_id=self.f('color').id),
            self._item(name='KPI', item_type='kpi', date_field_id=self.f('create_date').id,
                       date_filter_mode='fixed', fixed_date_filter='this_month', target_value=8,
                       kpi_comparison='previous'),
            self._item(name='Gauge', item_type='gauge', target_value=8),
            self._item(name='Mine', domain="[('ref', '=', 'axsw'), ('create_uid', '=', uid)]"),
        ])
        data, payload = self._data(dashboard)
        self.assertEqual(data['Count']['value'], 4)
        self.assertEqual(data['Sum']['value'], 170)
        self.assertEqual(data['Avg']['value'], 4.25)
        self.assertEqual(data['Max']['value'], 7)
        self.assertEqual(data['KPI']['value'], 4)
        self.assertEqual(data['KPI']['previous'], 0)
        self.assertIsNone(data['KPI']['change'], "no change percentage when the previous period is empty")
        self.assertEqual(data['Gauge']['progress'], 50)
        self.assertEqual(data['Mine']['value'], 4)
        self.assertEqual(len(payload['date_filters']), 23)
        self.assertTrue(payload['can_edit'])

    def test_charts_grouping_limit_drill(self):
        dashboard = self._dashboard([
            self._item(name='Bar', item_type='bar', group_field_id=self.f('country_id').id,
                       measure_type='sum', measure_field_id=self.f('color').id, sort_order='value_desc',
                       drill_field_id=self.f('type').id),
            self._item(name='Top1', item_type='pie', group_field_id=self.f('country_id').id, limit=1,
                       sort_order='value_desc'),
            self._item(name='Series', item_type='stacked_bar', group_field_id=self.f('country_id').id,
                       series_field_id=self.f('type').id),
            self._item(name='Cumul', item_type='line', group_field_id=self.f('name').id, sort_order='label_asc',
                       cumulative=True),
            self._item(name='Month', item_type='area', group_field_id=self.f('create_date').id,
                       group_interval='month'),
        ])
        data, _payload = self._data(dashboard)
        bar = data['Bar']
        self.assertEqual(bar['labels'][0], 'None', "partners without country have the highest sum (7)")
        sums = dict(zip(bar['labels'], bar['datasets'][0]['values']))
        self.assertEqual(sums[self.be.name], 5)
        self.assertEqual(sums[self.fr.name], 5)
        self.assertIn('None', sums)
        self.assertTrue(bar['can_drill'])
        self.assertEqual(len(bar['group_domains']), len(bar['labels']))
        top = data['Top1']
        self.assertEqual(top['labels'], [self.be.name, 'Others'])
        self.assertEqual(top['datasets'][0]['values'], [2, 2])
        series = data['Series']
        self.assertEqual(len(series['datasets']), 2, "one dataset per address type")
        self.assertEqual(data['Cumul']['datasets'][0]['values'], [1, 2, 3, 4])
        self.assertEqual(len(data['Month']['labels']), 1)
        self.assertRegex(data['Month']['labels'][0], r'^[A-Z][a-z]{2} \d{4}$')
        # drill down into Belgium: split by company flag
        item = dashboard.item_ids.filtered(lambda i: i.name == 'Bar')
        drilled, _payload = self._data(dashboard, drill={str(item.id): [self.be.id]})
        self.assertEqual(drilled['Bar']['drill'][0]['label'], self.be.name)
        self.assertEqual(len(drilled['Bar']['labels']), 2, "Belgium split by address type")
        self.assertFalse(drilled['Bar']['can_drill'])

    def test_lists_todo_text(self):
        dashboard = self._dashboard([
            self._item(name='Rows', item_type='list', list_field_ids=[(6, 0, [self.f('name').id, self.f('country_id').id,
                                                                            self.f('color').id])],
                       list_order_field_id=self.f('name').id, list_order_desc=False, page_size=3),
            self._item(name='Grouped', item_type='list', group_field_id=self.f('country_id').id,
                       sort_order='value_desc'),
            {'name': 'Tasks', 'item_type': 'todo', 'todo_ids': [(0, 0, {'name': 'Call'}), (0, 0, {'name': 'Mail', 'done': True})]},
            {'name': 'Note', 'item_type': 'text', 'content': '<p>Hello <script>alert(1)</script></p>'},
        ])
        item = dashboard.item_ids.filtered(lambda i: i.name == 'Rows')
        data, _payload = self._data(dashboard)
        rows = data['Rows']
        self.assertEqual(rows['total'], 4)
        self.assertEqual([r['cells'][0] for r in rows['rows']], ['AXS W1', 'AXS W2', 'AXS W3'])
        self.assertEqual(rows['rows'][0]['cells'][1], self.be.display_name)
        page2, _payload = self._data(dashboard, pages={str(item.id): 1})
        self.assertEqual([r['cells'][0] for r in page2['Rows']['rows']], ['AXS W4'])
        self.assertEqual(data['Grouped']['rows'][0]['value'], 2)
        self.assertEqual([t['done'] for t in data['Tasks']['todos']], [False, True])
        self.assertNotIn('<script', data['Note']['html'])
        self.assertIn('Hello', data['Note']['html'])

    def test_date_filters(self):
        dashboard = self._dashboard([
            self._item(name='This year', date_field_id=self.f('create_date').id, date_filter_mode='dashboard'),
            self._item(name='Old', date_field_id=self.f('create_date').id, date_filter_mode='fixed',
                       fixed_date_filter='before_30_days'),
        ], date_filter='this_year')
        data, payload = self._data(dashboard)
        self.assertEqual(payload['date_filter'], 'this_year')
        self.assertEqual(data['This year']['value'], 4)
        self.assertEqual(data['Old']['value'], 0)
        data, _payload = self._data(dashboard, date_filter='last_year')
        self.assertEqual(data['This year']['value'], 0)
        data, _payload = self._data(dashboard, date_filter='custom', date_from='2000-01-01', date_to='2000-12-31')
        self.assertEqual(data['This year']['value'], 0)

    def test_broken_item_does_not_break_dashboard(self):
        dashboard = self._dashboard([self._item(name='Fine'), self._item(name='Broken')])
        broken = dashboard.item_ids.filtered(lambda i: i.name == 'Broken')
        self.env.cr.execute("UPDATE axs_dashboard_item SET domain = %s WHERE id = %s",
                            ["[('no_such_field', '=', 1)]", broken.id])
        broken.invalidate_recordset(['domain'])
        data, _payload = self._data(dashboard)
        self.assertEqual(data['Fine']['value'], 4)
        self.assertIn('error', data['Broken'])

    def test_validation(self):
        with self.assertRaises(ValidationError):
            self._dashboard([self._item(name='Chart', item_type='bar')])
        with self.assertRaises(ValidationError):
            self._dashboard([self._item(name='Sum', measure_type='sum')])
        with self.assertRaises(ValidationError):
            self._dashboard([self._item(name='Bad domain', domain="[('name', '=',")])
        with self.assertRaises(ValidationError):
            self._dashboard([self._item(name='Color', color='red')])
        with self.assertRaises(ValidationError):
            self._dashboard([self._item(name='Size', grid_w=13)])
        with self.assertRaises(ValidationError):
            self._dashboard([], refresh_interval=5)


@tagged('post_install', '-at_install', 'axs_dashboard')
class TestDashboardAccess(DashboardCase):

    def test_backend_groups(self):
        group = self.env.ref('base.group_system')
        dashboard = self._dashboard([self._item(name='Count')], group_ids=[(6, 0, group.ids)])
        with self.assertRaises(AccessError):
            dashboard.with_user(self.user)._payload('backend')
        self.assertFalse(self.Dashboard.with_user(self.user).search([('id', '=', dashboard.id)]),
                         "record rule hides the dashboard")
        data, payload = self._data(dashboard, user=self.manager)
        self.assertEqual(data['Count']['value'], 4)
        self.assertTrue(payload['can_edit'])
        dashboard.group_ids = False
        data, payload = self._data(dashboard, user=self.user)
        self.assertFalse(payload['can_edit'])
        with self.assertRaises(AccessError):
            dashboard.with_user(self.portal)._payload('backend')

    def test_website_visibility(self):
        dashboard = self._dashboard([self._item(name='Count')], website_published=True,
                                    website_visibility='public', data_scope='shared')
        public = self.env.ref('base.public_user')
        self.assertTrue(dashboard._can_view_website(public))
        dashboard.website_visibility = 'signed_in'
        self.assertFalse(dashboard._can_view_website(public))
        self.assertTrue(dashboard._can_view_website(self.portal))
        dashboard.website_visibility = 'groups'
        dashboard.website_group_ids = self.env.ref('base.group_portal')
        self.assertTrue(dashboard._can_view_website(self.portal))
        self.assertFalse(dashboard._can_view_website(self.user))
        dashboard.website_published = False
        self.assertFalse(dashboard._can_view_website(self.portal))
        other = self.env['website'].create({'name': 'AXS Other Website'})
        dashboard.write({'website_published': True, 'website_id': other.id})
        self.assertFalse(dashboard._can_view_website(self.portal, self.env['website'].search(
            [('id', '!=', other.id)], limit=1)))
        self.assertTrue(dashboard._can_view_website(self.portal, other))

    def test_data_scope(self):
        """Portal users cannot read dashboard items: viewer's data is refused, shared data is computed."""
        item_model = self.env['ir.model']._get('axs.dashboard.item')
        dashboard = self._dashboard([{'name': 'Items', 'item_type': 'tile', 'model_id': item_model.id,
                                      'date_filter_mode': 'none'}],
                                    website_published=True, website_visibility='signed_in', data_scope='viewer')
        data, _payload = self._data(dashboard, channel='website', user=self.portal)
        self.assertTrue(data['Items'].get('no_access'))
        dashboard.data_scope = 'shared'
        data, _payload = self._data(dashboard, channel='website', user=self.portal)
        self.assertGreaterEqual(data['Items']['value'], 1)
        self.assertNotIn('domain', data['Items'], "domains are only sent to the back end")
        with self.assertRaises(ValidationError):
            dashboard.data_user_id = self.portal

    def test_record_rules_apply_to_viewer(self):
        rule_model = 'ir.rule' in self.env and self.env['ir.rule']
        dashboard = self._dashboard([self._item(name='Count')])
        if rule_model is not False:
            rule_model.create({'name': 'AXS only BE', 'model_id': self.partner_model.id,
                               'domain_force': "['|', ('ref', '!=', 'axsw'), ('country_id.code', '=', 'BE')]"})
        else:  # Odoo 20
            self.env['ir.access'].create({'name': 'AXS only BE', 'model_id': self.partner_model.id,
                                          'operation': 'r',
                                          'domain': "['|', ('ref', '!=', 'axsw'), ('country_id.code', '=', 'BE')]"})
        data, _payload = self._data(dashboard, user=self.user)
        self.assertEqual(data['Count']['value'], 2)

    def test_layout_and_todo_rights(self):
        dashboard = self._dashboard([self._item(name='Count')])
        item = dashboard.item_ids
        with self.assertRaises(AccessError):
            dashboard.with_user(self.user).save_layout([{'id': item.id, 'x': 1, 'y': 1, 'w': 2, 'h': 2}])
        dashboard.with_user(self.manager).save_layout([{'id': item.id, 'x': 40, 'y': 2, 'w': 20, 'h': 0}])
        self.assertEqual((item.grid_x, item.grid_y, item.grid_w, item.grid_h), (11, 2, 12, 1))


@tagged('post_install', '-at_install', 'axs_dashboard')
class TestDashboardTools(DashboardCase):

    def test_export_import_copy(self):
        dashboard = self._dashboard([
            self._item(name='Bar', item_type='bar', group_field_id=self.f('country_id').id, grid_x=2),
            self._item(name='Rows', item_type='list', list_field_ids=[(6, 0, [self.f('name').id])]),
            {'name': 'Tasks', 'item_type': 'todo', 'todo_ids': [(0, 0, {'name': 'Call'})]},
        ], theme='ocean')
        data = dashboard._export_data()
        imported = self.Dashboard._import_data(json.loads(json.dumps(data)))
        self.assertEqual(imported.theme, 'ocean')
        self.assertEqual(imported.item_ids.mapped('name'), dashboard.item_ids.mapped('name'))
        bar = imported.item_ids.filtered(lambda i: i.name == 'Bar')
        self.assertEqual(bar.group_field_id, self.f('country_id'))
        self.assertEqual(bar.grid_x, 2)
        self.assertEqual(imported.item_ids.filtered(lambda i: i.name == 'Tasks').todo_ids.name, 'Call')
        wizard = self.env['axs.dashboard.import.wizard'].create({
            'file': binary_input(json.dumps(data).encode()), 'filename': 'd.json'})
        action = wizard.action_import()
        self.assertEqual(len(action['domain'][0][2]), 1)
        self.assertIn('/web/content/', dashboard.action_export()['url'])
        copy = dashboard.copy()
        self.assertEqual(len(copy.item_ids), 3)
        self.assertIn('copy', copy.name)
        self.assertFalse(copy.website_published)

    def test_menus(self):
        dashboard = self._dashboard([self._item(name='Count')], backend_menu=True, website_published=True,
                                    website_menu=True)
        self.assertTrue(dashboard.menu_id.action)
        self.assertEqual(dashboard.action_id.tag, 'axs_website_dashboard.dashboard')
        self.assertTrue(dashboard.website_menu_id.url.startswith('/dashboards/'))
        dashboard.website_published = False
        self.assertFalse(dashboard.website_menu_id)
        dashboard.backend_menu = False
        self.assertFalse(dashboard.menu_id.active)
        menu, action = dashboard.menu_id, dashboard.action_id
        dashboard.unlink()
        self.assertFalse(menu.exists())
        self.assertFalse(action.exists())

    def test_templates(self):
        Wizard = self.env['axs.dashboard.template.wizard']
        keys = [k for k, _label in Wizard._template_selection()]
        self.assertIn('contacts', keys)
        for key in keys:
            wizard = Wizard.create({'template': key})
            action = wizard.action_create()
            dashboard = self.Dashboard.browse(action['params']['dashboard_id'])
            self.assertTrue(dashboard.item_ids, key)
            payload = dashboard._payload('backend')
            errors = [i['name'] for i in payload['items'] if i['data'].get('error')]
            self.assertFalse(errors, "template %s has failing items: %s" % (key, errors))


@tagged('post_install', '-at_install', 'axs_dashboard')
class TestDashboardHttp(HttpCase):

    def _rpc(self, url, params):
        res = self.url_open(url, data=json.dumps({'jsonrpc': '2.0', 'method': 'call', 'id': 1, 'params': params}),
                            headers={'Content-Type': 'application/json'})
        return res.json()

    def test_routes(self):
        partner_model = self.env['ir.model']._get('res.partner')
        dashboard = self.env['axs.dashboard'].create({
            'name': 'AXS Public', 'website_published': True, 'website_visibility': 'public',
            'data_scope': 'shared', 'data_user_id': self.env.ref('base.user_admin').id,
            'item_ids': [(0, 0, {'name': 'Partners', 'item_type': 'tile', 'model_id': partner_model.id,
                                 'date_filter_mode': 'none'})],
        })
        private = self.env['axs.dashboard'].create({'name': 'AXS Private', 'website_published': True,
                                                    'website_visibility': 'signed_in'})
        result = self._rpc('/axs_dashboard/data', {'dashboard_id': dashboard.id})['result']
        self.assertGreater(result['items'][0]['data']['value'], 0)
        self.assertFalse(result['can_edit'])
        result = self._rpc('/axs_dashboard/data', {'dashboard_id': dashboard.id, 'channel': 'backend'})['result']
        self.assertNotIn('domain', result['items'][0]['data'], "public visitors never get the back-end channel")
        result = self._rpc('/axs_dashboard/data', {'dashboard_id': private.id})['result']
        self.assertEqual(result.get('access'), False)
        page = self.url_open('/dashboards/%s' % dashboard.id)
        self.assertEqual(page.status_code, 200)
        self.assertIn('data-axs-dashboard="%s"' % dashboard.id, page.text)
        index = self.url_open('/dashboards')
        self.assertIn('AXS Public', index.text)
        self.assertNotIn('AXS Private', index.text)
        page = self.url_open('/dashboards/%s' % private.id, allow_redirects=False)
        self.assertIn(page.status_code, (302, 303))
        self.assertEqual(self.url_open('/dashboards/999999').status_code, 404)
        # layout changes need a signed-in manager
        response = self._rpc('/axs_dashboard/layout', {'dashboard_id': dashboard.id, 'layout': []})
        self.assertIn('error', response)
