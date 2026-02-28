import time
import serial
import matplotlib

# Force a GUI backend (works well once tk is installed)
matplotlib.use("TkAgg")

import matplotlib.pyplot as plt

PORT = "/dev/tty.usbmodem487F30FE67E91"
BAUD = 115200

ser = serial.Serial(PORT, BAUD, timeout=0.1)

# Create window FIRST
plt.ion()
fig, ax = plt.subplots()
ax.set_title("IMU XY")
ax.set_xlim(-100, 100)
ax.set_ylim(-60, 60)
point, = ax.plot([0], [0], marker="o")

fig.show()
fig.canvas.draw()
print("Plot window should be visible now. Listening on serial...")

while True:
    line = ser.readline().decode(errors="ignore").strip()
    if not line:
        # keep GUI responsive even if no serial data
        plt.pause(0.001)
        continue

    try:
        x_str, y_str = line.split(",")
        x = -float(x_str)
        y = -float(y_str)

        point.set_data([x], [y])
        fig.canvas.draw_idle()
        plt.pause(0.001)

    except Exception as e:
        # Print bad lines occasionally for debugging
        # (comment out once it works)
        print("bad line:", repr(line))
