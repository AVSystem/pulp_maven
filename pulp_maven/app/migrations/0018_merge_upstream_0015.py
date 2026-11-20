from django.db import migrations


class Migration(migrations.Migration):
    """Join the release's 0015 with this branch's 0015-0017; they change different models."""

    dependencies = [
        ("maven", "0015_remove_global_unique_sha256_mavenmetadata"),
        ("maven", "0017_mavenpendingdeploy_pull_through"),
    ]

    operations = []
