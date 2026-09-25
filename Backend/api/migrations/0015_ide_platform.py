from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [("api", "0014_platform_upgrade")]
    operations = [
        migrations.AddField(model_name="codeworkspace", name="framework", field=models.CharField(blank=True, default="", max_length=80)),
        migrations.AddField(model_name="codeworkspace", name="runtime", field=models.CharField(blank=True, default="python", max_length=40)),
        migrations.AddField(model_name="codeworkspace", name="package_manager", field=models.CharField(blank=True, default="", max_length=30)),
        migrations.CreateModel(
            name="FrameworkInstallation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("framework", models.CharField(max_length=80)),
                ("package_manager", models.CharField(max_length=30)),
                ("status", models.CharField(choices=[("queued","Queued"),("running","Running"),("success","Success"),("failed","Failed")], default="queued", max_length=20)),
                ("output", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("workspace", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="installations", to="api.codeworkspace")),
            ],
        ),
        migrations.CreateModel(
            name="IDEExecution",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("command", models.CharField(max_length=2000)),
                ("status", models.CharField(choices=[("queued","Queued"),("running","Running"),("success","Success"),("failed","Failed"),("timeout","Timeout")], default="queued", max_length=20)),
                ("stdout", models.TextField(blank=True, default="")),
                ("stderr", models.TextField(blank=True, default="")),
                ("exit_code", models.IntegerField(blank=True, null=True)),
                ("duration_ms", models.IntegerField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("workspace", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="executions", to="api.codeworkspace")),
            ],
        ),
    ]
