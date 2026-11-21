from django.urls import path

from . import views

urlpatterns = [
    path("", views.ListView.as_view()),
    path("<int:pk>/", views.DetailView.as_view()),
    path("<int:pk>/publish/", views.PublishView.as_view()),
    path("<int:pk>/members/", views.MembersView.as_view()),
    path("<int:pk>/orders/", views.OrdersView.as_view()),
    path("<int:pk>/orders/<int:order_id>/", views.OrderView.as_view()),
    path("<int:pk>/invoices/", views.InvoicesView.as_view()),
    path("<int:pk>/export/", views.ExportView.as_view()),
]
