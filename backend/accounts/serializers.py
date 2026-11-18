from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.db import transaction

from rest_framework import serializers

from .models import Profile

User = get_user_model()

class RegistrationSerializer(serializers.Serializer):

    first_name = serializers.CharField(max_length=150)

    last_name = serializers.CharField(
        max_length=150,
        required=False,
        allow_blank=True
    )

    username = serializers.CharField(
        max_length=150,
        validators=[UnicodeUsernameValidator()]
    )

    email = serializers.EmailField()

    password = serializers.CharField(
        write_only=True,
        validators=[validate_password]
    )

    confirm_password = serializers.CharField(write_only=True)

    def validate_username(self, value):
        value = value.strip()

        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError(
                "This username is already taken."
            )

        return value

    def validate_email(self, value):
        value = value.strip().lower()

        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError(
                "An account with this email already exists."
            )

        return value

    def validate(self, attrs):
        if attrs['password'] != attrs['confirm_password']:
            raise serializers.ValidationError({
                "confirm_password": "Passwords do not match."
            })

        return attrs

    @transaction.atomic
    def create(self, validated_data):

        validated_data.pop('confirm_password')
        password = validated_data.pop('password')

        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=password,
            first_name=validated_data['first_name'],
            last_name=validated_data.get('last_name', '')
        )

        Profile.objects.create(
            user=user,
            role='LEARNER'
        )

        return user

    def to_representation(self, instance):
        return {
            "id": instance.id,
            "first_name": instance.first_name,
            "last_name": instance.last_name,
            "username": instance.username,
            "email": instance.email,
            "role": instance.profile.role,
        }


class LoginSerializer(serializers.Serializer):

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):

        request = self.context.get('request')

        user = authenticate(
            request=request,
            email=attrs['email'].strip(),
            password=attrs['password']
        )

        if user is None:
            raise serializers.ValidationError(
                "Invalid email or password."
            )

        attrs['user'] = user

        return attrs


class AccountDeletionRequestSerializer(serializers.Serializer):

    replacement_email = serializers.EmailField(
        required=False,
        allow_blank=True
    )

    def validate_replacement_email(self, value):
        return value.strip().lower()
