from decimal import Decimal
import django.contrib.postgres.fields.jsonb
from django.db import migrations

TAX_PERCENTAGES = [
    Decimal(x)
    for x in (
        "0.00",
        "10.00",
        "14.00",
        "24.00",
        "25.50",
    )
]

def convert_cost_center_code(apps, schema_editor):
    Unit = apps.get_model('resources', 'Unit')
    for unit in Unit.objects.all():
        original_value = unit.cost_center_code_old
        if original_value:
            new_value = {str(tax): original_value for tax in TAX_PERCENTAGES}
            unit.cost_center_code = new_value
            unit.save(update_fields=['cost_center_code'])
            print('Converting cost_center_code for unit {} from {} to {}'.format(unit.id, original_value, new_value), flush=True)


def reverse_cost_center_code(apps, schema_editor):
    Unit = apps.get_model('resources', 'Unit')
    for unit in Unit.objects.all():
        json_value = unit.cost_center_code
        # Take the first value if available (priority to 0.00%)
        if json_value and isinstance(json_value, dict):
            # Try to get the 0.00% value first, or fall back to any value
            if "0.00" in json_value:
                unit.cost_center_code_old = json_value["0.00"]
            elif len(json_value) > 0:
                unit.cost_center_code_old = next(iter(json_value.values()))
            else:
                unit.cost_center_code_old = ""
        else:
            unit.cost_center_code_old = ""
        unit.save(update_fields=['cost_center_code_old'])
        print('Reverting cost_center_code for unit {} from {} to {}'.format(unit.id, json_value, unit.cost_center_code_old), flush=True)

class Migration(migrations.Migration):

    dependencies = [
        ('resources', '0130_resource_people_capacity_upper'),
    ]

    operations = [
        # First add a temporary field or rename existing field
        migrations.RenameField(
            model_name='unit',
            old_name='cost_center_code',
            new_name='cost_center_code_old',
        ),
        # Add the new JSONField
        migrations.AddField(
            model_name='unit',
            name='cost_center_code',
            field=django.contrib.postgres.fields.jsonb.JSONField(blank=True, null=True, default=dict, verbose_name='CeePos Cost center code'),
        ),
        # Run the data migration with reverse function
        migrations.RunPython(convert_cost_center_code, reverse_cost_center_code),
        # Remove the old field
        migrations.RemoveField(
            model_name='unit',
            name='cost_center_code_old',
        ),
    ]
