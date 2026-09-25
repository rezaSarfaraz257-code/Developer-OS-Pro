from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ("api", "0012_project_collaborators"),
    ]

    operations = [
        migrations.AddField(
            model_name="githuboauthstate",
            name="code_verifier",
            field=models.CharField(blank=True, default="", max_length=128),
        ),
    ]
