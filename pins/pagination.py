"""Pagination pour les flux de pins : permet page_size client (profils)."""

from rest_framework.pagination import PageNumberPagination


class PinFeedPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100


class BoardListPagination(PageNumberPagination):
    page_size = 24
    page_size_query_param = 'page_size'
    max_page_size = 100
