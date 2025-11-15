import multiprocessing
import os
import json
from multiprocessing.connection import Connection, wait
from argparse import ArgumentParser
from subprocess import Popen, PIPE
from time import sleep, time
from glob import glob
import traceback
from typing import List

import cv2
import numpy as np

from data_handler import IMG_FILE_TYPE, DataHandler

PORTRAIT_SIZE = (86, 86)
CACHE_FILE = "champ_cache.json"

SIFT_FLANN_INDEX_KDTREE = 0
SIFT_INDEX_PARAMS = dict(algorithm=SIFT_FLANN_INDEX_KDTREE, trees=5)
SIFT_SEARCH_PARAMS = dict(checks=50)

SIMILARITY_THRESHOLD = 15

def get_portraits_data(data_handler: DataHandler):
    sift = cv2.SIFT_create()

    image_data = []
    for image_file in glob(f"portraits/*.{IMG_FILE_TYPE}"):
        champ_id = int(os.path.basename(image_file).removesuffix(f".{IMG_FILE_TYPE}").split("_")[0])
        image = cv2.imread(image_file, cv2.IMREAD_COLOR)
        if image is None:
            continue

        image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        image = cv2.resize(image, PORTRAIT_SIZE)

        descriptors = sift.detectAndCompute(image, None)[1]

        data = {
            "image": image,
            "champ_data": data_handler.champ_data[champ_id],
            "sift_descriptors": descriptors,
        }

        image_data.append(data)

    return image_data

def get_similarities(image, truth_images):
    similarities = []

    sift = cv2.SIFT_create()

    descriptors = sift.detectAndCompute(image, None)[1]
    flann = cv2.FlannBasedMatcher(SIFT_INDEX_PARAMS, SIFT_SEARCH_PARAMS)

    for truth_data in truth_images:
        matches = flann.knnMatch(descriptors, truth_data["sift_descriptors"], k=2)

        similarity = 0
        for m, n in matches:
            if m.distance < 0.7*n.distance:
                similarity += n.distance - m.distance

        similarity = similarity / len(matches) if len(matches) > 0 else 0

        similarities.append((truth_data, similarity))

    return similarities

