#!/usr/bin/env python3

import sys

if sys.version_info[0] != 3:
    print("This script requires Python version 3 or greater")
    sys.exit(1)

import argparse, os.path
from PIL import Image
import pyocr,  pyocr.builders
import wand.image
import PyPDF2
import io
import codecs
import logging
import tempfile
from multiprocessing import Event,Pipe


class Hocr:
    image_tool = None
    languages = None
    language = None
    output_dir = None
    logger = None
    running = False

    def __init__(self, logger=None, language=None, output_directory=None):
        self.prereq()
        self.languages = self.image_tool.get_available_languages()
        if logger is not None:
            self.logger = logger
        else:
            self.internal_logger()
        if language is not None:
            self.set_language(language)
        if output_directory is not None:
            self.set_output_directory(output_directory)

    def prereq(self):
        """Ensure prerequisites for using this are available."""
        tools = pyocr.get_available_tools()
        if len(tools) == 0:
            raise HocrException("No OCR tool found")

        # The tools are returned in the recommended order of usage
        tool = tools[0]
        self.image_tool = tool

    def internal_logger(self):
        """Define a default logger if one is not provided to start."""
        self.logger = logging.getLogger('Hocr')
        self.logger.propogate = False
        # Logging Level
        logging_level = logging.INFO
        self.logger.setLevel(logging_level)
        if self.output_dir is not None:
            log_file = os.path.join(self.output_dir, 'Hocr.log')
        else:
            log_file = os.path.join(tempfile.gettempdir(), 'Hocr.log')
        fh = logging.FileHandler(log_file, 'w', 'utf-8')
        formatter = logging.Formatter('%(asctime)s %(name)-12s %(levelname)-8s %(message)s')
        fh.setFormatter(formatter)
        self.logger.addHandler(fh)

    def set_language(self, language):
        """Set the language for HOCRing"""
        if language.lower() not in [item.lower() for item in self.languages]:
            raise HocrException("Language {} not one of available ({})".format(language, self.languages.join(', ')))
        self.language = language

    def get_language(self):
        """Return the currently chosen language."""
        return self.language

    def get_languages(self):
        """Get the list of available languages."""
        return self.languages

    def set_output_directory(self, output_directory):
        """Set the directory to use for HOCR output."""
        process_dir = os.path.normpath(os.path.realpath(output_directory))
        if not os.path.exists(process_dir) or not os.access(process_dir, os.W_OK):
            raise HocrException("Directory {} does not exist or is not writable.".format(output_directory))
        self.output_dir = process_dir

    def run(self, the_file, pipe=None, stop=None, language=None, output_directory=None):
        if language is not None:
            self.set_language(language)
        if output_directory is not None:
            self.set_output_directory(output_directory)
        if self.language is None or self.output_dir is None:
            raise HocrException("You must choose a language and output directory before processing HOCR.")

        self.running = True

        sanitized_filename = "".join(c for c in os.path.basename(the_file) if c.isalnum()).rstrip()
        output_dir = os.path.join(self.output_dir, sanitized_filename)

        if not os.path.exists(output_dir):
            os.mkdir(output_dir, 0o775)

        pdf_file = PyPDF2.PdfFileReader(the_file)

        page_counter = 0
        total_pages = len(pdf_file.pages)
        for page in pdf_file.pages:
            if stop is not None and stop.is_set():
                break
            page_counter += 1
            if pipe is not None:
                pipe.send([page_counter, total_pages])
            page_number = pdf_file.getPageNumber(page)
            png = self.convert_page2png(pdf_file, page_number)
            temp_image = os.path.join(output_dir, 'Page{}.png'.format(page_number))
            png.save(filename=temp_image)
            with open(temp_image, 'rb') as fp:
                line_and_word_boxes = self.image_tool.image_to_string(
                    Image.open(fp), lang=language,
                    builder=pyocr.builders.LineBoxBuilder()
                )

            temp_hocr = os.path.join(output_dir, 'Page{}.hocr'.format(page_number))
            with codecs.open(temp_hocr, 'w', encoding='utf-8') as file_descriptor:
                pyocr.builders.LineBoxBuilder().write_file(file_descriptor, line_and_word_boxes)

        if pipe is not None:
            pipe.close()
        self.running = False
        return True

    def convert_page2png(self, pdffile, pagenum, resolution=300):
        dst_pdf = PyPDF2.PdfFileWriter()
        dst_pdf.addPage(pdffile.getPage(pagenum))

        pdf_bytes = io.BytesIO()
        dst_pdf.write(pdf_bytes)
        pdf_bytes.seek(0)

        img = wand.image.Image(file=pdf_bytes, resolution=resolution)
        img.convert("png")
        img.type = 'grayscale'

        return img


class HocrException(Exception):

    def __init__(self, *args, **kwargs):
        Exception.__init__(*args, **kwargs)

if __name__ == '__main__':

    hocr = Hocr()
    langs = hocr.get_langugages()

    parser = argparse.ArgumentParser(description='View edit HOCR from PDF/image file')
    parser.add_argument('-l', '--lang', dest='language', default=langs[0], choices=langs, help='Language to use for HOCR')
    parser.add_argument('-o', '--output-dir', dest='output_dir', default=None, required=True, help='Directory to place image and HOCR files')
    parser.add_argument('file', help='The PDF file to parse.')
    args = parser.parse_args()

    try:
        hocr.set_language(args.language)
        hocr.set_output_directory(args.output_dir)
    except HocrException as e:
        parser.error(e)

    if not os.path.exists(os.path.abspath(os.path.realpath(args.file))):
        parser.error('File {} not found'.format(args.file))

    hocr.process_file(args.file)
