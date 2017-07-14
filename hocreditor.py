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
sys.path.append(os.path.dirname(__file__))
from hocr import Hocr


class HocrEditor(ttk.Frame):

    child_pipe = None
    stop_event = None
    process = None
    hocr_progress = 0
    hocr = None
    thread = None

    def __init__(self):
        master = self.master = tk.Tk()
        ttk.Frame.__init__(self, master)
        master.title("HocrEditor")

        self.hocr = Hocr()

        self.inputFile = None  # The input filename
        self.outputDir = None  # The output directory

        self.running = False  # Are we running
        self.halt = False  # Should we stop?


        inputLblFrame = tk.LabelFrame(self.master, text="Input file", padx=2, pady=2)
        self.inputFile_str = tk.StringVar()
        self.inputFile_lbl = tk.Label(inputLblFrame, textvariable=self.inputFile_str)
        self.inputFile_lbl.pack()
        self.inputFile_btn = tk.Button(inputLblFrame, text="Open file", command=self.ask_input_file)
        self.inputFile_btn.pack()
        inputLblFrame.pack()

        outputLblFrame = tk.LabelFrame(self.master, text="Output directory", padx=2, pady=2)
        self.outputDir_str = tk.StringVar()
        self.outputDir_lbl = tk.Label(outputLblFrame, textvariable=self.outputDir_str)
        self.outputDir_lbl.pack()
        self.outputDir_btn = ttk.Button(outputLblFrame, text="Choose directory", command=self.ask_output_dir)
        self.outputDir_btn.pack()
        outputLblFrame.pack()

        self.run_btn = tk.Button(self.master, text="Run Hocr", command=self.start_hocr, state=tk.DISABLED)
        self.run_btn.pack()
        self.exit_btn = tk.Button(self.master, text="Exit", command=self.quitter)
        self.exit_btn.pack()

        (self.parent_pipe, self.child_pipe) = Pipe()
        self.stop_event = Event()

    def quitter(self):
        """Quit button stops processing if the program is running, otherwise it closes the whole application"""
        if self.running:
            self.stop_event.set()
        else:
            self.master.destroy()

    def run(self):
        self.mainloop()

    def ask_output_dir(self):
        """ask for a directory"""
        outputDir = fd.askdirectory(initialdir=os.path.dirname(__file__), title="Choose output directory")
        if outputDir is not None:
            if os.path.exists(outputDir) and os.access(outputDir, os.W_OK):
                self.outputDir_str.set(outputDir)
                self.check_hocr()
            else:
                tk.messagebox.showinfo(
                    title="Choose output directory",
                    icon="warning",
                    message="The directory {} does not exist or we can't write to it. Please choose another directory.".format(outputDir))
                self.ask_output_dir()

    def ask_input_file(self):
        """ask for a file"""
        inputFile = fd.askopenfilename(initialdir=os.path.dirname(__file__),
                                title="Open input file.",
                                filetypes=[('PDF files', '.pdf'),
                                           ("All files", '*.*')])
        if inputFile is not None:
            if os.path.exists(inputFile) and os.access(inputFile, os.R_OK):
                self.inputFile_str.set(inputFile)
                self.check_hocr()
            else:
                tk.messagebox.showinfo(
                    title="Choose input file",
                    icon='warning',
                    message='The input file {} does not exist or is not readable.'.format(inputFile)
                )
                self.ask_input_file()

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

