"""
WorkOS Authentication Service

Provides functions for integrating with WorkOS AuthKit and Magic Link authentication.
"""

import os
from typing import Optional
from workos import WorkOSClient


# Initialize WorkOS client (lazy initialization to allow testing)
_workos_client: Optional[WorkOSClient] = None


def get_workos_client() -> WorkOSClient:
    """Get or create the WorkOS client instance."""
    global _workos_client
    if _workos_client is None:
        _workos_client = WorkOSClient(
            api_key=os.getenv("WORKOS_API_KEY"), client_id=os.getenv("WORKOS_CLIENT_ID")
        )
    return _workos_client


def get_auth_url(redirect_uri: str, state: str = None) -> str:
    """
    Generate a WorkOS AuthKit authorization URL.

    Args:
        redirect_uri: The callback URL for your application
        state: Optional state parameter for CSRF protection

    Returns:
        The authorization URL to redirect the user to
    """
    client = get_workos_client()
    params = {
        "provider": "authkit",
        "redirect_uri": redirect_uri,
    }
    if state:
        params["state"] = state

    return client.user_management.get_authorization_url(**params)


def get_magic_link_url(email: str, redirect_uri: str) -> str:
    """
    Generate a Magic Link authorization URL for passwordless authentication.

    Args:
        email: The user's email address
        redirect_uri: The callback URL for your application

    Returns:
        The authorization URL to redirect the user to
    """
    client = get_workos_client()
    return client.user_management.get_authorization_url(
        provider="authkit", redirect_uri=redirect_uri, login_hint=email
    )


def authenticate_callback(code: str) -> dict:
    """
    Exchange an authorization code for user information and tokens.

    Args:
        code: The authorization code returned by WorkOS

    Returns:
        Dictionary containing user info and tokens
    """
    client = get_workos_client()
    return client.user_management.authenticate_with_code(code=code)


def create_workos_user(
    email: str, first_name: str = None, last_name: str = None
) -> dict:
    """
    Create a new user in WorkOS.

    Args:
        email: The user's email address
        first_name: Optional first name
        last_name: Optional last name

    Returns:
        The created WorkOS user object
    """
    client = get_workos_client()
    return client.user_management.create_user(
        email=email,
        first_name=first_name,
        last_name=last_name,
        email_verified=True,
        send_invitation=True,
    )


def get_logout_url(session_id: str = None) -> str:
    """
    Generate a WorkOS logout URL.

    Args:
        session_id: Optional session ID to invalidate

    Returns:
        The logout URL to redirect the user to
    """
    client = get_workos_client()
    if session_id:
        return client.user_management.get_logout_url(session_id=session_id)
    # Return the generic logout URL (configured in WorkOS dashboard)
    return "https://auth.workos.com/sign_out"
