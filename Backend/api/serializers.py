from io import BytesIO
import warnings

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from rest_framework import serializers
from urllib.parse import urlparse

from PIL import Image, ImageOps, UnidentifiedImageError

from .models import Favorite, Resource, Tool, UserProfile, Workflow, Project
from .models import Tag, Task, Note, Activity
from .models import Snippet, ProjectInvite
from .models import GitHubAccount, Organization, OrganizationMembership, Notification, Comment, TaskDependency, CodeWorkspace, AIConversation, AIMessage, Subscription, APIKey


def validate_http_url(value):
    if not value:
        return value
    if urlparse(value).scheme not in {"http", "https"}:
        raise serializers.ValidationError("Only http and https URLs are allowed.")
    return value


class ProjectSerializer(serializers.ModelSerializer):
    task_count = serializers.IntegerField(read_only=True)
    completed_task_count = serializers.IntegerField(read_only=True)
    progress = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = [
            'id', 'title', 'description', 'category', 'tags', 'link',
            'status', 'priority', 'start_date', 'deadline', 'repository_url', 'stack',
            'created_at', 'uploaded_at', 'task_count',
            'completed_task_count', 'progress',
        ]
        read_only_fields = ['id', 'created_at', 'uploaded_at', 'task_count', 'completed_task_count', 'progress']

    def get_progress(self, obj):
        total = getattr(obj, 'task_count', None)
        completed = getattr(obj, 'completed_task_count', None)
        if total is None:
            total = obj.tasks.count()
        if completed is None:
            completed = obj.tasks.filter(status='done').count()
        return round((completed / total) * 100) if total else 0

    def validate_tags(self, value):
        if not isinstance(value, list) or len(value) > 20:
            raise serializers.ValidationError('Tags must be a list of at most 20 items.')
        if any(not isinstance(tag, str) or len(tag.strip()) > 50 for tag in value):
            raise serializers.ValidationError('Each tag must be a string of at most 50 characters.')
        return [tag.strip() for tag in value if tag.strip()]

    def validate_link(self, value):
        return validate_http_url(value)

    def validate_repository_url(self, value):
        return validate_http_url(value)

    def validate_stack(self, value):
        if not isinstance(value, list) or len(value) > 30:
            raise serializers.ValidationError('Stack must be a list of at most 30 items.')
        if any(not isinstance(item, str) or len(item.strip()) > 50 for item in value):
            raise serializers.ValidationError('Each stack item must be a string of at most 50 characters.')
        return [item.strip() for item in value if item.strip()]


class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = [
            'full_name',
            'avatar_url',
            'bio',
            'github',
            'linkedin',
            'x',
            'website',
        ]


class ProfileUpdateSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    email = serializers.EmailField(max_length=254, required=False, allow_blank=True)
    full_name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    avatar = serializers.ImageField(required=False, write_only=True)
    remove_avatar = serializers.BooleanField(required=False, write_only=True, default=False)
    avatar_url = serializers.URLField(required=False, allow_blank=True, validators=[validate_http_url])
    bio = serializers.CharField(max_length=5_000, required=False, allow_blank=True)
    github = serializers.URLField(required=False, allow_blank=True, validators=[validate_http_url])
    linkedin = serializers.URLField(required=False, allow_blank=True, validators=[validate_http_url])
    x = serializers.URLField(required=False, allow_blank=True, validators=[validate_http_url])
    website = serializers.URLField(required=False, allow_blank=True, validators=[validate_http_url])

    def validate_avatar(self, uploaded_file):
        """Verify, strip metadata from, and re-encode an uploaded avatar.

        Re-encoding is intentional: it removes EXIF metadata and ensures the
        stored bytes are a browser-safe image format rather than merely trusting
        a filename or MIME type supplied by the client.
        """
        max_bytes = 5 * 1024 * 1024
        max_pixels = 12_000_000
        max_side = 4_096

        if uploaded_file.size > max_bytes:
            raise serializers.ValidationError("Profile images must be 5 MB or smaller.")

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                uploaded_file.seek(0)
                with Image.open(uploaded_file) as verified_image:
                    verified_image.verify()

                uploaded_file.seek(0)
                with Image.open(uploaded_file) as image:
                    image_format = image.format
                    width, height = image.size
                    if image_format not in {"JPEG", "PNG", "WEBP"}:
                        raise serializers.ValidationError(
                            "Only JPEG, PNG, and WebP profile images are allowed."
                        )
                    if not width or not height or width > max_side or height > max_side or width * height > max_pixels:
                        raise serializers.ValidationError(
                            "Profile image dimensions are too large."
                        )

                    image.load()
                    normalized = ImageOps.exif_transpose(image)
                    if normalized.mode in {"RGBA", "LA"} or "transparency" in normalized.info:
                        normalized = normalized.convert("RGBA")
                    else:
                        normalized = normalized.convert("RGB")
                    normalized.thumbnail((2048, 2048), Image.Resampling.LANCZOS)

                    output = BytesIO()
                    normalized.save(output, format="WEBP", quality=85, method=6)
        except serializers.ValidationError:
            raise
        except (OSError, UnidentifiedImageError, Image.DecompressionBombError, ValueError):
            raise serializers.ValidationError("Upload a valid, non-corrupted image file.")
        finally:
            uploaded_file.seek(0)

        return ContentFile(output.getvalue(), name="avatar.webp")

    def validate(self, attrs):
        if attrs.get("avatar") and attrs.get("remove_avatar"):
            raise serializers.ValidationError("Upload a new image or remove the current one, not both.")
        return attrs


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            'id',
            'username',
            'first_name',
            'last_name',
            'email',
        ]


class ResourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Resource
        fields = ['id', 'title', 'description', 'resource_type', 'category', 'link', 'created_at']
        read_only_fields = ['id', 'created_at']

    def validate_link(self, value):
        return validate_http_url(value)


class WorkflowSerializer(serializers.ModelSerializer):
    class Meta:
        model = Workflow
        fields = ['id', 'title', 'level', 'duration', 'summary', 'steps', 'created_at']
        read_only_fields = ['id', 'created_at']

    def validate_steps(self, value):
        if not isinstance(value, list) or len(value) > 50:
            raise serializers.ValidationError('Steps must be a list of at most 50 items.')
        if any(not isinstance(step, str) or len(step) > 500 for step in value):
            raise serializers.ValidationError('Each step must be a string of at most 500 characters.')
        return value


class FavoriteSerializer(serializers.ModelSerializer):
    tool_name = serializers.CharField(source='tool.name', read_only=True)
    tag = serializers.CharField(source='tool.tag', read_only=True)
    description = serializers.CharField(source='tool.description', read_only=True)

    class Meta:
        model = Favorite
        fields = ['id', 'tool', 'tool_name', 'tag', 'description', 'created_at']
        read_only_fields = fields


class ToolSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tool
        fields = ['id', 'name', 'tag', 'category', 'description', 'accent', 'rating', 'features', 'created_at']
        read_only_fields = ['id', 'created_at']


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ['id', 'name', 'slug']
        read_only_fields = ['id']


class TaskSerializer(serializers.ModelSerializer):
    assignee = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=False, allow_null=True)

    class Meta:
        model = Task
        fields = ['id', 'project', 'assignee', 'status', 'priority', 'title', 'description', 'due_date', 'tags', 'created_at', 'updated_at']
        read_only_fields = ['id', 'project', 'created_at', 'updated_at']

    def validate_assignee(self, value):
        request = self.context.get("request")
        project = self.instance.project if self.instance else None
        if request and project and value:
            if value.id != project.owner_id and not project.collaborators.filter(pk=value.id).exists():
                raise serializers.ValidationError("Assignee must be a project member.")
        return value


class NoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Note
        fields = ['id', 'project', 'title', 'content', 'author', 'created_at', 'updated_at']
        read_only_fields = ['id', 'project', 'author', 'created_at', 'updated_at']


class ActivitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Activity
        fields = ['id', 'actor', 'verb', 'message', 'related_type', 'related_id', 'metadata', 'created_at']
        read_only_fields = fields


class SnippetSerializer(serializers.ModelSerializer):
    class Meta:
        model = Snippet
        fields = ['id', 'author', 'project', 'title', 'code', 'language', 'description', 'tags', 'created_at', 'updated_at']
        read_only_fields = ['id', 'author', 'project', 'created_at', 'updated_at']


class GitHubAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = GitHubAccount
        fields = ['github_id', 'login', 'scope', 'token_type', 'created_at', 'updated_at']


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ["id", "name", "slug", "plan", "owner", "created_at", "updated_at"]
        read_only_fields = ["id", "owner", "created_at", "updated_at"]


class OrganizationMembershipSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    class Meta:
        model = OrganizationMembership
        fields = ["id", "organization", "user", "username", "email", "role", "created_at"]
        read_only_fields = ["id", "created_at"]


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "kind", "title", "body", "link", "read", "created_at"]
        read_only_fields = ["id", "created_at"]


class CommentSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source="author.username", read_only=True)
    class Meta:
        model = Comment
        fields = ["id", "author", "author_name", "project", "task", "body", "created_at", "updated_at"]
        read_only_fields = ["id", "author", "author_name", "created_at", "updated_at"]


class TaskDependencySerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskDependency
        fields = ["id", "task", "depends_on", "created_at"]
        read_only_fields = ["id", "created_at"]


class ProjectInviteSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectInvite
        fields = ["id", "project", "email", "role", "token", "expires_at", "accepted_at", "created_at"]
        read_only_fields = ["id", "token", "accepted_at", "created_at"]


class CodeWorkspaceSerializer(serializers.ModelSerializer):
    class Meta:
        model = CodeWorkspace
        fields = ["id", "project", "name", "files", "active_file", "language", "framework", "runtime", "package_manager", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_files(self, value):
        if not isinstance(value, dict) or len(value) > 2000:
            raise serializers.ValidationError("A workspace can contain at most 2,000 source files.")
        total = 0
        for filename, content in value.items():
            if not isinstance(filename, str) or len(filename) > 500:
                raise serializers.ValidationError("Invalid file path.")
            # Prevent path traversal before anything reaches the runner.
            normalized = filename.replace("\\", "/").lstrip("/")
            if ".." in normalized.split("/") or normalized in {"", "."}:
                raise serializers.ValidationError("Invalid workspace path.")
            if not isinstance(content, str) or len(content) > 1_000_000:
                raise serializers.ValidationError("Each text file must be 1 MB or smaller.")
            total += len(content.encode("utf-8"))
        if total > 50_000_000:
            raise serializers.ValidationError("Workspace source must be 50 MB or smaller.")
        return value


class AIConversationSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIConversation
        fields = ["id", "project", "title", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class AIMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIMessage
        fields = ["id", "role", "content", "context", "created_at"]
        read_only_fields = ["id", "created_at"]


class SubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subscription
        fields = ["plan", "status", "provider_customer_id", "provider_subscription_id", "current_period_end", "updated_at"]
        read_only_fields = fields


class APIKeySerializer(serializers.ModelSerializer):
    class Meta:
        model = APIKey
        fields = ["id", "name", "prefix", "last_used_at", "revoked_at", "created_at"]
        read_only_fields = fields
