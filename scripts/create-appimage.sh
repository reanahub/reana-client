#!/bin/sh
#
# This file is part of REANA.
# Copyright (C) 2022 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

if [ $# -eq 0 ]; then
    echo "Usage: $0 <version>"
    echo
    echo "Example: $0 0.8.0"
    echo
    echo "This script creates an AppImage executable for the desired reana-client version."
    echo "Please supply desired reana-client version as an argument. The version must be "
    echo "released on PyPI."
    exit 1
fi

version=$1

if ! [ -x "$(command -v convert)" ]; then
    echo "Error: No program 'convert'. Please install 'ImageMagick'."
    exit 1
fi

download_python_appimage () {
    wget https://github.com/niess/python-appimage/releases/download/python3.8/python3.8.12-cp38-cp38-manylinux1_x86_64.AppImage
    chmod +x python3.8.12-cp38-cp38-manylinux1_x86_64.AppImage
    wget https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage
    chmod a+x appimagetool-x86_64.AppImage
}

extract_python_appimage () {
    ./python3.8.12-cp38-cp38-manylinux1_x86_64.AppImage --appimage-extract
}

install_reana_client_into_python_appimage () {
    ./squashfs-root/AppRun -m pip install --no-cache-dir "reana-client==$version"
}

modify_python_appimage_to_run_reana_client_by_default () {
    sed -i -e 's|/opt/python3.8/bin/python3.8|/usr/bin/reana-client|g' ./squashfs-root/AppRun
}

test_modified_python_appimage () {
    ./squashfs-root/AppRun --help
}

edit_desktop_file () {
    mv squashfs-root/usr/share/applications/python3.8.12.desktop squashfs-root/usr/share/applications/reana-client.desktop
    sed -i -e 's|^Name=.*|Name=reana-client|g' squashfs-root/usr/share/applications/*.desktop
    sed -i -e 's|^Exec=.*|Exec=reana-client|g' squashfs-root/usr/share/applications/*.desktop
    sed -i -e 's|^Icon=.*|Icon=reana-client|g' squashfs-root/usr/share/applications/*.desktop
    sed -i -e 's|^Comment=.*|Comment=reana-client|g' squashfs-root/usr/share/applications/*.desktop
    sed -i -e 's|^Categories=.*|Categories=Science;|g' squashfs-root/usr/share/applications/*.desktop
    rm squashfs-root/*.desktop
    cp squashfs-root/usr/share/applications/*.desktop squashfs-root/
}

add_icon () {
    wget https://github.com/reanahub/reana/raw/master/docs/logo-reana.png
    mkdir -p squashfs-root/usr/share/icons/hicolor/128x128/apps/
    convert -size 128x128 logo-reana.png squashfs-root/usr/share/icons/hicolor/128x128/apps/reana-client.png
    cp squashfs-root/usr/share/icons/hicolor/128x128/apps/reana-client.png squashfs-root/
}

convert_back_to_reana_client_appimage () {
    VERSION=$version ARCH=x86_64 ./appimagetool-x86_64.AppImage squashfs-root/
}

test_created_reana_client_appimage () {
    "./reana-client-$version-x86_64.AppImage" --help
}

clean_after_ourselves () {
    rm -rf logo-reana.png squashfs-root
    rm -rf appimagetool-x86_64.AppImage python3.8.12-cp38-cp38-manylinux1_x86_64.AppImage
}

download_python_appimage
extract_python_appimage
install_reana_client_into_python_appimage
modify_python_appimage_to_run_reana_client_by_default
test_modified_python_appimage
edit_desktop_file
add_icon
convert_back_to_reana_client_appimage
test_created_reana_client_appimage
clean_after_ourselves
