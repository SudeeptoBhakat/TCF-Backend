import uuid
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from django.db.models import Prefetch, Q
from rest_framework.pagination import PageNumberPagination
from .models import ProductCategory, Product, ProductSKU, ProductMedia, SKUAttributeOption, CommodityVariant, CommodityRate
from .serializers import ProductCategoryListSerilizer, ProductListSerializer, ProductSearchSerializer
from rest_framework.permissions import AllowAny

# PRODUCT CATAGORY LSIT
class CategoryListAPIView(APIView):
    permission_classes = []

    def get(self, request):
        categories = ProductCategory.objects.filter(
            parent=None,
            is_active=True
        ).order_by("name")

        serializer = ProductCategoryListSerilizer(categories, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


# PRODUCTS FILTER BY CATAGORY
class CategoryProductListAPIView(APIView):
    permission_classes = []

    def get(self, request, identifier):

        try:
            uuid.UUID(str(identifier))
            lookup_field = "id"
        except ValueError:
            lookup_field = "slug"

        category = get_object_or_404(
            ProductCategory.objects.filter(is_active=True),
            **{lookup_field: identifier}
        )

        products = Product.objects.filter(
            category=category,
            is_active=True,
            category__is_active=True
        ).select_related(
            "category"
        ).prefetch_related(
            Prefetch("media", queryset=ProductMedia.objects.order_by("sort_order")),
            Prefetch(
                "skus",
                queryset=ProductSKU.objects.filter(is_active=True).select_related(
                    "commodity_variant"
                ).prefetch_related(
                    Prefetch(
                        "sku_attribute_options",
                        queryset=SKUAttributeOption.objects.select_related(
                            "attribute_option",
                            "attribute_option__attribute"
                        )
                    ),
                    Prefetch("commodity_variant__rates")
                )
            )
        ).order_by("-created_at")

        serializer = ProductListSerializer(products, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


# PRODUCT API LIST
class ProductPagination(PageNumberPagination):
    page_size = 12
    page_size_query_param = "page_size"
    max_page_size = 100


class ProductListAPIView(APIView):
    permission_classes = []  # Public API

    def get(self, request):
        # ------------ FILTERS ------------
        category_filter = request.GET.get("category")
        is_bestseller = request.GET.get("bestseller")
        diamond_filter = request.GET.get("diamond")
        bracelet_filter = request.GET.get("bracelet")

        filters = Q(is_active=True, category__is_active=True)

        # Category based filter: men / women / kids
        if category_filter in ["men", "women", "kids"]:
            filters &= Q(category__slug=category_filter)

        # Bestseller filter
        if is_bestseller in ["1", "true", "True"]:
            filters &= Q(is_bestseller=True)

        # Diamonds
        if diamond_filter in ["1", "true", "True"]:
            filters &= Q(tags__icontains="diamond")

        # Bracelets
        if bracelet_filter in ["1", "true", "True"]:
            filters &= Q(tags__icontains="bracelet")

        # ------------ BASE QUERY ------------
        queryset = (
            Product.objects.filter(filters)
            .select_related("category")
            .prefetch_related(
                Prefetch("media", queryset=ProductMedia.objects.order_by("sort_order")),
                Prefetch(
                    "skus",
                    queryset=ProductSKU.objects.filter(is_active=True)
                    .select_related("commodity_variant")
                    .prefetch_related(
                        Prefetch(
                            "sku_attribute_options",
                            queryset=SKUAttributeOption.objects.select_related(
                                "attribute_option", "attribute_option__attribute"
                            ),
                        ),
                        Prefetch("commodity_variant__rates"),
                    ),
                ),
            )
            .order_by("-created_at")
        )

        # ------------ PAGINATION ------------
        paginator = ProductPagination()
        paginated_products = paginator.paginate_queryset(queryset, request)

        serializer = ProductListSerializer(
            paginated_products,
            many=True,
            context={"request": request},
        )

        return paginator.get_paginated_response(serializer.data)



# SEARCH BY ID OR SLUG
class ProductDetailAPIView(APIView):
    permission_classes = []  # Public API

    def get(self, request, identifier):
        """
        Supports lookup by:
        - UUID (id)
        - slug (string)
        """
        try:
            uuid.UUID(str(identifier))
            lookup_field = "id"
        except ValueError:
            lookup_field = "slug"

        product = get_object_or_404(
            Product.objects.filter(is_active=True, category__is_active=True)
            .select_related("category")
            .prefetch_related(
                Prefetch("media", queryset=ProductMedia.objects.order_by("sort_order")),
                Prefetch(
                    "skus",
                    queryset=ProductSKU.objects.filter(is_active=True)
                    .select_related("commodity_variant")
                    .prefetch_related(
                        Prefetch(
                            "sku_attribute_options",
                            queryset=SKUAttributeOption.objects.select_related(
                                "attribute_option",
                                "attribute_option__attribute"
                            )
                        ),
                        Prefetch("commodity_variant__rates")
                    )
                )
            ),
            **{lookup_field: identifier}
        )

        serializer = ProductListSerializer(product)
        return Response(serializer.data, status=status.HTTP_200_OK)


class ProductSearchAPIView(APIView):
    """
    Fast search API that returns both products and categories as suggestions.
    - Searches in: product name, description, category name, SKU code
    - Returns images, basic details, and product ID/slug
    - Limit: 15 results
    """
    permission_classes = []
    
    def get(self, request):
        query = request.GET.get("q", "").strip()
        
        if not query or len(query) < 2:
            return Response({
                "query": query,
                "products": [],
                "categories": [],
                "message": "Query must be at least 2 characters"
            }, status=status.HTTP_200_OK)

        # Search Products
        product_results = Product.objects.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query) |
            Q(category__name__icontains=query) |
            Q(skus__sku_code__icontains=query),
            is_active=True,
            category__is_active=True
        ).select_related(
            "category"
        ).prefetch_related(
            Prefetch(
                "media",
                queryset=ProductMedia.objects.order_by("sort_order")
            ),
            Prefetch(
                "skus",
                queryset=ProductSKU.objects.filter(is_active=True)
                .select_related("commodity_variant")
                .prefetch_related(
                    Prefetch(
                        "sku_attribute_options",
                        queryset=SKUAttributeOption.objects.select_related(
                            "attribute_option__attribute"
                        )
                    ),
                    Prefetch("commodity_variant__rates")
                )
            )
        ).distinct()[:15]

        # Search Categories
        category_results = ProductCategory.objects.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query),
            is_active=True
        )[:10]

        product_serializer = ProductSearchSerializer(
            product_results,
            many=True,
            context={"request": request}
        )
        
        category_serializer = ProductCategoryListSerilizer(
            category_results,
            many=True
        )

        return Response({
            "query": query,
            "products": product_serializer.data,
            "categories": category_serializer.data,
            "total_products": len(product_serializer.data),
            "total_categories": len(category_serializer.data),
        }, status=status.HTTP_200_OK)