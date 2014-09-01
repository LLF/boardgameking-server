# -*- coding: utf-8 -*-

import os
import codecs
from collections import defaultdict
import glob
import traceback
import re
import json
import urllib2
import urllib
import commands

from module.version.ziputils import get_zip_metadata,generate_zips,copy_zips


from django.conf import settings
from module.version.models import DataVersion, DataFile, Version
from module.gamezone.models import GameZone

from boto.s3.connection import S3Connection
from boto.s3.key import Key


RESOLUTIONS = [320, 480, 640]

DLC_ZIP_PATH    = '../static/'

def get_version():
    version = None
    try:
        version = Version.objects.all()[0]
    except:
        pass

    print 'version------'
    print version
    return version


def get_data_version(new_version, old_version):
    cache_all = DataVersion.get_cache_all()
    for dv in cache_all:
        if dv.new_version == new_version and dv.old_version == old_version:
            return dv
    return None


def get_data_file_by_version_id(version_id):
    cache_all = DataFile.get_cache_all()
    df_list = []
    for df in cache_all:
        if df.versions_id == version_id:
            df_list.append(df)
    return df_list


def update_dlc_db(ios_app_version, android_app_version):
    try:
        # 根据类型找到对应的dlc json
        with codecs.open(os.path.join(DLC_ZIP_PATH, 'dlc.json'), 'r', 'utf-8') as f:
            data = f.read()

        version_dict = json.loads(data)
    except Exception as e:
        print 'DLC JSON could not be read successfully'
        print e
        return

    try:
        version = version_dict['version']

        # 更新data_version和data_file Table
        _update_db(version, version_dict['version_data'])

        # 更新version Table
        _update_data_version(version, ios_app_version, android_app_version)

        # 更新Cache
        Version.create_cache()
        DataVersion.create_cache()
        DataFile.create_cache()

    except Exception as e:
        print 'DLC JSON data was invalid'
        print traceback.format_exc()


def _update_db(new_version, version_dict):
    dv = None

    for vd in version_dict:
        old_version = vd['old_version']

        try:
            # 获取最新版本和某旧版本的差分记录
            dv = DataVersion.objects.get(new_version=new_version, old_version=old_version)

            # 删除该差分记录所对应的具体zip文件记录
            DataFile.objects.filter(versions=dv).delete()
        except DataVersion.DoesNotExist:
            # 如果该差分记录不存在，就创建一个，为后面DataFile的更新准备外键
            dv = DataVersion()
            dv.new_version = new_version
            dv.old_version = old_version
            dv.save()

        resolution_files = { 'base_files': 0, '320_files': 320, '480_files': 480, '640_files': 640 }
        for key, resolution in resolution_files.iteritems():
            if key in vd:
                files = vd[key]

                for f in files:
                    df = DataFile()
                    df.versions = dv
                    df.packed_size = f['packed_size']
                    df.unpacked_size = f['unpacked_size']
                    df.checksum = f['checksum']
                    df.file = f['file_name']
                    df.resolution = resolution
                    df.save()

    # 删除所有旧版本之间的差分
    DataVersion.objects.exclude(new_version=new_version).delete()


def _update_data_version(new_version, ios_app_version, android_app_version):
    try:
        version = Version.objects.all()[0]
    except:
        version = Version()

    version.dlc_version = new_version
    if ios_app_version:
        version.ios_app_version = ios_app_version
    if android_app_version:
        version.android_app_version = android_app_version
    version.save()

    # 更新分服的version信息
    update_gamezone_version(new_version, version.ios_app_version, version.android_app_version)


def update_app_version(ios_app_version, android_app_version):
    try:
        version = Version.objects.all()[0]
    except:
        print 'version_version not initialized'
        return

    if version.dlc_version:
        if ios_app_version:
            version.ios_app_version = ios_app_version
        if android_app_version:
            version.android_app_version = android_app_version
        version.save()

        # 更新Cache
        Version.create_cache()
        # 更新分服的version信息
        update_gamezone_version(version.dlc_version, version.ios_app_version, version.android_app_version)
    else:
        print 'dlc version not initialized'


