from datetime import timedelta
import secrets
from urllib.parse import urlencode, urlparse
import base64
import hashlib
import json

from django.contrib.auth.models import User
from django.db import connection
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.conf import settings
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes, permission_classes, throttle_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from django.shortcuts import get_object_or_404

import os
import re
import requests

from django.shortcuts import redirect
from django.utils import timezone
from django.utils.text import slugify

from .models import (
    Favorite,
    Resource,
    Tool,
    UserProfile,
    Workflow,
    Project,
    Tag,
    Task,
    Note,
    Activity,
    Snippet,
    GitHubOAuthState,
    GitHubAccount, Organization, OrganizationMembership, Notification, Comment, TaskDependency, ProjectInvite, CodeWorkspace, AIConversation, AIMessage, Subscription, APIKey,
)

from .serializers import (
    FavoriteSerializer,
    ProjectSerializer,
    ProfileUpdateSerializer,
    ResourceSerializer,
    ToolSerializer,
    WorkflowSerializer,
    TagSerializer,
    TaskSerializer,
    NoteSerializer,
    ActivitySerializer,
    SnippetSerializer,
    GitHubAccountSerializer, OrganizationSerializer, OrganizationMembershipSerializer, NotificationSerializer, CommentSerializer, TaskDependencySerializer, ProjectInviteSerializer, CodeWorkspaceSerializer, AIConversationSerializer, AIMessageSerializer, SubscriptionSerializer, APIKeySerializer,
)


class AuthRateThrottle(AnonRateThrottle):
    scope = "auth"


class AssistantRateThrottle(AnonRateThrottle):
    scope = "assistant"


def github_headers(access_token):
    return {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2026-03-10",
    }
# =========================================================
# CONFIG
# =========================================================

GITHUB_CLIENT_ID = os.environ.get("GITHUB_CLIENT_ID")
GITHUB_CLIENT_SECRET = os.environ.get("GITHUB_CLIENT_SECRET")
GITHUB_OAUTH_SCOPE = os.environ.get("GITHUB_OAUTH_SCOPE", "read:user user:email repo")

GITHUB_OAUTH_REDIRECT = os.environ.get(
    "GITHUB_OAUTH_REDIRECT",
    "http://127.0.0.1:8000/api/github/callback/"
)

FRONTEND_URL = os.environ.get(
    "FRONTEND_URL",
    "http://localhost:5173"
).rstrip("/")

frontend_url_parts = urlparse(FRONTEND_URL)
if frontend_url_parts.scheme not in {"http", "https"} or not frontend_url_parts.netloc:
    raise ValueError("FRONTEND_URL must be an absolute http(s) URL.")

GITHUB_API_URL = "https://api.github.com"
GITHUB_TIMEOUT = (3.05, 15)


def github_service_unavailable():
    return Response(
        {"error": "GitHub is temporarily unavailable. Please try again later."},
        status=status.HTTP_502_BAD_GATEWAY,
    )


# =========================================================
# PROJECTS
# =========================================================

