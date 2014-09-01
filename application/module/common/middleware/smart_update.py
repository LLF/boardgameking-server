# -*- coding: utf-8 -*-

from django.db.models import Model
from django.db.models.query import QuerySet


org_save = Model.save
org_update = QuerySet._update
org_init = Model.__init__


def _smart_save(self, force_insert=False, force_update=False, using=None):
    if force_update:
        QuerySet._update = org_update
    else:
        QuerySet._update = _smart_update
    org_save(self, force_insert, force_update, using)


def _smart_update(self, values):
    '''
    変更のあったフィールドのみ更新
    '''
    model = self[0]
    if not hasattr(model, '_init_dict'):
        return org_update(self, values)

    diff = {}
    update_fields = [f.name for f in model._meta.fields if not f.primary_key]
    assert len(update_fields), len(values)
    for i, f in enumerate(update_fields):
        after = values[i][2]
        before = model._init_dict[f]
        if before != after:
            diff[f] = after
    if not diff:
        return False  # 変更対象なしの場合

    # DB反映
    self.update(**diff)

    # 変更後データを変更前dictに保存
    for i, f in enumerate(update_fields):
        model._init_dict[f] = values[i]
    return True


def _smart_init(self, *args, **kw):
    '''
    DBからデータ取得時に変更前データを保持
    '''
    fields = self._meta.fields
    if args and len(fields) == len(args):
        field_names = map((lambda x: x.name), fields)
        self._init_dict = dict(zip(field_names, args))
    else:
        self._init_dict = {}
    org_init(self, *args, **kw)


def _smart_get_or_create(self, **kwargs):
    defaults = kwargs.pop('defaults', {})
    lookup = kwargs.copy()
    for f in self.model._meta.fields:
        if f.attname in lookup:
            lookup[f.name] = lookup.pop(f.attname)
    try:
        self._for_write = True
        return self.get(**lookup), False
    except self.model.DoesNotExist:
        params = dict([(k, v) for k, v in kwargs.items() if '__' not in k])
        params.update(defaults)
        obj = self.model(**params)
        obj.save(force_insert=True, using=self.db)
        return obj, True


class SmartUpdate(object):
    def __init__(self):
        Model.__init__ = _smart_init
        Model.save = _smart_save
        QuerySet.get_or_create = _smart_get_or_create


def test():
    '''
    from django.db.utils import DatabaseError
    from common.middleware.smart_update import SmartUpdate
    SmartUpdate()
    pid = request.player.pk
    p1 = player.api.get_player(pid)
    p2 = player.api.get_player(pid)
    p1_point = p1.point
    p2_money = p2.money
    p1.point += 10
    p1.save()
    p2.money += 10
    p2.save()
    p3 = player.api.get_player(pid)
    check(p3.point, p2.point)
    check(p3.money, p2.money)

    card = card.api.get_cards()[0]
    check.die(lambda: card.save(force_update=True), DatabaseError("Forced update did not affect any rows."))
    card.pk = 0
    check.die(lambda: card.save(force_insert=True))
    '''
    pass
