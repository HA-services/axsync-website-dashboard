"""Date ranges for the dashboard date filters, computed in the user's timezone."""
import datetime

import pytz
from dateutil.relativedelta import relativedelta

DATE_FILTERS = [
    ('none', 'All Time'),
    ('today', 'Today'),
    ('yesterday', 'Yesterday'),
    ('this_week', 'This Week'),
    ('this_month', 'This Month'),
    ('this_quarter', 'This Quarter'),
    ('this_year', 'This Year'),
    ('last_week', 'Last Week'),
    ('last_month', 'Last Month'),
    ('last_quarter', 'Last Quarter'),
    ('last_year', 'Last Year'),
    ('last_7_days', 'Last 7 Days'),
    ('last_30_days', 'Last 30 Days'),
    ('last_90_days', 'Last 90 Days'),
    ('last_365_days', 'Last 365 Days'),
    ('week_to_date', 'Week to Date'),
    ('month_to_date', 'Month to Date'),
    ('quarter_to_date', 'Quarter to Date'),
    ('year_to_date', 'Year to Date'),
    ('next_7_days', 'Next 7 Days'),
    ('next_30_days', 'Next 30 Days'),
    ('before_30_days', 'Older than 30 Days'),
    ('custom', 'Custom Range'),
]


def _quarter_start(day):
    return day.replace(month=3 * ((day.month - 1) // 3) + 1, day=1)


def date_range(key, today, date_from=None, date_to=None):
    """Inclusive ``(start, end)`` dates for a filter key; ``None`` means unbounded."""
    if not key or key == 'none':
        return None, None
    week_start = today - datetime.timedelta(days=today.weekday())
    month_start = today.replace(day=1)
    quarter_start = _quarter_start(today)
    year_start = today.replace(month=1, day=1)
    one = datetime.timedelta(days=1)
    ranges = {
        'today': (today, today),
        'yesterday': (today - one, today - one),
        'this_week': (week_start, week_start + datetime.timedelta(days=6)),
        'this_month': (month_start, month_start + relativedelta(months=1) - one),
        'this_quarter': (quarter_start, quarter_start + relativedelta(months=3) - one),
        'this_year': (year_start, year_start.replace(month=12, day=31)),
        'last_week': (week_start - datetime.timedelta(days=7), week_start - one),
        'last_month': (month_start - relativedelta(months=1), month_start - one),
        'last_quarter': (quarter_start - relativedelta(months=3), quarter_start - one),
        'last_year': (year_start - relativedelta(years=1), year_start - one),
        'last_7_days': (today - datetime.timedelta(days=6), today),
        'last_30_days': (today - datetime.timedelta(days=29), today),
        'last_90_days': (today - datetime.timedelta(days=89), today),
        'last_365_days': (today - datetime.timedelta(days=364), today),
        'week_to_date': (week_start, today),
        'month_to_date': (month_start, today),
        'quarter_to_date': (quarter_start, today),
        'year_to_date': (year_start, today),
        'next_7_days': (today, today + datetime.timedelta(days=6)),
        'next_30_days': (today, today + datetime.timedelta(days=29)),
        'before_30_days': (None, today - datetime.timedelta(days=30)),
    }
    if key == 'custom':
        start = _parse(date_from)
        end = _parse(date_to)
        if start and end and start > end:
            start, end = end, start
        return start, end
    return ranges.get(key, (None, None))


def previous_range(start, end):
    """The period of the same length right before ``start``-``end`` (for KPI comparisons)."""
    if not start or not end:
        return None, None
    length = (end - start).days + 1
    return start - datetime.timedelta(days=length), start - datetime.timedelta(days=1)


def _parse(value):
    if not value:
        return None
    if isinstance(value, datetime.date):
        return value
    try:
        return datetime.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def range_domain(field, start, end, tz_name):
    """Domain on ``field`` (a date or datetime field) for an inclusive date range."""
    domain = []
    if field.type == 'date':
        if start:
            domain.append((field.name, '>=', start.isoformat()))
        if end:
            domain.append((field.name, '<=', end.isoformat()))
        return domain
    tz = pytz.timezone(tz_name or 'UTC')

    def utc(day):
        local = tz.localize(datetime.datetime.combine(day, datetime.time.min))
        return local.astimezone(pytz.utc).replace(tzinfo=None).strftime('%Y-%m-%d %H:%M:%S')

    if start:
        domain.append((field.name, '>=', utc(start)))
    if end:
        domain.append((field.name, '<', utc(end + datetime.timedelta(days=1))))
    return domain
