from django.contrib.auth import get_user_model
from django.contrib.auth.models import update_last_login
from django.db import IntegrityError
from drf_spectacular.utils import extend_schema_view, extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet
from rest_framework_simplejwt.tokens import RefreshToken, AccessToken

from apps.core import serializers
from apps.core.managers.user_manager import UserManager

User = get_user_model()


@extend_schema_view(
    create=extend_schema(
        summary='Add or register a new user',
        description="""## Register a new user by email and password, then send an OTP code to the user's email address.
    
Generate an account activation code for a user whose account is not yet enabled.

The account activation code generated by this endpoint is designed for one-time use and will expire after 5 minutes. 
If a new POST request is made to this endpoint, a new code will be generated if the previous code has expired. The newly
 generated code will be valid for another 5 minutes, while the previous code will no longer be valid.

Following the registration request, this endpoint will send an OTP code to the user's email address. It is essential to 
verify this OTP code using the `/accounts/register/verify` endpoint. Verification confirms the user's email address and 
activates their account.
 
Please note that users cannot log in to their accounts until their email addresses are verified.
""",
    ),
    activation=extend_schema(
        summary='Verify user registration',
        description='Verify a new user registration by confirming the provided OTP.',
    ),
)
class UserViewSet(ModelViewSet):
    queryset = User.objects.all()
    serializer_class = serializers.UserSerializer

    # permission_classes = [IsAdminUser]

    def get_permissions(self):
        if self.action == 'create':
            # Allow registration for non-authenticated users and admins
            return [AllowAny()]
        elif self.action in ['list', 'retrieve', 'update', 'partial_update', 'destroy']:
            # Restrict listing, retrieving, updating, and deleting to admin users only
            return [IsAdminUser()]
        else:
            # For other actions, use the default permissions
            return super().get_permissions()

    def get_serializer_class(self):
        if self.action == 'create':
            return serializers.UserCreateSerializer
        elif self.action == 'activation':
            return serializers.ActivationSerializer
        return self.serializer_class

    def create(self, request, *args, **kwargs):

        if request.user.is_authenticated and not request.user.is_staff:
            return Response({"detail": "You do not have permission to perform this action."},
                            status=status.HTTP_403_FORBIDDEN)

        # --- validate ---
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user_data = serializer.validated_data

        # --- create user ---
        try:
            user = UserManager.create_inactive_user(**user_data)

            response_body = {
                'user_id': user.id,
                'email': user.email,
            }

            return Response(response_body, status=status.HTTP_201_CREATED)

        except IntegrityError:
            return Response({'error': 'User with this email already exists.'}, status=status.HTTP_400_BAD_REQUEST)

    @action(['patch'], detail=False)
    def activation(self, request, *args, **kwargs):

        # --- validate ---
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data

        # --- update user ---
        user.is_active = True
        user.save()
        update_last_login(None, user)

        # --- Create JWT tokens ---
        refresh_token = RefreshToken.for_user(user)
        access_token = AccessToken.for_user(user)
        response_body = {
            'access': str(access_token),
            'refresh': str(refresh_token),
            'message': 'Your email address has been confirmed. Account activated successfully.'
        }

        return Response(response_body, status=status.HTTP_200_OK)