def update_gamezone_version(dlc_version, ios_app_version, android_app_version):
    all_zone = GameZone.get_cache_all()
    for zone in all_zone:
        url = "http://{}/version/update_version/".format(zone.server)

        data = urllib.urlencode({
            'dlc_version': dlc_version,
            'ios_app_version': ios_app_version,
            'android_app_version': android_app_version
        })

        try:
            response = urllib2.urlopen(url, data, 5)
            response_json = response.read()
            response.close()
        except urllib2.URLError, e:
            if hasattr(e, 'code'):  # HTTPError
                print 'The server couldn\'t fulfill the request. Error code: [%s]' % e.code
            elif hasattr(e, 'reason'): # URLError
                print 'We failed to reach a server. Reason: [%s]' % e.reason
            print "SERVER:{} UPDATE NG".format(url)
            continue

        # parse the response
        response_data = json.loads(response_json)
        if response_data['status_code'] == 0:
            print "SERVER:{} UPDATE OK".format(url)
        else:
            print "SERVER:{} UPDATE NG".format(url)


def _sort_files(files):
    """ 
    """
    resolution_paths = {}
    for r in RESOLUTIONS:
        resolution_paths[str(r)] = '/%d/' % (r)

    all_files = defaultdict(list)

    # Separate the files into different file lists based on resolution size. Resolution independent files use the the 'base' key
    for file in files:
        resolution_dependent = False
        for r, r_path in resolution_paths.iteritems():
            if r_path in file:
                all_files[r].append(file)
                resolution_dependent = True
                break

        if not resolution_dependent:
            all_files['base'].append(file)  

    # Sort the file list alphabetically in ascending order
    for resolution, filelist in all_files.iteritems():
        all_files[resolution] = sorted(filelist)

    return all_files


def update_dlc(resource_file_dir, version_prefix, from_version):

    prefix_size = len(version_prefix)

    # 删除旧的zip文件
    remove_old_dlc_files()

    # 获取所有tag
    tag_list = []
    command_str_get_tag = 'cd {} && git tag'.format(resource_file_dir)
    for tag in commands.getoutput(command_str_get_tag).split('\n'):
        result = re.match('^%s(\d{1,2}\.\d{2})$' % version_prefix, tag)
        if result:
            current_version = result.group(1)
            if from_version and from_version > float(current_version) and current_version != '0.01' and current_version != '2.14':
                continue;
            tag_list.append(tag)

    if len(tag_list) == 0:
        print 'not tag for this git repo: %s' % settings.DLC_REPO
        return

    # 获取最新版本
    tag_list.sort()
    latest_version = tag_list.pop()

    print "latest_version:%s" % latest_version

    # 生成 assets 临时文件
    assets_files = generate_asset_filelist(resource_file_dir, latest_version, prefix_size)

    zips_data = []

    for version in tag_list:
        command_str = 'cd {} && git diff --name-only --diff-filter=ACMRTUXB {}..{}'.format(resource_file_dir, version, latest_version)
        update_files = [file for file in commands.getoutput(command_str).split('\n') if not file.startswith('.')]

        # 追加需要同时出现而没有出现的文件
        update_files.extend(get_unpair_files(update_files))

        # 追加临时生成的assets文件
        update_files.extend(assets_files)

        sorted_files = _sort_files(update_files)

        version_data = {}
        for resolution, files in sorted_files.iteritems():
            zip_paths = generate_zips(resource_file_dir, files)

            if zip_paths:
                zips = get_zip_metadata(zip_paths)
                version_data['%s_files' % resolution] = copy_zips(latest_version, version, zips, resolution, DLC_ZIP_PATH)

        if version_data:
            version_data['old_version'] = version[prefix_size:]
            zips_data.append(version_data)

            print '%s > %s DLC generated.' % (version, latest_version)
        else:
            print 'nothing different!!!! you should remove this version[%s].' % latest_version

    # 删除 assets 临时文件
    remove_asset_filelist(resource_file_dir)

    # Write JSON to dlc folder
    json_dict = { 'version': latest_version[prefix_size:], 'version_data' : zips_data }
    data = json.dumps(json_dict, indent=4)

    with codecs.open(os.path.join(DLC_ZIP_PATH,'dlc.json'), 'w', 'utf-8') as f:
        f.write(data)



def remove_old_dlc_files():
    path = os.path.join(DLC_ZIP_PATH,'*.zip')
    files = glob.glob(path)
    for f in files:
        os.remove(f)


def get_old_dlc_files():
    try:
        # 根据类型找到对应的dlc json
        with codecs.open(os.path.join(DLC_ZIP_PATH, 'dlc.json'), 'r', 'utf-8') as f:
            data = f.read()

        version_dict = json.loads(data)
    except Exception as e:
        print 'DLC JSON could not be read successfully'
        print e
        return False

    latest_version = version_dict['version']
    path = os.path.join(DLC_ZIP_PATH,'*.zip')

    files = glob.glob(path)
    old_files = []
    for f in files:
        # 不包含最新版本信息的zip文件为旧文件
        if f.find("v{}-v".format(latest_version)) == -1:
            old_files.append(f)

    return old_files

