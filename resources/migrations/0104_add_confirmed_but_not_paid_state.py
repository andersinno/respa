from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('resources', '0103_add_price_list'),
    ]

    operations = [
        migrations.AlterField(
            model_name='reservation',
            name='state',
            field=models.CharField(choices=[('created', 'created'), ('cancelled', 'cancelled'), ('confirmed', 'confirmed'), ('denied', 'denied'), ('requested', 'requested'), ('waiting_for_payment', 'waiting for payment'), ('confirmed_but_not_paid', 'confirmed but not paid'), ('paid', 'paid')], default='created', max_length=32, verbose_name='State'),
        ),
    ]
