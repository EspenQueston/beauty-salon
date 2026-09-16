from rest_framework.pagination import PageNumberPagination


class DefaultPagination(PageNumberPagination):
    """Pagination obligatoire : aucune liste de l'API n'est renvoyee entiere."""

    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100
