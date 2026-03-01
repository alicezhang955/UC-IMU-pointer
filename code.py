import time
import board
import displayio
import digitalio
import terminalio
from adafruit_display_text import label
import adafruit_icm20x
import mahony

# [backend] config 
i2c = board.I2C()
time.sleep(0.2)
sensor = adafruit_icm20x.ICM20948(i2c)
# magnetometer calibration
mag_min = [-0.5764, 0.0097, -0.5362]
mag_max = [0.4725, 0.9919, 0.4743]
# Mahony AHRS filter & update rate of the AHRS filter 
ahrs_hz = 100
ahrs = mahony.Mahony(ahrs_hz, 5, 100)
time_between_ahrs_updates = int(1e9 / ahrs_hz)
# data printing (streaming) rate; every 0.1 second
time_between_prints = 0.1
# smoothing
alpha = 0.5
last_ahrs_update_time = time.monotonic_ns()
last_print_time = time.monotonic()
baseline_pitch = 0.0
baseline_roll = 0.0
current_x = 0.0
current_y = 0.0

# [backend] helpers
def calibrate_baseline(sensor, calibration_length, calibration_countdown_label):
    calibration_start_time = time.monotonic()
    samples = 0
    sum_roll = 0.0
    sum_pitch = 0.0
    time.sleep(0.1)
    last_shown_time = None
    while True:
        current_time = time.monotonic()
        time_passed = current_time - calibration_start_time
        if time_passed >= calibration_length:
            break
        remaining_time = int(calibration_length - time_passed)
        if remaining_time != last_shown_time:
            calibration_countdown_label.text = f"Calibration stops in {remaining_time}s"
            last_shown_time = remaining_time
        apply_mahony_filter(sensor) 
        sum_roll += ahrs.roll
        sum_pitch += ahrs.pitch
        samples += 1
        time.sleep(1.0 / ahrs_hz)
    baseline_roll = sum_roll / samples
    baseline_pitch = sum_pitch / samples
    return baseline_roll, baseline_pitch

