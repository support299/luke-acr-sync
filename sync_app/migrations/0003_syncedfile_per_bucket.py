# Track each Drive file once per ACR bucket so one file can sync to several buckets.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sync_app", "0002_add_acr_duration"),
    ]

    operations = [
        migrations.AddField(
            model_name="syncedfile",
            name="bucket_id",
            field=models.CharField(db_index=True, default="22711", max_length=32),
        ),
        migrations.AlterField(
            model_name="syncedfile",
            name="drive_file_id",
            field=models.CharField(db_index=True, max_length=255),
        ),
        migrations.AddConstraint(
            model_name="syncedfile",
            constraint=models.UniqueConstraint(
                fields=("drive_file_id", "bucket_id"),
                name="uniq_drive_file_bucket",
            ),
        ),
        migrations.AlterField(
            model_name="syncedfile",
            name="bucket_id",
            field=models.CharField(db_index=True, default="", max_length=32),
        ),
    ]
