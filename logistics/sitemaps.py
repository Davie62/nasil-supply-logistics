from django.contrib.sitemaps import Sitemap
from django.urls import reverse


class PublicPageSitemap(Sitemap):
    """Public marketing, support, and legal pages only.

    Portal, dashboard, and staff routes are deliberately excluded so search
    engines never index authenticated areas.
    """

    PAGES = {
        "home": ("weekly", 1.0),
        "services": ("monthly", 0.9),
        "quote": ("monthly", 0.9),
        "industries": ("monthly", 0.8),
        "coverage": ("monthly", 0.8),
        "about": ("monthly", 0.8),
        "faq": ("monthly", 0.7),
        "contact": ("monthly", 0.7),
        "public_tracking": ("monthly", 0.5),
        "privacy": ("yearly", 0.3),
        "terms": ("yearly", 0.3),
        "cookies": ("yearly", 0.3),
    }

    def items(self):
        return list(self.PAGES)

    def location(self, item):
        return reverse(item)

    def changefreq(self, item):
        return self.PAGES[item][0]

    def priority(self, item):
        return self.PAGES[item][1]
