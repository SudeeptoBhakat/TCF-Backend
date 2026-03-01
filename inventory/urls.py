from django.urls import path
from .views import CategoryListAPIView, ProductListAPIView, ProductDetailAPIView, CategoryProductListAPIView, ProductSearchAPIView

urlpatterns = [
    path("categories/", CategoryListAPIView.as_view(), name="category-list"),
    path('products/', ProductListAPIView.as_view(), name="product-list"),
    path("products/<str:identifier>/", ProductDetailAPIView.as_view(), name="product-detail"),
    path("categories/<str:identifier>/products/", CategoryProductListAPIView.as_view(), name="filter-products-by-catagory"),

    # Search
    path("search/", ProductSearchAPIView.as_view(), name="product-search"),
]