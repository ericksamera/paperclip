# services/server/paperclip/qa/urls.py
from django.urls import path

from .api import ask_collection

urlpatterns = [
    path("collections/<int:collection_id>/ask", ask_collection, name="collections-ask"),
]
