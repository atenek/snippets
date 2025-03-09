import zipfile
import sys


if __name__ == '__main__':
    content_file = sys.argv[0]  # this file name
    zip_filename = f"./zip_001.zip"

    with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.write(content_file, arcname=content_file)

    with zipfile.ZipFile(zip_filename, 'r') as archive:
        archive.extractall('./extract_content.txt')
