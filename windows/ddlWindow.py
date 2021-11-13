from tkinter import *

import utils


class ddlWindow:
    def ddlWindow(self, id):
        # Window init - Fancy corners - Main frame - Events
        if True:
            size = (self.publisherDDLWindowMinWidth,
                    self.publisherDDLWindowMinHeight)
            if self.publisherChooser is None or not self.publisherChooser.winfo_exists():
                self.publisherChooser = utils.RoundTopLevel(
                    self.choice, title="Loading...", minsize=size, bg=self.colors['Gray3'], fg=self.colors['Gray2'])
            else:
                self.publisherChooser.clear()
                self.publisherChooser.titleLbl.configure(
                    text="Loading...", bg=self.colors['Gray3'], fg=self.colors['Gray2'], font=("Source Code Pro Medium", 18))

            table = utils.ScrollableFrame(
                self.publisherChooser, bg=self.colors['Gray3'])
            table.grid_columnconfigure(0, weight=1)
            table.grid()

            self.publisherChooser.update()
            if not self.publisherChooser.winfo_exists():
                return

        # Torrent publisher list
        if True:
            self.log("FILE_SEARCH", "Looking files for id:", id)
            titles = self.searchTorrents(id)
            # titles = self.getTorrentFiles(title)
            rowHeight = 25
            empty = True

            for i, data in enumerate(titles):
                if empty:
                    empty = False
                publisher, data = data
                marked = ('dual', 'dub')
                for title in [d['filename'] for d in data]:
                    fg = self.getTorrentColor(title)
                    if fg != self.colors['White']:
                        break
                bg = (self.colors['Gray2'], self.colors['Gray3'])[i % 2]
                if publisher is None:
                    publisher = 'None'
                if not self.publisherChooser.winfo_exists():
                    return
                Button(table, text=publisher, bd=0, height=1, relief='solid', font=("Source Code Pro Medium", 13),
                       activebackground=self.colors['Gray3'], activeforeground=fg, bg=bg, fg=fg,
                       command=lambda a=data, b=id: self.ddlFileListWindow(
                           a, b)
                       ).grid(row=i, column=0, sticky="nsew")

            try:
                if empty:
                    self.publisherChooser.titleLbl['text'] = "No files\nfound!"
                else:
                    self.publisherChooser.titleLbl['text'] = "Publisher:"
            except _tkinter.TclError:
                pass

            table.update()
            # self.publisherChooser.update()