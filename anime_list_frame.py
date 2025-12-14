import bisect
import os
import queue
import threading
import time

import tkinter as tk
from tkinter import (ALL, BOTH, BOTTOM, END, FLAT, GROOVE, HORIZONTAL, LEFT,
                      NE, NW, RAISED, RIDGE, RIGHT, SE, SOLID, SUNKEN, SW, TOP,
                      VERTICAL, Button, Canvas, Checkbutton, E, Entry, Frame,
                      Label, N, OptionMenu, S, Scrollbar, Toplevel, W, X, Y,
                      font, ttk)

from PIL import Image, ImageTk

try:
    from .classes import AnimeList, DefaultDict
except ImportError:
    from classes import AnimeList, DefaultDict

try:
    from .general_utils import parse_args
except ImportError:
    from general_utils import parse_args

try:
    from .window_frames import ScrollableFrame
except ImportError:
    from window_frames import ScrollableFrame

try:
    from .general_utils import Timer
except ImportError:
    from general_utils import Timer


class AnimeListFrame(ScrollableFrame):
    def __init__(self, root, parent, rows_per_page=50, **kwargs):
        self.root = root
        self.parent = parent
        self.animePerRow = self.parent.animePerRow
        self.animePerPage = self.parent.animePerPage
        self.log = self.parent.log

        self.list = []
        self.next_list = None
        self.blank_image = None
        self.list_id = 0

        # Virtual scrolling optimization
        self.virtual_scrolling = True
        self.visible_start = 0
        self.visible_end = rows_per_page
        self.item_height = 350  # Approximate height per anime item (image + text)
        self.visible_widgets = {}  # Cache for visible widgets
        self.widget_pool = []  # Pool of reusable widgets
        self.max_pool_size = 100

        super().__init__(self.root, **kwargs)

        # Bind scroll events for virtual scrolling
        if self.virtual_scrolling:
            self.canvas.bind("<MouseWheel>", self._on_scroll)
            self.canvas.bind("<Button-4>", self._on_scroll)  # Linux scroll up
            self.canvas.bind("<Button-5>", self._on_scroll)  # Linux scroll down

    def _get_list_length(self):
        """Safely get the length of the anime list"""
        try:
            if hasattr(self.list, 'list'):
                return len(self.list.list)
            elif hasattr(self.list, '__len__'):
                return len(self.list)
            else:
                # Convert to list to get length
                return len(list(self.list))
        except:
            return 0

    def _get_list_item(self, index):
        """Safely get an item from the anime list by index"""
        try:
            if hasattr(self.list, 'list'):
                # AnimeList has a .list attribute that's a deque
                list_items = list(self.list.list)
                return list_items[index] if index < len(list_items) else None
            elif hasattr(self.list, '__getitem__'):
                return self.list[index]
            else:
                # Convert to list and access
                list_items = list(self.list)
                return list_items[index] if index < len(list_items) else None
        except:
            return None

    def _on_scroll(self, event):
        """Handle scroll events for virtual scrolling"""
        if not self.virtual_scrolling or not self.list:
            return

        # Determine scroll direction and amount
        if event.delta > 0 or event.num == 4:  # Scroll up
            scroll_amount = -3  # Scroll up by 3 items
        else:  # Scroll down
            scroll_amount = 3   # Scroll down by 3 items

        # Calculate new visible range
        new_start = max(0, self.visible_start + scroll_amount)
        # Get list length safely
        list_length = self._get_list_length()

        max_start = max(0, list_length - self.animePerPage)
        new_start = min(new_start, max_start)

        if new_start != self.visible_start:
            self.visible_start = new_start
            self.visible_end = min(new_start + self.animePerPage, list_length)
            self._update_visible_items()

    def _update_visible_items(self):
        """Update which items are visible in the virtual scroll area"""
        if not self.virtual_scrolling:
            return

        # Clear current visible widgets
        for widget_info in self.visible_widgets.values():
            widget_info['canvas'].grid_remove()
            widget_info['label'].grid_remove()
            # Return to pool
            self._return_widget_to_pool(widget_info)

        self.visible_widgets.clear()

        # Create widgets for visible items
        que = queue.Queue()
        self.parent.getElemImages(que)

        list_length = self._get_list_length()

        for i in range(self.visible_start, min(self.visible_end, list_length)):
            anime = self._get_list_item(i)
            if anime:
                widget_info = self._get_widget_from_pool()
                self._create_virtual_elem(i, anime, widget_info, que)
                self.visible_widgets[i] = widget_info

        # Update canvas scroll region
        total_height = (list_length // self.animePerRow + 1) * self.item_height
        self.canvas.configure(scrollregion=(0, 0, self.canvas.winfo_width(), total_height))

    def _get_widget_from_pool(self):
        """Get a widget from the pool or create a new one"""
        if self.widget_pool:
            return self.widget_pool.pop()
        else:
            # Create new widget
            canvas = Canvas(
                self,
                width=225,
                height=310,
                highlightthickness=0,
                bg=self.parent.colors["Gray3"],
            )
            label = Label(
                self,
                text="",
                bg=self.parent.colors["Gray2"],
                fg=self.parent.colors["White"],
                font=("Source Code Pro Medium", 13),
                bd=0,
                wraplength=220,
            )
            return {'canvas': canvas, 'label': label}

    def _return_widget_to_pool(self, widget_info):
        """Return widget to pool for reuse"""
        if len(self.widget_pool) < self.max_pool_size:
            # Clear widget state
            widget_info['canvas'].delete("all")
            widget_info['label'].config(text="")
            self.widget_pool.append(widget_info)

    def _create_virtual_elem(self, index, anime, widget_info, queue):
        """Create a virtual scrolling element"""
        canvas = widget_info['canvas']
        label = widget_info['label']

        # Calculate grid position
        row = (index // self.animePerRow) * 2  # *2 because of image + label rows
        col = index % self.animePerRow

        # Position widgets
        canvas.grid(column=col, row=row, padx=5, pady=5)
        label.grid(column=col, row=row + 1, padx=5, pady=5)

        # Configure canvas
        canvas.delete("all")  # Clear previous content
        if self.blank_image is None:
            self.blank_image = self.parent.getImage(None, (225, 310))
        canvas.create_image(0, 0, image=self.blank_image, anchor="nw")
        canvas.image = self.blank_image  # Keep reference

        # Bind events
        canvas.bind("<Button-1>", lambda e, id=anime.id: self.parent.drawOptionsWindow(id))
        canvas.bind("<Button-3>", lambda e, id=anime.id: self.parent.view(id))

        # Configure label
        title = anime.title or "Unknown Title"
        if len(title) > 35:
            title = title[:35] + "..."

        if anime.like == 1:
            title += " ❤"

        label.config(
            text=title,
            fg=self.parent.colors[self.parent.tagcolors.get(anime.tag, "White")]
        )
        label.name = str(anime.id)

        # Load image asynchronously
        filename = os.path.join(self.parent.cache, str(anime.id) + ".jpg")
        pics = self.parent.getAnimePictures(anime.id)
        if pics:
            url = pics[0]["url"]
            queue.put((filename, url, canvas))

    def _draw_row(self, row, list_id, ids):
        """Draw a row of anime elements and update the cache."""
        buf = []
        while row:
            args = row.pop(0)
            buf.append(args)
        self.parent.getAnimePicturesCache([a[1].id for a in buf])  # Batch SQL requests for images
        for args in buf:
            tmp = self.create_elem(*args)
            if tmp:
                ids.add(tmp)
        if self.list_id != list_id:
            return False  # Interrupted
        return True

    def _get_process_func(self, start, stop, list_id, row, ids, que):
        """Return a function to process each anime item during list generation."""
        def wrapped(i, data):
            if i < 0 or i + start >= stop:
                return False  # Out of bounds
            if self.list_id != list_id or self.parent.closing:
                return False  # Interrupted
            if data is None:
                if i == 0 and start == 0:
                    # Display "No results" if no data at the beginning
                    Label(
                        self,
                        text="No results",
                        font=("Source Code Pro Medium", 20),
                        bg=self.parent.colors["Gray2"],
                        fg=self.parent.colors["Gray4"],
                    ).grid(columnspan=self.animePerRow, row=0, pady=50)
                return False
            row.append((i + start, data, que))
            if (i + start) % self.animePerRow == 2:
                return self._draw_row(row, list_id, ids)
            return True
        return wrapped

    def _get_completion_callback(self, start, list_id, row, last_ind, que, ids, anime_count):
        """Return a callback function to handle completion of list mapping."""
        def wrapped(i):
            if list_id != self.list_id:
                return
            last_ind.put(i)
            if i < last_ind.get(block=False):
                if self.next_list is not None:
                    self.list, self.next_list = self.next_list()
                    if self.list is not None:
                        # Recursively process the next list segment
                        process_func = self._get_process_func(start, anime_count + start, list_id, row, ids, que)
                        completion_callback = self._get_completion_callback(start, list_id, row, last_ind, que, ids, anime_count)
                        self.list.map(process_func, lambda func: self.after(100, func), completion_callback)
                    return
            else:
                try:
                    if not self.list.empty():
                        self.load_more_button(start + i - len(row) + 1)
                    else:
                        self._draw_row(row, list_id, ids)
                    self.list_timer.stats()
                    self.parent.stopSearch = True
                finally:
                    que.put("STOP")
        return wrapped

    def find(self, limit=1, **kwargs):
        c = 0
        for anime in self.list:
            if all(anime[k] == v for k, v in kwargs.items()):
                yield anime
                c += 1
                if c >= limit:
                    return

    def remove(self, **kwargs):
        for anime in self.list:
            if all(anime[k] == v for k, v in kwargs.items()):
                self.list.remove(anime)  # type: ignore  # AnimeList has remove method
                break
        self.createList()

    def set(self, data):
        if not isinstance(data, AnimeList):
            raise TypeError("AnimeList instance required, not: {}".format(type(data)))
        else:
            self.list = data
        self.next_list = None
        self.createList()

    def from_filter(self, criteria, listrange=(0, 50)):
        self.list, self.next_list = self.parent._database_manager.get_anime_list(criteria, listrange)

        self.update_scrollzone()  # Necessary?
        self.createList()

    def createList(self, start=0, waiting=None, list_id=None):
        if list_id is None:
            list_id = self.list_id + 1
            self.list_id = list_id
            # self.log("ANIME_LIST", f'New list id: {list_id}')

        self.generate_list(start, list_id)

    def generate_list(self, start, list_id):
        """Generate and display the anime list starting from the given index with the specified list ID."""
        que = queue.Queue()
        self.parent.getElemImages(que)

        if start == 0:
            # Clear the canvas and destroy existing widgets
            try:
                self.canvas.yview_moveto(0)
                while len(self.winfo_children()) > 0:
                    for child in self.winfo_children():
                        child.destroy()

            except Exception as e:
                self.log("MAIN_STATE", "[ERROR] - On AnimeListFrame.create_list():", e)
                return

            if self.list_id != list_id:
                return  # Interrupted

        # Calculate the number of anime to display per page, ensuring it fits the grid
        anime_count = self.animePerPage // self.animePerRow * self.animePerRow - 1

        ids = set()  # Set to track processed anime IDs
        row = []  # Buffer for current row of anime
        self.list_timer = Timer(
            "Anime List Timer", lambda *args: self.log("ANIME_LIST", *args)
        )

        last_ind = queue.Queue()
        last_ind.put(anime_count)

        # Get the processing and completion functions
        process_func = self._get_process_func(start, anime_count + start, list_id, row, ids, que)
        completion_callback = self._get_completion_callback(start, list_id, row, last_ind, que, ids, anime_count)

        # Map the list with the processing function
        self.list.map(process_func, lambda func: self.after(100, func), completion_callback)

    def create_elem(self, index, anime, queue):
        self.list_timer.start()
        if self.blank_image is None:
            self.blank_image = self.parent.getImage(None, (225, 310))

        title = anime.title
        if title is None:
            self.list_timer.stop()
            return

        if len(title) > 35:
            title = title[:35] + "..."

        img_can = Canvas(
            self,
            width=225,
            height=310,
            highlightthickness=0,
            bg=self.parent.colors["Gray3"],
        )
        img_can.bind(
            "<Button-1>", lambda e, id=anime.id: self.parent.drawOptionsWindow(id)
        )
        img_can.bind("<Button-3>", lambda e, id=anime.id: self.parent.view(id))
        img_can.grid(column=index % self.animePerRow, row=index // self.animePerRow * 2)

        img_can.create_image(0, 0, image=self.blank_image, anchor="nw")
        img_can.image = self.blank_image  # type: ignore  # Keep reference to prevent garbage collection

        if anime.like == 1:
            title += " ❤"

        lbl = Label(
            self,
            text=title,
            bg=self.parent.colors["Gray2"],
            fg=self.parent.colors[self.parent.tagcolors[anime.tag]],
            font=("Source Code Pro Medium", 13),
            bd=0,
            wraplength=220,
        )

        lbl.grid(
            column=index % self.animePerRow, row=(index // self.animePerRow * 2) + 1
        )
        lbl.name = str(anime.id)  # type: ignore  # Custom attribute for identification

        self.update_scrollzone([img_can, lbl])

        filename = os.path.join(self.parent.cache, str(anime.id) + ".jpg")
        # url = anime.picture
        pics = self.parent.getAnimePictures(anime.id)
        if pics:  # TODO - Choose best pic
            url = pics[0]["url"]
            queue.put((filename, url, img_can))
            out = None
        else:
            out = anime.id
        self.list_timer.stop()
        return out

    def load_more_button(self, index):
        img_can = Canvas(
            self,
            width=225,
            height=310,
            highlightthickness=0,
            bg=self.parent.colors["Gray2"],
        )
        img_can.grid(
            column=(index - 1) % self.animePerRow,
            row=(index - 1) // self.animePerRow * 2,
        )

        size = 75
        x, y = int(225 / 2 - size / 2), int(310 / 2 - size / 2)
        pos = (
            x,
            y + size / 2,
            x + size,
            y + size / 2,
            x + size / 2,
            y + size / 2,
            x + size / 2,
            y,
            x + size / 2,
            y + size,
        )
        img_can.create_line(  # type: ignore
            *pos, capstyle="round", fill=self.parent.colors["Gray4"], width=15
        )

        lbl = Label(
            self,
            text="Load more...",
            bg=self.parent.colors["Gray2"],
            fg=self.parent.colors["Gray4"],
            font=("Source Code Pro Medium", 13),
            bd=0,
            wraplength=220,
        )
        lbl.grid(
            column=(index - 1) % self.animePerRow,
            row=((index - 1) // self.animePerRow * 2) + 1,
        )
        lbl.name = str(-1)  # type: ignore  # Custom attribute for identification

        toDestroy = (img_can, lbl)
        img_can.bind("<Button-1>", lambda e, s=index: self.load_more(index, toDestroy))

    def load_more(self, start, toDestroy):
        [e.destroy() for e in toDestroy]
        self.createList(start=start - 1)