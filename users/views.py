from django.conf import settings
from django.middleware.csrf import get_token
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from .models import CustomUser
from .serializers import UserSerializer, RegisterSerializer, CustomTokenSerializer

ACCESS_COOKIE = settings.SIMPLE_JWT.get('AUTH_COOKIE_ACCESS', 'access_token')
REFRESH_COOKIE = settings.SIMPLE_JWT.get('AUTH_COOKIE_REFRESH', 'refresh_token')


def _set_auth_cookies(response, access=None, refresh=None):
    if access is not None:
        response.set_cookie(
            ACCESS_COOKIE,
            str(access),
            max_age=int(settings.SIMPLE_JWT['ACCESS_TOKEN_LIFETIME'].total_seconds()),
            httponly=True,
            secure=settings.COOKIE_SECURE,
            samesite=settings.COOKIE_SAMESITE,
            path='/',
        )
    if refresh is not None:
        response.set_cookie(
            REFRESH_COOKIE,
            str(refresh),
            max_age=int(settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME'].total_seconds()),
            httponly=True,
            secure=settings.COOKIE_SECURE,
            samesite=settings.COOKIE_SAMESITE,
            # Scoped so this cookie only goes out on the refresh call,
            # not on every request.
            path='/api/auth/token/refresh/',
        )
    return response


def _clear_auth_cookies(response):
    # IMPORTANT: samesite must match what was used in _set_auth_cookies.
    # Browsers won't let a Set-Cookie without SameSite=None; Secure
    # overwrite/delete a cookie that was originally set with those
    # attributes — the deletion is silently ignored otherwise, which
    # is exactly the "logout doesn't work" bug this fixes.
    response.delete_cookie(ACCESS_COOKIE, path='/', samesite=settings.COOKIE_SAMESITE)
    response.delete_cookie(
        REFRESH_COOKIE, path='/api/auth/token/refresh/', samesite=settings.COOKIE_SAMESITE
    )
    return response


class RegisterView(generics.CreateAPIView):
    queryset = CustomUser.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        # Auto-login after register: issue tokens as cookies instead
        # of in the response body.
        refresh = RefreshToken.for_user(user)
        response = Response(
            {'user': UserSerializer(user).data},
            status=status.HTTP_201_CREATED,
        )
        get_token(request)  # ensures the CSRF cookie gets set on this response
        return _set_auth_cookies(response, refresh.access_token, refresh)


class CustomLoginView(TokenObtainPairView):
    """
    Same validation as before (via CustomTokenSerializer), but strips
    access/refresh out of the response body and sets them as httpOnly
    cookies instead. Any extra fields your CustomTokenSerializer adds
    to validated_data (e.g. user info) still come back in the body.
    """
    serializer_class = CustomTokenSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        access = serializer.validated_data.pop('access', None)
        refresh = serializer.validated_data.pop('refresh', None)

        response = Response(serializer.validated_data, status=status.HTTP_200_OK)
        get_token(request)  # ensures the CSRF cookie gets set on this response
        return _set_auth_cookies(response, access, refresh)


class CookieTokenRefreshView(TokenRefreshView):
    """
    Reads the refresh token from the httpOnly cookie (not the request
    body), then reuses SimpleJWT's own TokenRefreshSerializer so
    ROTATE_REFRESH_TOKENS / BLACKLIST_AFTER_ROTATION behave exactly as
    configured in settings.
    """

    def post(self, request, *args, **kwargs):
        raw_refresh = request.COOKIES.get(REFRESH_COOKIE)
        if raw_refresh is None:
            return Response({'detail': 'No refresh token'}, status=status.HTTP_401_UNAUTHORIZED)

        serializer = self.get_serializer(data={'refresh': raw_refresh})
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError:
            response = Response(
                {'detail': 'Refresh token invalid or expired'},
                status=status.HTTP_401_UNAUTHORIZED,
            )
            return _clear_auth_cookies(response)

        access = serializer.validated_data.get('access')
        # Only present if ROTATE_REFRESH_TOKENS is True in settings.
        new_refresh = serializer.validated_data.get('refresh')

        response = Response({'detail': 'refreshed'})
        return _set_auth_cookies(response, access, new_refresh)


class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        raw_refresh = request.COOKIES.get(REFRESH_COOKIE)
        if raw_refresh:
            try:
                RefreshToken(raw_refresh).blacklist()
            except TokenError:
                pass  # already invalid/expired — fine, we're clearing cookies anyway
        response = Response({'detail': 'logged out'})
        return _clear_auth_cookies(response)


class ProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user