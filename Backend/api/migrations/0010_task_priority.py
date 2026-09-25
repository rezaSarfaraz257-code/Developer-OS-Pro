from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [("api", "0009_tool_name_case_insensitive_unique")]
    operations = [
        migrations.AddField(
            model_name="task",
            name="priority",
            field=models.CharField(
                choices=[("low", "Low"), ("medium", "Medium"), ("high", "High"), ("urgent", "Urgent")],
                default="medium",
                max_length=16,
            ),
        ),
    ]