@api_view(["GET"])
@permission_classes([AllowAny])
def health_api(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return Response({
            "status": "ok",
            "database": "ok",
            "service": "developer-os-api",
            "version": os.environ.get("RELEASE_VERSION", "1.0.0"),
        })
    except Exception:
        return Response({"status": "degraded", "database": "unavailable"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


@api_view(["GET"])
@permission_classes([AllowAny])
def readiness_api(request):
    """Deployment readiness probe: DB plus mandatory production configuration."""
    checks = {"database": False, "secret_key": False, "allowed_hosts": False}
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        checks["database"] = True
    except Exception:
        pass
    checks["secret_key"] = bool(settings.SECRET_KEY and not settings.SECRET_KEY.startswith("django-insecure-"))
    checks["allowed_hosts"] = bool(settings.ALLOWED_HOSTS and settings.ALLOWED_HOSTS != ["*"])
    ready = all(checks.values()) if not settings.DEBUG else checks["database"]
    return Response({"status": "ready" if ready else "not_ready", "checks": checks, "version": os.environ.get("RELEASE_VERSION", "1.0.0")}, status=status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def projects_api(request):

    if request.method == "GET":
        projects = Project.objects.filter(
            Q(owner=request.user) | Q(collaborators=request.user)
        ).distinct().annotate(
            task_count=Count("tasks"),
            completed_task_count=Count("tasks", filter=Q(tasks__status="done")),
        ).order_by("-created_at")

        serializer = ProjectSerializer(projects, many=True)
        return Response(serializer.data)

    if request.method == "POST":
        serializer = ProjectSerializer(data=request.data)

        if serializer.is_valid():
            project = serializer.save(owner=request.user)
            Activity.objects.create(actor=request.user, verb="created a project", message=project.title, related_type="project", related_id=project.id, metadata={"category": project.category})
            return Response(ProjectSerializer(project).data, status=status.HTTP_201_CREATED)

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )


@api_view(["GET", "PUT", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def project_detail_api(request, pk):

    project_obj = get_object_or_404(Project.objects.filter(Q(owner=request.user) | Q(collaborators=request.user)).distinct(), pk=pk)

    if request.method == "GET":
        project_obj = Project.objects.annotate(
            task_count=Count("tasks"),
            completed_task_count=Count("tasks", filter=Q(tasks__status="done")),
        ).get(pk=project_obj.pk)
        serializer = ProjectSerializer(project_obj)
        return Response(serializer.data)

    if request.method in ["PUT", "PATCH"]:
        if project_obj.owner_id != request.user.id:
            return Response({"error": "Only the project owner can edit this project."}, status=status.HTTP_403_FORBIDDEN)
        serializer = ProjectSerializer(
            project_obj,
            data=request.data,
            partial=request.method == "PATCH"
        )

        if serializer.is_valid():
            updated = serializer.save(owner=request.user)
            Activity.objects.create(actor=request.user, verb="updated a project", message=updated.title, related_type="project", related_id=updated.id, metadata={"status": updated.status, "progress": ProjectSerializer(updated).data.get("progress", 0)})
            return Response(ProjectSerializer(updated).data)

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )

    if request.method == "DELETE":
        if project_obj.owner_id != request.user.id:
            return Response({"error": "Only the project owner can delete this project."}, status=status.HTTP_403_FORBIDDEN)
        title = project_obj.title
        project_obj.delete()
        Activity.objects.create(actor=request.user, verb="deleted a project", message=title, related_type="project", related_id=pk)
        return Response(status=status.HTTP_204_NO_CONTENT)


# =========================================================
# SESSION
# =========================================================

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def logout_api(request):
    """Blacklist the presented refresh token so logout also invalidates it."""
    refresh_token = request.data.get("refresh")
    if not isinstance(refresh_token, str) or not refresh_token:
        return Response({"error": "refresh is required."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        token = RefreshToken(refresh_token)
        if str(token.get("user_id")) != str(request.user.id):
            return Response({"error": "Invalid refresh token."}, status=status.HTTP_400_BAD_REQUEST)
        token.blacklist()
    except TokenError:
        return Response({"error": "Invalid refresh token."}, status=status.HTTP_400_BAD_REQUEST)

    return Response(status=status.HTTP_204_NO_CONTENT)

# =========================================================
# PROFILE
# =========================================================

@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
@parser_classes([JSONParser, FormParser, MultiPartParser])
def profile_api(request):
    user = request.user
    profile, _ = UserProfile.objects.get_or_create(user=user)

    def profile_response():
        full_name = profile.full_name or " ".join(
            filter(None, [user.first_name, user.last_name])
        ).strip()
        return Response({
            "id": user.id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "full_name": full_name,
            "avatar_url": (
                request.build_absolute_uri(profile.avatar.url)
                if profile.avatar
                else profile.avatar_url
            ),
            "has_uploaded_avatar": bool(profile.avatar),
            "bio": profile.bio,
            "github": profile.github,
            "linkedin": profile.linkedin,
            "x": profile.x,
            "website": profile.website,
        })

    if request.method == "GET":
        return profile_response()

    serializer = ProfileUpdateSerializer(data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    payload = serializer.validated_data.copy()
    uploaded_avatar = payload.pop("avatar", None)
    remove_avatar = payload.pop("remove_avatar", False)

    if "email" in payload and payload["email"] and User.objects.exclude(pk=user.pk).filter(
        email__iexact=payload["email"]
    ).exists():
        return Response({"error": "Unable to use this email address."}, status=status.HTTP_400_BAD_REQUEST)

    user_fields = {"first_name", "last_name", "email"}
    changed_user_fields = [field for field in user_fields if field in payload]
    for field in changed_user_fields:
        setattr(user, field, payload[field])
    if changed_user_fields:
        user.save(update_fields=changed_user_fields)

    profile_fields = {"full_name", "avatar_url", "bio", "github", "linkedin", "x", "website"}
    changed_profile_fields = [field for field in profile_fields if field in payload]
    for field in changed_profile_fields:
        setattr(profile, field, payload[field])

    old_avatar_name = profile.avatar.name if profile.avatar else ""
    old_avatar_storage = profile.avatar.storage if profile.avatar else None
    if uploaded_avatar:
        profile.avatar = uploaded_avatar
        changed_profile_fields.append("avatar")
    elif remove_avatar and old_avatar_name:
        profile.avatar = ""
        changed_profile_fields.append("avatar")

    if changed_profile_fields:
        profile.save(update_fields=[*changed_profile_fields, "updated_at"])

    if old_avatar_name and old_avatar_name != profile.avatar.name and old_avatar_storage:
        try:
            old_avatar_storage.delete(old_avatar_name)
        except OSError:
            # The profile update is already committed; a stale media object is
            # harmless and should not turn a successful update into an error.
            pass

    return profile_response()


# =========================================================
# REGISTER
# =========================================================

@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([AuthRateThrottle])
def register_api(request):

    username = (
        request.data.get("username") or ""
    ).strip()

    email = (
        request.data.get("email") or ""
    ).strip()

    password = (
        request.data.get("password") or ""
    )

    first_name = (
        request.data.get("first_name") or ""
    ).strip()

    last_name = (
        request.data.get("last_name") or ""
    ).strip()

    if not username or not email or not password:

        return Response(
            {
                "error": (
                    "username, email and password "
                    "are required."
                )
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        validate_email(email)
        candidate = User(username=username, email=email)
        validate_password(password, user=candidate)
    except ValidationError as error:
        return Response({"error": error.messages}, status=status.HTTP_400_BAD_REQUEST)

    # Keep the same response for every duplicate case so this endpoint cannot
    # be used to enumerate registered usernames or email addresses.
    if User.objects.filter(username__iexact=username).exists() or User.objects.filter(email__iexact=email).exists():
        return Response(
            {"error": "Unable to create an account with these details."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        with transaction.atomic():
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
            )
            UserProfile.objects.get_or_create(user=user)
    except IntegrityError:
        return Response(
            {"error": "Unable to create an account with these details."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return Response(
        {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
        },
        status=status.HTTP_201_CREATED
    )


# =========================================================
# FAVORITES
# =========================================================

@api_view(["GET", "POST", "DELETE"])
@permission_classes([IsAuthenticated])
def favorites_api(request):

    if request.method == "GET":

        favorites = Favorite.objects.filter(
            user=request.user
        ).order_by("-created_at")

        serializer = FavoriteSerializer(
            favorites,
            many=True
        )

        return Response(serializer.data)

    if request.method == "DELETE":

        tool_name = (request.data.get("tool_name") or request.query_params.get("tool_name") or "").strip()

        if not tool_name:

            return Response(
                {
                    "error": "tool_name is required."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        deleted_count, _ = Favorite.objects.filter(user=request.user, tool__name__iexact=tool_name).delete()

        if deleted_count == 0:

            return Response(
                {
                    "error": "Favorite not found."
                },
                status=status.HTTP_404_NOT_FOUND
            )

        return Response(
            status=status.HTTP_204_NO_CONTENT
        )

    tool_name = (request.data.get("tool_name") or "").strip()
    if not tool_name or len(tool_name) > 120:
        return Response({"error": "A valid tool_name is required."}, status=status.HTTP_400_BAD_REQUEST)

    # Favorites reference the staff-managed shared catalog. A regular user
    # must never be able to create or modify global Tool records here.
    tool = Tool.objects.filter(name__iexact=tool_name).first()
    if tool is None:
        return Response({"error": "Tool not found in the catalog."}, status=status.HTTP_404_NOT_FOUND)

    favorite, created = Favorite.objects.get_or_create(user=request.user, tool=tool)
    return Response(
        FavoriteSerializer(favorite).data,
        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
    )


# =========================================================
# RESOURCES
# =========================================================

@api_view(["GET", "POST"])
@permission_classes([AllowAny])
def resources_api(request):

    if request.method == "GET":

        resources = Resource.objects.all().order_by("-created_at")
        query = str(request.query_params.get("q") or "").strip()
        category = str(request.query_params.get("category") or "").strip()
        if query:
            resources = resources.filter(
                Q(title__icontains=query) |
                Q(description__icontains=query) |
                Q(category__icontains=query)
            )
        if category and category.lower() != "all":
            resources = resources.filter(category__iexact=category)

        serializer = ResourceSerializer(resources, many=True)

        return Response(serializer.data)

    if not request.user.is_staff:
        return Response({"error": "Only staff can manage the shared resource catalog."}, status=status.HTTP_403_FORBIDDEN)

    serializer = ResourceSerializer(
        data=request.data
    )

    if serializer.is_valid():

        serializer.save()

        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED
        )

    return Response(
        serializer.errors,
        status=status.HTTP_400_BAD_REQUEST
    )


# =========================================================
# WORKFLOWS
# =========================================================

@api_view(["GET", "POST"])
@permission_classes([AllowAny])
def workflows_api(request):

    if request.method == "GET":

        workflows = Workflow.objects.all().order_by("-created_at")
        query = str(request.query_params.get("q") or "").strip()
        if query:
            workflows = workflows.filter(
                Q(title__icontains=query) |
                Q(summary__icontains=query) |
                Q(level__icontains=query)
            )

        serializer = WorkflowSerializer(workflows, many=True)

        return Response(serializer.data)

    if not request.user.is_staff:
        return Response({"error": "Only staff can manage the shared workflow catalog."}, status=status.HTTP_403_FORBIDDEN)

    serializer = WorkflowSerializer(
        data=request.data
    )

    if serializer.is_valid():

        serializer.save()

        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED
        )

    return Response(
        serializer.errors,
        status=status.HTTP_400_BAD_REQUEST
    )


# =========================================================
# TOOLS
# =========================================================

@api_view(["GET"])
@permission_classes([AllowAny])
def tools_api(request):
    tools = Tool.objects.all().order_by("name")
    query = str(request.query_params.get("q") or "").strip()
    category = str(request.query_params.get("category") or "").strip()
    if query:
        tools = tools.filter(
            Q(name__icontains=query) |
            Q(tag__icontains=query) |
            Q(description__icontains=query) |
            Q(category__icontains=query)
        )
    if category and category.lower() != "all":
        tools = tools.filter(category__iexact=category)

    serializer = ToolSerializer(tools, many=True)

    return Response(serializer.data)

# =========================================================
# GLOBAL SEARCH
# =========================================================

@api_view(["GET"])
@permission_classes([AllowAny])
def global_search_api(request):
    """Search the public developer catalog from one stable endpoint."""
    query = str(request.query_params.get("q") or "").strip()
    category = str(request.query_params.get("category") or "").strip()
    if len(query) > 120:
        return Response({"error": "Search query is too long."}, status=status.HTTP_400_BAD_REQUEST)

    tools = Tool.objects.all().order_by("name")
    resources = Resource.objects.all().order_by("-created_at")
    workflows = Workflow.objects.all().order_by("-created_at")
    if query:
        tools = tools.filter(Q(name__icontains=query) | Q(tag__icontains=query) | Q(description__icontains=query) | Q(category__icontains=query))
        resources = resources.filter(Q(title__icontains=query) | Q(description__icontains=query) | Q(category__icontains=query))
        workflows = workflows.filter(Q(title__icontains=query) | Q(summary__icontains=query) | Q(level__icontains=query))
    if category and category.lower() != "all":
        tools = tools.filter(category__iexact=category)
        resources = resources.filter(category__iexact=category)

    return Response({
        "query": query,
        "results": {
            "tools": ToolSerializer(tools[:20], many=True).data,
            "resources": ResourceSerializer(resources[:20], many=True).data,
            "workflows": WorkflowSerializer(workflows[:20], many=True).data,
        },
    })

# =========================================================
# TAGS
# =========================================================

@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def tags_api(request):

    if request.method == "GET":

        tags = Tag.objects.all().order_by(
            "name"
        )

        serializer = TagSerializer(
            tags,
            many=True
        )

        return Response(serializer.data)

    if not request.user.is_staff:
        return Response({"error": "Only staff can manage shared tags."}, status=status.HTTP_403_FORBIDDEN)

    serializer = TagSerializer(
        data=request.data
    )

    if serializer.is_valid():

        serializer.save()

        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED
        )

    return Response(
        serializer.errors,
        status=status.HTTP_400_BAD_REQUEST
    )


# =========================================================
# TASKS
# =========================================================

@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def tasks_api(request):
    if request.method == "GET":
        qs = Task.objects.filter(Q(project__owner=request.user) | Q(project__collaborators=request.user)).distinct().select_related("project", "assignee").order_by("status", "due_date", "-created_at")
        project_id = request.query_params.get("project")
        status_filter = request.query_params.get("status")
        if project_id:
            qs = qs.filter(project_id=project_id)
        if status_filter:
            qs = qs.filter(status=status_filter)
        return Response(TaskSerializer(qs, many=True).data)

    project_id = request.data.get("project")
    project_obj = get_object_or_404(Project.objects.filter(Q(owner=request.user) | Q(collaborators=request.user)).distinct(), pk=project_id) if project_id else None
    if project_obj is None:
        return Response({"error": "project is required."}, status=status.HTTP_400_BAD_REQUEST)
    serializer = TaskSerializer(data=request.data)
    if serializer.is_valid():
        task = serializer.save(project=project_obj, assignee=request.user)
        Activity.objects.create(actor=request.user, verb="created a task", message=task.title, related_type="task", related_id=task.id, metadata={"project_id": project_obj.id})
        return Response(TaskSerializer(task).data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(["GET", "PATCH", "PUT", "DELETE"])
@permission_classes([IsAuthenticated])
def task_detail_api(request, pk):
    task = get_object_or_404(Task.objects.filter(Q(project__owner=request.user) | Q(project__collaborators=request.user)).distinct(), pk=pk)
    if request.method == "GET":
        return Response(TaskSerializer(task).data)
    if request.method == "DELETE":
        title = task.title
        project_id = task.project_id
        task.delete()
        Activity.objects.create(actor=request.user, verb="deleted a task", message=title, related_type="task", related_id=pk, metadata={"project_id": project_id})
        return Response(status=status.HTTP_204_NO_CONTENT)
    serializer = TaskSerializer(task, data=request.data, partial=request.method == "PATCH", context={"request": request})
    if serializer.is_valid():
        updated = serializer.save()
        Activity.objects.create(actor=request.user, verb="updated a task", message=updated.title, related_type="task", related_id=updated.id, metadata={"project_id": updated.project_id, "status": updated.status})
        return Response(TaskSerializer(updated).data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# =========================================================
# NOTES
# =========================================================

@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def notes_api(request):

    if request.method == "GET":
        notes = Note.objects.filter(Q(project__owner=request.user) | Q(project__collaborators=request.user)).distinct().order_by("-created_at")

        serializer = NoteSerializer(notes, many=True)
        return Response(serializer.data)

    if request.method == "POST":
        project_id = request.data.get("project")
        if not project_id:
            return Response({"error": "project is required."}, status=status.HTTP_400_BAD_REQUEST)

        project_obj = get_object_or_404(Project.objects.filter(Q(owner=request.user) | Q(collaborators=request.user)).distinct(), pk=project_id)
        serializer = NoteSerializer(data=request.data)
        if serializer.is_valid():
            note = serializer.save(author=request.user, project=project_obj)
            Activity.objects.create(
                actor=request.user, verb="created a note", message=note.title or "Untitled note",
                related_type="note", related_id=note.id, metadata={"project_id": project_obj.id}
            )
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET", "PATCH", "PUT", "DELETE"])
@permission_classes([IsAuthenticated])
def note_detail_api(request, pk):
    note = get_object_or_404(Note.objects.filter(Q(project__owner=request.user) | Q(project__collaborators=request.user)).distinct(), pk=pk)
    if request.method == "GET":
        return Response(NoteSerializer(note).data)
    if request.method == "DELETE":
        title, project_id = note.title or "Untitled note", note.project_id
        note.delete()
        Activity.objects.create(actor=request.user, verb="deleted a note", message=title, related_type="note", related_id=pk, metadata={"project_id": project_id})
        return Response(status=status.HTTP_204_NO_CONTENT)
    serializer = NoteSerializer(note, data=request.data, partial=request.method == "PATCH")
    if serializer.is_valid():
        updated = serializer.save()
        Activity.objects.create(actor=request.user, verb="updated a note", message=updated.title or "Untitled note", related_type="note", related_id=updated.id, metadata={"project_id": updated.project_id})
        return Response(NoteSerializer(updated).data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# =========================================================
# ACTIVITY
# =========================================================

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def activity_api(request):
    """Return only the authenticated user's activity, never global history."""
    activities = Activity.objects.filter(actor=request.user).order_by("-created_at")[:200]
    return Response(ActivitySerializer(activities, many=True).data)

# =========================================================
# SNIPPETS
# =========================================================

@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def snippets_api(request):

    if request.method == "GET":
        snippets = Snippet.objects.filter(
            author=request.user
        ).order_by("-created_at")

        serializer = SnippetSerializer(
            snippets,
            many=True
        )

        return Response(serializer.data)

    if request.method == "POST":

        project_id = request.data.get("project")

        project_obj = None

        if project_id:
            project_obj = get_object_or_404(
                Project,
                pk=project_id,
                owner=request.user
            )

        serializer = SnippetSerializer(data=request.data)

        if serializer.is_valid():
            serializer.save(
                author=request.user,
                project=project_obj
            )

            return Response(
                serializer.data,
                status=status.HTTP_201_CREATED
            )

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )

@api_view(["GET", "PATCH", "PUT", "DELETE"])
@permission_classes([IsAuthenticated])
def snippet_detail_api(request, pk):
    snippet = get_object_or_404(Snippet, pk=pk, author=request.user)
    if request.method == "GET":
        return Response(SnippetSerializer(snippet).data)
    if request.method == "DELETE":
        snippet.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    serializer = SnippetSerializer(snippet, data=request.data, partial=request.method == "PATCH")
    if serializer.is_valid():
        return Response(SnippetSerializer(serializer.save()).data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# =========================================================
# GITHUB AUTHORIZE
# =========================================================

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def github_authorize(request):

    if not GITHUB_CLIENT_ID:
        return Response(
            {
                "error": "GITHUB_CLIENT_ID is not configured."
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE
        )

    if not GITHUB_CLIENT_SECRET:
        return Response(
            {
                "error": "GITHUB_CLIENT_SECRET is not configured."
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE
        )

    if not settings.GITHUB_TOKEN_ENCRYPTION_KEY:
        return Response(
            {"error": "GitHub token encryption is not configured."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    state = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")

    expires_before = timezone.now() - timedelta(minutes=10)
    GitHubOAuthState.objects.filter(user=request.user, created_at__lt=expires_before).delete()
    GitHubOAuthState.objects.filter(user=request.user, used=False).delete()
    GitHubOAuthState.objects.create(
        user=request.user,
        state=state,
        code_verifier=code_verifier,
    )

    github_url = "https://github.com/login/oauth/authorize?" + urlencode({
        "client_id": GITHUB_CLIENT_ID,
        "redirect_uri": GITHUB_OAUTH_REDIRECT,
        "scope": GITHUB_OAUTH_SCOPE,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "allow_signup": "true",
    })

    # Frontend receives this URL and redirects browser to it.
    return Response({
        "authorization_url": github_url
    })


# =========================================================
# GITHUB CALLBACK
# =========================================================

@api_view(["GET"])
@permission_classes([AllowAny])
def github_callback(request):

    code = request.query_params.get("code")
    state = request.query_params.get("state")
    github_error = request.query_params.get("error")

    if github_error:

        return redirect(f"{FRONTEND_URL}/?github=error")

    if not code or not state:

        return Response(
            {
                "error": "Missing code or state."
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        with transaction.atomic():
            oauth_state = GitHubOAuthState.objects.select_for_update().select_related("user").get(
                state=state,
                used=False,
                created_at__gte=timezone.now() - timedelta(minutes=10),
            )
            # Consume state before the external exchange to prevent replay.
            oauth_state.used = True
            oauth_state.save(update_fields=["used"])
    except GitHubOAuthState.DoesNotExist:
        return Response({"error": "Invalid or expired OAuth state."}, status=status.HTTP_400_BAD_REQUEST)

    # Exchange code for GitHub access token
    try:
        token_response = requests.post(
            "https://github.com/login/oauth/access_token",
            data={
                "client_id": GITHUB_CLIENT_ID,
                "client_secret": GITHUB_CLIENT_SECRET,
                "code": code,
                "redirect_uri": GITHUB_OAUTH_REDIRECT,
                "code_verifier": oauth_state.code_verifier,
            },
            headers={"Accept": "application/json"},
            timeout=GITHUB_TIMEOUT,
        )

    except requests.RequestException:
        return github_service_unavailable()

    if token_response.status_code != 200:

        return Response({"error": "Failed to exchange GitHub code."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        token_data = token_response.json()
    except ValueError:
        return github_service_unavailable()

    access_token = token_data.get(
        "access_token"
    )

    if not access_token:

        return Response({"error": "GitHub did not return an access token."}, status=status.HTTP_400_BAD_REQUEST)

    # -----------------------------------------------------
    # Get GitHub user
    # -----------------------------------------------------

    try:
        user_response = requests.get(
            f"{GITHUB_API_URL}/user",
            headers=github_headers(access_token),
            timeout=GITHUB_TIMEOUT,
        )
    except requests.RequestException:
        return github_service_unavailable()

    if user_response.status_code != 200:

        return Response({"error": "Failed to fetch GitHub user."}, status=status.HTTP_502_BAD_GATEWAY)

    try:
        github_user = user_response.json()
    except ValueError:
        return github_service_unavailable()

    github_id = github_user.get("id")
    github_login = github_user.get("login", "")

    # -----------------------------------------------------
    # Save GitHub account
    # -----------------------------------------------------

    GitHubAccount.objects.update_or_create(
        user=oauth_state.user,
        defaults={
            "github_id": github_id,
            "login": github_login,
            "access_token": access_token,
            "scope": token_data.get("scope", ""),
            "token_type": token_data.get(
                "token_type",
                "bearer"
            ),
        }
    )

    # -----------------------------------------------------
    # Update user profile
    # -----------------------------------------------------

    profile, _ = UserProfile.objects.get_or_create(
        user=oauth_state.user
    )

    github_html_url = github_user.get(
        "html_url",
        ""
    )

    if github_html_url:
        profile.github = github_html_url

    if not profile.avatar_url:
        profile.avatar_url = github_user.get(
            "avatar_url",
            ""
        )

    profile.save()

    # -----------------------------------------------------
    # Create activity
    # -----------------------------------------------------

    Activity.objects.create(
        actor=oauth_state.user,
        verb="connected_github",
        message=f"Connected GitHub account @{github_login}",
        related_type="github_account",
        metadata={
            "github_id": github_id,
            "login": github_login,
        }
    )

    # Redirect back to frontend
    return redirect(f"{FRONTEND_URL}/?github=connected")


# =========================================================
# GITHUB ACCOUNT
# =========================================================

@api_view(["GET", "DELETE"])
@permission_classes([IsAuthenticated])
def github_account_api(request):

    try:

        github_account = GitHubAccount.objects.get(
            user=request.user
        )

    except GitHubAccount.DoesNotExist:

        return Response({
            "connected": False,
            "account": None,
        })

    if request.method == "GET":

        serializer = GitHubAccountSerializer(
            github_account
        )

        data = serializer.data

        # Never expose access token
        data.pop(
            "access_token",
            None
        )

        return Response({
            "connected": True,
            "account": data,
        })

    # -----------------------------------------------------
    # Disconnect GitHub
    # -----------------------------------------------------

    github_account.delete()

    Activity.objects.create(
        actor=request.user,
        verb="disconnected_github",
        message="Disconnected GitHub account",
        related_type="github_account",
    )

    return Response(
        {
            "message": "GitHub account disconnected successfully."
        }
    )


# =========================================================
# GITHUB REPOSITORIES
# =========================================================

@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def github_account_disconnect_api(request):
    deleted, _ = GitHubAccount.objects.filter(user=request.user).delete()
    GitHubOAuthState.objects.filter(user=request.user, used=False).update(used=True)
    return Response(status=status.HTTP_204_NO_CONTENT if deleted else status.HTTP_404_NOT_FOUND)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def github_repos_api(request):


    try:

        github_account = GitHubAccount.objects.get(
            user=request.user
        )

    except GitHubAccount.DoesNotExist:

        return Response(
            {
                "error": "GitHub account is not connected."
            },
            status=status.HTTP_404_NOT_FOUND
        )

    if not github_account.access_token:

        return Response(
            {
                "error": "GitHub access token is missing."
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    page = request.query_params.get(
        "page",
        "1"
    )

    per_page = request.query_params.get(
        "per_page",
        "30"
    )

    try:
        page = max(1, int(page))
        per_page = min(
            100,
            max(1, int(per_page))
        )

    except ValueError:

        page = 1
        per_page = 30

    try:
        response = requests.get(
            f"{GITHUB_API_URL}/user/repos",
            headers=github_headers(github_account.access_token),
            params={
                "sort": "updated",
                "direction": "desc",
                "per_page": per_page,
                "page": page,
            },
            timeout=GITHUB_TIMEOUT,
        )
    except requests.RequestException:
        return github_service_unavailable()

    if response.status_code == 401:

        return Response(
            {
                "error": "GitHub access token is invalid or expired."
            },
            status=status.HTTP_401_UNAUTHORIZED
        )

    if response.status_code != 200:

        return Response({"error": "Failed to fetch GitHub repositories."}, status=status.HTTP_502_BAD_GATEWAY)

    try:
        repositories = response.json()
    except ValueError:
        return github_service_unavailable()

    formatted_repositories = []

    for repo in repositories:

        formatted_repositories.append({
            "id": repo.get("id"),
            "name": repo.get("name"),
            "full_name": repo.get("full_name"),
            "description": repo.get("description"),
            "html_url": repo.get("html_url"),
            "language": repo.get("language"),
            "private": repo.get("private"),
            "fork": repo.get("fork"),
            "default_branch": repo.get(
                "default_branch"
            ),
            "stars": repo.get(
                "stargazers_count",
                0
            ),
            "forks": repo.get(
                "forks_count",
                0
            ),
            "open_issues": repo.get(
                "open_issues_count",
                0
            ),
            "updated_at": repo.get(
                "updated_at"
            ),
            "created_at": repo.get(
                "created_at"
            ),
            "pushed_at": repo.get(
                "pushed_at"
            ),
            "owner": {
                "login": (
                    repo.get("owner") or {}
                ).get("login"),
                "avatar_url": (
                    repo.get("owner") or {}
                ).get("avatar_url"),
            },
        })

    return Response({
        "count": len(formatted_repositories),
        "page": page,
        "per_page": per_page,
        "repositories": formatted_repositories,
    })


# =========================================================
# GITHUB SYNC ACTIVITY
# =========================================================

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def github_sync_activity(request):

    try:

        github_account = GitHubAccount.objects.get(
            user=request.user
        )

    except GitHubAccount.DoesNotExist:

        return Response(
            {
                "error": "GitHub account is not connected."
            },
            status=status.HTTP_404_NOT_FOUND
        )

    if not github_account.access_token:

        return Response(
            {
                "error": "GitHub access token is missing."
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    # -----------------------------------------------------
    # Get authenticated GitHub user
    # -----------------------------------------------------

    try:
        user_response = requests.get(
            f"{GITHUB_API_URL}/user",
            headers=github_headers(github_account.access_token),
            timeout=GITHUB_TIMEOUT,
        )
    except requests.RequestException:
        return github_service_unavailable()

    if user_response.status_code != 200:

        return Response({"error": "Failed to authenticate with GitHub."}, status=status.HTTP_502_BAD_GATEWAY)

    try:
        github_user = user_response.json()
    except ValueError:
        return github_service_unavailable()

    github_login = github_user.get("login")
    requested_repo = str(request.data.get("repo_full_name") or "").strip()

    # -----------------------------------------------------
    # Get GitHub events
    # -----------------------------------------------------

    try:
        events_response = requests.get(
            f"{GITHUB_API_URL}/users/{github_login}/events",
            headers=github_headers(github_account.access_token),
            params={"per_page": 30},
            timeout=GITHUB_TIMEOUT,
        )
    except requests.RequestException:
        return github_service_unavailable()

    if events_response.status_code != 200:

        return Response({"error": "Failed to fetch GitHub activity."}, status=status.HTTP_502_BAD_GATEWAY)

    try:
        events = events_response.json()
    except ValueError:
        return github_service_unavailable()

    synced = 0

    activities = []

    # -----------------------------------------------------
    # Convert GitHub events -> Developer OS Activity
    # -----------------------------------------------------

    for event in events:

        event_id = event.get(
            "id"
        )

        event_type = event.get(
            "type",
            "GitHubActivity"
        )

        repo = event.get(
            "repo"
        ) or {}

        repo_name = repo.get("name", "")
        if requested_repo and repo.get("full_name", repo_name) != requested_repo:
            continue

        message = f"{event_type} in {repo_name}" if repo_name else event_type

        # Avoid duplicate activity using metadata event_id
        already_exists = Activity.objects.filter(
            actor=request.user,
            related_type="github_event",
            metadata__github_event_id=event_id,
        ).exists()

        if already_exists:
            continue

        activity = Activity.objects.create(
            actor=request.user,
            verb=event_type,
            message=message,
            related_type="github_event",
            metadata={
                "github_event_id": event_id,
                "repo": repo_name,
                "event_type": event_type,
                "created_at": event.get(
                    "created_at"
                ),
            }
        )

        activities.append(
            ActivitySerializer(
                activity
            ).data
        )

        synced += 1

    # -----------------------------------------------------
    # Final sync activity
    # -----------------------------------------------------

    Activity.objects.create(
        actor=request.user,
        verb="synced_github_activity",
        message=f"Synced {synced} GitHub activities",
        related_type="github_account",
        metadata={
            "github_login": github_login,
            "synced_count": synced,
        }
    )

    return Response({
        "success": True,
        "github_user": github_login,
        "synced": synced,
        "activities": activities,
    })

# =========================================================
# WORKSPACE INTELLIGENCE + COLLABORATION
# =========================================================

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def workspace_summary_api(request):
    user = request.user
    projects = Project.objects.filter(owner=user).annotate(
        task_count=Count("tasks"),
        completed_task_count=Count("tasks", filter=Q(tasks__status="done")),
    )
    tasks = Task.objects.filter(project__owner=user)
    total = tasks.count()
    done = tasks.filter(status="done").count()
    blocked = tasks.filter(status="blocked").count()
    urgent = tasks.filter(priority="urgent").exclude(status="done").count()
    active = tasks.exclude(status="done").count()
    completion = round(done * 100 / total) if total else 0
    overdue = tasks.filter(due_date__lt=timezone.localdate()).exclude(status="done").count()
    notes = Note.objects.filter(author=user).count()
    snippets = Snippet.objects.filter(author=user).count()
    recent_activity = Activity.objects.filter(actor=user).order_by("-created_at")[:12]
    return Response({
        "projects": projects.count(), "active_tasks": active, "done_tasks": done,
        "blocked_tasks": blocked, "urgent_tasks": urgent, "overdue_tasks": overdue,
        "completion": completion, "notes": notes, "snippets": snippets,
        "project_completion": [
            {"id": p.id, "title": p.title, "progress": round(p.completed_task_count * 100 / p.task_count) if p.task_count else 0,
             "tasks": p.task_count, "status": p.status, "deadline": p.deadline}
            for p in projects.order_by("-created_at")[:10]
        ],
        "recent_activity": ActivitySerializer(recent_activity, many=True).data,
    })


def _project_access(project, user):
    return project.owner_id == user.id or project.collaborators.filter(pk=user.id).exists()


@api_view(["GET", "POST", "DELETE"])
@permission_classes([IsAuthenticated])
def project_collaborators_api(request, pk):
    project = get_object_or_404(Project, pk=pk)
    if not _project_access(project, request.user):
        return Response({"error": "You do not have access to this project."}, status=status.HTTP_403_FORBIDDEN)

    if request.method == "GET":
        members = [project.owner, *project.collaborators.all()]
        seen = set()
        data = []
        for member in members:
            if member.id in seen:
                continue
            seen.add(member.id)
            data.append({
                "id": member.id,
                "username": member.username,
                "email": member.email,
                "full_name": " ".join(filter(None, [member.first_name, member.last_name])).strip() or member.username,
                "role": "owner" if member.id == project.owner_id else "member",
            })
        return Response(data)

    if project.owner_id != request.user.id:
        return Response({"error": "Only the project owner can change collaborators."}, status=status.HTTP_403_FORBIDDEN)

    identifier = str(request.data.get("username") or request.data.get("email") or "").strip()
    if not identifier:
        return Response({"error": "username or email is required."}, status=status.HTTP_400_BAD_REQUEST)
    member = User.objects.filter(Q(username__iexact=identifier) | Q(email__iexact=identifier)).first()
    if not member:
        return Response({"error": "No registered user matches that username or email."}, status=status.HTTP_404_NOT_FOUND)
    if member.id == request.user.id:
        return Response({"error": "The project owner is already a member."}, status=status.HTTP_400_BAD_REQUEST)

    if request.method == "POST":
        project.collaborators.add(member)
        Activity.objects.create(actor=request.user, verb="added a collaborator", message=f"{member.username} → {project.title}", related_type="project", related_id=project.id)
        return Response({"id": member.id, "username": member.username, "email": member.email, "role": "member"}, status=status.HTTP_201_CREATED)

    project.collaborators.remove(member)
    Activity.objects.create(actor=request.user, verb="removed a collaborator", message=f"{member.username} ← {project.title}", related_type="project", related_id=project.id)
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([AssistantRateThrottle])
def assistant_api(request):
    prompt = str(request.data.get("message") or "").strip()
    if not prompt:
        return Response({"error": "message is required."}, status=status.HTTP_400_BAD_REQUEST)
    if len(prompt) > 6000:
        return Response({"error": "message must be 6000 characters or fewer."}, status=status.HTTP_400_BAD_REQUEST)

    tasks = Task.objects.filter(project__owner=request.user)
    projects = Project.objects.filter(owner=request.user)
    total = tasks.count(); done = tasks.filter(status="done").count()
    blocked = tasks.filter(status="blocked").count()
    urgent = tasks.filter(priority="urgent").exclude(status="done").count()
    overdue = tasks.filter(due_date__lt=timezone.localdate()).exclude(status="done").count()
    context = {
        "projects": projects.count(), "tasks": total, "completed": done,
        "completion": round(done * 100 / total) if total else 0,
        "blocked": blocked, "urgent": urgent, "overdue": overdue,
        "recent_projects": list(projects.order_by("-created_at").values_list("title", flat=True)[:6]),
    }

    # Optional OpenAI-compatible provider. The app remains functional without it
    # by using deterministic workspace intelligence rather than fake AI text.
    provider_url = os.environ.get("AI_API_URL", "").rstrip("/")
    provider_key = os.environ.get("AI_API_KEY", "")
    provider_model = os.environ.get("AI_MODEL", "")
    if provider_url and provider_key and provider_model:
        try:
            upstream = requests.post(
                f"{provider_url}/chat/completions",
                headers={"Authorization": f"Bearer {provider_key}", "Content-Type": "application/json"},
                json={"model": provider_model, "temperature": 0.2, "messages": [
                    {"role": "system", "content": "You are DeveloperOS, a concise software project copilot. Use only the supplied workspace context. Give practical next actions and never invent project facts."},
                    {"role": "user", "content": f"Workspace context: {context}\nUser request: {prompt}"},
                ]}, timeout=25,
            )
            upstream.raise_for_status()
            content = upstream.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            if content:
                return Response({"mode": "provider", "answer": content, "context": context})
        except (requests.RequestException, ValueError, IndexError, KeyError):
            pass

    if blocked or overdue:
        issues = []
        if blocked: issues.append(f"{blocked} blocked")
        if overdue: issues.append(f"{overdue} overdue")
        answer = f"Your workspace has {', '.join(issues)} item(s). Clear those first, then move the highest-priority active task forward."
    elif urgent:
        answer = f"You have {urgent} urgent active task(s). Finish or rescope the smallest urgent item first; your current completion is {context['completion']}%."
    elif total:
        answer = f"Your workspace is {context['completion']}% complete across {total} tasks. Keep the active queue small and define the next concrete milestone for {context['recent_projects'][0] if context['recent_projects'] else 'your current project'}."
    else:
        answer = "Your workspace is ready. Create a project and a few concrete tasks so DeveloperOS can generate useful delivery signals."
    return Response({"mode": "local", "answer": answer, "context": context})


# =========================================================
# PLATFORM UPGRADE — SEARCH / COLLAB / IDE / AI / SAAS
# =========================================================

def _visible_projects(user):
    return Project.objects.filter(Q(owner=user) | Q(collaborators=user)).distinct()


def _workspace_context(user, project_id=None):
    projects = _visible_projects(user)
    if project_id:
        projects = projects.filter(pk=project_id)
    project_rows = list(projects.order_by("-updated_at" if hasattr(Project, "updated_at") else "-created_at").values(
        "id", "title", "description", "status", "priority", "category", "deadline", "repository_url", "stack"
    )[:20])
    for p in project_rows:
        if p.get("deadline"):
            p["deadline"] = p["deadline"].isoformat()
    tasks = Task.objects.filter(project_id__in=project_ids).select_related("project", "assignee").order_by("status", "priority", "due_date")[:80]
    notes = Note.objects.filter(project_id__in=project_ids).order_by("-updated_at")[:40]
    snippets = Snippet.objects.filter(Q(author=user) | Q(project_id__in=project_ids)).order_by("-updated_at")[:40]
    return {
        "projects": project_rows,
        "tasks": [
            {"id": t.id, "project": t.project.title if t.project else None, "title": t.title, "status": t.status,
             "priority": t.priority, "due_date": t.due_date.isoformat() if t.due_date else None,
             "assignee": t.assignee.username if t.assignee else None}
            for t in tasks
        ],
        "notes": [{"id": n.id, "project": n.project_id, "title": n.title, "content": n.content[:1500]} for n in notes],
        "snippets": [{"id": s.id, "project": s.project_id, "title": s.title, "language": s.language, "code": s.code[:3000]} for s in snippets],
    }


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def platform_search_api(request):
    q = str(request.query_params.get("q") or "").strip()
    if not q:
        return Response({"query": "", "results": []})
    if len(q) > 160:
        return Response({"error": "Query too long."}, status=400)
    projects = _visible_projects(request.user).filter(
        Q(title__icontains=q) | Q(description__icontains=q) | Q(category__icontains=q)
    )[:15]
    tasks = Task.objects.filter(
        Q(project__in=_visible_projects(request.user)) &
        (Q(title__icontains=q) | Q(description__icontains=q) | Q(tags__icontains=q))
    ).select_related("project")[:20]
    notes = Note.objects.filter(
        Q(project__in=_visible_projects(request.user)) &
        (Q(title__icontains=q) | Q(content__icontains=q))
    ).select_related("project")[:15]
    snippets = Snippet.objects.filter(
        Q(author=request.user) | Q(project__in=_visible_projects(request.user))
    ).filter(Q(title__icontains=q) | Q(code__icontains=q) | Q(description__icontains=q))[:15]
    tools = Tool.objects.filter(Q(name__icontains=q) | Q(description__icontains=q) | Q(tag__icontains=q))[:10]
    resources = Resource.objects.filter(Q(title__icontains=q) | Q(description__icontains=q) | Q(category__icontains=q))[:10]
    results = (
        [{"type":"project","id":p.id,"title":p.title,"subtitle":p.description[:120],"route":f"/projects/{p.id}"} for p in projects] +
        [{"type":"task","id":t.id,"title":t.title,"subtitle":f"{t.project.title} · {t.status}","route":f"/projects/{t.project_id}?tab=tasks"} for t in tasks] +
        [{"type":"note","id":n.id,"title":n.title or "Untitled note","subtitle":(n.content or "")[:120],"route":f"/projects/{n.project_id}?tab=notes"} for n in notes] +
        [{"type":"snippet","id":s.id,"title":s.title,"subtitle":s.language,"route":"/ide"} for s in snippets] +
        [{"type":"tool","id":t.id,"title":t.name,"subtitle":t.category,"route":"/explore"} for t in tools] +
        [{"type":"resource","id":r.id,"title":r.title,"subtitle":r.category,"route":"/resources"} for r in resources]
    )
    return Response({"query": q, "results": results[:80]})


@api_view(["GET", "POST", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def notifications_api(request):
    if request.method == "GET":
        qs = Notification.objects.filter(user=request.user).order_by("-created_at")[:100]
        unread = Notification.objects.filter(user=request.user, read=False).count()
        return Response({"unread": unread, "items": NotificationSerializer(qs, many=True).data})
    if request.method == "POST":
        # Internal-safe endpoint for creating user notifications; clients can only target themselves.
        payload = {"kind": request.data.get("kind","system"), "title": request.data.get("title","Notification"),
                   "body": request.data.get("body",""), "link": request.data.get("link","")}
        n = Notification.objects.create(user=request.user, **payload)
        return Response(NotificationSerializer(n).data, status=201)
    if request.method == "PATCH":
        ids = request.data.get("ids")
        qs = Notification.objects.filter(user=request.user)
        if ids:
            qs = qs.filter(id__in=ids)
        qs.update(read=True)
        return Response({"ok": True})
    Notification.objects.filter(user=request.user, id=request.data.get("id")).delete()
    return Response(status=204)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def comments_api(request):
    if request.method == "GET":
        qs = Comment.objects.filter(Q(project__in=_visible_projects(request.user)) | Q(task__project__in=_visible_projects(request.user))).select_related("author").order_by("-created_at")
        if request.query_params.get("project"): qs = qs.filter(project_id=request.query_params["project"])
        if request.query_params.get("task"): qs = qs.filter(task_id=request.query_params["task"])
        return Response(CommentSerializer(qs[:100], many=True).data)
    project_id = request.data.get("project")
    task_id = request.data.get("task")
    if not project_id and not task_id:
        return Response({"error":"project or task is required"}, status=400)
    if task_id:
        task = get_object_or_404(Task.objects.select_related("project"), pk=task_id)
        if not _project_access(task.project, request.user): return Response({"error":"Forbidden"}, status=403)
    if project_id:
        project = get_object_or_404(Project, pk=project_id)
        if not _project_access(project, request.user): return Response({"error":"Forbidden"}, status=403)
    serializer = CommentSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    c = serializer.save(author=request.user)
    Activity.objects.create(actor=request.user, verb="commented", message=c.body[:200], related_type="comment", related_id=c.id)
    return Response(CommentSerializer(c).data, status=201)


@api_view(["GET", "POST", "DELETE"])
@permission_classes([IsAuthenticated])
def task_dependencies_api(request, pk):
    task = get_object_or_404(Task, pk=pk)
    if not task.project or not _project_access(task.project, request.user): return Response({"error":"Forbidden"}, status=403)
    if request.method == "GET":
        deps = TaskDependency.objects.filter(task=task)
        return Response(TaskDependencySerializer(deps, many=True).data)
    if request.method == "DELETE":
        dep = get_object_or_404(TaskDependency, pk=request.data.get("dependency_id"), task=task)
        dep.delete(); return Response(status=204)
    dep_task = get_object_or_404(Task, pk=request.data.get("depends_on"))
    if dep_task == task: return Response({"error":"A task cannot depend on itself."}, status=400)
    if dep_task.project_id != task.project_id: return Response({"error":"Dependencies must stay inside the project."}, status=400)
    dep, _ = TaskDependency.objects.get_or_create(task=task, depends_on=dep_task)
    return Response(TaskDependencySerializer(dep).data, status=201)


@api_view(["GET", "POST", "PATCH"])
@permission_classes([IsAuthenticated])
def ide_workspaces_api(request):
    if request.method == "GET":
        qs = CodeWorkspace.objects.filter(owner=request.user).order_by("-updated_at")
        return Response(CodeWorkspaceSerializer(qs[:30], many=True).data)
    if request.method == "POST":
        payload = request.data.copy()
        payload.setdefault("files", {
            "main.py": "# Developer OS Web IDE\nprint('Hello, Developer OS')\n",
            "README.md": "# Workspace\n\nBuild, test and ship from the Developer OS command center.\n"
        })
        serializer = CodeWorkspaceSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        ws = serializer.save(owner=request.user)
        return Response(CodeWorkspaceSerializer(ws).data, status=201)
    ws = get_object_or_404(CodeWorkspace, pk=request.data.get("id"), owner=request.user)
    serializer = CodeWorkspaceSerializer(ws, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    return Response(CodeWorkspaceSerializer(serializer.save()).data)


# =========================================================
# WEB IDE — file system, framework provisioning and sandboxed execution
# =========================================================

FRAMEWORK_CATALOG = {
    "react-vite": {"label": "React + Vite", "runtime": "node", "package_manager": "npm", "install": "npm install react react-dom && npm install -D vite @vitejs/plugin-react", "start": "npm run dev -- --host 0.0.0.0"},
    "vue-vite": {"label": "Vue + Vite", "runtime": "node", "package_manager": "npm", "install": "npm install vue && npm install -D vite @vitejs/plugin-vue", "start": "npm run dev -- --host 0.0.0.0"},
    "svelte-vite": {"label": "Svelte + Vite", "runtime": "node", "package_manager": "npm", "install": "npm install svelte && npm install -D vite @sveltejs/vite-plugin-svelte", "start": "npm run dev -- --host 0.0.0.0"},
    "nextjs": {"label": "Next.js", "runtime": "node", "package_manager": "npm", "install": "npm install next react react-dom", "start": "npm run dev -- --hostname 0.0.0.0"},
    "express": {"label": "Express", "runtime": "node", "package_manager": "npm", "install": "npm install express", "start": "node server.js"},
    "nestjs": {"label": "NestJS", "runtime": "node", "package_manager": "npm", "install": "npm install @nestjs/core @nestjs/common reflect-metadata rxjs", "start": "npm run start:dev"},
    "django": {"label": "Django + DRF", "runtime": "python", "package_manager": "pip", "install": "python -m pip install django djangorestframework django-cors-headers", "start": "python manage.py runserver 0.0.0.0:8000"},
    "fastapi": {"label": "FastAPI", "runtime": "python", "package_manager": "pip", "install": "python -m pip install fastapi uvicorn[standard] pydantic", "start": "python -m uvicorn main:app --host 0.0.0.0 --port 8000"},
    "flask": {"label": "Flask", "runtime": "python", "package_manager": "pip", "install": "python -m pip install flask", "start": "flask --app app run --host 0.0.0.0 --port 8000"},
    "litestar": {"label": "Litestar", "runtime": "python", "package_manager": "pip", "install": "python -m pip install litestar uvicorn", "start": "uvicorn app:app --host 0.0.0.0 --port 8000"},
    "streamlit": {"label": "Streamlit", "runtime": "python", "package_manager": "pip", "install": "python -m pip install streamlit", "start": "streamlit run app.py --server.address 0.0.0.0"},
    "httpx": {"label": "Python HTTP stack", "runtime": "python", "package_manager": "pip", "install": "python -m pip install httpx", "start": "python main.py"},
    "django-ninja": {"label": "Django Ninja", "runtime": "python", "package_manager": "pip", "install": "python -m pip install django django-ninja", "start": "python manage.py runserver 0.0.0.0:8000"},
}

RUNNER_URL = os.environ.get("IDE_RUNNER_URL", "http://runner:8080").rstrip("/")
RUNNER_TOKEN = os.environ.get("IDE_RUNNER_TOKEN", "")

def _runner_request(method, path, payload, timeout=30):
    if not RUNNER_TOKEN:
        return None, {"error": "IDE runner is not configured. Set IDE_RUNNER_TOKEN and start the runner service."}
    try:
        response = requests.request(
            method, f"{RUNNER_URL}{path}", json=payload,
            headers={"Authorization": f"Bearer {RUNNER_TOKEN}"},
            timeout=timeout,
        )
        data = response.json() if response.content else {}
        if response.status_code >= 400:
            return None, data
        return data, None
    except requests.RequestException as exc:
        return None, {"error": f"IDE runner unavailable: {exc.__class__.__name__}"}

def _workspace_payload(ws):
    return {"workspace_id": str(ws.id), "files": ws.files, "active_file": ws.active_file}

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def ide_frameworks_api(request):
    return Response([
        {"id": key, **value}
        for key, value in FRAMEWORK_CATALOG.items()
    ])

@api_view(["GET", "POST", "DELETE"])
@permission_classes([IsAuthenticated])
def ide_workspace_files_api(request, pk):
    ws = get_object_or_404(CodeWorkspace, pk=pk, owner=request.user)
    files = dict(ws.files or {})
    if request.method == "GET":
        return Response({"files": files, "active_file": ws.active_file})
    if request.method == "DELETE":
        path = str(request.data.get("path") or "").replace("\\", "/").lstrip("/")
        if not path or ".." in path.split("/"):
            return Response({"error": "Invalid path."}, status=400)
        # Directories are virtual (files are stored by path), so deleting a
        # directory removes every descendant. This makes the IDE behave like
        # a real project filesystem without storing unsafe filesystem paths.
        if path in files:
            del files[path]
        else:
            prefix = path.rstrip("/") + "/"
            removed = [key for key in files if key.startswith(prefix)]
            if not removed:
                return Response({"error": "File or directory not found."}, status=404)
            for key in removed:
                del files[key]
        if ws.active_file not in files:
            ws.active_file = next(iter(files), "")
        ws.files = files
        ws.save(update_fields=["files", "active_file", "updated_at"])
        _runner_request("POST", "/sync", _workspace_payload(ws), timeout=30)
        return Response({"files": files, "active_file": ws.active_file})
    action = str(request.data.get("action") or "write")
    path = str(request.data.get("path") or "").replace("\\", "/").lstrip("/")
    if action == "rename":
        target = str(request.data.get("to") or "").replace("\\", "/").lstrip("/")
        if not path or not target or ".." in path.split("/") or ".." in target.split("/") or path not in files:
            return Response({"error": "Valid source and target paths are required."}, status=400)
        if target in files:
            return Response({"error": "Target already exists."}, status=409)
        if path in files:
            files[target] = files.pop(path)
        else:
            prefix = path.rstrip("/") + "/"
            matches = [key for key in files if key.startswith(prefix)]
            if not matches:
                return Response({"error": "Source file or directory not found."}, status=404)
            target_prefix = target.rstrip("/") + "/"
            if any(key == target or key.startswith(target_prefix) for key in files):
                return Response({"error": "Target already exists."}, status=409)
            moved = {}
            for key in matches:
                moved[target_prefix + key[len(prefix):]] = files.pop(key)
            files.update(moved)
        if ws.active_file == path:
            ws.active_file = target
        elif ws.active_file.startswith(path.rstrip("/") + "/"):
            ws.active_file = target.rstrip("/") + ws.active_file[len(path.rstrip("/")): ]
        ws.files = files
        ws.save(update_fields=["files", "active_file", "updated_at"])
        _runner_request("POST", "/sync", _workspace_payload(ws), timeout=30)
        return Response({"files": files, "active_file": ws.active_file})
    content = request.data.get("content", "")
    if not path or ".." in path.split("/") or not isinstance(content, str):
        return Response({"error": "Valid path and text content are required."}, status=400)
    files[path] = content
    serializer = CodeWorkspaceSerializer(ws, data={"files": files, "active_file": path}, partial=True)
    serializer.is_valid(raise_exception=True)
    ws = serializer.save()
    _runner_request("POST", "/sync", _workspace_payload(ws), timeout=30)
    return Response({"files": ws.files, "active_file": ws.active_file})

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def ide_workspace_sync_api(request, pk):
    ws = get_object_or_404(CodeWorkspace, pk=pk, owner=request.user)
    data, error = _runner_request("POST", "/sync", _workspace_payload(ws), timeout=30)
    if error:
        return Response(error, status=503)
    return Response(data)

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def ide_install_framework_api(request, pk):
    ws = get_object_or_404(CodeWorkspace, pk=pk, owner=request.user)
    framework = str(request.data.get("framework") or "").lower()
    spec = FRAMEWORK_CATALOG.get(framework)
    if not spec:
        return Response({"error": "Unsupported framework preset."}, status=400)
    installation = FrameworkInstallation.objects.create(
        workspace=ws, framework=framework, package_manager=spec["package_manager"], status="running"
    )
    data, error = _runner_request("POST", "/install", {
        **_workspace_payload(ws), "command": spec["install"], "framework": framework,
        "package_manager": spec["package_manager"],
    }, timeout=240)
    if error:
        installation.status = "failed"; installation.output = json.dumps(error); installation.finished_at = timezone.now(); installation.save()
        return Response(error, status=503)
    runner_files = data.get("files")
    if isinstance(runner_files, dict):
        serializer = CodeWorkspaceSerializer(ws, data={"files": runner_files}, partial=True)
        serializer.is_valid(raise_exception=True)
        ws = serializer.save()
    installation.status = "success" if data.get("exit_code", 1) == 0 else "failed"
    installation.output = (data.get("stdout", "") + "\n" + data.get("stderr", ""))[-30000:]
    installation.finished_at = timezone.now(); installation.save()
    ws.framework = framework
    ws.runtime = spec["runtime"]
    ws.package_manager = spec["package_manager"]
    ws.save(update_fields=["framework", "runtime", "package_manager", "updated_at"])
    return Response({"installation": {"id": installation.id, "status": installation.status, "output": installation.output}, "workspace": CodeWorkspaceSerializer(ws).data})

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def ide_install_packages_api(request, pk):
    ws = get_object_or_404(CodeWorkspace, pk=pk, owner=request.user)
    manager = str(request.data.get("package_manager") or ws.package_manager or "npm").lower()
    packages = request.data.get("packages") or []
    if isinstance(packages, str):
        packages = [x.strip() for x in packages.split(",") if x.strip()]
    if manager not in {"npm", "pip"} or not isinstance(packages, list) or not packages or len(packages) > 50:
        return Response({"error": "Use npm or pip and provide 1–50 packages."}, status=400)
    safe = re.compile(r"^[A-Za-z0-9_.@/\-<>=!~\[\],]+$")
    if any(not isinstance(pkg, str) or len(pkg) > 160 or not safe.fullmatch(pkg) for pkg in packages):
        return Response({"error": "One or more package names are invalid."}, status=400)
    command = ("npm install " + " ".join(packages)) if manager == "npm" else ("python -m pip install " + " ".join(packages))
    data, error = _runner_request("POST", "/exec", {**_workspace_payload(ws), "command": command}, timeout=240)
    if error:
        return Response(error, status=503)
    if isinstance(data.get("files"), dict):
        serializer = CodeWorkspaceSerializer(ws, data={"files": data["files"], "package_manager": manager}, partial=True)
        serializer.is_valid(raise_exception=True)
        ws = serializer.save()
    return Response({
        "status": "success" if data.get("exit_code") == 0 else "failed",
        "command": command,
        "exit_code": data.get("exit_code"),
        "stdout": data.get("stdout", ""),
        "stderr": data.get("stderr", ""),
        "workspace": CodeWorkspaceSerializer(ws).data,
    })

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def ide_execute_api(request, pk):
    ws = get_object_or_404(CodeWorkspace, pk=pk, owner=request.user)
    command = str(request.data.get("command") or "").strip()
    if not command or len(command) > 2000:
        return Response({"error": "A command up to 2,000 characters is required."}, status=400)
    execution = IDEExecution.objects.create(workspace=ws, command=command, status="running")
    started = timezone.now()
    data, error = _runner_request("POST", "/exec", {**_workspace_payload(ws), "command": command}, timeout=125)
    duration = int((timezone.now() - started).total_seconds() * 1000)
    if error:
        execution.status = "failed"; execution.stderr = json.dumps(error); execution.duration_ms = duration; execution.finished_at = timezone.now(); execution.save()
        return Response(error, status=503)
    runner_files = data.get("files")
    if isinstance(runner_files, dict):
        serializer = CodeWorkspaceSerializer(ws, data={"files": runner_files}, partial=True)
        serializer.is_valid(raise_exception=True)
        ws = serializer.save()
    execution.exit_code = data.get("exit_code")
    execution.stdout = str(data.get("stdout") or "")[-50000:]
    execution.stderr = str(data.get("stderr") or "")[-50000:]
    execution.duration_ms = duration
    execution.status = "success" if execution.exit_code == 0 else "failed"
    execution.finished_at = timezone.now()
    execution.save()
    return Response({"id": execution.id, "status": execution.status, "exit_code": execution.exit_code, "stdout": execution.stdout, "stderr": execution.stderr, "duration_ms": duration})


@api_view(["GET", "POST", "DELETE"])
@permission_classes([IsAuthenticated])
def api_keys_api(request):
    if request.method == "GET":
        return Response(APIKeySerializer(APIKey.objects.filter(user=request.user).order_by("-created_at"), many=True).data)
    if request.method == "DELETE":
        key = get_object_or_404(APIKey, pk=request.data.get("id"), user=request.user)
        key.revoked_at = timezone.now(); key.save(update_fields=["revoked_at"]); return Response(status=204)
    name = str(request.data.get("name") or "Developer OS CLI").strip()[:100]
    sub, _ = Subscription.objects.get_or_create(user=request.user)
    limit = {"free": 2, "pro": 10, "team": 50, "enterprise": 200}.get(sub.plan, 2)
    active_keys = APIKey.objects.filter(user=request.user, revoked_at__isnull=True).count()
    if active_keys >= limit:
        return Response({"error": f"Your {sub.plan} plan allows {limit} active API key(s)."}, status=403)
    raw = "dos_live_" + secrets.token_urlsafe(32)
    key = APIKey.objects.create(user=request.user, name=name, prefix=raw[:14], key_hash=hashlib.sha256(raw.encode()).hexdigest())
    return Response({"key": raw, "record": APIKeySerializer(key).data}, status=201)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def subscription_api(request):
    sub, _ = Subscription.objects.get_or_create(user=request.user)
    if request.method == "GET":
        return Response(SubscriptionSerializer(sub).data)
    plan = str(request.data.get("plan") or "free").lower()
    if plan not in dict(Subscription.PLAN_CHOICES):
        return Response({"error":"Unsupported plan"}, status=400)
    # The state is persisted immediately. A payment provider can be attached through
    # the provider IDs without changing the application entitlement model.
    sub.plan = plan
    sub.status = "active"
    sub.save(update_fields=["plan","status","updated_at"])
    return Response(SubscriptionSerializer(sub).data)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def organizations_api(request):
    if request.method == "GET":
        orgs = Organization.objects.filter(Q(owner=request.user) | Q(memberships__user=request.user)).distinct()
        return Response(OrganizationSerializer(orgs, many=True).data)
    name = str(request.data.get("name") or "").strip()
    if not name: return Response({"error":"name is required"}, status=400)
    slug = slugify(name)[:160]
    base = slug
    n = 2
    while Organization.objects.filter(slug=slug).exists():
        slug = f"{base}-{n}"; n += 1
    org = Organization.objects.create(owner=request.user, name=name, slug=slug, plan="free")
    OrganizationMembership.objects.create(organization=org, user=request.user, role="owner")
    return Response(OrganizationSerializer(org).data, status=201)


@api_view(["GET", "POST", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
def organization_members_api(request, pk):
    org = get_object_or_404(Organization, pk=pk)
    if not (org.owner_id == request.user.id or org.memberships.filter(user=request.user, role__in=["owner","admin"]).exists()):
        return Response({"error":"Forbidden"}, status=403)
    if request.method == "GET":
        return Response(OrganizationMembershipSerializer(org.memberships.select_related("user"), many=True).data)
    if request.method == "DELETE":
        m = get_object_or_404(OrganizationMembership, pk=request.data.get("id"), organization=org)
        if m.user_id == org.owner_id: return Response({"error":"Owner cannot be removed."}, status=400)
        m.delete(); return Response(status=204)
    identifier = str(request.data.get("username") or request.data.get("email") or "").strip()
    user = get_object_or_404(User, Q(username__iexact=identifier) | Q(email__iexact=identifier))
    role = str(request.data.get("role") or "developer")
    if role not in {"admin","developer","viewer"}: return Response({"error":"Invalid role"}, status=400)
    m, created = OrganizationMembership.objects.update_or_create(organization=org, user=user, defaults={"role":role})
    return Response(OrganizationMembershipSerializer(m).data, status=201 if created else 200)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def ai_conversations_api(request):
    if request.method == "GET":
        qs = AIConversation.objects.filter(owner=request.user).order_by("-updated_at")[:50]
        return Response(AIConversationSerializer(qs, many=True).data)
    project_id = request.data.get("project")
    if project_id:
        project = get_object_or_404(Project, pk=project_id)
        if not _project_access(project, request.user):
            return Response({"error":"Forbidden"}, status=403)
    c = AIConversation.objects.create(owner=request.user, project_id=project_id, title=str(request.data.get("title") or "New conversation")[:200])
    return Response(AIConversationSerializer(c).data, status=201)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def ai_conversation_messages_api(request, pk):
    c = get_object_or_404(AIConversation, pk=pk, owner=request.user)
    return Response(AIMessageSerializer(c.messages.all(), many=True).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([AssistantRateThrottle])
def ai_chat_api(request):
    message = str(request.data.get("message") or "").strip()
    if not message: return Response({"error":"message is required"}, status=400)
    if len(message) > 12000: return Response({"error":"message too long"}, status=400)
    conversation = None
    if request.data.get("conversation"):
        conversation = get_object_or_404(AIConversation, pk=request.data["conversation"], owner=request.user)
    else:
        project_id = request.data.get("project")
        if project_id:
            project = get_object_or_404(Project, pk=project_id)
            if not _project_access(project, request.user):
                return Response({"error":"Forbidden"}, status=403)
        conversation = AIConversation.objects.create(owner=request.user, project_id=project_id, title=message[:60])
    context = _workspace_context(request.user, conversation.project_id)
    user_msg = AIMessage.objects.create(conversation=conversation, role="user", content=message, context=context)
    provider_url = os.environ.get("AI_API_URL", "").rstrip("/")
    provider_key = os.environ.get("AI_API_KEY", "")
    provider_model = os.environ.get("AI_MODEL", "")
    system = ("You are Developer OS Intelligence. You are a software engineering copilot. "
              "Use only the supplied workspace context for project facts. Be explicit about uncertainty. "
              "Return practical, technically precise steps. You may review architecture, tasks, notes and snippets.")
    answer = ""
    if provider_url and provider_key and provider_model:
        try:
            messages = [{"role":"system","content":system},
                        {"role":"user","content":json.dumps({"workspace":context,"request":message}, default=str)}]
            upstream = requests.post(f"{provider_url}/chat/completions", headers={"Authorization":f"Bearer {provider_key}","Content-Type":"application/json"},
                                     json={"model":provider_model,"temperature":0.15,"messages":messages}, timeout=35)
            upstream.raise_for_status()
            answer = upstream.json().get("choices",[{}])[0].get("message",{}).get("content","").strip()
        except (requests.RequestException, ValueError, IndexError, KeyError):
            answer = ""
    if not answer:
        tasks = context["tasks"]
        blocked = [t for t in tasks if t["status"]=="blocked"]
        urgent = [t for t in tasks if t["priority"]=="urgent" and t["status"]!="done"]
        answer = (
            f"I indexed {len(context['projects'])} project(s), {len(tasks)} task(s), "
            f"{len(context['notes'])} note(s), and {len(context['snippets'])} snippet(s). "
            f"There are {len(blocked)} blocked and {len(urgent)} urgent active tasks. "
            "Connect an OpenAI-compatible provider for generative reasoning; the local engine will keep returning deterministic workspace signals."
        )
    assistant_msg = AIMessage.objects.create(conversation=conversation, role="assistant", content=answer, context=context)
    return Response({"conversation": AIConversationSerializer(conversation).data, "message": AIMessageSerializer(assistant_msg).data, "context": context})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def billing_webhook_api(request):
    # Provider-agnostic webhook envelope. Production providers should verify their
    # signature before calling this endpoint or the deployment should put a signed gateway in front.
    event = request.data if isinstance(request.data, dict) else {}
    return Response({"received": True, "event_type": event.get("type", "unknown")})
