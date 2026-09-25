from uuid import uuid4

from django.contrib.auth.models import User
from django.db import models
from django.db.models.functions import Lower
from django.utils.text import slugify

from .fields import EncryptedTextField

def profile_avatar_upload_to(instance, _filename):
    """Store avatars under an opaque, user-scoped name.

    The API re-encodes every accepted avatar as WebP before saving it, so the
    generated extension is deliberate rather than supplied by the client.
    """
    return f"avatars/user_{instance.user_id}/{uuid4().hex}.webp"


# Create your models here.

class Project(models.Model):
    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="projects"
    )

    CATEGORY_CHOICES = [
        ("Frontend", "Frontend"),
        ("Backend", "Backend"),
        ("DevOps", "DevOps"),
        ("AI", "AI"),
        ("Design", "Design"),
        ("Productivity", "Productivity"),
        ("General", "General"),
    ]

    STATUS_CHOICES = [
        ("In Progress", "In Progress"),
        ("Planning", "Planning"),
        ("Completed", "Completed"),
        ("On Hold", "On Hold"),
    ]

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    category = models.CharField(
        max_length=50,
        choices=CATEGORY_CHOICES,
        default="General"
    )
    tags = models.JSONField(default=list, blank=True)
    link = models.URLField(blank=True, default="")
    status = models.CharField(
        max_length=40,
        choices=STATUS_CHOICES,
        default="In Progress",
    )
    PRIORITY_CHOICES = [("low", "Low"), ("medium", "Medium"), ("high", "High"), ("urgent", "Urgent")]
    priority = models.CharField(max_length=16, choices=PRIORITY_CHOICES, default="medium")
    start_date = models.DateField(null=True, blank=True)
    deadline = models.DateField(null=True, blank=True)
    repository_url = models.URLField(blank=True, default="")
    stack = models.JSONField(default=list, blank=True)
    collaborators = models.ManyToManyField(User, related_name="collaborated_projects", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    uploaded_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    full_name = models.CharField(max_length=200, blank=True, default="")
    avatar = models.ImageField(upload_to=profile_avatar_upload_to, blank=True)
    avatar_url = models.URLField(blank=True, default="")
    bio = models.TextField(blank=True, default="")
    github = models.URLField(blank=True, default="")
    linkedin = models.URLField(blank=True, default="")
    x = models.URLField(blank=True, default="")
    website = models.URLField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} profile"

class Resource(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    resource_type = models.CharField(max_length=50, default="Guide")
    category = models.CharField(max_length=80, default="General")
    link = models.URLField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

class Workflow(models.Model):
    title = models.CharField(max_length=200)
    level = models.CharField(max_length=50, default="Beginner")
    duration = models.CharField(max_length=50, default="Flexible")
    summary = models.TextField(blank=True, default="")
    steps = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

class Tool(models.Model):
    CATEGORY_CHOICES = [
        ("Frontend", "Frontend"),
        ("Backend", "Backend"),
        ("DevOps", "DevOps"),
        ("AI", "AI"),
        ("Design", "Design"),
        ("Productivity", "Productivity"),
        ("General", "General"),
    ]

    name = models.CharField(max_length=120)
    tag = models.CharField(max_length=50, default="General")
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default="General")
    description = models.TextField(blank=True, default="")
    accent = models.CharField(max_length=20, default="cyan")
    rating = models.DecimalField(max_digits=3, decimal_places=1, default=4.5)
    features = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    class Meta:
        constraints = [
            models.UniqueConstraint(
                Lower("name"),
                name="unique_tool_name_case_insensitive",
            )
        ]

class Favorite(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="favorites"
    )

    tool = models.ForeignKey(
        Tool,
        on_delete=models.CASCADE,
        related_name="favorited_by",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "tool"],
                name="unique_user_tool_favorite"
            )
        ]

    def __str__(self):
        return f"{self.user.username}: {self.tool.name}"

class Tag(models.Model):
    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(max_length=100, unique=True, blank=True)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)[:90] or "tag"
            candidate = base_slug
            suffix = 2
            while type(self).objects.exclude(pk=self.pk).filter(slug=candidate).exists():
                candidate = f"{base_slug[:95 - len(str(suffix))]}-{suffix}"
                suffix += 1
            self.slug = candidate
        super().save(*args, **kwargs)

class Task(models.Model):
    STATUS = [
        ("todo", "To Do"),
        ("in_progress", "In Progress"),
        ("done", "Done"),
        ("blocked", "Blocked"),
    ]

    PRIORITY = [
        ("low", "Low"),
        ("medium", "Medium"),
        ("high", "High"),
        ("urgent", "Urgent"),
    ]

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="tasks",
        null=True,
        blank=True,
    )

    assignee = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_tasks",
    )

    status = models.CharField(
        max_length=32,
        choices=STATUS,
        default="todo",
    )

    priority = models.CharField(
        max_length=16,
        choices=PRIORITY,
        default="medium",
    )

    title = models.CharField(
        max_length=200
    )

    description = models.TextField(
        blank=True,
        default=""
    )

    due_date = models.DateField(
        null=True,
        blank=True
    )

    tags = models.JSONField(
        default=list,
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    def __str__(self):
        return self.title

class Note(models.Model):
    title = models.CharField(max_length=200, blank=True, default="")
    content = models.TextField()
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="notes")
    project = models.ForeignKey(Project, on_delete=models.CASCADE, null=True, blank=True, related_name="notes")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title or f"Note {self.pk}"

class Activity(models.Model):
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="activities")
    verb = models.CharField(max_length=200)
    message = models.TextField(blank=True, default="")
    related_type = models.CharField(max_length=100, blank=True, default="")
    related_id = models.IntegerField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.actor or 'System'} {self.verb}"

