from datetime import datetime
import multiprocessing
import os
import json
from multiprocessing.connection import Connection, wait
from argparse import ArgumentParser
import shutil
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

def get_data_for_portrait(sift, data_handler: DataHandler, folder: str, filename: str):
    basename = os.path.basename(filename)
    champ_id = int(basename.removesuffix(f".{IMG_FILE_TYPE}").split("_")[0])

    cache_dir = f"{folder}/cache"
    basename = os.path.basename(filename).split(".")[0]
    cache_path = f"{cache_dir}/{basename}.npy"

    if os.path.exists(cache_path):
        with open(cache_path, "rb") as fp:
            descriptors = np.load(fp)
    else:
        if not os.path.exists(cache_dir):
            os.mkdir(cache_dir)

        image = cv2.imread(filename, cv2.IMREAD_COLOR)
        if image is None:
            return None

        image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        image = cv2.resize(image, PORTRAIT_SIZE)

        descriptors = sift.detectAndCompute(image, None)[1]

        with open(cache_path, "wb") as fp:
            np.save(fp, descriptors)

    return {
        "champ_data": data_handler.champ_data[champ_id],
        "sift_descriptors": descriptors,
    }

def get_portraits_data(data_handler: DataHandler):
    sift = cv2.SIFT_create()

    image_data = []
    for patch in data_handler.major_patches:
        major_part = patch.split(".")[0]
        folders = glob(f"portraits/{major_part}*")
        if folders == []:
            continue

        for folder in folders:
            for image_file in glob(f"{folder}/*.{IMG_FILE_TYPE}"):
                portrait_data = get_data_for_portrait(sift, data_handler, folder, image_file)
                if portrait_data is None:
                    continue

                image_data.append(portrait_data)

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

def try_get_file_date(filename):
    space_split = filename.split(" ")
    if len(space_split) == 1:
        return None

    date_split = space_split[1].split(" - ")
    if len(date_split) == 1:
        return None

    try:
        year, month, day = date_split[0].split(".")
        hour, minute, second = date_split[1].split(".")[:3]
        return datetime(year, month, day, hour, minute, second).timestamp()
    except Exception:
        return None

def extract_portrait(filename, image):
    wf = PORTRAIT_SIZE[0] / 1920
    hf = PORTRAIT_SIZE[1] / 1080

    if os.stat(filename).st_ctime < 1633600800:
        x = int(image.shape[1] * 0.3240416) # 600
        y = int(image.shape[0] * 0.9004444) # 970
    else:
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
    return max(similarities, key=lambda x: x[1])

def process_video(filename, portraits):
    reader = cv2.VideoCapture(filename)
    frames = reader.get(cv2.CAP_PROP_FRAME_COUNT)
    attempts = 10
    interval = frames // attempts

    matches = []
    try:
        for attempt in range(attempts):
            reader.set(cv2.CAP_PROP_POS_FRAMES, interval * attempt)
            ret, frame = reader.read()

            if not ret:
                break

            portrait = extract_portrait(filename, frame)

            champ_data, similarity = get_best_match(portrait, portraits)
            if similarity > SIMILARITY_THRESHOLD:
                return champ_data, similarity

            matches.append((champ_data, similarity))

    finally:
        reader.release()

    if matches == []:
        return None
    
    counts = {}
    for champ_data, similarity in matches:
        key = champ_data["champ_data"]["key"]
        counts[key] = counts.get(key, 0) + 1

    sorted_counts = sorted(list(counts.items()), key=lambda x: x[1], reverse=True)
    if sorted_counts[0][1] > attempts / 3 and (len(sorted_counts) == 1 or sorted_counts[0][1] > sorted_counts[1][1] * 2):
        for champ_data, similarity in matches:
            if champ_data["champ_data"]["key"] == sorted_counts[0][0]:
                return (champ_data, similarity)

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

def compress_portraits(data_handler: DataHandler):
    print("Compressing portrait data...")

    if data_handler.patches_to_remove:
        print("Removing old patch data")
        for patch in data_handler.patches_to_remove:
            shutil.rmtree(f"champ_data/{patch}")
            shutil.rmtree(f"portraits/{patch}")

        return

    sift = cv2.SIFT_create()

    valid_patches = [patch for patch in data_handler.major_patches + data_handler.new_patches if os.path.exists(f"portraits/{patch}")]
    for index, patch in enumerate(valid_patches[1:], start=1):
        champ_data = data_handler.fetch_champ_data(patch, False, False)
        old_files = data_handler.get_missing_portraits(patch, valid_patches[:index], champ_data)[1]
        old_descriptors = {old_file: get_data_for_portrait(sift, data_handler, patch, old_files[old_file]) for old_file in old_files}

        for filename in glob(f"portraits/{patch}/*.{IMG_FILE_TYPE}"):
            if (old_descriptor := old_descriptors.get(filename)):
                image = cv2.imread(filename, cv2.IMREAD_COLOR)
                if image is None:
                    return None

                image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
                image = cv2.resize(image, PORTRAIT_SIZE)

                similarity = get_similarities(image, [old_descriptor])[0][1]
                if similarity < 150:
                    print(f"Removing {filename} from portraits/{patch}")
                    os.remove(filename)

def play_video(filename: str):
    Popen(["haruna", filename], stdout=PIPE, stderr=PIPE).wait()

if __name__ == "__main__":
    data_handler = DataHandler()
    if data_handler.new_patches:
        compress_portraits(data_handler)

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
        cached_data = {
            "timestamp": time(),
            "patch": data_handler.latest_patch,
            "data": {},
            "ignored_data": [],
        }
    else:
        print("Found results in cache, loading those...")
        with open(cache_path, "r", encoding="utf-8") as fp:
            cached_data = json.load(fp)

        if "ignored" not in cached_data:
            cached_data["ignored_data"] = []

    print("Finding unprocessed videos...")
    videos = []
    cached_videos = []
    for video in glob(f"{path}*.mp4"):
        basename = os.path.basename(video)
        if not args.no_cache and basename in cached_data["ignored_data"]:
            continue

        cached_video_data = cached_data["data"].get(basename)
        if cached_video_data is not None:
            cached_videos.append(cached_video_data)
        elif not args.only_cache:
            videos.append(video)

    num_videos = len(videos)
    quant = "video" if num_videos == 1 else "videos"
    print(f"Found {len(cached_videos)} cached data, {num_videos} new {quant}")

    matched_videos = [
        (filename, cached_data["data"][filename]["similarity"])
        for filename in cached_data["data"]
        if cached_data["data"][filename]["champion"].lower() == args.champion
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

                        cached_data["data"][os.path.basename(filename)] = {
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
                json.dump(cached_data, fp, indent=4)

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

        while True:
            ignore_char = input("Do you wish to ignore these in the future? (y/n): ").strip()
            if ignore_char == "y":
                if "ignored_data" not in cached_data:
                    cached_data["ignored_data"] = []

                cached_data["ignored_data"].extend(failed_videos)
                cached_data["ignored_data"] = list(set(cached_data["ignored_data"]))

                with open(cache_path, "w", encoding="utf-8") as fp:
                    json.dump(cached_data, fp)

                break
 
            elif ignore_char == "n":
                break

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
                except (ValueError, IndexError):
                    continue

        except KeyboardInterrupt:
            pass

    else:
        print(f"'{args.champion.capitalize()}' was not found in any video.")
