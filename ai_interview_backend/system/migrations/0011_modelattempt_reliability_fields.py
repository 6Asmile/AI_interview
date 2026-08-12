from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('system', '0010_modelattempt'),
    ]

    operations = [
        migrations.AddField(
            model_name='modelattempt',
            name='error_category',
            field=models.CharField(blank=True, max_length=32),
        ),
        migrations.AddField(
            model_name='modelattempt',
            name='estimated_cost',
            field=models.DecimalField(decimal_places=6, default=0, max_digits=12),
        ),
        migrations.AddField(
            model_name='modelattempt',
            name='provider_request_id',
            field=models.CharField(blank=True, max_length=200),
        ),
    ]
