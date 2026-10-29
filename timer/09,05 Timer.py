import cv2
import numpy as np
import time
import schedule
import requests
from ultralytics import YOLO
from google.cloud import vision
import io
import re
import os
import threading


# Change the current directory to a new one
os.chdir(r".")
print("Current working directory:", os.getcwd())

# work'-4514526146' '7837912859:AAFR-fDePI4eCPYHfFlyMtFkOIzEo4OYWY0'
# home 'YOUR_CHAT_ID' 'YOUR_TELEGRAM_BOT_TOKEN'
# Constants for Telegram Bot
TELEGRAM_TOKEN = 'YOUR_TELEGRAM_BOT_TOKEN'
CHAT_ID = 'YOUR_CHAT_ID'


# Указываем путь к JSON-ключу Google Cloud
#os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = r".\chernomorrecognizer-c5b10a14314b.json"

# Указываем путь к JSON-ключу Google Cloud
#os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = r".\odessa-463210-a9cbaf4f6a13.json"
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = r"credentials.json"

# Google Vision API
client = vision.ImageAnnotatorClient()
daily_report = []

def compute_intersection_area(frame_shape, roi_points, bbox, return_mask=False):
    mask_roi = np.zeros(frame_shape[:2], dtype=np.uint8)
    mask_bbox = np.zeros(frame_shape[:2], dtype=np.uint8)

    # POI masks
    cv2.fillPoly(mask_roi, roi_points, 1)
    x1, y1, x2, y2 = bbox
    cv2.rectangle(mask_bbox, (x1, y1), (x2, y2), 1, -1)

    intersection = cv2.bitwise_and(mask_roi, mask_bbox)
    intersection_area = np.count_nonzero(intersection)
    roi_area = np.count_nonzero(mask_roi)
    coverage_percent = (intersection_area / roi_area * 100) if roi_area else 0.0

    if return_mask:
        return coverage_percent, intersection
    return coverage_percent



def capture_second_camera(poi_name):
    """Captures a frame from the second video stream 5 seconds after the first snapshot."""

    photo_path_2 = f"{poi_name.lower()}_second_camera.jpg"

    cap2 = cv2.VideoCapture("http://cctv.example.com:555/stream2")
    time.sleep(5)  # ? Waiting 5 seconds before taking the snapshot (if possible)
    ret2, frame_2 = cap2.read()

    if ret2:
        cv2.imwrite(photo_path_2, frame_2) # ?? Saving the second snapshot
        print(f"[{poi_name}] ? Second camera snapshot saved: {photo_path_2}")
    else:
        print(f"[{poi_name}] ? Failed to capture frame from second camera")

    cap2.release()

def capture_and_send_images(poi_name, poi_time, plate_text, frame_1):
    """Sends the previously saved snapshots to Telegram."""
    photo_path_1 = f"{poi_name.lower()}_detected.jpg"
    photo_path_2 = f"{poi_name.lower()}_second_camera.jpg"

    # Checking if both snapshots are available before sending
    if not os.path.exists(photo_path_1):
        print(f"[{poi_name}] ? First snapshot missing, skipping Telegram send!")
        return
    if not os.path.exists(photo_path_2):
        print(f"[{poi_name}] ? Second snapshot missing, skipping Telegram send!")
        return

    send_photos_to_telegram(photo_path_1, photo_path_2, poi_time, plate_text, poi_name)



def send_photos_to_telegram(photo_path_1, photo_path_2, poi_time, plate_text, poi_name):
    """Sends 2 photos in a single message, but the text appears right below the first photo."""
    url_photos = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMediaGroup"

    poi_time = round(float(poi_time), 2)

    caption_text = f"{poi_name} -Time: {poi_time} sec\nCar Number: {plate_text}"

    media = [
        {"type": "photo", "media": "attach://photo1", "caption": caption_text},
        {"type": "photo", "media": "attach://photo2"}
    ]

    files = {
        "photo1": open(photo_path_1, "rb"),
        "photo2": open(photo_path_2, "rb")
    }

    payload_photos = {
        "chat_id": CHAT_ID,
        "media": str(media).replace("'", '"')
    }

    try:
        response_photos = requests.post(url_photos, data=payload_photos, files=files)
        response_photos.raise_for_status()
        print(f"{poi_name} - Photos sent successfully:", response_photos.json())
    except requests.exceptions.RequestException as e:
        print(f"Error sending photos to Telegram: {e}")
    finally:
        files["photo1"].close()
        files["photo2"].close()


