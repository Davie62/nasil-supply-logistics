from types import SimpleNamespace

from django.core.paginator import Paginator
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase


class SharedMobileComponentTests(SimpleTestCase):
    def setUp(self):
        self.request = RequestFactory().get('/customers/?q=Tea+%26+Coffee&status=active&page=2')

    def render_pagination(self, page):
        return render_to_string('operations/components/pagination.html', {
            'request': self.request, 'page_obj': page,
        })

    def test_pagination_preserves_filters_and_exposes_all_controls(self):
        html = self.render_pagination(Paginator(range(100), 10).page(2))
        self.assertIn('q=Tea+%26+Coffee&amp;status=active&amp;page=3', html)
        for label in ('First page', 'Previous page', 'Next page', 'Last page'):
            self.assertIn(f'aria-label="{label}"', html)
        self.assertIn('aria-current="page">2</a>', html)

    def test_large_page_counts_have_a_bounded_window(self):
        html = self.render_pagination(Paginator(range(100000), 10).page(5000))
        self.assertLess(html.count('class="ui-page-number"'), 10)
        self.assertIn('&hellip;', html)

    def test_disabled_controls_are_not_focusable_links(self):
        html = self.render_pagination(Paginator(range(30), 10).page(1))
        self.assertIn('aria-disabled="true" aria-label="First page"', html)
        self.assertNotIn('rel="prev"', html)

    def test_one_page_does_not_display_redundant_page_links(self):
        html = self.render_pagination(Paginator(range(2), 10).page(1))
        self.assertIn('1&ndash;2 of 2 records', html)
        self.assertNotIn('ui-pagination-pages', html)

    def test_customer_navigation_marks_current_section(self):
        self.request.customer = SimpleNamespace(full_name='QA Customer')
        self.request.resolver_match = SimpleNamespace(url_name='portal_shipment')
        html = render_to_string('portal/base.html', {'request': self.request})
        self.assertIn('href="/portal/shipments/" aria-current="page"', html)
        self.assertIn('aria-controls="portal-navigation"', html)

    def test_notification_severity_and_escaping_are_preserved(self):
        class Message:
            tags = 'error'
            def __str__(self):
                return '<script>alert(1)</script>'
        html = render_to_string('ui/toasts.html', {'messages': [Message()]})
        self.assertIn('data-tone="error" role="alert"', html)
        self.assertIn('&lt;script&gt;', html)
        self.assertNotIn('<script>', html)
