#!/usr/bin/env python3

import sys
if sys.version_info[0] != 3:
    print("This script requires Python version 3 or greater")
    sys.exit(1)

import tkinter as tk
from tkinter import ttk as ttk
from tkinter import filedialog as fd
from tkinter import messagebox
from multiprocessing import Process, Pipe, Event
import threading
import os.path
from PIL import Image, ImageTk
sys.path.append(os.path.dirname(__file__))
from hocr import Hocr
from hocrdisplayer import HocrDisplayer


class HocrEditor(ttk.Frame):

    child_pipe = None
    stop_event = None
    process = None
    hocr_progress = 0
    hocr = None
    thread = None
    gui = {}
    display_hocr = None
    display_hocr_current_page = None
    test_canvas = None
    scale = 1.0
    image_size = 1024
    image = None
    image_id = None

    def __init__(self):
        master = self.master = tk.Tk()
        ttk.Frame.__init__(self, master)
        self.top = tk.Frame(self.master)
        self.gui['notebook'] = ttk.Notebook(self.master)
        master.title("HocrEditor")
        master.wm_geometry("300x300+10+10")

        self.hocr = Hocr()

        self.inputFile = None  # The input filename
        self.outputDir = None  # The output directory

        self.running = False  # Are we running
        self.halt = False  # Should we stop?

        menubar = tk.Menu(master)

        # create a pulldown menu, and add it to the menu bar
        filemenu = tk.Menu(menubar, tearoff=0)
        filemenu.add_command(label="Quit", command=self.quitter)
        menubar.add_cascade(label="File", menu=filemenu)

        self.gui['hocr_frame'] = ttk.Frame(self.gui['notebook'])
        inputLblFrame = tk.LabelFrame(self.gui['hocr_frame'], text="Input file", padx=2, pady=2)
        self.inputFile_str = tk.StringVar()
        inputFile_lbl = tk.Label(inputLblFrame, textvariable=self.inputFile_str, anchor=tk.W, justify=tk.LEFT)
        inputFile_lbl.pack()
        self.gui['inputFile_btn'] = tk.Button(inputLblFrame, text="Open file", command=self.ask_input_file)
        self.gui['inputFile_btn'].pack()
        inputLblFrame.pack()

        outputLblFrame = tk.LabelFrame(self.gui['hocr_frame'], text="Output directory", padx=2, pady=2)
        self.outputDir_str = tk.StringVar()

        outputDir_lbl = tk.Label(outputLblFrame, textvariable=self.outputDir_str, anchor=tk.W, justify=tk.LEFT)
        outputDir_lbl.pack()
        self.outputDir_btn = ttk.Button(outputLblFrame, text="Choose directory", command=self.ask_output_dir)
        self.outputDir_btn.pack()
        outputLblFrame.pack()

        self.run_btn = tk.Button(self.gui['hocr_frame'], text="Run Hocr", command=self.start_hocr, state=tk.DISABLED)
        self.run_btn.pack()
        self.exit_btn = tk.Button(self.gui['hocr_frame'], text="Exit", command=self.quitter)
        self.exit_btn.pack()
        self.gui['notebook'].add(self.gui['hocr_frame'], text="Process")

        self.correctDir = tk.StringVar()
        self.gui['correct_frame'] = ttk.Frame(self.gui['notebook'])
        reviewDir_lbl = tk.LabelFrame(self.gui['correct_frame'], text="Directory to process")
        correctLbl = tk.Label(reviewDir_lbl, textvariable=self.correctDir, anchor=tk.W, justify=tk.LEFT, wraplength=250)
        correctLbl.pack()
        outputDir_btn2 = ttk.Button(reviewDir_lbl, text="Choose directory", command=self.ask_correct_dir)
        outputDir_btn2.pack()
        reviewDir_lbl.pack()
        self.gui['hocr_list'] = tk.Listbox(self.gui['correct_frame'], selectmode=tk.SINGLE)
        self.gui['hocr_list'].pack()
        self.close_preview_btn = ttk.Button(self.gui['correct_frame'], text="Close Preview", command=self.preview_close,
                                            state=tk.DISABLED)
        self.close_preview_btn.pack()
        self.gui['notebook'].add(self.gui['correct_frame'], text="Review")

        self.gui['notebook'].pack(expand=1, fill="both")

        (self.parent_pipe, self.child_pipe) = Pipe()
        self.stop_event = Event()

        master.config(menu=menubar)

    def quitter(self):
        """Quit button stops processing if the program is running, otherwise it closes the whole application"""
        if self.running:
            self.stop_event.set()
        else:
            self.master.destroy()

    def run(self):
        self.master.mainloop()

    def ask_output_dir(self):
        """ask for a directory"""
        output_dir = fd.askdirectory(initialdir=os.path.dirname(__file__), title="Choose output directory")
        if output_dir is not None:
            if os.path.exists(output_dir) and os.access(output_dir, os.W_OK):
                self.outputDir_str.set(output_dir)
                self.check_hocr()
            else:
                tk.messagebox.showinfo(
                    title="Choose output directory",
                    icon="warning",
                    message="The directory {} does not exist or we can't write to it. Please choose another directory.".format(output_dir))
                self.ask_output_dir()

    def ask_input_file(self):
        """ask for a file"""
        input_file = fd.askopenfilename(initialdir=os.path.dirname(__file__),
                                title="Open input file.",
                                filetypes=[('PDF files', '.pdf'),
                                           ("All files", '*.*')])
        if input_file is not None:
            if os.path.exists(input_file) and os.access(input_file, os.R_OK):
                self.inputFile_str.set(input_file)
                self.check_hocr()
            else:
                tk.messagebox.showinfo(
                    title="Choose input file",
                    icon='warning',
                    message='The input file {} does not exist or is not readable.'.format(input_file)
                )
                self.ask_input_file()

    def preview_close(self):
        """Close the preview window."""
        if self.test_canvas is not None:
            if self.image_id is not None:
                self.test_canvas.delete(self.image_id)
            self.preview.destroy()
            self.test_canvas = None
            self.preview = None
            self.close_preview_btn.config({'state': tk.DISABLED})

    def __load_processed_files(self):
        """Update the list with the pages available."""
        if self.correctDir.get() is not None and self.display_hocr is not None:
            self.gui['hocr_list'].delete(0, tk.END)
            for k, v in self.display_hocr.get_file_listing().items():
                self.gui['hocr_list'].insert(tk.END, k)
            self.__poll_processed_list()

    def __poll_processed_list(self):
        """Has a new page been selected?"""
        now = self.gui['hocr_list'].curselection()
        if now != self.display_hocr_current_page:
            self.__list_has_changed(now)
            self.display_hocr_current_page = now
        self.after(250, self.__poll_processed_list)

    def __list_has_changed(self, pages):
        """Chose a new page, show it on the canvas."""
        if pages is not None and len(pages) > 0:
            (page, ) = pages
            if self.image_id is not None and self.test_canvas is not None:
                self.test_canvas.delete(self.image_id)
            elif self.test_canvas is None:
                self.preview = tk.Toplevel(self.master)
                self.test_canvas = tk.Canvas(master=self.preview, height=self.image_size + 10, width=self.image_size + 10)
            file_map = self.display_hocr.get_file_listing()
            image_selection = file_map.get(self.gui['hocr_list'].get(page))
            back_image = image_selection.get('image_file')
            self.scale = 1.0

            self.original_image = Image.open(os.path.join(self.display_hocr.directory, back_image))
            original_width = self.original_image.width
            original_height = self.original_image.height
            (new_height, new_width) = self.__resize_image(original_height, original_width, self.image_size)
            image_new = self.original_image.resize((new_width, new_height), Image.ANTIALIAS)  # best down-sizing filter
            self.image = ImageTk.PhotoImage(image_new)
            self.image_id = self.test_canvas.create_image(0, 0, image=self.image, anchor=tk.NW)
            self.test_canvas.bind("<MouseWheel>", self.zoom)
            self.test_canvas.pack()
            self.test_canvas.focus()
            self.close_preview_btn.config({'state':tk.NORMAL})

    def redraw_image(self, x=0, y=0):
        """Redraw the image, usually with adjusted scale."""
        if self.image_id and self.original_image:
            self.test_canvas.delete(self.image_id)
        iw, ih = self.original_image.size
        # crop rectangle
        cw, ch = iw / self.scale, ih / self.scale
        if cw > iw or ch > ih:
            cw = iw
            ch = ih
        # crop it
        _x = int(iw / 2 - cw / 2)
        _y = int(ih / 2 - ch / 2)
        tmp_image = self.original_image.crop((_x, _y, _x + int(cw), _y + int(ch)))
        size = int(cw * self.scale), int(ch * self.scale)
        self.image = ImageTk.PhotoImage(tmp_image.resize(size))
        self.image_id = self.test_canvas.create_image(x, y, image=self.image, anchor=tk.CENTER)

        # tell the canvas to scale up/down the vector objects as well
        self.test_canvas.scale(tk.ALL, x, y, self.scale, self.scale)

    def zoom(self, event):
        """Zoom bound to mouse wheel event."""
        if event.delta > 0:
            self.scale *= 2
        elif event.delta < 0:
            self.scale *= 0.5
        self.redraw_image(event.x, event.y)

    def __resize_image(self, height, width, max_size):
        """Figure out the resized image."""
        if width > max_size or height > max_size:
            if height >= width:
                new_height = max_size
                new_width = int((max_size / height) * width)
            else:
                new_width = max_size
                new_height = int((max_size / width) * height)
        return (new_height, new_width)

    def ask_correct_dir(self):
        """ask for a directory"""
        output_dir = fd.askdirectory(initialdir=os.path.dirname(__file__), title="Choose the directory of processed files.")
        if output_dir is not None:
            if os.path.exists(output_dir) and os.access(output_dir, os.R_OK):
                self.display_hocr = HocrDisplayer(output_dir)
                files = self.display_hocr.get_file_listing()
                if len(files) == 0:
                    tk.messagebox.showinfo(
                        title="Choose a directory of processed files.",
                        icon="warning",
                        message="The directory {} does not contain any HOCR'd pages. Please choose another directory.".format(
                            output_dir))
                    self.ask_correct_dir()
                else:
                    self.correctDir.set(output_dir)
                    self.__load_processed_files()

            else:
                tk.messagebox.showinfo(
                    title="Choose a directory of processed files.",
                    icon="warning",
                    message="The directory {} does not exist or we can't write to it. Please choose another directory.".format(output_dir))
                self.ask_correct_dir()

    def check_hocr(self):
        if self.inputFile_str.get() != "" and self.outputDir_str.get() != "":
            self.run_btn.config({'state': tk.NORMAL})
        else:
            self.run_btn.config({'state': tk.DISABLED})

    def start_hocr(self):
        if self.inputFile_str.get() is None:
            tk.messagebox.showinfo(title="No file", message="Choose a file to process.", icon='warning')
            return
        if self.outputDir_str.get() is None:
            tk.messagebox.showinfo(title="No directory", message="Choose an output directory.", icon='warning')
            return
        self.hocr_progress = 0
        window = tk.Toplevel(self)
        window.wm_title("HOCR Progress")
        window.attributes("-topmost", True)
        progress = ttk.Progressbar(window, variable=self.hocr_progress)
        progress.pack()
        btn = tk.Button(window, text="Cancel", command=self.quitter)
        btn.pack()
        window.focus()

        keyword_args = {'language': 'eng', 'output_directory': self.outputDir_str.get(), 'pipe': self.child_pipe,
                        'stop': self.stop_event}
        self.process = Process(target=self.hocr.run, args=[self.inputFile_str.get()], kwargs=keyword_args)
        ThreadedTask(self.process, self.running).start()

        self.after(1000, self.check_process())
        window.destroy()

    def start_and_wait_for_task(self):
        self.running = True
        self.process.start()

    def stop_hocr(self):
        self.stop_event.set()

    def check_process(self):
        if self.parent_pipe.poll(10):
            (current_page, total_pages) = self.parent_pipe.recv()
            self.hocr_progress = current_page / total_pages
        if not self.process.is_alive():
            self.running = False
        else:
            self.after(1000, self.check_process())


class ThreadedTask(threading.Thread):
    def __init__(self, process, running):
        threading.Thread.__init__(self)
        self.process = process
        self.running = running

    def run(self):
        self.process.start()
        self.running = False



if __name__ == '__main__':
    gui = HocrEditor()
    gui.run()

