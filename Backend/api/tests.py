from io import BytesIO
import tempfile

from django.contrib.auth.models import User
from django.db import IntegrityError, connection
from django.test import override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from cryptography.fernet import Fernet
from PIL import Image
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from .models import GitHubAccount, Project, Tag, Tool, Task


class ProjectApiSecurityTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner", password="long-test-password-123")
        self.other_user = User.objects.create_user(username="other", password="long-test-password-123")
        self.owner_project = Project.objects.create(owner=self.owner, title="Private project")
        Project.objects.create(owner=self.other_user, title="Other private project")

    def authenticate(self, user):
        self.client.force_authenticate(user=user)

    def test_projects_are_visible_only_to_their_owner(self):
        self.authenticate(self.owner)
        response = self.client.get("/api/projects/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([project["id"] for project in response.data], [self.owner_project.id])
        self.assertNotIn("owner", response.data[0])

    def test_api_responses_include_restrictive_security_headers(self):
        self.authenticate(self.owner)
        response = self.client.get("/api/projects/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("default-src 'none'", response["Content-Security-Policy"])
        self.assertEqual(response["X-Frame-Options"], "DENY")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")

    def test_cannot_access_another_users_project(self):
        self.authenticate(self.owner)
        response = self.client.get(f"/api/projects/{self.owner_project.id + 1}/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_favorites_use_the_tool_relation_without_exposing_user_id(self):
        self.authenticate(self.owner)
        tool = Tool.objects.create(name="Django", tag="Backend")

        response = self.client.post("/api/favorites/", {"tool_name": tool.name}, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["tool_name"], "Django")
        self.assertNotIn("user", response.data)

    def test_favorites_cannot_create_shared_tools(self):
        self.authenticate(self.owner)
        tool_count = Tool.objects.count()

        response = self.client.post("/api/favorites/", {"tool_name": "Unapproved Tool"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(Tool.objects.count(), tool_count)

    def test_tool_names_are_case_insensitively_unique(self):
        Tool.objects.create(name="React", tag="Frontend")

        with self.assertRaises(IntegrityError):
            Tool.objects.create(name="react", tag="Frontend")

    def test_only_staff_can_modify_shared_catalogs(self):
        self.authenticate(self.owner)
        response = self.client.post("/api/resources/", {"title": "Untrusted resource"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_logout_blacklists_the_authenticated_users_refresh_token(self):
        refresh = RefreshToken.for_user(self.owner)
        self.authenticate(self.owner)

        response = self.client.post("/api/logout/", {"refresh": str(refresh)}, format="json")

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        with self.assertRaises(TokenError):
            refresh.check_blacklist()

    def test_staff_created_tags_receive_a_unique_slug(self):
        self.owner.is_staff = True
        self.owner.save(update_fields=["is_staff"])
        self.authenticate(self.owner)

        first = self.client.post("/api/tags/", {"name": "API Security"}, format="json")
        second = self.client.post("/api/tags/", {"name": "API Security"}, format="json")

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(first.data["slug"], "api-security")
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Tag.objects.count(), 1)

    def test_profile_rejects_non_http_urls(self):
        self.authenticate(self.owner)

        response = self.client.patch("/api/profile/", {"website": "ftp://example.test"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("website", response.data)

    def test_profile_accepts_the_multipart_payload_sent_by_the_frontend(self):
        self.authenticate(self.owner)

        response = self.client.patch(
            "/api/profile/",
            {
                "first_name": "Profile",
                "last_name": "Owner",
                "email": "owner@example.test",
                "full_name": "Profile Owner",
                "bio": "Updated safely.",
                "github": "https://github.com/owner",
                "linkedin": "https://www.linkedin.com/in/owner",
                "website": "https://owner.example.test",
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["full_name"], "Profile Owner")
        self.assertEqual(response.data["website"], "https://owner.example.test")

    def test_profile_avatar_is_reencoded_and_returned_as_a_media_url(self):
        image_buffer = BytesIO()
        Image.new("RGBA", (40, 30), "#2ad9ff").save(image_buffer, format="PNG")
        avatar = SimpleUploadedFile("portrait.png", image_buffer.getvalue(), content_type="image/png")
        media_directory = tempfile.TemporaryDirectory()
        self.addCleanup(media_directory.cleanup)

        self.authenticate(self.owner)
        with override_settings(MEDIA_ROOT=media_directory.name):
            response = self.client.patch("/api/profile/", {"avatar": avatar}, format="multipart")

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertTrue(response.data["has_uploaded_avatar"])
            self.assertIn("/media/avatars/user_", response.data["avatar_url"])

            self.owner.profile.refresh_from_db()
            self.assertTrue(self.owner.profile.avatar.name.endswith(".webp"))
            with self.owner.profile.avatar.open("rb") as stored_file:
                with Image.open(stored_file) as stored_image:
                    self.assertEqual(stored_image.format, "WEBP")


class GitHubTokenEncryptionTests(APITestCase):
    @override_settings(GITHUB_TOKEN_ENCRYPTION_KEY=Fernet.generate_key().decode())
    def test_github_access_token_is_encrypted_at_rest(self):
        user = User.objects.create_user(username="token-owner", password="long-test-password-123")
        account = GitHubAccount.objects.create(user=user, login="token-owner", access_token="sensitive-token")

        with connection.cursor() as cursor:
            cursor.execute("SELECT access_token FROM api_githubaccount WHERE id = %s", [account.id])
            stored_token = cursor.fetchone()[0]

        self.assertNotEqual(stored_token, "sensitive-token")
        self.assertTrue(stored_token.startswith("enc:v1:"))
        account.refresh_from_db()
        self.assertEqual(account.access_token, "sensitive-token")

class CollaborationAndIntelligenceTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner2", email="owner2@example.test", password="long-test-password-123")
        self.member = User.objects.create_user(username="member2", email="member2@example.test", password="long-test-password-123")
        self.project = Project.objects.create(owner=self.owner, title="Shared project")

    def authenticate(self, user):
        self.client.force_authenticate(user=user)

    def test_owner_can_add_and_member_can_see_project(self):
        self.authenticate(self.owner)
        response = self.client.post(f"/api/projects/{self.project.id}/collaborators/", {"username": self.member.username}, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.authenticate(self.member)
        projects = self.client.get("/api/projects/")
        self.assertEqual(projects.status_code, status.HTTP_200_OK)
        self.assertIn(self.project.id, [item["id"] for item in projects.data])

    def test_non_owner_cannot_change_collaborators(self):
        self.project.collaborators.add(self.member)
        self.authenticate(self.member)
        response = self.client.post(f"/api/projects/{self.project.id}/collaborators/", {"username": self.owner.username}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_workspace_summary_is_real_data(self):
        from .models import Task
        Task.objects.create(project=self.project, title="Done", status="done")
        Task.objects.create(project=self.project, title="Blocked", status="blocked")
        self.authenticate(self.owner)
        response = self.client.get("/api/workspace/summary/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["projects"], 1)
        self.assertEqual(response.data["completion"], 50)
        self.assertEqual(response.data["blocked_tasks"], 1)

    def test_assistant_uses_workspace_context_without_fake_static_metrics(self):
        from .models import Task
        Task.objects.create(project=self.project, title="Urgent", priority="urgent")
        self.authenticate(self.owner)
        response = self.client.post("/api/assistant/", {"message": "What should I do next?"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["mode"], "local")
        self.assertIn("urgent", response.data["answer"].lower())


class ProductionCatalogAndOAuthTests(APITestCase):
    def test_catalog_is_publicly_readable(self):
        from .models import Resource, Workflow
        Tool.objects.create(name="Public Tool", tag="Testing")
        Resource.objects.create(title="Public Resource", link="https://example.com")
        Workflow.objects.create(title="Public Workflow", steps=["One"])

        response = self.client.get("/api/tools/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(any(item["name"] == "Public Tool" for item in response.data))

        response = self.client.get("/api/resources/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.get("/api/workflows/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @override_settings(
        GITHUB_CLIENT_ID="test-client",
        GITHUB_CLIENT_SECRET="test-secret",
        GITHUB_TOKEN_ENCRYPTION_KEY=Fernet.generate_key().decode(),
    )
    def test_github_authorization_uses_pkce(self):
        user = User.objects.create_user(username="pkce-user", password="long-test-password-123")
        self.client.force_authenticate(user=user)

        response = self.client.get("/api/github/authorize/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        authorization_url = response.data["authorization_url"]
        self.assertIn("code_challenge=", authorization_url)
        self.assertIn("code_challenge_method=S256", authorization_url)
        self.assertIn("state=", authorization_url)

        state = GitHubOAuthState.objects.get(user=user)
        self.assertTrue(state.code_verifier)

class GlobalSearchAndObservabilityTests(APITestCase):
    def test_global_search_returns_cross_catalog_results(self):
        from .models import Resource, Workflow
        Tool.objects.create(name="Searchable React", tag="Frontend", category="Frontend", description="UI library")
        Resource.objects.create(title="React search guide", category="Frontend", description="Components")
        Workflow.objects.create(title="React delivery", summary="Ship a React feature", steps=["Build"])

        response = self.client.get("/api/search/?q=React")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["results"]["tools"])
        self.assertTrue(response.data["results"]["resources"])
        self.assertTrue(response.data["results"]["workflows"])
        self.assertTrue(response["X-Request-ID"])
        self.assertIn("app;dur=", response["Server-Timing"])

    def test_global_search_rejects_unbounded_query_size(self):
        response = self.client.get("/api/search/?q=" + ("x" * 121))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class GitHubIntegrationLifecycleTests(APITestCase):
    @override_settings(GITHUB_TOKEN_ENCRYPTION_KEY=Fernet.generate_key().decode())
    def test_github_account_can_be_disconnected(self):
        user = User.objects.create_user(username="disconnect-user", password="long-test-password-123")
        GitHubAccount.objects.create(user=user, login="disconnect-user", access_token="token")
        self.client.force_authenticate(user=user)

        response = self.client.delete("/api/github/account/disconnect/")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(GitHubAccount.objects.filter(user=user).exists())

    @override_settings(GITHUB_TOKEN_ENCRYPTION_KEY=Fernet.generate_key().decode())
    def test_github_activity_filter_uses_full_repository_name(self):
        from unittest.mock import patch, Mock
        user = User.objects.create_user(username="github-filter-user", password="long-test-password-123")
        GitHubAccount.objects.create(user=user, login="github-filter-user", access_token="token")
        self.client.force_authenticate(user=user)

        def fake_get(url, **kwargs):
            response = Mock()
            response.status_code = 200
            if url.endswith("/user"):
                response.json.return_value = {"login": "github-filter-user"}
            else:
                response.json.return_value = [
                    {"id": "1", "type": "PushEvent", "repo": {"name": "owner/wanted"}},
                    {"id": "2", "type": "PushEvent", "repo": {"name": "owner/other"}},
                ]
            return response

        with patch("api.views.requests.get", side_effect=fake_get):
            response = self.client.post("/api/github/sync-activity/", {"repo_full_name": "owner/wanted"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["synced"], 1)


class PlatformUpgradeTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="platform-user", password="long-test-password-123")
        self.client.force_authenticate(user=self.user)
        self.project = Project.objects.create(owner=self.user, title="Quantum IDE", description="Build a web IDE")
        Task.objects.create(project=self.project, title="Ship editor", priority="urgent")

    def test_universal_search_scopes_to_workspace(self):
        response = self.client.get("/api/platform/search/?q=Quantum")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["results"][0]["type"], "project")

    def test_ide_workspace_is_persistent(self):
        response = self.client.post("/api/ide/workspaces/", {"name":"Main","files":{"main.py":"print(1)"}, "active_file":"main.py"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        workspace_id = response.data["id"]
        response = self.client.patch("/api/ide/workspaces/", {"id":workspace_id,"files":{"main.py":"print(2)","README.md":"# OS"}}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["files"]["main.py"], "print(2)")

    def test_organization_membership_and_subscription(self):
        response = self.client.post("/api/organizations/", {"name":"Quantum Labs"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        org_id = response.data["id"]
        response = self.client.get(f"/api/organizations/{org_id}/members/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data[0]["role"], "owner")
        response = self.client.post("/api/subscription/", {"plan":"pro"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["plan"], "pro")

    def test_comment_requires_project_access(self):
        response = self.client.post("/api/comments/", {"project":self.project.id,"body":"Ship it"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["body"], "Ship it")

    def test_api_key_returns_secret_once(self):
        response = self.client.post("/api/api-keys/", {"name":"CLI"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["key"].startswith("dos_live_"))
        self.assertNotIn("key_hash", response.data["record"])
