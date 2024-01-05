from django.contrib.auth import get_user_model
from django.contrib.auth.models import update_last_login
from django.db import IntegrityError
from drf_spectacular.utils import extend_schema_view, extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from apps.core import serializers
from apps.core.models import UserVerification
from apps.core.services.email.email_service import EmailService
from apps.core.services.token_service import TokenService


# TODO write swagger docs
# TODO write all unittest
@extend_schema_view(
    create=extend_schema(
        tags=["User Management"],
        summary="Add or register a new user",
        description="""## Register a new user by email and password, then send an OTP code to the user's email address.
    
Generate an account activation code for a user whose account is not yet enabled.

The account activation code generated by this endpoint is designed for one-time use and will expire after 5 minutes. 
If a new POST request is made to this endpoint, a new code will be generated if the previous code has expired. The newly
 generated code will be valid for another 5 minutes, while the previous code will no longer be valid.

Following the registration request, this endpoint will send an OTP code to the user's email address. It is essential to 
verify this OTP code using the `/auth/users/activation/` endpoint. Verification confirms the user's email address and 
activates their account.
 
Please note that users cannot log in to their accounts until their email addresses are verified.
""",
    ),
    list=extend_schema(
        tags=["User Management"],
        summary="",
        description="",
    ),
    retrieve=extend_schema(
        tags=["User Management"],
        summary="",
        description="",
    ),
    update=extend_schema(
        tags=["User Management"],
        summary="",
        description="",
    ),
    partial_update=extend_schema(
        tags=["User Management"],
        summary="",
        description="",
    ),
    destroy=extend_schema(
        tags=["User Management"],
        summary="",
        description="",
    ),
    activation=extend_schema(
        tags=["User Activation"],
        summary="Confirm User Registration",
        description="""Verify a new user registration by confirming the provided One-Time Password (OTP).
        This action confirms the user's email address and activates their account.""",
    ),
    resend_activation=extend_schema(
        tags=["User Activation"],
        summary="Resend OTP for Registration Confirmation",
        description="""Resend the One-Time Password (OTP) to the user's email for confirming their registration.
        This action allows the user to receive a new OTP in case the previous one was not received or expired.""",
    ),
)
class UserViewSet(ModelViewSet):
    queryset = get_user_model().objects.all()
    serializer_class = serializers.UserSerializer

    ACTION_PERMISSIONS = {
        "create": [AllowAny()],
        "list": [IsAdminUser()],
        "retrieve": [IsAdminUser()],
        "update": [IsAdminUser()],
        "partial_update": [IsAdminUser()],
        "destroy": [IsAdminUser()],
        "me": [IsAuthenticated()],
        "change_email": [IsAuthenticated()],
        "change_email_conformation": [IsAuthenticated()],
        "change_password": [IsAuthenticated()],
    }

    ACTION_SERIALIZERS = {
        "create": serializers.UserCreateSerializer,
        "activation": serializers.ActivationSerializer,
        "me": serializers.MeSerializer,
        "resend_activation": serializers.ResendActivationSerializer,
        "change_email": serializers.ChangeEmailSerializer,
        "change_email_conformation": serializers.ChangeEmailConformationSerializer,
        "reset_password": serializers.ResetPasswordSerializer,
        "reset_password_conformation": serializers.ResetPasswordConformationSerializer,
        "change_password": serializers.ChangePasswordSerializer,
    }

    def get_permissions(self):
        #  If the action is not in the dictionary, it falls back to the default permission class/.
        return self.ACTION_PERMISSIONS.get(self.action, super().get_permissions())

    def get_serializer_class(self):
        # If the action is not in the dictionary, it falls back to the default serializer class.
        return self.ACTION_SERIALIZERS.get(self.action, self.serializer_class)

    def get_instance(self):
        return self.request.user

    def create(self, request, *args, **kwargs):
        """
        Endpoint for creating a new user with the provided data.

        Returns:
        - Returns a response containing the user ID and email upon successful user creation.

        Raises:
        - If the user is already authenticated and not an admin, a 403 Forbidden response is returned.
        - If the provided data is invalid, a 400 Bad Request response is returned.
        - If a user with the provided email already exists, a 400 Bad Request response is returned.
        - If there are issues with creating the user, an appropriate error response is returned.
        """

        # Check user permissions
        if request.user.is_authenticated and not request.user.is_staff:
            return Response(
                {"detail": "You do not have permission to perform this action."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Validate input data
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user_data = serializer.validated_data

        # Create user
        try:
            user = get_user_model().objects.create_user(is_active=False, **user_data)

            # Build response body
            response_body = {
                "id": user.id,
                "email": user.email,
            }
            return Response(response_body, status=status.HTTP_201_CREATED)

        # Handle duplicate email
        except IntegrityError:
            return Response(
                {"error": "User with this email already exists."},
                status=status.HTTP_400_BAD_REQUEST,
            )

    # -----------------------------
    # --- activate user account ---
    # -----------------------------

    @action(["patch"], detail=False)
    def activation(self, request, *args, **kwargs):
        """
        Endpoint for activate the user's account after email verification and provide JWT tokens for authentication.

        Returns:
        - Returns a response containing JWT tokens and a success message upon successful account activation.

        Raises:
        - If the provided data is invalid, a 400 Bad Request response is returned.
        - If there are issues with updating the user or creating JWT tokens, an appropriate error response is returned.

        """

        # --- validate ---
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data

        # --- update user ---
        user.is_active = True
        user.save()
        update_last_login(None, user)

        # --- Create JWT tokens ---
        access_token, refresh_token = TokenService.jwt_get_tokens(user)
        response_body = {
            "access": str(access_token),
            "refresh": str(refresh_token),
            "message": "Your email address has been confirmed. Account activated successfully.",
        }

        return Response(response_body, status=status.HTTP_200_OK)

    @action(["post"], url_path="resend-activation", detail=False)
    def resend_activation(self, request, *args, **kwargs):
        """
        Endpoint for resending the activation email to the user's email.

        Returns:
        - Returns a response indicating the success of the activation email resend.

        Raises:
        - If the user's email is already activated, a 400 Bad Request response is returned.
        - If there are issues with sending the activation email, an appropriate error response is returned.

        """

        # --- validate ---
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data

        # --- send email ---
        if not user.is_active:
            EmailService.send_activation_email(user.email)
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(
            {"detail": "This user is already activated."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ----------
    # --- me ---
    # ----------
    @extend_schema(
        tags=["User Profile"],
        summary="",
        description="",
    )
    @action(["get", "put", "patch"], detail=False)
    def me(self, request, *args, **kwargs):
        """
        Endpoint for managing the authenticated user's profile.

        GET:
        Retrieve details of the authenticated user.

        PUT:
        Update the details of the authenticated user.

        PATCH:
        Partially update the details of the authenticated user.

        Returns:
        - For GET: Returns a response with the details of the authenticated user.
        - For PUT: Returns a response indicating the success of the update.
        - For PATCH: Returns a response indicating the success of the partial update.

        """

        self.get_object = self.get_instance
        if request.method == "GET":
            return self.retrieve(request, *args, **kwargs)
        elif request.method == "PUT":
            return self.update(request, *args, **kwargs)
        elif request.method == "PATCH":
            return self.partial_update(request, *args, **kwargs)
        # elif request.method == 'DELETE':
        #     return self.destroy(request, *args, **kwargs)

    # --------------------
    # --- change email ---
    # --------------------

    @extend_schema(
        tags=["User Profile"],
        summary="",
        description="",
    )
    @action(
        ["post"],
        url_path="me/change-email",
        detail=False,
    )
    def change_email(self, request, *args, **kwargs):
        """
        Endpoint for initiating the process of changing the authenticated user's email.

        POST:
        Send an OTP code to the new email address and save the new email in the UserVerification model.

        Returns:
        - Returns a response indicating the success of the email change initiation.

        Raises:
        - If the user is not authenticated, a 403 Forbidden response is returned.
        - If there are issues with sending the change email confirmation, an appropriate error response is returned.

        """

        # --- validate ---
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_email = serializer.validated_data

        # --- save email nad send mail to new-email ---
        UserVerification.objects.update_or_create(
            user=request.user, new_email=new_email
        )
        EmailService.send_change_email(new_email)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        tags=["User Profile"],
        summary="",
        description="",
    )
    @action(["post"], url_path="me/change-email/conformation", detail=False)
    def change_email_conformation(self, request, *args, **kwargs):
        """
        Endpoint for confirming the change of the authenticated user's email.

        POST:
        Update the user's email to the new email after confirming the provided OTP.

        Returns:
        - Returns a response indicating the success of the email change confirmation.

        Raises:
        - If the user is not authenticated, a 403 Forbidden response is returned.
        - If the provided OTP is invalid, a 400 Bad Request response is returned.
        - If the entered email does not match the requested email, a 400 Bad Request response is returned.

        """

        # --- validate ---
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_email = serializer.validated_data

        # --- get current user verification ---
        user_verification = UserVerification.objects.get(user=request.user)
        if user_verification.new_email == new_email:
            # --- Update the user's email ---
            user = request.user
            user.email = new_email
            user.save()

            user_verification.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        else:
            return Response(
                {"detail": "The email entered does not match the requested email."},
                status=status.HTTP_400_BAD_REQUEST,
            )

    # -----------------------
    # --- change password ---
    # -----------------------

    @extend_schema(
        tags=["User Profile"],
        summary="",
        description="",
    )
    @action(["post"], url_path="me/change-password", detail=False)
    def change_password(self, request, *args, **kwargs):
        # --- validate ---
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # --- set new password ---
        self.request.user.set_password(serializer.validated_data["new_password"])
        self.request.user.save()

        # logout_user(self.request)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        tags=["User Profile"],
        summary="",
        description="",
    )
    @action(["post"], url_path="me/reset-password", detail=False)
    def reset_password(self, request, *args, **kwargs):
        # --- validate ---
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data

        # --- send email ---
        if user.is_active:
            EmailService.send_reset_password_email(user.email)
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response(
            {"detail": "first activate you account"}, status=status.HTTP_400_BAD_REQUEST
        )

    @extend_schema(
        tags=["User Profile"],
        summary="",
        description="",
    )
    @action(["post"], url_path="me/reset-password/conformation", detail=False)
    def reset_password_conformation(self, request, *args, **kwargs):
        # --- validate ---
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user, new_password = serializer.validated_data

        # --- set new password ---
        user.set_password(new_password)
        user.save()

        return Response(status=status.HTTP_204_NO_CONTENT)
