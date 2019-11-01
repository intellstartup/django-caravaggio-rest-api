# Generated by Django 2.2.5 on 2019-09-16 18:44

import caravaggio_rest_api.users.models
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('auth', '0011_update_proxy_permissions'),
    ]

    operations = [
        migrations.CreateModel(
            name='CaravaggioClient',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('email', models.EmailField(max_length=254, unique=True, verbose_name='email address')),
                ('name', models.CharField(max_length=100, verbose_name='client name')),
                ('is_active', models.BooleanField(default=True, help_text='Designates whether this client should be treated as active. Unselect this instead of deleting clients.', verbose_name='active')),
                ('date_joined', models.DateTimeField(default=django.utils.timezone.now, verbose_name='date joined')),
                ('date_deactivated', models.DateTimeField(blank=True, null=True, verbose_name='date deactivated')),
            ],
            options={
                'db_table': 'caravaggio_client',
                'ordering': ['-date_joined'],
            },
        ),
        migrations.CreateModel(
            name='CaravaggioUser',
            fields=[
                ('password', models.CharField(max_length=128, verbose_name='password')),
                ('last_login', models.DateTimeField(blank=True, null=True, verbose_name='last login')),
                ('is_superuser', models.BooleanField(default=False, help_text='Designates that this user has all permissions without explicitly assigning them.', verbose_name='superuser status')),
                ('first_name', models.CharField(blank=True, max_length=30, verbose_name='first name')),
                ('last_name', models.CharField(blank=True, max_length=150, verbose_name='last name')),
                ('is_staff', models.BooleanField(default=False, help_text='Designates whether the user can log into this admin site.', verbose_name='staff status')),
                ('is_active', models.BooleanField(default=True, help_text='Designates whether this user should be treated as active. Unselect this instead of deleting accounts.', verbose_name='active')),
                ('date_joined', models.DateTimeField(default=django.utils.timezone.now, verbose_name='date joined')),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('username', models.CharField(error_messages={'unique': 'A user with that username already exists.'}, max_length=150, unique=True, verbose_name='username')),
                ('email', models.EmailField(max_length=254, verbose_name='email address')),
                ('is_client_staff', models.BooleanField(default=False, help_text='Designates whether the user can operate with client users.', verbose_name='client staff status')),
                ('date_deactivated', models.DateTimeField(blank=True, null=True, verbose_name='date deactivated')),
                ('client', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='users.CaravaggioClient')),
                ('groups', models.ManyToManyField(blank=True, help_text='The groups this user belongs to. A user will get all permissions granted to each of their groups.', related_name='user_set', related_query_name='user', to='auth.Group', verbose_name='groups')),
                ('user_permissions', models.ManyToManyField(blank=True, help_text='Specific permissions for this user.', related_name='user_set', related_query_name='user', to='auth.Permission', verbose_name='user permissions')),
            ],
            options={
                'db_table': 'caravaggio_user',
                'ordering': ['-date_joined'],
                'swappable': 'AUTH_USER_MODEL',
                'unique_together': {('client', 'email')},
            },
            managers=[
                ('objects', caravaggio_rest_api.users.models.CaravaggioUserManager()),
            ],
        ),
        migrations.CreateModel(
            name='CaravaggioOrganization',
            fields=[
                ('id', models.UUIDField(editable=False, primary_key=True, serialize=False)),
                ('email', models.EmailField(max_length=254, verbose_name='email address')),
                ('name', models.CharField(max_length=100, verbose_name='client name')),
                ('number_of_total_members', models.PositiveIntegerField(default=1)),
                ('number_of_administrators', models.PositiveIntegerField(default=0)),
                ('number_of_members', models.PositiveIntegerField(default=0)),
                ('number_of_restricted_members', models.PositiveIntegerField(default=0)),
                ('is_active', models.BooleanField(default=True, help_text='Designates whether this organization should be treated as active. Unselect this instead of deleting organizations.', verbose_name='active')),
                ('created', models.DateTimeField(default=django.utils.timezone.now, verbose_name='created')),
                ('updated', models.DateTimeField(default=django.utils.timezone.now, verbose_name='updated')),
                ('date_deactivated', models.DateTimeField(blank=True, null=True, verbose_name='date deactivated')),
                ('administrators', models.ManyToManyField(blank=True, related_name='administrator_of', to=settings.AUTH_USER_MODEL)),
                ('all_members', models.ManyToManyField(blank=True, related_name='organizations', to=settings.AUTH_USER_MODEL)),
                ('client', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='users.CaravaggioClient')),
                ('members', models.ManyToManyField(blank=True, related_name='member_of', to=settings.AUTH_USER_MODEL)),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='owner_of', to=settings.AUTH_USER_MODEL)),
                ('restricted_members', models.ManyToManyField(blank=True, related_name='restricted_member_of', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'caravaggio_organization',
                'ordering': ['-created'],
                'unique_together': {('client', 'email')},
            },
        ),
    ]