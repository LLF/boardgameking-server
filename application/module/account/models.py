# -*- coding: utf-8 -*-
import random

from django.db import models
from django.conf import settings

from horizontalpartitioning.models import HorizontalPartitioningModel
from submodule.kvs.redis_client import get_client

from module.common.enum import enum
from module.common.redismodel import DefaultRedis, PartitionRedis

# 账户类型
IDENTITY_TYPE = enum('MAC', 'GAME_CENTER')

IDENTITY_TYPE_CHOICE = (
        (IDENTITY_TYPE.MAC, 'MAC'),
        (IDENTITY_TYPE.GAME_CENTER, 'GAME_CENTER'),
)

# 创建账户时和用户登录时记录该账户相关的数据
class IdentifierForVendorAndMac2(HorizontalPartitioningModel):
    HORIZONTAL_PARTITIONING_KEY_FIELD = 'player_id'

    player_id = models.CharField(max_length=255)
    identifier_for_vendor = models.CharField(max_length=255)
    mac_address = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = (('player_id', 'identifier_for_vendor', 'mac_address'),)

# 用于解决IOS6.1.x上出现的IdentifierForVendor改变的问题
class IdentifierForVendorAndMac3(HorizontalPartitioningModel):
    HORIZONTAL_PARTITIONING_KEY_FIELD = 'player_id'

    player_id = models.CharField(max_length=255, primary_key=True)
    mac_address = models.CharField(max_length=255, db_index=True)
    identifier_for_vendor = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

class IdentifierPairLog(HorizontalPartitioningModel):
    HORIZONTAL_PARTITIONING_KEY_FIELD = 'player_id'

    player_id = models.CharField(max_length=255)
    identifier_for_vendor = models.CharField(max_length=255)
    identifier_for_vendor_native = models.CharField(max_length=255, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = (('player_id', 'identifier_for_vendor', 'identifier_for_vendor_native'))

class Account(HorizontalPartitioningModel):
    HORIZONTAL_PARTITIONING_KEY_FIELD = 'player_id'

    #系统内用户ID
    player_id   = models.CharField(max_length=20, primary_key=True)

    # 设备MAC（匿名登录时绑定的设备MAC地址） IOS上改用IdentifierForVendor
    mac_address = models.CharField(max_length=255, default=None, null=True, unique=True)

    # 用户账号（非匿名登录时所绑定非系统内账号，如GC，微博等）
    identity_id = models.CharField(max_length=255, default=None, null=True)

    # 用户帐号类型
    identity_type = models.PositiveIntegerField(choices=IDENTITY_TYPE_CHOICE)

    # 创建时间
    created_at = models.DateTimeField(auto_now_add=True)

    # 修改时间
    last_modified_at = models.DateTimeField(auto_now=True)

    # 访问UUID
    uuid = models.CharField(max_length=255)

    class Meta:
        unique_together = (('identity_type', 'identity_id'),)


class UUID2PlayerID(PartitionRedis):
    def __init__(self, primary_key, client=None, readonly=False):
        super(UUID2PlayerID, self).__init__(primary_key, client, readonly=readonly)

    def get(self):
        return self.client.get(self.get_key())

    def set(self, value):
        return self.client.set(self.get_key(),value)

    def delete(self):
        return self.client.delete(self.get_key())


class Identity2PlayerID(UUID2PlayerID):
    def __init__(self, identity_type, identity_id, client=None, readonly=False):
        primary_key = "{}:{}".format(identity_type,identity_id)
        super(Identity2PlayerID, self).__init__(primary_key, client, readonly=readonly)


class PlayerIDGenerator(DefaultRedis):
    def __init__(self):
        super(PlayerIDGenerator, self).__init__(u'PLAYER_ID_COUNTER')

    def _check_exists_or_create(self):
        if not self.exists():
            # 用户ID的初始值，从0开始
            self.client.set(self.get_key(), 0)
            self.stored = True

    def get_counter(self):
        self._check_exists_or_create()
        return self.client.get(self.get_key())

    def get_next_player_id(self):
        self._check_exists_or_create()

        gz_id = settings.GAMEZONE_ID
        salt = random.randint(0,99)
        next_counter = self.client.incr(self.get_key())
        return "%d%02d%08d" % (gz_id, salt, next_counter)



# GNA对应player表
class PlayerGNA(HorizontalPartitioningModel):
    """
    Player for GNA
    """
    #osuser = models.OneToOneField(OpenSocialUser, primary_key=True)
    osuser_id = models.CharField(max_length=255, primary_key=True)
    is_closed = models.PositiveIntegerField(default=0)
    closed_at = models.DateTimeField(default=None, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now_add=True, auto_now=True)

    HORIZONTAL_PARTITIONING_KEY_FIELD = 'osuser_id'

    class Meta:
        db_table = 'player_player'


class IdentiyidInMaintenance(DefaultRedis):
    def __init__(self):
        super(IdentiyidInMaintenance, self).__init__('')

    def add(self, identity_id):
        return self.client.sadd(self.get_key(), identity_id)

    def has_identity_id(self, identity_id):
        return self.client.sismember(self.get_key(), identity_id)

    def count(self):
        return self.client.scard(self.get_key())

    def delete(self, identity_id):
        return self.client.srem(self.get_key(), identity_id)


class PlayerName(HorizontalPartitioningModel):
    HORIZONTAL_PARTITIONING_KEY_FIELD = 'player_id'

    #系统内用户ID
    player_id   = models.CharField(max_length=20, primary_key=True)

    # 用户名字
    name = models.CharField(max_length=255, db_index=True)

    # 创建时间
    created_at = models.DateTimeField(auto_now_add=True)

    # 修改时间
    last_modified_at = models.DateTimeField(auto_now=True)
