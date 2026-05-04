"""Pagination légère pour la liste des notifications (évite charger tout l’historique)."""

from rest_framework.pagination import PageNumberPagination


class NotificationPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 50
