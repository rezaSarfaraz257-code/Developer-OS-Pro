from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0013_github_oauth_pkce"),
    ]

    operations = [
        migrations.CreateModel(
            name="Organization",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=160)),
                ("slug", models.SlugField(max_length=180, unique=True)),
                ("plan", models.CharField(choices=[("free","Free"),("pro","Pro"),("team","Team"),("enterprise","Enterprise")], default="free", max_length=20)),
                ("provider_customer_id", models.CharField(blank=True, default="", max_length=180)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="owned_organizations", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="Notification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(default="system", max_length=40)),
                ("title", models.CharField(max_length=180)),
                ("body", models.TextField(blank=True, default="")),
                ("link", models.CharField(blank=True, default="", max_length=500)),
                ("read", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="notifications", to=settings.AUTH_USER_MODEL)),
            ],
            options={"indexes":[models.Index(fields=["user","read","-created_at"], name="api_notif_user_read_created"), models.Index(fields=["user","-created_at"], name="api_notif_user_created")]},
        ),
        migrations.CreateModel(
            name="CodeWorkspace",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(default="Untitled Workspace", max_length=160)),
                ("files", models.JSONField(blank=True, default=dict)),
                ("active_file", models.CharField(default="main.py", max_length=500)),
                ("language", models.CharField(default="python", max_length=40)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="code_workspaces", to=settings.AUTH_USER_MODEL)),
                ("project", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="code_workspaces", to="api.project")),
            ],
            options={"indexes":[models.Index(fields=["owner","-updated_at"], name="api_codework_owner_updated")]},
        ),
        migrations.CreateModel(
            name="Subscription",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("plan", models.CharField(choices=[("free","Free"),("pro","Pro"),("team","Team"),("enterprise","Enterprise")], default="free", max_length=20)),
                ("status", models.CharField(choices=[("trialing","Trialing"),("active","Active"),("past_due","Past due"),("canceled","Canceled")], default="active", max_length=20)),
                ("provider_customer_id", models.CharField(blank=True, default="", max_length=180)),
                ("provider_subscription_id", models.CharField(blank=True, default="", max_length=180)),
                ("current_period_end", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="subscription", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="AIConversation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(default="New conversation", max_length=200)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="ai_conversations", to=settings.AUTH_USER_MODEL)),
                ("project", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="ai_conversations", to="api.project")),
            ],
        ),
        migrations.CreateModel(
            name="APIKey",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100)),
                ("prefix", models.CharField(max_length=16)),
                ("key_hash", models.CharField(max_length=128, unique=True)),
                ("last_used_at", models.DateTimeField(blank=True, null=True)),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="api_keys", to=settings.AUTH_USER_MODEL)),
            ],
            options={"indexes":[models.Index(fields=["user","revoked_at"], name="api_apikey_user_revoked")]},
        ),
        migrations.CreateModel(
            name="OrganizationMembership",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("role", models.CharField(choices=[("owner","Owner"),("admin","Admin"),("developer","Developer"),("viewer","Viewer")], default="developer", max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="memberships", to="api.organization")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="organization_memberships", to=settings.AUTH_USER_MODEL)),
            ],
            options={"constraints":[models.UniqueConstraint(fields=("organization","user"), name="unique_org_member")]},
        ),
        migrations.CreateModel(
            name="Comment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("body", models.TextField(max_length=10000)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("author", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="comments", to=settings.AUTH_USER_MODEL)),
                ("project", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="comments", to="api.project")),
                ("task", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="comments", to="api.task")),
            ],
        ),
        migrations.CreateModel(
            name="ProjectInvite",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("email", models.EmailField(max_length=254)),
                ("role", models.CharField(choices=[("admin","Admin"),("developer","Developer"),("viewer","Viewer")], default="developer", max_length=20)),
                ("token", models.CharField(max_length=96, unique=True)),
                ("expires_at", models.DateTimeField()),
                ("accepted_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("inviter", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="sent_project_invites", to=settings.AUTH_USER_MODEL)),
                ("project", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="invites", to="api.project")),
            ],
        ),
        migrations.CreateModel(
            name="TaskDependency",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("depends_on", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="dependents", to="api.task")),
                ("task", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="dependencies", to="api.task")),
            ],
            options={"constraints":[models.UniqueConstraint(fields=("task","depends_on"), name="unique_task_dependency")]},
        ),
        migrations.CreateModel(
            name="AIMessage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("role", models.CharField(choices=[("system","System"),("user","User"),("assistant","Assistant"),("tool","Tool")], max_length=20)),
                ("content", models.TextField()),
                ("context", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("conversation", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="messages", to="api.aiconversation")),
            ],
            options={"ordering":["created_at"]},
        ),
    ]
