# -*- coding: utf-8 -*-
from django.views.decorators.http import require_http_methods
from django.conf import settings

from module.common.util import STATUS_CODE, output_response
from module.common.decorators.api import check_ip_address

from module.version.api import (
    get_version,
    get_data_version,
    get_data_file_by_version_id,
    is_IOS
)

from module.account.models import IDENTITY_TYPE
from module.version.models import VersionRedis

from module.actionlog.api import log_do_check_version

@require_http_methods(['GET'])
def fetch_domain(request):
    app_version = request.REQUEST.get('app_version', None)
    if not app_version:
        return output_response(status_code=1000, errmsg='invalid post parameter:{}'.format(app_version))

    # 是否是未发布的版本
    is_pre = False
    if is_IOS(request.META.get('HTTP_X_KK_DEVICEOS', '')):
        if app_version > settings.RELEASED_ISO_APP_VERSION:
            is_pre = True
    else:
        if app_version > settings.RELEASED_ANDROID_APP_VERSION:
            is_pre = True

    if is_pre:
        return output_response(data=settings.PRE_RELEASE_DOMAIN)
    else:
        return output_response(data=settings.RELEASED_DOMAIN)


@require_http_methods(['POST'])
def check_version(request):
    dlc_version = request.REQUEST.get('dlc_version', None)
    app_version = request.REQUEST.get('app_version', None)
    device = request.REQUEST.get('device', None)
    identity_type = request.REQUEST.get('identity_type', IDENTITY_TYPE.MAC)
    identity_id   = request.REQUEST.get('identity_id', 'XX:XX:XX:XX:XX:XX')  # default : X x 12
    identifier_for_vendor = request.REQUEST.get('identifier_for_vendor', '')

    if not dlc_version or not app_version or not device:
        return output_response(status_code=1000, errmsg='invalid post parameter:{},{},{}'.format(dlc_version,app_version,device))

    DEVICEOS = request.META.get('HTTP_X_KK_DEVICEOS', '')

    log_do_check_version(identity_type, identifier_for_vendor, identity_id)

    version = get_version()
    if not version:
        return output_response(status_code=1001, errmsg='no version record')

    app_version_db = ''
    if is_IOS(DEVICEOS):
        app_version_db = version.ios_app_version
    else:
        app_version_db = version.android_app_version

    data = {
        'app_version': app_version_db,
        'dlc_version': version.dlc_version,
        'terms_and_conditions_version': version.terms_and_conditions_version,
    }

    # 客户端是否需要升级
    if cmp(app_version,app_version_db) < 0:
        return output_response(data=data)

    dlc_host = getattr(settings, 'DLC_HOST', getattr(settings, 'STATIC_URL', ''))
    files = []

    # 资源文件是否需要升级
    if dlc_version != version.dlc_version:
        data_version = get_data_version(version.dlc_version, dlc_version)
        if data_version:
            data_file_record = get_data_file_by_version_id(data_version.id)
            dlc_dlc_data = [d.to_raw_dict() for d in data_file_record]
            files.extend(dlc_dlc_data)
        else:
            return output_response(status_code=1002, errmsg='no dlc for {}'.format(dlc_version))

    data['files'] = files

    return output_response(data=data)


@require_http_methods(['GET', 'POST'])
@check_ip_address
def update_version(request):
    dlc_version = request.REQUEST.get('dlc_version', None)
    ios_app_version = request.REQUEST.get('ios_app_version', None)
    android_app_version = request.REQUEST.get('android_app_version', None)

    if not dlc_version or not ios_app_version or not android_app_version:
        return output_response(status_code=1000, errmsg='invalid post parameter:{},{},{}'.format(dlc_version,ios_app_version, android_app_version))

    version = VersionRedis()
    if version.exists():
        version.update(dlc_version=dlc_version, ios_app_version=ios_app_version, android_app_version=android_app_version)
    else:
        version.create(dlc_version=dlc_version, ios_app_version=ios_app_version, android_app_version=android_app_version)

    return output_response(STATUS_CODE.OK)