# normalize magnetometer values
def map_range(x, in_min, in_max, out_min, out_max):
    mapped = (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min
    if out_min <= out_max:
        if mapped < out_min:
            return out_min
        if mapped > out_max:
            return out_max
        return mapped
    else:
        if mapped < out_max:
            return out_max
        if mapped > out_min:
            return out_min
        return mapped

# read data from sensors and feed into Mahony filter 
def apply_mahony_filter(sensor):
    mag_x, mag_y, mag_z = sensor.magnetic
    gyro_x, gyro_y, gyro_z = sensor.gyro
    acc_x, acc_y, acc_z = sensor.acceleration
    # normalize values 
    mag_x = map_range(mag_x, mag_min[0], mag_max[0], -1.0, 1.0)
    mag_y = map_range(mag_y, mag_min[1], mag_max[1], -1.0, 1.0)
    mag_z = map_range(mag_z, mag_min[2], mag_max[2], -1.0, 1.0)
    # mounting adjustments 
    gyro_z = -gyro_z
    mag_y = -mag_y
    # apply Mahony filter
    ahrs.update(gyro_x, gyro_y, gyro_z, acc_x, acc_y, acc_z, mag_x, mag_y, mag_z)

# compute new x and y using updated roll and pitch values 
def compute_new_coordinates(baseline_roll, baseline_pitch, current_x, current_y):
    # baseline correction
    new_x = (ahrs.roll - baseline_roll) * 57.29578
    new_y = (ahrs.pitch - baseline_pitch) * -57.29578  
    # smoothing
    new_x = new_x + alpha * (current_x - new_x)
    new_y = new_y + alpha * (current_y - new_y)
    return new_x, new_y

# [frontend] config
auto_recording_countdown = 10.0  
stop_recording_countdown = 8.0  

# [frontend] hardware setup (button, display)
button = digitalio.DigitalInOut(board.D0)
button.switch_to_input(pull=digitalio.Pull.UP)
display = board.DISPLAY
width = display.width
height = display.height
root = displayio.Group()
display.root_group = root

# [frontend] global variables
mode = "landing"
selected_color = None
color_index = 0
countdown_start_time = time.monotonic()
recording_start_time = None
recording_stop_time = None
next_data_transmission = time.monotonic()
# True = not pressed, False = pressed 
recent_button_state = button.value 

# [frontend] UI setup - choose drawing color, record drawing, and stop recording
colors = ["black", "pink", "purple"]
choose_color_ui = displayio.Group()
instructions = [
    label.Label(terminalio.FONT, text="Select a color for your drawing:", color=0xFFFFFF, x=5, y=15),
    label.Label(terminalio.FONT, text="Press once = black",  color=0xFFFFFF, x=5, y=35),
    label.Label(terminalio.FONT, text="Press twice = Pink",  color=0xFFFFFF, x=5, y=55),
    label.Label(terminalio.FONT, text="Press again = Purple",color=0xFFFFFF, x=5, y=75),
]
countdown_label = label.Label(terminalio.FONT, text="", color=0xFFFFFF, x=5, y=height - 20)
for instruction in instructions:
    choose_color_ui.append(instruction)
choose_color_ui.append(countdown_label)
root.append(choose_color_ui)
recording_ui = displayio.Group()
recording_label = label.Label(terminalio.FONT, text="", color=0xFFFFFF, x=5, y=height // 2)
calibration_countdown_label = label.Label(terminalio.FONT, text="", color=0xFFFFFF, x=5, y=height - 20)
recording_ui.append(recording_label)
recording_ui.append(calibration_countdown_label)
recording_ui.hidden = True
root.append(recording_ui)
stop_ui = displayio.Group()
stop_label = label.Label(terminalio.FONT, text="", color=0xFFFFFF, x=5, y=height // 2)
stop_ui.append(stop_label)
stop_ui.hidden = True
root.append(stop_ui)

# [frontend] main loop 
while True:
    current_time_s = time.monotonic()
    current_button_state = button.value
    pressed_event = (recent_button_state is True) and (current_button_state is False)
    # process button presses 
    if pressed_event:
        # select drawing color 
        if mode == "landing":
            selected_color = colors[color_index]
            color_index = (color_index + 1) % len(colors)
        # stop recording 
        elif mode == "recording":
            print("Stop")
            mode = "stopping"
            recording_stop_time = current_time_s
            stop_ui.hidden = False
            choose_color_ui.hidden = True
    # landing - select color, countdown 
    if mode == "landing":
        choose_color_ui.hidden = False
        stop_ui.hidden = True
        time_passed = current_time_s - countdown_start_time
        remaining_time = int(auto_recording_countdown - time_passed)
        if selected_color is not None:
            picked = selected_color
        else:
            picked = "none"
        countdown_label.text = f"You picked the color {picked}.\nRecording starting in {remaining_time}s" 
        if remaining_time <= 0:
            if selected_color is None:
                # set to default color if no color selected by user
                selected_color = "black" 
            mode = "calibrating"
            choose_color_ui.hidden = True
            recording_ui.hidden = False
            # 5-second calibration 
            recording_label.text = "Hold device still.\nCalibrating!"
            baseline_roll, baseline_pitch = calibrate_baseline(sensor, 5.0, calibration_countdown_label)
            calibration_countdown_label.text = ""
            current_x = 0.0
            current_y = 0.0
            mode = "recording"
            print("Start")
            last_print_time = time.monotonic()
            recording_start_time = current_time_s
            next_data_transmission = current_time_s
            recording_label.text = "Currently recording!\nPress D0 to stop"
    if mode == "recording":
        # AHRS update
        current_time_ns = time.monotonic_ns()
        if (current_time_ns - last_ahrs_update_time) >= time_between_ahrs_updates:
            last_ahrs_update_time = current_time_ns
            apply_mahony_filter(sensor)
        # stream data for visualization on laptop
        if (current_time_s - last_print_time) >= time_between_prints:
            last_print_time = current_time_s
            current_x, current_y = compute_new_coordinates(baseline_roll, baseline_pitch, current_x, current_y)
            print(f"{current_x:.4f},{current_y:.4f},{selected_color}")
    # stop recording
    if mode == "stopping":
        recording_ui.hidden = True
        time_passed = current_time_s - recording_stop_time
        remaining_time = int(stop_recording_countdown - time_passed)
        stop_label.text = f"Recording stopped!\nReturning to home screen in {remaining_time}s"
        if remaining_time == 0:
            mode = "landing"
            countdown_start_time = current_time_s
            selected_color = None
            color_index = 0
            stop_ui.hidden = True
            choose_color_ui.hidden = False
    recent_button_state = current_button_state
    time.sleep(0.001)