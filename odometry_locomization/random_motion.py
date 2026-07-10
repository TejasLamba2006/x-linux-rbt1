import tkinter as tk
import time

root = tk.Tk()
root.attributes("-fullscreen", True)

canvas = tk.Canvas(root, bg="black")
canvas.pack(fill="both", expand=True)

x = 0

frames = 0
last = time.time()


def update():
    global x, frames, last

    canvas.delete("all")
    canvas.create_rectangle(x, 100, x+100, 200, fill="white")

    x = (x + 20) % 2000

    frames += 1

    now = time.time()

    if now - last >= 1:
        print("FPS:", frames)
        frames = 0
        last = now

    root.after(1, update)


update()
root.mainloop()