def generate_asset_filelist(resource_file_dir, latest_version, prefix_size):
    """
    Generate json files of the base assets and resolution-specific assets
    """
    if not os.path.exists(resource_file_dir):
        print 'Folder not found : %s' % resource_file_dir
        return

    # Get list of all files in dlc folder
    files = []
    for root, dirnames, filenames in os.walk(resource_file_dir):
        for filename in filenames:
            folder = os.path.relpath(root, resource_file_dir)
            if folder == '.':
                folder = ''
            elif folder.startswith('.'):  # 隐藏文件不计算在内
                break
            # Hide hidden files and the assets.json files
            if not filename.startswith('.') and not filename.endswith('_assets.json') and filename != 'README.md':
                files.append(os.path.join(folder, filename))

    # Sort files into resolution dependent and resolution independent assets
    sorted_files = _sort_files(files)
    assets_files = []

    for k,v in sorted_files.iteritems():

        # Write JSON for each array of assets
        json_array = {
            'version': latest_version[prefix_size:],
            'assets': [{ 'file': file } for file in v]
        }
        json_data = json.dumps(json_array, indent=4)

        # 生成临时文件，打包之后删除
        json_path = os.path.join(resource_file_dir, '%s_assets.json' % k)
        with codecs.open(json_path, 'w', 'utf-8') as f:
            f.write(json_data)

        # Hardcode the mtime, atime and mode of the generated files because they cause the MD5 checksums to be different even when the content of these files are the same
        os.utime(json_path, (1000000000, 1000000000))
        os.chmod(json_path, 0664)

        assets_files.append('%s_assets.json' % k)

    return assets_files


def remove_asset_filelist(resource_file_dir):
    path = os.path.join(resource_file_dir, '*_assets.json')
    files = glob.glob(path)
    for f in files:
        os.remove(f)

def upload_s3(version_prefix):
    try:
        # 根据类型找到对应的dlc json
        with codecs.open(os.path.join(DLC_ZIP_PATH, 'dlc.json'), 'r', 'utf-8') as f:
            data = f.read()

        version_dict = json.loads(data)
    except Exception as e:
        print 'DLC JSON could not be read successfully'
        print e
        return False

    conn = S3Connection(settings.AWS_ACCESS_KEY_ID, settings.AWS_SECRET_ACCESS_KEY)
    bucket = conn.get_bucket('gumichina-dlc')

    try:
        version = version_dict['version']

        version_data = version_dict['version_data']

    except Exception as e:
        print 'DLC JSON data was invalid'
        print traceback.format_exc()
        return False

    pattern = "{}/{}{}".format(settings.DLC_PREFIX, version_prefix, version)
    print "delete old dlc file for latest version:{}".format(version)
    all_keys = bucket.list()
    for key in all_keys:
        if key.name.startswith(pattern):
            key.delete()
            print "deleted {}".format(key.name)

    for dv in version_data:
        for file_info in dv['base_files']:
            k = Key(bucket)
            k.key = "{}/{}".format(settings.DLC_PREFIX, file_info['file_name'])
            print 'uploading {} -> {}'.format(file_info['file_name'], k.key)
            k.set_contents_from_filename(os.path.join(DLC_ZIP_PATH, file_info['file_name']))
            k.set_acl('public-read')

    print 'delete old version dlc files'
    all_keys = bucket.list()
    for key in all_keys:
        if key.name.startswith(settings.DLC_PREFIX + '/') and not key.name.startswith(pattern):
            key.delete()
            print "deleted {}".format(key.name)

def is_IOS(device_str):
    if device_str.upper().startswith('IOS'):
        return True
    else:
        return False

def get_unpair_files(file_list):
    unpair_files = []
    pattern1 = '.pvr.ccz'
    pattern2 = '.plist'

    for file_name in file_list:
        # 同一个目录下的*.pvr.ccz和*.plist 必须要同时出现
        if file_name.endswith(pattern1):
            paired_file_name = file_name.replace(pattern1, pattern2)
            if not paired_file_name in file_list:
                unpair_files.append(paired_file_name)
        elif file_name.endswith(pattern2):
            paired_file_name = file_name.replace(pattern2, pattern1)
            if not paired_file_name in file_list:
                unpair_files.append(paired_file_name)

    return unpair_files
