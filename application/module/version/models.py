# -*- coding: utf-8 -*-
from collections import defaultdict

from django.db import models
from django.conf import settings

from module.common.models import ModelDjangoCacheHelper2
from module.common.redismodel import PartitionHashRedis
from submodule.kvs.redis_client import get_client


class Version(models.Model, ModelDjangoCacheHelper2):
    ios_app_version = models.CharField(max_length=5, default='1.00')
    android_app_version = models.CharField(max_length=5, default='1.00')
    dlc_version = models.CharField(max_length=5,  default='1.00')
    terms_and_conditions_version = models.CharField(max_length=5, default='1.00')


class DataVersion(models.Model, ModelDjangoCacheHelper2):
    new_version = models.CharField(max_length=5, default='1.00', help_text='Version should be X.XX format')
    old_version = models.CharField(max_length=5, default='1.00', help_text='Version should be X.XX format')

    class Meta:
        unique_together = ('new_version', 'old_version')

    def __unicode__(self):
        return "%s > %s" % (self.old_version, self.new_version)


class DataFile(models.Model, ModelDjangoCacheHelper2):
    RESOLUTION = [0,320,480,640]

    versions = models.ForeignKey(DataVersion)
    file = models.CharField(max_length=255)
    packed_size = models.IntegerField(help_text='File size when packed')
    unpacked_size = models.IntegerField(help_text='File size when unpacked')
    checksum = models.CharField(max_length=40, help_text='MD5 checksum of file')
    resolution = models.IntegerField(help_text='0 for resolution independent files, otherwise 320, 480 or 640')

    def __unicode__(self):
        return self.file

    def to_raw_dict(self):
        dlc_host = getattr(settings, 'DLC_HOST', getattr(settings, 'STATIC_URL', ''))
        file_url = '%s%s' % (dlc_host, self.file)

        return  {
            'file_url' : file_url,
            'checksum' : self.checksum,
            'packed_size' : self.packed_size,
            'unpacked_size' : self.unpacked_size,
            'resolution': str(self.resolution)
        }

class VersionRedis(PartitionHashRedis):
    attributes = {
        # ios app最低版本号
        'ios_app_version': {'type': str},
        # android app最低版本号
        'android_app_version': {'type': str},
        # dlc版本号
        'dlc_version': {'type': str},
    }

    def __init__(self):
        client = get_client(name='default', setting=settings.REDIS_DATABASES)
        super(VersionRedis, self).__init__('VERSION', client=client)
