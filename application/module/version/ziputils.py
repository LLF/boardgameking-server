# -*- coding: utf-8 -*-

import os
import stat
import filecmp
import hashlib
import zipfile
import shutil

MAX_TOTAL_UNPACKED_SIZE = 10000000

def calculate_md5(file, block_size=2**20):
    """
    Calculate md5 for a file
    """

    with open(file, 'rb') as f:
        md5 = hashlib.md5()
        while True:
            data = f.read(block_size)
            if not data:
                break
            md5.update(data)

    return md5.hexdigest()

def get_zip_metadata(zip_paths):
    """
    Get the zip metadata - packed size, unpacked size and MD5 checksum
    """

    zips = []
    # Iterate through all the zips and get the zip info - packed size, unpacked size and md5 checksum
    for zip_path in zip_paths:
        try:
            with zipfile.ZipFile(zip_path, mode='r') as zf:
                unpacked_size = 0

                for info in zf.infolist():
                    unpacked_size += info.file_size

            packed_size = os.stat(zip_path)[stat.ST_SIZE]
            checksum = calculate_md5(zip_path)

            zips.append( { 'file': zip_path, 'packed_size': packed_size, 'unpacked_size': unpacked_size, 'checksum' : checksum })
        except zipfile.BadZipfile:
            print '%s is not a valid ZIP file.' % zip_path
            pass

    return zips

def generate_zips(version_folder, files):
    """
    Generate the zip based on the list of paths

    Return the paths of these zips
    """
    temp_folder = '/tmp'

    files.sort()

    zip_paths = []
    # Create the zips and return the paths to those zips
    count = 1

    total_file_size = 0
    create_new_zip = True

    if not files:
        return zip_paths

    for file in files:

        # Create a new file if the total uncompressed file size of all files added to date exceed MAX_TOTAL_UNCOMPRESSED_FILESIZE
        if total_file_size > MAX_TOTAL_UNPACKED_SIZE:
            zf.close()
            zip_paths.append(zip_path)
            count += 1
            create_new_zip = True

        if create_new_zip:
            zip_path = os.path.join(temp_folder, '%02d.zip' % count)
            zf = zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED)
            total_file_size = 0
            create_new_zip = False

        # Add file to zip
        try:
            path = os.path.join(version_folder, file)
            # 统一dlc所有文件的mtime,atime和mode，以免产生的zip文件 md5值不一样
            os.utime(path, (1000000000, 1000000000))
            os.chmod(path, 0664)
            size = os.stat(path)[stat.ST_SIZE]

            zf.write(path, file)
            compress_size = zf.getinfo(file).compress_size
            total_file_size += compress_size
        except Exception, e:
            print e
            print '%s could not be written to zip.' % file
            pass

    zf.close()
    if not zip_path in zip_paths:
        zip_paths.append(zip_path)

    return zip_paths

def generate_file_hash(new_version, old_version, file_path):
    md5 = hashlib.md5()
    md5.update(old_version)
    md5.update(new_version)
    md5.update(file_path)
    return md5.hexdigest()

def copy_zips(new_version, old_version, zips, resolution, dlc_zip_path):
    """
    Copy zips and update the metadata
    """
    zips_data = [dict(z) for z in zips] 

    for z in zips_data:
        old_filename = os.path.splitext(os.path.basename(z['file']))[0]

        z['file_name'] = '%s-%s_%s_%s_%s.zip' % (new_version, old_version, resolution, old_filename, generate_file_hash(new_version, old_version, z['checksum']))

        # Copy file from temp folder to DLC_ZIP_PATH
        shutil.move(z['file'], os.path.join(dlc_zip_path, z['file_name']))

    return zips_data
