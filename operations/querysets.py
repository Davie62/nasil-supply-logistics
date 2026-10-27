"""Shared filtering and pagination operate on QuerySets before materialization."""
from datetime import datetime, time, timedelta
from django.core.paginator import Paginator
from django.db.models import Q
from django.utils import timezone


def search(queryset, term, fields):
    if term:
        match = Q()
        for field in fields:
            match |= Q(**{field + "__icontains": term[:150]})
        queryset = queryset.filter(match)
    return queryset


def paginate(request, queryset, size=25):
    page = Paginator(queryset, size).get_page(request.GET.get("page"))
    return page, {"page_obj": page, "server_search": True, "search_term": request.GET.get("q", "")[:150]}


def date_range(queryset, data, field="created_at"):
    if data.get("date_from"):
        start = timezone.make_aware(datetime.combine(data["date_from"], time.min))
        queryset = queryset.filter(**{field + "__gte": start})
    if data.get("date_to"):
        end = timezone.make_aware(datetime.combine(data["date_to"] + timedelta(days=1), time.min))
        queryset = queryset.filter(**{field + "__lt": end})
    return queryset
