"""Small helpers hiding the API differences between Odoo 16 and Odoo 20."""
import datetime

from odoo import release

MAJOR = release.version_info[0]


def can_read(Model):
    """True when the environment user may read the model (ACL only, rules are applied by the queries)."""
    if hasattr(Model, 'has_access'):  # Odoo 18+
        return Model.has_access('read')
    return Model.check_access_rights('read', raise_exception=False)


def slug(record):
    if MAJOR >= 18:
        return record.env['ir.http']._slug(record)
    from odoo.addons.http_routing.models.ir_http import slug as _slug
    return _slug(record)


def _to_date(value):
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    if isinstance(value, str) and value:
        return datetime.date.fromisoformat(value[:10])
    return None


def group_data(Model, domain, groupby, aggregate, limit=None):
    """Aggregate ``Model`` records.

    :param groupby: list of group specifications (``field`` or ``field:interval``), at most two
    :param aggregate: ``__count`` or ``field:sum|avg|min|max``
    :returns: list of ``{'keys': [raw key per groupby], 'value': number, 'count': int}`` where a raw key is
        a record id for many2one fields, a ``datetime.date`` (period start) for dates, or the field value.
    """
    measure = aggregate.split(':')[0]
    rows = []
    if MAJOR >= 17:
        aggregates = ['__count'] if aggregate == '__count' else [aggregate, '__count']
        for res in Model._read_group(domain, list(groupby), aggregates, limit=limit):
            keys = list(res[:len(groupby)])
            values = res[len(groupby):]
            norm = []
            for spec, key in zip(groupby, keys):
                fname = spec.split(':')[0]
                field = Model._fields[fname]
                if field.type == 'many2one':
                    norm.append(key.id or False)
                elif field.type in ('date', 'datetime'):
                    norm.append(_to_date(key) if key else False)
                else:
                    norm.append(key)
            value = values[0] if aggregate != '__count' else values[0]
            count = values[-1]
            rows.append({'keys': norm, 'value': value or 0, 'count': count})
        return rows
    # Odoo 16
    fields = ['__count'] if aggregate == '__count' else [aggregate]
    for res in Model.read_group(domain, fields, list(groupby), lazy=False, limit=limit):
        norm = []
        for spec in groupby:
            fname = spec.split(':')[0]
            field = Model._fields[fname]
            key = res.get(spec)
            if field.type == 'many2one':
                norm.append(key[0] if key else False)
            elif field.type in ('date', 'datetime'):
                rng = (res.get('__range') or {}).get(spec)
                norm.append(_to_date(rng['from']) if rng and key else False)
            else:
                norm.append(key)
        count = res.get('__count', 0)
        value = count if aggregate == '__count' else res.get(measure) or 0
        rows.append({'keys': norm, 'value': value, 'count': count})
    return rows


def field_aggregator(field):
    return getattr(field, 'aggregator', None) or getattr(field, 'group_operator', None)


def current_website(env):
    """The website of the current request (or the first website outside requests)."""
    Website = env['website'].sudo()
    if hasattr(Website, 'get_current_website'):  # up to Odoo 19
        return Website.get_current_website()
    website = getattr(env, 'website', None)  # Odoo 20
    return (website and website.sudo()) or Website.search([], limit=1)


def binary_read(value):
    """Raw bytes of a Binary field value (base64 up to Odoo 19, BinaryValue in Odoo 20)."""
    import base64
    if not value:
        return b''
    if hasattr(value, 'content'):
        return value.content
    return base64.b64decode(value)


def binary_input(raw):
    """Value to write in a Binary field from raw bytes."""
    import base64
    try:
        from odoo.tools import BinaryBytes
    except ImportError:
        return base64.b64encode(raw)
    return BinaryBytes(raw)
