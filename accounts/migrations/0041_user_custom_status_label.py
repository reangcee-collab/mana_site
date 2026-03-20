from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0040_remove_user_dashboard_status_label_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='custom_status_label',
            field=models.CharField(blank=True, default='', max_length=120),
        ),
    ]
