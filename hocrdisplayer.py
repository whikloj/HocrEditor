#!/usr/bin/env python3
import os
import os.path
import re

class HocrDisplayer:

    file_map = {}

    def __init__(self, directory):
        if not os.path.exists(directory) or not os.path.isdir(directory):
            raise HocrDisplayerException("{} does not exist or is not a directory.".format(directory))
        self.directory = directory
        self.file_regex = re.compile(r'^Page(\d+)\.hocr$')
        self.__load_directory()

    def __load_directory(self):
        self.file_map.clear()
        for file in os.listdir(self.directory):
            if self.file_regex.match(file):
                matches = self.file_regex.match(file)
                page_num = int(matches[1])
                display_pagenum = page_num + 1
                self.file_map['Page {}'.format(str(display_pagenum))] = {
                    'image_file': 'Page{}.png'.format(str(page_num)),
                    'ocr_file': 'Page{}.hocr'.format(str(page_num))
                }
    def get_file_listing(self):
        return self.file_map


class HocrDisplayerException(Exception):
    def __init__(self, *args, **kwargs):
        Exception.__init__(*args, **kwargs)