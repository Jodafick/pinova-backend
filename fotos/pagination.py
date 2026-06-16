"""Pagination pour les flux de fotos : permet page_size client (profils)."""

from rest_framework.pagination import PageNumberPagination


class FotoFeedPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100


class BoardListPagination(PageNumberPagination):
    page_size = 24
    page_size_query_param = 'page_size'
    max_page_size = 100
