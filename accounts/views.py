import traceback
import requests
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions, viewsets, mixins
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from django.conf import settings
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView
from .models import ShippingAddress, User, AuthProvider, Cart, CartItem, Wishlist, ProductReview
from .serializers import (
    ShippingAddressSerializer, UserSerializer, CartSerializer, CartItemSerializer, UserUpdateSerializer, WishlistSerializer,
    ForgotPasswordSerializer, VerifyOTPSerializer, ResetPasswordSerializer, ProductReviewSerializer
)
from rest_framework_simplejwt.tokens import RefreshToken, TokenError
from rest_framework.permissions import IsAuthenticated
import jwt
from django.db.models import Prefetch
from datetime import datetime, timedelta
from django.contrib.auth import authenticate
from django.core.cache import cache
from django.utils import timezone
from .utils import (
    _otp_code, generate_reset_token,
    otp_cache_key, otp_request_count_key, otp_attempts_key, reset_token_cache_key,
)
from rest_framework.permissions import AllowAny
from django.shortcuts import get_object_or_404
from inventory.models import CommodityRate, ProductMedia, ProductSKU, SKUAttributeOption
from django.db import transaction
from rest_framework.decorators import action

google_client_id = settings.SOCIALACCOUNT_PROVIDERS['google']['APP'].get('client_id')
providers = getattr(settings, "SOCIALACCOUNT_PROVIDERS", {})
facebook_config = providers.get("facebook", {}).get("APP", {})

fb_app_id = facebook_config.get("client_id")
fb_app_secret = facebook_config.get("secret")

def _normalize_target(s: str) -> str:
    return s.strip().lower()

# Helper function to create JWT tokens
def generate_jwt_token(user):
    refresh = RefreshToken.for_user(user)
    access = refresh.access_token
    return str(access), str(refresh)