# Function to add data to the daily report
def add_to_daily_report(plate_text, poi_time):
    """Adds data to the daily report."""
    current_time = time.strftime("%d.%m.%Y, %H:%M:%S")  # Current time
    report_entry = f"{len(daily_report) + 1}. {plate_text}, POI Time: {poi_time:.2f} sec, {current_time}"
    daily_report.append(report_entry)
    print(f"Added to daily report: {report_entry}")


# Function to send the final daily report message
def send_daily_message():
    if not daily_report:
        send_telegram_message("No events were registered today.")
        return

    MAX_LENGTH = 4000
    report_chunks = []
    chunk = ""

    for line in daily_report:
        if len(chunk) + len(line) + 1 < MAX_LENGTH:
            chunk += line + "\n"
        else:
            report_chunks.append(chunk)
            chunk = line + "\n"
    if chunk:
        report_chunks.append(chunk)

    for i, part in enumerate(report_chunks):
        header = f"?? Daily report (part {i + 1}/{len(report_chunks)}):\n"
        send_telegram_message(header + part)

    print(f"[{time.strftime('%H:%M:%S')}] ? Daily report sent in {len(report_chunks)} parts.")
    daily_report.clear()




# Function to send a message to Telegram
def send_telegram_message(message):
    """Sends a message to the specified Telegram chat."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        'chat_id': CHAT_ID,
        'text': message
    }
    try:
        response = requests.post(url, data=payload)
        response.raise_for_status()  # Raise an error if the request fails
        if response.status_code == 200:
            print(f"[{time.strftime('%d.%m.%Y, %H:%M:%S')}] Message sent successfully: {message}")
            return True
        else:
            print(
                f"[{time.strftime('%d.%m.%Y, %H:%M:%S')}] Failed to send message, received status code: {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"[{time.strftime('%d.%m.%Y, %H:%M:%S')}] Error sending message to Telegram: {e}")
        return False


# Function to run the scheduler in a separate thread
def scheduler_thread():
    """Runs the scheduler in a separate thread to check scheduled tasks."""
    while True:
        print(f"[{time.strftime('%d.%m.%Y, %H:%M:%S')}] Checking scheduled tasks...")
        schedule.run_pending()  # Execute scheduled tasks
        time.sleep(600)  # Wait for 10 minutes before the next check


# Start the scheduler in a separate thread
scheduler = threading.Thread(target=scheduler_thread, daemon=True)
scheduler.start()

# Schedule the daily summary message to be sent every day at 12:30 PM
schedule.every().day.at("23:50").do(send_daily_message)

def detect_license_plate_text(image_path, retries=3, delay=2):
    def format_plate_number(plate):

        return re.sub(r"^([A-Z?-?]{2,3})\s?(\d{3,4})\s?([A-Z?-?]{2,3})$", r"\1 \2 \3", plate)

    for attempt in range(1, retries + 1):
        try:
            with io.open(image_path, "rb") as image_file:
                content = image_file.read()

            image = vision.Image(content=content)
            response = client.text_detection(image=image)
            break
        except Exception as e:
            print(f"? ?????? Vision API (??????? {attempt}/{retries}): {e}")
            if attempt == retries:
                return ["Vision API Error"]
            time.sleep(delay)

    texts = response.text_annotations
    if not texts:
        print("? ?????? ?? ??????????.")
        return []

    detected_texts = texts[0].description.strip().split("\n")
    print(f"?? ??? ???????????? ??????: {detected_texts}")

    excluded_words = {"PROMETEY", "DAF", "WIELTON", "TRUCK", "TAG_vesovaya_1", "BRAIN TEARING COMPAR"}
    filtered_texts = [text for text in detected_texts if text.upper() not in excluded_words]

    plate_pattern = re.compile(
        r'^[A-ZА-Я]{1}\s?\d{4}\s?[A-ZА-Я]{2}$|'  # A1234BC
        r'^[A-ZА-Я]{2}\s?\d{3,4}\s?[A-ZА-Я]{1,3}$|'  # AB1234C or AB 123 CD
        r'^[A-ZА-Я]{1,3}-?\d{3,4}-?[A-ZА-Я]{1,3}$|'  # AB-1234-CD or A-1234-B
        r'^\d{3,5}\s?[A-ZА-Я]{1,3}$|'  # 12345 AB
        r'^[A-ZА-Я]{1,3}\s?\d{3,5}$|'  # AB 12345
        r'^[A-ZА-Я0-9]{5,8}$'  # Compact format
    )

    plate_numbers = [
        format_plate_number(text) for text in filtered_texts
        if plate_pattern.match(text)
        and any(c.isdigit() for c in text)
        and any(c.isalpha() for c in text)
    ]

    if plate_numbers:
        print(f"? ????????? ??????: {plate_numbers}")
        return plate_numbers
    else:
        print("? ????????????? ?????? ?? ???????.")
        return []

def iou(boxA, boxB):
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[2], boxB[2])
    yB = min(boxA[3], boxB[3])

    interArea = max(0, xB - xA) * max(0, yB - yA)
    boxAArea = (boxA[2] - boxA[0]) * (boxA[3] - boxA[1])
    boxBArea = (boxB[2] - boxB[0]) * (boxB[3] - boxB[1])

    if (boxAArea + boxBArea - interArea) == 0:
        return 0
    return interArea / float(boxAArea + boxBArea - interArea)



model = YOLO(r".\models\yolo11m.pt")

# Set up the video stream from the URL
stream_url = "http://cctv.example.com:555/stream1"
cap = cv2.VideoCapture(stream_url)

# Define video writer for output
fourcc = cv2.VideoWriter_fourcc(*'MJPG')
video_out = cv2.VideoWriter('output.avi', fourcc, 20.0, (1280, 720))


# ?????????? ??????
shift_amount = 200  # ????? ???????????? ??????
top_shift = 100  # ????? ??????? ??????? ????
left_shift = 200  # ????? ????? ??????? ROI2 ?????
right_shift = 350  # ????? ?????? ??????? ROI2 ??? ?????

left_shift_poi1 = 150  # ???????? ????? ??????? ROI1 ??????
right_shift_poi1 = 200  # ???????? ?????? ??????? ROI1 ??????

roi_points1 = np.array([[
    (600 + shift_amount + left_shift_poi1, 1000),  # ???????? ????? ??????? ??????
    (600 + shift_amount + left_shift_poi1, 0 + top_shift),  # ???????? ??????? ??????? ????
    (2200 + right_shift_poi1, 0 + top_shift),  # ???????? ?????? ??????? ??????
    (2200 + right_shift_poi1, 1000)  # ???????? ?????? ??????? ??????
]], dtype=np.int32)

roi_points2 = np.array([[
    (3000 - left_shift, 0 + top_shift),  # ???? ??????, ??? ??????
    (3000 - left_shift, 1000),
    (4800 - shift_amount - right_shift, 1000),  # ??? ?????
    (4800 - shift_amount - right_shift, 0 + top_shift)  # ??? ?????
]], dtype=np.int32)




class EventTimer:
    def __init__(self):
        self.start_time = None
        self.total_time = 0
        self.is_active = False

    def start(self):
        if not self.is_active:
            self.start_time = time.time()
            self.is_active = True
            print("Timer started")

    def stop(self):
        if self.is_active:
            elapsed = time.time() - self.start_time
            self.total_time += elapsed
            self.start_time = None
            self.is_active = False
            print(f"Timer stopped, total time: {self.total_time:.2f} sec")

    def reset(self):
        print(f"[TIMER] Resetting. Previous total time: {self.total_time:.2f} sec.")
        self.start_time = None
        self.total_time = 0
        self.is_active = False
        print("Timer reset")

    def get_total_time(self):
        if self.is_active:
            return self.total_time + (time.time() - self.start_time)
        return self.total_time


# Create timers for each POI
poi_timers = {
    "POI1": {"timer": EventTimer(), "photo_path": None},
    "POI2": {"timer": EventTimer(), "photo_path": None}
}

# ?? ?????? ?????????? ? ????????? ???????? ??????? ??? ??????? POI
last_active_objects = {"POI1": None, "POI2": None}


def reconnect_stream(url, delay=5):
    """Reconnects to the video stream if the connection fails."""
    cap.release()
    time.sleep(delay)
    new_cap = cv2.VideoCapture(url)
    if new_cap.isOpened():
        print("Reconnected to the video stream.")
    else:
        print("Reconnection failed. Retrying...")
    return new_cap


def draw_timer_with_background(frame, text, position, font_scale=1.5, font_thickness=2):
    """Draw timer text with a background box."""
    (text_width, text_height), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, font_thickness)
    x, y = position
    overlay = frame.copy()
    cv2.rectangle(overlay, (x, y - text_height - 20), (x + text_width + 20, y + 10), (0, 0, 0), -1)
    frame = cv2.addWeighted(overlay, 0.7, frame, 0.3, 0)
    cv2.putText(frame, text, (x + 10, y), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 255, 0), font_thickness)
    return frame


def is_object_in_roi(centroid, roi_points):
    """Check if the object is within the ROI."""
    return cv2.pointPolygonTest(roi_points, centroid, False) >= 0


def get_largest_object(detected_objects):
    """
    ???????? bounding box ?????? ???????? ??????? ? POI.
    """
    if not detected_objects:
        return None
    return max(detected_objects, key=lambda obj: obj["area"])  # ???????? ?????? ? ?????????? ????????

output_window_size = (1280, 360)

# Main loop for processing video frames
while True:

    schedule.run_pending()
    # FPS calculation start
    fps_start_time = cv2.getTickCount()

    ret, frame = cap.read()

    if not ret:
        print("Failed to retrieve the frame. Reconnecting...")
        cap = reconnect_stream(stream_url)
        continue

    clean_frame = frame.copy()  # ?? ????????? ???????? ??? ????????? ? ?????

    # Perform inference using YOLOv8
    results = model(frame, conf=0.25, verbose=False)

    class_ids, confidences, boxes, centers = [], [], [], []

    for result in results:
        if hasattr(result, 'boxes'):
            for detection in result.boxes.data.numpy():
                x1, y1, x2, y2, conf, class_id = detection
                if conf > 0.25:
                    class_name = model.names[int(class_id)]
                    if class_name in ["truck", "bus", "large vehicle"]:
                        box = [int(x1), int(y1), int(x2 - x1), int(y2 - y1)]
                        boxes.append(box)
                        confidences.append(float(conf))
                        class_ids.append(int(class_id))
                        centers.append((int((x1 + x2) / 2), int((y1 + y2) / 2)))

    # ?? ????????? ???????? (?????????????)
    FRAME_THRESHOLD_SMALL_OBJECTS = 4  # ??????, ?????? ??? ???????? ?? ??????????? ???????
    FRAME_THRESHOLD_MISSING_OBJECTS = 4  # ??????, ?????? ??? ???????? ?? ?????????? ???????
    MIN_VALID_TIME = 25.0  # ? ??????????? ?????????? ?????, ????? ??????? ??????? ????????
    MIN_COVERAGE_PERCENT = 55  # ??????????? ??????????, ????? ??????? ?????? ????????
    # ?? ?????????????? ???????? ??????, ???? ??? ???????????
    for poi in ["POI1", "POI2"]:
        if "small_object_count" not in poi_timers[poi]:
            poi_timers[poi]["small_object_count"] = 0
        if "missing_object_count" not in poi_timers[poi]:
            poi_timers[poi]["missing_object_count"] = 0

    # ?? Apply Non-Maximum Suppression (NMS)
    if boxes:
        indexes = cv2.dnn.NMSBoxes(boxes, confidences, 0.5, 0.4)
        indexes = indexes.flatten() if len(indexes) > 0 else []
    else:
        indexes = []  # ???????? ??????, ???? ???????? ???

    for i in range(len(boxes)):
        if i in indexes:
            x, y, w, h = boxes[i]
            label = str(model.names[class_ids[i]])
            color = (0, 255, 0)

            cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
            cv2.putText(frame, label, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 1.5, color, 2)

    for poi, roi_points in zip(["POI1", "POI2"], [roi_points1, roi_points2]):
        timer_data = poi_timers[poi]
        roi_area = cv2.contourArea(roi_points[0])

        detected_objects = []  # ?????? ???????? ? ??????? POI

        for i in range(len(boxes)):
            if i in indexes:
                x, y, w, h = boxes[i]
                object_area = w * h
                object_id = (x, y, x + w, y + h)  # ?????????? bbox
                center = (x + w // 2, y + h // 2)

                if is_object_in_roi(center, roi_points):
                    detected_objects.append({"area": object_area, "bbox": object_id, "index": i})

        # ???????? **????? ??????? ??????** ? POI
        largest_obj = get_largest_object(detected_objects)

        iou_threshold = 0.3
        current_bbox = largest_obj["bbox"] if largest_obj else None
        last_bbox = last_active_objects[poi]

        if last_bbox is not None and current_bbox is not None:
            if iou(current_bbox, last_bbox) < iou_threshold:
                print(f"[{poi}] ? IoU too low — ?????? ?????? ??? ????. ????? last_active.")
                last_active_objects[poi] = None
        elif current_bbox is None:
            last_active_objects[poi] = None


        if largest_obj:
            i = largest_obj["index"]
            x, y, w, h = boxes[i]
            x1, y1, x2, y2 = largest_obj["bbox"]




            coverage_percent, intersection_mask = compute_intersection_area(frame.shape, [roi_points[0]],
                                                                            (x1, y1, x2, y2), return_mask=True)
            print(f"{poi} - Object detected with area coverage: {coverage_percent:.2f}%")
            # ????????????: ??????? ??????? ????? ?? ???????????? ????
            colored_mask = np.zeros_like(frame)
            colored_mask[intersection_mask == 1] = (0, 255, 0)  # ??????? ???? ??? ??????????

            # ?????????? ? ???????????? ??????
            frame = cv2.addWeighted(frame, 1.0, colored_mask, 0.4, 0)

            # 1?? ???? ?????? ??????? ?????????
            if coverage_percent < 55:
                timer_data["small_object_count"] += 1
                print(
                    f"[{poi}] ?? Object too small ({coverage_percent:.2f}%) for {timer_data['small_object_count']} frames.")

                if timer_data["small_object_count"] >= FRAME_THRESHOLD_SMALL_OBJECTS:
                    print(f"[{poi}] ? Reached small object threshold.")

                    if timer_data["timer"].is_active:
                        timer_data["timer"].stop()
                        poi_time = timer_data["timer"].get_total_time()
                        timer_data["timer"].reset()

                        plate_numbers = detect_license_plate_text(timer_data["photo_path"]) if timer_data[
                            "photo_path"] else ["Unknown number"]
                        plate_text = ", ".join(plate_numbers)

                        if poi_time >= MIN_VALID_TIME:
                            add_to_daily_report(plate_text, poi_time)
                            print(f"[{poi}] ? Timer stopped due to small object size, time: {poi_time:.2f} sec")

                            if timer_data["photo_path"]:
                                capture_and_send_images(poi, poi_time, plate_text, frame)
                                timer_data["photo_path"] = None
                        else:
                            print(f"[{poi}] ?? Skipped (too short): {poi_time:.2f} sec — below {MIN_VALID_TIME} sec")
                    else:
                        print(f"[{poi}] ?? Timer was not active, cleaning up anyway.")

                    # ??????? ??????, ?????????? ?? ????????? ???????
                    last_active_objects[poi] = None
                    timer_data["small_object_count"] = 0
                    timer_data["missing_object_count"] = 0


            # 2?? ???? ?????? ?????????? ??????? ? ?????????/????????? ??????
            else:
                timer_data["small_object_count"] = 0  # ????? ????????
                if timer_data["timer"].is_active:
                    print(
                        f"[{poi}] ? Timer is already running. Elapsed time: {timer_data['timer'].get_total_time():.2f} sec")
                    last_active_objects[poi] = largest_obj["bbox"]
                else:
                    if last_active_objects[poi] != largest_obj["bbox"]:
                        print(f"[{poi}] ?? Starting timer now!")
                        timer_data["timer"].start()
                        timer_data["photo_path"] = f"{poi.lower()}_detected.jpg"

                        cv2.imwrite(timer_data["photo_path"], clean_frame)


                        # ?????? ??????? ??? ?????? ?????? (??????? ?????? ????? 5 ???)
                        threading.Timer(5.0, capture_second_camera, args=(poi,)).start()

                        last_active_objects[poi] = largest_obj["bbox"]

    # 4?? ???? ?????? ??? ????????, ??????? ????? ??????????
    for poi, timer_data in poi_timers.items():
        if timer_data["timer"].is_active:
            if last_active_objects[poi] is None:
                timer_data["missing_object_count"] += 1
                print(f"[{poi}] ?? Object missing for {timer_data['missing_object_count']} frames.")

                # ???? ?????? ??????????? ? ????? ?????? X ?????? – ?????????? ??????
                if timer_data["missing_object_count"] >= FRAME_THRESHOLD_MISSING_OBJECTS:
                    print(f"[{poi}] ? Object missing for {FRAME_THRESHOLD_MISSING_OBJECTS} frames, resetting timer!")
                    timer_data["timer"].stop()
                    poi_time = timer_data["timer"].get_total_time()
                    timer_data["timer"].reset()
                    last_active_objects[poi] = None
                    timer_data["out_roi_count"] = 0
                    timer_data["small_object_count"] = 0
                    timer_data["missing_object_count"] = 0

                    plate_numbers = detect_license_plate_text(timer_data["photo_path"]) if timer_data[
                        "photo_path"] else ["Unknown number"]
                    plate_text = ", ".join(plate_numbers)

                    if poi_time >= MIN_VALID_TIME:
                        add_to_daily_report(plate_text, poi_time)
                        print(
                            f"[{poi}] ? Timer stopped due to object missing for {FRAME_THRESHOLD_MISSING_OBJECTS} frames, time: {poi_time:.2f} sec")

                        if timer_data["photo_path"]:
                            capture_and_send_images(poi, poi_time, plate_text, frame)
                            timer_data["photo_path"] = None
                    else:
                        print(f"[{poi}] ?? Skipped (too short): {poi_time:.2f} sec — below {MIN_VALID_TIME} sec")



    # Draw ROI areas
    cv2.polylines(frame, [roi_points1], isClosed=True, color=(0, 0, 255), thickness=3)
    cv2.polylines(frame, [roi_points2], isClosed=True, color=(255, 0, 0), thickness=3)

    # Draw timer with background for POI1 and POI2
    frame = draw_timer_with_background(frame, f"POI1 Time: {poi_timers['POI1']['timer'].get_total_time():.1f}s",
                                       (50, 50))
    frame = draw_timer_with_background(frame, f"POI2 Time: {poi_timers['POI2']['timer'].get_total_time():.1f}s",
                                       (50, 120))

    # Calculate FPS
    fps_end_time = cv2.getTickCount()
    time_diff = (fps_end_time - fps_start_time) / cv2.getTickFrequency()
    fps = 1 / time_diff

    # Display FPS in console
    #####print(f"FPS: {fps:.2f}")

    # Display FPS on the frame
    cv2.putText(frame, f"FPS: {fps:.2f}", (frame.shape[1] - 150, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 0), 2,
                cv2.LINE_AA)

    # Display frame
    cv2.imshow("Detection", cv2.resize(frame, output_window_size))


    # ? Independent Timer Check
    for poi in ["POI1", "POI2"]:
        timer_data = poi_timers[poi]
        if timer_data["timer"].is_active:
            total_time = timer_data["timer"].get_total_time()
            if total_time > 300:
                print(f"[{poi}] Auto-reset (independent check): Timer exceeded 300 sec!")

                roi_check = any(
                    is_object_in_roi(center, roi_points1) for center in centers) if poi == "POI1" else \
                    any(is_object_in_roi(center, roi_points2) for center in centers)

                print(f"[DEBUG] {poi} - Independent check: Object still in ROI? {roi_check}")

                if roi_check:
                    print(f"[{poi}] Still in ROI. Not resetting.")
                else:
                    print(f"[{poi}] Left ROI. Resetting (independent check).")

                    timer_data["timer"].stop()
                    print(f"[{poi}] Timer stopped (independent check), total time: {total_time:.2f} sec")
                    timer_data["timer"].reset()
                    print(f"[{poi}] Timer reset completed! (Independent check)")

                    plate_numbers = detect_license_plate_text(timer_data["photo_path"]) if timer_data["photo_path"] else ["Unknown number"]
                    plate_text = ", ".join(plate_numbers)

                    if total_time >= MIN_VALID_TIME:
                        add_to_daily_report(plate_text, total_time)
                        print(f"[{poi}] ? Timer stopped due to: Timer exceeded 300 sec (Independent check), time: {total_time:.2f} sec")

                        if timer_data["photo_path"]:
                            capture_and_send_images(poi, total_time, plate_text, frame)
                            timer_data["photo_path"] = None
                    else:
                        print(f"[{poi}] ?? Skipped (too short): {total_time:.2f} sec — below {MIN_VALID_TIME} sec")



    # Key press handling
    key = cv2.waitKey(1) & 0xFF

    if key == ord('q'):
        # Exit program
        print("?? Exiting program.")
        cap.release()
        video_out.release()
        cv2.destroyAllWindows()
        break

    elif key == ord('1'):
        if not poi_timers["POI1"]["timer"].is_active:
            poi_timers["POI1"]["timer"].start()
            print("?? Timer POI1 started manually.")

        timer_data = poi_timers["POI1"]
        timer_data["photo_path"] = "poi1_manual.jpg"
        cv2.imwrite(timer_data["photo_path"], frame)
        print("?? Photo saved for POI1.")

    elif key == ord('2'):
        if poi_timers["POI1"]["timer"].is_active:
            poi_time = poi_timers["POI1"]["timer"].get_total_time()
            timer_data = poi_timers["POI1"]

            plate_numbers = detect_license_plate_text(timer_data["photo_path"]) if timer_data["photo_path"] else [
                "Unknown number"]
            plate_text = ", ".join(plate_numbers)

            if poi_time >= MIN_VALID_TIME:
                add_to_daily_report(plate_text, poi_time)
                print(f"?? POI1 - Timer reset manually, time: {poi_time:.2f} sec")
                print("?? Photo path:", timer_data["photo_path"])

                if timer_data["photo_path"]:
                    capture_and_send_images("POI1", poi_time, plate_text, frame)
            else:
                print(f"?? POI1 - Skipped manual reset: {poi_time:.2f} sec < {MIN_VALID_TIME} sec")

            poi_timers["POI1"]["timer"].reset()
            print("?? POI1 timer reset manually.")

    elif key == ord('3'):
        if not poi_timers["POI2"]["timer"].is_active:
            poi_timers["POI2"]["timer"].start()
            print("?? Timer POI2 started manually.")

        timer_data = poi_timers["POI2"]
        timer_data["photo_path"] = "poi2_manual.jpg"
        cv2.imwrite(timer_data["photo_path"], frame)
        print("?? Photo saved for POI2.")

    elif key == ord('4'):
        if poi_timers["POI2"]["timer"].is_active:
            poi_time = poi_timers["POI2"]["timer"].get_total_time()
            timer_data = poi_timers["POI2"]

            plate_numbers = detect_license_plate_text(timer_data["photo_path"]) if timer_data["photo_path"] else [
                "Unknown number"]
            plate_text = ", ".join(plate_numbers)

            if poi_time >= MIN_VALID_TIME:
                add_to_daily_report(plate_text, poi_time)
                print(f"?? POI2 - Timer reset manually, time: {poi_time:.2f} sec")
                print("?? Photo path:", timer_data["photo_path"])

                if timer_data["photo_path"]:
                    capture_and_send_images("POI2", poi_time, plate_text, frame)
            else:
                print(f"?? POI2 - Skipped manual reset: {poi_time:.2f} sec < {MIN_VALID_TIME} sec")

            poi_timers["POI2"]["timer"].reset()
            print("?? POI2 timer reset manually.")
