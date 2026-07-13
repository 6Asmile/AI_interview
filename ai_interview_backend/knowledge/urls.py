from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import KnowledgeDocumentViewSet, KnowledgeImportBatchViewSet, KnowledgeSearchDebugView

router = DefaultRouter()
router.register(r'knowledge/documents', KnowledgeDocumentViewSet, basename='knowledge-document')
router.register(r'knowledge/import-batches', KnowledgeImportBatchViewSet, basename='knowledge-import-batch')

urlpatterns = [
    path('knowledge/search/debug/', KnowledgeSearchDebugView.as_view(), name='knowledge-search-debug'),
    path('', include(router.urls)),
]