class GoogleLoginAPIView(APIView):
    permission_classes = (permissions.AllowAny,)

    def post(self, request):
        token = request.data.get("id_token") or request.data.get("token") or request.data.get("credential")
        if not token:
            return Response({"detail": "Missing id_token"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # VERIFY token using google-auth
            idinfo = id_token.verify_oauth2_token(token, google_requests.Request(), google_client_id)
            # idinfo contains: sub (user id), email, email_verified, name, picture, etc.
        except ValueError as e:
            return Response({"detail": "Invalid token", "error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        # Basic fields
        email = idinfo.get("email")
        email_verified = idinfo.get("email_verified", False)
        name = idinfo.get("name", "")
        google_sub = idinfo.get("sub")

        if not email:
            return Response({"detail": "Google account has no email"}, status=status.HTTP_400_BAD_REQUEST)

        # Try to find existing user by email
        user, created = User.objects.get_or_create(email=email, defaults={
            "full_name": name,
            "auth_provider": AuthProvider.GOOGLE,
            "is_verified": email_verified,
        })

        # If existing user has different auth_provider, handle it:
        if not created:
            if user.auth_provider != AuthProvider.GOOGLE:
                # Option: you can allow link, or reject. We'll set provider to GOOGLE for simplicity
                user.auth_provider = AuthProvider.GOOGLE
                user.is_verified = user.is_verified or email_verified
                user.save(update_fields=["auth_provider", "is_verified"])

        # Create tokens
        # refresh = RefreshToken.for_user(user)
        # access_token = str(refresh.access_token)
        # refresh_token = str(refresh)
        access_token, refresh_token = generate_jwt_token(user)

        # Build response
        serializer = UserSerializer(user)
        data = {
            "user": serializer.data,
            "access": access_token,
        }

        response = Response(data, status=status.HTTP_200_OK)

        # Set refresh token as HttpOnly secure cookie
        # Cookie configuration — adjust domain/secure for your environment
        cookie_max_age = 7 * 24 * 60 * 60  # 7 days in seconds (match SIMPLE_JWT REFRESH LIFETIME)
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=True,
            secure=True,      # set True in production (HTTPS)
            samesite="Lax",
            max_age=cookie_max_age,
        )

        return response


class RefreshFromCookieAPIView(APIView):
    permission_classes = (permissions.AllowAny,)

    def post(self, request):
        refresh_token = request.COOKIES.get("refresh_token")
        if not refresh_token:
            return Response({"detail": "No refresh token cookie."}, status=status.HTTP_401_UNAUTHORIZED)
        try:
            refresh = RefreshToken(refresh_token)
            # optionally rotate:
            new_access = str(refresh.access_token)
            # If you use ROTATE_REFRESH_TOKENS=True you'd create a new refresh token as well.
            data = {"access": new_access}
            return Response(data, status=status.HTTP_200_OK)
        except TokenError:
            return Response({"detail": "Invalid refresh token."}, status=status.HTTP_401_UNAUTHORIZED)


class CurrentUserAPIView(APIView):
    permission_classes = (IsAuthenticated,)
    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)


class LogoutAPIView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request):

        res = Response(
            {"message": "Logout successful."},
            status=status.HTTP_200_OK
        )

        # ❗ Delete cookies (must match login parameters exactly)
        res.delete_cookie(
            key="access_token",
            path="/",
            samesite="None",
            secure=True,
        )
        res.delete_cookie(
            key="refresh_token",
            path="/",
            samesite="None",
            secure=True,
        )
        res.delete_cookie(
            key="sessionid",
            path="/",
            samesite="None",
            secure=True,
        )

        return res



# User = get_user_model()

class FacebookLoginAPIView(APIView):
    permission_classes = (permissions.AllowAny,)

    def post(self, request):
        """
        Expects: { access_token: "<FB user access token>", remember: bool optional }
        Flow:
          1. Call debug_token to validate the token was issued for our app
          2. If valid, fetch user profile (email, name, picture)
          3. Create or get user, set auth_provider
          4. Issue JWT tokens and set refresh cookie
        """
        access_token = request.data.get("access_token")
        remember = bool(request.data.get("remember", False))

        if not access_token:
            return Response({"detail": "Missing access_token"}, status=status.HTTP_400_BAD_REQUEST)

        if not fb_app_id or not fb_app_secret:
            return Response({"detail": "Facebook app credentials not configured"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Verify token belongs to this app using debug_token
        app_token = f"{fb_app_id}|{fb_app_secret}"
        debug_url = "https://graph.facebook.com/debug_token"
        try:
            debug_resp = requests.get(debug_url, params={
                "input_token": access_token,
                "access_token": app_token
            }, timeout=10)
            debug_resp.raise_for_status()
            debug_data = debug_resp.json()
        except Exception as e:
            traceback.print_exc()
            return Response({"detail": "Failed to validate Facebook token", "error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        data = debug_data.get("data", {})
        if not data.get("is_valid"):
            return Response({"detail": "Invalid Facebook token"}, status=status.HTTP_400_BAD_REQUEST)

        # check app id matches
        if str(data.get("app_id")) != str(fb_app_id):
            return Response({"detail": "Facebook token was not issued for this app"}, status=status.HTTP_400_BAD_REQUEST)

        # Fetch profile
        try:
            profile_url = "https://graph.facebook.com/me"
            profile_resp = requests.get(profile_url, params={
                "fields": "id,name,email,picture",
                "access_token": access_token
            }, timeout=10)
            profile_resp.raise_for_status()
            profile = profile_resp.json()
        except Exception as e:
            traceback.print_exc()
            return Response({"detail": "Failed to fetch Facebook profile", "error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        email = profile.get("email")
        name = profile.get("name", "")
        facebook_id = profile.get("id")
        picture = None
        pic = profile.get("picture")
        if isinstance(pic, dict):
            picture = pic.get("data", {}).get("url")

        if not email:
            # Facebook accounts sometimes don't return email
            return Response({"detail": "Facebook account has no email address"}, status=status.HTTP_400_BAD_REQUEST)

        # Create/get user
        try:
            user, created = User.objects.get_or_create(email=email, defaults={
                "full_name": name,
                "auth_provider": "meta",  # or 'facebook' if you prefer
                "is_verified": True,
            })
            # if existing user had different provider, link or update
            if not created and user.auth_provider != "meta":
                # Option: set provider to meta (or keep original and ask the user)
                user.auth_provider = "meta"
                user.is_verified = user.is_verified or True
                user.save(update_fields=["auth_provider", "is_verified"])
        except Exception as e:
            traceback.print_exc()
            return Response({"detail": "Error creating or retrieving user", "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Issue JWT tokens
        refresh = RefreshToken.for_user(user)
        access_token_jwt = str(refresh.access_token)
        refresh_token_jwt = str(refresh)

        # Set refresh token cookie
        cookie_max_age = 30 * 24 * 60 * 60 if remember else 7 * 24 * 60 * 60
        response_data = {
            "user": UserSerializer(user).data,
            "access": access_token_jwt,
        }
        response = Response(response_data, status=status.HTTP_200_OK)
        response.set_cookie(
            key="refresh_token",
            value=refresh_token_jwt,
            httponly=True,
            secure=False,   # set True in production (requires https)
            samesite="Lax",
            max_age=cookie_max_age,
        )

        return response


# REGISTER USER (Manual Signup)
class RegisterSendOTPAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        target = request.data.get("email_or_phone")

        if not target:
            return Response({"error": "Email or phone is required."}, status=400)

        # Check existing account
        user_exists = False
        if "@" in target:
            if User.objects.filter(email=target).exists():
                user_exists = True
        else:
            if User.objects.filter(phone=target).exists():
                user_exists = True

        otp = _otp_code()  # 4-digit OTP
        key = otp_cache_key(target)

        cache.set(key, otp, timeout=600)  # valid for 10 mins

        # TODO: Replace with email or SMS send
        print(f"DEBUG OTP for {target} → {otp}")  # For testing

        message = "OTP sent successfully."
        if user_exists:
            message = "Welcome back! OTP sent to your registered contact."
        else:
            message = "Account created. Please verify with the OTP sent to you."

        return Response({
            "message": message,
            "is_new_user": not user_exists
        }, status=200)


class RegisterVerifyOTPAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        target = request.data.get("email_or_phone")
        full_name = request.data.get("full_name")
        # password = request.data.get("password") # Password not needed for OTP auth
        otp_submitted = request.data.get("otp")

        if not target or not otp_submitted:
            return Response({"error": "Email/Phone and OTP are required."}, status=400)

        # Retrieve OTP from Redis
        key = otp_cache_key(target)
        otp_stored = cache.get(key)

        if not otp_stored:
            return Response({"error": "OTP expired or not found."}, status=400)

        if otp_stored != otp_submitted:
            return Response({"error": "Invalid OTP."}, status=400)

        # OTP is correct → delete OTP from cache
        cache.delete(key)

        # Determine if this is email or phone based registration
        email = target if "@" in target else None
        phone = target if not "@" in target else None
        
        # Check if user exists (Login Flow)
        user = None
        if email:
            user = User.objects.filter(email=email).first()
        else:
            user = User.objects.filter(phone=phone).first()

        if user:
            # User exists -> Login
            if not user.is_verified:
                user.is_verified = True
                user.save()
            message = "Login successful."
        else:
            # User does not exist -> Register
            if not full_name:
                 return Response({"error": "Full name is required for new registration."}, status=400)
            
            auth_provider = AuthProvider.EMAIL if email else AuthProvider.PHONE
            # Generate a random password for OTP-only users or handle password differently
            import secrets
            random_password = secrets.token_urlsafe(16)
            
            user = User.objects.create_user(
                email=email,
                phone=phone,
                password=random_password,
                full_name=full_name,
                auth_provider=auth_provider
            )
            user.is_verified = True
            user.save()
            message = "Registration completed."

        # Generate JWT Tokens
        access, refresh = generate_jwt_token(user)

        res = Response({
            "message": message,
            "user": UserSerializer(user).data,
            "access": access,
            "refresh": refresh
        }, status=201)

        # Set cookies
        res.set_cookie(
            key='access_token',
            value=access,
            httponly=True,
            secure=True,
            samesite='None',
            max_age=60 * 15,
        )
        
        res.set_cookie(
            key='refresh_token',
            value=refresh,
            httponly=True,
            secure=True,
            samesite='None',
            max_age=60 * 60 * 24 * 7,
        )
        return res



# LOGIN USER (Manual Login)
class LoginAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email_or_phone = request.data.get('email_or_phone')
        password = request.data.get('password')

        if not email_or_phone or not password:
            return Response({'error': 'Both email/phone and password are required.'}, status=400)

        user = User.objects.filter(email=email_or_phone).first() or User.objects.filter(phone=email_or_phone).first()

        if not user:
            return Response({'error': 'No account found with that email or phone.'}, status=400)

        if not user.check_password(password):
            return Response({'error': 'Invalid password.'}, status=400)

        access, refresh = generate_jwt_token(user)

        res = Response({
            'user': UserSerializer(user).data,
            'access': access,
            'refresh': refresh
        }, status=status.HTTP_200_OK)

        # Set cookies
        res.set_cookie(
            key='access_token',
            value=access,
            httponly=True,
            secure=True,
            samesite='None',
            max_age=60 * 15,
        )
        
        res.set_cookie(
            key='refresh_token',
            value=refresh,
            httponly=True,
            secure=True,
            samesite='None',
            max_age=60 * 60 * 24 * 7,
        )        
        return res


# FORGATE PASSWORD
class ForgotPasswordAPIView(APIView):
    permission_classes = [AllowAny]
    """
    Request: { "email_or_phone": "user@example.com" }
    Response is intentionally generic to avoid account enumeration.
    """
    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        target = _normalize_target(serializer.validated_data["email_or_phone"])

        # Rate-limit requests per target
        req_count_key = otp_request_count_key(target)
        req_count = cache.get(req_count_key) or 0
        if req_count >= settings.OTP_MAX_REQUESTS_PER_HOUR:
            # Generic message
            return Response({"message": "If an account exists, an OTP has been sent."}, status=status.HTTP_200_OK)

        # find user (silent if not found)
        user = None
        if "@" in target:
            user = User.objects.filter(email__iexact=target).first()
        else:
            user = User.objects.filter(phone__iexact=target).first()

        # Generate OTP and store only if user exists; still respond generically
        if user:
            try:
                otp = _otp_code(settings.OTP_LENGTH)
                key = otp_cache_key(target)
                cache.set(key, otp, timeout=settings.OTP_TTL_SECONDS)

                # Optionally reset verification attempts counter
                cache.set(otp_attempts_key(target), 0, timeout=settings.OTP_TTL_SECONDS)

                # increase request count for rate limiting
                cache.set(req_count_key, req_count + 1, timeout=3600)  # 1 hour window

                # send OTP (email or SMS)
                # if user.email:
                #     send_otp_via_email(user.email, otp)
                # else:
                #     # implement send_sms(user.phone, otp) if needed
                #     pass

                # For development/testing: also log/print
                print(f"[OTP] {target} -> {otp}")

            except Exception as e:
                # log but keep response generic
                traceback.print_exc()
                # don't reveal send failure to client
        # Always return generic message
        return Response({"message": "If an account exists, an OTP has been sent."}, status=status.HTTP_200_OK)


class VerifyOTPAPIView(APIView):
    permission_classes = [AllowAny]
    """
    Request: { "email_or_phone": "...", "otp": "1234" }
    On success returns a one-time reset_token (temporary).
    """
    def post(self, request):
        serializer = VerifyOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        target = _normalize_target(serializer.validated_data["email_or_phone"])
        otp_supplied = str(serializer.validated_data["otp"]).strip()

        key = otp_cache_key(target)
        stored_otp = cache.get(key)
        # track attempts
        attempts_key = otp_attempts_key(target)
        attempts = cache.get(attempts_key) or 0

        if attempts >= settings.OTP_MAX_VERIFY_ATTEMPTS:
            return Response({"detail": "Too many attempts. Try again later."}, status=status.HTTP_429_TOO_MANY_REQUESTS)

        if not stored_otp or stored_otp != otp_supplied:
            cache.set(attempts_key, attempts + 1, timeout=settings.OTP_TTL_SECONDS)
            return Response({"detail": "Invalid or expired OTP."}, status=status.HTTP_400_BAD_REQUEST)

        # OTP valid: create one-time reset token and remove OTP
        reset_token = generate_reset_token()
        reset_key = reset_token_cache_key(reset_token)
        cache.set(reset_key, target, timeout=settings.RESET_TOKEN_TTL_SECONDS)
        cache.delete(key)
        cache.delete(attempts_key)

        return Response({"reset_token": reset_token, "message": "OTP verified. Use reset_token to change password."}, status=status.HTTP_200_OK)


class ResetPasswordAPIView(APIView):
    permission_classes = [AllowAny]
    """
    Request: { "reset_token": "...", "new_password": "..." }
    """
    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reset_token = serializer.validated_data["reset_token"]
        new_password = serializer.validated_data["new_password"]

        reset_key = reset_token_cache_key(reset_token)
        target = cache.get(reset_key)
        if not target:
            return Response({"detail": "Invalid or expired reset token."}, status=status.HTTP_400_BAD_REQUEST)

        # find user
        if "@" in target:
            user = User.objects.filter(email__iexact=target).first()
        else:
            user = User.objects.filter(phone__iexact=target).first()

        if not user:
            # Should not usually happen — treat as generic failure
            cache.delete(reset_key)
            return Response({"detail": "Invalid reset token."}, status=status.HTTP_400_BAD_REQUEST)

        # Update password
        user.set_password(new_password)
        user.save(update_fields=["password"])
        # Invalidate reset token
        cache.delete(reset_key)

        return Response({"message": "Password has been updated successfully."}, status=status.HTTP_200_OK)



class UserDashboardAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        cart = (
            Cart.objects.filter(user=user)
            .prefetch_related(
                Prefetch(
                    "items",
                    queryset=CartItem.objects.select_related(
                        "sku",
                        "sku__commodity_variant"
                    ).prefetch_related(
                        Prefetch(
                            "sku__media",
                            queryset=ProductMedia.objects.order_by("sort_order")
                        ),
                        Prefetch(
                            "sku__sku_attribute_options",
                            queryset=SKUAttributeOption.objects.select_related(
                                "attribute_option",
                                "attribute_option__attribute"
                            )
                        ),
                        Prefetch(
                            "sku__commodity_variant__rates",
                            queryset=CommodityRate.objects.order_by("-effective_date")
                        )
                    )
                )
            )
            .first()
        )

        wishlist = (
            Wishlist.objects.filter(user=user)
            .select_related("sku", "sku__commodity_variant")
            .prefetch_related(
                Prefetch(
                    "sku__media",
                    queryset=ProductMedia.objects.order_by("sort_order")
                ),
                Prefetch(
                    "sku__sku_attribute_options",
                    queryset=SKUAttributeOption.objects.select_related(
                        "attribute_option",
                        "attribute_option__attribute"
                    )
                ),
            )
        )

        shipping_addresses = ShippingAddress.objects.filter(user=user, is_active=True)

        data = {
            "user": UserSerializer(user).data,
            "shipping_addresses": ShippingAddressSerializer(shipping_addresses, many=True).data,
            "cart": CartSerializer(cart).data if cart else None,
            "wishlist": WishlistSerializer(wishlist, many=True).data
        }

        return Response(data, status=status.HTTP_200_OK)


# class UserUpdateAPIView(APIView):
#     permission_classes = [IsAuthenticated]

#     def put(self, request):
#         user = request.user
#         serializer = UserUpdateSerializer(user, data=request.data, partial=True)

#         if serializer.is_valid():
#             updated_data = serializer.validated_data

#             # Trigger OTP if email changed
#             if "email" in updated_data and updated_data["email"] != user.email:
#                 otp = _otp_code()  # 4-digit OTP
#                 key = otp_cache_key(updated_data["email"])

#                 cache.set(key, otp, timeout=600)  # valid for 10 mins
#                 # TODO: Replace with email or SMS send
#                 print(f"DEBUG OTP for {updated_data["email"]} → {otp}")  # For testing

#             # Trigger OTP if phone changed
#             if "phone" in updated_data and updated_data["phone"] != user.phone:
#                 otp = _otp_code()  # 4-digit OTP
#                 key = otp_cache_key(updated_data["phone"])

#                 cache.set(key, otp, timeout=600)  # valid for 10 mins
#                 # TODO: Replace with email or SMS send
#                 print(f"DEBUG OTP for {updated_data["phone"]} → {otp}")  # For testing

#             serializer.save()

#             return Response(
#                 {
#                     "message": "Profile updated. Verification required if email/phone changed.",
#                     "user": UserSerializer(user).data
#                 },
#                 status=status.HTTP_200_OK
#             )

#         return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class RequestUpdateOTP(APIView):
    """
    Request OTP for updating email or phone
    
    Sends OTP to the user's CURRENT email or phone
    (not the new one - that comes later)
    
    POST /api/accounts/user/update/request-otp/
    {
        "update_type": "email" or "phone"
    }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        update_type = request.data.get("update_type")  # "email" or "phone"

        if not update_type or update_type not in ["email", "phone"]:
            return Response(
                {"error": "update_type must be 'email' or 'phone'"},
                status=400
            )
        # ✅ Send OTP to CURRENT contact (not new)
        if update_type == "email":
            target = user.email
            if not user.email:
                target = user.phone
                # return Response(
                #     {"error": "You don't have an email set. Please add one."},
                #     status=400
                # )

            otp = _otp_code()
            # Store OTP with "pending_email_verification" flag
            cache.set(
                otp_cache_key(f"pending_email_verification:{user.id}"),
                otp,
                timeout=600  # 10 minutes
            )
            print(f"DEBUG: OTP {otp} sent to email {target}")
            # Send OTP to current email
            # if send_otp_email(user.email, otp):
            #     print(f"DEBUG: OTP {otp} sent to email {user.email}")
            return Response({
                "message": f"OTP sent to {target}",
                "contact": target,
                "update_type": "email"
            })
            # else:
            #     return Response(
            #         {"error": "Failed to send OTP. Please try again."},
            #         status=500
            #     )

        elif update_type == "phone":
            target = user.phone
            if not user.phone:
                target = user.email
                # return Response(
                #     {"error": "You don't have a phone set. Please add one."},
                #     status=400
                # )

            otp = _otp_code()
            # Store OTP with "pending_phone_verification" flag
            cache.set(
                otp_cache_key(f"pending_phone_verification:{user.id}"),
                otp,
                timeout=600  # 10 minutes
            )
            print(f"DEBUG: OTP {otp} sent to phone {target}")

            # Send OTP to current phone
            # if send_otp_sms(user.phone, otp):
            #     print(f"DEBUG: OTP {otp} sent to phone {user.phone}")
            return Response({
                "message": f"OTP sent to {target}",
                "contact": target,
                "update_type": "phone"
            })
            # else:
            #     return Response(
            #         {"error": "Failed to send OTP. Please try again."},
            #         status=500
            #     )


# ============================================
# Step 2: Verify OTP & Update Contact
# ============================================

class VerifyUpdateOTP(APIView):
    """
    Verify OTP and update email or phone
    
    Verifies OTP sent to current contact,
    then updates to the new contact provided
    
    POST /api/accounts/user/update/verify-otp/
    {
        "otp": "1234",
        "update_type": "email" or "phone",
        "new_email": "newemail@example.com" (if email),
        "new_phone": "+1234567890" (if phone)
    }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        otp = request.data.get("otp")
        update_type = request.data.get("update_type")
        new_email = request.data.get("new_email")
        new_phone = request.data.get("new_phone")

        if not otp:
            return Response(
                {"error": "OTP is required"},
                status=400
            )

        if not update_type or update_type not in ["email", "phone"]:
            return Response(
                {"error": "update_type must be 'email' or 'phone'"},
                status=400
            )

        # ============================================
        # Verify Email Update
        # ============================================
        if update_type == "email":
            if not new_email:
                return Response(
                    {"error": "new_email is required"},
                    status=400
                )

            # Check if OTP is valid
            cache_key = otp_cache_key(f"pending_email_verification:{user.id}")
            cached_otp = cache.get(cache_key)

            if cached_otp is None:
                return Response(
                    {"error": "OTP expired. Please request a new one."},
                    status=400
                )

            if str(cached_otp) != str(otp):
                return Response(
                    {"error": "Invalid OTP. Please try again."},
                    status=400
                )

            # ✅ OTP is valid, update email
            user.email = new_email
            user.save()

            # Clear the OTP from cache
            cache.delete(cache_key)

            from accounts.serializers import UserSerializer
            return Response({
                "message": "Email updated successfully",
                "user": UserSerializer(user).data
            })

        # ============================================
        # Verify Phone Update
        # ============================================
        elif update_type == "phone":
            if not new_phone:
                return Response(
                    {"error": "new_phone is required"},
                    status=400
                )

            # Check if OTP is valid
            cache_key = otp_cache_key(f"pending_phone_verification:{user.id}")
            cached_otp = cache.get(cache_key)

            if cached_otp is None:
                return Response(
                    {"error": "OTP expired. Please request a new one."},
                    status=400
                )

            if str(cached_otp) != str(otp):
                return Response(
                    {"error": "Invalid OTP. Please try again."},
                    status=400
                )

            # ✅ OTP is valid, update phone
            user.phone = new_phone
            user.save()

            # Clear the OTP from cache
            cache.delete(cache_key)

            from accounts.serializers import UserSerializer
            return Response({
                "message": "Phone updated successfully",
                "user": UserSerializer(user).data
            })




class ShippingAddressListCreateAPIView(ListCreateAPIView):
    serializer_class = ShippingAddressSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return ShippingAddress.objects.filter(user=self.request.user, is_active=True)

    def perform_create(self, serializer):
        user = self.request.user

        # If creating a new default address → remove default from others
        if serializer.validated_data.get("is_default", False):
            ShippingAddress.objects.filter(user=user, is_default=True).update(is_default=False)

        serializer.save(user=user)


class ShippingAddressDetailAPIView(RetrieveUpdateDestroyAPIView):
    serializer_class = ShippingAddressSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "id"

    def get_queryset(self):
        return ShippingAddress.objects.filter(user=self.request.user, is_active=True)

    def perform_update(self, serializer):
        instance = self.get_object()

        # If new "is_default=True" → unset every other default
        if "is_default" in serializer.validated_data:
            if serializer.validated_data["is_default"]:
                ShippingAddress.objects.filter(
                    user=self.request.user, is_default=True
                ).exclude(id=instance.id).update(is_default=False)

        serializer.save()



class CartAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        cart, _ = Cart.objects.get_or_create(user=request.user, is_active=True)
        return Response(CartSerializer(cart).data)


class CartAddItemAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        sku_id = request.data.get("sku_id")
        quantity = int(request.data.get("quantity", 1))

        if not sku_id:
            return Response({"error": "sku_id is required"}, status=400)

        if quantity <= 0:
            return Response({"error": "Quantity must be > 0"}, status=400)

        sku = get_object_or_404(ProductSKU, id=sku_id)

        if sku.stock_qty < quantity:
            return Response({"error": "Insufficient stock"}, status=400)

        cart, _ = Cart.objects.get_or_create(user=request.user, is_active=True)

        with transaction.atomic():

            cart_item, created = CartItem.objects.get_or_create(
                cart=cart,
                sku=sku,
                defaults={"quantity": quantity, "price_snapshot": sku.price},
            )

            if not created:
                if sku.stock_qty < (cart_item.quantity + quantity):
                    return Response(
                        {"error": "Insufficient stock for total quantity"}, status=400
                    )
                cart_item.quantity += quantity
                cart_item.price_snapshot = sku.price
                cart_item.save()

        return Response(CartSerializer(cart).data)


class CartUpdateItemAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        sku_id = request.data.get("sku_id")
        quantity = int(request.data.get("quantity", 1))

        cart = get_object_or_404(Cart, user=request.user, is_active=True)
        sku = get_object_or_404(ProductSKU, id=sku_id)

        # Remove item if quantity <= 0
        if quantity <= 0:
            CartItem.objects.filter(cart=cart, sku=sku).delete()
            return Response(CartSerializer(cart).data)

        # Stock validation
        if sku.stock_qty < quantity:
            return Response({"error": "Insufficient stock"}, status=400)

        cart_item = get_object_or_404(CartItem, cart=cart, sku=sku)
        cart_item.quantity = quantity
        cart_item.price_snapshot = sku.price
        cart_item.save()

        return Response(CartSerializer(cart).data)


class CartRemoveItemAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        sku_id = request.data.get("sku_id")

        cart = get_object_or_404(Cart, user=request.user, is_active=True)
        CartItem.objects.filter(cart=cart, sku_id=sku_id).delete()

        return Response(CartSerializer(cart).data)


class WishlistAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = Wishlist.objects.filter(user=request.user, is_active=True)
        return Response(WishlistSerializer(qs, many=True).data)

    def post(self, request):
        serializer = WishlistSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(user=request.user)
        return Response(serializer.data, status=201)

class WishlistRemoveAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        sku_id = request.data.get("sku_id")
        Wishlist.objects.filter(user=request.user, sku_id=sku_id).delete()
        return Response({"message": "Removed"})

class WishlistMoveToCartAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        sku_id = request.data.get("sku_id")

        wishlist_item = get_object_or_404(
            Wishlist, user=request.user, sku_id=sku_id, is_active=True
        )

        sku = wishlist_item.sku

        if sku.stock_qty < 1:
            return Response({"error": "Insufficient stock"}, status=400)

        cart, _ = Cart.objects.get_or_create(user=request.user, is_active=True)

        with transaction.atomic():
            item, created = CartItem.objects.get_or_create(
                cart=cart,
                sku=sku,
                defaults={"quantity": 1, "price_snapshot": sku.price},
            )
            if not created:
                item.quantity += 1
                item.price_snapshot = sku.price
                item.save()

            wishlist_item.delete()

        return Response({"message": "Moved to cart"})


# PUBLIC: Get Verified Reviews
class ProductReviewListAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, sku_id):
        reviews = ProductReview.objects.filter(
            sku_id=sku_id,
            is_active=True,
            is_verified_purchase=True
        ).select_related("user").order_by("-created_at")

        serializer = ProductReviewSerializer(reviews, many=True)
        return Response(serializer.data)


# USER: Add / Update Review
class ProductReviewCreateUpdateAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, sku_id):
        sku = get_object_or_404(ProductSKU, id=sku_id)

        serializer = ProductReviewSerializer(
            data=request.data,
            context={"request": request}
        )

        if serializer.is_valid():
            serializer.save(sku=sku)
            return Response(
                {"success": True, "message": "Review submitted successfully"},
                status=status.HTTP_201_CREATED
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, sku_id):
        review = get_object_or_404(
            ProductReview,
            sku_id=sku_id,
            user=request.user
        )

        serializer = ProductReviewSerializer(
            review,
            data=request.data,
            partial=True,
            context={"request": request}
        )

        if serializer.is_valid():
            serializer.save(is_verified_purchase=False)  # re-verify on edit
            return Response(
                {"success": True, "message": "Review updated. Awaiting verification"}
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# USER: Delete Review
class ProductReviewDeleteAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, sku_id):
        review = get_object_or_404(
            ProductReview,
            sku_id=sku_id,
            user=request.user
        )
        review.delete()
        return Response(
            {"success": True, "message": "Review deleted"},
            status=status.HTTP_200_OK
        )
