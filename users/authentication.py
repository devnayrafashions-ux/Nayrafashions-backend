from django.conf import settings
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, AuthenticationFailed


class CookieJWTAuthentication(JWTAuthentication):
    """
    Same as SimpleJWT's default JWTAuthentication, but reads the access
    token from an httpOnly cookie instead of the Authorization header.
    Falls back to the header if present (so tools like admin scripts,
    Postman, or mobile-app clients that still send Bearer tokens keep
    working without change).
    """

    def authenticate(self, request):
        # Prefer Authorization header if a client sends one (e.g. a
        # future native mobile app using Bearer tokens instead of cookies).
        header = self.get_header(request)
        if header is not None:
            raw_token = self.get_raw_token(header)
        else:
            cookie_name = getattr(settings, 'SIMPLE_JWT', {}).get(
                'AUTH_COOKIE_ACCESS', 'access_token'
            )
            raw_token = request.COOKIES.get(cookie_name)

        if raw_token is None:
            return None

        try:
            validated_token = self.get_validated_token(raw_token)
        except InvalidToken:
            raise AuthenticationFailed('Access token invalid or expired')

        return self.get_user(validated_token), validated_token