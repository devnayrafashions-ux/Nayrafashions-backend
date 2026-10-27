from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from .models import CustomUser

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = [
            'id', 'email', 'username', 'first_name', 'last_name',
            'phone', 'profile_picture', 'address_line1', 'address_line2',
            'city', 'state', 'pincode', 'date_joined',
            'is_staff', 'is_superuser'  # ← add these
        ]
        read_only_fields = ['id', 'date_joined', 'is_staff', 'is_superuser']

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True)

    class Meta:
        model = CustomUser
        fields = ['email', 'first_name', 'last_name',
                  'password', 'confirm_password', 'phone']

    def validate(self, data):
        if data['password'] != data['confirm_password']:
            raise serializers.ValidationError("Passwords do not match.")
        return data

    def create(self, validated_data):
        validated_data.pop('confirm_password')
        # FIX: previously used validated_data['email'].split('@')[0],
        # which produces the SAME username for different emails that
        # share a prefix (e.g. admin@nayra.in and admin@nayra.com both
        # became "admin"). AbstractUser.username is unique, so the
        # second registration always hit a database IntegrityError and
        # crashed with a 500 — regardless of which email was used.
        # The email field is already guaranteed unique, so using it
        # directly as the username removes the collision entirely.
        validated_data['username'] = validated_data['email']
        user = CustomUser.objects.create_user(**validated_data)
        return user

class CustomTokenSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        email = attrs.get(self.username_field)

        if email and not CustomUser.objects.filter(email=email).exists():
            raise serializers.ValidationError({
                'email': 'No account found with this email. Please register first.'
            })

        data = super().validate(attrs)
        data['user'] = UserSerializer(self.user).data
        return data