class Snippet(models.Model):
    LANGUAGE_CHOICES = [
        ("py", "Python"),
        ("js", "JavaScript"),
        ("sh", "Shell"),
        ("sql", "SQL"),
        ("md", "Markdown"),
        ("txt", "Text"),
    ]

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="snippets",
        null=True,
        blank=True,
    )

    title = models.CharField(max_length=200)
    code = models.TextField()
    language = models.CharField(max_length=10, choices=LANGUAGE_CHOICES, default="py")
    description = models.TextField(blank=True, default="")
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="snippets")
    tags = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

class GitHubOAuthState(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="github_states")
    state = models.CharField(max_length=200, unique=True)
    code_verifier = models.CharField(max_length=128, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    used = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.user.username} - {self.state}"

class GitHubAccount(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="github_account")
    github_id = models.IntegerField(null=True, blank=True)
    login = models.CharField(max_length=200, blank=True, default="")
    access_token = EncryptedTextField(blank=True, default="")
    scope = models.CharField(max_length=200, blank=True, default="")
    token_type = models.CharField(max_length=50, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} -> {self.login or 'github'}"



# =========================================================
# DEVELOPER OS 2.0 — Intelligence / Collaboration / SaaS / IDE
# =========================================================

class Organization(models.Model):
    PLAN_CHOICES = [("free", "Free"), ("pro", "Pro"), ("team", "Team"), ("enterprise", "Enterprise")]
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="owned_organizations")
    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=180, unique=True)
    plan = models.CharField(max_length=20, choices=PLAN_CHOICES, default="free")
    provider_customer_id = models.CharField(max_length=180, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class OrganizationMembership(models.Model):
    ROLE_CHOICES = [("owner", "Owner"), ("admin", "Admin"), ("developer", "Developer"), ("viewer", "Viewer")]
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="organization_memberships")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="developer")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["organization", "user"], name="unique_org_member")]


class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    kind = models.CharField(max_length=40, default="system")
    title = models.CharField(max_length=180)
    body = models.TextField(blank=True, default="")
    link = models.CharField(max_length=500, blank=True, default="")
    read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "read", "-created_at"]),
            models.Index(fields=["user", "-created_at"]),
        ]


class Comment(models.Model):
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name="comments")
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="comments", null=True, blank=True)
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="comments", null=True, blank=True)
    body = models.TextField(max_length=10000)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class TaskDependency(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="dependencies")
    depends_on = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="dependents")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["task", "depends_on"], name="unique_task_dependency"),
        ]


class ProjectInvite(models.Model):
    ROLE_CHOICES = [("admin", "Admin"), ("developer", "Developer"), ("viewer", "Viewer")]
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="invites")
    inviter = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sent_project_invites")
    email = models.EmailField()
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="developer")
    token = models.CharField(max_length=96, unique=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class CodeWorkspace(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="code_workspaces")
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="code_workspaces", null=True, blank=True)
    name = models.CharField(max_length=160, default="Untitled Workspace")
    files = models.JSONField(default=dict, blank=True)
    active_file = models.CharField(max_length=500, default="main.py")
    language = models.CharField(max_length=40, default="python")
    framework = models.CharField(max_length=80, blank=True, default="")
    runtime = models.CharField(max_length=40, blank=True, default="python")
    package_manager = models.CharField(max_length=30, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["owner", "-updated_at"])]

class FrameworkInstallation(models.Model):
    STATUS_CHOICES = [("queued", "Queued"), ("running", "Running"), ("success", "Success"), ("failed", "Failed")]
    workspace = models.ForeignKey(CodeWorkspace, on_delete=models.CASCADE, related_name="installations")
    framework = models.CharField(max_length=80)
    package_manager = models.CharField(max_length=30)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="queued")
    output = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

class IDEExecution(models.Model):
    STATUS_CHOICES = [("queued", "Queued"), ("running", "Running"), ("success", "Success"), ("failed", "Failed"), ("timeout", "Timeout")]
    workspace = models.ForeignKey(CodeWorkspace, on_delete=models.CASCADE, related_name="executions")
    command = models.CharField(max_length=2000)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="queued")
    stdout = models.TextField(blank=True, default="")
    stderr = models.TextField(blank=True, default="")
    exit_code = models.IntegerField(null=True, blank=True)
    duration_ms = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)


class AIConversation(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="ai_conversations")
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="ai_conversations", null=True, blank=True)
    title = models.CharField(max_length=200, default="New conversation")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class AIMessage(models.Model):
    ROLE_CHOICES = [("system", "System"), ("user", "User"), ("assistant", "Assistant"), ("tool", "Tool")]
    conversation = models.ForeignKey(AIConversation, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content = models.TextField()
    context = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class Subscription(models.Model):
    PLAN_CHOICES = [("free", "Free"), ("pro", "Pro"), ("team", "Team"), ("enterprise", "Enterprise")]
    STATUS_CHOICES = [("trialing", "Trialing"), ("active", "Active"), ("past_due", "Past due"), ("canceled", "Canceled")]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="subscription")
    plan = models.CharField(max_length=20, choices=PLAN_CHOICES, default="free")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    provider_customer_id = models.CharField(max_length=180, blank=True, default="")
    provider_subscription_id = models.CharField(max_length=180, blank=True, default="")
    current_period_end = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)


class APIKey(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="api_keys")
    name = models.CharField(max_length=100)
    prefix = models.CharField(max_length=16)
    key_hash = models.CharField(max_length=128, unique=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["user", "revoked_at"])]
