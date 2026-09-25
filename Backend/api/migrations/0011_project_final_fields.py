from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("api", "0010_task_priority")]
    operations = [
        migrations.AddField(model_name="project", name="priority", field=models.CharField(choices=[("low", "Low"), ("medium", "Medium"), ("high", "High"), ("urgent", "Urgent")], default="medium", max_length=16)),
        migrations.AddField(model_name="project", name="start_date", field=models.DateField(blank=True, null=True)),
        migrations.AddField(model_name="project", name="deadline", field=models.DateField(blank=True, null=True)),
        migrations.AddField(model_name="project", name="repository_url", field=models.URLField(blank=True, default="")),
        migrations.AddField(model_name="project", name="stack", field=models.JSONField(blank=True, default=list)),
    ]
