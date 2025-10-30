# core/pagination.py

from rest_framework.pagination import PageNumberPagination

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 10  # 每页默认显示10条数据
    page_size_query_param = 'page_size' # 允许客户端通过URL查询参数来改变每页大小
    max_page_size = 100 # 每页最大显示数量