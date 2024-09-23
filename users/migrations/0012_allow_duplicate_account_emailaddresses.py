from django.db import migrations

class Migration(migrations.Migration):

    dependencies = [
        ('account', '0002_email_max_length'),
        ('users', '0011_change_last_name_length'),
    ]

    operations = [
        migrations.RunSQL(
            sql=[
                """
                DO $$ 
                DECLARE
                    r RECORD;
                BEGIN
                    FOR r IN 
                        SELECT conname 
                        FROM pg_constraint
                        JOIN pg_class ON conrelid = pg_class.oid
                        WHERE pg_class.relname = 'account_emailaddress'
                            AND conname LIKE '%email%'
                            AND contype = 'u'
                    LOOP
                        EXECUTE 'ALTER TABLE account_emailaddress DROP CONSTRAINT ' || r.conname;
                    END LOOP;
                END $$;
                """,
                "ALTER TABLE account_emailaddress ADD CONSTRAINT account_emailaddress_email_key UNIQUE (user_id, email);",
            ],
            reverse_sql=[
                "ALTER TABLE account_emailaddress DROP CONSTRAINT account_emailaddress_email_key;",
                "ALTER TABLE account_emailaddress ADD CONSTRAINT account_emailaddress_email_key UNIQUE (email);",
            ],
        ),
    ]
