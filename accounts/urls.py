from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    CurrentUserAPIView, ForgotPasswordAPIView, GoogleLoginAPIView, 
    RefreshFromCookieAPIView, LogoutAPIView, FacebookLoginAPIView, 
    LoginAPIView, RegisterSendOTPAPIView, RegisterVerifyOTPAPIView, RequestUpdateOTP, 
    ResetPasswordAPIView, ShippingAddressDetailAPIView, ShippingAddressListCreateAPIView, VerifyOTPAPIView, CartAPIView, CartAddItemAPIView, CartUpdateItemAPIView,
    CartRemoveItemAPIView, VerifyUpdateOTP, WishlistAPIView, WishlistRemoveAPIView, WishlistMoveToCartAPIView,
    UserDashboardAPIView, ProductReviewListAPIView, ProductReviewCreateUpdateAPIView, ProductReviewDeleteAPIView)

urlpatterns = [
    path("login/google/", GoogleLoginAPIView.as_view(), name="google-login"),
    path("token/refresh-cookie/", RefreshFromCookieAPIView.as_view(), name="token-refresh-cookie"),
    path("logout/", LogoutAPIView.as_view(), name="logout"),
    path('me/', CurrentUserAPIView.as_view(), name="current-user"),
    path("login/facebook/", FacebookLoginAPIView.as_view(), name="facebook-login"),
    path("register/send-otp/", RegisterSendOTPAPIView.as_view(), name="register-send-otp"),
    path("register/verify-otp/", RegisterVerifyOTPAPIView.as_view(), name="register-verify-otp"),
    path("login/", LoginAPIView.as_view(), name="login"),
    path("forgot-password/", ForgotPasswordAPIView.as_view(), name="forgot-password"),
    path("verify-otp/", VerifyOTPAPIView.as_view(), name="verify-otp"),
    path("reset-password/", ResetPasswordAPIView.as_view(), name="reset-password"),

    # USER
    path("dashboard/", UserDashboardAPIView.as_view(), name="user-dashboard"),
    path("user/update/request-otp/", RequestUpdateOTP.as_view(), name="request-otp-for-mobile/email-update"),
    path("user/update/verify-otp/", VerifyUpdateOTP.as_view(), name='udpate-mobile/email-after-otp-verrify'),
    path("shipping/address/", ShippingAddressListCreateAPIView.as_view(), name="shippingaddress-list-create"),
    path("shipping/address/<uuid:id>/", ShippingAddressDetailAPIView.as_view(), name="shippingaddress-detail"),

    # CART
    path("cart/", CartAPIView.as_view(), name="cart"),
    path("cart/add/", CartAddItemAPIView.as_view(), name="cart-add"),
    path("cart/update/", CartUpdateItemAPIView.as_view(), name="cart-update"),
    path("cart/remove/", CartRemoveItemAPIView.as_view(), name="cart-remove"),

    # WISHLIST
    path("wishlist/", WishlistAPIView.as_view(), name="wishlist"),
    path("wishlist/remove/", WishlistRemoveAPIView.as_view(), name="wishlist-remove"),
    path("wishlist/move-to-cart/", WishlistMoveToCartAPIView.as_view(), name="wishlist-move-to-cart"),

    # COMMENT & REVIWES
    path("reviews/<uuid:sku_id>/", ProductReviewListAPIView.as_view(), name="product-reviews-list"),
    path("reviews/<uuid:sku_id>/add/", ProductReviewCreateUpdateAPIView.as_view(), name="add-update-review"),
    path("reviews/<uuid:sku_id>/delete/", ProductReviewDeleteAPIView.as_view(), name="delete-review"),
]