def extract_portrait(image):
    wf = PORTRAIT_SIZE[0] / 1920
    hf = PORTRAIT_SIZE[1] / 1080
    x = int(image.shape[1] * 0.310416) # 600
    y = int(image.shape[0] * 0.894444) # 970
    w = int(image.shape[1] * wf) # 85
    h = int(image.shape[0] * hf) # 85

    # x = 596
    # y = 966
    # w = PORTRAIT_SIZE[0]
    # h = PORTRAIT_SIZE[1]

    square_img = image[y: y + h, x:x + w]

    # draw filled circles in white on black background as masks
    mask = np.zeros_like(square_img)
    mask = cv2.circle(mask, (w // 2, h // 2), w // 2, (255, 255, 255), -1)

    # put mask into alpha channel of input
    result = square_img & mask

    return cv2.resize(cv2.cvtColor(result, cv2.COLOR_BGRA2GRAY), PORTRAIT_SIZE)

def get_best_match(image, portraits):
    similarities = get_similarities(image, portraits)

    max_similarity = max(similarities, key=lambda x: x[1])
    if max_similarity[1] < SIMILARITY_THRESHOLD:
        return None

    return max_similarity

def process_video(filename, portraits):
    reader = cv2.VideoCapture(filename)
    fps = int(reader.get(cv2.CAP_PROP_FPS))
    frames = reader.get(cv2.CAP_PROP_FRAME_COUNT)
    interval = int(fps * 10)
    attempts = 8
    if interval * attempts > frames:
        interval = frames // attempts

    try:
        for attempt in range(attempts):
            reader.set(cv2.CAP_PROP_POS_FRAMES, interval * attempt)
            ret, frame = reader.read()

            if not ret:
                break

            portrait = extract_portrait(frame)

            best_match = get_best_match(portrait, portraits)
            if best_match is not None or attempt == attempts:
                return best_match

    finally:
        reader.release()

    return None

def worker_func(pipe_conn: Connection, portraits: List[cv2.UMat]):
    while True:
        filename = pipe_conn.recv()
        if filename is None:
            break

        match_data = process_video(filename, portraits)
        pipe_conn.send((filename, match_data))

def load_results_from_cache(filename):
    if not os.path.exists(filename):
        return None

def play_video(filename: str):
    command = [
        "vlc",
        filename,
        "--sout-all",
        "--sout",
        "#display",
        "@@u",
        "%U",
        "@@",
        "--started-from-file",
        "--no-playlist-enqueue"
    ]

    process = Popen(command, stdout=PIPE, stderr=PIPE)
    process.wait()

if __name__ == "__main__":
    data_handler = DataHandler()

    parser = ArgumentParser()
    parser.add_argument("path")
    parser.add_argument("champion", choices=[entry["name"].lower() for entry in  data_handler.champ_data.values()])
    group = parser.add_mutually_exclusive_group()
    group.add_argument("-oc", "--only-cache", action="store_true", help="Ignore raw data and only search in already cached results.")
    group.add_argument("-nc", "--no-cache", action="store_true", help="Ignore cached results and only search raw data.")

    args = parser.parse_args()

    path = args.path if args.path.endswith("/") else f"{args.path}/"

    cache_path = f"{path}{CACHE_FILE}"
    if args.no_cache or not os.path.exists(cache_path):
        cache_data = {
            "timestamp": time(),
            "patch": data_handler.patch,
            "data": {}
        }
    else:
        print("Found results in cache, loading those...")
        with open(cache_path, "r", encoding="utf-8") as fp:
            cache_data = json.load(fp)

    print("Finding unprocessed videos...")
    videos = []
    cached_videos = []
    for video in glob(f"{path}*.mp4"):
        basename = os.path.basename(video)
        cached_video_data = cache_data["data"].get(basename)
        if cached_video_data is not None:
            cached_videos.append(cached_video_data)
        elif not args.only_cache:
            videos.append(video)

    num_videos = len(videos)
    print(f"Found {len(cached_videos)} cached data, {num_videos} new videos")

    matched_videos = [
        (filename, cache_data["data"][filename]["similarity"])
        for filename in cache_data["data"]
        if cache_data["data"][filename]["champion"].lower() == args.champion
    ]
    failed_videos = []

    if num_videos > 0:
        print("Loading portraits...")
        portraits = get_portraits_data(data_handler)

        print("Starting search...")
        processed = 0
        num_processes = min(num_videos, 16)
        pipes = []
        processes = []
        for _ in range(num_processes):
            conn_1, conn_2 = multiprocessing.Pipe()
            process = multiprocessing.Process(target=worker_func, args=(conn_2, portraits))
            process.start()

            file = videos.pop(0)

            conn_1.send(file)
            pipes.append(conn_1)
            processes.append(process)

        try:
            while processed < num_videos:
                for pipe in wait(pipes):
                    filename, result = pipe.recv()

                    processed += 1

                    if result is not None:
                        champ_data, similarity = result
                        if champ_data["champ_data"]["name"].lower() == args.champion:
                            matched_videos.append((os.path.basename(filename), similarity))

                        cache_data["data"][os.path.basename(filename)] = {
                            "champion": champ_data["champ_data"]["name"],
                            "similarity": similarity,
                        }
                    else:
                        failed_videos.append(os.path.basename(filename))

                    if videos:
                        file = videos.pop(0)
                        pipe.send(file)

                    pct = int((processed / num_videos) * 100)
                    print(f"Searched {processed}/{num_videos} ({pct}%) - {len(failed_videos)} failed...", end="\r")

        except Exception as exc:
            print("Exception during search!", exc)
            traceback.print_exc()

        finally:
            with open(cache_path, "w", encoding="utf-8") as fp:
                json.dump(cache_data, fp, indent=4)

            for pipe in pipes:
                pipe.send(None)

        while any(p.is_alive() for p in processes):
            sleep(0.1)

        pct = int((processed / num_videos) * 100)
        print(f"Searched {processed}/{num_videos} ({pct}%) - {len(failed_videos)} failed.")

    if failed_videos:
        print("WARNING: Could not find champion for the following videos:")
        for video in failed_videos:
            print(f"- {video}")

    print()

    if matched_videos:
        matched_videos.sort(key=lambda x: x[0])
        print(f"'{args.champion.capitalize()}' was found in the following {len(matched_videos)} videos:")
        for index, (filename, similarity) in enumerate(matched_videos):
            print(f"({index}): {filename} (confidence={similarity:.2f})")

        print()
        print("(Optional): Play any of the videos by providing its index.")
        try:
            while True:
                video_index = input("Play video: ")
                if video_index == "":
                    break

                try:
                    filename = f"{path}{matched_videos[int(video_index)][0]}"
                    play_video(filename)
                except ValueError:
                    continue

        except KeyboardInterrupt:
            pass

    else:
        print(f"'{args.champion.capitalize()}' was not found in any video.")
