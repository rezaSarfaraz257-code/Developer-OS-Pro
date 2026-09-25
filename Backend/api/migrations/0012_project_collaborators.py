from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("api", "0011_project_final_fields")]
    operations = [
        migrations.AddField(
            model_name="project",
            name="collaborators",
            field=models.ManyToManyField(blank=True, related_name="collaborated_projects", to="auth.user"),
        ),
    ]
