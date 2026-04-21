from django.urls import path

from . import views

app_name = "analyzer"

urlpatterns = [
    path("", views.LandingView.as_view(), name="landing"),
    path("analyzing/<uuid:uuid>/", views.AnalyzingView.as_view(), name="analyzing"),
    path("results/<uuid:uuid>/", views.ResultsView.as_view(), name="results"),
    path("results/<uuid:uuid>/share/", views.SharedResultsView.as_view(), name="results-share"),
    path("results/<uuid:uuid>/status/", views.ResultStatusView.as_view(), name="results-status"),
    path("results/<uuid:uuid>/share-link/", views.GenerateShareLinkView.as_view(), name="generate-share-link"),
    path("error/", views.ErrorView.as_view(), name="error"),
]
