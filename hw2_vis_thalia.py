import time
from collections import deque
import serial
import matplotlib.pyplot as plt

# config 
port = "/dev/cu.usbmodem487F303F49801" # note to user: replace this with your port if it doesn't work
baud_rate = 115200
# maximum number of points that can be drawn 
max_points = 35000
velocity = 0.1
refresh_rate = 1/10

def main():
    feather = serial.Serial(port, baud_rate, timeout=0.1)
    time.sleep(1.0)         
    feather.reset_input_buffer()
    x_coordinates = deque(maxlen=max_points)
    y_coordinates = deque(maxlen=max_points)
    # current position in the canvas 
    converted_x = 0.0
    converted_y = 0.0
    next_plot = time.time()
    is_recording = False
    # plot setup 
    plt.ion()
    fig, ax = plt.subplots()
    plt.show(block=False)
    (line,) = ax.plot([], [], linewidth=2)
    ax.set_aspect("equal", adjustable="datalim")
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    ax.set_title("Real-time Long Exposure Drawing via IMU Sensing")
    current_color = "black"  
    try:
        while True:
            feather_data = feather.readline()
            if feather_data:
                decoded_data = feather_data.decode("utf-8", errors="ignore").strip()
                print("RAW LINE:", decoded_data)
                if not decoded_data:
                    continue
                # detect if the user is recording the first time, or re-recording 
                # start with an empty background 
                if decoded_data == "Start":
                    x_coordinates.clear()
                    y_coordinates.clear()
                    converted_x = 0.0 
                    converted_y = 0.0
                    is_recording = True
                    last_time = time.time()
                    continue
                if decoded_data == "Stop":
                    is_recording = False
                if not is_recording:
                    continue
                data_parts = []
                # proceed to parse IMU sensor data and selected color 
                for part in decoded_data.split(","):
                    data_parts.append(part.strip())
                if len(data_parts) >= 2:
                    # x and y coordinates 
                    x = -float(data_parts[0])
                    y = -float(data_parts[1])
                    if len(data_parts) == 3:
                        selected_color = data_parts[2]
                        current_color = selected_color
                        line.set_color(current_color)  
                    alpha = 0.3
                    converted_x = alpha * x + (1 - alpha) * converted_x
                    converted_y = alpha * y + (1 - alpha) * converted_y
                    x_coordinates.append(converted_x)
                    y_coordinates.append(converted_y)
            if time.time() >= next_plot:
                next_plot += refresh_rate
                if len(x_coordinates) > 2:
                    line.set_data(x_coordinates, y_coordinates)
                    ax.relim()
                    ax.autoscale_view()
                fig.canvas.draw()
                fig.canvas.flush_events()
    # save image via Ctrl + C
    except KeyboardInterrupt:
        filename = f"drawing_{int(time.time())}.png"
        ax.axis("off")
        fig.savefig(filename, dpi=300, bbox_inches="tight", pad_inches=0)
        print("Drawing saved!", filename)
    finally:
        feather.close()
        plt.ioff()
        plt.show()

if __name__ == "__main__":
    main()